"""Load uncited prompts from DB (prompts with zero citations in last N days)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.db.connection import get_connection


def get_uncited_prompts(days: int = 7, limit: int = 50):
    """Return list of (prompt_id, text) for prompts with no citations in recent runs."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT p.id, p.text
            FROM prompts p
            WHERE NOT EXISTS (
                SELECT 1 FROM citations c
                JOIN runs r ON r.id = c.run_id
                WHERE c.prompt_id = p.id AND c.is_own_domain = 1
                  AND r.started_at >= date('now', ?)
            )
            ORDER BY p.id
            LIMIT ?
        """, (f"-{days} days", limit)).fetchall()
        return [(r["id"], r["text"]) for r in rows]
    finally:
        conn.close()
