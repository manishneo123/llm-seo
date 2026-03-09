"""Run monitoring: load prompts from DB, query each model, parse citations, store results."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from src.db.connection import get_connection, init_db
from src.monitor.query_runner import run_all_prompts, MODELS, get_available_models
from src.monitor.citation_parser import parse_response, load_tracked_domains
from src.monitor.mention_detector import brand_mentioned_in_text, get_mentions_in_text


def run(
    database_path=None,
    limit_prompts: int | None = None,
    models: list[str] | None = None,
    execution_id: int | None = None,
    trigger_type: str = "manual",
    settings_snapshot: dict | None = None,
    domain_ids: list[int] | None = None,
    delay_seconds: float | None = None,
):
    if limit_prompts is None:
        from src.config_loader import get_monitor_limit
        limit_prompts = get_monitor_limit()
    if database_path:
        os.environ["LLM_SEO_DB_PATH"] = str(database_path)
    conn = get_connection()
    init_db(conn)

    if execution_id is None:
        conn.execute(
            """INSERT INTO monitoring_executions (trigger_type, status, settings_snapshot)
               VALUES (?, 'running', ?)""",
            (trigger_type, json.dumps(settings_snapshot) if settings_snapshot else None),
        )
        execution_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

    prompt_query = "SELECT id, text, niche FROM prompts"
    params = []
    if domain_ids:
        placeholders = ",".join("?" * len(domain_ids))
        domain_rows = conn.execute(
            f"SELECT domain FROM domains WHERE id IN ({placeholders})",
            domain_ids,
        ).fetchall()
        domain_strings = [r["domain"] for r in domain_rows if r["domain"]]
        if domain_strings:
            placeholders2 = ",".join("?" * len(domain_strings))
            niches = [f"domain:{d}" for d in domain_strings]
            prompt_query += f" WHERE niche IN ({placeholders2})"
            params.extend(niches)
    prompt_query += " ORDER BY id LIMIT ?"
    params.append(limit_prompts or 9999)
    cur = conn.execute(prompt_query, params)
    rows = cur.fetchall()
    prompts = [(r["id"], r["text"]) for r in rows]
    if not prompts:
        print("No prompts in DB. Run prompt_generator.py first.")
        if execution_id is not None:
            conn.execute(
                """UPDATE monitoring_executions SET status = 'failed', finished_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (execution_id,),
            )
            conn.commit()
        conn.close()
        return execution_id

    models = models or get_available_models()
    if not models:
        print("No API keys set. Set at least one of OPENAI_API_KEY, ANTHROPIC_API_KEY, PERPLEXITY_API_KEY, GOOGLE_API_KEY in .env")
        if execution_id is not None:
            conn.execute(
                """UPDATE monitoring_executions SET status = 'failed', finished_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (execution_id,),
            )
            conn.commit()
        conn.close()
        return execution_id
    run_ids = {}
    for model in models:
        if execution_id is not None:
            conn.execute(
                "INSERT INTO runs (execution_id, model, status, prompt_count) VALUES (?, ?, 'running', ?)",
                (execution_id, model, len(prompts)),
            )
        else:
            conn.execute(
                "INSERT INTO runs (model, status, prompt_count) VALUES (?, 'running', ?)",
                (model, len(prompts)),
            )
        rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        run_ids[model] = rid
    conn.commit()

    def _progress(current: int, total: int, prompt_id: int, model: str) -> None:
        print(f"  Monitor: {current}/{total} (prompt_id={prompt_id}, model={model})")

    delay = 0.5 if delay_seconds is None else max(0, float(delay_seconds))
    results = run_all_prompts(prompts, models=models, delay_seconds=delay, progress_callback=_progress)
    debug_citations = os.environ.get("DEBUG_CITATIONS", "").lower() in ("1", "true", "yes")
    tracked_domains = load_tracked_domains()
    for prompt_id, _text, model, response in results:
        run_id = run_ids[model]
        if debug_citations:
            print(f"  [response] prompt_id={prompt_id} model={model} len={len(response or '')} has_http={'http' in (response or '')}")
        parsed = parse_response(prompt_id, model, response, debug=debug_citations)
        for _pid, _model, cited_domain, snippet, is_own_domain in parsed:
            conn.execute(
                "INSERT INTO citations (run_id, prompt_id, model, cited_domain, raw_snippet, is_own_domain) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, prompt_id, model, cited_domain, (snippet or "")[:500], is_own_domain),
            )
        if debug_citations and parsed:
            print(f"    [stored] {len(parsed)} citations for run_id={run_id}")

        # run_prompt_visibility: had_own_citation, brand_mentioned, competitor_only
        had_own_citation = 1 if any(is_own for (_, _, _, _, is_own) in parsed if is_own) else 0
        mentions_list = get_mentions_in_text(response or "", tracked_domains=tracked_domains)
        brand_mentioned = 1 if mentions_list else 0
        substantive = len(parsed) > 0 or (len((response or "").strip()) >= 100)
        competitor_only = 1 if (had_own_citation == 0 and brand_mentioned == 0 and substantive) else 0
        conn.execute(
            """INSERT OR REPLACE INTO run_prompt_visibility (run_id, prompt_id, had_own_citation, brand_mentioned, competitor_only)
               VALUES (?, ?, ?, ?, ?)""",
            (run_id, prompt_id, had_own_citation, brand_mentioned, competitor_only),
        )
        # run_prompt_mentions: which brand/domain was mentioned (own vs other)
        conn.execute("DELETE FROM run_prompt_mentions WHERE run_id = ? AND prompt_id = ?", (run_id, prompt_id))
        for mentioned_str, is_own in mentions_list:
            conn.execute(
                "INSERT INTO run_prompt_mentions (run_id, prompt_id, model, mentioned, is_own_domain) VALUES (?, ?, ?, ?, ?)",
                (run_id, prompt_id, model, (mentioned_str or "")[:500], 1 if is_own else 0),
            )
        # Store full LLM response for re-processing and display
        if (response or "").strip():
            conn.execute(
                """INSERT OR REPLACE INTO run_prompt_responses (run_id, prompt_id, model, response_text)
                   VALUES (?, ?, ?, ?)""",
                (run_id, prompt_id, model, (response or "").strip()),
            )
    for model in models:
        conn.execute(
            "UPDATE runs SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (run_ids[model],),
        )
    if execution_id is not None:
        conn.execute(
            """UPDATE monitoring_executions SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (execution_id,),
        )
    conn.commit()
    conn.close()
    print("Runs finished: {} queries, citations stored for run_ids {}.".format(len(results), list(run_ids.values())))
    return execution_id


if __name__ == "__main__":
    import argparse
    from src.config_loader import get_monitor_limit
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="Max prompts to run (default: from config/domains.yaml monitor.limit)")
    p.add_argument("--models", nargs="+", default=list(MODELS.keys()), choices=list(MODELS.keys()))
    args = p.parse_args()
    run(limit_prompts=args.limit, models=args.models)
