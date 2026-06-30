# -*- coding: utf-8 -*-
"""ETL Load Phase: Saving to SQLite/PostgreSQL relational tables."""

import os
import json
import shutil
from pathlib import Path
from typing import Any

from .db import db_execute

def save_summary_report(conn: Any, db_type: str, key: str, payload: dict) -> None:
    """Save aggregated monthly/annual summaries to the structured crime_summary_reports table."""
    cursor = conn.cursor()

    # 1. Write to structured crime_summary_reports table
    if key.startswith("official-summary_"):
        suffix = key.replace("official-summary_", "")
        is_annual = suffix.endswith("_annual")
        report_type = "annual" if is_annual else "monthly"
        
        try:
            if is_annual:
                year_str = suffix.split("_")[0]
                source_year = int(year_str)
                source_month = None
                report_key = f"{source_year}_annual"
            else:
                source_year = int(suffix[:4])
                source_month = int(suffix[4:])
                report_key = suffix
                
            sql_report = """
            INSERT INTO crime_summary_reports (
              report_key, report_type, source_year, source_month, source_url, dataset_id,
              total_cases, total_change_pct, safety_index, category_counts, iccs_breakdown,
              flags_summary, topic_drilldowns, annual_comparison,
              region_weighted_counts, region_counts, quality, summary, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (report_key) DO UPDATE SET
              report_type = EXCLUDED.report_type,
              source_year = EXCLUDED.source_year,
              source_month = EXCLUDED.source_month,
              source_url = EXCLUDED.source_url,
              dataset_id = EXCLUDED.dataset_id,
              total_cases = EXCLUDED.total_cases,
              total_change_pct = EXCLUDED.total_change_pct,
              safety_index = EXCLUDED.safety_index,
              category_counts = EXCLUDED.category_counts,
              iccs_breakdown = EXCLUDED.iccs_breakdown,
              flags_summary = EXCLUDED.flags_summary,
              topic_drilldowns = EXCLUDED.topic_drilldowns,
              annual_comparison = EXCLUDED.annual_comparison,
              region_weighted_counts = EXCLUDED.region_weighted_counts,
              region_counts = EXCLUDED.region_counts,
              quality = EXCLUDED.quality,
              summary = EXCLUDED.summary,
              updated_at = CURRENT_TIMESTAMP
            """
            
            if db_type == "postgres":
                from psycopg2.extras import Json
                wrap_json = Json
                sql_report = sql_report.replace("?", "%s")
            else:
                wrap_json = lambda val: json.dumps(val, ensure_ascii=False)
            
            cursor.execute(sql_report, (
                report_key,
                report_type,
                source_year,
                source_month,
                payload.get("source_url"),
                payload.get("dataset_id"),
                payload.get("total_cases", 0),
                payload.get("total_change_pct"),
                payload.get("safety_index", 0),
                wrap_json(payload.get("category_counts", [])),
                wrap_json(payload.get("iccs_breakdown", [])),
                wrap_json(payload.get("flags_summary", {})),
                wrap_json(payload.get("topic_drilldowns", [])),
                wrap_json(payload.get("annual_comparison", {})),
                wrap_json(payload.get("region_weighted_counts", [])),
                wrap_json(payload.get("region_counts", [])),
                wrap_json(payload.get("quality", {})),
                wrap_json(payload.get("summary", {})),
            ))

            sql_payload_cache = """
            INSERT INTO crime_summary_payload_cache (cache_key, report_key, payload, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT (cache_key) DO UPDATE SET
              report_key = EXCLUDED.report_key,
              payload = EXCLUDED.payload,
              updated_at = CURRENT_TIMESTAMP
            """
            if db_type == "postgres":
                sql_payload_cache = sql_payload_cache.replace("?", "%s")

            cursor.execute(sql_payload_cache, (
                f"official-summary:{report_key}",
                report_key,
                wrap_json(payload),
            ))
            conn.commit()
            print(f"Database ({db_type}): Synced {report_type} report '{report_key}' and API payload cache.")
        except Exception as e:
            conn.rollback()
            print(f"Error syncing report '{suffix}' to crime_summary_reports: {e}")
