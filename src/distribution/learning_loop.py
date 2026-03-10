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


def generate_weekly_summary(from_date: str | None = None, to_date: str | None = None) -> str:
    """Compare recent runs; output text summary of what worked.
    from_date, to_date: optional ISO date strings (YYYY-MM-DD). Filter runs by started_at in range [from_date, to_date].
    """
    conn = get_connection()
    try:
        run_where = "status = 'finished' AND prompt_count > 0"
        run_params: list = []
        if from_date:
            run_where += " AND date(started_at) >= date(?)"
            run_params.append(from_date)
        if to_date:
            run_where += " AND date(started_at) <= date(?)"
            run_params.append(to_date)
        run_params.append(30)
        runs = conn.execute(
            f"""SELECT id, model, started_at, prompt_count FROM runs
               WHERE {run_where}
               ORDER BY started_at DESC LIMIT ?""",
            tuple(run_params),
        ).fetchall()
        if not runs:
            return "No finished runs yet for the selected range. Run the monitor first or widen the date range."
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
        draft_where = "status IN ('published','approved')"
        draft_params: list = []
        if from_date:
            draft_where += " AND date(updated_at) >= date(?)"
            draft_params.append(from_date)
        if to_date:
            draft_where += " AND date(updated_at) <= date(?)"
            draft_params.append(to_date)
        draft_params.append(5)
        drafts = conn.execute(
            f"SELECT id, title, status, published_at FROM drafts WHERE {draft_where} ORDER BY updated_at DESC LIMIT ?",
            tuple(draft_params),
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
