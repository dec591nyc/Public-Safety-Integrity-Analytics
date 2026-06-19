#!/usr/bin/env python
"""Serve a read-only local review dashboard for the judgment index."""

from __future__ import annotations

import argparse
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
    def __init__(self, *args, db_path: Path, static_dir: Path, **kwargs):
        self.db_path = db_path
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
        rows = rows_to_dicts(conn.execute(
            """
            SELECT source_month, COUNT(*) AS count
            FROM judgments
            GROUP BY source_month
            ORDER BY source_month DESC
            """
        ).fetchall())
        conn.close()
        self.send_json({"items": rows})

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
        daily_counts = rows_to_dicts(conn.execute(
            f"""
            SELECT substr(jdate, 1, 10) AS date, COUNT(*) AS count
            FROM judgments {where} AND COALESCE(jdate, '') <> ''
            GROUP BY substr(jdate, 1, 10)
            ORDER BY date
            """,
            params,
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
        conn.close()
        self.send_json({
            "source_month": month,
            "total_judgments": total,
            "by_case_domain": by_domain,
            "category_counts": category_counts,
            "daily_counts": daily_counts,
            "top_courts": top_courts,
            "top_titles": top_titles,
            "summary": aggregate_summary(month, total, by_domain, category_counts),
        })

    def handle_opinion(self, parsed):
        month = parse_qs(parsed.query).get("month", ["202604"])[0]
        self.send_json({
            "source_month": month,
            "status": "not_configured",
            "sources": OPINION_SOURCES,
            "daily_counts": [],
            "topic_summaries": [],
            "message": "尚未啟動輿論爬蟲，因此不顯示推估或示範數字。",
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
                   matched_keywords
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
                   category_flags, matched_keywords
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
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"SQLite DB not found: {args.db}")
    handler = lambda *a, **kw: DashboardHandler(*a, db_path=args.db, static_dir=args.static, **kw)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Review dashboard: http://{args.host}:{args.port}")
    print(f"SQLite DB: {args.db}")
    server.serve_forever()


if __name__ == "__main__":
    main()
