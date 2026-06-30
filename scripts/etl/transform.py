# -*- coding: utf-8 -*-
"""ETL Transform Phase: KPI calculations, trends, AI insights, and YoY comparisons."""

import calendar
import re
import json
from datetime import datetime
from typing import Any

from .config import (
    TOTAL_GEOGRAPHY, TOTAL_METRIC, EXCLUDED_GEOGRAPHIES, 
    PEAK_SEGMENT_LIMIT, OTHER_SEGMENT_COLOR,
    OFFICIAL_CATEGORY_MAP, OFFICIAL_TOPIC_GROUPS
)
from .db import db_fetch_all, metric_color

def percent_change(current: float | int | None, previous: float | int | None) -> float | None:
    if previous in {None, 0}:
        return None
    if current is None:
        return None
    return round((current - previous) / previous * 100, 2)

def percent_of(part: float | int, whole: float | int) -> float:
    if not whole:
        return 0.0
    return round(part / whole * 100, 2)

def row_to_dict(row: Any, cursor_desc: list = None) -> dict:
    """Helper to convert sqlite3.Row, dict, or psycopg2 tuple to standard dict."""
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    if hasattr(row, 'keys'): # sqlite3.Row
        return dict(row)
    # psycopg2 tuple
    if cursor_desc:
        return {desc[0]: val for desc, val in zip(cursor_desc, row)}
    return {}

def get_row_dict_list(rows: list, cursor: Any) -> list[dict]:
    """Helper to convert list of query results to standard list of dicts."""
    desc = cursor.description if cursor else None
    return [row_to_dict(row, desc) for row in rows]

def official_case_metrics(stats_lookup: dict) -> tuple[str, ...]:
    rows = [
        (metric, int(count or 0))
        for (geography, metric), count in stats_lookup.items()
        if geography == TOTAL_GEOGRAPHY and metric != TOTAL_METRIC
    ]
    rows.sort(key=lambda item: (-item[1], item[0]))
    return tuple(metric for metric, _ in rows)

def topic_definitions(stats_lookup: dict) -> list[dict]:
    all_metrics = official_case_metrics(stats_lookup)
    covered_metrics = {
        metric
        for topic in OFFICIAL_TOPIC_GROUPS
        for metric in topic["metrics"]
    }
    other_metrics = tuple(metric for metric in all_metrics if metric not in covered_metrics)

    return [
        *OFFICIAL_TOPIC_GROUPS,
        {
            "id": "other_types",
            "label": "其他類型",
            "description": "收納未放入前六個分析主題的官方案件；其中包含官方原始欄位「其他」。",
            "metrics": other_metrics,
            "is_residual_scope": True,
            "note": "其他類型是前六個分析主題之外的官方案件集合，不是模擬或推估數據。",
        },
        {
            "id": "all_types",
            "label": "全部類型",
            "description": "包含官方匯出中所有非總計案件，作為可與全國總案量互相核對的完整資料範圍。",
            "metrics": all_metrics,
            "is_total_scope": True,
            "note": "全部類型為完整案件加總；其他主題包是分析入口，可能不完整且部分案件會跨主題出現。",
        },
    ]

def build_topic_yoy_lookup(conn: Any, db_type: str, selected_month: str, topics: list[dict]) -> dict:
    if not re.fullmatch(r"\d{6}", selected_month or ""):
        return {}
    
    previous_month = f"{int(selected_month[:4]) - 1}{selected_month[4:]}"
    lookup = {}

    for topic in topics:
        if topic.get("is_total_scope"):
            sql = """
            SELECT geography, raw_value AS total
            FROM official_statistics
            WHERE source_month = ? AND metric = ?
            """
            cursor = conn.cursor()
            if db_type == "postgres":
                sql = sql.replace("?", "%s")
            cursor.execute(sql, (previous_month, TOTAL_METRIC))
            rows = get_row_dict_list(cursor.fetchall(), cursor)
        else:
            metrics = tuple(topic.get("metrics") or ())
            if not metrics:
                continue
            markers = ",".join("?" for _ in metrics)
            sql = f"""
            SELECT geography, SUM(raw_value) AS total
            FROM official_statistics
            WHERE source_month = ? AND metric IN ({markers})
            GROUP BY geography
            """
            cursor = conn.cursor()
            if db_type == "postgres":
                sql = sql.replace("?", "%s")
            cursor.execute(sql, (previous_month,) + metrics)
            rows = get_row_dict_list(cursor.fetchall(), cursor)

        for row in rows:
            lookup[(topic["id"], row["geography"])] = int(row["total"] or 0)

    return lookup

