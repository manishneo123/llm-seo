-- TRUSEO - SQLite schema

-- Users (for signup/signin and data scoping)
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  name TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Prompts we query LLMs with (generated or loaded from config)
CREATE TABLE IF NOT EXISTS prompts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  text TEXT NOT NULL,
  niche TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  prompt_generation_run_id INTEGER,
  FOREIGN KEY (user_id) REFERENCES users(id),
  UNIQUE(user_id, text)
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
  user_id INTEGER NOT NULL,
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
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (prompt_id) REFERENCES prompts(id)
);

-- Drafts (Sprint 3)
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
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
  image_urls TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id),
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
  user_id INTEGER NOT NULL,
  domain TEXT NOT NULL,
  brand_names TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id),
  UNIQUE(user_id, domain)
);

-- Categories: metadata table of all possible domain categories (populated by discovery)
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name);

-- Domain discovery profiles (replaces config/domain_profiles.yaml)
CREATE TABLE IF NOT EXISTS domain_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  domain_id INTEGER NOT NULL UNIQUE,
  category TEXT,
  categories TEXT,
  niche TEXT,
  value_proposition TEXT,
  key_topics TEXT,
  target_audience TEXT,
  competitors TEXT,
  discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (domain_id) REFERENCES domains(id)
);

CREATE INDEX IF NOT EXISTS idx_domain_profiles_domain_id ON domain_profiles(domain_id);

-- Monitoring settings (one row per user)
CREATE TABLE IF NOT EXISTS monitoring_settings (
  user_id INTEGER PRIMARY KEY,
  enabled INTEGER DEFAULT 1,
  frequency_minutes INTEGER,
  domain_ids TEXT,
  models TEXT,
  prompt_limit INTEGER,
  delay_seconds REAL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Monitoring executions (one per manual or scheduled run)
CREATE TABLE IF NOT EXISTS monitoring_executions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMP,
  trigger_type TEXT DEFAULT 'manual',
  status TEXT DEFAULT 'running',
  settings_snapshot TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_monitoring_executions_started ON monitoring_executions(started_at);

-- Prompt generation schedule (one row per user)
CREATE TABLE IF NOT EXISTS prompt_generation_settings (
  user_id INTEGER PRIMARY KEY,
  enabled INTEGER DEFAULT 0,
  frequency_days REAL NOT NULL DEFAULT 7,
  prompts_per_domain INTEGER,
  last_run_at TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Prompt generation runs (one row per scheduled or manual run)
CREATE TABLE IF NOT EXISTS prompt_generation_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMP,
  trigger_type TEXT DEFAULT 'manual',
  status TEXT DEFAULT 'running',
  inserted_count INTEGER,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_prompt_generation_runs_started ON prompt_generation_runs(started_at);

-- Content sources (Hashnode, Ghost, WordPress, Webflow, etc.) – user-created, mapped to domains
CREATE TABLE IF NOT EXISTS content_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  config TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Mapping: which content sources are used for which domains (many-to-many)
CREATE TABLE IF NOT EXISTS domain_content_source (
  domain_id INTEGER NOT NULL,
  content_source_id INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (domain_id, content_source_id),
  FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE,
  FOREIGN KEY (content_source_id) REFERENCES content_sources(id) ON DELETE CASCADE
);

-- Record of each publication: draft → content source (or manual URL) with full details
CREATE TABLE IF NOT EXISTS draft_publications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  draft_id INTEGER NOT NULL,
  content_source_id INTEGER,
  published_url TEXT,
  status TEXT NOT NULL,
  error_message TEXT,
  published_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE,
  FOREIGN KEY (content_source_id) REFERENCES content_sources(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_domain_content_source_domain ON domain_content_source(domain_id);
CREATE INDEX IF NOT EXISTS idx_domain_content_source_source ON domain_content_source(content_source_id);
CREATE INDEX IF NOT EXISTS idx_draft_publications_draft ON draft_publications(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_publications_source ON draft_publications(content_source_id);

-- LLM provider API keys and model names (OpenAI, Perplexity, Anthropic, Gemini) – per user, stored in Settings
CREATE TABLE IF NOT EXISTS llm_provider_settings (
  user_id INTEGER PRIMARY KEY,
  openai_api_key TEXT,
  perplexity_api_key TEXT,
  anthropic_api_key TEXT,
  gemini_api_key TEXT,
  openai_model TEXT,
  perplexity_model TEXT,
  anthropic_model TEXT,
  gemini_model TEXT,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Trial sessions: token-based access to execution status for unauthenticated trial runs
CREATE TABLE IF NOT EXISTS trial_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token TEXT NOT NULL UNIQUE,
  website TEXT NOT NULL,
  slug TEXT NOT NULL,
  execution_id INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (execution_id) REFERENCES monitoring_executions(id)
);
CREATE INDEX IF NOT EXISTS idx_trial_sessions_token ON trial_sessions(token);
