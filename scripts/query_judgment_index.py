#!/usr/bin/env python
"""Run common dashboard queries against the local judgment SQLite index."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


CATEGORIES = [
    "fraud",
    "money_laundering",
    "sexual_offense",
    "injury",
    "traffic_injury",
    "public_integrity",
    "election_law",
]


def query_dashboard(db_path: Path, source_month: str | None, top_n: int) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    filters = []
    params: list[Any] = []
    if source_month:
        filters.append("source_month = ?")
        params.append(source_month)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    def fetchall(sql: str, extra_params: list[Any] | None = None) -> list[Any]:
        return conn.execute(sql, params + (extra_params or [])).fetchall()

    def fetchone(sql: str, extra_params: list[Any] | None = None) -> Any:
        return conn.execute(sql, params + (extra_params or [])).fetchone()[0]

    category_counts = {
        category: fetchone(
            f"SELECT COUNT(*) FROM judgments {where} "
            f"{'AND' if where else 'WHERE'} json_extract(category_flags, ?) = 1",
            [f"$.{category}"],
        )
        for category in CATEGORIES
    }

    return {
        "source_month": source_month,
        "total_judgments": fetchone(f"SELECT COUNT(*) FROM judgments {where}"),
        "by_case_domain": [
            {"case_domain": row[0], "count": row[1]}
            for row in fetchall(
                f"""
                SELECT case_domain, COUNT(*) AS count
                FROM judgments
                {where}
                GROUP BY case_domain
                ORDER BY count DESC
                """
            )
        ],
        "category_counts": category_counts,
        "top_courts": [
            {"court_folder": row[0], "count": row[1]}
            for row in fetchall(
                f"""
                SELECT court_folder, COUNT(*) AS count
                FROM judgments
                {where}
                GROUP BY court_folder
                ORDER BY count DESC
                LIMIT ?
                """,
                [top_n],
            )
        ],
        "top_titles": [
            {"jtitle": row[0], "count": row[1]}
            for row in fetchall(
                f"""
                SELECT COALESCE(jtitle, ''), COUNT(*) AS count
                FROM judgments
                {where}
                GROUP BY jtitle
                ORDER BY count DESC
                LIMIT ?
                """,
                [top_n],
            )
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/local/public_safety.sqlite"))
    parser.add_argument("--month", default="202604")
    parser.add_argument("--top-n", type=int, default=10)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(json.dumps(query_dashboard(args.db, args.month, args.top_n), ensure_ascii=False, indent=2))