def build_topic_monthly_trends(conn: Any, db_type: str, months: list[str], topics: list[dict]) -> dict[str, list[dict]]:
    trends = {}
    
    sql_total = """
    SELECT source_month, raw_value AS count
    FROM official_statistics
    WHERE geography = ? AND metric = ?
    ORDER BY source_month
    """
    cursor = conn.cursor()
    if db_type == "postgres":
        sql_total = sql_total.replace("?", "%s")
    cursor.execute(sql_total, (TOTAL_GEOGRAPHY, TOTAL_METRIC))
    total_rows = get_row_dict_list(cursor.fetchall(), cursor)
    
    total_lookup = {row["source_month"]: int(row["count"] or 0) for row in total_rows}
    trends["all_types"] = [{"month": m, "count": total_lookup.get(m, 0)} for m in months]

    for topic in topics:
        if topic.get("is_total_scope"):
            continue
        
        metrics = tuple(topic.get("metrics") or ())
        if not metrics:
            trends[topic["id"]] = [{"month": m, "count": 0} for m in months]
            continue
        markers = ",".join("?" for _ in metrics)
        sql_topic = f"""
        SELECT source_month, SUM(raw_value) AS count
        FROM official_statistics
        WHERE geography = ? AND metric IN ({markers})
        GROUP BY source_month
        ORDER BY source_month
        """
        cursor = conn.cursor()
        if db_type == "postgres":
            sql_topic = sql_topic.replace("?", "%s")
        cursor.execute(sql_topic, (TOTAL_GEOGRAPHY,) + tuple(metrics))
        rows = get_row_dict_list(cursor.fetchall(), cursor)
        
        trend_lookup = {row["source_month"]: int(row["count"] or 0) for row in rows}
        trends[topic["id"]] = [{"month": m, "count": trend_lookup.get(m, 0)} for m in months]

    return trends

def build_topic_drilldowns(
    stats_lookup: dict, 
    geographies: set[str], 
    national_total: int, 
    metric_colors: dict[str, str], 
    topics: list[dict], 
    topic_trends: dict = None, 
    topic_yoy_lookup: dict = None
) -> list[dict]:
    topic_rows = []
    topic_yoy_lookup = topic_yoy_lookup or {}

    for topic in topics:
        national_segments = []
        for index, metric in enumerate(topic["metrics"]):
            count = int(stats_lookup.get((TOTAL_GEOGRAPHY, metric), 0) or 0)
            if count <= 0:
                continue
            national_segments.append({
                "metric": metric,
                "label": metric,
                "count": count,
                "color": metric_color(metric, metric_colors, index),
            })
        
        national_segments.sort(key=lambda s: (-s["count"], s["label"]))
        topic_total = sum(s["count"] for s in national_segments)
        
        for segment in national_segments:
            segment["share_pct"] = percent_of(segment["count"], topic_total)

        topic_previous_total = topic_yoy_lookup.get((topic["id"], TOTAL_GEOGRAPHY))
        top_regions = []

        for geography in sorted(geographies - {TOTAL_GEOGRAPHY, "署所屬機關"}):
            region_segments = []
            for index, metric in enumerate(topic["metrics"]):
                count = int(stats_lookup.get((geography, metric), 0) or 0)
                if count <= 0:
                    continue
                region_segments.append({
                    "metric": metric,
                    "label": metric,
                    "count": count,
                    "color": metric_color(metric, metric_colors, index),
                })
            
            region_segments.sort(key=lambda s: (-s["count"], s["label"]))
            region_total = sum(s["count"] for s in region_segments)
            if region_total <= 0:
                continue
            
            for segment in region_segments:
                segment["share_pct"] = percent_of(segment["count"], region_total)

            previous_region_total = topic_yoy_lookup.get((topic["id"], geography))
            top_regions.append({
                "geography": geography,
                "total": region_total,
                "share_pct": percent_of(region_total, topic_total),
                "previous_year_total": previous_region_total,
                "yoy_pct": percent_change(region_total, previous_region_total),
                "segments": region_segments,
            })

        sorted_regions = sorted(top_regions, key=lambda row: row["total"], reverse=True)

        topic_rows.append({
            "id": topic["id"],
            "label": topic["label"],
            "description": topic["description"],
            "total": topic_total,
            "share_pct": percent_of(topic_total, national_total),
            "previous_year_total": topic_previous_total,
            "yoy_pct": percent_change(topic_total, topic_previous_total),
            "is_total_scope": bool(topic.get("is_total_scope")),
            "is_residual_scope": bool(topic.get("is_residual_scope")),
            "segments": national_segments,
            "top_regions": sorted_regions[:5],
            "region_breakdowns": sorted_regions,
            "trend": (topic_trends or {}).get(topic["id"], []),
            "source_metrics": list(topic["metrics"]),
            "note": topic.get("note") or "主題包是分析入口，部分案件可能因公共安全語意出現在多個主題中，不應跨主題加總。",
        })

    return topic_rows

