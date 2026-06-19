#!/usr/bin/env python
"""Build a searchable judgment metadata index from Judicial Yuan JSON files."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "fraud": ["詐欺", "詐騙"],
    "money_laundering": ["洗錢"],
    "sexual_offense": ["妨害性自主", "性侵", "猥褻"],
    "injury": ["傷害", "重傷", "過失傷害"],
    "traffic_injury": ["交通", "車禍", "過失傷害", "交簡", "交訴"],
    "public_integrity": ["貪污", "瀆職", "圖利", "收賄", "賄賂"],
    "election_law": ["選罷法", "公職人員選舉罷免法", "賄選"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_path(path_value: str, base_dir: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return base_dir / path


def classify_case(text: str, title: str, jcase: str) -> tuple[dict[str, bool], list[str]]:
    haystack = "\n".join([title or "", jcase or "", text or ""])
    flags: dict[str, bool] = {}
    matched: list[str] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        hits = [keyword for keyword in keywords if keyword in haystack]
        flags[category] = bool(hits)
        matched.extend(f"{category}:{hit}" for hit in hits)
    return flags, matched


def infer_case_domain(court_folder: str) -> str:
    if "刑事" in court_folder:
        return "criminal"
    if "民事" in court_folder:
        return "civil"
    if "行政" in court_folder:
        return "administrative"
    if "憲法" in court_folder:
        return "constitutional"
    if "懲戒" in court_folder:
        return "disciplinary"
    return "other"


def init_sqlite(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(schema_path.read_text(encoding="utf-8"))


def upsert_judgment(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    full_text: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO judgments (
          jid, source_month, court_folder, case_domain, file_path,
          jyear, jcase, jno, jdate, jtitle, jpdf, text_length, excerpt,
          category_flags, matched_keywords, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(jid) DO UPDATE SET
          source_month=excluded.source_month,
          court_folder=excluded.court_folder,
          case_domain=excluded.case_domain,
          file_path=excluded.file_path,
          jyear=excluded.jyear,
          jcase=excluded.jcase,
          jno=excluded.jno,
          jdate=excluded.jdate,
          jtitle=excluded.jtitle,
          jpdf=excluded.jpdf,
          text_length=excluded.text_length,
          excerpt=excluded.excerpt,
          category_flags=excluded.category_flags,
          matched_keywords=excluded.matched_keywords,
          updated_at=excluded.updated_at
        """,
        (
            row["jid"],
            row["source_month"],
            row["court_folder"],
            row["case_domain"],
            row["file_path"],
            row["jyear"],
            row["jcase"],
            row["jno"],
            row["jdate"],
            row["jtitle"],
            row["jpdf"],
            row["text_length"],
            row["excerpt"],
            row["category_flags"],
            row["matched_keywords"],
            utc_now(),
        ),
    )
    if full_text is not None:
        conn.execute(
            """
            INSERT INTO judgment_texts (jid, jfull)
            VALUES (?, ?)
            ON CONFLICT(jid) DO UPDATE SET jfull=excluded.jfull
            """,
            (row["jid"], full_text),
        )


