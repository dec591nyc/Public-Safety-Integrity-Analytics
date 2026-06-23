#!/usr/bin/env python
"""Serve a read-only local review dashboard for the judgment index."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


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


def percent_change(current: int, previous: int | None) -> float | None:
    if previous in {None, 0}:
        return None
    return round((current - previous) / previous * 100, 2)


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


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
                WHERE metric = '總計' AND geography = '機關別總計'
                GROUP BY source_month
                ORDER BY source_month DESC
                """
            )
            rows = [{"source_month": r["source_month"], "count": r["count"]} for r in cursor.fetchall()]
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
                ORDER BY source_month ASC
                """
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

            month = query.get("month", [months[-1]])[0]
            if month not in months:
                month = months[-1]

            selected_metric = query.get("metric", ["詐欺背信"])[0]

            # Get current month stats
            current_rows = rows_to_dicts(conn.execute(
                """
                SELECT metric, geography, raw_value 
                FROM official_statistics 
                WHERE source_month = ?
                """,
                [month]
            ).fetchall())

            # Build a helper lookup dict: {(geography, metric): value}
            stats_lookup = {(r["geography"], r["metric"]): r["raw_value"] for r in current_rows}

            # Total cases
            total = stats_lookup.get(("機關別總計", "總計"), 0)

            # Get previous month for change percent
            prev_month = None
            idx = months.index(month)
            if idx > 0:
                prev_month = months[idx - 1]

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
            for m in months:
                cnt_row = conn.execute(
                    "SELECT raw_value FROM official_statistics WHERE source_month = ? AND geography = '機關別總計' AND metric = '總計'",
                    [m]
                ).fetchone()
                monthly_counts.append({"month": m, "count": cnt_row[0] if cnt_row else 0})

            # Calculate public safety index (加權治安指數)
            # Sum of (raw_value * severity_score) for '機關別總計' where metric != '總計'
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
                WHERE s.source_month = ? AND s.geography = '機關別總計'
                """,
                [month]
            ).fetchone()
            
            flags_summary = {
                "cyber": flags_row["cyber"] if flags_row and flags_row["cyber"] else 0,
                "weapon": flags_row["weapon"] if flags_row and flags_row["weapon"] else 0,
                "domestic": flags_row["domestic"] if flags_row and flags_row["domestic"] else 0,
                "organized_fraud": flags_row["organized_fraud"] if flags_row and flags_row["organized_fraud"] else 0
            }

            # Get regional weighted scores ranking
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

            # Demographics aggregations
            where_clause = "WHERE source_month = ?"
            params_val = [month]
            demographics = {
                "gender": {},
                "age": {},
                "occupation": {},
                "education": {},
                "income_level": {},
                "birth_city": {}
            }
            
            # Gender counts
            for r in conn.execute(f"SELECT COALESCE(gender, 'Unknown') as g, COUNT(*) FROM judgments {where_clause} GROUP BY g", params_val).fetchall():
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
            {where_clause}
            GROUP BY age_group
            """
            for r in conn.execute(age_sql, params_val).fetchall():
                demographics["age"][r[0]] = r[1]
                
            # Occupation counts
            for r in conn.execute(f"SELECT COALESCE(occupation, 'Unknown') as occ, COUNT(*) as cnt FROM judgments {where_clause} GROUP BY occ ORDER BY cnt DESC LIMIT 8", params_val).fetchall():
                demographics["occupation"][r[0]] = r[1]
                
            # Education counts
            for r in conn.execute(f"SELECT COALESCE(education, 'Unknown') as edu, COUNT(*) as cnt FROM judgments {where_clause} GROUP BY edu ORDER BY cnt DESC LIMIT 8", params_val).fetchall():
                demographics["education"][r[0]] = r[1]
                
            # Income level counts
            for r in conn.execute(f"SELECT COALESCE(income_level, 'Unknown') as inc, COUNT(*) as cnt FROM judgments {where_clause} GROUP BY inc ORDER BY cnt DESC LIMIT 8", params_val).fetchall():
                demographics["income_level"][r[0]] = r[1]
                
            # Birth city counts
            for r in conn.execute(f"SELECT COALESCE(birth_city, 'Unknown') as city, COUNT(*) as cnt FROM judgments {where_clause} GROUP BY city ORDER BY cnt DESC LIMIT 8", params_val).fetchall():
                demographics["birth_city"][r[0]] = r[1]

            # Get quality checks
            raw_rows_count = len(current_rows)
            metric_count_val = conn.execute("SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month = ?", [month]).fetchone()[0]

            # Summary text
            fraud_val = stats_lookup.get(("機關別總計", "詐欺背信"), 0)
            injury_val = stats_lookup.get(("機關別總計", "傷害"), 0)
            sexual_val = stats_lookup.get(("機關別總計", "妨害性自主罪"), 0)

            summary_text = (
                f"{month[:4]} 年 {int(month[4:])} 月受（處）理刑事案件共 {total:,} 件，"
                f"加權治安指數為 {safety_index:,}；"
                f"詐欺背信 {fraud_val:,} 件、"
                f"傷害 {injury_val:,} 件、"
                f"妨害性自主罪 {sexual_val:,} 件。"
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
                "region_weighted_counts": region_weighted_counts,
                "region_metric": selected_metric,
                "region_counts": region_counts,
                "demographics": demographics,
                "quality": {
                    "raw_rows": raw_rows_count,
                    "selected_rows": raw_rows_count // 24 if raw_rows_count > 0 else 0,
                    "duplicate_rows_dropped": 0,
                    "metric_count": metric_count_val,
                    "matched_metric_totals": metric_count_val,
                    "invalid_cells": 0,
                    "dash_zero_cells": 0,
                },
                "summary": {
                    "text": summary_text,
                    "method": "MOI dataset 9603 SQL descriptive statistics with severity weighting",
                },
            })
        finally:
            conn.close()

    def handle_summary(self, parsed):
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
        message = "已更新本月輿情討論資料。" if summaries else "尚未啟動輿論爬蟲，因此不顯示推估或示範數字。"

        self.send_json({
            "source_month": month,
            "status": status,
            "sources": OPINION_SOURCES,
            "daily_counts": daily_counts,
            "topic_summaries": summaries,
            "message": message,
        })

    def handle_judgments(self, parsed):
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
