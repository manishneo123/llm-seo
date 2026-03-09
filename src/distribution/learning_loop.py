"""Re-run monitoring and compute citation uplift; generate weekly summary."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.db.connection import get_connection


def get_citation_rates_by_run(conn, run_ids: list[int]) -> dict[int, float]:
    """Citation rate (cited prompts / total prompts) per run."""
    rates = {}
    for run_id in run_ids:
        r = conn.execute(
            "SELECT prompt_count FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if not r or not r["prompt_count"]:
            rates[run_id] = 0.0
            continue
        total = r["prompt_count"]
        cited = conn.execute(
            "SELECT COUNT(DISTINCT prompt_id) AS c FROM citations WHERE run_id = ? AND is_own_domain = 1",
            (run_id,),
        ).fetchone()["c"]
        rates[run_id] = (cited / total * 100) if total else 0.0
    return rates


def generate_weekly_summary() -> str:
    """Compare recent runs; output text summary of what worked."""
    conn = get_connection()
    try:
        runs = conn.execute(
            """SELECT id, model, started_at, prompt_count FROM runs
               WHERE status = 'finished' AND prompt_count > 0
               ORDER BY started_at DESC LIMIT 30"""
        ).fetchall()
        if not runs:
            return "No finished runs yet. Run the monitor first."
        by_model = {}
        for r in runs:
            rate = get_citation_rates_by_run(conn, [r["id"]])[r["id"]]
            key = r["model"]
            if key not in by_model:
                by_model[key] = []
            by_model[key].append((r["started_at"], rate))
        lines = ["Weekly citation summary", "---"]
        for model, points in by_model.items():
            if len(points) >= 2:
                latest = points[0][1]
                prev = points[1][1]
                delta = latest - prev
                lines.append(f"{model}: {latest:.1f}% (prev {prev:.1f}%, delta {delta:+.1f}%)")
            else:
                lines.append(f"{model}: {points[0][1]:.1f}% (single run)")
        drafts = conn.execute(
            "SELECT id, title, status, published_at FROM drafts WHERE status IN ('published','approved') ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
        if drafts:
            lines.append("")
            lines.append("Recent published/approved drafts:")
            for d in drafts:
                lines.append(f"  - {d['title'][:50]} ({d['status']})")
        return "\n".join(lines)
    finally:
        conn.close()


def store_uplift(draft_id: int, run_id_before: int, run_id_after: int, rate_before: float, rate_after: float) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO citation_uplift (draft_id, run_id_before, run_id_after, citation_rate_before, citation_rate_after)
               VALUES (?, ?, ?, ?, ?)""",
            (draft_id, run_id_before, run_id_after, rate_before, rate_after),
        )
        conn.commit()
    finally:
        conn.close()
