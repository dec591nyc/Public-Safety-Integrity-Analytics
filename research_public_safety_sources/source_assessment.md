# Public Safety Integrity Data Source Assessment

Date: 2026-06-19

## Summary

Official open-data sources are preferable to page scraping for the first version. Crime statistics and election/party data can be acquired without accounts or API keys. Court judgment bulk data is available as monthly RAR files on the Judicial Yuan open-data platform, but the judgment datasets are marked as member-limited and should be treated as requiring an account/session workflow.

## Tested Sources

### 1. Ministry of the Interior / National Police Crime Statistics

- Source: Government Data Open Platform dataset `9603`, "受(處)理刑事案件發生件數-按機關別分"
- Detail API: `https://data.gov.tw/api/front/dataset/detail?nid=9603`
- Data URL: `https://statis.moi.gov.tw/micst/webMain.aspx?...funid=c0620101...ym=11101&ymt=11112`
- Access: no account, no API key observed
- Format: UTF-8 CSV
- Useful columns: total, theft, injury, fraud/breach of trust, offenses against sexual autonomy, corruption, malfeasance, election/recall-law violation, and other criminal categories
- Automation fit: high. n8n can call HTTP Request and parse CSV directly.

Sample row fetched:

```csv
"刑事案件發生件數","總計","竊盜","贓物","賭博","傷害","詐欺背信","妨害自由","殺人","駕駛過失","妨害家庭及婚姻","妨害風化","妨害性自主罪",...
"111年/ 機關別總計",265518,37670,67,3135,13972,30876,14438,254,21172,349,849,4520,...
```

### 2. Police Thematic PDF Reports

- Example source: Government Data Open Platform dataset `176659`, "114年第2季傷害案件"
- File URL: `https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/5541BB10-EBEE-40F4-A647-61599BEA0A9B/resource/B85219A3-DC0C-4407-86D6-6898BAD7B6AE/download`
- Access: no account observed
- Format: PDF
- Automation fit: medium. Useful for reports and narrative context, but less ideal than CSV for dashboards.

### 3. Judicial Yuan Court Judgments

- Platform: `https://opendata.judicial.gov.tw/`
- Dataset search API: `https://opendata.judicial.gov.tw/api/Datasets?keyword=裁判書&page=1&pageSize=10`
- File download pattern: `https://opendata.judicial.gov.tw/api/FilesetLists/{fileSetId}/file`
- Access: judgment bulk datasets are marked `categoryDataset = B`; frontend hides file links unless logged in. A no-session GET test on a judgment RAR file returned HTTP 500 JSON.
- Format: monthly RAR files; fields shown by API include `ID`, `JYEAR`, `JCASE`, `JNO`, `JDATE`, `JTITLE`, `JFULL`, `JPDF`.
- Automation fit: medium if account/session handling is acceptable; low if no login is allowed.

### 4. Central Election Commission Election Database

- Platform: `https://db.cec.gov.tw/ElecTable`
- Static list example: `https://db.cec.gov.tw/static/elections/list/ELC_L0.json`
- Party distribution example: `https://db.cec.gov.tw/static/elections/data/summaries/L0/e06c04a91fcb0bb3f9a563fe93395ad5.json`
- Access: no account, no API key observed
- Format: static JSON
- Automation fit: high. Good source for party/candidate/elected-office enrichment.

Sample JSON fetched:

```json
[
  {"party_code":16,"party_name":"民主進步黨","distribution_num":36},
  {"party_code":1,"party_name":"中國國民黨","distribution_num":36},
  {"party_code":999,"party_name":"無黨籍及未經政黨推薦","distribution_num":1}
]
```

## Scraping vs Open Data

Use official open-data endpoints first. They are more stable, structured, and easier to schedule in n8n. Browser scraping should be reserved for gaps such as individual news events, prosecutor press releases, or judicial search pages when bulk court data access is unavailable.

## Recommended n8n Flow

1. Cron Trigger
2. HTTP Request: fetch crime CSV from MOI statistics endpoint
3. Spreadsheet File or Code node: parse UTF-8 CSV
4. Normalize categories: `詐欺背信`, `妨害性自主罪`, `傷害`, `貪污`, `瀆職`, `違反選罷法`
5. HTTP Request: fetch CEC JSON party/candidate reference data
6. Optional HTTP Request: Judicial Yuan dataset list and file download
7. If Judicial Yuan RAR is used: binary download -> external unzip/unrar step -> parse CSV/XML/JSON payload
8. Store in PostgreSQL/Supabase or local DuckDB
9. Dashboard/API refresh

## Key Limitation

Official crime statistics are aggregate counts, not individual offender identities. Analysis of "officials or party members involved in fraud/illegal conduct" requires a separate entity-resolution layer using court judgments, prosecutor press releases, Control Yuan records, election candidate lists, and possibly manual review. This should be presented as evidence-linked case analysis, not as a simple official aggregate statistic.
