#!/usr/bin/env python
"""Synchronize stable colors for official MOI crime metric labels."""

from __future__ import annotations

import argparse
import colorsys
import re
import sqlite3
from pathlib import Path
from typing import Any


PRIORITY_COLORS = [
    "#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2",
    "#db2777", "#65a30d", "#ea580c", "#4f46e5", "#0d9488", "#be123c",
    "#9333ea", "#15803d", "#b45309", "#0369a1", "#c026d3", "#047857",
    "#991b1b", "#4338ca", "#115e59", "#a16207", "#9d174d", "#1d4ed8",
    "#7e22ce", "#166534", "#c2410c", "#0e7490", "#a21caf", "#be185d",
    "#1e40af", "#ca8a04", "#2f855a", "#9f1239", "#3730a3", "#0f766e",
]


def generated_color(index: int) -> str:
    hue = ((index * 137.508) % 360) / 360
    saturation = 0.66 if index % 2 else 0.74
    lightness = 0.38 if index % 3 else 0.44
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def color_for_index(index: int) -> str:
    if index < len(PRIORITY_COLORS):
        return PRIORITY_COLORS[index]
    return generated_color(index)


def is_hex_color(value: str | None) -> bool:
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""))


def ensure_metric_styles_table(conn: Any, db_type: str = "sqlite") -> None:
    if db_type == "postgres":
        sql = """
        CREATE TABLE IF NOT EXISTS official_metric_styles (
          metric TEXT PRIMARY KEY,
          color TEXT NOT NULL,
          sort_order INTEGER NOT NULL DEFAULT 0,
          is_total INTEGER NOT NULL DEFAULT 0,
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
    else:
        sql = """
        CREATE TABLE IF NOT EXISTS official_metric_styles (
          metric TEXT PRIMARY KEY,
          color TEXT NOT NULL,
          sort_order INTEGER NOT NULL DEFAULT 0,
          is_total INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    conn.cursor().execute(sql)


def _fetch_all(conn: Any, sql: str, db_type: str = "sqlite") -> list:
    if db_type == "postgres":
        sql = sql.replace("?", "%s")
    cursor = conn.cursor()
    cursor.execute(sql)
    return cursor.fetchall()


def _execute(conn: Any, sql: str, params: tuple, db_type: str = "sqlite") -> None:
    if db_type == "postgres":
        sql = sql.replace("?", "%s")
    conn.cursor().execute(sql, params)


def _first_value(row: Any) -> Any:
    return row[0] if not isinstance(row, sqlite3.Row) else row[0]


def sync_metric_styles(conn: Any, db_type: str = "sqlite") -> int:
    ensure_metric_styles_table(conn, db_type)
    existing_rows = _fetch_all(
        conn,
        "SELECT metric, color FROM official_metric_styles ORDER BY sort_order, metric",
        db_type,
    )
    existing = {row[0]: row[1] for row in existing_rows if is_hex_color(row[1])}
    metric_rows = _fetch_all(
        conn,
        """
        SELECT metric, SUM(raw_value) AS total
        FROM official_statistics
        GROUP BY metric
        ORDER BY CASE WHEN metric = '總計' THEN 0 ELSE 1 END, total DESC, metric
        """,
        db_type,
    )
    metrics = [_first_value(row) for row in metric_rows]

    for index, metric in enumerate(metrics):
        color = existing.get(metric) or ("#334155" if metric == "總計" else color_for_index(index - 1 if index else 0))
        is_total = 1 if metric == "總計" else 0
        _execute(
            conn,
            """
            INSERT INTO official_metric_styles (metric, color, sort_order, is_total, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(metric) DO UPDATE SET
              sort_order=EXCLUDED.sort_order,
              is_total=EXCLUDED.is_total,
              updated_at=CURRENT_TIMESTAMP
            """,
            (metric, color, index, is_total),
            db_type,
        )

    conn.commit()
    return len(metrics)


def load_metric_colors(conn: Any) -> dict[str, str]:
    try:
        rows = conn.execute("SELECT metric, color FROM official_metric_styles").fetchall()
        colors = {row["metric"]: row["color"] for row in rows if is_hex_color(row["color"])}
        if colors:
            return colors
    except sqlite3.OperationalError:
        pass

    try:
        rows = conn.execute(
            """
            SELECT metric, SUM(raw_value) AS total
            FROM official_statistics
            GROUP BY metric
            ORDER BY CASE WHEN metric = '總計' THEN 0 ELSE 1 END, total DESC, metric
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    colors = {}
    for index, row in enumerate(rows):
        metric = row["metric"]
        colors[metric] = "#334155" if metric == "總計" else color_for_index(index - 1 if index else 0)
    return colors


def metric_color(metric: str, colors: dict[str, str], fallback_index: int = 0) -> str:
    color = colors.get(metric)
    if is_hex_color(color):
        return color
    return color_for_index(fallback_index)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/local/public_safety.sqlite"))
    args = parser.parse_args()
    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row
        count = sync_metric_styles(conn)
    print(f"Synced {count} official metric styles into {args.db}")


if __name__ == "__main__":
    main()
