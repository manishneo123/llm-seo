"""Orchestrator: rule-based autonomous run of the LLM SEO pipeline."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from src.orchestrator.state import load_state, save_state, mark_run, get_last_run, STEPS
from src.orchestrator.queries import (
    get_prompt_count,
    get_uncited_prompt_count,
    get_pending_brief_count,
    get_approved_or_published_draft_count,
)

# Intervals (tunable)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DISCOVERY_MAX_AGE_DAYS = 7
PROMPT_GEN_MAX_AGE_DAYS = 7
MONITOR_INTERVAL_HOURS = 24
BRIEF_MAX_PENDING = 20   # run brief agent if pending briefs below this and we have uncited prompts
CONTENT_LIMIT_PER_RUN = 5
DISTRIBUTION_INTERVAL_DAYS = 7
WEEKLY_REPORT_INTERVAL_DAYS = 7
LEARNING_INTERVAL_DAYS = 7


def _should_run_discovery() -> bool:
    profiles_path = PROJECT_ROOT / "config" / "domain_profiles.yaml"
    if not profiles_path.exists():
        return True
    mtime = datetime.fromtimestamp(profiles_path.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(tz=timezone.utc) - mtime).days >= DISCOVERY_MAX_AGE_DAYS


def _should_run_prompt_gen() -> bool:
    if get_prompt_count() == 0:
        return True
    last = get_last_run("prompt_gen")
    if not last:
        return True
    return (datetime.now(tz=timezone.utc) - last).days >= PROMPT_GEN_MAX_AGE_DAYS


def _should_run_monitor() -> bool:
    if get_prompt_count() == 0:
        return False
    last = get_last_run("monitor")
    if not last:
        return True
    return (datetime.now(tz=timezone.utc) - last).total_seconds() >= MONITOR_INTERVAL_HOURS * 3600


def _should_run_brief() -> bool:
    uncited = get_uncited_prompt_count(days=7)
    pending = get_pending_brief_count()
    return uncited > 0 and pending < BRIEF_MAX_PENDING


def _should_run_content() -> bool:
    return get_pending_brief_count() > 0


def _should_run_distribution() -> bool:
    if get_approved_or_published_draft_count() == 0:
        return False
    last = get_last_run("distribution")
    if not last:
        return True
    return (datetime.now(tz=timezone.utc) - last).days >= DISTRIBUTION_INTERVAL_DAYS


def _should_run_weekly_report() -> bool:
    last = get_last_run("weekly_report")
    if not last:
        return True
    return (datetime.now(tz=timezone.utc) - last).days >= WEEKLY_REPORT_INTERVAL_DAYS


def _should_run_learning() -> bool:
    last = get_last_run("learning")
    if not last:
        return True
    return (datetime.now(tz=timezone.utc) - last).days >= LEARNING_INTERVAL_DAYS


def _run_discovery():
    from src.domain_discovery.run_discovery import run
    run()


def _run_prompt_gen():
    from src.monitor.prompt_generator import main
    main()


def _run_monitor():
    from src.monitor.run_monitor import run
    from src.config_loader import get_monitor_limit
    run(limit_prompts=get_monitor_limit())


def _run_brief():
    from src.gap_brief.run_brief_agent import run
    run(days=7, limit=10)


def _run_content():
    from src.content.run_content_agent import run
    run(limit=CONTENT_LIMIT_PER_RUN)


def _run_distribution():
    from src.distribution.run_distribution import run_distribute
    run_distribute(limit=5)


def _run_weekly_report():
    from src.distribution.run_distribution import run_weekly_report
    run_weekly_report()


def _run_learning():
    from src.learning.run_learning import run_learning_job
    run_learning_job()


def run_once(dry_run: bool = False):
    """Evaluate rules and run whichever steps are due. Optionally dry_run only prints what would run."""
    state = load_state()
    actions = []

    if _should_run_discovery():
        actions.append(("discovery", _run_discovery))
    if _should_run_prompt_gen():
        actions.append(("prompt_gen", _run_prompt_gen))
    if _should_run_monitor():
        actions.append(("monitor", _run_monitor))
    if _should_run_brief():
        actions.append(("brief", _run_brief))
    if _should_run_content():
        actions.append(("content", _run_content))
    if _should_run_distribution():
        actions.append(("distribution", _run_distribution))
    if _should_run_weekly_report():
        actions.append(("weekly_report", _run_weekly_report))
    if _should_run_learning():
        actions.append(("learning", _run_learning))

    if not actions:
        print("Orchestrator: nothing to run (all steps within interval).")
        return

    if dry_run:
        print("Orchestrator (dry run) would run:", [a[0] for a in actions])
        return

    for step_name, fn in actions:
        print(f"[Orchestrator] Running: {step_name}")
        try:
            fn()
            mark_run(step_name)
            print(f"[Orchestrator] Done: {step_name}")
        except Exception as e:
            print(f"[Orchestrator] Error in {step_name}: {e}")
            # Continue with next step; state not updated for failed step so it will retry next time


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Run LLM SEO pipeline autonomously (rule-based).")
    p.add_argument("--dry-run", action="store_true", help="Only print which steps would run.")
    args = p.parse_args()
    run_once(dry_run=args.dry_run)
