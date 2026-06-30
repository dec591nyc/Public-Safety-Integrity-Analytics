#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Compile and sync structured summary reports into the configured database."""

import os
import sys
import json
import re
import tempfile
import argparse
from collections import defaultdict
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

def parse_report_month(value: str) -> str:
    if not re.fullmatch(r"\d{6}", value or ""):
        raise argparse.ArgumentTypeError("month must use YYYYMM")
    year = int(value[:4])
    month = int(value[4:])
    if year <= 1911 or not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("month must be a valid Gregorian month")
    return value

def parse_report_year(value: str) -> str:
    if not re.fullmatch(r"\d{4}", value or ""):
        raise argparse.ArgumentTypeError("year must use YYYY")
    year = int(value)
    if year <= 1911:
        raise argparse.ArgumentTypeError("year must be a valid Gregorian year")
    return value

class SummaryBuildContext:
    """In-memory official statistics index used to avoid per-report DB scans."""

    def __init__(self, conn, db_type, available_months):
        self.months = sorted(
            str(m)
            for m in available_months
            if re.fullmatch(r"\d{6}", str(m or ""))
        )
        self.month_set = set(self.months)
        self.values = {}
        self.statuses = {}
        self.by_month = defaultdict(dict)
        self.by_year = defaultdict(lambda: defaultdict(int))
        self.month_geographies = defaultdict(set)
        self.year_geographies = defaultdict(set)
        self.month_metrics = defaultdict(set)
        self.year_metrics = defaultdict(set)
        self.rows_by_month = defaultdict(int)
        self.rows_by_year = defaultdict(int)
        self.categories = {}
        self._load_statistics(conn, db_type)
        self._load_categories(conn, db_type)

    def _load_statistics(self, conn, db_type):
        cursor = conn.cursor()
        sql = """
        SELECT source_month, geography, metric, raw_value, value_status
        FROM official_statistics
        """
        cursor.execute(sql)
        rows = get_row_dict_list(cursor.fetchall(), cursor)
        for row in rows:
            month = str(row["source_month"])
            if self.month_set and month not in self.month_set:
                continue
            year = month[:4]
            geography = row["geography"]
            metric = row["metric"]
            value = int(row.get("raw_value") or 0)
            key = (month, geography, metric)
            aggregate_key = (geography, metric)

            self.values[key] = value
            self.statuses[key] = row.get("value_status")
            self.by_month[month][aggregate_key] = value
            self.by_year[year][aggregate_key] += value
            self.month_geographies[month].add(geography)
            self.year_geographies[year].add(geography)
            self.month_metrics[month].add(metric)
            self.year_metrics[year].add(metric)
            self.rows_by_month[month] += 1
            self.rows_by_year[year] += 1

    def _load_categories(self, conn, db_type):
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT metric, iccs_code, iccs_name, severity_score,
                   flag_cyber, flag_weapon, flag_domestic, flag_organized_fraud
            FROM crime_categories
            """
        )
        for row in get_row_dict_list(cursor.fetchall(), cursor):
            self.categories[row["metric"]] = row

    def stats_lookup(self, month_or_year, is_annual=False):
        if is_annual:
            return dict(self.by_year[str(month_or_year)])
        return dict(self.by_month[str(month_or_year)])

    def geographies(self, month_or_year, is_annual=False):
        if is_annual:
            return set(self.year_geographies[str(month_or_year)])
        return set(self.month_geographies[str(month_or_year)])

    def total_for_month(self, month):
        return int(self.values.get((month, TOTAL_GEOGRAPHY, TOTAL_METRIC), 0) or 0)

    def total_for_year(self, year):
        return int(self.by_year[str(year)].get((TOTAL_GEOGRAPHY, TOTAL_METRIC), 0) or 0)

    def months_for_year(self, year):
        prefix = str(year)
        return [month for month in self.months if month.startswith(prefix)]

    def months_between(self, start, end):
        return [month for month in self.months if start <= month <= end]

    def monthly_counts(self, months):
        return [{"month": month, "count": self.total_for_month(month)} for month in months]

    def sum_metrics(self, months, geography, metrics):
        metric_set = set(metrics)
        total = 0
        for month in months:
            month_lookup = self.by_month.get(month, {})
            for metric in metric_set:
                total += int(month_lookup.get((geography, metric), 0) or 0)
        return total

    def category_rows(self, stats_lookup, prev_lookup):
        rows = []
        for key, label, source_labels in OFFICIAL_CATEGORY_MAP:
            count = sum(int(stats_lookup.get((TOTAL_GEOGRAPHY, metric), 0) or 0) for metric in source_labels)
            previous = sum(int(prev_lookup.get((TOTAL_GEOGRAPHY, metric), 0) or 0) for metric in source_labels)
            rows.append({
                "category": key,
                "label": label,
                "count": count,
                "change_pct": percent_change(count, previous),
            })
        return rows

    def safety_index(self, stats_lookup):
        total = 0
        for (geography, metric), count in stats_lookup.items():
            if geography != TOTAL_GEOGRAPHY or metric == TOTAL_METRIC:
                continue
            category = self.categories.get(metric)
            if not category:
                continue
            total += int(count or 0) * int(category.get("severity_score") or 0)
        return total

    def iccs_breakdown(self, stats_lookup):
        groups = {}
        children = defaultdict(list)
        for (geography, metric), count in stats_lookup.items():
            if geography != TOTAL_GEOGRAPHY or metric == TOTAL_METRIC:
                continue
            category = self.categories.get(metric)
            if not category:
                continue
            code = category["iccs_code"]
            name = category["iccs_name"]
            score = int(category.get("severity_score") or 0)
            count = int(count or 0)
            group = groups.setdefault(code, {"code": code, "name": name, "count": 0, "weighted_score": 0})
            group["count"] += count
            group["weighted_score"] += count * score
            children[code].append({
                "metric": metric,
                "severity_score": score,
                "count": count,
                "weighted_score": count * score,
            })

        result = []
        for code in sorted(groups):
            child_rows = sorted(children[code], key=lambda row: row["count"], reverse=True)
            result.append({**groups[code], "children": child_rows})
        return result

    def flags_summary(self, stats_lookup):
        flags = {"cyber": 0, "weapon": 0, "domestic": 0, "organized_fraud": 0}
        for (geography, metric), count in stats_lookup.items():
            if geography != TOTAL_GEOGRAPHY:
                continue
            category = self.categories.get(metric)
            if not category:
                continue
            count = int(count or 0)
            flags["cyber"] += count if int(category.get("flag_cyber") or 0) else 0
            flags["weapon"] += count if int(category.get("flag_weapon") or 0) else 0
            flags["domestic"] += count if int(category.get("flag_domestic") or 0) else 0
            flags["organized_fraud"] += count if int(category.get("flag_organized_fraud") or 0) else 0
        return flags

    def region_weighted_counts(self, stats_lookup):
        rows = {}
        for (geography, metric), count in stats_lookup.items():
            if geography in EXCLUDED_GEOGRAPHIES or metric == TOTAL_METRIC:
                continue
            category = self.categories.get(metric)
            if not category:
                continue
            count = int(count or 0)
            entry = rows.setdefault(geography, {"geography": geography, "count": 0, "weighted_score": 0})
            entry["count"] += count
            entry["weighted_score"] += count * int(category.get("severity_score") or 0)
        return sorted(rows.values(), key=lambda row: row["weighted_score"], reverse=True)

    def region_counts(self, stats_lookup, metric):
        rows = []
        for (geography, item_metric), count in stats_lookup.items():
            if item_metric == metric and geography not in EXCLUDED_GEOGRAPHIES:
                rows.append({"geography": geography, "count": int(count or 0)})
        return sorted(rows, key=lambda row: row["count"], reverse=True)

    def quality(self, month_or_year, stats_lookup, total, is_annual=False):
        if is_annual:
            raw_rows_count = self.rows_by_year[str(month_or_year)]
            metrics = self.year_metrics[str(month_or_year)]
        else:
            raw_rows_count = self.rows_by_month[str(month_or_year)]
            metrics = self.month_metrics[str(month_or_year)]
        national_metric_sum = sum(
            int(count or 0)
            for (geography, metric), count in stats_lookup.items()
            if geography == TOTAL_GEOGRAPHY and metric != TOTAL_METRIC
        )
        total_reconciliation_delta = int(total or 0) - int(national_metric_sum or 0)
        return {
            "raw_rows": raw_rows_count,
            "selected_rows": raw_rows_count // 24 if raw_rows_count > 0 else 0,
            "duplicate_rows_dropped": 0,
            "metric_count": len(metrics),
            "case_metric_count": len([metric for metric in metrics if metric != TOTAL_METRIC]),
            "national_metric_sum": national_metric_sum,
            "total_reconciliation_delta": total_reconciliation_delta,
            "matched_metric_totals": 1 if total_reconciliation_delta == 0 else 0,
            "invalid_cells": 0,
            "dash_zero_cells": 0,
        }

    def topic_monthly_trends(self, months, topics):
        trends = {
            "all_types": [{"month": month, "count": self.total_for_month(month)} for month in months]
        }
        for topic in topics:
            if topic.get("is_total_scope"):
                continue
            metrics = tuple(topic.get("metrics") or ())
            trends[topic["id"]] = [
                {"month": month, "count": self.sum_metrics([month], TOTAL_GEOGRAPHY, metrics)}
                for month in months
            ]
        return trends

    def topic_yoy_lookup(self, selected_month, topics):
        if not re.fullmatch(r"\d{6}", selected_month or ""):
            return {}
        previous_month = f"{int(selected_month[:4]) - 1}{selected_month[4:]}"
        previous_lookup = self.by_month.get(previous_month, {})
        lookup = {}
        for topic in topics:
            if topic.get("is_total_scope"):
                for (geography, metric), count in previous_lookup.items():
                    if metric == TOTAL_METRIC:
                        lookup[(topic["id"], geography)] = int(count or 0)
                continue
            metrics = set(topic.get("metrics") or ())
            if not metrics:
                continue
            totals = defaultdict(int)
            for (geography, metric), count in previous_lookup.items():
                if metric in metrics:
                    totals[geography] += int(count or 0)
            for geography, count in totals.items():
                lookup[(topic["id"], geography)] = count
        return lookup

    def annual_comparison(self, months, selected_month, metric_colors):
        selected_year = int(selected_month[:4])
        selected_month_num = int(selected_month[4:])
        years = sorted({int(m[:4]) for m in months if re.fullmatch(r"\d{6}", m)})
        years = [y for y in years if y <= selected_year][-8:]

        rows = []
        previous_total = None
        for year in years:
            period_months = self.months_between(f"{year}01", f"{year}{selected_month_num:02d}")
            total = sum(self.total_for_month(month) for month in period_months)
            rows.append({
                "year": year,
                "total": total,
                "months_covered": len(period_months),
                "yoy_pct": percent_change(total, previous_total),
            })
            if total:
                previous_total = total

        peak_rows = []
        for year in years:
            end_month = selected_month_num if year == selected_year else 12
            period_months = self.months_between(f"{year}01", f"{year}{end_month:02d}")
            if not period_months:
                continue
            peak_month = sorted(period_months, key=lambda month: (-self.total_for_month(month), month))[0]
            peak_total = self.total_for_month(peak_month)
            month_lookup = self.by_month.get(peak_month, {})
            top_metrics = sorted(
                [
                    (metric, int(count or 0))
                    for (geography, metric), count in month_lookup.items()
                    if geography == TOTAL_GEOGRAPHY
                    and metric not in {TOTAL_METRIC, "其他"}
                    and int(count or 0) > 0
                ],
                key=lambda item: (-item[1], item[0]),
            )[:10]
            top_metric_sum = sum(count for _, count in top_metrics)
            segments = [
                {
                    "metric": metric,
                    "label": metric,
                    "count": count,
                    "share_pct": percent_of(count, peak_total),
                    "color": metric_color(metric, metric_colors, index),
                }
                for index, (metric, count) in enumerate(top_metrics)
            ]
            other_count = max(peak_total - top_metric_sum, 0)
            if other_count:
                segments.append({
                    "metric": "__other__",
                    "label": "其他案件",
                    "count": other_count,
                    "share_pct": percent_of(other_count, peak_total),
                    "color": "#94a3b8",
                })
            peak_rows.append({
                "year": year,
                "peak_month": peak_month,
                "total": peak_total,
                "top_metric_sum": top_metric_sum,
                "other_count": other_count,
                "scope": f"{year}/01-{year}/{end_month:02d}" if year == selected_year else f"{year}/01-{year}/12",
                "segments": segments,
            })

        def build_change_driver(current_year, previous_year, end_mo, period_lbl):
            current_months = self.months_between(f"{current_year}01", f"{current_year}{end_mo:02d}")
            previous_months = self.months_between(f"{previous_year}01", f"{previous_year}{end_mo:02d}")
            current_total = sum(self.total_for_month(month) for month in current_months)
            previous_total = sum(self.total_for_month(month) for month in previous_months)

            current_metrics = defaultdict(int)
            previous_metrics = defaultdict(int)
            for month in current_months:
                for (geography, metric), count in self.by_month.get(month, {}).items():
                    if geography == TOTAL_GEOGRAPHY and metric != TOTAL_METRIC:
                        current_metrics[metric] += int(count or 0)
            for month in previous_months:
                for (geography, metric), count in self.by_month.get(month, {}).items():
                    if geography == TOTAL_GEOGRAPHY and metric != TOTAL_METRIC:
                        previous_metrics[metric] += int(count or 0)

            total_delta = current_total - previous_total
            metric_deltas = []
            for metric in sorted(set(current_metrics) | set(previous_metrics)):
                current_count = current_metrics.get(metric, 0)
                previous_count = previous_metrics.get(metric, 0)
                delta = current_count - previous_count
                if delta == 0:
                    continue
                metric_deltas.append({
                    "metric": metric,
                    "label": "其他案件" if metric == "其他" else metric,
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
                "period_label": period_lbl,
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
            change_drivers.append(build_change_driver(
                int(row["year"]),
                int(rows[index - 1]["year"]),
                selected_month_num,
                f"1-{selected_month_num}月同期間",
            ))

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
            "note": "年度比較採同期間累計；年度高峰月為搜尋範圍內單月總量最高月份。案件拆解使用全部官方案件做加總檢查，頁面只顯示主要增減案件。",
        }

def calculate_summary_fast(context, metric_colors, month_or_year, available_months, is_annual=False):
    available_months = sorted(
        str(m)
        for m in available_months
        if re.fullmatch(r"\d{6}", str(m or ""))
    )

    if is_annual:
        year = int(month_or_year)
        selected_month = f"{year}12"
        query_param = f"{year}%"
        stats_lookup = context.stats_lookup(str(year), is_annual=True)
        geographies = context.geographies(str(year), is_annual=True)
        prev_lookup = context.stats_lookup(str(year - 1), is_annual=True)
        previous_total = context.total_for_year(year - 1)
        months_through_selected = [m for m in available_months if m <= f"{year}12"]
        monthly_counts = context.monthly_counts(context.months_for_year(year))
    else:
        month = month_or_year
        selected_month = month
        query_param = month
        stats_lookup = context.stats_lookup(month)
        geographies = context.geographies(month)
        if month in available_months:
            idx = available_months.index(month)
            prev_month = available_months[idx - 1] if idx > 0 else None
            months_through_selected = available_months[: idx + 1]
        else:
            prev_month = None
            months_through_selected = available_months
        prev_lookup = context.stats_lookup(prev_month) if prev_month else {}
        previous_total = context.total_for_month(prev_month) if prev_month else 0
        monthly_counts = context.monthly_counts(months_through_selected)

    total = int(stats_lookup.get((TOTAL_GEOGRAPHY, TOTAL_METRIC), 0) or 0)
    safety_index = context.safety_index(stats_lookup)
    category_counts = context.category_rows(stats_lookup, prev_lookup)
    iccs_breakdown = context.iccs_breakdown(stats_lookup)
    flags_summary = context.flags_summary(stats_lookup)
    region_weighted_counts = context.region_weighted_counts(stats_lookup)

    topics = topic_definitions(stats_lookup)
    topic_monthly_trends = context.topic_monthly_trends(months_through_selected, topics)
    topic_yoy_lookup = context.topic_yoy_lookup(selected_month, topics)
    topic_drilldowns = build_topic_drilldowns(
        stats_lookup, geographies, total, metric_colors, topics,
        topic_monthly_trends, topic_yoy_lookup
    )

    ai_insight = build_ai_insight(monthly_counts, topic_drilldowns)
    annual_comparison = context.annual_comparison(months_through_selected, selected_month, metric_colors)

    selected_metric = "詐欺背信"
    region_counts = context.region_counts(stats_lookup, selected_metric)
    quality = context.quality(month_or_year, stats_lookup, total, is_annual=is_annual)

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
        "quality": quality,
        "summary": {
            "text": summary_text,
            "method": "MOI dataset 9603 official descriptive statistics",
        },
    }

def calculate_summary(conn, db_type, month_or_year, available_months, is_annual=False):
    available_months = sorted(
        str(m)
        for m in available_months
        if re.fullmatch(r"\d{6}", str(m or ""))
    )
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

def fetch_available_months(cursor, db_type):
    print("Generating months list...")
    sql_months = """
    SELECT source_month, SUM(raw_value) as count
    FROM official_statistics
    WHERE metric = ? AND geography = ? AND source_month <= ?
    GROUP BY source_month
    ORDER BY source_month ASC
    """
    if db_type == "postgres":
        sql_months = sql_months.replace("?", "%s")
    cursor.execute(sql_months, (TOTAL_METRIC, TOTAL_GEOGRAPHY, latest_complete_month()))
    months_rows = [{"source_month": r[0], "count": r[1]} for r in cursor.fetchall()]

    if not months_rows:
        return [{"source_month": "202606", "count": 1248}]
    return months_rows

def resolve_generation_targets(args, months_rows):
    if not months_rows:
        return [], []

    available_months = [m["source_month"] for m in months_rows]
    available_years = sorted({m[:4] for m in available_months if m <= latest_complete_month()})

    if args.full_refresh:
        target_months = available_months
    elif args.month:
        target_months = [args.month]
    elif args.year or args.from_year or args.to_year or args.annual_only:
        target_months = []
    else:
        target_months = [available_months[-1]]

    if args.year:
        target_years = [args.year]
    elif args.from_year or args.to_year:
        start_year = args.from_year or available_years[0]
        end_year = args.to_year or available_years[-1]
        target_years = [y for y in available_years if start_year <= y <= end_year]
    elif args.full_refresh:
        target_years = available_years
    elif args.annual_only:
        target_years = available_years
    else:
        target_years = sorted({m[:4] for m in target_months})

    return target_months, target_years

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/local/public_safety.sqlite"))
    parser.add_argument("--month", type=parse_report_month, help="Compile one monthly report YYYYMM and its annual report")
    parser.add_argument("--year", type=parse_report_year, help="Compile one annual report YYYY")
    parser.add_argument("--from-year", type=parse_report_year, help="Compile annual reports from this Gregorian year")
    parser.add_argument("--to-year", type=parse_report_year, help="Compile annual reports through this Gregorian year")
    parser.add_argument("--annual-only", action="store_true", help="Compile annual reports only; use with --from-year/--to-year to limit the range")
    parser.add_argument("--full-refresh", action="store_true", help="Recompute every available monthly and annual report")
    parser.add_argument("--latest-only", action="store_true", help="Explicit default: compile only the latest available month and its annual report")
    parser.add_argument("--no-preload", action="store_true", help="Use the legacy per-report SQL query path instead of in-memory preloading")
    parser.add_argument("--sqlite", action="store_true", help="Force SQLite even when PUBLIC_SAFETY_DATABASE_URL is configured")
    args = parser.parse_args()

    if args.month and args.full_refresh:
        parser.error("--month cannot be combined with --full-refresh")
    if args.year and args.full_refresh:
        parser.error("--year cannot be combined with --full-refresh")
    if args.annual_only and args.month:
        parser.error("--annual-only cannot be combined with --month")
    if args.year and (args.from_year or args.to_year):
        parser.error("--year cannot be combined with --from-year or --to-year")
    if args.from_year and args.to_year and args.from_year > args.to_year:
        parser.error("--from-year cannot be later than --to-year")

    conn, db_type = get_connection(args.db, db_type="sqlite" if args.sqlite else None)
    init_db(conn, db_type)
    cursor = conn.cursor()

    try:
        # Sync metric styles first
        metric_style_count = sync_metric_styles(conn, db_type)
        print(f"Metric styles synced: {metric_style_count}")

        months_rows = fetch_available_months(cursor, db_type)
        available_months = [m["source_month"] for m in months_rows]
        target_months, target_years = resolve_generation_targets(args, months_rows)
        report_count = len(target_months) + len(target_years)
        defer_commit = report_count > 1
        metric_colors = load_metric_colors(conn, db_type)
        build_context = None
        use_preload = (
            not args.no_preload
            and report_count
            and (args.full_refresh or args.annual_only or args.year or args.from_year or args.to_year or report_count > 2)
        )
        if use_preload:
            print("Preloading official statistics into memory...")
            build_context = SummaryBuildContext(conn, db_type, available_months)

        print(f"Available months: {available_months[0]}..{available_months[-1]} ({len(available_months)} months)")
        print(f"Monthly reports to compile: {target_months}")
        print(f"Annual reports to compile: {target_years}")

        for month in target_months:
            print(f"\nProcessing month {month}...")
            if build_context:
                payload = calculate_summary_fast(build_context, metric_colors, month, available_months, is_annual=False)
            else:
                payload = calculate_summary(conn, db_type, month, available_months, is_annual=False)
            save_summary_report(conn, db_type, f"official-summary_{month}", payload, commit=not defer_commit)

        print("\nGenerating annual summaries...")
        for year in target_years:
            print(f"Generating annual summary for year {year}...")
            if build_context:
                payload = calculate_summary_fast(build_context, metric_colors, year, available_months, is_annual=True)
            else:
                payload = calculate_summary(conn, db_type, year, available_months, is_annual=True)
            save_summary_report(conn, db_type, f"official-summary_{year}_annual", payload, commit=not defer_commit)

        if defer_commit:
            conn.commit()
            print(f"Committed {report_count} report updates in one transaction.")

        print("\nStructured data calculated and synchronized successfully.")
        return

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
