import { NextResponse } from 'next/server';
import pool from '@/utils/db';

export async function GET() {
  if (!pool) {
    return NextResponse.json({ error: "Database not connected" }, { status: 500 });
  }

  try {
    const client = await pool.connect();
    try {
      const result = await client.query(
        "SELECT report_key AS source_month, total_cases AS count FROM crime_summary_reports WHERE report_type = 'monthly' ORDER BY report_key DESC"
      );
      return NextResponse.json({ items: result.rows });
    } finally {
      client.release();
    }
  } catch (e) {
    console.error("Database query failed:", e);
    return NextResponse.json({ error: "Failed to fetch months list" }, { status: 500 });
  }
}
