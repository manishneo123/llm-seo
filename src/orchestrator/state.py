"""Persist and read orchestrator state (last run times per step)."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = Path(os.environ.get("ORCHESTRATOR_STATE_PATH", str(PROJECT_ROOT / "data" / "orchestrator_state.json")))

STEPS = ("discovery", "prompt_gen", "monitor", "brief", "content", "distribution", "weekly_report", "learning")


def _ensure_data_dir():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_state() -> dict:
    """Load state from JSON. Returns dict with 'last_run' keyed by step (ISO timestamp or None)."""
    _ensure_data_dir()
    if not STATE_PATH.exists():
        return {"last_run": {s: None for s in STEPS}}
    try:
        with open(STATE_PATH) as f:
            data = json.load(f)
        last_run = data.get("last_run") or {}
        for s in STEPS:
            if s not in last_run:
                last_run[s] = None
        return {"last_run": last_run}
    except Exception:
        return {"last_run": {s: None for s in STEPS}}


def save_state(state: dict) -> None:
    _ensure_data_dir()
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def mark_run(step: str) -> None:
    if step not in STEPS:
        return
    state = load_state()
    state["last_run"][step] = datetime.now(tz=timezone.utc).isoformat()
    save_state(state)


def get_last_run(step: str) -> datetime | None:
    state = load_state()
    raw = state["last_run"].get(step)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
