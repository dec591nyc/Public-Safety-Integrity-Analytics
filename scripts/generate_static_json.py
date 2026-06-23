#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate static JSON files from SQLite database to enable no-server Live Demo."""

import json
import sqlite3
import urllib.parse
from pathlib import Path
import re

# Same configuration as serve_review_dashboard
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
    {"name": "PTT", "status": "ready"},
    {"name": "Dcard", "status": "ready"},
    {"name": "新聞媒體", "status": "ready"},
    {"name": "法律／司改評論", "status": "ready"},
]

OFFICIAL_CATEGORY_MAP = [
    ("fraud", "詐欺背信", ("詐欺背信",)),
    ("injury", "傷害", ("傷害",)),
    ("sexual_offense", "妨害性自主罪", ("妨害性自主罪",)),
    ("public_integrity", "貪污／瀆職", ("違反貪污治罪條例", "瀆職")),
    ("election_law", "違反選罷法", ("違反選罷法",)),
]

def percent_change(current, previous):
    if previous in {None, 0}:
        return None
    return round((current - previous) / previous * 100, 2)

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

def main():
    db_path = Path("data/local/public_safety.sqlite")
    static_api_dir = Path("web/static_api")
    static_api_dir.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to database {db_path}...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Months list
    print("Generating months.json...")
    cursor.execute(
        """
        SELECT source_month, SUM(raw_value) as count
        FROM official_statistics
        WHERE metric = '總計' AND geography = '機關別總計'
        GROUP BY source_month
        ORDER BY source_month DESC
        """
    )
    months_rows = [{"source_month": r["source_month"], "count": r["count"]} for r in cursor.fetchall()]
    if not months_rows:
        months_rows = [{"source_month": "202606", "count": 1248}]
    
    with open(static_api_dir / "months.json", "w", encoding="utf-8") as f:
        json.dump({"items": months_rows}, f, ensure_ascii=False, indent=2)

    # We will export details for every month found in DB
    available_months = [m["source_month"] for m in months_rows]

    for month in available_months:
        print(f"\nProcessing month {month}...")
        
        # 2. Official Summary Profile
        # Get all months in order
        all_months_cursor = conn.execute("SELECT DISTINCT source_month FROM official_statistics ORDER BY source_month ASC")
        months_list = [r["source_month"] for r in all_months_cursor.fetchall()]
        
        current_rows = [dict(r) for r in conn.execute(
            "SELECT metric, geography, raw_value FROM official_statistics WHERE source_month = ?", [month]
        ).fetchall()]
        stats_lookup = {(r["geography"], r["metric"]): r["raw_value"] for r in current_rows}
        total = stats_lookup.get(("機關別總計", "總計"), 0)

        prev_month = None
        if month in months_list:
            idx = months_list.index(month)
            if idx > 0:
                prev_month = months_list[idx - 1]

        previous_total = 0
        if prev_month:
            prev_total_row = conn.execute(
                "SELECT raw_value FROM official_statistics WHERE source_month = ? AND geography = '機關別總計' AND metric = '總計'",
                [prev_month]
            ).fetchone()
            previous_total = prev_total_row[0] if prev_total_row else 0

        monthly_counts = []
        for m in months_list:
            cnt_row = conn.execute(
                "SELECT raw_value FROM official_statistics WHERE source_month = ? AND geography = '機關別總計' AND metric = '總計'",
                [m]
            ).fetchone()
            monthly_counts.append({"month": m, "count": cnt_row[0] if cnt_row else 0})

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
            children = [dict(c) for c in conn.execute(
                """
                SELECT s.metric, c.severity_score, s.raw_value as count, (s.raw_value * c.severity_score) as weighted_score
                FROM official_statistics s
                JOIN crime_categories c ON s.metric = c.metric
                WHERE s.source_month = ? AND s.geography = '機關別總計' AND c.iccs_code = ?
                ORDER BY count DESC
                """,
                [month, code]
            ).fetchall()]
            
            iccs_breakdown.append({
                "code": code,
                "name": r["iccs_name"],
                "count": r["count"],
                "weighted_score": r["weighted_score"],
                "children": children
            })

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

        selected_metric = "詐欺背信"
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

        raw_rows_count = len(current_rows)
        metric_count_val = conn.execute("SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month = ?", [month]).fetchone()[0]

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

        official_summary_payload = {
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
        }

        with open(static_api_dir / f"official-summary_{month}.json", "w", encoding="utf-8") as f:
            json.dump(official_summary_payload, f, ensure_ascii=False, indent=2)

        # 3. Opinion Summary
        print(f"Generating opinion_{month}.json...")
        # Get opinion posts
        month_pattern = f"{month[:4]}-{month[4:]}%"
        opinion_rows = [dict(r) for r in conn.execute(
            """
            SELECT post_id, source, author, title, content, url, publish_date, category, sentiment, matched_keywords
            FROM opinion_posts
            WHERE publish_date LIKE ?
            ORDER BY publish_date DESC
            """,
            [month_pattern]
        ).fetchall()]

        topic_summaries = []
        for r in opinion_rows:
            kw = parse_json(r["matched_keywords"], [])
            topic_summaries.append({
                "topic": r["category"],
                "source": r["source"],
                "title": r["title"],
                "excerpt": compact_text(r["content"], 180),
                "url": r["url"],
                "publish_date": r["publish_date"],
                "sentiment": r["sentiment"],
                "keywords": kw
            })

        daily_rows = conn.execute(
            """
            SELECT SUBSTR(publish_date, 9, 2) as day, COUNT(*) as count
            FROM opinion_posts
            WHERE publish_date LIKE ?
            GROUP BY day
            ORDER BY day ASC
            """,
            [month_pattern]
        ).fetchall()
        daily_counts = [{"day": int(r["day"]), "count": r["count"]} for r in daily_rows]

        opinion_status = "ready" if topic_summaries else "not_configured"
        opinion_message = "已更新本月輿情討論資料。" if topic_summaries else "尚未啟動輿論爬蟲，因此不顯示推估或示範數字。"

        opinion_payload = {
            "source_month": month,
            "status": opinion_status,
            "sources": OPINION_SOURCES,
            "daily_counts": daily_counts,
            "topic_summaries": topic_summaries,
            "message": opinion_message,
        }

        with open(static_api_dir / f"opinion_{month}.json", "w", encoding="utf-8") as f:
            json.dump(opinion_payload, f, ensure_ascii=False, indent=2)

        # 4. Judgments List
        print(f"Generating judgments_{month}.json...")
        
        # Get count of total judgments for the month
        total_judgments = conn.execute("SELECT COUNT(*) FROM judgments WHERE source_month = ?", [month]).fetchone()[0]
        
        # Fetch up to 150 judgments
        judgments_cursor = conn.execute(
            """
            SELECT jid, source_month, court_folder, case_domain, jyear, jcase, jno,
                   jdate, jtitle, jpdf, text_length, excerpt, category_flags,
                   matched_keywords, age, gender, occupation, education, income_level, birth_city
            FROM judgments
            WHERE source_month = ?
            ORDER BY jdate DESC, jid ASC
            LIMIT 150
            """,
            [month]
        ).fetchall()
        
        judgments_items = []
        for r in judgments_cursor:
            item = dict(r)
            # Remove heavy text field to keep static JSON lightweight
            item.pop("excerpt", None)
            item["category_flags"] = parse_json(item["category_flags"], {})
            item["matched_keywords"] = parse_json(item["matched_keywords"], [])
            # Skip heavy extractive summary for static JSON
            item["summary"] = None
            judgments_items.append(item)
                
        judgments_payload = {
            "total": total_judgments if total_judgments > 0 else len(judgments_items),
            "limit": 150,
            "offset": 0,
            "items": judgments_items,
            "warnings": [],
            "search_capabilities": {
                "title": "static_in_memory",
                "court": "static_in_memory",
                "plaintiff": "static_in_memory",
                "defendant": "static_in_memory",
            },
        }
        
        with open(static_api_dir / f"judgments_{month}.json", "w", encoding="utf-8") as f:
            json.dump(judgments_payload, f, ensure_ascii=False, indent=2)
            
        print(f"Completed month {month}: exported {len(judgments_items)} judgments details.")

    conn.close()
    
    # Sync generated JSON files to docs/static_api for production GitHub Pages
    import shutil
    docs_api_dir = Path("docs/static_api")
    docs_api_dir.mkdir(parents=True, exist_ok=True)
    print("\nSyncing generated JSON files to docs/static_api...")
    for item in static_api_dir.glob("*"):
        if item.is_file():
            shutil.copy2(item, docs_api_dir / item.name)
    print("Sync to docs completed successfully!")
    
    print("\nStatic API JSON generation completed successfully!")

if __name__ == "__main__":
    main()
