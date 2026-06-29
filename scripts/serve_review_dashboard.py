#!/usr/bin/env python

"""Serve a read-only local review dashboard for the judgment index."""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import re
import sqlite3
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from metric_styles import load_metric_colors, metric_color

CATEGORIES = [
    "fraud",
    "money_laundering",
    "sexual_offense",
    "injury",
    "traffic_injury",
    "public_integrity",
    "election_law",
]

CATEGORY_LABELS = {
    "fraud": "詐欺／詐騙",
    "money_laundering": "洗錢",
    "sexual_offense": "妨害性自主／性侵",
    "injury": "傷害／重傷",
    "traffic_injury": "交通傷害",
    "public_integrity": "貪污／瀆職／圖利／賄賂",
    "election_law": "選罷法／賄選",
}

DOMAIN_LABELS = {
    "civil": "民事",
    "criminal": "刑事",
    "administrative": "行政",
    "constitutional": "憲法",
    "disciplinary": "懲戒",
    "other": "其他",
    "unknown": "未分類",
}

OPINION_SOURCES = [
    {"name": "PTT", "status": "not_configured"},
    {"name": "Dcard", "status": "not_configured"},
    {"name": "新聞媒體", "status": "not_configured"},
    {"name": "法律／司改評論", "status": "not_configured"},
]

OFFICIAL_CATEGORY_MAP = [
    ("fraud", "詐欺背信", ("詐欺背信",)),
    ("injury", "傷害", ("傷害",)),
    ("sexual_offense", "妨害性自主罪", ("妨害性自主罪",)),
    ("public_integrity", "貪污／瀆職", ("違反貪污治罪條例", "瀆職")),
    ("election_law", "違反選罷法", ("違反選罷法",)),
]

TOTAL_GEOGRAPHY = "機關別總計"

TOTAL_METRIC = "總計"

EXCLUDED_GEOGRAPHIES = {TOTAL_GEOGRAPHY, "署所屬機關"}

OTHER_SEGMENT_COLOR = "#94a3b8"

PEAK_SEGMENT_LIMIT = 10

TOPIC_COLORS = ["#2563eb", "#0891b2", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#64748b"]

OFFICIAL_TOPIC_GROUPS = [
    {
        "id": "property_fraud",
        "label": "財產與詐欺",
        "description": "以詐欺、竊盜、侵占、強盜搶奪等民眾最常感受到的財產侵害案類為主。",
        "metrics": ("詐欺背信", "竊盜", "侵占", "竊佔", "毀棄損壞", "強盜搶奪", "恐嚇取財"),
    },
    {
        "id": "violence_personal",
        "label": "暴力與人身安全",
        "description": "觀察殺人、傷害、妨害自由、強盜搶奪等直接影響人身安全的案件。",
        "metrics": ("傷害", "殺人", "妨害自由", "強盜搶奪", "擄人勒贖", "恐嚇取財"),
    },
    {
        "id": "sexual_safety",
        "label": "性犯罪與家庭",
        "description": "聚焦妨害性自主、妨害風化、家庭與婚姻相關案類，適合後續接被害保護與通報資源。",
        "metrics": ("妨害性自主罪", "妨害風化", "妨害家庭及婚姻", "遺棄"),
    },
    {
        "id": "drug_public_safety",
        "label": "毒品與公共安全",
        "description": "比較毒品、公共危險、槍砲彈藥刀械與秩序類案件的縣市分布。",
        "metrics": ("違反毒品危害防制條例", "公共危險", "違反槍砲彈藥刀械管制條例", "妨害秩序"),
    },
    {
        "id": "integrity_governance",
        "label": "廉政與治理",
        "description": "追蹤貪污治罪條例、瀆職、選罷法與偽造文書印文等治理信任相關案類。",
        "metrics": ("違反貪污治罪條例", "瀆職", "違反選罷法", "偽造文書印文"),
    },
    {
        "id": "digital_ip",
        "label": "數位與智慧財產",
        "description": "整理妨害電腦使用、著作權、商標與專利法案件，作為數位犯罪與智財風險入口。",
        "metrics": ("妨害電腦使用", "違反著作權法", "違反商標法", "違反專利法"),
    },
]

def load_official_profiles(stats_root: Path) -> list[dict]:

    profiles = []

    if not stats_root.exists():

        return profiles

    for path in sorted(stats_root.glob("*/profile.json")):

        try:

            profile = json.loads(path.read_text(encoding="utf-8"))

            profile["_directory"] = str(path.parent)

            profiles.append(profile)

        except (OSError, json.JSONDecodeError):

            continue

    return profiles

def official_category_counts(profile: dict) -> list[dict]:

    focus = profile.get("focus_national_totals", {})

    return [
        {
            "category": key,
            "label": label,
            "count": sum(int(focus.get(source_label) or 0) for source_label in source_labels),
        }
        for key, label, source_labels in OFFICIAL_CATEGORY_MAP
    ]

def percent_of(part: int | float, whole: int | float) -> float:

    if not whole:

        return 0.0

    return round(part / whole * 100, 2)

def official_case_metrics(stats_lookup: dict[tuple[str, str], int]) -> tuple[str, ...]:

    rows = [
        (metric, int(count or 0))
        for (geography, metric), count in stats_lookup.items()
        if geography == TOTAL_GEOGRAPHY and metric != TOTAL_METRIC
    ]

    rows.sort(key=lambda item: (-item[1], item[0]))

    return tuple(metric for metric, _ in rows)

def topic_definitions(stats_lookup: dict[tuple[str, str], int]) -> list[dict]:

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
            "description": "收納未放入前六個分析主題的官方案類；其中包含官方原始欄位「其他」。",
            "metrics": other_metrics,
            "is_residual_scope": True,
            "note": "其他類型是前六個分析主題之外的官方案類集合，不是模擬或推估數據。",
        },
        {
            "id": "all_types",
            "label": "全部類型",
            "description": "包含官方匯出中所有非總計案類，作為可與全國總案量互相核對的完整資料範圍。",
            "metrics": all_metrics,
            "is_total_scope": True,
            "note": "全部類型為完整案類加總；其他主題包是分析入口，可能不完整且部分案類會跨主題出現。",
        },
    ]

