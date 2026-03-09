"""Query DB for queue sizes and conditions (no side effects)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.db.connection import get_connection, init_db


def get_prompt_count() -> int:
    conn = get_connection()
    try:
        init_db(conn)
        r = conn.execute("SELECT COUNT(*) AS c FROM prompts").fetchone()
        return r["c"] or 0
    finally:
        conn.close()


def get_uncited_prompt_count(days: int = 7) -> int:
    conn = get_connection()
    try:
        init_db(conn)
        r = conn.execute(
            """SELECT COUNT(*) AS c FROM prompts p
               WHERE NOT EXISTS (
                 SELECT 1 FROM citations c
                 JOIN runs r ON r.id = c.run_id
                 WHERE c.prompt_id = p.id AND c.is_own_domain = 1 AND r.started_at >= date('now', ?)
               )""",
            (f"-{days} days",),
        ).fetchone()
        return r["c"] or 0
    finally:
        conn.close()


def get_pending_brief_count() -> int:
    conn = get_connection()
    try:
        init_db(conn)
        r = conn.execute("SELECT COUNT(*) AS c FROM content_briefs WHERE status = 'pending'").fetchone()
        return r["c"] or 0
    finally:
        conn.close()


def get_pending_draft_count() -> int:
    conn = get_connection()
    try:
        init_db(conn)
        r = conn.execute("SELECT COUNT(*) AS c FROM drafts WHERE status = 'draft'").fetchone()
        return r["c"] or 0
    finally:
        conn.close()


def get_approved_or_published_draft_count() -> int:
    conn = get_connection()
    try:
        init_db(conn)
        r = conn.execute(
            "SELECT COUNT(*) AS c FROM drafts WHERE status IN ('approved','published')"
        ).fetchone()
        return r["c"] or 0
    finally:
        conn.close()
