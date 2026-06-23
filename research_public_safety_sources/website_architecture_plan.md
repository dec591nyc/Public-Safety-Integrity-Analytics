# Website Architecture and Roadmap

## Product Direction - 2026-06-23

The website is a dynamic statistics dashboard displaying judicial demographic distributions, public opinion trends, and (advanced phase) political case backgrounds. It is designed to be lightweight, querying only recent case data and discarding raw files after indexing.

### Primary Dashboard Views:

1. **Demographic Insights View (大眾量化統計)**:
   - Displays distribution charts for key defendant demographic variables extracted from recent judgments:
     - **Age Groups (年齡分布):** E.g., under 20, 20-30, 30-40, etc.
     - **Gender (性別比例):** Male vs. Female.
     - **Occupational Sectors (職業分布):** Categorized by industry (e.g., labor, hospitality, public official, student, unemployed).
     - **Educational Attainment (教育程度):** Breakdown of high school, university, etc.
     - **Geographic and Socioeconomic Contexts (出生地與財產狀況):** Region charts and statistical income/property references.
2. **Public Opinion Feed View (輿情聲量)**:
   - Displays social media discussion volume, sentiment tags, and hot topics classified by crime category.
3. **Divergence Analysis Matrix (關注度落差)**:
   - Compares the volume of specific crime categories in courts (e.g., fraud vs. violent crime) with public discussion frequency to expose gaps in attention.
4. **Political Integrity Board (進階政商背景 - 未來特色)**:
   - Tracks case volumes and listings cross-referenced with political party affiliations (via Central Election Commission candidate match).

---

## Technical Stack

- **Frontend:** Vanilla HTML, CSS, and JavaScript. Simple Single Page Application (SPA) architecture with responsive CSS grid layout.
- **Backend:** Python 3 standard library. Performs daily routine web scraping and handles JSON serialization.
- **Database:**
  - SQLite (`data/local/public_safety.sqlite`): Used for local development and testing.
  - PostgreSQL / Supabase: Secondary cloud database for production, storing normalized aggregates and metrics.
- **n8n Orchestration (Optional):** Schedules daily scrape jobs and triggers front-end cache flushes.

---

## Proposed Database Schemas

### Table: `judgments`

Stores structured attributes extracted from each scraped court judgment:

| Field Name | Data Type | Description |
| --- | --- | --- |
| `jid` | VARCHAR(100) | Unique judgment identifier |
| `jdate` | DATE | Date of the ruling |
| `jcase` | VARCHAR(50) | Case code/category |
| `jtitle` | VARCHAR(255) | Case title/cause |
| `court_name`| VARCHAR(100) | Court/Bench name |
| `age` | INT | Extracted age of the defendant |
| `gender` | VARCHAR(10) | Extracted gender (Male/Female) |
| `occupation` | VARCHAR(100) | Extracted occupation |
| `education` | VARCHAR(100) | Extracted education level |
| `income_level`| VARCHAR(100) | Extracted financial/income description |
| `birth_city` | VARCHAR(100) | Extracted birthplace or address city |
| `party_code` | INT | (Advanced) CEC party code match |
| `candidacy` | VARCHAR(100) | (Advanced) CEC candidacy details |

### Table: `opinion_metrics`

Stores public opinion indicators parsed daily:

| Field Name | Data Type | Description |
| --- | --- | --- |
| `opinion_id` | VARCHAR(100) | Unique post/news identifier |
| `source` | VARCHAR(50) | Platform name (PTT, Dcard, News) |
| `publish_date`| DATE | Publication date |
| `category` | VARCHAR(50) | Topic classification (fraud, corruption, etc.) |
| `sentiment` | FLOAT | Sentiment score (-1.0 to +1.0) |
| `post_url` | VARCHAR(255) | Source link |

---

## Data Retention and Transient Processing

To ensure compliance, minimize storage costs, and run smoothly under free hosting quotas:
1. **Raw Text Disposal:** Raw scraped HTML and judgment text are treated as transient. Once demographics (age, gender, etc.) are extracted and stored in the database, the full judgment text is discarded.
2. **Audit Excerpts Only:** Only short, legally compliant snippets of the judgment or opinion post are retained for verification.
3. **No Heavy PDF storage:** PDF links are stored as external references, and files are never downloaded in bulk.\n