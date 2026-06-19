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
  category_flags TEXT NOT NULL DEFAULT '{}',
  matched_keywords TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_judgments_source_month ON judgments(source_month);
CREATE INDEX IF NOT EXISTS idx_judgments_jdate ON judgments(jdate);
CREATE INDEX IF NOT EXISTS idx_judgments_jtitle ON judgments(jtitle);
CREATE INDEX IF NOT EXISTS idx_judgments_court_folder ON judgments(court_folder);
CREATE INDEX IF NOT EXISTS idx_judgments_case_domain ON judgments(case_domain);

CREATE TABLE IF NOT EXISTS judgment_texts (
  jid TEXT PRIMARY KEY,
  jfull TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (jid) REFERENCES judgments(jid) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY,
  source_month TEXT NOT NULL,
  source_dir TEXT NOT NULL,
  local_db_path TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  files_seen INTEGER NOT NULL DEFAULT 0,
  files_indexed INTEGER NOT NULL DEFAULT 0,
  errors INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL
);
