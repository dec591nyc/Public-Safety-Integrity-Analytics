-- PostgreSQL Schema for Supabase Integration

CREATE TABLE IF NOT EXISTS judgments (
  jid TEXT PRIMARY KEY,
  source_month TEXT NOT NULL,
  court_folder TEXT NOT NULL,
  case_domain TEXT NOT NULL,
  file_path TEXT NOT NULL,
  jyear TEXT,
  jcase TEXT,
  jno TEXT,
  jdate TEXT,
  jtitle TEXT,
  jpdf TEXT,
  text_length INTEGER NOT NULL DEFAULT 0,
  excerpt TEXT,
  category_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
  matched_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_judgments_source_month ON judgments(source_month);
CREATE INDEX IF NOT EXISTS idx_judgments_jdate ON judgments(jdate);
CREATE INDEX IF NOT EXISTS idx_judgments_jtitle ON judgments(jtitle);

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
