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


def _validate_domain_ids(conn, domain_ids: list[int], user_id: int | None) -> None:
    """Raise ValueError if any domain_id does not exist or (when user_id is set) does not belong to the user."""
    if not domain_ids:
        return
    placeholders = ",".join("?" * len(domain_ids))
    if user_id is not None:
        rows = conn.execute(
            f"SELECT id FROM domains WHERE id IN ({placeholders}) AND user_id = ?",
            (*domain_ids, user_id),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT id FROM domains WHERE id IN ({placeholders})",
            tuple(domain_ids),
        ).fetchall()
    found = {r["id"] for r in rows}
    missing = [did for did in domain_ids if did not in found]
    if missing:
        raise ValueError(
            f"One or more domain IDs do not exist or do not belong to this account: {missing}. Please use valid domain IDs from the Domains list."
        )


def _get_prompts_to_run_for_model(conn, model: str, domain_ids: list[int] | None, limit_prompts: int | None, user_id: int | None = None) -> list[tuple[int, str]]:
    """Return list of (prompt_id, text) to run for this model: prompts that have no recent
    citation/brand win for this model, or were last monitored for this model >30 days ago.
    If user_id is set, only that user's prompts.
    """
    base = "SELECT p.id, p.text FROM prompts p"
    params: list = []
    if user_id is not None:
        base += " WHERE p.user_id = ?"
        params.append(user_id)
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
            base += f" AND p.niche IN ({placeholders2})" if user_id is not None else f" WHERE p.niche IN ({placeholders2})"
            params.extend(niches)
    # Exclude prompt_ids with a recent win (citation or brand) for this model in last 30 days
    exclude = """
        SELECT DISTINCT rpv.prompt_id FROM run_prompt_visibility rpv
        JOIN runs r ON r.id = rpv.run_id
        WHERE r.model = ? AND (rpv.had_own_citation = 1 OR rpv.brand_mentioned = 1)
        AND r.started_at >= datetime('now', '-30 days')
    """
    if "WHERE" in base:
        q = f"{base} AND p.id NOT IN ({exclude}) ORDER BY p.id"
    else:
        q = f"{base} WHERE p.id NOT IN ({exclude}) ORDER BY p.id"
    params.append(model)
    if limit_prompts is not None and limit_prompts != "":
        try:
            cap = int(limit_prompts)
            if cap > 0:
                q += " LIMIT ?"
                params.append(cap)
        except (TypeError, ValueError):
            pass
    cur = conn.execute(q, params)
    rows = cur.fetchall()
    return [(r["id"], r["text"]) for r in rows]


def run(
    database_path=None,
    limit_prompts: int | None = None,
    models: list[str] | None = None,
    execution_id: int | None = None,
    trigger_type: str = "manual",
    settings_snapshot: dict | None = None,
    domain_ids: list[int] | None = None,
    delay_seconds: float | None = None,
    skip_prompts_with_recent_win: bool = True,
    user_id: int | None = None,
    use_queue: bool = False,
):
    # When using smart selection, treat None/empty limit as "no limit". Otherwise use config default.
    if not skip_prompts_with_recent_win and limit_prompts is None:
        from src.config_loader import get_monitor_limit
        limit_prompts = get_monitor_limit()
    if database_path:
        os.environ["LLM_SEO_DB_PATH"] = str(database_path)
    conn = get_connection()
    init_db(conn)

    if execution_id is None:
        if user_id is not None:
            conn.execute(
                """INSERT INTO monitoring_executions (user_id, trigger_type, status, settings_snapshot)
                   VALUES (?, ?, 'running', ?)""",
                (user_id, trigger_type, json.dumps(settings_snapshot) if settings_snapshot else None),
            )
        else:
            conn.execute(
                """INSERT INTO monitoring_executions (trigger_type, status, settings_snapshot)
                   VALUES (?, 'running', ?)""",
                (trigger_type, json.dumps(settings_snapshot) if settings_snapshot else None),
            )
        execution_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
    else:
        row = conn.execute("SELECT user_id FROM monitoring_executions WHERE id = ?", (execution_id,)).fetchone()
        if row and row["user_id"] is not None and user_id is None:
            user_id = row["user_id"]

    if domain_ids:
        _validate_domain_ids(conn, domain_ids, user_id)

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

    if skip_prompts_with_recent_win:
        # Per-model prompt lists: only run prompts without recent citation/brand or last run >30 days ago
        prompts_per_model = {m: _get_prompts_to_run_for_model(conn, m, domain_ids, limit_prompts, user_id=user_id) for m in models}
        run_ids = {}
        all_results: list[tuple[int, str, str, str]] = []
        delay = 0.5 if delay_seconds is None else max(0, float(delay_seconds))

        def _progress(current: int, total: int, prompt_id: int, model: str) -> None:
            print(f"  Monitor: {current}/{total} (prompt_id={prompt_id}, model={model})")

        for model in models:
            prompts_for_model = prompts_per_model[model]
            if execution_id is not None:
                conn.execute(
                    "INSERT INTO runs (execution_id, model, status, prompt_count) VALUES (?, ?, 'running', ?)",
                    (execution_id, model, len(prompts_for_model)),
                )
            else:
                conn.execute(
                    "INSERT INTO runs (model, status, prompt_count) VALUES (?, 'running', ?)",
                    (model, len(prompts_for_model)),
                )
            rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            run_ids[model] = rid
        conn.commit()

        total_queries = sum(len(prompts_per_model[m]) for m in models)
        if total_queries == 0:
            print("No prompts to run for any model (all have recent citation/brand or filter empty).")
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
            return execution_id

        if use_queue and execution_id is not None:
            from src.monitor.llm_task_queue import enqueue_monitor_tasks
            enqueue_monitor_tasks(conn, execution_id, run_ids, prompts_per_model)
            conn.close()
            return execution_id

        for model in models:
            prompts_for_model = prompts_per_model[model]
            if not prompts_for_model:
                conn.execute(
                    "UPDATE runs SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (run_ids[model],),
                )
                conn.commit()
                continue
            results_m = run_all_prompts(
                prompts_for_model,
                models=[model],
                delay_seconds=delay,
                progress_callback=_progress,
            )
            all_results.extend(results_m)
        results = all_results
    else:
        # Legacy: one shared prompt list for all models
        prompt_query = "SELECT id, text, niche FROM prompts"
        params = []
        if user_id is not None:
            prompt_query += " WHERE user_id = ?"
            params.append(user_id)
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
                prompt_query += f" AND niche IN ({placeholders2})" if user_id is not None else f" WHERE niche IN ({placeholders2})"
                params.extend(niches)
        prompt_query += " ORDER BY id"
        if limit_prompts is not None and limit_prompts != "":
            try:
                cap = int(limit_prompts)
                if cap > 0:
                    prompt_query += " LIMIT ?"
                    params.append(cap)
            except (TypeError, ValueError):
                params.append(9999)
                prompt_query += " LIMIT ?"
        else:
            params.append(99999)
            prompt_query += " LIMIT ?"
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

        if use_queue and execution_id is not None:
            from src.monitor.llm_task_queue import enqueue_monitor_tasks
            prompts_per_model_legacy = {m: prompts for m in models}
            enqueue_monitor_tasks(conn, execution_id, run_ids, prompts_per_model_legacy)
            conn.close()
            return execution_id

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
