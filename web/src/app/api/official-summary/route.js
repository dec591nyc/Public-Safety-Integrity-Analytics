import { unstable_cache } from 'next/cache';
import { NextResponse } from 'next/server';
import pool from '@/utils/db';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const revalidate = 3600;

const CACHE_HEADERS = {
  'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=86400',
};

const hasAnnualComparisonRows = (value) => (
  value &&
  Array.isArray(value.rows) &&
  value.rows.length > 0
);

const pctChange = (current, previous) => {
  const currentNum = Number(current || 0);
  const previousNum = Number(previous || 0);
  if (!previousNum) {
    return null;
  }
  return Number((((currentNum - previousNum) / previousNum) * 100).toFixed(1));
};

async function getStoredAnnualComparison(reportKey) {
  try {
    const result = await pool.query(
      'SELECT annual_comparison FROM crime_summary_reports WHERE report_key = $1',
      [reportKey]
    );
    return result.rows[0]?.annual_comparison || null;
  } catch (e) {
    if (e.code === '42703') {
      return null;
    }
    throw e;
  }
}

async function buildAnnualComparisonFromReports(reportKey) {
  const isAnnual = reportKey.endsWith('_annual');
  const selectedYear = isAnnual ? Number(reportKey.split('_')[0]) : Number(reportKey.slice(0, 4));
  if (!selectedYear) {
    return null;
  }

  let selectedMonthNum = isAnnual ? 12 : Number(reportKey.slice(4, 6));
  if (isAnnual) {
    const monthResult = await pool.query(
      `
      SELECT MAX(source_month) AS selected_month
      FROM crime_summary_reports
      WHERE report_type = 'monthly'
        AND source_year = $1
      `,
      [selectedYear]
    );
    selectedMonthNum = Number(monthResult.rows[0]?.selected_month || selectedMonthNum);
  }

  if (!selectedMonthNum || selectedMonthNum < 1 || selectedMonthNum > 12) {
    return null;
  }

  const result = await pool.query(
    `
    SELECT
      source_year AS year,
      SUM(total_cases)::bigint AS total,
      COUNT(*)::int AS months_covered
    FROM crime_summary_reports
    WHERE report_type = 'monthly'
      AND source_year <= $1
      AND source_month <= $2
    GROUP BY source_year
    ORDER BY source_year ASC
    `,
    [selectedYear, selectedMonthNum]
  );

  const rowsAsc = result.rows
    .map((row) => ({
      year: Number(row.year),
      total: Number(row.total || 0),
      months_covered: Number(row.months_covered || 0),
      yoy_pct: null,
    }))
    .filter((row) => row.year && row.months_covered > 0)
    .slice(-8);

  if (rowsAsc.length === 0) {
    return null;
  }

  let previousTotal = null;
  for (const row of rowsAsc) {
    row.yoy_pct = pctChange(row.total, previousTotal);
    if (row.total) {
      previousTotal = row.total;
    }
  }

  const selectedMonth = `${selectedYear}${String(selectedMonthNum).padStart(2, '0')}`;
  const periodLabel = `1-${selectedMonthNum}月同期`;

  return {
    period_label: periodLabel,
    selected_year: selectedYear,
    selected_month: selectedMonth,
    rows: [...rowsAsc].reverse(),
    peak_months: [],
    change_drivers: [],
    full_year_change_drivers: [],
    note: '此區塊由既有月報表重建年度 KPI；完整高峰月與案件拆解會在 n8n 重新產生 summary cache 後顯示。',
  };
}

async function resolveAnnualComparison(reportKey, cachedValue = null) {
  if (hasAnnualComparisonRows(cachedValue)) {
    return cachedValue;
  }

  const storedValue = await getStoredAnnualComparison(reportKey);
  if (hasAnnualComparisonRows(storedValue)) {
    return storedValue;
  }

  return buildAnnualComparisonFromReports(reportKey);
}

const getSummaryReport = unstable_cache(
  async (reportKey) => {
    let payloadResult = null;
    try {
      payloadResult = await pool.query(
        'SELECT payload FROM crime_summary_payload_cache WHERE cache_key = $1',
        [`official-summary:${reportKey}`]
      );
    } catch (e) {
      if (e.code !== '42P01') {
        throw e;
      }
    }

    if (payloadResult?.rows[0]?.payload) {
      const payload = payloadResult.rows[0].payload;
      const annualComparison = await resolveAnnualComparison(reportKey, payload.annual_comparison);
      return annualComparison
        ? { ...payload, annual_comparison: annualComparison }
        : payload;
    }

    const isAnnual = reportKey.endsWith('_annual');
    const year = isAnnual ? parseInt(reportKey.split('_')[0], 10) : null;

    const result = await pool.query(
      `
      WITH report AS (
        SELECT
          report_key,
          report_type,
          source_url,
          dataset_id,
          total_cases,
          total_change_pct,
          safety_index,
          category_counts,
          iccs_breakdown,
          flags_summary,
          topic_drilldowns,
          region_weighted_counts,
          region_counts,
          quality,
          summary
        FROM crime_summary_reports
        WHERE report_key = $1
      ),
      monthly_counts AS (
        SELECT COALESCE(
          json_agg(json_build_object('month', report_key, 'count', total_cases) ORDER BY report_key ASC),
          '[]'::json
        ) AS items
        FROM crime_summary_reports
        WHERE report_type = 'monthly'
          AND (
            ($2::boolean = true AND report_key LIKE $3)
            OR ($2::boolean = false AND report_key <= $1)
          )
      )
      SELECT report.*, monthly_counts.items AS monthly_counts
      FROM report
      CROSS JOIN monthly_counts
      `,
      [reportKey, isAnnual, isAnnual ? `${year}%` : '']
    );

    const summary = result.rows[0];
    if (!summary) {
      return null;
    }

    return {
      source_month: summary.report_key,
      source_url: summary.source_url,
      dataset_id: summary.dataset_id,
      total_cases: summary.total_cases,
      total_change_pct: summary.total_change_pct ? parseFloat(summary.total_change_pct) : null,
      safety_index: summary.safety_index,
      monthly_counts: summary.monthly_counts || [],
      category_counts: summary.category_counts,
      iccs_breakdown: summary.iccs_breakdown,
      flags_summary: summary.flags_summary,
      topic_drilldowns: summary.topic_drilldowns,
      annual_comparison: await resolveAnnualComparison(reportKey),
      region_weighted_counts: summary.region_weighted_counts,
      region_metric: 'è©æ¬ºèƒŒä¿¡',
      region_counts: summary.region_counts,
      quality: summary.quality,
      summary: summary.summary,
    };
  },
  ['official-summary-report'],
  { revalidate: 3600 }
);

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const selectedMonth = searchParams.get('month') || '202604';

  if (!pool) {
    return NextResponse.json({ error: 'Database not connected' }, { status: 500 });
  }

  try {
    const payload = await getSummaryReport(selectedMonth);

    if (!payload) {
      return NextResponse.json({ error: `Report ${selectedMonth} not found` }, { status: 404 });
    }

    return NextResponse.json(payload, { headers: CACHE_HEADERS });
  } catch (e) {
    console.error(`Database query failed for ${selectedMonth}:`, e);
    return NextResponse.json({ error: 'Failed to fetch report summary' }, { status: 500 });
  }
}
