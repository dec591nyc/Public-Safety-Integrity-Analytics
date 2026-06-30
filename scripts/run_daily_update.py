#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Unified daily update script to sync MOI statistics and crawl opinion data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add current scripts directory to sys.path to allow importing etl
sys.path.append(str(Path(__file__).resolve().parent))
from etl import (
    get_connection, init_db, parse_month, get_months_range,
    download_and_ingest_moi, sync_metric_styles
)

def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = (year * 12 + (month - 1)) + delta
    return month_index // 12, (month_index % 12) + 1

def default_update_month(min_release_day: int) -> str:
    now = datetime.now()
    lag_months = -1 if now.day >= min_release_day else -2
    year, month = shift_month(now.year, now.month, lag_months)
    return f"{year}{month:02d}"

def has_month(conn, db_type: str, month: str) -> bool:
    cursor = conn.cursor()
    sql = """
    SELECT 1
    FROM official_statistics
    WHERE source_month = ?
    LIMIT 1
    """
    if db_type == "postgres":
        sql = sql.replace("?", "%s")
    cursor.execute(sql, (month,))
    return cursor.fetchone() is not None

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/local/public_safety.sqlite"))
    parser.add_argument("--sqlite", action="store_true", help="Force SQLite even when PUBLIC_SAFETY_DATABASE_URL is configured")
    parser.add_argument("--backfill", help="Start month for backfilling YYYYMM (e.g. 199301)")
    parser.add_argument("--month", help="Single Gregorian month to update YYYYMM")
    parser.add_argument("--skip-existing", action="store_true", help="Skip download when the target month already exists in the database")
    parser.add_argument(
        "--min-release-day",
        type=int,
        default=8,
        help="For automatic monthly runs, do not target the previous month until this day of the month",
    )
    args = parser.parse_args()
    
    # Determine DB connection type and retrieve connection
    conn, db_type = get_connection(args.db, db_type="sqlite" if args.sqlite else None)
    if db_type == "postgres":
        print("Using PostgreSQL Database (Supabase)...")
    else:
        print(f"Using SQLite Database ({args.db})...")
        
    try:
        # Initialize DB & Seed categories
        init_db(conn, db_type)
        
        # Determine months list
        if args.month:
            months = [args.month]
        elif args.backfill:
            months = get_months_range(args.backfill)
        else:
            months = [default_update_month(args.min_release_day)]
            
        print(f"Update target months: {months}")
        
        synced_stats = 0
        synced_opinions = 0
        synced_judgments = 0
        for m in months:
            if args.skip_existing and has_month(conn, db_type, m):
                print(f"\nSkipping month {m}: already exists in database.")
                continue

            print(f"\nProcessing month {m}...")
            stats_pts = download_and_ingest_moi(conn, db_type, m)
            synced_stats += stats_pts
            
            print("Skipping judgment/opinion collection: those feeds are not displayed until a verified, non-mock source is implemented.")
        
        metric_style_count = sync_metric_styles(conn, db_type)
        print(f"  Metric Styles Synced:         {metric_style_count}")
                
        print(f"\nSummary of Run:")
        print(f"  Total Statistics Points Synced: {synced_stats}")
        print(f"  Total Opinion Posts Synced:    {synced_opinions}")
        print(f"  Total Judgments Scraped:        {synced_judgments}")
        
        result = {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "months_processed": months,
            "statistics_count": synced_stats,
            "opinions_count": synced_opinions,
            "judgments_count": synced_judgments
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        conn.close()

if __name__ == "__main__":
    main()
