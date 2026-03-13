"""Task-level queue for LLM calls: enqueue monitor tasks, worker processes one at a time with delay."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# Load .env when running as worker
if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    except ImportError:
        pass

# Optional project root
try:
    from src.db.connection import get_connection, init_db
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.db.connection import get_connection, init_db

from src.monitor.query_runner import run_one
from src.monitor.citation_parser import parse_response, load_tracked_domains
from src.monitor.mention_detector import get_mentions_in_text

TASK_TYPE_MONITOR_CALL = "monitor_call"


def get_queue_delay_seconds() -> float:
    """Delay between processing consecutive queue tasks (env QUEUE_DELAY_SECONDS or TRIAL_DELAY_SECONDS)."""
    v = os.environ.get("QUEUE_DELAY_SECONDS") or os.environ.get("TRIAL_DELAY_SECONDS", "3.5")
    try:
        return max(0.0, float(v))
    except (TypeError, ValueError):
        return 3.5


def enqueue_monitor_tasks(
    conn,
    execution_id: int,
    run_ids: dict[str, int],
    prompts_per_model: dict[str, list[tuple[int, str]]],
) -> int:
    """
    Enqueue one task per (prompt_id, prompt_text, model). run_ids maps model -> run_id.
    prompts_per_model maps model -> [(prompt_id, text), ...].
    Returns number of tasks enqueued.
    """
    count = 0
    for model, prompts in prompts_per_model.items():
        run_id = run_ids.get(model)
        if run_id is None:
            continue
        for prompt_id, prompt_text in prompts:
            payload = {
                "execution_id": execution_id,
                "run_id": run_id,
                "prompt_id": prompt_id,
                "prompt_text": prompt_text,
                "model": model,
            }
            conn.execute(
                """INSERT INTO llm_task_queue (type, payload, status, execution_id, run_id)
                   VALUES (?, ?, 'pending', ?, ?)""",
                (TASK_TYPE_MONITOR_CALL, json.dumps(payload), execution_id, run_id),
            )
            count += 1
    conn.commit()
    return count


def _store_single_monitor_result(conn, run_id: int, prompt_id: int, model: str, response: str) -> None:
    """Parse response and write citations, visibility, mentions, and response for one (run_id, prompt_id, model)."""
    debug = os.environ.get("DEBUG_CITATIONS", "").lower() in ("1", "true", "yes")
    tracked_domains = load_tracked_domains()
    parsed = parse_response(prompt_id, model, response or "", debug=debug)
    for _pid, _m, cited_domain, snippet, is_own_domain in parsed:
        conn.execute(
            "INSERT INTO citations (run_id, prompt_id, model, cited_domain, raw_snippet, is_own_domain) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, prompt_id, model, cited_domain, (snippet or "")[:500], is_own_domain),
        )
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
    conn.execute("DELETE FROM run_prompt_mentions WHERE run_id = ? AND prompt_id = ?", (run_id, prompt_id))
    for mentioned_str, is_own in mentions_list:
        conn.execute(
            "INSERT INTO run_prompt_mentions (run_id, prompt_id, model, mentioned, is_own_domain) VALUES (?, ?, ?, ?, ?)",
            (run_id, prompt_id, model, (mentioned_str or "")[:500], 1 if is_own else 0),
        )
    if (response or "").strip():
        conn.execute(
            """INSERT OR REPLACE INTO run_prompt_responses (run_id, prompt_id, model, response_text)
               VALUES (?, ?, ?, ?)""",
            (run_id, prompt_id, model, (response or "").strip()),
        )


def _mark_execution_finished_if_done(conn, execution_id: int) -> None:
    """If no pending or running tasks remain for this execution, mark runs and execution as finished."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM llm_task_queue WHERE execution_id = ? AND status IN ('pending', 'running')",
        (execution_id,),
    ).fetchone()
    if row and row["n"] and row["n"] > 0:
        return
    conn.execute(
        "UPDATE runs SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE execution_id = ?",
        (execution_id,),
    )
    conn.execute(
        "UPDATE monitoring_executions SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
        (execution_id,),
    )
    conn.commit()


