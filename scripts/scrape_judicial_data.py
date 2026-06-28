#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Scrape targeted judgments and extract demographic metadata (Age, Gender, Occupation, Education, Income, Birth-City)."""

from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import re
import sqlite3
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Target categories and keywords
KEYWORDS = {
    "fraud": ["詐欺", "詐騙"],
    "money_laundering": ["洗錢"],
    "injury": ["傷害", "重傷", "過失傷害"],
    "public_integrity": ["貪污", "瀆職", "圖利", "收賄", "賄賂"],
    "election_law": ["選罷法", "公職人員選舉罷免法", "賄選"],
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def get_unverified_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()

def http_get(url: str, headers: dict[str, str] | None = None) -> str:
    ctx = get_unverified_context()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            **(headers or {})
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        raise RuntimeError(f"HTTP GET to {url} failed: {e}")

# Demographic Regex Parsers
def parse_demographics(text: str) -> dict[str, Any]:
    """Parse demographic fields from judgment text (best effort)."""
    demographics = {
        "age": None,
        "gender": None,
        "occupation": None,
        "education": None,
        "income_level": None,
        "birth_city": None
    }
    
    # 1. Gender (性別)
    gender_match = re.search(r"被告\s+\w+\s*，(男|女)", text)
    if gender_match:
        demographics["gender"] = gender_match.group(1)
    else:
        # Fallback gender search
        if re.search(r"被告\s+.*，性別：男", text) or re.search(r"，男，", text[:2000]):
            demographics["gender"] = "男"
        elif re.search(r"被告\s+.*，性別：女", text) or re.search(r"，女，", text[:2000]):
            demographics["gender"] = "女"
            
    # 2. Age / Birth Year (年齡/出生年)
    birth_year = None
    # Pattern: 民國 75 年生 / 民國75年生 / 民國七十五年生
    birth_match = re.search(r"民國\s*(\d{2,3})\s*年\s*生", text)
    if birth_match:
        birth_year = int(birth_match.group(1))
    else:
        # Check complete date: 民國75年8月10日生
        birth_match_date = re.search(r"民國\s*(\d{2,3})\s*年\s*\d+\s*月\s*\d+\s*日生", text)
        if birth_match_date:
            birth_year = int(birth_match_date.group(1))
            
    if birth_year:
        # Approximate age at current time (assume current year ROC equivalent)
        current_roc_year = datetime.datetime.now().year - 1911
        demographics["age"] = current_roc_year - birth_year
    else:
        # Direct age reference: 35歲, 歲數為40
        age_match = re.search(r"(\d{2})\s*歲", text[:3000])
        if age_match:
            demographics["age"] = int(age_match.group(1))

    # 3. Occupation (職業)
    # Search in defendant details: 職業：工 / 職業為臨時工
    occ_match = re.search(r"職業[：為\s]+([^\s，\n、]+)", text[:3000])
    if occ_match:
        demographics["occupation"] = occ_match.group(1).strip()
    else:
        # Sentencing mentions: 從事餐飲業 / 擔任助理
        occ_sentence = re.search(r"(從事|擔任|從事於|為業)[：\s]*([^\s，。\n、]{2,10})", text[:3000])
        if occ_sentence:
            demographics["occupation"] = occ_sentence.group(2).strip()

    # 4. Education (教育程度 / 智識程度)
    # Header check: 教育程度：大專畢業
    edu_match = re.search(r"教育程度[：為\s]+([^\s，\n、]+)", text[:3000])
    if edu_match:
        demographics["education"] = edu_match.group(1).strip()
    else:
        # Sentencing reasons: 大學畢業之智識程度 / 國小畢業之智識程度 / 智識程度為高職畢業
        edu_sentence = re.search(r"([^\s，。、\n]{2,15})(畢業|肄業|學歷|學位)之(智識|知識)程度", text)
        if edu_sentence:
            demographics["education"] = (edu_sentence.group(1) + edu_sentence.group(2)).strip()
        else:
            edu_alt = re.search(r"(智識|知識)程度[：為\s]*([^\s，。、\n]{2,10})", text)
            if edu_alt:
                demographics["education"] = edu_alt.group(2).strip()

    # 5. Income / Economy (家庭經濟 / 財產狀況)
    # Pattern: 家庭經濟狀況勉可維持 / 家庭生活狀況貧寒
    income_match = re.search(r"家庭(經濟|生活)狀況[：為\s]*([^\s，。、\n]{2,10})", text)
    if income_match:
        demographics["income_level"] = income_match.group(2).strip()
    else:
        # Alternative: 家境勉可維持 / 家境清寒
        income_alt = re.search(r"家境[：為\s]*([^\s，。、\n]{2,10})", text)
        if income_alt:
            demographics["income_level"] = income_alt.group(2).strip()

    # 6. Birth-City / Residence (出生地/設籍地)
    # Pattern: 住基隆市 / 設籍台北市 / 戶籍設在高雄市
    city_match = re.search(r"(住|設籍地|戶籍設在|戶籍設於|戶籍地)[：\s]*([^\s，\n、()（）]{2,10}?(市|縣))", text[:3000])
    if city_match:
        demographics["birth_city"] = city_match.group(2).strip()
        
    return demographics

def clean_html(html_str: str) -> str:
    """Strip HTML tags and decode entities."""
    # Remove script/style
    html_str = re.sub(r'<(script|style).*?>.*?</\1>', '', html_str, flags=re.DOTALL|re.IGNORECASE)
    # Remove other tags
    html_str = re.sub(r'<[^>]+>', ' ', html_str)
    # Decode html entities
    return html.unescape(html_str)

def db_execute(conn: Any, db_type: str, sql: str, params: tuple | list = ()) -> Any:
    cursor = conn.cursor()
    if db_type == "postgres":
        sql = sql.replace("?", "%s")
    cursor.execute(sql, params)
    return cursor

def save_judgment(conn: Any, db_type: str, item: dict[str, Any], month: str) -> None:
    """Save extracted judgment details to the database."""
    flags_json = json.dumps(item["category_flags"])
    keywords_json = json.dumps(item["matched_keywords"])
    
    if db_type == "postgres":
        from psycopg2.extras import Json
        flags_param = Json(item["category_flags"])
        keywords_param = Json(item["matched_keywords"])
    else:
        flags_param = flags_json
        keywords_param = keywords_json

    sql = """
    INSERT INTO judgments (
      jid, source_month, court_folder, case_domain, file_path,
      jyear, jcase, jno, jdate, jtitle, jpdf, text_length, excerpt,
      category_flags, matched_keywords,
      age, gender, occupation, education, income_level, birth_city,
      updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
      age=EXCLUDED.age,
      gender=EXCLUDED.gender,
      occupation=EXCLUDED.occupation,
      education=EXCLUDED.education,
      income_level=EXCLUDED.income_level,
      birth_city=EXCLUDED.birth_city,
      updated_at=CURRENT_TIMESTAMP
    """
    
    # Excerpt first 200 chars for dashboard snippet
    excerpt = item["full_text"][:200] + "..." if len(item["full_text"]) > 200 else item["full_text"]
    
    db_execute(
        conn,
        db_type,
        sql,
        (
            item["jid"], month, item["court"], "criminal", "Scraper",
            item["jyear"], item["jcase"], item["jno"], item["jdate"], item["jtitle"],
            item["jpdf"], len(item["full_text"]), excerpt,
            flags_param, keywords_param,
            item["demographics"]["age"], item["demographics"]["gender"],
            item["demographics"]["occupation"], item["demographics"]["education"],
            item["demographics"]["income_level"], item["demographics"]["birth_city"]
        )
    )

def scrape_and_parse(conn: Any, db_type: str, start_date: str, end_date: str, limit: int = 15) -> int:
    """Scrape recent judgments, parse demographics and save them to the DB."""
    # Convert dates to judicial search format (YYYYMMDD)
    sdate = start_date.replace("-", "")
    edate = end_date.replace("-", "")
    month_str = sdate[:6]
    
    total_added = 0
    print(f"Scraper: Fetching judgments published between {start_date} and {end_date}...")
    
    for cat_name, keywords in KEYWORDS.items():
        if total_added >= limit:
            break
            
        keyword = keywords[0] # Search first keyword of category
        print(f"Scraper: Querying category '{cat_name}' with keyword '{keyword}'...")
        
        # Build search query URL. Failed or blocked requests must not create mock records.
        query_url = f"https://judgment.judicial.gov.tw/FJUD/qryresult.aspx?kw={urllib.parse.quote(keyword)}&sdate={sdate}&edate={edate}&judtype=JU1"
        
        try:
            time.sleep(0.5) # Polite throttle delay
            html_content = http_get(query_url)
            
            # Find links to data.aspx?id=... (JID)
            jids = list(set(re.findall(r'data\.aspx\?id=([^"\'>\s]+)', html_content)))
            print(f"Scraper: Found {len(jids)} matching cases for '{keyword}' on the search page.")
            
            if len(jids) == 0:
                print(f"Scraper: No verified cases found for '{keyword}'. Skipping this category without fallback data.")
                continue
                
            for jid_encoded in jids[:5]:
                if total_added >= limit:
                    break
                    
                jid = urllib.parse.unquote(jid_encoded)
                case_url = f"https://judgment.judicial.gov.tw/FJUD/data.aspx?id={jid_encoded}"
                
                try:
                    time.sleep(1.5) # Throttling delay
                    case_html = http_get(case_url)
                    clean_txt = clean_html(case_html)
                    
                    # Basic metadata parsing from page
                    # JID format: COURT,JYEAR,JCASE,JNO,JDATE,JID_SUFFIX
                    parts = jid.split(",")
                    court = parts[0] if len(parts) > 0 else "UnknownCourt"
                    jyear = parts[1] if len(parts) > 1 else ""
                    jcase = parts[2] if len(parts) > 2 else ""
                    jno = parts[3] if len(parts) > 3 else ""
                    
                    # Try to extract ruling date from title or details
                    jdate = start_date # Fallback
                    date_match = re.search(r"中華民國\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", clean_txt)
                    if date_match:
                        yr = int(date_match.group(1)) + 1911
                        mo = int(date_match.group(2))
                        dy = int(date_match.group(3))
                        jdate = f"{yr}-{mo:02d}-{dy:02d}"
                        
                    jtitle = f"違反{cat_name}案件"
                    title_match = re.search(r"案由[：\s]+([^\s\n，。]+)", clean_txt)
                    if title_match:
                        jtitle = title_match.group(1).strip()
                        
                    # Extract demographics
                    demo_data = parse_demographics(clean_txt)
                    
                    item = {
                        "jid": jid,
                        "court": court,
                        "jyear": jyear,
                        "jcase": jcase,
                        "jno": jno,
                        "jdate": jdate,
                        "jtitle": jtitle,
                        "jpdf": f"https://judgment.judicial.gov.tw/FJUD/pdf.aspx?id={jid_encoded}",
                        "full_text": clean_txt,
                        "category_flags": {cat: cat == cat_name for cat in KEYWORDS},
                        "matched_keywords": [keyword],
                        "demographics": demo_data
                    }
                    
                    save_judgment(conn, db_type, item, month_str)
                    conn.commit()
                    total_added += 1
                    print(f"Scraper: Successfully parsed and saved JID {jid} (Gender: {demo_data['gender']}, Age: {demo_data['age']})")
                except Exception as e:
                    print(f"Scraper: Failed to fetch case details for JID {jid}: {e}", file=sys.stderr)
                    
        except Exception as e:
            print(f"Scraper: Web crawling blocked or failed for keyword '{keyword}' ({e}). Skipping without fallback data.")
            
    return total_added

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", help="Scrape judgments published in specific month (YYYYMM)")
    parser.add_argument("--days", type=int, default=3, help="Number of recent days to scrape (default: 3)")
    parser.add_argument("--limit", type=int, default=15, help="Total execution limit (default: 15)")
    args = parser.parse_args()

    # Determine date range
    today = datetime.date.today()
    if args.month:
        year = int(args.month[:4])
        month = int(args.month[4:])
        # Last day of that month
        if month == 12:
            next_month = datetime.date(year + 1, 1, 1)
        else:
            next_month = datetime.date(year, month + 1, 1)
        last_day = next_month - datetime.timedelta(days=1)
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month:02d}-{last_day.day:02d}"
    else:
        # Last N days
        start = today - datetime.timedelta(days=args.days)
        start_date = start.strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

    # Connect DB
    pg_url = os.environ.get("PUBLIC_SAFETY_DATABASE_URL")
    if pg_url:
        import psycopg2
        conn = psycopg2.connect(pg_url)
        db_type = "postgres"
    else:
        db_path = Path("data/local/public_safety.sqlite")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        db_type = "sqlite"
        
    try:
        count = scrape_and_parse(conn, db_type, start_date, end_date, args.limit)
        print(f"Scraper Run Complete: Synced {count} judgments.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
