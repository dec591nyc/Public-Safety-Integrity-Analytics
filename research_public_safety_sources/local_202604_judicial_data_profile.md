# Local 202604 Judicial Data Profile

Source path:

`C:\Users\zifue\Documents\AgenticAI\CodexPlayground\Public-Safety-Integrity-Analytics\data\202604`

## What This Data Is

The local `202604` folder contains Judicial Yuan court judgment JSON files, organized by court/bench and case type. This is different from aggregate police statistics: it is case-document data with judgment text and PDF links.

## Observed Scale

- Top-level court/bench folders: 133
- JSON files: 100,427
- Total JSON size: about 598.34 MB
- Filename date range: 2026-04-01 to 2026-04-30

## Folder-Type Counts

- Civil folders: 60,605 JSON files
- Criminal folders: 35,740 JSON files
- Administrative folders: 3,709 JSON files
- Constitutional folders: 160 JSON files
- Disciplinary folders: 17 JSON files
- Other folders: 196 JSON files

## JSON Schema

Observed fields:

- `JID`: judgment identifier, also reflected in filename
- `JYEAR`: ROC case year
- `JCASE`: case category/code
- `JNO`: case number
- `JDATE`: judgment date in `YYYYMMDD`
- `JTITLE`: case title/cause
- `JFULL`: full judgment text
- `JPDF`: PDF download URL

Example:

```json
{
  "JID": "SJEM,115,重秩,25,20260415,1",
  "JYEAR": "115",
  "JCASE": "重秩",
  "JNO": "25",
  "JDATE": "20260415",
  "JTITLE": "違反社會秩序維護法",
  "JPDF": "https://data.judicial.gov.tw/opendl/JDocFile/SJEM/115%2c%e9%87%8d%e7%a7%a9%2c25%2c20260415%2c1.pdf"
}
```

## Initial Keyword Candidate Counts

These are full-text keyword hit counts, not final statistical counts. One judgment can match multiple categories, and civil damages cases often reference related criminal cases.

- Fraud/scam keywords (`詐欺`, `詐騙`): 14,972 files
- Money laundering (`洗錢`): 10,344 files
- Injury/serious injury keywords (`傷害`, `重傷`): 8,668 files
- Sexual offense keywords (`妨害性自主`, `性侵`): 711 files
- Public integrity/election keywords (`貪污`, `瀆職`, `選罷法`, `公職人員選舉罷免法`): 226 files

## Automation Implications

This local dataset should be treated as a raw landing zone. Do not repeatedly scan all JSON files in n8n on every run. Instead:

1. Build a metadata index from filename and JSON fields.
2. Store one row per judgment in DuckDB/PostgreSQL/Supabase.
3. Store category flags from keyword/NLP classification.
4. Keep `JFULL` in a full-text-search table or document store.
5. Use `JPDF` only as a reference link, not as the primary parsed source.

## Suggested Entity-Resolution Layer

For the political-party/government-official analysis, match judgment text against:

- CEC candidate/elected-person lists
- Legislator/councilor/local-official rosters
- Political party names and aliases
- Court text cues such as `被告`, `公務員`, `議員`, `里長`, `鄉長`, `市長`, `立法委員`, `貪污治罪條例`, `選罷法`

Manual review is still needed for high-stakes public accusations because name collisions are common and court text may mention a person without finding them liable.
