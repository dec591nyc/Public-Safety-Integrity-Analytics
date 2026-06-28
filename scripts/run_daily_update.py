#!/usr/bin/env python
"""Unified daily update script to sync MOI statistics and crawl opinion data."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import sys
import uuid
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Add current scripts directory to sys.path to allow importing scrape_judicial_data
sys.path.append(str(Path(__file__).resolve().parent))
from scrape_judicial_data import scrape_and_parse
from metric_styles import sync_metric_styles

# Base Configurations
DATASET_ID = "9603"
BASE_URL = "https://statis.moi.gov.tw/micst/webMain.aspx"
BASE_PARAMS = {
    "sys": "220",
    "kind": "21",
    "type": "1",
    "funid": "c0620101",
    "cycle": "41",
    "outmode": "12",
    "utf": "1",
    "compmode": "0",
    "outkind": "3",
    "fldspc": "0,2,4,3,9,3,14,4,22,1,25,4,34,4,40,31,",
    "codspc0": "0,2,3,2,6,1,9,1,12,1,15,17,",
    "rdm": "public-safety-integrity-analytics",
}

CRIME_SEEDS = [
    ("殺人", "01", "Acts leading to death or intending to cause death", 100, 0, 1, 0, 0),
    ("擄人勒贖", "04", "Acts of violence or threatened violence against a person that involve property", 95, 0, 1, 0, 0),
    ("內亂", "09", "Acts against public safety and national security", 90, 0, 0, 0, 0),
    ("強盜搶奪", "04", "Acts of violence or threatened violence against a person that involve property", 80, 0, 1, 0, 0),
    ("妨害性自主罪", "03", "Injurious acts of a sexual nature", 70, 0, 0, 0, 0),
    ("違反貪污治罪條例", "07", "Acts involving fraud, deception or corruption", 35, 0, 0, 0, 0),
    ("恐嚇取財", "04", "Acts of violence or threatened violence against a person that involve property", 30, 0, 0, 0, 0),
    ("瀆職", "07", "Acts involving fraud, deception or corruption", 25, 0, 0, 0, 0),
    ("違反選罷法", "08", "Acts against public order and authority", 15, 0, 0, 0, 0),
    ("傷害", "02", "Acts causing harm or intending to cause harm to the person", 15, 0, 0, 0, 0),
    ("公共危險", "09", "Acts against public safety and national security", 12, 0, 0, 0, 0),
    ("違反毒品危害防制條例", "06", "Acts involving controlled substances or other psychoactive substances", 12, 0, 0, 0, 0),
    ("駕駛過失", "02", "Acts causing harm or intending to cause harm to the person", 10, 0, 0, 0, 0),
    ("偽造有價證券", "07", "Acts involving fraud, deception or corruption", 10, 0, 0, 0, 0),
    ("妨害風化", "03", "Injurious acts of a sexual nature", 10, 0, 0, 0, 0),
    ("妨害公務", "08", "Acts against public order and authority", 10, 0, 0, 0, 0),
    ("詐欺背信", "07", "Acts involving fraud, deception or corruption", 8, 0, 0, 0, 1),
    ("偽造文書印文", "07", "Acts involving fraud, deception or corruption", 8, 0, 0, 0, 0),
    ("妨害電腦使用", "11", "Other criminal acts not elsewhere classified", 8, 1, 0, 0, 0),
    ("妨害秩序", "08", "Acts against public order and authority", 8, 0, 0, 0, 0),
    ("違反藥事法", "06", "Acts involving controlled substances or other psychoactive substances", 8, 0, 0, 0, 0),
    ("侵占", "05", "Acts against property only", 6, 0, 0, 0, 0),
    ("竊盜", "05", "Acts against property only", 5, 0, 0, 0, 0),
    ("竊佔", "05", "Acts against property only", 5, 0, 0, 0, 0),
    ("重利", "05", "Acts against property only", 5, 0, 0, 0, 0),
    ("妨害家庭及婚姻", "11", "Other criminal acts not elsewhere classified", 5, 0, 0, 1, 0),
    ("違反森林法", "10", "Acts against the natural environment", 5, 0, 0, 0, 0),
    ("毀棄損壞", "05", "Acts against property only", 4, 0, 0, 0, 0),
    ("違反著作權法", "11", "Other criminal acts not elsewhere classified", 4, 0, 0, 0, 0),
    ("贓物", "05", "Acts against property only", 3, 0, 0, 0, 0),
    ("違反專利法", "11", "Other criminal acts not elsewhere classified", 3, 0, 0, 0, 0),
    ("違反商標法", "11", "Other criminal acts not elsewhere classified", 3, 0, 0, 0, 0)
]

def db_execute(conn: Any, db_type: str, sql: str, params: tuple | list = ()) -> Any:
    cursor = conn.cursor()
    if db_type == "postgres":
        sql = sql.replace("?", "%s")
    cursor.execute(sql, params)
    return cursor

def db_executemany(conn: Any, db_type: str, sql: str, params_list: list) -> Any:
    cursor = conn.cursor()
    if db_type == "postgres":
        sql = sql.replace("?", "%s")
    cursor.executemany(sql, params_list)
    return cursor

def init_db(conn: Any, db_type: str, db_path: Path) -> None:
    schema_file = "schema_postgres.sql" if db_type == "postgres" else "schema_sqlite.sql"
    schema_path = Path(__file__).resolve().parent.parent / "sql" / schema_file
    if not schema_path.exists():
        print(f"Error: Schema file not found at {schema_path}", file=sys.stderr)
        sys.exit(1)
    
    cursor = conn.cursor()
    if db_type == "sqlite":
        db_path.parent.mkdir(parents=True, exist_ok=True)
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.executescript(schema_path.read_text(encoding="utf-8"))
    else:
        print("Initializing PostgreSQL tables (Supabase)...")
        # Run PostgreSQL schema SQL
        cursor.execute(schema_path.read_text(encoding="utf-8"))
        
    # Seed categories
    db_executemany(
        conn,
        db_type,
        """
        INSERT INTO crime_categories (
          metric, iccs_code, iccs_name, severity_score, flag_cyber, flag_weapon, flag_domestic, flag_organized_fraud
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(metric) DO UPDATE SET
          iccs_code=EXCLUDED.iccs_code,
          iccs_name=EXCLUDED.iccs_name,
          severity_score=EXCLUDED.severity_score,
          flag_cyber=EXCLUDED.flag_cyber,
          flag_weapon=EXCLUDED.flag_weapon,
          flag_domestic=EXCLUDED.flag_domestic,
          flag_organized_fraud=EXCLUDED.flag_organized_fraud
        """,
        CRIME_SEEDS
    )
    conn.commit()
    print(f"Database initialized and seeded ({db_type}).")

def parse_month(value: str) -> tuple[str, str]:
    if len(value) != 6 or not value.isdigit():
        raise argparse.ArgumentTypeError("month must use YYYYMM")
    year = int(value[:4])
    month = int(value[4:])
    if year <= 1911 or not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("month must be a valid Taiwan Gregorian month")
    return value, f"{year - 1911:03d}{month:02d}"

def get_months_range(start_month_str: str) -> list[str]:
    start_yr = int(start_month_str[:4])
    start_mo = int(start_month_str[4:])
    
    now = datetime.now()
    end_yr = now.year
    end_mo = now.month - 1
    if end_mo == 0:
        end_mo = 12
        end_yr -= 1
    
    months = []
    curr_yr, curr_mo = start_yr, start_mo
    while (curr_yr < end_yr) or (curr_yr == end_yr and curr_mo <= end_mo):
        months.append(f"{curr_yr}{curr_mo:02d}")
        curr_mo += 1
        if curr_mo > 12:
            curr_mo = 1
            curr_yr += 1
    return months

def build_url(roc_month: str) -> str:
    params = {**BASE_PARAMS, "ym": roc_month, "ymt": roc_month}
    return f"{BASE_URL}?{urlencode(params)}"

def parse_value(value: str) -> tuple[int, str]:
    cleaned = value.strip().replace(",", "")
    if cleaned == "-":
        return 0, "dash_zero"
    if cleaned == "":
        return 0, "empty"
    try:
        return int(cleaned), "numeric"
    except ValueError:
        return 0, "invalid"

def geography_name(row_label: str) -> str:
    return row_label.rsplit("/", 1)[-1].strip()

def row_label_month(row_label: str) -> str | None:
    range_match = re.search(r"(\d{2,3})年\s*\((\d{1,2})~(\d{1,2})月\)", row_label)
    if range_match:
        roc_year = int(range_match.group(1))
        start_month = int(range_match.group(2))
        end_month = int(range_match.group(3))
        if start_month == end_month:
            return f"{roc_year + 1911}{end_month:02d}"
        return None
    single_match = re.search(r"(\d{2,3})年\s*(\d{1,2})月", row_label)
    if single_match:
        return f"{int(single_match.group(1)) + 1911}{int(single_match.group(2)):02d}"
    return None

def download_and_ingest_moi(conn: Any, db_type: str, month: str) -> int:
    year = int(month[:4])
    roc_month = f"{year - 1911:03d}{month[4:]}"
    url = build_url(roc_month)
    
    ctx = ssl._create_unverified_context()
    req = Request(url, headers={"User-Agent": "Public-Safety-Integrity-Analytics/0.1"})
    
    try:
        with urlopen(req, timeout=30, context=ctx) as response:
            if response.status != 200:
                print(f"MOI: Failed to download {month} with HTTP {response.status}", file=sys.stderr)
                return 0
            content = response.read()
            text = content.decode("utf-8-sig", errors="ignore")
    except Exception as e:
        print(f"MOI: Connection failed for {month}: {e}", file=sys.stderr)
        return 0
        
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        print(f"MOI: No headers found for {month}", file=sys.stderr)
        return 0
        
    rows = list(reader)
    if not rows:
        print(f"MOI: No data rows found for {month}", file=sys.stderr)
        return 0
        
    dimension_name = reader.fieldnames[0]
    metrics = reader.fieldnames[1:]
    
    monthly_rows = [row for row in rows if re.search(r"\d+月/", row[dimension_name])]
    if not monthly_rows:
        monthly_rows = rows

    row_months = {row_label_month(row[dimension_name]) for row in monthly_rows}
    row_months.discard(None)
    if month not in row_months:
        display_months = ", ".join(sorted(row_months)) or "unknown"
        print(
            f"MOI: Skipping {month}; official export returned month(s): {display_months}.",
            file=sys.stderr,
        )
        return 0
    monthly_rows = [row for row in monthly_rows if row_label_month(row[dimension_name]) == month]

    db_execute(conn, db_type, "DELETE FROM official_statistics WHERE source_month = ?", (month,))
    upsert_count = 0
    for row in monthly_rows:
        geo = geography_name(row[dimension_name])
        for metric in metrics:
            val, status = parse_value(row.get(metric, ""))
            db_execute(
                conn,
                db_type,
                """
                INSERT INTO official_statistics (source_month, geography, metric, raw_value, value_status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_month, geography, metric) DO UPDATE SET
                  raw_value=EXCLUDED.raw_value,
                  value_status=EXCLUDED.value_status
                """,
                (month, geo, metric, val, status)
            )
            upsert_count += 1
            
    conn.commit()
    print(f"MOI: Synced {month} - Ingested {upsert_count} metric data points.")
    return upsert_count

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/local/public_safety.sqlite"))
    parser.add_argument("--backfill", help="Start month for backfilling YYYYMM (e.g. 199301)")
    parser.add_argument("--month", help="Single Gregorian month to update YYYYMM")
    args = parser.parse_args()
    
    # Determine DB connection type
    pg_url = os.environ.get("PUBLIC_SAFETY_DATABASE_URL")
    if pg_url:
        print("Using PostgreSQL Database (Supabase)...")
        import psycopg2
        # Use simple DictCursor compatibility
        conn = psycopg2.connect(pg_url)
        db_type = "postgres"
    else:
        print(f"Using SQLite Database ({args.db})...")
        args.db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(args.db)
        conn.row_factory = sqlite3.Row
        db_type = "sqlite"
        
    try:
        # Initialize DB & Seed categories
        init_db(conn, db_type, args.db)
        
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
