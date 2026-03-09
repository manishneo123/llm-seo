"""Run distribution for approved/published drafts, then optional re-monitor and learning report."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from src.db.connection import get_connection, init_db
from src.distribution.adapters import distribute
from src.distribution.learning_loop import generate_weekly_summary


def run_distribute(limit: int = 5, base_url: str = "", channels: list[str] | None = None):
    """Post recent approved/published drafts to distribution channels."""
    base_url = base_url or os.environ.get("SITE_BASE_URL", "https://example.com")
    conn = get_connection()
    init_db(conn)
    rows = conn.execute(
        "SELECT id, title, slug, body_md FROM drafts WHERE status IN ('approved','published') ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    for r in rows:
        url = f"{base_url.rstrip('/')}/{r['slug']}" if r["slug"] else base_url
        summary = (r["body_md"] or "")[:300].replace("\n", " ")
        results = distribute(r["title"], url, summary, channels=channels or ["devto"])
        print(r["title"][:50], "->", results)
    conn.close()


def run_weekly_report():
    """Print weekly learning summary to stdout (and could write to file or API)."""
    summary = generate_weekly_summary()
    print(summary)
    return summary


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--distribute", action="store_true", help="Post to channels")
    p.add_argument("--report", action="store_true", help="Print weekly summary")
    p.add_argument("--limit", type=int, default=5)
    args = p.parse_args()
    if args.report:
        run_weekly_report()
    if args.distribute:
        run_distribute(limit=args.limit)
