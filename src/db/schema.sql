-- LLM SEO Agent System - SQLite schema

-- Prompts we query LLMs with (generated or loaded from config)
CREATE TABLE IF NOT EXISTS prompts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL,
  niche TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(text)
);

-- Each monitoring run (one per model per execution)
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model TEXT NOT NULL,
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMP,
  prompt_count INTEGER DEFAULT 0,
  status TEXT DEFAULT 'running'
);

-- Raw citation records: which prompt, which run, which domain was cited (own or other)
CREATE TABLE IF NOT EXISTS citations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  prompt_id INTEGER NOT NULL,
  model TEXT NOT NULL,
  cited_domain TEXT NOT NULL,
  raw_snippet TEXT,
  is_own_domain INTEGER DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (run_id) REFERENCES runs(id),
  FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);

-- Content briefs (Sprint 2)
CREATE TABLE IF NOT EXISTS content_briefs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt_id INTEGER,
  topic TEXT NOT NULL,
  angle TEXT,
  priority_score REAL,
  suggested_headings TEXT,
  entities_to_mention TEXT,
  schema_to_add TEXT,
  image_prompts TEXT,
  image_urls TEXT,
  status TEXT DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);

-- Drafts (Sprint 3)
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  brief_id INTEGER,
  title TEXT NOT NULL,
  slug TEXT,
  body_md TEXT,
  body_html TEXT,
  schema_json TEXT,
  status TEXT DEFAULT 'draft',
  published_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  published_url TEXT,
  verification_status TEXT,
  verified_at TIMESTAMP,
  FOREIGN KEY (brief_id) REFERENCES content_briefs(id)
);

-- Citation uplift tracking (Sprint 4): before/after per article
CREATE TABLE IF NOT EXISTS citation_uplift (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  draft_id INTEGER,
  run_id_before INTEGER,
  run_id_after INTEGER,
  citation_rate_before REAL,
  citation_rate_after REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (draft_id) REFERENCES drafts(id),
  FOREIGN KEY (run_id_before) REFERENCES runs(id),
  FOREIGN KEY (run_id_after) REFERENCES runs(id)
);

-- Per-(run, prompt) visibility: brand mention in text, competitor-only, etc.
CREATE TABLE IF NOT EXISTS run_prompt_visibility (
  run_id INTEGER NOT NULL,
  prompt_id INTEGER NOT NULL,
  had_own_citation INTEGER DEFAULT 0,
  brand_mentioned INTEGER DEFAULT 0,
  competitor_only INTEGER DEFAULT 0,
  PRIMARY KEY (run_id, prompt_id),
  FOREIGN KEY (run_id) REFERENCES runs(id),
  FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);

CREATE INDEX IF NOT EXISTS idx_citations_run_id ON citations(run_id);
CREATE INDEX IF NOT EXISTS idx_citations_prompt_id ON citations(prompt_id);
CREATE INDEX IF NOT EXISTS idx_citations_model ON citations(model);
CREATE INDEX IF NOT EXISTS idx_runs_model ON runs(model);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);
-- Per-(run, prompt, model) brand/domain mentions in response text (which brand was mentioned, own vs other)
CREATE TABLE IF NOT EXISTS run_prompt_mentions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  prompt_id INTEGER NOT NULL,
  model TEXT NOT NULL,
  mentioned TEXT NOT NULL,
  is_own_domain INTEGER DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (run_id) REFERENCES runs(id),
  FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);

CREATE INDEX IF NOT EXISTS idx_run_prompt_visibility_run ON run_prompt_visibility(run_id);
CREATE INDEX IF NOT EXISTS idx_run_prompt_visibility_prompt ON run_prompt_visibility(prompt_id);
-- Stored LLM response content per (run, prompt) for re-processing and display
CREATE TABLE IF NOT EXISTS run_prompt_responses (
  run_id INTEGER NOT NULL,
  prompt_id INTEGER NOT NULL,
  model TEXT NOT NULL,
  response_text TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (run_id, prompt_id),
  FOREIGN KEY (run_id) REFERENCES runs(id),
  FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);

CREATE INDEX IF NOT EXISTS idx_run_prompt_mentions_prompt ON run_prompt_mentions(prompt_id);
CREATE INDEX IF NOT EXISTS idx_run_prompt_mentions_run ON run_prompt_mentions(run_id);
CREATE INDEX IF NOT EXISTS idx_run_prompt_responses_prompt ON run_prompt_responses(prompt_id);

-- Domains (replaces config/domains.yaml tracked_domains + brand_names)
CREATE TABLE IF NOT EXISTS domains (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain TEXT NOT NULL UNIQUE,
  brand_names TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Domain discovery profiles (replaces config/domain_profiles.yaml)
CREATE TABLE IF NOT EXISTS domain_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain_id INTEGER NOT NULL UNIQUE,
  category TEXT,
  niche TEXT,
  value_proposition TEXT,
  key_topics TEXT,
  target_audience TEXT,
  competitors TEXT,
  discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (domain_id) REFERENCES domains(id)
);

CREATE INDEX IF NOT EXISTS idx_domain_profiles_domain_id ON domain_profiles(domain_id);

-- Monitoring settings (singleton: one row id=1)
CREATE TABLE IF NOT EXISTS monitoring_settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  enabled INTEGER DEFAULT 1,
  frequency_minutes INTEGER,
  domain_ids TEXT,
  models TEXT,
  prompt_limit INTEGER,
  delay_seconds REAL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Monitoring executions (one per manual or scheduled run)
CREATE TABLE IF NOT EXISTS monitoring_executions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMP,
  trigger_type TEXT DEFAULT 'manual',
  status TEXT DEFAULT 'running',
  settings_snapshot TEXT
);

CREATE INDEX IF NOT EXISTS idx_monitoring_executions_started ON monitoring_executions(started_at);
