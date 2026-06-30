import { NextResponse } from 'next/server';
import pool from '@/utils/db';

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const selectedMonth = searchParams.get('month') || '202604';

  if (!pool) {
    return NextResponse.json({ error: "Database not connected" }, { status: 500 });
  }

  try {
    const client = await pool.connect();
    try {
      let summary = null;
      let monthlyCounts = [];
      
      const isAnnual = selectedMonth.endsWith('_annual');
      const reportKey = selectedMonth;
      
      const result = await client.query(
        "SELECT * FROM crime_summary_reports WHERE report_key = $1",
        [reportKey]
      );
      
      if (result.rows.length > 0) {
        summary = result.rows[0];
        
        if (isAnnual) {
          const year = parseInt(selectedMonth.split('_')[0], 10);
          const countsResult = await client.query(
            "SELECT report_key AS month, total_cases AS count FROM crime_summary_reports WHERE report_type = 'monthly' AND report_key LIKE $1 ORDER BY report_key ASC",
            [`${year}%`]
          );
          monthlyCounts = countsResult.rows;
        } else {
          const countsResult = await client.query(
            "SELECT report_key AS month, total_cases AS count FROM crime_summary_reports WHERE report_type = 'monthly' AND report_key <= $1 ORDER BY report_key ASC",
            [selectedMonth]
          );
          monthlyCounts = countsResult.rows;
        }
      }

      if (summary) {
        const payload = {
          source_month: summary.report_key,
          source_url: summary.source_url,
          dataset_id: summary.dataset_id,
          total_cases: summary.total_cases,
          total_change_pct: summary.total_change_pct ? parseFloat(summary.total_change_pct) : null,
          safety_index: summary.safety_index,
          monthly_counts: monthlyCounts,
          category_counts: summary.category_counts,
          iccs_breakdown: summary.iccs_breakdown,
          flags_summary: summary.flags_summary,
          topic_drilldowns: summary.topic_drilldowns,
          region_weighted_counts: summary.region_weighted_counts,
          region_metric: "詐欺背信",
          region_counts: summary.region_counts,
          quality: summary.quality,
          summary: summary.summary
        };
        return NextResponse.json(payload);
      } else {
        return NextResponse.json({ error: `Report ${selectedMonth} not found` }, { status: 404 });
      }
    } finally {
      client.release();
    }
  } catch (e) {
    console.error(`Database query failed for ${selectedMonth}:`, e);
    return NextResponse.json({ error: "Failed to fetch report summary" }, { status: 500 });
  }
}
