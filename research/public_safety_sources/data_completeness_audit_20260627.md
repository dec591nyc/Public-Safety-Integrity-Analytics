# 台灣地方治安數據儀表板：資料完整度審計與實作計畫

Date: 2026-06-27

## 1. 結論摘要

專案應改名並重新定位為「台灣地方治安數據儀表板」。目前最能支撐產品核心的資料，不是裁判書或輿情，而是內政部統計查詢網的刑事案件月統計。

現有 SQLite 已有一條很強的官方統計基礎：

- `official_statistics`: 395,616 rows
- 月份範圍: `200001` 到 `202606`
- 月份數: 317
- 地理列: 24，包括 22 縣市、`機關別總計`、`署所屬機關`
- 案類指標: 52
- 每月資料點: 24 geographies x 52 metrics = 1,248
- 完整性: 目前 SQLite 中沒有缺列月份

但產品要對社會大眾有用，第一輪 refactor 必須先修資料可信度與產品語意：

1. `202606` 不應當成已發布真實 6 月資料。即時請求 `ym=11506` 時，官方端點仍回傳 `115年 (5~5月)`，代表 6 月尚未發布或系統回退到最新可用月份。
2. 本機 SQLite 的 `202605` 和 `202606` 目前仍是舊值，和 2026-06-27 即時官方端點回傳的 202605 不一致。ETL 需要重新抓取並驗證「請求月份」和「CSV 內部月份標籤」。
3. `judgments` 目前是每月 10 筆、`court_folder = MOCK` 的示範資料，不能作為地方治安趨勢或人口特徵結論。
4. `opinion_posts` 目前是 `generate_mock_opinions()` 產生的展示資料，不能當真實輿情。
5. `crime_categories` 只映射 32 個官方指標，官方共有 52 個指標；目前加權治安指數會漏掉未映射案類。

建議第一版產品主軸：

> 以官方月統計為核心，提供縣市別、案類別、時間序列、每十萬人口標準化、破獲率/嫌疑犯數擴充、資料品質註記、定期報告輸出。

裁判書、輿情、165 打詐儀表板、地方警政新聞，應先作為補充脈絡，不應放在第一版核心指標。

## 2. 現有資料資產審計

### 2.1 內政部刑事案件發生件數

Current source in code:

- Endpoint: `https://statis.moi.gov.tw/micst/webMain.aspx`
- Function id: `c0620101`
- Header observed: `刑事案件發生件數`
- Access: public CSV over HTTP query
- Existing script: `scripts/ingest_official_statistics.py`, `scripts/run_daily_update.py`
- Existing table: `official_statistics`

Live verification on 2026-06-27:

| Requested month | Official row label | Total | Fraud/breach of trust | SHA-256 note |
| --- | --- | ---: | ---: | --- |
| 202603 | `115年 (3~3月)/ 機關別總計` | 52,098 | 15,768 | distinct |
| 202604 | `115年 (4~4月)/ 機關別總計` | 51,381 | 15,126 | distinct |
| 202605 | `115年 (5~5月)/ 機關別總計` | 52,759 | 14,088 | distinct |
| 202606 | `115年 (5~5月)/ 機關別總計` | 52,759 | 14,088 | same as 202605 |

Audit judgment:

- Grade: A for historical monthly county-level crime counts.
- Current month handling: needs guardrail.
- Product fit: core dataset.
- Limitation: county/city only; no township, police precinct, point location, incident-level data, victim profile, or population denominator.

Required ETL fix:

- Store both `requested_month` and `observed_month`.
- Reject or quarantine rows when observed period does not match requested period.
- Add `source_url`, `fetched_at`, `sha256`, `source_header`, `source_first_label`.
- Do not publish current month unless official row label matches.

### 2.2 Other MOI crime-statistics function ids discovered

The same MOI statistical endpoint appears to expose compatible datasets:

| Function id | Observed header | Shape | Status |
| --- | --- | --- | --- |
| `c0620101` | `刑事案件發生件數` | 48 rows x 53 columns | already integrated |
| `c0620102` | `刑事案件破獲件數` | 48 rows x 53 columns | high-priority candidate |
| `c0620103` | `刑事案件嫌疑犯人數` | 48 rows x 53 columns | high-priority candidate |
| `c0620104` | timed out in this pass | unknown | retry later |
| `c0620105` | returned crime occurrence-like table | uncertain | verify before use |
| `c0620201` | `嫌疑犯人數` | annual/gender-like small table under current params | candidate, needs parameter profiling |
| `c0620301` | `刑案被害人數` | annual/victim-like small table under current params | candidate, needs parameter profiling |

Audit judgment:

- `c0620102` and `c0620103` should be the next expansion because they align with current table shape.
- `破獲件數` enables clearance-rate style indicators.
- `嫌疑犯人數` enables cases-to-suspects comparison, but must avoid demographic overclaim.
- `c0620201` and `c0620301` may support suspect/victim profile analysis later, but they need separate parameter discovery.

Recommended normalized model:

```text
fact_moi_crime_statistics
- dataset_family: moi_crime
- measure_type: occurrence | cleared | suspects | victims | unknown
- funid
- requested_month
- observed_month
- geography
- metric
- value
- value_status
- source_url
- source_header
- source_first_label
- sha256
- fetched_at
```

### 2.3 Crime category mapping

Existing table:

- `crime_categories`: 32 rows
- Official metrics: 52

Audit judgment:

- Grade: B.
- Good enough for a first `category group` layer, but not for a defensible public-facing safety index yet.
- Current `safety_index` is a custom weighted score and should be labeled as experimental or removed from public copy until all metrics are mapped and methodology is documented.

Required work:

- Map all 52 metrics.
- Separate three concepts:
  - official legal/statistical category
  - dashboard display group
  - custom severity/impact score
- Add `is_index_included` and `index_methodology_version`.

### 2.4 Judicial Yuan judgment data

Existing table:

- `judgments`: 3,180 rows
- Range: `200001` to `202606`
- Distribution: 10 rows per month in recent sample
- `court_folder`: only `MOCK`
- `judgment_texts`: 0 rows
- Demographic fields: all non-null, but values are synthetic/repeated.

Audit judgment:

- Grade: D for current production analytics.
- Fit: demo/search UX only.
- Not valid for demographic distribution, defendant profile, or local safety conclusions.

Recommended repositioning:

- Do not use current judgment rows in public dashboard metrics.
- Keep Judicial Yuan as a later case-context source:
  - selected official-source links
  - manually reviewed examples
  - case lookup
  - no broad demographic conclusions unless the crawler and validation are rebuilt.

### 2.5 Opinion/public discussion data

Existing table:

- `opinion_posts`: 1,585 rows
- Sources: PTT, Dcard, news media, legal/reform commentary
- Generation path: `generate_mock_opinions()`
- Pattern: roughly 5 posts per month, constructed from official statistics.

Audit judgment:

- Grade: D for real-world analysis.
- Fit: UI placeholder only.
- Risk: generated content may look like real posts and must be clearly labeled or removed from production static exports.

Required work:

- Rename current data to `demo_opinion_posts` or exclude from public static export.
- Real opinion ingestion must start with source policy checks, robots rules, and provenance.
- Prefer official press releases/RSS before forums.

## 3. External / Potential Sources

### 3.1 Core official sources

| Source | Data | Status | Grade | Product role |
| --- | --- | --- | --- | --- |
| MOI statistics `c0620101` | criminal case occurrence counts by month/county/category | integrated and live-verified | A | core trend data |
| MOI statistics `c0620102` | cleared/solved criminal case counts | live-discovered, same shape | A- | clearance-rate expansion |
| MOI statistics `c0620103` | suspect counts | live-discovered, same shape | A- | suspect/case comparison |
| MOI/RIS population statistics page | population denominator | official page verified, API not yet validated | B | per-100k rates |
| Judicial Yuan open judgment/search | case documents and links | repo has API spec/reference, current DB mock | C | selected case context |

Population source checked:

- `https://www.ris.gov.tw/app/portal/346` is the official RIS population statistics page.
- Guessed `rs-opendata` API calls returned `查無資料`, so the exact automated population endpoint still needs discovery.
- Population data is mandatory before comparing county safety levels.

### 3.2 Fraud-specific source

Source checked:

- `https://165dashboard.tw/`
- Page title: `內政部警政署 165打詐儀錶板`
- Page description says it includes scam-method top 5, monthly scam data, county/city scam data, latest scam cases, anti-fraud performance, and prevention content.
- Frontend JS exposes a base path `CIB_DWS_API/api/` and dashboard method names such as:
  - `GetDailyFraudMethodRanking`
  - `GetMonthlyCityFraudMethodRanking`
  - `GetMonthlyFraudMethodRanking`
  - `GetMonthlyCityPerformanceStatistics`
  - `GetMonthlyCityCaseStatistics`
  - `GetDailyCityFraudData`
  - `GetMonthlyVirtualCurrencyStatistics`

Audit judgment:

- Grade: B/C until API parameters, access policy, and terms are confirmed.
- Strong product value for fraud because MOI `詐欺背信` is now the largest category.
- Do not integrate as automated ETL until source policy and endpoint stability are checked.
- Safe first step: link out or manually cite high-level anti-fraud dashboard insights.

### 3.3 Traffic and road safety

Candidate:

- Road traffic accident statistics, especially A1/A2 accidents, casualties, drunk driving, pedestrian safety.

Audit judgment:

- Grade: C in this pass because a stable endpoint was not verified.
- Product value is high for "local public safety" but it should be treated as a second-source family, not mixed into crime metrics.
- Needs a separate source-discovery pass over MOTC/NPA open data.

### 3.4 Local police news and press releases

Candidate:

- National Police Agency news
- Criminal Investigation Bureau releases
- Local police department announcements/RSS

Audit judgment:

- Grade: C.
- Use as event timeline and source links, not as statistical evidence.
- Good for PWA and LineBot user-facing context:
  - "recent official alerts in this county"
  - "fraud prevention notices"
  - "local police press releases"

### 3.5 Deprioritized sources

| Source | Reason |
| --- | --- |
| PTT/Dcard forum crawling | source policy, representativeness, and moderation issues; not core for public safety MVP |
| broad defendant demographic extraction | high risk of privacy/ethics overclaim; current data is mock |
| CEC political matching | belongs to integrity-analysis scope, not the renamed local safety dashboard MVP |
| incident-level crime maps | no verified official open source in this pass; avoid implying precision |

## 4. Data Completeness Matrix

| Dimension | Current state | Completeness | Risk |
| --- | --- | --- | --- |
| Time coverage | 2000-01 to latest official available month | high | current-month fallback must be filtered |
| County/city coverage | 22 local governments plus aggregate rows | high | no township/precinct granularity |
| Crime category coverage | 52 official metrics | high | dashboard category mapping only covers 32 |
| Source traceability | partial URL/profiles exist | medium | SQLite lacks full source metadata |
| Population denominator | not integrated | low | cannot compare county rates responsibly |
| Clearance rate | not integrated, but `c0620102` found | medium | requires second measure type |
| Suspect count | not integrated, but `c0620103` found | medium | avoid demographic interpretation |
| Fraud methods/losses | 165 dashboard found | medium-low | API policy/parameters not confirmed |
| Judgment context | current DB is mock | low | should be removed from public claims |
| Opinion context | current DB is mock | low | should be removed or clearly labeled |
| Report/PPT/Power BI output | not formalized | low | depends on stable normalized facts |

## 5. Recommended Implementation Plan

### Phase 0: Data trust hardening

Goal: make the current official statistics trustworthy before adding features.

Tasks:

1. Add a source catalog for known and candidate data sources.
2. Refactor MOI ingestion to validate observed period from the first CSV dimension label.
3. Store `requested_month` and `observed_month`; quarantine mismatches.
4. Refresh `202605`; remove or mark `202606` as unpublished/pending until the official row label is June.
5. Add a data coverage audit command that reports:
   - months available
   - latest valid observed month
   - per-month row counts
   - duplicate SHA-256 anomalies
   - missing category mappings