def month_day_count(month: str) -> int:
    if not re.fullmatch(r"\d{6}", month or ""):
        return 30
    return calendar.monthrange(int(month[:4]), int(month[4:]))[1]

def build_ai_insight(monthly_counts: list[dict], topic_drilldowns: list[dict]) -> dict:
    window = monthly_counts[-12:]
    if len(window) < 3:
        return {
            "status": "insufficient",
            "title": "趨勢資料不足",
            "method": "rule_based_official_statistics_v1",
            "summary": "目前可用月份不足，暫不產生趨勢異常研判。",
            "evidence": [],
            "topic_observations": [],
            "limitations": ["至少需要 3 個月份才進行趨勢低點或高點判讀。"],
        }

    counts = [int(row.get("count") or 0) for row in window]
    average = sum(counts) / len(counts)
    min_index, min_point = min(enumerate(window), key=lambda item: int(item[1].get("count") or 0))
    min_month = min_point["month"]
    min_count = int(min_point.get("count") or 0)
    previous_point = window[min_index - 1] if min_index > 0 else None
    next_point = window[min_index + 1] if min_index < len(window) - 1 else None
    previous_count = int(previous_point["count"]) if previous_point else None
    next_count = int(next_point["count"]) if next_point else None

    vs_average = percent_change(min_count, round(average))
    vs_previous = percent_change(min_count, previous_count)
    vs_next = percent_change(min_count, next_count)
    day_count = month_day_count(min_month)

    topic_observations = []
    for topic in topic_drilldowns:
        lookup = {row["month"]: int(row.get("count") or 0) for row in topic.get("trend", [])}
        if min_month not in lookup:
            continue
        previous_topic_count = lookup.get(previous_point["month"]) if previous_point else None
        change = percent_change(lookup[min_month], previous_topic_count)
        topic_observations.append({
            "label": topic.get("label"),
            "count": lookup[min_month],
            "previous_count": previous_topic_count,
            "change_pct": change,
        })

    topic_observations = sorted(
        topic_observations,
        key=lambda r: (r["change_pct"] is None, r["change_pct"] if r["change_pct"] is not None else 0),
    )[:6]

    severity = "watch"
    if vs_average is not None and vs_average <= -20:
        severity = "high"
    elif vs_average is not None and vs_average <= -10:
        severity = "medium"

    return {
        "status": "ready",
        "severity": severity,
        "title": f"{min_month[:4]} 年 {int(min_month[4:])} 月為近 {len(window)} 個月低點",
        "method": "rule_based_official_statistics_v1",
        "summary": (
            f"{min_month[:4]} 年 {int(min_month[4:])} 月總案量 {min_count:,} 件，"
            f"低於近 {len(window)} 個月平均 {round(average):,} 件。"
            "此區塊僅依官方統計做異常提示，不推定犯罪實際增減原因。"
        ),
        "evidence": [
            {"label": "低點月份", "value": min_month, "display": f"{min_month[:4]}/{min_month[4:]}"},
            {"label": "低點案量", "value": min_count, "display": f"{min_count:,} 件"},
            {"label": "近月平均", "value": round(average), "display": f"{round(average):,} 件"},
            {"label": "相對平均", "value": vs_average, "display": f"{vs_average:+.1f}%" if vs_average is not None else "無法計算"},
            {"label": "相對前月", "value": vs_previous, "display": f"{vs_previous:+.1f}%" if vs_previous is not None else "無前月基準"},
            {"label": "相對次月", "value": vs_next, "display": f"{vs_next:+.1f}%" if vs_next is not None else "無次月基準"},
            {"label": "低點日均", "value": round(min_count / day_count, 1), "display": f"{min_count / day_count:,.1f} 件/日"},
        ],
        "topic_observations": topic_observations,
        "limitations": [
            "目前尚未納入工作日數、春節假期、人口數或報案登錄延遲。",
            "刑事案件發生件數不是起訴、判決 or 定罪件數。",
            "AI 研判僅提供可追溯的異常提示，需搭配行政時程與地方背景再判讀。",
        ],
    }

