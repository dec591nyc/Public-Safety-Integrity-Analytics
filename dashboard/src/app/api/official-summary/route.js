import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import pool from '@/utils/db';

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const selectedMonth = searchParams.get('month') || '202604';
  const key = `official-summary_${selectedMonth}`;

  // 1. Try Supabase Postgres first if connected
  if (pool) {
    try {
      const client = await pool.connect();
      try {
        const result = await client.query(
          "SELECT summary_json FROM official_summaries WHERE source_month = $1",
          [key]
        );
        if (result.rows.length > 0) {
          return NextResponse.json(result.rows[0].summary_json);
        }
      } finally {
        client.release();
      }
    } catch (e) {
      console.warn(`Database query failed for ${key}, falling back to static file:`, e);
    }
  }

  // 2. Fallback to local static JSON file in public folder
  try {
    const filePath = path.join(process.cwd(), `public/static_api/${key}.json`);
    if (fs.existsSync(filePath)) {
      const fileContent = fs.readFileSync(filePath, 'utf-8');
      return NextResponse.json(JSON.parse(fileContent));
    }
  } catch (e) {
    console.error(`Failed to read fallback ${key}.json:`, e);
  }

  // 3. Last resort fallback
  return NextResponse.json({
    source_month: selectedMonth,
    source_url: "https://statis.moi.gov.tw/micst/webMain.aspx",
    dataset_id: "9603",
    total_cases: 0,
    total_change_pct: 0,
    safety_index: 0,
    monthly_counts: [{"month": selectedMonth, "count": 0}],
    category_counts: [],
    iccs_breakdown: [],
    flags_summary: {},
    topic_drilldowns: [],
    region_weighted_counts: [],
    region_metric: "詐欺背信",
    region_counts: [],
    quality: {
      raw_rows: 0, "selected_rows": 0, "duplicate_rows_dropped": 0,
      "metric_count": 0, "matched_metric_totals": 0, "invalid_cells": 0, "dash_value_count": 0
    },
    summary: {
      text: "尚未下載或載入官方統計資料。請在資料庫上載入數據，並將預編譯檔案上傳至 Supabase。",
      method: "Fallback placeholder"
    }
  });
}
