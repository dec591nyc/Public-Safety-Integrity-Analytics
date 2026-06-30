-- PostgreSQL Schema for Supabase Integration

CREATE TABLE IF NOT EXISTS crime_categories (
  metric TEXT PRIMARY KEY,
  iccs_code TEXT NOT NULL,
  iccs_name TEXT NOT NULL,
  severity_score INTEGER NOT NULL,
  flag_cyber INTEGER NOT NULL DEFAULT 0,
  flag_weapon INTEGER NOT NULL DEFAULT 0,
  flag_domestic INTEGER NOT NULL DEFAULT 0,
  flag_organized_fraud INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS official_statistics (
  source_month TEXT NOT NULL,
  geography TEXT NOT NULL,
  metric TEXT NOT NULL,
  raw_value INTEGER NOT NULL,
  value_status TEXT NOT NULL,
  PRIMARY KEY (source_month, geography, metric)
);

CREATE INDEX IF NOT EXISTS idx_official_statistics_lookup ON official_statistics(source_month, geography);

CREATE TABLE IF NOT EXISTS official_metric_styles (
  metric TEXT PRIMARY KEY,
  color TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_total INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS opinion_posts (
  post_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  author TEXT,
  title TEXT NOT NULL,
  content TEXT,
  url TEXT,
  publish_date TEXT NOT NULL,
  category TEXT,
  sentiment REAL DEFAULT 0.0,
  matched_keywords JSONB DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_opinion_posts_filter ON opinion_posts(publish_date, source, category);

CREATE TABLE IF NOT EXISTS crime_summary_reports (
  report_key TEXT PRIMARY KEY,       -- 'YYYYMM' or 'YYYY_annual' (e.g. '202604', '2026_annual')
  report_type TEXT NOT NULL,         -- 'monthly' or 'annual'
  source_year INTEGER NOT NULL,      -- YYYY (e.g. 2026)
  source_month INTEGER,              -- MM (e.g. 4, NULL for annual reports)
  source_url TEXT,
  dataset_id TEXT,
  total_cases INTEGER NOT NULL,
  total_change_pct REAL,
  safety_index INTEGER NOT NULL,
  category_counts JSONB NOT NULL,
  iccs_breakdown JSONB NOT NULL,
  flags_summary JSONB NOT NULL,
  topic_drilldowns JSONB NOT NULL,
  region_weighted_counts JSONB NOT NULL,
  region_counts JSONB NOT NULL,
  quality JSONB NOT NULL,
  summary JSONB NOT NULL,            -- { "text": "...", "method": "..." }
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);