def build_annual_comparison(conn: Any, db_type: str, months: list[str], selected_month: str, metric_colors: dict[str, str]) -> dict:
    selected_year = int(selected_month[:4])
    selected_month_num = int(selected_month[4:])
    years = sorted({int(m[:4]) for m in months if re.fullmatch(r"\d{6}", m)})
    years = [y for y in years if y <= selected_year][-8:]

    rows = []
    previous_total = None
    cursor = conn.cursor()

    for year in years:
        start = f"{year}01"
        end = f"{year}{selected_month_num:02d}"
        
        sql = """
        SELECT SUM(raw_value) AS total, COUNT(DISTINCT source_month) AS months_covered
        FROM official_statistics
        WHERE source_month BETWEEN ? AND ?
          AND geography = ?
          AND metric = ?
        """
        if db_type == "postgres":
            sql = sql.replace("?", "%s")
        cursor.execute(sql, (start, end, TOTAL_GEOGRAPHY, TOTAL_METRIC))
        result = row_to_dict(cursor.fetchone(), cursor.description)
        total = int(result.get("total") or 0) if result else 0

        rows.append({
            "year": year,
            "total": total,
            "months_covered": int(result.get("months_covered") or 0) if result else 0,
            "yoy_pct": percent_change(total, previous_total),
        })
        if total:
            previous_total = total

    peak_rows = []
    for year in years:
        start = f"{year}01"
        end_month = selected_month_num if year == selected_year else 12
        end = f"{year}{end_month:02d}"

        sql_peak = """
        SELECT source_month, raw_value
        FROM official_statistics
        WHERE source_month BETWEEN ? AND ?
          AND geography = ?
          AND metric = ?
        ORDER BY raw_value DESC, source_month ASC
        LIMIT 1
        """
        if db_type == "postgres":
            sql_peak = sql_peak.replace("?", "%s")
        cursor.execute(sql_peak, (start, end, TOTAL_GEOGRAPHY, TOTAL_METRIC))
        peak = row_to_dict(cursor.fetchone(), cursor.description)
        if not peak:
            continue

        sql_top = """
        SELECT metric, raw_value
        FROM official_statistics
        WHERE source_month = ?
          AND geography = ?
          AND metric NOT IN ('總計', '其他')
          AND raw_value > 0
        ORDER BY raw_value DESC
        LIMIT ?
        """
        if db_type == "postgres":
            sql_top = sql_top.replace("?", "%s")
        cursor.execute(sql_top, (peak["source_month"], TOTAL_GEOGRAPHY, PEAK_SEGMENT_LIMIT))
        top_metrics = get_row_dict_list(cursor.fetchall(), cursor)
        top_metric_sum = sum(int(r["raw_value"] or 0) for r in top_metrics)
        peak_total = int(peak["raw_value"] or 0)

        segments = []
        for index, r in enumerate(top_metrics):
            count = int(r["raw_value"] or 0)
            segments.append({
                "metric": r["metric"],
                "label": r["metric"],
                "count": count,
                "share_pct": percent_of(count, peak_total),
                "color": metric_color(r["metric"], metric_colors, index),
            })

        other_count = max(peak_total - top_metric_sum, 0)
        if other_count:
            segments.append({
                "metric": "__other__",
                "label": "其他案件",
                "count": other_count,
                "share_pct": percent_of(other_count, peak_total),
                "color": OTHER_SEGMENT_COLOR,
            })

        peak_rows.append({
            "year": year,
            "peak_month": peak["source_month"],
            "total": peak_total,
            "top_metric_sum": top_metric_sum,
            "other_count": other_count,
            "scope": f"{year}/01-{year}/{end_month:02d}" if year == selected_year else f"{year}/01-{year}/12",
            "segments": segments,
        })

    def build_change_driver(current_year, previous_year, end_mo, period_lbl):
        c_start = f"{current_year}01"
        c_end = f"{current_year}{end_mo:02d}"
        p_start = f"{previous_year}01"
        p_end = f"{previous_year}{end_mo:02d}"

        sql_c_tot = """
        SELECT SUM(raw_value) AS total FROM official_statistics
        WHERE source_month BETWEEN ? AND ? AND geography = ? AND metric = ?
        """
        if db_type == "postgres":
            sql_c_tot = sql_c_tot.replace("?", "%s")
        cursor.execute(sql_c_tot, (c_start, c_end, TOTAL_GEOGRAPHY, TOTAL_METRIC))
        c_tot_res = row_to_dict(cursor.fetchone(), cursor.description)
        c_total = int(c_tot_res.get("total") or 0) if c_tot_res else 0

        cursor.execute(sql_c_tot, (p_start, p_end, TOTAL_GEOGRAPHY, TOTAL_METRIC))
        p_tot_res = row_to_dict(cursor.fetchone(), cursor.description)
        p_total = int(p_tot_res.get("total") or 0) if p_tot_res else 0

        sql_metrics = """
        SELECT metric, SUM(raw_value) AS total FROM official_statistics
        WHERE source_month BETWEEN ? AND ? AND geography = ? AND metric != ?
        GROUP BY metric
        """
        if db_type == "postgres":
            sql_metrics = sql_metrics.replace("?", "%s")
        
        cursor.execute(sql_metrics, (c_start, c_end, TOTAL_GEOGRAPHY, TOTAL_METRIC))
        c_m_rows = get_row_dict_list(cursor.fetchall(), cursor)
        c_metrics = {r["metric"]: int(r["total"] or 0) for r in c_m_rows}

        cursor.execute(sql_metrics, (p_start, p_end, TOTAL_GEOGRAPHY, TOTAL_METRIC))
        p_m_rows = get_row_dict_list(cursor.fetchall(), cursor)
        p_metrics = {r["metric"]: int(r["total"] or 0) for r in p_m_rows}

        metric_deltas = []
        total_delta = c_total - p_total
        for metric in sorted(set(c_metrics) | set(p_metrics)):
            c_count = c_metrics.get(metric, 0)
            p_count = p_metrics.get(metric, 0)
            delta = c_count - p_count
            if delta == 0:
                continue
            metric_deltas.append({
                "metric": metric,
                "label": "其他案件" if metric == "其他" else metric,
                "current": c_count,
                "previous": p_count,
                "delta": delta,
                "delta_share_pct": percent_of(delta, total_delta) if total_delta else None,
                "color": metric_color(metric, metric_colors, len(metric_deltas)),
            })

        metric_delta_sum = sum(item["delta"] for item in metric_deltas)
        metric_deltas.sort(key=lambda item: abs(item["delta"]), reverse=True)

        return {
            "year": current_year,
            "previous_year": previous_year,
            "period_label": period_lbl,
            "current_total": c_total,
            "previous_total": p_total,
            "total_delta": total_delta,
            "metric_delta_sum": metric_delta_sum,
            "reconciliation_delta": total_delta - metric_delta_sum,
            "drivers": metric_deltas[:8],
            "driver_count": len(metric_deltas),
            "current_metric_sum": sum(c_metrics.values()),
            "previous_metric_sum": sum(p_metrics.values()),
        }

    change_drivers = []
    for index, r in enumerate(rows):
        if index == 0:
            continue
        change_drivers.append(
            build_change_driver(
                int(r["year"]),
                int(rows[index - 1]["year"]),
                selected_month_num,
                f"1-{selected_month_num}月同期間",
            )
        )

    complete_years = [
        y for y in years
        if y < selected_year and all(f"{y}{m:02d}" in months for m in range(1, 13))
    ]

    full_year_change_drivers = []
    for index, year in enumerate(complete_years):
        if index == 0:
            continue
        full_year_change_drivers.append(
            build_change_driver(year, complete_years[index - 1], 12, "1-12月完整年度")
        )

    return {
        "period_label": f"1-{selected_month_num}月同期間",
        "selected_year": selected_year,
        "selected_month": selected_month,
        "rows": list(reversed(rows)),
        "peak_months": list(reversed(peak_rows)),
        "change_drivers": list(reversed(change_drivers)),
        "full_year_change_drivers": list(reversed(full_year_change_drivers)),
        "note": "年度比較採同期間累計；年度高峰月為搜尋範圍內單月總量最高月份。案件拆解使用全部官方案件做加總檢查，頁面只顯示主要增減案件。",
    }