def build_topic_yoy_lookup(
    conn: sqlite3.Connection,
    selected_month: str,
    topics: list[dict],
) -> dict[tuple[str, str], int]:

    if not re.fullmatch(r"\d{6}", selected_month or ""):

        return {}

    previous_month = f"{int(selected_month[:4]) - 1}{selected_month[4:]}"

    lookup: dict[tuple[str, str], int] = {}

    for topic in topics:

        if topic.get("is_total_scope"):

            rows = conn.execute(
                """



                SELECT geography, raw_value AS total



                FROM official_statistics



                WHERE source_month = ? AND metric = ?



                """,
                [previous_month, TOTAL_METRIC],
            ).fetchall()

        else:

            metrics = tuple(topic.get("metrics") or ())

            if not metrics:

                continue

            markers = ",".join("?" for _ in metrics)

            rows = conn.execute(
                f"""



                SELECT geography, SUM(raw_value) AS total



                FROM official_statistics



                WHERE source_month = ? AND metric IN ({markers})



                GROUP BY geography



                """,
                [previous_month] + list(metrics),
            ).fetchall()

        for row in rows:

            lookup[(topic["id"], row["geography"])] = int(row["total"] or 0)

    return lookup

def build_topic_monthly_trends(conn: sqlite3.Connection, months: list[str], topics: list[dict]) -> dict[str, list[dict]]:

    trends = {}

    total_rows = conn.execute(
        """



        SELECT source_month, raw_value AS count



        FROM official_statistics



        WHERE geography = ? AND metric = ?



        ORDER BY source_month



        """,
        [TOTAL_GEOGRAPHY, TOTAL_METRIC],
    ).fetchall()

    total_lookup = {row["source_month"]: int(row["count"] or 0) for row in total_rows}

    trends["all_types"] = [{"month": month, "count": total_lookup.get(month, 0)} for month in months]

    for topic in topics:

        if topic.get("is_total_scope"):

            continue

        markers = ",".join("?" for _ in topic["metrics"])

        rows = conn.execute(
            f"""



            SELECT source_month, SUM(raw_value) AS count



            FROM official_statistics



            WHERE geography = ? AND metric IN ({markers})



            GROUP BY source_month



            ORDER BY source_month



            """,
            [TOTAL_GEOGRAPHY] + list(topic["metrics"]),
        ).fetchall()

        trend_lookup = {row["source_month"]: int(row["count"] or 0) for row in rows}

        trends[topic["id"]] = [{"month": month, "count": trend_lookup.get(month, 0)} for month in months]

    return trends

def build_topic_drilldowns(
    stats_lookup: dict[tuple[str, str], int],
    geographies: set[str],
    national_total: int,
    metric_colors: dict[str, str],
    topics: list[dict],
    topic_trends: dict[str, list[dict]] | None = None,
    topic_yoy_lookup: dict[tuple[str, str], int] | None = None,
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

        national_segments.sort(key=lambda segment: (-segment["count"], segment["label"]))

        topic_total = sum(segment["count"] for segment in national_segments)

        for segment in national_segments:

            segment["share_pct"] = percent_of(segment["count"], topic_total)

        topic_previous_total = topic_yoy_lookup.get((topic["id"], TOTAL_GEOGRAPHY))

        top_regions = []

        for geography in sorted(geographies - EXCLUDED_GEOGRAPHIES):

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

            region_segments.sort(key=lambda segment: (-segment["count"], segment["label"]))

            region_total = sum(segment["count"] for segment in region_segments)

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
            "note": topic.get("note") or "主題包是分析入口，部分案類可能因公共安全語意出現在多個主題中，不應跨主題加總。",
        })

    return topic_rows

def percent_change(current: int, previous: int | None) -> float | None:

    if previous in {None, 0}:

        return None

    return round((current - previous) / previous * 100, 2)

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
        key=lambda row: (row["change_pct"] is None, row["change_pct"] if row["change_pct"] is not None else 0),
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
            "刑事案件發生件數不是起訴、判決或定罪件數。",
            "AI 研判僅提供可追溯的異常提示，需搭配行政時程與地方背景再判讀。",
        ],
    }

