# Development Plan

## Product Scope Decision - 2026-06-23

The project is a lightweight, dynamic scraping and demographic statistics dashboard. It focuses on targeted web scraping of recent judicial judgments and public opinions rather than archiving massive offline bulk datasets.

### Primary Objectives:

1. **Lightweight Targeted Ingestion:** Scraping recent Judicial Yuan judgments and extracting case metadata instead of downloading large monthly RAR archives.
2. **Core Public Demographics:** Structuring and displaying demographic statistics extracted from judgment text headers, including:
   - **Age (年齡)**
   - **Gender (性別)**
   - **Income (收入/財產狀況)**
   - **Birth-City (出生地/戶籍地)**
   - **Occupation (職業)**
   - **Education-Level (教育程度)**
3. **Opinion Comparison:** Tracking forum, news, and civic commentary discussions to compare judicial outputs against public attention trends.
4. **Phased CEC Integration (Advanced Phase):** Mapping case defendants with political candidacy listings in the Central Election Commission (CEC) database to identify party backgrounds and political contexts of integrity-related cases (e.g., corruption, bribery).

---

## Current Architecture

The codebase contains local/remote database pathways and automated scraping pipelines:

1. **Local SQLite Database:**
   - Database File: `data/local/public_safety.sqlite`
   - Purpose: Stores scraped judgment metadata, parsed demographics, and crawled opinion metrics. Keeps data storage under 50 MB for quick local runs.
2. **Remote PostgreSQL / Supabase:**
   - Schema: `sql/schema_postgres.sql`
   - Purpose: Houses structured dashboard metrics and opinion feeds for the deployed SPA.
3. **Ingestion Pipelines:**
   - `scripts/run_daily_update.py`: Triggered daily to run lightweight scrapers and write data to the DB.
   - `scripts/scrape_judicial_data.py` (Planned): Extracts recent court judgments, parses demographic variables using regex/rules, and commits to SQLite.

---

## Phased Development Timeline

### Phase 1: Dynamic Scraper & Demographic Parsing
- Implement `scrape_judicial_data.py` to query the Judicial Yuan public search system (`https://judgment.judicial.gov.tw/`) for new daily rulings.
- Create rule-based text parsers to identify Age, Gender, Income, Birth-City, Occupation, and Education-Level from judgment texts.
- Write unit tests using mock judgment texts to validate parsing accuracy.

### Phase 2: Lightweight Database Schema & Daily Ingestion
- Update `sql/schema_sqlite.sql` and `sql/schema_postgres.sql` to include columns for the six demographic attributes.
- Refactor `run_daily_update.py` to orchestrate both the Judicial Yuan scraper and opinion crawlers on a daily cron schedule.
- Ensure automated database writes are idempotent (handling duplicates via `ON CONFLICT` updates).

### Phase 3: Demographic Visualization Dashboard
- Redesign the front-end SPA dashboard to display public demographic charts (e.g., age distribution bar chart, occupation pie chart, gender breakdown, and education level tables).
- Implement interactive filters allowing users to view demographics by case category (e.g., fraud, violent crimes) and region.
- Retain opinion attention gap metrics to contrast public concerns with actual court metrics.

### Phase 4 (Advanced Feature): Political Background Tracking
- Sync Central Election Commission (CEC) candidate and elected-official tables into the database.
- Develop a name-matching service that matches defendants in political crime cases (corruption, bribery, election-law) with CEC candidates.
- Add a political background analysis section to the front-end dashboard, displaying case volumes and summaries categorized by party affiliations.

---

## Environment Modes

Use environment variables to control project environments:

- `LOCAL_DEV`: SQLite only, fast scraping tests, low-cost local iteration.
- `PRODUCTION`: Automated daily cron, writes to remote Supabase database, SPA deployed to static hosting (Vercel/GitHub Pages).

```text
PUBLIC_SAFETY_ENV=LOCAL_DEV
PUBLIC_SAFETY_DATABASE_URL=postgresql://...
PUBLIC_SAFETY_LOCAL_DB=data/local/public_safety.sqlite
```\n