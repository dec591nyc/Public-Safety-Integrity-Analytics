# Development Plan

## Current State

The project now has two database access paths:

1. Local DB path
   - Driver: SQLite
   - File: `data/local/public_safety.sqlite`
   - Status: implemented and tested with the full `202604` judgment set.

2. Remote DB path
   - Target: PostgreSQL/Supabase-compatible schema
   - Schema: `sql/schema_postgres.sql`
   - Connection setting: environment variable `PUBLIC_SAFETY_DATABASE_URL`
   - Status: interface and schema implemented. Actual remote write requires either `psycopg` installed in Python or n8n's PostgreSQL/Supabase node.

The first full local indexing run completed:

- Files indexed: 100,427
- Errors: 0
- Local DB size: about 212.86 MB
- CSV export size: about 168.52 MB

## Why This Dataset Matters

The `202604` data is not only an aggregate statistics table. It is judgment-level data with:

- court and case identifiers
- judgment date
- case title
- full judgment text
- PDF reference URL

This supports deeper analysis than crime counts, including judgment basis, claims, party roles, awarded amounts, sentencing outcomes, and recurring court reasoning patterns.

## Analysis Tracks

### 1. Public Safety Monthly Dashboard

Purpose: show monthly volume and distribution.

Core metrics:

- total judgments by month
- case-domain distribution: civil, criminal, administrative, constitutional, disciplinary
- category candidate counts: fraud, money laundering, sexual offense, injury, public integrity, election law
- court/bench distribution
- top case titles and case codes

Important caveat: these are court-document counts, not police incident counts.

### 2. Judgment-Basis Extraction

Purpose: understand why courts reach specific outcomes.

Fields to extract:

- court
- judge name if detectable
- plaintiff/applicant/prosecutor role
- defendant/respondent role
- legal basis and cited statutes
- claim amount
- awarded amount
- sentence or disposition
- evidence types
- reasoning summary
- appeal availability

Implementation approach:

1. Start with deterministic regex/rules for common sections such as `主文`, `事實及理由`, `理由`, `據上論結`.
2. Add lightweight NLP/LLM extraction only after rule output is stored and auditable.
3. Store extracted facts separately from raw judgment text so every derived claim can point back to `JID` and `JPDF`.

### 3. Fairness and Consistency Signals

Purpose: detect patterns worth human review, not automatically declare unfairness.

Candidate indicators:

- similar case facts with materially different outcomes
- unusually high or low damages compared with peers
- repeated reduction patterns in claims vs awarded amount
- same charge/statute but divergent sentence ranges
- court or judge-level outliers after controlling for case type
- default judgment patterns in fraud-related civil cases

Guardrail: dashboard wording should use `review signal`, `outlier`, and `requires manual verification`, not direct accusations.

### 4. Political/Official Integrity Analysis

Purpose: connect public-office or party context only when evidence is traceable.

Required reference tables:

- CEC candidates/elected persons
- party names and aliases
- public office rosters where available
- court judgment entity mentions

Matching levels:

- Level 0: keyword mention only
- Level 1: name match to candidate/official reference table
- Level 2: name + office/party/context match
- Level 3: manually reviewed and evidence-linked

Only Level 3 should be used for public-facing claims.

### 5. Automation With n8n

Recommended n8n flow:

1. Cron trigger
2. Download or watch monthly Judicial Yuan archive
3. Extract RAR/ZIP to `data/raw/YYYYMM`
4. Run `scripts/build_judgment_index.py`
5. Upsert local SQLite or remote PostgreSQL/Supabase
6. Run extraction/classification jobs
7. Generate dashboard refresh signal
8. Send notification with counts and errors

n8n should orchestrate. Heavy parsing should stay in Python scripts.

## Environment Modes

Use explicit modes so the same project can run locally or in production:

- `LOCAL_DEV`: SQLite only, fast iteration, no remote writes
- `REMOTE_STAGING`: SQLite plus PostgreSQL/Supabase write, test dashboard
- `PRODUCTION`: scheduled ingest, remote DB primary, local DB optional backup

Suggested environment variables:

```text
PUBLIC_SAFETY_ENV=LOCAL_DEV
PUBLIC_SAFETY_DATABASE_URL=postgresql://...
PUBLIC_SAFETY_RAW_ROOT=C:/path/to/data/raw
PUBLIC_SAFETY_LOCAL_DB=data/local/public_safety.sqlite
```

## Next Build Steps

1. Add `query_judgment_index.py` for common dashboard queries.
2. Add extraction table for parties, statutes, claim amounts, awarded amounts, and sentencing outcomes.
3. Add a first dashboard prototype reading from SQLite.
4. Add n8n workflow documentation and command-node examples.
5. Add remote DB installation notes once the actual PostgreSQL/Supabase target is chosen.
