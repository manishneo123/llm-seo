"""SQLite connection and init from schema."""
import os
import sqlite3
from pathlib import Path

# Default DB path: project root / data/llm_seo.db
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "llm_seo.db"


def get_db_path() -> Path:
    return Path(os.environ.get("LLM_SEO_DB_PATH", str(DEFAULT_DB_PATH)))


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_drafts_publication_columns(conn: sqlite3.Connection) -> None:
    """Add published_url, verification_status, verified_at to drafts if missing."""
    cur = conn.execute("PRAGMA table_info(drafts)")
    names = {row[1] for row in cur.fetchall()}
    for col, typ in [("published_url", "TEXT"), ("verification_status", "TEXT"), ("verified_at", "TIMESTAMP")]:
        if col not in names:
            conn.execute(f"ALTER TABLE drafts ADD COLUMN {col} {typ}")
    conn.commit()


def _migrate_briefs_image_columns(conn: sqlite3.Connection) -> None:
    """Add image_prompts, image_urls, and updated_at to content_briefs if missing (JSON arrays)."""
    cur = conn.execute("PRAGMA table_info(content_briefs)")
    names = {row[1] for row in cur.fetchall()}
    for col, typ in [("image_prompts", "TEXT"), ("image_urls", "TEXT"), ("updated_at", "TIMESTAMP")]:
        if col not in names:
            conn.execute(f"ALTER TABLE content_briefs ADD COLUMN {col} {typ}")
    conn.commit()


def _migrate_drafts_image_urls(conn: sqlite3.Connection) -> None:
    """Add image_urls to drafts if missing (JSON array of image URLs)."""
    cur = conn.execute("PRAGMA table_info(drafts)")
    names = {row[1] for row in cur.fetchall()}
    if "image_urls" not in names:
        conn.execute("ALTER TABLE drafts ADD COLUMN image_urls TEXT")
        conn.commit()


def _migrate_prompts_generation_run_id(conn: sqlite3.Connection) -> None:
    """Add prompt_generation_run_id to prompts if missing (links prompt to the run that created it)."""
    cur = conn.execute("PRAGMA table_info(prompts)")
    names = {row[1] for row in cur.fetchall()}
    if "prompt_generation_run_id" not in names:
        conn.execute("ALTER TABLE prompts ADD COLUMN prompt_generation_run_id INTEGER")
        conn.commit()


def _migrate_citations_is_own_domain(conn: sqlite3.Connection) -> None:
    """Add is_own_domain to citations if missing (1 = our tracked domain, 0 = other website)."""
    cur = conn.execute("PRAGMA table_info(citations)")
    names = {row[1] for row in cur.fetchall()}
    if "is_own_domain" not in names:
        conn.execute("ALTER TABLE citations ADD COLUMN is_own_domain INTEGER DEFAULT 1")
        conn.commit()


