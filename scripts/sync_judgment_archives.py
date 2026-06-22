#!/usr/bin/env python
"""Sync judgment RAR archives from the Judicial Yuan Open Data API since 1993."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

# Base URL for the Judicial Yuan Open Data Portal
PORTAL_URL = "https://opendata.judicial.gov.tw"
API_CATEGORIES = f"{PORTAL_URL}/data/api/rest/categories"

def get_unverified_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()

def fetch_json(url: str, headers: dict[str, str] | None = None) -> Any:
    ctx = get_unverified_context()
    req = Request(url, headers=headers or {})
    try:
        with urlopen(req, timeout=30, context=ctx) as response:
            if response.status != 200:
                raise RuntimeError(f"API call to {url} failed with HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}")

def is_valid_archive(path: Path) -> bool:
    """Check if the file is a valid non-empty ZIP or RAR archive."""
    if not path.exists():
        return False
    # A valid monthly archive is typically at least 10KB
    if path.stat().st_size < 1024 * 10:
        return False
    try:
        with open(path, "rb") as f:
            header = f.read(4)
            # RAR signature: Rar! (0x52 0x61 0x72 0x21)
            # ZIP signature: PK.. (0x50 0x4b 0x03 0x04)
            if header.startswith(b"Rar!") or header.startswith(b"PK\x03\x04"):
                return True
    except OSError:
        pass
    return False

def parse_date(title: str) -> tuple[int, int] | None:
    """Extract Gregorian or ROC year and month from dataset title."""
    # Try YYYYMM format (e.g. 202604)
    match_greg = re.search(r"(\d{6})", title)
    if match_greg:
        ym = match_greg.group(1)
        return int(ym[:4]), int(ym[4:])
    
    # Try ROC format (e.g. 102年12月)
    match_roc = re.search(r"(\d+)年(\d+)月", title)
    if match_roc:
        return int(match_roc.group(1)) + 1911, int(match_roc.group(2))
    return None

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=1993, help="Start Gregorian year (default: 1993)")
    parser.add_argument("--end-year", type=int, default=datetime.now().year if 'datetime' in globals() else 2026, help="End Gregorian year")
    parser.add_argument("--dest", type=Path, default=Path("data/raw_judgments"), help="Destination directory for downloads")
    parser.add_argument("--username", help="Judicial Yuan portal username (optional)")
    parser.add_argument("--password", help="Judicial Yuan portal password (optional)")
    parser.add_argument("--session-cookie", help="Direct session cookie value if logged in via browser (optional)")
    parser.add_argument("--limit", type=int, help="Limit number of archives to download in this run")
    parser.add_argument("--dry-run", action="store_true", help="List fileset links without downloading")
    args = parser.parse_args()

    # Resolve environment variables if not provided
    username = args.username or os.environ.get("JUDICIAL_PORTAL_USER")
    password = args.password or os.environ.get("JUDICIAL_PORTAL_PASSWORD")
    session_cookie = args.session_cookie or os.environ.get("JUDICIAL_PORTAL_SESSION")

    if session_cookie:
        cookie_path = None
        if session_cookie.startswith("@"):
            cookie_path = Path(session_cookie[1:])
        elif Path(session_cookie).exists() and Path(session_cookie).is_file():
            cookie_path = Path(session_cookie)
            
        if cookie_path:
            if cookie_path.exists():
                session_cookie = cookie_path.read_text(encoding="utf-8").strip()
                print(f"Loaded session cookie from file: {cookie_path}")
            else:
                print(f"Warning: Cookie file {cookie_path} not found.", file=sys.stderr)

    args.dest.mkdir(parents=True, exist_ok=True)

    # Set up request headers for auth
    headers = {"User-Agent": "Public-Safety-Integrity-Analytics/0.1"}
    if session_cookie:
        headers["Cookie"] = session_cookie
    elif username and password:
        # If credentials are provided, we can log in or prompt to fetch token
        # In a real environment, open-data authentication is cookies-based or token-based.
        # We will add it to authorization headers.
        print("Note: Authenticating using provided username/password credentials.")
        # Simulating basic auth header or login process if supported by Judicial Yuan
        import base64
        creds = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {creds}"

    print("Fetching Judicial Yuan open data category list...")
    try:
        categories = fetch_json(API_CATEGORIES)
    except Exception as e:
        print(f"Error: Could not retrieve categories list: {e}", file=sys.stderr)
        sys.exit(1)

    # Find the categories related to judgments (裁判書)
    judgment_categories = []
    for cat in categories:
        if "裁判" in cat.get("categoryName", "") or "司法" in cat.get("categoryName", ""):
            judgment_categories.append(cat)
            
    if not judgment_categories:
        # Fallback to check all categories
        judgment_categories = categories

    print(f"Found {len(judgment_categories)} relevant categories. Searching for resources...")
    
    filesets_to_download = []
    for cat in judgment_categories:
        cat_no = cat.get("categoryNo")
        cat_name = cat.get("categoryName")
        url_resources = f"{PORTAL_URL}/data/api/rest/categories/{cat_no}/resources"
        try:
            resources = fetch_json(url_resources)
            for res in resources:
                res_title = res.get("title", "")
                filesets = res.get("filesets", [])
                
                # Check if this resource is a judgment archive
                if "裁判書" in res_title:
                    greg_date = parse_date(res_title)
                    if greg_date:
                        greg_yr, greg_mo = greg_date
                        
                        if args.start_year <= greg_yr <= args.end_year:
                            for fs in filesets:
                                fs_id = fs.get("fileSetId")
                                format_type = fs.get("resourceFormat", "").lower()
                                
                                # We want RAR or ZIP formats containing the bulk files
                                if format_type in ["rar", "zip"]:
                                    filesets_to_download.append({
                                        "year": greg_yr,
                                        "month": greg_mo,
                                        "title": res_title,
                                        "fileSetId": fs_id,
                                        "format": format_type,
                                        "url": f"{PORTAL_URL}/api/FilesetLists/{fs_id}/file"
                                    })
        except Exception as e:
            # Skip errors for single category resource lookups
            continue

    # Sort filesets chronologically
    filesets_to_download.sort(key=lambda x: (x["year"], x["month"]))
    print(f"Found {len(filesets_to_download)} judgment monthly filesets between {args.start_year} and {args.end_year}.")

    if not filesets_to_download:
        print("No matching judgment filesets found in the specified year range.")
        return

    download_count = 0
    for fs in filesets_to_download:
        if args.limit and download_count >= args.limit:
            print(f"Reached download limit of {args.limit}.")
            break

        month_str = f"{fs['year']}{fs['month']:02d}"
        file_name = f"{month_str}_judgments.{fs['format']}"
        output_path = args.dest / file_name

        print(f"[{download_count + 1}] Fileset {fs['fileSetId']}: {fs['title']} ({fs['format'].upper()})")
        print(f"    Source URL: {fs['url']}")
        print(f"    Output Path: {output_path}")

        if args.dry_run:
            download_count += 1
            continue

        if output_path.exists():
            if is_valid_archive(output_path):
                print(f"    Already exists and is valid. Skipping.")
                download_count += 1
                continue
            else:
                print(f"    Suspected corrupted/error file exists ({output_path.stat().st_size} bytes). Re-downloading...")
                try:
                    output_path.unlink()
                except OSError:
                    pass

        # Start download
        ctx = get_unverified_context()
        req = Request(fs["url"], headers=headers)
        try:
            with urlopen(req, timeout=60, context=ctx) as response:
                if response.status != 200:
                    print(f"    Download failed with HTTP {response.status}. Session credentials may be required.", file=sys.stderr)
                    continue
                
                # Write to disk
                with open(output_path, "wb") as f:
                    # Download block by block
                    while True:
                        chunk = response.read(1024 * 1024) # 1MB chunks
                        if not chunk:
                            break
                        f.write(chunk)
            
            # Post-download validation
            if is_valid_archive(output_path):
                print("    Successfully downloaded and validated.")
                download_count += 1
            else:
                # Try to read the error payload (usually WAF block HTML)
                try:
                    error_preview = output_path.read_text(encoding="utf-8", errors="ignore")[:300].strip()
                    print(f"    Error: Downloaded content is not a valid archive. WAF/Error Preview:\n{error_preview}", file=sys.stderr)
                except Exception:
                    print("    Error: Downloaded content is invalid/empty.", file=sys.stderr)
                
                # Remove the invalid download to allow retry
                try:
                    output_path.unlink()
                except OSError:
                    pass
        except Exception as e:
            print(f"    Failed to download: {e}", file=sys.stderr)

    print(f"\nCompleted. Processed {download_count} filesets.")

if __name__ == "__main__":
    from datetime import datetime
    main()
