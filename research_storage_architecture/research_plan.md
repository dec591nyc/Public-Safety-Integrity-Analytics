# Dynamic Judgment Storage Architecture Research Plan

## Main Question

How should the project structure local and cloud storage tiers to support a lightweight, dynamic scraping and daily concise updates strategy while remaining within free hosting limits (e.g. Supabase Free Plan)?

## Key Subtopics

### 1. Daily Ingestion Storage Growth Estimation
- Expected: Model database growth based on daily scraping frequency and targeted crime categories (calculating storage sizes for metadata and demographic fields per ruling).

### 2. Transient Parsing Storage Requirements
- Expected: Define temporary directory requirements for holding scraped raw HTML or JSON responses during the parsing phase. Confirm automatic cleanup routines to prevent local storage creep.

### 3. PostgreSQL & Supabase Free Tier Optimization
- Expected: Verify database connection pools and indexes to ensure daily metrics and opinion tables stay within the 500 MB database quota, avoiding heavy indexing and redundant logs.

### 4. Backup and Recovery Model
- Expected: Determine a lightweight database dump strategy (e.g. daily automated sqlite database backups or git-tracked database exports) to ensure easy recovery without storing full-text archives.

## Expected Output

- Structured estimation of DB size growth.
- Ingestion guidelines confirming immediate raw text cleanup.
- Recommended indexing and schema optimizations to ensure free cloud hosting compatibility.\n