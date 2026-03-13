"""Collect success data from DB: citation uplift, cited prompts/niches, published drafts and their briefs."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.db.connection import get_connection, init_db


def collect_uplift_and_briefs() -> list[dict]:
    """Return list of uplift rows with draft and brief info for drafts that had citation uplift."""
    conn = get_connection()
    try:
        init_db(conn)
        rows = conn.execute("""
            SELECT u.id, u.draft_id, u.citation_rate_before, u.citation_rate_after,
                   u.brand_rate_before, u.brand_rate_after,
                   d.title AS draft_title, d.brief_id, d.status AS draft_status,
                   b.topic, b.angle, b.suggested_headings, b.schema_to_add, b.priority_score
            FROM citation_uplift u
            JOIN drafts d ON d.id = u.draft_id
            LEFT JOIN content_briefs b ON b.id = d.brief_id
            ORDER BY (u.citation_rate_after - u.citation_rate_before) + (COALESCE(u.brand_rate_after, 0) - COALESCE(u.brand_rate_before, 0)) DESC
            LIMIT 20
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def collect_cited_prompts_by_niche(limit: int = 100) -> list[dict]:
    """Return prompts that got at least one citation, with niche and count."""
    conn = get_connection()
    try:
        init_db(conn)
        rows = conn.execute("""
            SELECT p.id, p.text, p.niche, COUNT(DISTINCT c.run_id) AS citation_runs
            FROM prompts p
            JOIN citations c ON c.prompt_id = p.id AND c.is_own_domain = 1
            GROUP BY p.id
            ORDER BY citation_runs DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def collect_recent_run_summary() -> list[dict]:
    """Citation rate per run (model, started_at, rate)."""
    conn = get_connection()
    try:
        init_db(conn)
        runs = conn.execute("""
            SELECT id, model, started_at, prompt_count FROM runs
            WHERE status = 'finished' AND prompt_count > 0
            ORDER BY started_at DESC LIMIT 30
        """).fetchall()
        out = []
        for r in runs:
            cited = conn.execute(
                "SELECT COUNT(DISTINCT prompt_id) AS c FROM citations WHERE run_id = ? AND is_own_domain = 1",
                (r["id"],),
            ).fetchone()["c"]
            rate = (cited / r["prompt_count"] * 100) if r["prompt_count"] else 0
            out.append({"model": r["model"], "started_at": r["started_at"], "citation_rate_pct": round(rate, 2)})
        return out
    finally:
        conn.close()


def collect_all_for_hints() -> dict:
    """Aggregate all data needed to generate learning hints."""
    uplift = collect_uplift_and_briefs()
    cited = collect_cited_prompts_by_niche(50)
    runs = collect_recent_run_summary()
    # Build a short text summary for the LLM
    lines = ["=== Citation and brand uplift (drafts that improved citation or brand mention rate) ==="]
    if uplift:
        for u in uplift[:10]:
            cite_delta = (u.get("citation_rate_after") or 0) - (u.get("citation_rate_before") or 0)
            brand_before = u.get("brand_rate_before")
            brand_after = u.get("brand_rate_after")
            brand_delta = (brand_after - brand_before) if (brand_before is not None and brand_after is not None) else None
            brand_str = f"; brand_delta={brand_delta:+.1f}%" if brand_delta is not None else ""
            lines.append(
                f"  Draft: {u.get('draft_title', '')[:50]}; topic={u.get('topic', '')[:40]}; schema={u.get('schema_to_add')}; citation_delta={cite_delta:.1f}%{brand_str}"
            )
    else:
        lines.append("  (none yet)")

    lines.append("\n=== Prompts/niches that got cited ===")
    if cited:
        by_niche = {}
        for c in cited:
            n = c.get("niche") or "unknown"
            by_niche.setdefault(n, []).append(c.get("text", "")[:60])
        for niche, texts in list(by_niche.items())[:10]:
            lines.append(f"  Niche: {niche}; examples: {texts[:3]}")
    else:
        lines.append("  (none yet)")

    lines.append("\n=== Recent run citation rates ===")
    for r in runs[:10]:
        lines.append(f"  {r['model']} @ {r['started_at']}: {r['citation_rate_pct']}%")

    return {"summary": "\n".join(lines), "uplift": uplift, "cited_prompts": cited, "runs": runs}