6. Remove mock opinion and mock judgment data from public dashboard claims.

Exit criteria:

- Latest valid month is determined from source content, not request params.
- Dashboard copy no longer implies mock data is real.
- All generated static API files include a data quality/status section.

### Phase 1: Core official dashboard

Goal: build the first defensible public product.

Features:

- Product rename: `台灣地方治安數據儀表板`.
- County/city monthly trend for total cases.
- Case-category trend for 52 official metrics.
- MoM and YoY comparison.
- Top rising / falling categories.
- County ranking by raw count, clearly labeled as raw count.
- Data source badge and latest valid month.
- PWA shell after dashboard IA stabilizes.

Do not include:

- mock opinion
- mock judgment demographic charts
- "safety index" as a public claim
- current-month data when source label mismatches

### Phase 2: Population and rates

Goal: make cross-county comparisons fair.

Tasks:

1. Confirm automated RIS population endpoint or download workflow.
2. Create `fact_population_monthly`.
3. Normalize county names across MOI crime stats and population.
4. Add per-100k metrics:
   - total cases per 100k
   - fraud per 100k
   - violent-category per 100k after category mapping
5. Keep raw count and per-capita views side by side.

Exit criteria:

- Every county/month crime row can join to a population denominator.
- Ranking defaults to per-100k where appropriate, not raw count only.

### Phase 3: Measure expansion

Goal: use additional official crime measures.

Tasks:

1. Generalize MOI ingestion by `funid`.
2. Backfill:
   - `c0620101`: occurrence
   - `c0620102`: cleared
   - `c0620103`: suspects
3. Derive:
   - clearance rate = cleared / occurrence
   - suspects per case
   - category-specific clearance rate
4. Build a clear metric dictionary.

Exit criteria:

- Same dashboard can switch measure type without changing frontend data shape.
- Clearance rate is shown only when denominator is valid.

### Phase 4: Automation and delivery outputs

Goal: connect the technologies the project should demonstrate.

Recommended order:

1. ETL script hardening in Python.
2. n8n workflow to schedule monthly fetch after official release window.
3. Static API export for GitHub Pages/Vercel.
4. PWA dashboard for mobile use.
5. Monthly report generation:
   - Markdown
   - HTML
   - PDF later if needed
6. Power BI export:
   - star schema CSV/parquet
   - DAX measures for MoM, YoY, per-100k, clearance rate
7. LineBot:
   - county lookup
   - latest valid month summary
   - fraud trend query
8. PPT/video:
   - generated from monthly report, not manually reauthored.

### Phase 5: Fraud and event context

Goal: add socially useful context without corrupting statistical claims.

Tasks:

1. Validate 165 dashboard API policy and parameters.
2. If allowed, ingest aggregate fraud method/county/loss statistics.
3. Otherwise, show official link-out cards and manually verified summaries.
4. Add official police/news event timeline by source URL and county.
5. Keep event count separate from crime count.

Exit criteria:

- Every fraud/event item has provenance.
- No forum/social post is shown as official evidence.

## 6. Refactor Priorities

1. Rename product and README framing away from broad "judicial justice" and toward local safety official data.
2. Split data modules:
   - source fetchers
   - normalizers
   - validators
   - facts/aggregates
   - exports
   - frontend
3. Replace mock data surfaces with explicit demo labels or exclude them.
4. Add source metadata to every exported JSON payload.
5. Add automated coverage checks before any static export.
6. Rebuild dashboard IA around source confidence:
   - official statistics first
   - derived rates second
   - fraud/source context third
   - judgment/opinion later.

## 7. Next Concrete Work Items

Recommended next implementation slice:

1. Create source catalog file.
2. Add MOI source validator for `observed_month`.
3. Refresh official statistics for latest valid months.
4. Generate a coverage report JSON/Markdown.
5. Remove mock opinion/judgment charts from the default first screen.
6. Rename the visible product title.
7. Add population-source discovery as the next research task.

This sequence gives the project a defensible MVP before adding n8n, LineBot, Power BI, PPT, or crawler features.