def process_one_task(conn=None):
    """
    Pop one pending task, run the LLM call, store result, mark task done.
    If no tasks left for that execution, mark execution and runs as finished.
    Returns True if a task was processed, False if queue was empty.
    """
    if conn is None:
        conn = get_connection()
    init_db(conn)
    row = conn.execute(
        "SELECT id, type, payload FROM llm_task_queue WHERE status = 'pending' ORDER BY created_at LIMIT 1"
    ).fetchone()
    if not row:
        return False
    task_id = row["id"]
    task_type = row["type"]
    payload = json.loads(row["payload"])
    conn.execute(
        "UPDATE llm_task_queue SET status = 'running', started_at = CURRENT_TIMESTAMP WHERE id = ?",
        (task_id,),
    )
    conn.commit()
    error_message = None
    try:
        if task_type == TASK_TYPE_MONITOR_CALL:
            run_id = payload["run_id"]
            prompt_id = payload["prompt_id"]
            prompt_text = payload["prompt_text"]
            model = payload["model"]
            execution_id = payload.get("execution_id")
            try:
                response = run_one(prompt_text, model)
            except Exception as e:
                response = f"[Error: {e}]"
                error_message = str(e)
            _store_single_monitor_result(conn, run_id, prompt_id, model, response)
        else:
            error_message = f"Unknown task type: {task_type}"
    except Exception as e:
        error_message = str(e)
        execution_id = payload.get("execution_id")
        conn.execute(
            "UPDATE llm_task_queue SET status = 'failed', finished_at = CURRENT_TIMESTAMP, error_message = ? WHERE id = ?",
            (error_message, task_id),
        )
        conn.commit()
        if execution_id is not None:
            _mark_execution_finished_if_done(conn, execution_id)
        return True
    conn.execute(
        "UPDATE llm_task_queue SET status = 'done', finished_at = CURRENT_TIMESTAMP, error_message = ? WHERE id = ?",
        (error_message, task_id),
    )
    conn.commit()
    # After marking this task done, check if execution has no remaining tasks so we can mark it finished
    execution_id = payload.get("execution_id")
    if execution_id is not None:
        _mark_execution_finished_if_done(conn, execution_id)
    return True


def run_worker_loop(conn=None, delay_seconds: float | None = None, once: bool = False):
    """Loop: process one task, sleep delay_seconds, repeat. If once=True, process at most one task and return."""
    delay = delay_seconds if delay_seconds is not None else get_queue_delay_seconds()
    if conn is None:
        conn = get_connection()
    while True:
        processed = process_one_task(conn)
        if once:
            return
        if not processed:
            time.sleep(1)
            continue
        time.sleep(delay)


def get_queue_status(conn=None, execution_id: int | None = None):
    """
    Return queue stats: total and per-execution pending/done/failed counts and recent errors.
    If execution_id is set, include stats for that execution only; otherwise global.
    """
    if conn is None:
        conn = get_connection()
    init_db(conn)
    out = {"pending": 0, "running": 0, "done": 0, "failed": 0, "by_execution": {}, "recent_errors": []}
    if execution_id is not None:
        rows = conn.execute(
            """SELECT status, error_message FROM llm_task_queue WHERE execution_id = ?""",
            (execution_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT execution_id, status, error_message FROM llm_task_queue"""
        ).fetchall()
    for row in rows:
        r = dict(row)
        status = (r.get("status") or "pending").lower()
        exec_id = r.get("execution_id") if execution_id is None else execution_id
        if status == "pending":
            out["pending"] += 1
        elif status == "running":
            out["running"] += 1
        elif status == "done":
            out["done"] += 1
        elif status == "failed":
            out["failed"] += 1
            err = (r.get("error_message") or "").strip()
            if err and len(out["recent_errors"]) < 5:
                out["recent_errors"].append({"execution_id": exec_id, "error": err[:500]})
        if exec_id is not None:
            if exec_id not in out["by_execution"]:
                out["by_execution"][exec_id] = {"pending": 0, "running": 0, "done": 0, "failed": 0}
            out["by_execution"][exec_id][status] = out["by_execution"][exec_id].get(status, 0) + 1
    if execution_id is not None and execution_id in out["by_execution"]:
        out["execution"] = out["by_execution"][execution_id]
    return out


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="LLM task queue worker: process monitor_call tasks with delay.")
    p.add_argument("--once", action="store_true", help="Process one task and exit")
    p.add_argument("--delay", type=float, default=None, help="Seconds between tasks (default: QUEUE_DELAY_SECONDS or 3.5)")
    p.add_argument("--status", action="store_true", help="Print queue status (pending/done/failed) and exit")
    p.add_argument("--execution-id", type=int, default=None, help="With --status: filter by execution ID")
    args = p.parse_args()
    if args.status:
        import json
        import sys
        conn = get_connection()
        init_db(conn)
        status = get_queue_status(conn, execution_id=args.execution_id)
        print(json.dumps(status, indent=2))
        conn.close()
        sys.exit(0)
    run_worker_loop(once=args.once, delay_seconds=args.delay)
