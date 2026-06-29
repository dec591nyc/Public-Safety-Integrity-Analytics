# Dashboard Information Architecture

## Navigation Order

1. `總覽儀表板`
2. `輿論情報`
3. `輿情真相`
4. `裁判資料庫`

`輿情真相` compares court data, public discussion, and manually reviewed facts while keeping source status visible.

## Chart Allocation

### Overview

- KPI cards: total judgments and selected topic counts.
- Line chart: monthly judgment volume trend. A time axis is required, so a line chart is the primary form.
- Donut chart: category composition. It is limited to seven stable categories and includes a numeric legend.
- Horizontal bars: court ranking. Bars support precise comparison better than a pie chart.
- Table: case-title ranking. Text-heavy labels need a table, not chart labels.

### Public Opinion

- Time switcher: month and date range are first-class filters.
- Line chart: discussion volume over time after crawlers are connected.
- Stacked bars: forum/source mix by topic after data exists.
- Summary list: monthly topic summaries with source links and crawl status.
- Empty states must never fabricate discussion counts.

### Public Opinion Truth

- KPI cards: source coverage, linked judgment rate, reviewed sample count, and signal status.
- Comparison table: court volume versus discussion volume versus review status.
- Scatter/bubble chart later: discussion volume against judicial-data outlier score.
- System summary: neutral wording with method and evidence status.

### Judgment Database

- Search and table/list are primary. Charts are secondary because the user task is retrieval and review.
- Global fields: month, case title, court, plaintiff, and defendant.
- Record-level extractive summary, evidence excerpt, category tags, and PDF source link.
- Plaintiff/defendant matching is explicitly marked as excerpt-level preliminary search until fact extraction is complete.

## AI Summary Policy

- Current provider: `extractive_rule_v1`.
- Optional local provider: Ollama.
- Deferred production provider: OpenAI API.
- The UI must display provider, confidence, and review requirement.
