# Dynamic Judgment Storage Architecture

Date: 2026-06-23

## Decision Summary

The project shifts from a heavy bulk judgment RAR warehouse to a **dynamic web scraping and concise daily storage architecture**.
1. **Targeted Scraping:** Query the Judicial Yuan public search system daily for newly published judgments matching targeted categories, extracting only metadata, structured demographic variables (Age, Gender, Income, Birth-City, Occupation, Education-Level), and (advanced phase) political CEC candidate matches.
2. **Transient Text Processing:** Raw HTML or full texts of judgments are parsed and then immediately discarded. We do not store large uncompressed judgment bodies or PDF files on our servers.
3. **Opinion Alignment:** Collect social forum and news metadata in separate lean tables, discarding article bodies after computing sentiment score and topic category.

This dynamic approach keeps storage footprint extremely small, making the project highly cost-effective and perfectly compatible with local development and cloud free tiers.

---

## Storage Footprint Comparison

| Metrics | Dynamic Scraping (Current Strategy) | Bulk RAR Warehousing (Legacy) |
| --- | --- | --- |
| **Ingestion Target** | Concise (Targeted cases only) | Massive (100% of Taiwan court judgments) |
| **Yearly DB Size** | < 50 MB (SQLite / PostgreSQL) | ~ 2.5 GB SQLite index |
| **Raw JSON Size** | 0 MB (Transiently discarded) | ~ 7.0 GB uncompressed text |
| **Cloud Storage** | 0 MB (No PDFs/Raw text stored) | > 1.0 GB storage (RAR archives) |
| **API Costs** | Free (Public scraping) | Free (If portal members) |

---

## Recommended Storage Layers

### 1. Local SQLite Database
- Database File: `data/local/public_safety.sqlite`
- Structure: Lightweight tables storing:
  - Case metadata (dates, court name, title, case code)
  - Extracted demographics (Age, Gender, Occupation, Education-Level, Income description, Birth-City)
  - Public opinion metrics (dates, source, category, sentiment score, URL reference)
  - (Advanced) CEC candidates and political party rosters.
- Advantage: Extremely fast queries, fully portable, easily backed up.

### 2. Supabase Free Plan Fit
- Free Quotas: 500 MB Postgres database, 1 GB file storage.
- Storage Fit: Under the dynamic scraping model, we only store structured counters, metrics, and metadata. The database size is estimated to grow at only **1.5 MB to 3 MB per month** (depending on scraping frequency). A 500 MB database will easily last for **over 10 years of daily operation**.
- Deletion Policy: Raw crawled text is never saved to Supabase storage, completely staying within the 1 GB free file storage limit.

---

## Ingestion Pipelines and Boundaries

- **`scripts/scrape_judicial_data.py` (Planned):** Performs daily query scrapes from `https://judgment.judicial.gov.tw/`, parses demographic attributes, logs processing statistics, and commits metadata to the database before discarding raw text.
- **`scripts/run_daily_update.py`:** Orchestrates the daily update schedule for both the judicial scraper and opinion crawler.
- **CEC Alignment Script (Advanced Phase):** Matches defendant names against the Central Election Commission (CEC) candidates and updates candidate affiliation flags.\n