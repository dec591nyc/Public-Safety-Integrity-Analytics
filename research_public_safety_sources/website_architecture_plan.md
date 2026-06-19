# Website Architecture and Roadmap

## Current Implementation

### Language

- Backend: Python 3 standard library
- Frontend: HTML, CSS, vanilla JavaScript
- Local database: SQLite
- Remote database target: PostgreSQL or Supabase-compatible schema

### Current Backend

`/.scripts/serve_review_dashboard.py` runs a read-only local HTTP server.

Responsibilities:

- Serve static SPA files from `web/`
- Read `data/local/public_safety.sqlite` in read-only mode
- Provide JSON APIs:
  - `/api/summary`
  - `/api/judgments`
  - `/api/judgments/{jid}`

Why this stack now:

- No Node/npm dependency required
- Fast to run locally
- Works with the existing SQLite index
- Good enough for review before building extraction logic

### Current Frontend

The frontend is a lightweight SPA with four routes:

1. `#overview` - 總覽儀表板
2. `#opinion` - 輿論情報
3. `#cross-observation` - 交叉觀測
4. `#database` - 裁判資料庫

Design direction:

- Traditional Chinese interface
- Data-dense dashboard style
- Neutral professional palette
- Clear separation between indexed court data, public-opinion planning, and verified findings

## Planned Upgrade Options

### Option A: Keep Lightweight Stack

Best for early research and local review.

- Python HTTP server
- SQLite
- Vanilla JS SPA
- Minimal dependencies

Use this until the information architecture and data model stabilize.

### Option B: Production Web App

Recommended after fact extraction is validated.

- Backend: FastAPI or Flask
- Database: PostgreSQL or Supabase
- Frontend: React, Vue, or SvelteKit
- Search: PostgreSQL full text, Meilisearch, or OpenSearch
- Automation: n8n scheduled ingest and extraction jobs

### Option C: Analytics BI Stack

Recommended if the priority is internal dashboarding.

- DuckDB or PostgreSQL
- Evidence tables and feature tables
- Metabase, Superset, or Streamlit
- n8n for monthly data ingestion

## Public Opinion Intelligence Plan

The public opinion layer should be separate from court data. It should not be mixed into judgment facts until the source and classification are clear.

### Source Types

- Forums: PTT, Dcard
- News: Taiwanese legal/social news coverage
- Civic/legal organizations: judicial reform and legal commentary sources
- Official correction sources: Judicial Yuan releases, ministry responses, court press releases

### Ingestion Fields

- source_name
- source_url
- published_at
- title
- author_or_board if public and permitted
- topic_category
- sentiment or stance label
- summary
- referenced_judgment_id if detected
- confidence
- crawl_run_id

### Categories

- fraud_money_laundering
- traffic_injury_compensation
- sexual_offense_sentencing
- public_integrity_corruption
- election_law_dispute
- constitutional_or_high_profile_dispute
- general_judicial_trust

### Guardrails

- Respect platform terms and robots rules.
- Store links and short summaries, not unnecessary personal data.
- Treat public opinion as perception data, not proof of unfair judgment.
- Use manual review for high-impact claims.

## Cross Observation Dashboard Concept

The cross-observation layer compares three things without treating public opinion as proof:

1. Court data signals
2. Public opinion signals
3. Manually verified extraction results

Useful outputs:

- High court-data volume, low public attention
- Low court-data volume, high public attention
- Similar cases with divergent outcomes
- Cases with strong public controversy but weak evidence linkage
- Cases where public concern and court-data outliers align

## Next Technical Step

Build `extract_judgment_facts.py` after UI review.

Initial extraction table:

- jid
- plaintiff_text
- defendant_text
- main_text
- legal_basis_text
- claim_amount
- awarded_amount
- sentence_text
- result_label
- extraction_method
- extraction_confidence
- needs_manual_review

This second table is required before the dashboard can make stronger claims about judgment patterns or fairness signals.

## Summary Provider Decision

- Local development default: deterministic extractive summary with evidence snippets.
- Optional local generation: Ollama, after model and hardware evaluation.
- Advanced local deployment: llama.cpp server.
- Browser inference: Transformers.js only for lightweight experiments, not the default legal summarizer.
- Production option: OpenAI API is recorded but deferred. No API key is required in the current version.
