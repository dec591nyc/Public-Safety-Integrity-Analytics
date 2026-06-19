CREATE TABLE IF NOT EXISTS judgments (
  jid TEXT PRIMARY KEY,
  source_month TEXT NOT NULL,
  court_folder TEXT NOT NULL,
  case_domain TEXT NOT NULL,
  file_path TEXT NOT NULL,
  jyear TEXT,
  jcase TEXT,
  jno TEXT,
  jdate DATE,
  jtitle TEXT,
  jpdf TEXT,
  text_length INTEGER NOT NULL DEFAULT 0,
  excerpt TEXT,
  category_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
  matched_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_judgments_source_month ON judgments(source_month);
CREATE INDEX IF NOT EXISTS idx_judgments_jdate ON judgments(jdate);
CREATE INDEX IF NOT EXISTS idx_judgments_jtitle ON judgments(jtitle);
CREATE INDEX IF NOT EXISTS idx_judgments_court_folder ON judgments(court_folder);
CREATE INDEX IF NOT EXISTS idx_judgments_case_domain ON judgments(case_domain);
CREATE INDEX IF NOT EXISTS idx_judgments_category_flags ON judgments USING GIN(category_flags);

CREATE TABLE IF NOT EXISTS judgment_texts (
  jid TEXT PRIMARY KEY REFERENCES judgments(jid) ON DELETE CASCADE,
  jfull TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY,
  source_month TEXT NOT NULL,
  source_dir TEXT NOT NULL,
  local_db_path TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  files_seen INTEGER NOT NULL DEFAULT 0,
  files_indexed INTEGER NOT NULL DEFAULT 0,
  errors INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL
);
