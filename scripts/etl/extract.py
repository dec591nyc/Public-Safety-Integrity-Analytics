# -*- coding: utf-8 -*-
"""ETL Extract Phase: Ingestion from official source URL."""

import ssl
import sys
import re
import csv
import argparse
from pathlib import Path
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from typing import Any

from .config import BASE_PARAMS, BASE_URL, TOTAL_GEOGRAPHY, TOTAL_METRIC
from .db import db_execute, db_executemany

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
    insert_data = []
    for row in monthly_rows:
        geo = geography_name(row[dimension_name])
        for metric in metrics:
            val, status = parse_value(row.get(metric, ""))
            insert_data.append((month, geo, metric, val, status))
            
    if insert_data:
        db_executemany(
            conn,
            db_type,
            """
            INSERT INTO official_statistics (source_month, geography, metric, raw_value, value_status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_month, geography, metric) DO UPDATE SET
              raw_value=EXCLUDED.raw_value,
              value_status=EXCLUDED.value_status
            """,
            insert_data
        )
            
    conn.commit()
    print(f"MOI: Synced {month} - Ingested {len(insert_data)} metric data points.")
    return len(insert_data)
