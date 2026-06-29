import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import pool from '@/utils/db';

export async function GET() {
  // 1. Try Supabase Postgres first if connected
  if (pool) {
    try {
      const client = await pool.connect();
      try {
        const result = await client.query(
          "SELECT summary_json FROM official_summaries WHERE source_month = 'months'"
        );
        if (result.rows.length > 0) {
          return NextResponse.json(result.rows[0].summary_json);
        }
      } finally {
        client.release();
      }
    } catch (e) {
      console.warn("Database query failed, falling back to static file:", e);
    }
  }

  // 2. Fallback to local static JSON file in public folder
  try {
    const filePath = path.join(process.cwd(), 'public/static_api/months.json');
    if (fs.existsSync(filePath)) {
      const fileContent = fs.readFileSync(filePath, 'utf-8');
      return NextResponse.json(JSON.parse(fileContent));
    }
  } catch (e) {
    console.error("Failed to read fallback months.json:", e);
  }

  // 3. Last resort fallback
  return NextResponse.json({ items: [{ source_month: "202604", count: 0 }] });
}