def write_csv(rows: list[dict[str, Any]], csv_path: Path) -> None:
    if not rows:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "jid",
        "source_month",
        "court_folder",
        "case_domain",
        "file_path",
        "jyear",
        "jcase",
        "jno",
        "jdate",
        "jtitle",
        "jpdf",
        "text_length",
        "excerpt",
        "category_flags",
        "matched_keywords",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def maybe_push_remote(remote_url_env: str, rows: list[dict[str, Any]]) -> None:
    remote_url = os.environ.get(remote_url_env)
    if not remote_url:
        print(f"remote: skipped; set {remote_url_env} to enable remote writes")
        return
    try:
        import psycopg  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "remote: psycopg is not installed. Install psycopg or use n8n's "
            "PostgreSQL/Supabase node with sql/schema_postgres.sql."
        ) from exc
    with psycopg.connect(remote_url) as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO judgments (
                      jid, source_month, court_folder, case_domain, file_path,
                      jyear, jcase, jno, jdate, jtitle, jpdf, text_length,
                      excerpt, category_flags, matched_keywords, updated_at
                    )
                    VALUES (
                      %(jid)s, %(source_month)s, %(court_folder)s, %(case_domain)s,
                      %(file_path)s, %(jyear)s, %(jcase)s, %(jno)s,
                      to_date(%(jdate)s, 'YYYYMMDD'), %(jtitle)s, %(jpdf)s,
                      %(text_length)s, %(excerpt)s, %(category_flags)s::jsonb,
                      %(matched_keywords)s::jsonb, now()
                    )
                    ON CONFLICT (jid) DO UPDATE SET
                      source_month=excluded.source_month,
                      court_folder=excluded.court_folder,
                      case_domain=excluded.case_domain,
                      file_path=excluded.file_path,
                      jyear=excluded.jyear,
                      jcase=excluded.jcase,
                      jno=excluded.jno,
                      jdate=excluded.jdate,
                      jtitle=excluded.jtitle,
                      jpdf=excluded.jpdf,
                      text_length=excluded.text_length,
                      excerpt=excluded.excerpt,
                      category_flags=excluded.category_flags,
                      matched_keywords=excluded.matched_keywords,
                      updated_at=now()
                    """,
                    row,
                )
        conn.commit()
    print(f"remote: upserted {len(rows)} rows")


def build_index(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path.cwd()
    config = load_json_config(args.config)

    source_dir = Path(args.source_dir or config.get("raw_judgments_dir", ""))
    if not source_dir.exists():
        raise SystemExit(f"source directory does not exist: {source_dir}")

    source_month = args.month or config.get("source_month") or source_dir.name
    local_db_value = args.local_db or config.get("local_db", {}).get(
        "path", "data/local/public_safety.sqlite"
    )
    local_db = resolve_path(local_db_value, repo_root)
    local_db.parent.mkdir(parents=True, exist_ok=True)

    schema_path = repo_root / "sql" / "schema_sqlite.sql"
    store_full_text = args.store_full_text or bool(
        config.get("indexing", {}).get("store_full_text", False)
    )
    excerpt_chars = int(args.excerpt_chars or config.get("indexing", {}).get("excerpt_chars", 500))
    export_csv_value = args.export_csv or config.get("exports", {}).get("metadata_csv")
    export_csv = resolve_path(export_csv_value, repo_root) if export_csv_value else None

    started_at = utc_now()
    run_id = str(uuid.uuid4())
    rows_for_export: list[dict[str, Any]] = []
    files_seen = 0
    indexed = 0
    errors = 0

    with sqlite3.connect(local_db) as conn:
        init_sqlite(conn, schema_path)
        conn.execute(
            """
            INSERT INTO pipeline_runs (
              run_id, source_month, source_dir, local_db_path, started_at, status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, source_month, str(source_dir), str(local_db), started_at, "running"),
        )

        for path in source_dir.rglob("*.json"):
            files_seen += 1
            try:
                raw = path.read_text(encoding="utf-8", errors="ignore")
                doc = json.loads(raw)
                jfull = doc.get("JFULL") or ""
                flags, matched = classify_case(jfull, doc.get("JTITLE") or "", doc.get("JCASE") or "")
                court_folder = path.parent.name
                row = {
                    "jid": doc.get("JID") or path.stem,
                    "source_month": source_month,
                    "court_folder": court_folder,
                    "case_domain": infer_case_domain(court_folder),
                    "file_path": str(path),
                    "jyear": doc.get("JYEAR"),
                    "jcase": doc.get("JCASE"),
                    "jno": doc.get("JNO"),
                    "jdate": doc.get("JDATE"),
                    "jtitle": doc.get("JTITLE"),
                    "jpdf": doc.get("JPDF"),
                    "text_length": len(jfull),
                    "excerpt": jfull[:excerpt_chars],
                    "category_flags": json.dumps(flags, ensure_ascii=False),
                    "matched_keywords": json.dumps(matched, ensure_ascii=False),
                }
                upsert_judgment(conn, row, jfull if store_full_text else None)
                rows_for_export.append(row)
                indexed += 1
                if args.limit and indexed >= args.limit:
                    break
                if indexed % args.commit_every == 0:
                    conn.commit()
                    if args.verbose:
                        print(f"indexed {indexed} files...")
            except Exception as exc:
                errors += 1
                print(f"error: {path}: {exc}", file=sys.stderr)

        status = "complete" if errors == 0 else "complete_with_errors"
        conn.execute(
            """
            UPDATE pipeline_runs
            SET finished_at=?, files_seen=?, files_indexed=?, errors=?, status=?
            WHERE run_id=?
            """,
            (utc_now(), files_seen, indexed, errors, status, run_id),
        )
        conn.commit()

    if export_csv is not None:
        write_csv(rows_for_export, export_csv)
    if args.push_remote:
        maybe_push_remote(args.remote_url_env, rows_for_export)

    return {
        "run_id": run_id,
        "source_month": source_month,
        "source_dir": str(source_dir),
        "local_db": str(local_db),
        "export_csv": str(export_csv) if export_csv else None,
        "files_seen": files_seen,
        "files_indexed": indexed,
        "errors": errors,
        "store_full_text": store_full_text,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/pipeline.example.json"))
    parser.add_argument("--source-dir")
    parser.add_argument("--month")
    parser.add_argument("--local-db")
    parser.add_argument("--export-csv")
    parser.add_argument("--excerpt-chars", type=int)
    parser.add_argument("--store-full-text", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--commit-every", type=int, default=1000)
    parser.add_argument("--push-remote", action="store_true")
    parser.add_argument("--remote-url-env", default="PUBLIC_SAFETY_DATABASE_URL")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    result = build_index(parse_args())
    print(json.dumps(result, ensure_ascii=False, indent=2))
