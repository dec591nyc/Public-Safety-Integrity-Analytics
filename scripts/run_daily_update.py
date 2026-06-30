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

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/local/public_safety.sqlite"))
    parser.add_argument("--backfill", help="Start month for backfilling YYYYMM (e.g. 199301)")
    parser.add_argument("--month", help="Single Gregorian month to update YYYYMM")
    args = parser.parse_args()
    
    # Determine DB connection type and retrieve connection
    conn, db_type = get_connection(args.db)
    if db_type == "postgres":
        print("Using PostgreSQL Database (Supabase)...")
    else:
        print(f"Using SQLite Database ({args.db})...")
        
    try:
        # Initialize DB & Seed categories
        init_db(conn, db_type)
        
        # Determine months list
        now = datetime.now()
        if args.month:
            months = [args.month]
        elif args.backfill:
            months = get_months_range(args.backfill)
        else:
            prev_month = now.month - 1
            prev_year = now.year
            if prev_month == 0:
                prev_month = 12
                prev_year -= 1
            months = [f"{prev_year}{prev_month:02d}"]
            
        print(f"Update target months: {months}")
        
        synced_stats = 0
        synced_opinions = 0
        synced_judgments = 0
        for m in months:
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
