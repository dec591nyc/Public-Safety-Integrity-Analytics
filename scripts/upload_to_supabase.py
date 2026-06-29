#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sync pre-compiled JSON summaries (months.json, official-summary_*.json) to Supabase Database."""

import os
import json
import sqlite3
from pathlib import Path

def main():
    pg_url = os.environ.get("PUBLIC_SAFETY_DATABASE_URL")
    if not pg_url:
        print("Error: PUBLIC_SAFETY_DATABASE_URL environment variable is not set. Skipping upload.")
        return

    # Check connection type and import psycopg2
    try:
        import psycopg2
        from psycopg2.extras import Json
    except ImportError:
        print("psycopg2 is not installed. Please run: pip install psycopg2-binary")
        return

    static_api_dir = Path("web/static_api")
    if not static_api_dir.exists():
        print(f"Error: {static_api_dir} does not exist. Please run generate_static_json.py first.")
        return

    print(f"Connecting to Supabase Database...")
    try:
        conn = psycopg2.connect(pg_url)
        with conn.cursor() as cur:
            # Create official_summaries table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS official_summaries (
                  source_month TEXT PRIMARY KEY,
                  summary_json JSONB NOT NULL,
                  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

            # 1. Sync months.json
            months_path = static_api_dir / "months.json"
            if months_path.exists():
                print("Uploading months.json as 'months' key...")
                with open(months_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cur.execute("""
                    INSERT INTO official_summaries (source_month, summary_json, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (source_month) DO UPDATE SET
                      summary_json = EXCLUDED.summary_json,
                      updated_at = CURRENT_TIMESTAMP
                """, ("months", Json(data)))
                conn.commit()

            # 2. Sync all official-summary_*.json files
            for file_path in static_api_dir.glob("official-summary_*.json"):
                # Extract the source_month key from file name (e.g. official-summary_202604.json -> official-summary_202604)
                key = file_path.stem
                print(f"Uploading {file_path.name} as '{key}' key...")
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cur.execute("""
                    INSERT INTO official_summaries (source_month, summary_json, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (source_month) DO UPDATE SET
                      summary_json = EXCLUDED.summary_json,
                      updated_at = CURRENT_TIMESTAMP
                """, (key, Json(data)))
                conn.commit()

            print("Supabase upload complete! All summaries synced successfully.")
    except Exception as e:
        print(f"Error uploading to Supabase: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