def _migrate_run_prompt_visibility(conn: sqlite3.Connection) -> None:
    """Create run_prompt_visibility table if missing."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='run_prompt_visibility'"
    )
    if cur.fetchone():
        return
    conn.execute("""
        CREATE TABLE run_prompt_visibility (
          run_id INTEGER NOT NULL,
          prompt_id INTEGER NOT NULL,
          had_own_citation INTEGER DEFAULT 0,
          brand_mentioned INTEGER DEFAULT 0,
          competitor_only INTEGER DEFAULT 0,
          PRIMARY KEY (run_id, prompt_id),
          FOREIGN KEY (run_id) REFERENCES runs(id),
          FOREIGN KEY (prompt_id) REFERENCES prompts(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_prompt_visibility_run ON run_prompt_visibility(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_prompt_visibility_prompt ON run_prompt_visibility(prompt_id)")
    conn.commit()


def _migrate_run_prompt_mentions(conn: sqlite3.Connection) -> None:
    """Create run_prompt_mentions table if missing."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='run_prompt_mentions'"
    )
    if cur.fetchone():
        return
    conn.execute("""
        CREATE TABLE run_prompt_mentions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id INTEGER NOT NULL,
          prompt_id INTEGER NOT NULL,
          model TEXT NOT NULL,
          mentioned TEXT NOT NULL,
          is_own_domain INTEGER DEFAULT 1,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY (run_id) REFERENCES runs(id),
          FOREIGN KEY (prompt_id) REFERENCES prompts(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_prompt_mentions_prompt ON run_prompt_mentions(prompt_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_prompt_mentions_run ON run_prompt_mentions(run_id)")
    conn.commit()


def _migrate_run_prompt_responses(conn: sqlite3.Connection) -> None:
    """Create run_prompt_responses table if missing (store full LLM response text)."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='run_prompt_responses'"
    )
    if cur.fetchone():
        return
    conn.execute("""
        CREATE TABLE run_prompt_responses (
          run_id INTEGER NOT NULL,
          prompt_id INTEGER NOT NULL,
          model TEXT NOT NULL,
          response_text TEXT NOT NULL,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (run_id, prompt_id),
          FOREIGN KEY (run_id) REFERENCES runs(id),
          FOREIGN KEY (prompt_id) REFERENCES prompts(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_run_prompt_responses_prompt ON run_prompt_responses(prompt_id)")
    conn.commit()


def _migrate_domains_and_profiles(conn: sqlite3.Connection) -> None:
    """Create domains and domain_profiles tables if missing."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='domains'"
    )
    if cur.fetchone():
        return
    conn.execute("""
        CREATE TABLE domains (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          domain TEXT NOT NULL UNIQUE,
          brand_names TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE domain_profiles (
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
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_profiles_domain_id ON domain_profiles(domain_id)")
    conn.commit()


def _migrate_categories_and_domain_profiles_categories(conn: sqlite3.Connection) -> None:
    """Create categories table if missing; add categories column to domain_profiles if missing."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='categories'"
    )
    if not cur.fetchone():
        conn.execute("""
            CREATE TABLE categories (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name)")
    cur = conn.execute("PRAGMA table_info(domain_profiles)")
    names = {row[1] for row in cur.fetchall()}
    if "categories" not in names:
        conn.execute("ALTER TABLE domain_profiles ADD COLUMN categories TEXT")
    conn.commit()


def _migrate_monitoring_tables(conn: sqlite3.Connection) -> None:
    """Create monitoring_settings, monitoring_executions; add execution_id to runs."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='monitoring_settings'"
    )
    if not cur.fetchone():
        conn.execute("""
            CREATE TABLE monitoring_settings (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              enabled INTEGER DEFAULT 1,
              frequency_minutes INTEGER,
              domain_ids TEXT,
              models TEXT,
              prompt_limit INTEGER,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT OR IGNORE INTO monitoring_settings (id, enabled) VALUES (1, 1)"
        )
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='monitoring_executions'"
    )
    if not cur.fetchone():
        conn.execute("""
            CREATE TABLE monitoring_executions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              finished_at TIMESTAMP,
              trigger_type TEXT DEFAULT 'manual',
              status TEXT DEFAULT 'running',
              settings_snapshot TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_monitoring_executions_started ON monitoring_executions(started_at)"
        )
    cur = conn.execute("PRAGMA table_info(runs)")
    names = {row[1] for row in cur.fetchall()}
    if "execution_id" not in names:
        conn.execute("ALTER TABLE runs ADD COLUMN execution_id INTEGER")
    cur = conn.execute("PRAGMA table_info(monitoring_settings)")
    names = {row[1] for row in cur.fetchall()}
    if "delay_seconds" not in names:
        conn.execute("ALTER TABLE monitoring_settings ADD COLUMN delay_seconds REAL")
    conn.commit()


def _migrate_prompt_generation_settings(conn: sqlite3.Connection) -> None:
    """Create prompt_generation_settings singleton if missing."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='prompt_generation_settings'"
    )
    if cur.fetchone():
        return
    conn.execute("""
        CREATE TABLE prompt_generation_settings (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          enabled INTEGER DEFAULT 0,
          frequency_days REAL NOT NULL DEFAULT 7,
          prompts_per_domain INTEGER,
          last_run_at TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "INSERT OR IGNORE INTO prompt_generation_settings (id, enabled, frequency_days) VALUES (1, 0, 7)"
    )
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='prompt_generation_runs'"
    )
    if not cur.fetchone():
        conn.execute("""
            CREATE TABLE prompt_generation_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              finished_at TIMESTAMP,
              trigger_type TEXT DEFAULT 'manual',
              status TEXT DEFAULT 'running',
              inserted_count INTEGER
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_prompt_generation_runs_started ON prompt_generation_runs(started_at)"
        )
    conn.commit()


def _migrate_users_and_user_id(conn: sqlite3.Connection) -> None:
    """Create users table and add user_id to all user-owned tables; create default user and backfill."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
    )
    if not cur.fetchone():
        conn.execute("""
            CREATE TABLE users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              name TEXT,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    # Ensure default user exists (for backfilling existing data)
    cur = conn.execute("SELECT id FROM users WHERE email = 'legacy@local'").fetchone()
    if not cur:
        cur = conn.execute("SELECT id FROM users WHERE id = 1").fetchone()
    if not cur:
        import hashlib
        placeholder = hashlib.sha256(b"legacy-placeholder").hexdigest()
        try:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, created_at) VALUES (1, ?, ?, CURRENT_TIMESTAMP)",
                ("legacy@local", placeholder),
            )
        except sqlite3.IntegrityError:
            conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                ("legacy@local", placeholder),
            )
    cur = conn.execute("SELECT id FROM users WHERE email = 'legacy@local'").fetchone()
    default_uid = cur[0] if cur else 1

    tables_and_columns = [
        ("domains", "user_id"),
        ("prompts", "user_id"),
        ("content_briefs", "user_id"),
        ("drafts", "user_id"),
        ("content_sources", "user_id"),
        ("monitoring_executions", "user_id"),
        ("prompt_generation_runs", "user_id"),
    ]
    for table, col in tables_and_columns:
        cur = conn.execute(f"PRAGMA table_info({table})")
        names = {row[1] for row in cur.fetchall()}
        if col not in names:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER DEFAULT 1")
            conn.execute(f"UPDATE {table} SET {col} = ? WHERE {col} IS NULL", (default_uid,))

    # Migrate monitoring_settings from id=1 to user_id PK
    cur = conn.execute("PRAGMA table_info(monitoring_settings)")
    cols = {row[1] for row in cur.fetchall()}
    if "id" in cols and "user_id" not in cols:
        conn.execute("""
            CREATE TABLE monitoring_settings_new (
              user_id INTEGER PRIMARY KEY,
              enabled INTEGER DEFAULT 1,
              frequency_minutes INTEGER,
              domain_ids TEXT,
              models TEXT,
              prompt_limit INTEGER,
              delay_seconds REAL,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            INSERT INTO monitoring_settings_new (user_id, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds, updated_at)
            SELECT 1, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds, updated_at
            FROM monitoring_settings WHERE id = 1
        """)
        conn.execute("DROP TABLE monitoring_settings")
        conn.execute("ALTER TABLE monitoring_settings_new RENAME TO monitoring_settings")
    elif "user_id" not in cols:
        conn.execute("ALTER TABLE monitoring_settings ADD COLUMN user_id INTEGER PRIMARY KEY")
        # SQLite doesn't allow ADD COLUMN with PRIMARY KEY like that; use new table
        conn.execute("""
            CREATE TABLE monitoring_settings_new (
              user_id INTEGER PRIMARY KEY,
              enabled INTEGER DEFAULT 1,
              frequency_minutes INTEGER,
              domain_ids TEXT,
              models TEXT,
              prompt_limit INTEGER,
              delay_seconds REAL,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            INSERT INTO monitoring_settings_new (user_id, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds, updated_at)
            SELECT ?, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds, updated_at
            FROM monitoring_settings LIMIT 1
        """, (default_uid,))
        conn.execute("DROP TABLE monitoring_settings")
        conn.execute("ALTER TABLE monitoring_settings_new RENAME TO monitoring_settings")

    # Migrate prompt_generation_settings from id=1 to user_id PK
    cur = conn.execute("PRAGMA table_info(prompt_generation_settings)")
    cols = {row[1] for row in cur.fetchall()}
    if "id" in cols and "user_id" not in cols:
        conn.execute("""
            CREATE TABLE prompt_generation_settings_new (
              user_id INTEGER PRIMARY KEY,
              enabled INTEGER DEFAULT 0,
              frequency_days REAL NOT NULL DEFAULT 7,
              prompts_per_domain INTEGER,
              last_run_at TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            INSERT INTO prompt_generation_settings_new (user_id, enabled, frequency_days, prompts_per_domain, last_run_at, updated_at)
            SELECT 1, enabled, frequency_days, prompts_per_domain, last_run_at, updated_at
            FROM prompt_generation_settings WHERE id = 1
        """)
        conn.execute("DROP TABLE prompt_generation_settings")
        conn.execute("ALTER TABLE prompt_generation_settings_new RENAME TO prompt_generation_settings")
    elif "user_id" not in cols:
        conn.execute("""
            CREATE TABLE prompt_generation_settings_new (
              user_id INTEGER PRIMARY KEY,
              enabled INTEGER DEFAULT 0,
              frequency_days REAL NOT NULL DEFAULT 7,
              prompts_per_domain INTEGER,
              last_run_at TIMESTAMP,
              updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            INSERT INTO prompt_generation_settings_new (user_id, enabled, frequency_days, prompts_per_domain, last_run_at, updated_at)
            SELECT ?, enabled, frequency_days, prompts_per_domain, last_run_at, updated_at
            FROM prompt_generation_settings LIMIT 1
        """, (default_uid,))
        conn.execute("DROP TABLE prompt_generation_settings")
        conn.execute("ALTER TABLE prompt_generation_settings_new RENAME TO prompt_generation_settings")

    conn.commit()


def _migrate_content_sources_tables(conn: sqlite3.Connection) -> None:
    """Create content_sources, domain_content_source, draft_publications if missing."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='content_sources'"
    )
    if cur.fetchone():
        return
    conn.execute("""
        CREATE TABLE content_sources (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          type TEXT NOT NULL,
          config TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE domain_content_source (
          domain_id INTEGER NOT NULL,
          content_source_id INTEGER NOT NULL,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (domain_id, content_source_id),
          FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE,
          FOREIGN KEY (content_source_id) REFERENCES content_sources(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE draft_publications (
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
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_content_source_domain ON domain_content_source(domain_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_domain_content_source_source ON domain_content_source(content_source_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_publications_draft ON draft_publications(draft_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_publications_source ON draft_publications(content_source_id)")
    conn.commit()


def _migrate_llm_provider_settings(conn: sqlite3.Connection) -> None:
    """Create llm_provider_settings table if missing; add model columns if missing."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_provider_settings'"
    )
    if not cur.fetchone():
        conn.execute("""
            CREATE TABLE llm_provider_settings (
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
            )
        """)
        conn.commit()
        return
    cur = conn.execute("PRAGMA table_info(llm_provider_settings)")
    names = {row[1] for row in cur.fetchall()}
    for col in ("openai_model", "perplexity_model", "anthropic_model", "gemini_model"):
        if col not in names:
            conn.execute(f"ALTER TABLE llm_provider_settings ADD COLUMN {col} TEXT")
    conn.commit()


def _migrate_trial_sessions(conn: sqlite3.Connection) -> None:
    """Create trial_sessions table if missing; add slug column if missing."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='trial_sessions'"
    )
    if not cur.fetchone():
        conn.execute("""
            CREATE TABLE trial_sessions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              token TEXT NOT NULL UNIQUE,
              website TEXT NOT NULL,
              slug TEXT NOT NULL,
              execution_id INTEGER NOT NULL,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (execution_id) REFERENCES monitoring_executions(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trial_sessions_token ON trial_sessions(token)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trial_sessions_slug ON trial_sessions(slug)")
        conn.commit()
        return
    cur = conn.execute("PRAGMA table_info(trial_sessions)")
    names = {row[1] for row in cur.fetchall()}
    if "slug" not in names:
        conn.execute("ALTER TABLE trial_sessions ADD COLUMN slug TEXT")
        conn.execute("UPDATE trial_sessions SET slug = REPLACE(LOWER(website), '.', '-') WHERE slug IS NULL OR slug = ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trial_sessions_slug ON trial_sessions(slug)")
    conn.commit()


def _migrate_llm_task_queue(conn: sqlite3.Connection) -> None:
    """Create llm_task_queue table for task-level rate limiting of LLM calls."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='llm_task_queue'"
    )
    if cur.fetchone():
        return
    conn.execute("""
        CREATE TABLE llm_task_queue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          type TEXT NOT NULL,
          payload TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          execution_id INTEGER,
          run_id INTEGER,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          started_at TIMESTAMP,
          finished_at TIMESTAMP,
          error_message TEXT,
          FOREIGN KEY (execution_id) REFERENCES monitoring_executions(id),
          FOREIGN KEY (run_id) REFERENCES runs(id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_task_queue_status_created ON llm_task_queue(status, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_task_queue_execution ON llm_task_queue(execution_id)")
    conn.commit()


def _migrate_citation_uplift_brand_rates(conn: sqlite3.Connection) -> None:
    """Add brand_rate_before and brand_rate_after to citation_uplift for self-learning from brand mentions."""
    cur = conn.execute("PRAGMA table_info(citation_uplift)")
    names = {row[1] for row in cur.fetchall()}
    for col, typ in [("brand_rate_before", "REAL"), ("brand_rate_after", "REAL")]:
        if col not in names:
            conn.execute(f"ALTER TABLE citation_uplift ADD COLUMN {col} {typ}")
    conn.commit()


def _migrate_trial_rate_limit(conn: sqlite3.Connection) -> None:
    """Create trial_rate_limit table for per-IP rate limiting of trial runs."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='trial_rate_limit'"
    )
    if cur.fetchone():
        return
    conn.execute("""
        CREATE TABLE trial_rate_limit (
            ip TEXT NOT NULL,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trial_rate_limit_ip ON trial_rate_limit(ip)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trial_rate_limit_requested ON trial_rate_limit(requested_at)")
    conn.commit()


def init_db(conn: sqlite3.Connection | None = None) -> None:
    if conn is None:
        conn = get_connection()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    _migrate_drafts_publication_columns(conn)
    _migrate_briefs_image_columns(conn)
    _migrate_drafts_image_urls(conn)
    _migrate_prompts_generation_run_id(conn)
    _migrate_citations_is_own_domain(conn)
    _migrate_run_prompt_visibility(conn)
    _migrate_run_prompt_mentions(conn)
    _migrate_run_prompt_responses(conn)
    _migrate_domains_and_profiles(conn)
    _migrate_categories_and_domain_profiles_categories(conn)
    _migrate_monitoring_tables(conn)
    _migrate_prompt_generation_settings(conn)
    _migrate_users_and_user_id(conn)
    _migrate_content_sources_tables(conn)
    _migrate_llm_provider_settings(conn)
    _migrate_trial_sessions(conn)
    _migrate_llm_task_queue(conn)
    _migrate_citation_uplift_brand_rates(conn)
    _migrate_trial_rate_limit(conn)
