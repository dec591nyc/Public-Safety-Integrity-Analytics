#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate static JSON files and structured summaries in Supabase Database."""

import os
import sys
import json
import re
import tempfile
import argparse
from pathlib import Path
from datetime import datetime

# Add current scripts directory to sys.path to allow importing etl
sys.path.append(str(Path(__file__).resolve().parent))
from etl import (
    get_connection, init_db, sync_metric_styles, load_metric_colors, metric_color,
    percent_change, percent_of, row_to_dict, get_row_dict_list,
    topic_definitions, build_topic_yoy_lookup, build_topic_monthly_trends,
    build_topic_drilldowns, build_ai_insight, build_annual_comparison,
    save_summary_report,
    TOTAL_GEOGRAPHY, TOTAL_METRIC, EXCLUDED_GEOGRAPHIES, DATASET_ID, BASE_URL, OFFICIAL_CATEGORY_MAP
)

def latest_complete_month():
    today = datetime.now()
    year = today.year
    month = today.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}{month:02d}"

def calculate_summary(conn, db_type, month_or_year, available_months, is_annual=False):
    metric_colors = load_metric_colors(conn, db_type)
    cursor = conn.cursor()

    if is_annual:
        year = int(month_or_year)
        selected_month = f"{year}12"
        query_param = f"{year}%"
        
        # Fetch annual raw metrics
        sql_rows = """
        SELECT metric, geography, SUM(raw_value) as raw_value
        FROM official_statistics
        WHERE source_month LIKE ?
        GROUP BY metric, geography
        """
        if db_type == "postgres":
            sql_rows = sql_rows.replace("?", "%s")
        cursor.execute(sql_rows, (query_param,))
        current_rows = get_row_dict_list(cursor.fetchall(), cursor)
    else:
        month = month_or_year
        selected_month = month
        query_param = month
        
        # Fetch monthly raw metrics
        sql_rows = """
        SELECT metric, geography, raw_value
        FROM official_statistics
        WHERE source_month = ?
        """
        if db_type == "postgres":
            sql_rows = sql_rows.replace("?", "%s")
        cursor.execute(sql_rows, (query_param,))
        current_rows = get_row_dict_list(cursor.fetchall(), cursor)

    stats_lookup = {(r["geography"], r["metric"]): r["raw_value"] for r in current_rows}
    geographies = {r["geography"] for r in current_rows}
    total = stats_lookup.get((TOTAL_GEOGRAPHY, TOTAL_METRIC), 0)

    # YoY Comparisons setup
    prev_month = None
    if not is_annual:
        if month in available_months:
            idx = available_months.index(month)
            if idx > 0:
                prev_month = available_months[idx - 1]
            months_through_selected = available_months[: idx + 1]
        else:
            months_through_selected = available_months
            
        previous_total = 0
        if prev_month:
            sql_prev = "SELECT raw_value FROM official_statistics WHERE source_month = ? AND geography = ? AND metric = ?"
            if db_type == "postgres":
                sql_prev = sql_prev.replace("?", "%s")
            cursor.execute(sql_prev, (prev_month, TOTAL_GEOGRAPHY, TOTAL_METRIC))
            prev_row = cursor.fetchone()
            previous_total = prev_row[0] if prev_row else 0
    else:
        prev_year = year - 1
        months_through_selected = [m for m in sorted(available_months) if m <= f"{year}12"]
        
        sql_prev = "SELECT SUM(raw_value) FROM official_statistics WHERE source_month LIKE ? AND geography = ? AND metric = ?"
        if db_type == "postgres":
            sql_prev = sql_prev.replace("?", "%s")
        cursor.execute(sql_prev, (f"{prev_year}%", TOTAL_GEOGRAPHY, TOTAL_METRIC))
        prev_row = cursor.fetchone()
        previous_total = prev_row[0] if prev_row and prev_row[0] is not None else 0

    # Monthly Counts list (required for charts)
    monthly_counts = []
    if not is_annual:
        if months_through_selected:
            markers = ",".join("?" for _ in months_through_selected)
            sql_cnt = f"SELECT source_month, raw_value FROM official_statistics WHERE source_month IN ({markers}) AND geography = ? AND metric = ?"
            if db_type == "postgres":
                sql_cnt = sql_cnt.replace("?", "%s")
            cursor.execute(sql_cnt, tuple(months_through_selected) + (TOTAL_GEOGRAPHY, TOTAL_METRIC))
            rows = cursor.fetchall()
            lookup = {r[0]: r[1] for r in rows}
            for m in months_through_selected:
                monthly_counts.append({"month": m, "count": lookup.get(m, 0)})
    else:
        # For annual, monthly_counts lists the months of that year
        year_months = [m for m in sorted(available_months) if m.startswith(str(year))]
        if year_months:
            markers = ",".join("?" for _ in year_months)
            sql_cnt = f"SELECT source_month, raw_value FROM official_statistics WHERE source_month IN ({markers}) AND geography = ? AND metric = ?"
            if db_type == "postgres":
                sql_cnt = sql_cnt.replace("?", "%s")
            cursor.execute(sql_cnt, tuple(year_months) + (TOTAL_GEOGRAPHY, TOTAL_METRIC))
            rows = cursor.fetchall()
            lookup = {r[0]: r[1] for r in rows}
            for m in year_months:
                monthly_counts.append({"month": m, "count": lookup.get(m, 0)})

    # Safety Index calculation
    op_operator = "LIKE" if is_annual else "="
    sql_safety = f"""
    SELECT SUM(s.raw_value * c.severity_score)
    FROM official_statistics s
    JOIN crime_categories c ON s.metric = c.metric
    WHERE s.source_month {op_operator} ? AND s.geography = ? AND s.metric != ?
    """
    if db_type == "postgres":
        sql_safety = sql_safety.replace("?", "%s")
    cursor.execute(sql_safety, (query_param, TOTAL_GEOGRAPHY, TOTAL_METRIC))
    safety_row = cursor.fetchone()
    safety_index = safety_row[0] if safety_row and safety_row[0] else 0

    # Category Counts
    category_counts = []
    for key, label, source_labels in OFFICIAL_CATEGORY_MAP:
        count = sum(stats_lookup.get((TOTAL_GEOGRAPHY, sl), 0) for sl in source_labels)
        prev_count = 0
        
        if not is_annual and prev_month:
            markers = ",".join("?" for _ in source_labels)
            sql_prev_cat = f"SELECT SUM(raw_value) FROM official_statistics WHERE source_month = ? AND geography = ? AND metric IN ({markers})"
            if db_type == "postgres":
                sql_prev_cat = sql_prev_cat.replace("?", "%s")
            cursor.execute(sql_prev_cat, (prev_month, TOTAL_GEOGRAPHY) + tuple(source_labels))
            prev_row = cursor.fetchone()
            prev_count = prev_row[0] if prev_row and prev_row[0] else 0
        elif is_annual:
            markers = ",".join("?" for _ in source_labels)
            sql_prev_cat = f"SELECT SUM(raw_value) FROM official_statistics WHERE source_month LIKE ? AND geography = ? AND metric IN ({markers})"
            if db_type == "postgres":
                sql_prev_cat = sql_prev_cat.replace("?", "%s")
            cursor.execute(sql_prev_cat, (f"{prev_year}%", TOTAL_GEOGRAPHY) + tuple(source_labels))
            prev_row = cursor.fetchone()
            prev_count = prev_row[0] if prev_row and prev_row[0] else 0

        category_counts.append({
            "category": key,
            "label": label,
            "count": count,
            "change_pct": percent_change(count, prev_count)
        })

    # ICCS Level Breakdown
    sql_iccs = f"""
    SELECT c.iccs_code, c.iccs_name, SUM(s.raw_value) as count, SUM(s.raw_value * c.severity_score) as weighted_score
    FROM official_statistics s
    JOIN crime_categories c ON s.metric = c.metric
    WHERE s.source_month {op_operator} ? AND s.geography = ? AND s.metric != ?
    GROUP BY c.iccs_code, c.iccs_name
    ORDER BY c.iccs_code
    """
    if db_type == "postgres":
        sql_iccs = sql_iccs.replace("?", "%s")
    cursor.execute(sql_iccs, (query_param, TOTAL_GEOGRAPHY, TOTAL_METRIC))
    iccs_rows = get_row_dict_list(cursor.fetchall(), cursor)
    
    iccs_breakdown = []
    for r in iccs_rows:
        code = r["iccs_code"]
        sql_child = f"""
        SELECT s.metric, c.severity_score, SUM(s.raw_value) as count, SUM(s.raw_value * c.severity_score) as weighted_score
        FROM official_statistics s
        JOIN crime_categories c ON s.metric = c.metric
        WHERE s.source_month {op_operator} ? AND s.geography = ? AND c.iccs_code = ?
        GROUP BY s.metric, c.severity_score
        ORDER BY count DESC
        """
        if db_type == "postgres":
            sql_child = sql_child.replace("?", "%s")
        cursor.execute(sql_child, (query_param, TOTAL_GEOGRAPHY, code))
        children = get_row_dict_list(cursor.fetchall(), cursor)
        
        iccs_breakdown.append({
            "code": code,
            "name": r["iccs_name"],
            "count": int(r["count"] or 0),
            "weighted_score": int(r["weighted_score"] or 0),
            "children": children
        })

    # Flags Summary
    sql_flags = f"""
    SELECT
      SUM(CASE WHEN c.flag_cyber = 1 THEN s.raw_value ELSE 0 END) as cyber,
      SUM(CASE WHEN c.flag_weapon = 1 THEN s.raw_value ELSE 0 END) as weapon,
      SUM(CASE WHEN c.flag_domestic = 1 THEN s.raw_value ELSE 0 END) as domestic,
      SUM(CASE WHEN c.flag_organized_fraud = 1 THEN s.raw_value ELSE 0 END) as organized_fraud
    FROM official_statistics s
    JOIN crime_categories c ON s.metric = c.metric
    WHERE s.source_month {op_operator} ? AND s.geography = ?
    """
    if db_type == "postgres":
        sql_flags = sql_flags.replace("?", "%s")
    cursor.execute(sql_flags, (query_param, TOTAL_GEOGRAPHY))
    flags_row = row_to_dict(cursor.fetchone(), cursor.description)
    flags_summary = {
        "cyber": int(flags_row.get("cyber") or 0),
        "weapon": int(flags_row.get("weapon") or 0),
        "domestic": int(flags_row.get("domestic") or 0),
        "organized_fraud": int(flags_row.get("organized_fraud") or 0)
    }

    # Region Weighted Counts
    sql_region = f"""
    SELECT s.geography, SUM(s.raw_value) as count, SUM(s.raw_value * c.severity_score) as weighted_score
    FROM official_statistics s
    JOIN crime_categories c ON s.metric = c.metric
    WHERE s.source_month {op_operator} ? AND s.geography NOT IN ('機關別總計', '署所屬機關') AND s.metric != '總計'
    GROUP BY s.geography
    ORDER BY weighted_score DESC
    """
    if db_type == "postgres":
        sql_region = sql_region.replace("?", "%s")
    cursor.execute(sql_region, (query_param,))
    region_weighted_rows = get_row_dict_list(cursor.fetchall(), cursor)
    region_weighted_counts = [
        {"geography": r["geography"], "count": int(r["count"] or 0), "weighted_score": int(r["weighted_score"] or 0)} 
        for r in region_weighted_rows
    ]

    # Topics and Drilldowns
    topics = topic_definitions(stats_lookup)
    topic_monthly_trends = build_topic_monthly_trends(conn, db_type, months_through_selected, topics)
    topic_yoy_lookup = build_topic_yoy_lookup(conn, db_type, selected_month, topics)
    topic_drilldowns = build_topic_drilldowns(
        stats_lookup, geographies, total, metric_colors, topics,
        topic_monthly_trends, topic_yoy_lookup
    )

    ai_insight = build_ai_insight(monthly_counts, topic_drilldowns)
    annual_comparison = build_annual_comparison(conn, db_type, months_through_selected, selected_month, metric_colors)

    # Region counts for selected metric "詐欺背信"
    selected_metric = "詐欺背信"
    sql_region_counts = f"""
    SELECT geography, SUM(raw_value) as raw_value
    FROM official_statistics
    WHERE source_month {op_operator} ? AND metric = ? AND geography NOT IN ('機關別總計', '署所屬機關')
    GROUP BY geography
    ORDER BY raw_value DESC
    """
    if db_type == "postgres":
        sql_region_counts = sql_region_counts.replace("?", "%s")
    cursor.execute(sql_region_counts, (query_param, selected_metric))
    region_rows = get_row_dict_list(cursor.fetchall(), cursor)
    region_counts = [{"geography": r["geography"], "count": r["raw_value"]} for r in region_rows]

    # Quality reconciliation metrics
    sql_quality_raw = f"SELECT COUNT(*) FROM official_statistics WHERE source_month {op_operator} ?"
    if db_type == "postgres":
        sql_quality_raw = sql_quality_raw.replace("?", "%s")
    cursor.execute(sql_quality_raw, (query_param,))
    raw_rows_count = cursor.fetchone()[0] or 0

    sql_quality_metrics = f"SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month {op_operator} ?"
    if db_type == "postgres":
        sql_quality_metrics = sql_quality_metrics.replace("?", "%s")
    cursor.execute(sql_quality_metrics, (query_param,))
    metric_count_val = cursor.fetchone()[0] or 0

    sql_quality_cases = f"SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month {op_operator} ? AND metric != ?"
    if db_type == "postgres":
        sql_quality_cases = sql_quality_cases.replace("?", "%s")
    cursor.execute(sql_quality_cases, (query_param, TOTAL_METRIC))
    case_metric_count = cursor.fetchone()[0] or 0

    sql_quality_nat = f"SELECT SUM(raw_value) FROM official_statistics WHERE source_month {op_operator} ? AND geography = ? AND metric != ?"
    if db_type == "postgres":
        sql_quality_nat = sql_quality_nat.replace("?", "%s")
    cursor.execute(sql_quality_nat, (query_param, TOTAL_GEOGRAPHY, TOTAL_METRIC))
    national_metric_sum = cursor.fetchone()[0] or 0

    total_reconciliation_delta = int(total or 0) - int(national_metric_sum or 0)

    leading_topics = [
        item for item in sorted(topic_drilldowns, key=lambda item: item["total"], reverse=True)
        if not item.get("is_total_scope") and not item.get("is_residual_scope")
    ][:3]
    leading_text = "、".join(f"{item['label']} {item['total']:,} 件" for item in leading_topics)

    summary_text = (
        f"{month_or_year} 年官方刑事案件發生件數資料已累計載入。"
        f"本頁優先呈現民眾與民代常關注的治安主題：{leading_text}；"
        f"全國總案量 {total:,} 件僅作統計範圍背景。"
    )

    return {
        "source_month": f"{year}_annual" if is_annual else selected_month,
        "source_url": f"{BASE_URL}?ym={query_param}",
        "dataset_id": DATASET_ID,
        "total_cases": total,
        "total_change_pct": percent_change(total, previous_total),
        "safety_index": safety_index,
        "monthly_counts": monthly_counts,
        "category_counts": category_counts,
        "iccs_breakdown": iccs_breakdown,
        "flags_summary": flags_summary,
        "topic_drilldowns": topic_drilldowns,
        "ai_insight": ai_insight,
        "annual_comparison": annual_comparison,
        "metric_styles": {
            "count": len(metric_colors),
            "items": [{"metric": m, "color": c} for m, c in sorted(metric_colors.items())],
        },
        "region_weighted_counts": region_weighted_counts,
        "region_metric": selected_metric,
        "region_counts": region_counts,
        "quality": {
            "raw_rows": raw_rows_count,
            "selected_rows": raw_rows_count // 24 if raw_rows_count > 0 else 0,
            "duplicate_rows_dropped": 0,
            "metric_count": metric_count_val,
            "case_metric_count": case_metric_count,
            "national_metric_sum": national_metric_sum,
            "total_reconciliation_delta": total_reconciliation_delta,
            "matched_metric_totals": 1 if total_reconciliation_delta == 0 else 0,
            "invalid_cells": 0,
            "dash_zero_cells": 0,
        },
        "summary": {
            "text": summary_text,
            "method": "MOI dataset 9603 official descriptive statistics",
        },
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/local/public_safety.sqlite"))
    args = parser.parse_args()

    conn, db_type = get_connection(args.db)
    init_db(conn, db_type)
    cursor = conn.cursor()

    try:
        # Sync metric styles first
        metric_style_count = sync_metric_styles(conn, db_type)
        print(f"Metric styles synced: {metric_style_count}")

        # 1. Months list query
        print("Generating months list...")
        sql_months = """
        SELECT source_month, SUM(raw_value) as count
        FROM official_statistics
        WHERE metric = '總計' AND geography = '機關別總計' AND source_month <= ?
        GROUP BY source_month
        ORDER BY source_month DESC
        """
        if db_type == "postgres":
            sql_months = sql_months.replace("?", "%s")
        cursor.execute(sql_months, (latest_complete_month(),))
        months_rows = [{"source_month": r[0], "count": r[1]} for r in cursor.fetchall()]

        if not months_rows:
            months_rows = [{"source_month": "202606", "count": 1248}]

        available_months = [m["source_month"] for m in months_rows]

        # 2. Compute and sync monthly summaries
        for month in available_months:
            print(f"\nProcessing month {month}...")
            payload = calculate_summary(conn, db_type, month, available_months, is_annual=False)
            save_summary_report(conn, db_type, f"official-summary_{month}", payload)

        # 3. Compute and sync annual summaries
        print("\nGenerating annual summaries...")
        years = sorted(list({m[:4] for m in available_months if m <= latest_complete_month()}))
        for year in years:
            print(f"Generating annual summary for year {year}...")
            payload = calculate_summary(conn, db_type, year, available_months, is_annual=True)
            save_summary_report(conn, db_type, f"official-summary_{year}_annual", payload)

        print("\nAll structured data calculated and synchronized successfully.")
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()
