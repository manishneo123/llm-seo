"""Re-run monitoring and compute citation uplift; generate weekly summary."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.db.connection import get_connection


def _uplift_before_days() -> int:
    """Days before publication to look for 'before' run. Env UPLIFT_BEFORE_DAYS or 30."""
    try:
        return max(1, int(os.environ.get("UPLIFT_BEFORE_DAYS", "30")))
    except (TypeError, ValueError):
        return 30


def _uplift_after_days() -> int:
    """Max days after publication to look for 'after' run. Env UPLIFT_AFTER_DAYS or 14."""
    try:
        return max(1, int(os.environ.get("UPLIFT_AFTER_DAYS", "14")))
    except (TypeError, ValueError):
        return 14


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


def get_brand_rates_by_run(conn, run_ids: list[int]) -> dict[int, float]:
    """Brand mention rate (prompts with brand_mentioned=1 / total prompts) per run, as percentage 0-100."""
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
        brand = conn.execute(
            "SELECT COUNT(DISTINCT prompt_id) AS c FROM run_prompt_visibility WHERE run_id = ? AND brand_mentioned = 1",
            (run_id,),
        ).fetchone()["c"]
        rates[run_id] = (brand / total * 100) if total else 0.0
    return rates


def compute_and_store_uplift_for_draft(draft_id: int, conn=None) -> bool:
    """
    For a published/approved draft, find before/after monitoring runs for the same user,
    compute citation and brand rates, and store one citation_uplift row. Idempotent: skips if uplift already exists.
    Returns True if a new row was stored, False otherwise.
    """
    own_conn = conn is None
    if conn is None:
        conn = get_connection()
    try:
        draft = conn.execute(
            "SELECT id, user_id, status, published_at, updated_at FROM drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
        if not draft or draft["status"] not in ("published", "approved"):
            return False
        existing = conn.execute(
            "SELECT id FROM citation_uplift WHERE draft_id = ? LIMIT 1",
            (draft_id,),
        ).fetchone()
        if existing:
            return False
        ref_ts = draft["published_at"] or draft["updated_at"]
        if not ref_ts:
            return False
        user_id = draft["user_id"]
        run_before = conn.execute(
            """SELECT r.id FROM runs r
               JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
               WHERE r.status = 'finished' AND r.prompt_count > 0 AND r.started_at < ?
               ORDER BY r.started_at DESC LIMIT 1""",
            (user_id, ref_ts),
        ).fetchone()
        after_days = _uplift_after_days()
        run_after = conn.execute(
            """SELECT r.id FROM runs r
               JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
               WHERE r.status = 'finished' AND r.prompt_count > 0 AND r.started_at > ?
               AND date(r.started_at) <= date(?, '+' || ? || ' days')
               ORDER BY r.started_at ASC LIMIT 1""",
            (user_id, ref_ts, ref_ts, after_days),
        ).fetchone()
        if not run_before or not run_after:
            return False
        rid_before = run_before["id"]
        rid_after = run_after["id"]
        citation_rates = get_citation_rates_by_run(conn, [rid_before, rid_after])
        brand_rates = get_brand_rates_by_run(conn, [rid_before, rid_after])
        store_uplift(
            draft_id=draft_id,
            run_id_before=rid_before,
            run_id_after=rid_after,
            citation_rate_before=citation_rates.get(rid_before, 0.0),
            citation_rate_after=citation_rates.get(rid_after, 0.0),
            brand_rate_before=brand_rates.get(rid_before, 0.0),
            brand_rate_after=brand_rates.get(rid_after, 0.0),
        )
        return True
    finally:
        if own_conn:
            conn.close()


def compute_uplift_for_published_drafts(conn=None, user_id: int | None = None) -> int:
    """
    Find published/approved drafts that do not yet have a citation_uplift row and compute uplift for each.
    Returns count of new uplift rows stored.
    """
    if conn is None:
        conn = get_connection()
    try:
        where = "d.status IN ('published','approved') AND NOT EXISTS (SELECT 1 FROM citation_uplift u WHERE u.draft_id = d.id)"
        params: list = []
        if user_id is not None:
            where += " AND d.user_id = ?"
            params.append(user_id)
        drafts = conn.execute(
            f"SELECT d.id FROM drafts d WHERE {where}",
            tuple(params),
        ).fetchall()
        count = 0
        for row in drafts:
            if compute_and_store_uplift_for_draft(row["id"], conn=conn):
                count += 1
        return count
    finally:
        pass


def generate_weekly_summary(from_date: str | None = None, to_date: str | None = None, user_id: int | None = None) -> str:
    """Compare recent runs; output text summary of what worked.
    from_date, to_date: optional ISO date strings (YYYY-MM-DD). Filter runs by started_at in range [from_date, to_date].
    user_id: if set, only that user's runs and drafts.
    """
    conn = get_connection()
    try:
        run_params: list = []
        if user_id is not None:
            run_where = "r.status = 'finished' AND r.prompt_count > 0 AND e.user_id = ?"
            run_params.append(user_id)
        else:
            run_where = "r.status = 'finished' AND r.prompt_count > 0"
        if from_date:
            run_where += " AND date(r.started_at) >= date(?)"
            run_params.append(from_date)
        if to_date:
            run_where += " AND date(r.started_at) <= date(?)"
            run_params.append(to_date)
        run_params.append(30)
        if user_id is not None:
            runs = conn.execute(
                f"""SELECT r.id, r.model, r.started_at, r.prompt_count FROM runs r
                   JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
                   WHERE {run_where}
                   ORDER BY r.started_at DESC LIMIT ?""",
                tuple(run_params),
            ).fetchall()
        else:
            runs = conn.execute(
                f"""SELECT r.id, r.model, r.started_at, r.prompt_count FROM runs r
                   WHERE {run_where}
                   ORDER BY r.started_at DESC LIMIT ?""",
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
        if user_id is not None:
            draft_where += " AND user_id = ?"
            draft_params.append(user_id)
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


def store_uplift(
    draft_id: int,
    run_id_before: int,
    run_id_after: int,
    citation_rate_before: float,
    citation_rate_after: float,
    brand_rate_before: float | None = None,
    brand_rate_after: float | None = None,
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO citation_uplift (draft_id, run_id_before, run_id_after, citation_rate_before, citation_rate_after, brand_rate_before, brand_rate_after)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                draft_id,
                run_id_before,
                run_id_after,
                citation_rate_before,
                citation_rate_after,
                brand_rate_before,
                brand_rate_after,
            ),
        )
        conn.commit()
    finally:
        conn.close()