def build_annual_comparison(
    conn: sqlite3.Connection,
    months: list[str],
    selected_month: str,
    metric_colors: dict[str, str],
) -> dict:

    selected_year = int(selected_month[:4])

    selected_month_num = int(selected_month[4:])

    years = sorted({int(month[:4]) for month in months if re.fullmatch(r"\d{6}", month)})

    years = [year for year in years if year <= selected_year][-8:]

    rows = []

    previous_total = None

    for year in years:

        start = f"{year}01"

        end = f"{year}{selected_month_num:02d}"

        result = conn.execute(
            """



            SELECT SUM(raw_value) AS total, COUNT(*) AS months_covered



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric = '總計'



            """,
            [start, end],
        ).fetchone()

        total = int(result["total"] or 0) if result else 0

        rows.append({
            "year": year,
            "total": total,
            "months_covered": int(result["months_covered"] or 0) if result else 0,
            "yoy_pct": percent_change(total, previous_total),
        })

        if total:

            previous_total = total

    peak_rows = []

    for year in years:

        start = f"{year}01"

        end_month = selected_month_num if year == selected_year else 12

        end = f"{year}{end_month:02d}"

        peak = conn.execute(
            """



            SELECT source_month, raw_value



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric = '總計'



            ORDER BY raw_value DESC, source_month ASC



            LIMIT 1



            """,
            [start, end],
        ).fetchone()

        if not peak:

            continue

        top_metrics = conn.execute(
            """



            SELECT metric, raw_value



            FROM official_statistics



            WHERE source_month = ?



              AND geography = '機關別總計'



              AND metric != '總計'



              AND raw_value > 0



            ORDER BY raw_value DESC



            LIMIT ?



            """,
            [peak["source_month"], PEAK_SEGMENT_LIMIT],
        ).fetchall()

        top_metric_sum = sum(int(row["raw_value"] or 0) for row in top_metrics)

        peak_total = int(peak["raw_value"] or 0)

        segments = []

        for index, row in enumerate(top_metrics):

            count = int(row["raw_value"] or 0)

            segments.append({
                "metric": row["metric"],
                "label": row["metric"],
                "count": count,
                "share_pct": percent_of(count, peak_total),
                "color": metric_color(row["metric"], metric_colors, index),
            })

        other_count = max(peak_total - top_metric_sum, 0)

        if other_count:

            segments.append({
                "metric": "__other__",
                "label": "其他案類",
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

    def build_change_driver(current_year: int, previous_year: int, end_month: int, period_label: str) -> dict:

        current_start = f"{current_year}01"

        current_end = f"{current_year}{end_month:02d}"

        previous_start = f"{previous_year}01"

        previous_end = f"{previous_year}{end_month:02d}"

        current_total_row = conn.execute(
            """



            SELECT SUM(raw_value) AS total



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric = '總計'



            """,
            [current_start, current_end],
        ).fetchone()

        previous_total_row = conn.execute(
            """



            SELECT SUM(raw_value) AS total



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric = '總計'



            """,
            [previous_start, previous_end],
        ).fetchone()

        current_total = int(current_total_row["total"] or 0) if current_total_row else 0

        previous_total = int(previous_total_row["total"] or 0) if previous_total_row else 0

        current_metric_rows = conn.execute(
            """



            SELECT metric, SUM(raw_value) AS total



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric != '總計'



            GROUP BY metric



            """,
            [current_start, current_end],
        ).fetchall()

        previous_metric_rows = conn.execute(
            """



            SELECT metric, SUM(raw_value) AS total



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric != '總計'



            GROUP BY metric



            """,
            [previous_start, previous_end],
        ).fetchall()

        current_metrics = {item["metric"]: int(item["total"] or 0) for item in current_metric_rows}

        previous_metrics = {item["metric"]: int(item["total"] or 0) for item in previous_metric_rows}

        metric_deltas = []

        total_delta = current_total - previous_total

        for metric in sorted(set(current_metrics) | set(previous_metrics)):

            current_count = current_metrics.get(metric, 0)

            previous_count = previous_metrics.get(metric, 0)

            delta = current_count - previous_count

            if delta == 0:

                continue

            metric_deltas.append({
                "metric": metric,
                "label": metric,
                "current": current_count,
                "previous": previous_count,
                "delta": delta,
                "delta_share_pct": percent_of(delta, total_delta) if total_delta else None,
                "color": metric_color(metric, metric_colors, len(metric_deltas)),
            })

        metric_delta_sum = sum(item["delta"] for item in metric_deltas)

        metric_deltas.sort(key=lambda item: abs(item["delta"]), reverse=True)

        return {
            "year": current_year,
            "previous_year": previous_year,
            "period_label": period_label,
            "current_total": current_total,
            "previous_total": previous_total,
            "total_delta": total_delta,
            "metric_delta_sum": metric_delta_sum,
            "reconciliation_delta": total_delta - metric_delta_sum,
            "drivers": metric_deltas[:8],
            "driver_count": len(metric_deltas),
            "current_metric_sum": sum(current_metrics.values()),
            "previous_metric_sum": sum(previous_metrics.values()),
        }

    change_drivers = []

    for index, row in enumerate(rows):

        if index == 0:

            continue

        change_drivers.append(
            build_change_driver(
                int(row["year"]),
                int(rows[index - 1]["year"]),
                selected_month_num,
                f"1-{selected_month_num}月同期間",
            )
        )

    complete_years = [
        year for year in years
        if year < selected_year and all(f"{year}{month:02d}" in months for month in range(1, 13))
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
        "note": "年度比較採同期間累計；年度高峰月為搜尋範圍內單月總量最高月份。案類拆解使用全部官方案類做加總檢查，頁面只顯示主要增減案類。",
    }

def connect_readonly(db_path: Path) -> sqlite3.Connection:

    uri = f"file:{db_path.as_posix()}?mode=ro"

    conn = sqlite3.connect(uri, uri=True)

    conn.row_factory = sqlite3.Row

    return conn

def rows_to_dicts(rows):

    return [dict(row) for row in rows]

def latest_complete_month() -> str:

    today = datetime.now()

    year = today.year

    month = today.month - 1

    if month == 0:

        year -= 1

        month = 12

    return f"{year}{month:02d}"

def parse_json(value, fallback):

    if isinstance(value, (dict, list)):

        return value

    try:

        return json.loads(value or "")

    except (TypeError, json.JSONDecodeError):

        return fallback

def compact_text(value: str, limit: int = 260) -> str:

    text = re.sub(r"\s+", " ", value or "").strip()

    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

def extractive_summary(row: dict) -> dict:

    """Create a traceable navigation summary without making new legal claims."""

    excerpt = compact_text(row.get("excerpt") or "", 900)

    if not excerpt:

        return {
            "text": "索引中沒有足夠文字可供摘要，請開啟來源 PDF 人工審閱。",
            "provider": "extractive_rule_v1",
            "confidence": "insufficient",
            "needs_manual_review": True,
            "evidence_snippets": [],
        }

    sentences = [
        compact_text(part, 180)
        for part in re.split(r"(?<=[。！？；])", excerpt)
        if compact_text(part, 180)
    ]

    matched = parse_json(row.get("matched_keywords"), [])

    anchors = ["主文", "原告", "被告", "判決", "裁定", "應給付", "有期徒刑", "無罪", "駁回"]

    scored = []

    for index, sentence in enumerate(sentences):

        score = sum(2 for term in anchors if term in sentence)

        score += sum(1 for term in matched[:8] if term and term in sentence)

        scored.append((score, index, sentence))

    selected = sorted(scored, key=lambda item: (-item[0], item[1]))[:2]

    selected = sorted(selected, key=lambda item: item[1])

    evidence = [item[2] for item in selected] or [compact_text(excerpt, 180)]

    title = compact_text(row.get("jtitle") or "未標示案由", 48)

    text = compact_text(f"{title}：" + " ".join(evidence), 300)

    return {
        "text": text,
        "provider": "extractive_rule_v1",
        "confidence": "low",
        "needs_manual_review": True,
        "evidence_snippets": evidence,
    }

def aggregate_summary(month: str, total: int, by_domain: list[dict], categories: list[dict]) -> dict:

    leading_domain = by_domain[0] if by_domain else {"case_domain": "unknown", "count": 0}

    leading_category = max(categories, key=lambda item: item["count"], default={"label": "無", "count": 0})

    display_month = f"{month[:4]} 年 {int(month[4:])} 月" if re.fullmatch(r"\d{6}", month) else month

    return {
        "text": (
            f"{display_month}索引共 {total:,} 筆裁判；量體最高的案件領域為 "
            f"{DOMAIN_LABELS.get(leading_domain['case_domain'], leading_domain['case_domain'])}"
            f"（{leading_domain['count']:,} 筆），議題候選以 "
            f"{leading_category['label']}（{leading_category['count']:,} 筆）最多。"
        ),
        "provider": "aggregate_rule_v1",
        "confidence": "descriptive_only",
        "needs_manual_review": True,
    }

class DashboardHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, db_path: Path, static_dir: Path, stats_root: Path, **kwargs):

        self.db_path = db_path

        self.stats_root = stats_root

        super().__init__(*args, directory=str(static_dir), **kwargs)

    def send_json(self, payload, status=200):

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        self.send_response(status)

        self.send_header("Content-Type", "application/json; charset=utf-8")

        self.send_header("Cache-Control", "no-store")

        self.send_header("Content-Length", str(len(body)))

        self.end_headers()

        self.wfile.write(body)

    def send_removed_dataset(self):

        self.send_json({
            "status": "removed",
            "message": "此端點曾使用未驗證資料，已從儀表板移除。請使用 /api/official-summary 取得官方統計資料。",
        }, status=410)

    def do_GET(self):

        parsed = urlparse(self.path)

        if parsed.path == "/api/months":

            return self.handle_months()

        if parsed.path == "/api/summary":

            return self.handle_summary(parsed)

        if parsed.path == "/api/official-summary":

            return self.handle_official_summary(parsed)

        if parsed.path == "/api/opinion":

            return self.handle_opinion(parsed)

        if parsed.path == "/api/judgments":

            return self.handle_judgments(parsed)

        if parsed.path.startswith("/api/judgments/"):

            jid = unquote(parsed.path.split("/api/judgments/", 1)[1])

            return self.handle_judgment_detail(jid)

        return super().do_GET()

    def handle_months(self):

        conn = connect_readonly(self.db_path)

        try:

            cursor = conn.cursor()

            cursor.execute(
                """



                SELECT source_month, SUM(raw_value) as count



                FROM official_statistics



                WHERE metric = '總計' AND geography = '機關別總計' AND source_month <= ?



                GROUP BY source_month



                ORDER BY source_month DESC



                """,
                [latest_complete_month()]
            )

            monthly_rows = [{"source_month": r["source_month"], "count": r["count"]} for r in cursor.fetchall()]

            # Fetch completed years totals

            cursor.execute(
                """



                SELECT SUBSTR(source_month, 1, 4) as year, SUM(raw_value) as total



                FROM official_statistics



                WHERE metric = '總計' AND geography = '機關別總計' AND source_month <= ?



                GROUP BY year



                ORDER BY year DESC



                """,
                [latest_complete_month()]
            )

            annual_rows = [{"source_month": f"{r['year']}_annual", "count": r['total']} for r in cursor.fetchall()]

            rows = annual_rows + monthly_rows

        except Exception:

            rows = []

        finally:

            conn.close()

        # Fallback to default if empty

        if not rows:

            rows = [{"source_month": "202604", "count": 0}]

        self.send_json({"items": rows})

    def handle_official_summary(self, parsed):

        query = parse_qs(parsed.query)

        conn = connect_readonly(self.db_path)

        try:

            # Get all available months

            months_rows = conn.execute(
                """



                SELECT DISTINCT source_month



                FROM official_statistics



                WHERE source_month <= ?



                ORDER BY source_month ASC



                """,
                [latest_complete_month()]
            ).fetchall()

            months = [r["source_month"] for r in months_rows]

            if not months:

                # Fallback if DB is empty

                fallback_profile = {
                    "source_month": "202604",
                    "source_url": "https://statis.moi.gov.tw/micst/webMain.aspx",
                    "dataset_id": "9603",
                    "total_cases": 0,
                    "total_change_pct": 0,
                    "safety_index": 0,
                    "monthly_counts": [{"month": "202604", "count": 0}],
                    "category_counts": [],
                    "iccs_breakdown": [],
                    "flags_summary": {},
                    "topic_drilldowns": [],
                    "region_weighted_counts": [],
                    "region_metric": "詐欺背信",
                    "region_counts": [],
                    "quality": {
                        "raw_rows": 0, "selected_rows": 0, "duplicate_rows_dropped": 0,
                        "metric_count": 0, "matched_metric_totals": 0, "invalid_cells": 0, "dash_value_count": 0
                    },
                    "summary": {
                        "text": "尚未下載或載入任何官方統計資料。請在終端機中運行 `python scripts/run_daily_update.py --month 202604` 以取得並匯入最新線上數據。",
                        "method": "Fallback placeholder"
                    }
                }

                return self.send_json(fallback_profile)

            requested_month = query.get("month", [months[-1]])[0]

            is_annual = requested_month.endswith("_annual")

            if is_annual or requested_month in months:

                month = requested_month

            else:

                month = months[-1]

            selected_metric = query.get("metric", ["詐欺背信"])[0]

            if is_annual:

                year = month.split("_")[0]

                prev_year = str(int(year) - 1)

                prev_month = f"{prev_year}_annual"

                months_through_selected = [m for m in months if m <= f"{year}12"]

                current_rows = rows_to_dicts(conn.execute(
                    """



                    SELECT metric, geography, SUM(raw_value) as raw_value



                    FROM official_statistics



                    WHERE source_month LIKE ?



                    GROUP BY metric, geography



                    """,
                    [f"{year}%"]
                ).fetchall())

                stats_lookup = {(r["geography"], r["metric"]): r["raw_value"] for r in current_rows}

                geographies = {r["geography"] for r in current_rows}

                total = stats_lookup.get(("機關別總計", "總計"), 0)

                prev_total_row = conn.execute(
                    """



                    SELECT SUM(raw_value)



                    FROM official_statistics



                    WHERE source_month LIKE ? AND geography = '機關別總計' AND metric = '總計'



                    """,
                    [f"{prev_year}%"]
                ).fetchone()

                previous_total = prev_total_row[0] if prev_total_row and prev_total_row[0] else 0

            else:

                current_rows = rows_to_dicts(conn.execute(
                    """



                    SELECT metric, geography, raw_value



                    FROM official_statistics



                    WHERE source_month = ?



                    """,
                    [month]
                ).fetchall())

                stats_lookup = {(r["geography"], r["metric"]): r["raw_value"] for r in current_rows}

                geographies = {r["geography"] for r in current_rows}

                total = stats_lookup.get(("機關別總計", "總計"), 0)

                prev_month = None

                idx = months.index(month)

                if idx > 0:

                    prev_month = months[idx - 1]

                months_through_selected = months[: idx + 1]

                previous_total = 0

                if prev_month:

                    prev_total_row = conn.execute(
                        """



                        SELECT raw_value



                        FROM official_statistics



                        WHERE source_month = ? AND geography = '機關別總計' AND metric = '總計'



                        """,
                        [prev_month]
                    ).fetchone()

                    previous_total = prev_total_row[0] if prev_total_row else 0

            # Get monthly totals list for chart

            monthly_counts = []

            for m in months_through_selected:

                cnt_row = conn.execute(
                    "SELECT raw_value FROM official_statistics WHERE source_month = ? AND geography = '機關別總計' AND metric = '總計'",
                    [m]
                ).fetchone()

                monthly_counts.append({"month": m, "count": cnt_row[0] if cnt_row else 0})

            # Legacy weighted score retained only for backward-compatible API clients.

            # Sum of (raw_value * severity_score) for '機關別總計' where metric != '總計'

            if is_annual:

                safety_index_row = conn.execute(
                    """



                    SELECT SUM(s.raw_value * c.severity_score)



                    FROM official_statistics s



                    JOIN crime_categories c ON s.metric = c.metric



                    WHERE s.source_month LIKE ? AND s.geography = '機關別總計' AND s.metric != '總計'



                    """,
                    [f"{year}%"]
                ).fetchone()

            else:

                safety_index_row = conn.execute(
                    """



                    SELECT SUM(s.raw_value * c.severity_score)



                    FROM official_statistics s



                    JOIN crime_categories c ON s.metric = c.metric



                    WHERE s.source_month = ? AND s.geography = '機關別總計' AND s.metric != '總計'



                    """,
                    [month]
                ).fetchone()

            safety_index = safety_index_row[0] if safety_index_row and safety_index_row[0] else 0

            # Calculate categories counts and their percent changes

            category_counts = []

            for key, label, source_labels in OFFICIAL_CATEGORY_MAP:

                count = sum(stats_lookup.get(("機關別總計", sl), 0) for sl in source_labels)

                prev_count = 0

                if prev_month:

                    markers = ",".join("?" for _ in source_labels)

                    if is_annual:

                        prev_row = conn.execute(
                            f"SELECT SUM(raw_value) FROM official_statistics WHERE source_month LIKE ? AND geography = '機關別總計' AND metric IN ({markers})",
                            [f"{prev_year}%"] + list(source_labels)
                        ).fetchone()

                    else:

                        prev_row = conn.execute(
                            f"SELECT SUM(raw_value) FROM official_statistics WHERE source_month = ? AND geography = '機關別總計' AND metric IN ({markers})",
                            [prev_month] + list(source_labels)
                        ).fetchone()

                    prev_count = prev_row[0] if prev_row and prev_row[0] else 0

                category_counts.append({
                    "category": key,
                    "label": label,
                    "count": count,
                    "change_pct": percent_change(count, prev_count)
                })

            # Get ICCS Level 1 breakdown and child level 2 details

            if is_annual:

                iccs_rows = conn.execute(
                    """



                    SELECT c.iccs_code, c.iccs_name, SUM(s.raw_value) as count, SUM(s.raw_value * c.severity_score) as weighted_score



                    FROM official_statistics s



                    JOIN crime_categories c ON s.metric = c.metric



                    WHERE s.source_month LIKE ? AND s.geography = '機關別總計' AND s.metric != '總計'



                    GROUP BY c.iccs_code, c.iccs_name



                    ORDER BY c.iccs_code



                    """,
                    [f"{year}%"]
                ).fetchall()

            else:

                iccs_rows = conn.execute(
                    """



                    SELECT c.iccs_code, c.iccs_name, SUM(s.raw_value) as count, SUM(s.raw_value * c.severity_score) as weighted_score



                    FROM official_statistics s



                    JOIN crime_categories c ON s.metric = c.metric



                    WHERE s.source_month = ? AND s.geography = '機關別總計' AND s.metric != '總計'



                    GROUP BY c.iccs_code, c.iccs_name



                    ORDER BY c.iccs_code



                    """,
                    [month]
                ).fetchall()

            iccs_breakdown = []

            for r in iccs_rows:

                code = r["iccs_code"]

                if is_annual:

                    children = rows_to_dicts(conn.execute(
                        """



                        SELECT s.metric, c.severity_score, SUM(s.raw_value) as count, (SUM(s.raw_value) * c.severity_score) as weighted_score



                        FROM official_statistics s



                        JOIN crime_categories c ON s.metric = c.metric



                        WHERE s.source_month LIKE ? AND s.geography = '機關別總計' AND c.iccs_code = ?



                        GROUP BY s.metric, c.severity_score



                        ORDER BY count DESC



                        """,
                        [f"{year}%", code]
                    ).fetchall())

                else:

                    children = rows_to_dicts(conn.execute(
                        """



                        SELECT s.metric, c.severity_score, s.raw_value as count, (s.raw_value * c.severity_score) as weighted_score



                        FROM official_statistics s



                        JOIN crime_categories c ON s.metric = c.metric



                        WHERE s.source_month = ? AND s.geography = '機關別總計' AND c.iccs_code = ?



                        ORDER BY count DESC



                        """,
                        [month, code]
                    ).fetchall())

                iccs_breakdown.append({
                    "code": code,
                    "name": r["iccs_name"],
                    "count": r["count"],
                    "weighted_score": r["weighted_score"],
                    "children": children
                })

            # Get flags/tags summary

            flags_row = conn.execute(
                """



                SELECT



                  SUM(CASE WHEN c.flag_cyber = 1 THEN s.raw_value ELSE 0 END) as cyber,



                  SUM(CASE WHEN c.flag_weapon = 1 THEN s.raw_value ELSE 0 END) as weapon,



                  SUM(CASE WHEN c.flag_domestic = 1 THEN s.raw_value ELSE 0 END) as domestic,



                  SUM(CASE WHEN c.flag_organized_fraud = 1 THEN s.raw_value ELSE 0 END) as organized_fraud



                FROM official_statistics s



                JOIN crime_categories c ON s.metric = c.metric



                WHERE s.source_month LIKE ? AND s.geography = '機關別總計'



                """,
                [f"{year}%" if is_annual else month]
            ).fetchone()

            flags_summary = {
                "cyber": flags_row["cyber"] if flags_row and flags_row["cyber"] else 0,
                "weapon": flags_row["weapon"] if flags_row and flags_row["weapon"] else 0,
                "domestic": flags_row["domestic"] if flags_row and flags_row["domestic"] else 0,
                "organized_fraud": flags_row["organized_fraud"] if flags_row and flags_row["organized_fraud"] else 0
            }

            # Get regional weighted scores ranking

            if is_annual:

                region_weighted_rows = conn.execute(
                    """



                    SELECT s.geography, SUM(s.raw_value) as count, SUM(s.raw_value * c.severity_score) as weighted_score



                    FROM official_statistics s



                    JOIN crime_categories c ON s.metric = c.metric



                    WHERE s.source_month LIKE ? AND s.geography NOT IN ('機關別總計', '署所屬機關') AND s.metric != '總計'



                    GROUP BY s.geography



                    ORDER BY weighted_score DESC



                    """,
                    [f"{year}%"]
                ).fetchall()

            else:

                region_weighted_rows = conn.execute(
                    """



                    SELECT s.geography, SUM(s.raw_value) as count, SUM(s.raw_value * c.severity_score) as weighted_score



                    FROM official_statistics s



                    JOIN crime_categories c ON s.metric = c.metric



                    WHERE s.source_month = ? AND s.geography NOT IN ('機關別總計', '署所屬機關') AND s.metric != '總計'



                    GROUP BY s.geography



                    ORDER BY weighted_score DESC



                    """,
                    [month]
                ).fetchall()

            region_weighted_counts = [{"geography": r["geography"], "count": r["count"], "weighted_score": r["weighted_score"]} for r in region_weighted_rows]

            metric_colors = load_metric_colors(conn)

            topics = topic_definitions(stats_lookup)

            topic_monthly_trends = build_topic_monthly_trends(conn, months_through_selected, topics)

            topic_yoy_lookup = build_topic_yoy_lookup(conn, f"{year}12" if is_annual else month, topics)

            topic_drilldowns = build_topic_drilldowns(
                stats_lookup,
                geographies,
                total,
                metric_colors,
                topics,
                topic_monthly_trends,
                topic_yoy_lookup,
            )

            ai_insight = build_ai_insight(monthly_counts, topic_drilldowns)

            annual_comparison = build_annual_comparison(conn, months_through_selected, f"{year}12" if is_annual else month, metric_colors)

            # Get region counts for selected metric

            region_rows = conn.execute(
                """



                SELECT geography, raw_value



                FROM official_statistics



                WHERE source_month = ? AND metric = ? AND geography NOT IN ('機關別總計', '署所屬機關')



                ORDER BY raw_value DESC



                """,
                [month, selected_metric]
            ).fetchall()

            region_counts = [{"geography": r["geography"], "count": r["raw_value"]} for r in region_rows]

            # Get quality checks

            if is_annual:

                raw_rows_count = conn.execute("SELECT COUNT(*) FROM official_statistics WHERE source_month LIKE ?", [f"{year}%"]).fetchone()[0]

                metric_count_val = conn.execute("SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month LIKE ?", [f"{year}%"]).fetchone()[0]

                case_metric_count = conn.execute(
                    "SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month LIKE ? AND metric != ?",
                    [f"{year}%", TOTAL_METRIC],
                ).fetchone()[0]

                national_metric_sum = conn.execute(
                    """



                    SELECT SUM(raw_value)



                    FROM official_statistics



                    WHERE source_month LIKE ? AND geography = ? AND metric != ?



                    """,
                    [f"{year}%", TOTAL_GEOGRAPHY, TOTAL_METRIC],
                ).fetchone()[0] or 0

            else:

                raw_rows_count = len(current_rows)

                metric_count_val = conn.execute("SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month = ?", [month]).fetchone()[0]

                case_metric_count = conn.execute(
                    "SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month = ? AND metric != ?",
                    [month, TOTAL_METRIC],
                ).fetchone()[0]

                national_metric_sum = conn.execute(
                    """



                    SELECT SUM(raw_value)



                    FROM official_statistics



                    WHERE source_month = ? AND geography = ? AND metric != ?



                    """,
                    [month, TOTAL_GEOGRAPHY, TOTAL_METRIC],
                ).fetchone()[0] or 0

            total_reconciliation_delta = int(total or 0) - int(national_metric_sum or 0)

            # Summary text

            leading_topics = [
                item for item in sorted(topic_drilldowns, key=lambda item: item["total"], reverse=True)
                if not item.get("is_total_scope") and not item.get("is_residual_scope")
            ][:3]

            leading_text = "、".join(f"{item['label']} {item['total']:,} 件" for item in leading_topics)

            if is_annual:

                summary_text = (
                    f"{year} 年整年官方刑事案件發生件數資料已累計載入。"
                    f"本頁優先呈現民眾與民代常關注的治安主題：{leading_text}；"
                    f"全國總案量 {total:,} 件僅作統計範圍背景。"
                )

            else:

                summary_text = (
                    f"{month[:4]} 年 {int(month[4:])} 月官方刑事案件發生件數資料已載入。"
                    f"本頁優先呈現民眾與民代常關注的治安主題：{leading_text}；"
                    f"全國總案量 {total:,} 件僅作統計範圍背景。"
                )

            self.send_json({
                "source_month": month,
                "source_url": "https://statis.moi.gov.tw/micst/webMain.aspx",
                "dataset_id": "9603",
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
                    "items": [{"metric": metric, "color": color} for metric, color in sorted(metric_colors.items())],
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
            })

        finally:

            conn.close()

    def handle_summary(self, parsed):

        return self.send_removed_dataset()

        query = parse_qs(parsed.query)

        month = query.get("month", ["202604"])[0]

        conn = connect_readonly(self.db_path)

        where = "WHERE source_month = ?"

        params = [month]

        total = conn.execute(f"SELECT COUNT(*) FROM judgments {where}", params).fetchone()[0]

        by_domain = rows_to_dicts(conn.execute(
            f"""



            SELECT case_domain, COUNT(*) AS count



            FROM judgments {where}



            GROUP BY case_domain



            ORDER BY count DESC



            """,
            params,
        ).fetchall())

        category_counts = []

        for category in CATEGORIES:

            count = conn.execute(
                f"SELECT COUNT(*) FROM judgments {where} AND json_extract(category_flags, ?) = 1",
                params + [f"$.{category}"],
            ).fetchone()[0]

            category_counts.append({
                "category": category,
                "label": CATEGORY_LABELS[category],
                "count": count,
            })

        monthly_counts = rows_to_dicts(conn.execute(
            """



            SELECT source_month AS month, COUNT(*) AS count



            FROM judgments



            GROUP BY source_month



            ORDER BY source_month



            """
        ).fetchall())

        top_courts = rows_to_dicts(conn.execute(
            f"""



            SELECT court_folder, COUNT(*) AS count



            FROM judgments {where}



            GROUP BY court_folder



            ORDER BY count DESC



            LIMIT 10



            """,
            params,
        ).fetchall())

        top_titles = rows_to_dicts(conn.execute(
            f"""



            SELECT COALESCE(jtitle, '') AS jtitle, COUNT(*) AS count



            FROM judgments {where}



            GROUP BY jtitle



            ORDER BY count DESC



            LIMIT 10



            """,
            params,
        ).fetchall())

        # Demographics aggregations

        demographics = {
            "gender": {},
            "age": {},
            "occupation": {},
            "education": {},
            "income_level": {},
            "birth_city": {}
        }

        # Gender counts

        for r in conn.execute(f"SELECT COALESCE(gender, 'Unknown') as g, COUNT(*) FROM judgments {where} GROUP BY g", params).fetchall():

            demographics["gender"][r[0]] = r[1]

        # Age group counts

        age_sql = f"""



        SELECT



          CASE



            WHEN age IS NULL THEN 'Unknown'



            WHEN age < 20 THEN 'Under 20'



            WHEN age >= 20 AND age < 30 THEN '20-29'



            WHEN age >= 30 AND age < 40 THEN '30-39'



            WHEN age >= 40 AND age < 50 THEN '40-49'



            WHEN age >= 50 AND age < 60 THEN '50-59'



            ELSE '60+'



          END as age_group,



          COUNT(*)



        FROM judgments



        {where}



        GROUP BY age_group



        """

        for r in conn.execute(age_sql, params).fetchall():

            demographics["age"][r[0]] = r[1]

        # Occupation counts

        for r in conn.execute(f"SELECT COALESCE(occupation, 'Unknown') as occ, COUNT(*) as cnt FROM judgments {where} GROUP BY occ ORDER BY cnt DESC LIMIT 8", params).fetchall():

            demographics["occupation"][r[0]] = r[1]

        # Education counts

        for r in conn.execute(f"SELECT COALESCE(education, 'Unknown') as edu, COUNT(*) as cnt FROM judgments {where} GROUP BY edu ORDER BY cnt DESC LIMIT 8", params).fetchall():

            demographics["education"][r[0]] = r[1]

        # Income level counts

        for r in conn.execute(f"SELECT COALESCE(income_level, 'Unknown') as inc, COUNT(*) as cnt FROM judgments {where} GROUP BY inc ORDER BY cnt DESC LIMIT 8", params).fetchall():

            demographics["income_level"][r[0]] = r[1]

        # Birth city counts

        for r in conn.execute(f"SELECT COALESCE(birth_city, 'Unknown') as city, COUNT(*) as cnt FROM judgments {where} GROUP BY city ORDER BY cnt DESC LIMIT 8", params).fetchall():

            demographics["birth_city"][r[0]] = r[1]

        conn.close()

        self.send_json({
            "source_month": month,
            "total_judgments": total,
            "by_case_domain": by_domain,
            "category_counts": category_counts,
            "monthly_counts": monthly_counts,
            "top_courts": top_courts,
            "top_titles": top_titles,
            "demographics": demographics,
            "summary": aggregate_summary(month, total, by_domain, category_counts),
        })

    def handle_opinion(self, parsed):

        return self.send_removed_dataset()

        query = parse_qs(parsed.query)

        month = query.get("month", ["202604"])[0]

        category = query.get("topic", [""])[0]  # Front-end query uses 'topic'

        source = query.get("source", [""])[0]

        conn = connect_readonly(self.db_path)

        try:

            # Build query filters

            conditions = ["publish_date LIKE ?"]

            # Format month YYYYMM as YYYY-MM

            month_pattern = f"{month[:4]}-{month[4:]}%"

            params = [month_pattern]

            if category:

                conditions.append("category = ?")

                params.append(category)

            if source:

                conditions.append("source = ?")

                params.append(source)

            where = "WHERE " + " AND ".join(conditions)

            rows = rows_to_dicts(conn.execute(
                f"""



                SELECT post_id, source, author, title, content, url, publish_date, category, sentiment, matched_keywords



                FROM opinion_posts



                {where}



                ORDER BY publish_date DESC



                """,
                params
            ).fetchall())

            # Group summaries for the front-end 'opinion-summaries' view

            summaries = []

            for r in rows:

                kw = parse_json(r["matched_keywords"], [])

                summaries.append({
                    "topic": r["category"],
                    "source": r["source"],
                    "title": r["title"],
                    "excerpt": compact_text(r["content"], 180),
                    "url": r["url"],
                    "publish_date": r["publish_date"],
                    "sentiment": r["sentiment"],
                    "keywords": kw
                })

            # Daily counts for the line chart

            daily_rows = conn.execute(
                f"""



                SELECT SUBSTR(publish_date, 9, 2) as day, COUNT(*) as count



                FROM opinion_posts



                {where}



                GROUP BY day



                ORDER BY day ASC



                """,
                params
            ).fetchall()

            daily_counts = [{"day": int(r["day"]), "count": r["count"]} for r in daily_rows]

        except Exception:

            summaries = []

            daily_counts = []

        finally:

            conn.close()

        # Check status

        status = "ready" if summaries else "not_configured"

        message = "已更新本月輿情討論資料。" if summaries else "尚未啟動輿論爬蟲，因此不顯示推估或未驗證數字。"

        self.send_json({
            "source_month": month,
            "status": status,
            "sources": OPINION_SOURCES,
            "daily_counts": daily_counts,
            "topic_summaries": summaries,
            "message": message,
        })

    def handle_judgments(self, parsed):

        return self.send_removed_dataset()

        query = parse_qs(parsed.query)

        month = query.get("month", ["202604"])[0]

        category = query.get("category", [""])[0]

        domain = query.get("domain", [""])[0]

        q = query.get("q", [""])[0].strip()

        title = query.get("title", [""])[0].strip()

        court = query.get("court", [""])[0].strip()

        plaintiff = query.get("plaintiff", [""])[0].strip()

        defendant = query.get("defendant", [""])[0].strip()

        limit = min(max(int(query.get("limit", ["25"])[0]), 1), 100)

        offset = max(int(query.get("offset", ["0"])[0]), 0)

        conditions = ["source_month = ?"]

        params = [month]

        warnings = []

        if category:

            conditions.append("json_extract(category_flags, ?) = 1")

            params.append(f"$.{category}")

        if domain:

            conditions.append("case_domain = ?")

            params.append(domain)

        if title:

            conditions.append("jtitle LIKE ?")

            params.append(f"%{title}%")

        if court:

            conditions.append("court_folder LIKE ?")

            params.append(f"%{court}%")

        if plaintiff:

            conditions.append("excerpt LIKE ?")

            params.append(f"%{plaintiff}%")

            warnings.append("原告目前使用索引片段初篩；完成當事人事實抽取後才會成為精確欄位。")

        if defendant:

            conditions.append("excerpt LIKE ?")

            params.append(f"%{defendant}%")

            warnings.append("被告目前使用索引片段初篩；完成當事人事實抽取後才會成為精確欄位。")

        if q:

            conditions.append("(jid LIKE ? OR jtitle LIKE ? OR court_folder LIKE ? OR excerpt LIKE ? OR matched_keywords LIKE ?)")

            like = f"%{q}%"

            params.extend([like, like, like, like, like])

        where = "WHERE " + " AND ".join(conditions)

        conn = connect_readonly(self.db_path)

        total = conn.execute(f"SELECT COUNT(*) FROM judgments {where}", params).fetchone()[0]

        rows = rows_to_dicts(conn.execute(
            f"""



            SELECT jid, source_month, court_folder, case_domain, jyear, jcase, jno,



                   jdate, jtitle, jpdf, text_length, excerpt, category_flags,



                   matched_keywords, age, gender, occupation, education, income_level, birth_city



            FROM judgments



            {where}



            ORDER BY jdate DESC, jid ASC



            LIMIT ? OFFSET ?



            """,
            params + [limit, offset],
        ).fetchall())

        conn.close()

        for row in rows:

            row["category_flags"] = parse_json(row["category_flags"], {})

            row["matched_keywords"] = parse_json(row["matched_keywords"], [])

            row["summary"] = extractive_summary(row)

        self.send_json({
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": rows,
            "warnings": list(dict.fromkeys(warnings)),
            "search_capabilities": {
                "title": "indexed",
                "court": "indexed",
                "plaintiff": "excerpt_preliminary",
                "defendant": "excerpt_preliminary",
            },
        })

    def handle_judgment_detail(self, jid: str):

        return self.send_removed_dataset()

        conn = connect_readonly(self.db_path)

        row = conn.execute(
            """



            SELECT jid, source_month, court_folder, case_domain, file_path, jyear,



                   jcase, jno, jdate, jtitle, jpdf, text_length, excerpt,



                   category_flags, matched_keywords, age, gender, occupation, education, income_level, birth_city



            FROM judgments



            WHERE jid = ?



            """,
            [jid],
        ).fetchone()

        conn.close()

        if row is None:

            return self.send_json({"error": "not found"}, status=404)

        payload = dict(row)

        payload["category_flags"] = parse_json(payload["category_flags"], {})

        payload["matched_keywords"] = parse_json(payload["matched_keywords"], [])

        payload["summary"] = extractive_summary(payload)

        self.send_json(payload)

def main():

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument("--host", default="127.0.0.1")

    parser.add_argument("--port", type=int, default=8765)

    parser.add_argument("--db", type=Path, default=Path("data/local/public_safety.sqlite"))

    parser.add_argument("--static", type=Path, default=Path("web"))

    parser.add_argument("--stats", type=Path, default=Path("output/official_statistics"))

    args = parser.parse_args()

    if not args.db.exists():

        print(f"SQLite DB not found at {args.db}. Initializing empty database using schema...")

        args.db.parent.mkdir(parents=True, exist_ok=True)

        schema_path = Path(__file__).resolve().parent.parent / "sql" / "schema_sqlite.sql"

        if schema_path.exists():

            with sqlite3.connect(args.db) as conn:

                conn.execute("PRAGMA journal_mode=WAL")

                conn.execute("PRAGMA synchronous=NORMAL")

                conn.execute("PRAGMA foreign_keys=ON")

                conn.executescript(schema_path.read_text(encoding="utf-8"))

            print("Database initialized successfully.")

        else:

            raise SystemExit(f"SQLite DB not found, and schema file not found at: {schema_path}")

    handler = lambda *a, **kw: DashboardHandler(
        *a,
        db_path=args.db,
        static_dir=args.static,
        stats_root=args.stats,
        **kw,
    )

    server = ThreadingHTTPServer((args.host, args.port), handler)

    print(f"Review dashboard: http://{args.host}:{args.port}")

    print(f"SQLite DB: {args.db}")

    server.serve_forever()

if __name__ == "__main__":

    main()
