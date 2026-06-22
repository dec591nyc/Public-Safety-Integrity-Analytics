#!/usr/bin/env python
"""Sync judgment metadata from Judicial Yuan Open Data API using parallel calls and save to DB."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
import urllib.request

# API Endpoints
PORTAL_API_URL = "https://data.judicial.gov.tw"
AUTH_API = f"{PORTAL_API_URL}/jdg/api/Auth"
JLIST_API = f"{PORTAL_API_URL}/jdg/api/JList"
JDOC_API = f"{PORTAL_API_URL}/jdg/api/JDoc"

CATEGORY_KEYWORDS = {
    "fraud": ["詐欺", "詐騙"],
    "money_laundering": ["洗錢"],
    "sexual_offense": ["妨害性自主", "性侵", "猥褻"],
    "injury": ["傷害", "重傷", "過失傷害"],
    "traffic_injury": ["交通", "車禍", "過失傷害", "交簡", "交訴"],
    "public_integrity": ["貪污", "瀆職", "圖利", "收賄", "賄賂"],
    "election_law": ["選罷法", "公職人員選舉罷免法", "賄選"],
}

def get_unverified_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()

def post_json(url: str, data: dict[str, Any]) -> Any:
    ctx = get_unverified_context()
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP Error {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"API call to {url} failed: {e}")

def db_execute(conn: Any, db_type: str, sql: str, params: tuple | list = ()) -> Any:
    cursor = conn.cursor()
    if db_type == "postgres":
        sql = sql.replace("?", "%s")
    cursor.execute(sql, params)
    return cursor

def infer_case_domain_from_jid(jid: str) -> str:
    first_part = jid.split(",")[0]
    if not first_part:
        return "unknown"
    last_char = first_part[-1].upper()
    if last_char == "V":
        return "civil"
    if last_char == "M":
        return "criminal"
    if last_char == "A":
        return "administrative"
    if last_char == "P":
        return "disciplinary"
    if last_char == "C":
        return "constitutional"
    return "other"

def classify_by_title(jtitle: str) -> tuple[dict[str, bool], list[str]]:
    flags = {}
    matched = []
    title_str = jtitle or ""
    for cat, keywords in CATEGORY_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in title_str]
        flags[cat] = bool(hits)
        matched.extend(f"{cat}:{hit}" for hit in hits)
    return flags, matched

def format_jdate(jdate_str: str) -> str:
    s = (jdate_str or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s

def fetch_single_jdoc(token: str, jid: str) -> dict[str, Any] | None:
    try:
        res = post_json(JDOC_API, {"token": token, "j": jid})
        if not res or "error" in res:
            return None
        
        jtitle = res.get("JTITLE", "")
        jdate = res.get("JDATE", "")
        
        flags, matched = classify_by_title(jtitle)
        
        return {
            "jid": res.get("JID", jid),
            "jyear": res.get("JYEAR", ""),
            "jcase": res.get("JCASE", ""),
            "jno": res.get("JNO", ""),
            "jdate": format_jdate(jdate),
            "jtitle": jtitle,
            "category_flags": flags,
            "matched_keywords": matched
        }
    except Exception as e:
        print(f"Error fetching JID {jid}: {e}", file=sys.stderr)
        return None

def upsert_judgment_db(conn: Any, db_type: str, item: dict[str, Any]) -> None:
    flags = item["category_flags"]
    keywords = item["matched_keywords"]
    
    if db_type == "postgres":
        from psycopg2.extras import Json
        flags_param = Json(flags)
        keywords_param = Json(keywords)
    else:
        flags_param = json.dumps(flags)
        keywords_param = json.dumps(keywords)
        
    sql = """
    INSERT INTO judgments (
      jid, source_month, court_folder, case_domain, file_path,
      jyear, jcase, jno, jdate, jtitle, jpdf, text_length, excerpt,
      category_flags, matched_keywords, updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(jid) DO UPDATE SET
      source_month=EXCLUDED.source_month,
      court_folder=EXCLUDED.court_folder,
      case_domain=EXCLUDED.case_domain,
      file_path=EXCLUDED.file_path,
      jyear=EXCLUDED.jyear,
      jcase=EXCLUDED.jcase,
      jno=EXCLUDED.jno,
      jdate=EXCLUDED.jdate,
      jtitle=EXCLUDED.jtitle,
      jpdf=EXCLUDED.jpdf,
      text_length=EXCLUDED.text_length,
      excerpt=EXCLUDED.excerpt,
      category_flags=EXCLUDED.category_flags,
      matched_keywords=EXCLUDED.matched_keywords,
      updated_at=CURRENT_TIMESTAMP
    """
    
    court_folder = item["jid"].split(",")[0]
    case_domain = infer_case_domain_from_jid(item["jid"])
    source_month = item["jdate"].replace("-", "")[:6] if item["jdate"] else "unknown"
    
    db_execute(
        conn,
        db_type,
        sql,
        (
            item["jid"], source_month, court_folder, case_domain, "API",
            item["jyear"], item["jcase"], item["jno"], item["jdate"], item["jtitle"],
            "", 0, "", flags_param, keywords_param
        )
    )

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", help="Judicial Yuan portal username")
    parser.add_argument("--password", help="Judicial Yuan portal password")
    parser.add_argument("--workers", type=int, default=16, help="Number of thread workers (default: 16)")
    parser.add_argument("--db", type=Path, default=Path("data/local/public_safety.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("data/api_judgments_metadata.json"), help="Output metadata file path")
    args = parser.parse_args()

    user = args.user or os.environ.get("JUDICIAL_PORTAL_USER")
    password = args.password or os.environ.get("JUDICIAL_PORTAL_PASSWORD")

    if not user or not password:
        print("Error: Username and Password are required. Please provide them via parameters or env variables.", file=sys.stderr)
        sys.exit(1)

    # Determine DB connection type
    pg_url = os.environ.get("PUBLIC_SAFETY_DATABASE_URL")
    if pg_url:
        print("Connecting to PostgreSQL Database (Supabase)...")
        import psycopg2
        conn = psycopg2.connect(pg_url)
        db_type = "postgres"
    else:
        print(f"Connecting to SQLite Database ({args.db})...")
        conn = sqlite3.connect(args.db)
        db_type = "sqlite"

    try:
        print("Authenticating with Judicial Yuan Open Data API...")
        auth_res = post_json(AUTH_API, {"user": user, "password": password})
        token = auth_res.get("Token")
        if not token:
            print(f"Authentication failed: {auth_res.get('error', 'Unknown Error')}", file=sys.stderr)
            sys.exit(1)
        print("Authentication successful. Token obtained.")

        print("Fetching judgment change list (JList)...")
        jlist_res = post_json(JLIST_API, {"token": token})
        if not isinstance(jlist_res, list):
            print("Error: Unexpected change list response format.", file=sys.stderr)
            sys.exit(1)

        # Gather all JIDs from list
        jids: list[str] = []
        for item in jlist_res:
            jids.extend(item.get("list", []))
            
        jids = list(dict.fromkeys(jids))
        total_jids = len(jids)
        print(f"Found {total_jids} unique judgment JIDs to process.")

        if not jids:
            print("No judgments found in the 7-day change list.")
            return

        # Process JDocs in parallel
        print(f"Fetching judgment details in parallel using {args.workers} workers...")
        results: list[dict[str, Any]] = []
        completed = 0
        
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(fetch_single_jdoc, token, jid): jid for jid in jids}
            for future in as_completed(futures):
                res = future.result()
                completed += 1
                if res:
                    results.append(res)
                    # Write directly to Database
                    try:
                        upsert_judgment_db(conn, db_type, res)
                        conn.commit()
                    except Exception as e:
                        print(f"Failed to save JID {res['jid']} to DB: {e}", file=sys.stderr)
                if completed % 10 == 0 or completed == total_jids:
                    print(f"Progress: {completed}/{total_jids} processed (Successfully saved count: {len(results)})")

        # Also write JSON backup file
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
            
        print(f"\nCompleted! Saved metadata for {len(results)} judgments to DB ({db_type}) and JSON backup: {args.output}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
