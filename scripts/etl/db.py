# -*- coding: utf-8 -*-
"""Database Connection and In-database Utilities."""

import os
import sys
import sqlite3
from pathlib import Path
from typing import Any
from .config import CRIME_SEEDS

# Load env variables from .env file (useful for both local dev and n8n Docker mount)
def load_env_file():
    dotenv_path = Path(__file__).resolve().parents[2] / '.env'
    if dotenv_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=dotenv_path)
        except ImportError:
            # Dependency-free fallback parser
            with open(dotenv_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        k, v = line.split('=', 1)
                        os.environ[k.strip()] = v.strip().strip('"\'')

load_env_file()

def get_connection(db_path: Path | str = None, db_type: str = None) -> tuple[Any, str]:
    """Retrieve connection to SQLite or Postgres based on parameters or environment variables."""
    pg_url = os.environ.get("PUBLIC_SAFETY_DATABASE_URL")
    if db_type == "postgres" or (db_type is None and pg_url):
        import psycopg2
        conn = psycopg2.connect(pg_url)
        return conn, "postgres"
    else:
        if db_path is None:
            db_path = Path("data/local/public_safety.sqlite")
        else:
            db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

def db_execute(conn: Any, db_type: str, sql: str, params: tuple | list = ()) -> Any:
    """Execute SQL statement with cross-db compatibility (handles placeholder mapping)."""
    cursor = conn.cursor()
    if db_type == "postgres":
        sql = sql.replace("?", "%s")
    cursor.execute(sql, params)
    return cursor

def db_executemany(conn: Any, db_type: str, sql: str, params_list: list) -> Any:
    """Execute batch SQL statements with cross-db compatibility."""
    cursor = conn.cursor()
    if db_type == "postgres":
        if "values" in sql.lower() and "on conflict" in sql.lower():
            from psycopg2.extras import execute_values
            import re
            sql_mod = re.sub(r"(?i)values\s*\([^)]*\)", "VALUES %s", sql)
            sql_mod = sql_mod.replace("?", "%s")
            execute_values(cursor, sql_mod, params_list)
        else:
            sql = sql.replace("?", "%s")
            cursor.executemany(sql, params_list)
    else:
        cursor.executemany(sql, params_list)
    return cursor

def db_fetch_all(conn: Any, db_type: str, sql: str, params: tuple | list = ()) -> list:
    """Fetch all rows from a query."""
    cursor = db_execute(conn, db_type, sql, params)
    return cursor.fetchall()

def init_db(conn: Any, db_type: str) -> None:
    """Initialize database tables using appropriate schema file, and seed categories."""
    schema_file = "schema_postgres.sql" if db_type == "postgres" else "schema_sqlite.sql"
    schema_path = Path(__file__).resolve().parent.parent.parent / "sql" / schema_file
    if not schema_path.exists():
        print(f"Error: Schema file not found at {schema_path}", file=sys.stderr)
        sys.exit(1)
    
    cursor = conn.cursor()
    if db_type == "sqlite":
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.executescript(schema_path.read_text(encoding="utf-8"))
    else:
        cursor.execute(schema_path.read_text(encoding="utf-8"))
        
    # Seed categories
    db_executemany(
        conn,
        db_type,
        """
        INSERT INTO crime_categories (
          metric, iccs_code, iccs_name, severity_score, flag_cyber, flag_weapon, flag_domestic, flag_organized_fraud
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(metric) DO UPDATE SET
          iccs_code=EXCLUDED.iccs_code,
          iccs_name=EXCLUDED.iccs_name,
          severity_score=EXCLUDED.severity_score,
          flag_cyber=EXCLUDED.flag_cyber,
          flag_weapon=EXCLUDED.flag_weapon,
          flag_domestic=EXCLUDED.flag_domestic,
          flag_organized_fraud=EXCLUDED.flag_organized_fraud
        """,
        CRIME_SEEDS
    )
    conn.commit()
    print(f"Database initialized and seeded ({db_type}).")

def is_hex_color(value: str | None) -> bool:
    import re
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""))

PRIORITY_COLORS = [
    "#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2",
    "#db2777", "#65a30d", "#ea580c", "#4f46e5", "#0d9488", "#be123c",
    "#9333ea", "#15803d", "#b45309", "#0369a1", "#c026d3", "#047857",
    "#991b1b", "#4338ca", "#115e59", "#a16207", "#9d174d", "#1d4ed8",
    "#7e22ce", "#166534", "#c2410c", "#0e7490", "#a21caf", "#be185d",
    "#1e40af", "#ca8a04", "#2f855a", "#9f1239", "#3730a3", "#0f766e",
]

def generated_color(index: int) -> str:
    import colorsys
    hue = ((index * 137.508) % 360) / 360
    saturation = 0.66 if index % 2 else 0.74
    lightness = 0.38 if index % 3 else 0.44
    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"

def color_for_index(index: int) -> str:
    if index < len(PRIORITY_COLORS):
        return PRIORITY_COLORS[index]
    return generated_color(index)

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
    db_execute(conn, db_type, sql)

def sync_metric_styles(conn: Any, db_type: str = "sqlite") -> int:
    ensure_metric_styles_table(conn, db_type)
    existing_rows = db_fetch_all(
        conn,
        db_type,
        "SELECT metric, color FROM official_metric_styles ORDER BY sort_order, metric"
    )
    existing = {row[0]: row[1] for row in existing_rows if is_hex_color(row[1])}
    metric_rows = db_fetch_all(
        conn,
        db_type,
        """
        SELECT metric, SUM(raw_value) AS total
        FROM official_statistics
        GROUP BY metric
        ORDER BY CASE WHEN metric = '總計' THEN 0 ELSE 1 END, total DESC, metric
        """
    )
    metrics = [row[0] for row in metric_rows]

    for index, metric in enumerate(metrics):
        color = existing.get(metric) or ("#334155" if metric == "總計" else color_for_index(index - 1 if index else 0))
        is_total = 1 if metric == "總計" else 0
        db_execute(
            conn,
            db_type,
            """
            INSERT INTO official_metric_styles (metric, color, sort_order, is_total, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(metric) DO UPDATE SET
              sort_order=EXCLUDED.sort_order,
              is_total=EXCLUDED.is_total,
              updated_at=CURRENT_TIMESTAMP
            """,
            (metric, color, index, is_total)
        )

    conn.commit()
    return len(metrics)

def load_metric_colors(conn: Any, db_type: str = "sqlite") -> dict[str, str]:
    try:
        rows = db_fetch_all(conn, db_type, "SELECT metric, color FROM official_metric_styles")
        colors = {row[0]: row[1] for row in rows if is_hex_color(row[1])}
        if colors:
            return colors
    except Exception:
        pass

    try:
        rows = db_fetch_all(
            conn,
            db_type,
            """
            SELECT metric, SUM(raw_value) AS total
            FROM official_statistics
            GROUP BY metric
            ORDER BY CASE WHEN metric = '總計' THEN 0 ELSE 1 END, total DESC, metric
            """
        )
    except Exception:
        return {}

    colors = {}
    for index, row in enumerate(rows):
        metric = row[0]
        colors[metric] = "#334155" if metric == "總計" else color_for_index(index - 1 if index else 0)
    return colors

def metric_color(metric: str, colors: dict[str, str], fallback_index: int = 0) -> str:
    color = colors.get(metric)
    if is_hex_color(color):
        return color
    return color_for_index(fallback_index)
