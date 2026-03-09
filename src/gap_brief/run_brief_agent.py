"""Run Gap & Brief agent: load uncited prompts, research, generate briefs, store in DB and Markdown."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from src.db.connection import get_connection, init_db
from src.gap_brief.uncited_prompts import get_uncited_prompts
from src.gap_brief.research import research_query
from src.gap_brief.brief_generator import generate_brief, store_brief_in_db


def run(days: int = 7, limit: int = 10, output_dir: Path | None = None):
    output_dir = output_dir or Path(__file__).resolve().parents[2] / "briefs"
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    init_db(conn)

    prompts = get_uncited_prompts(days=days, limit=limit)
    if not prompts:
        print("No uncited prompts in the last {} days.".format(days))
        conn.close()
        return

    print("Processing {} uncited prompts...".format(len(prompts)))
    for prompt_id, text in prompts:
        research_response, cited_urls = research_query(text)
        brief = generate_brief(text, research_response, cited_urls)
        bid = store_brief_in_db(prompt_id, brief, conn)
        # Write Markdown to briefs/
        md = f"""# {brief.get('topic', 'Untitled')}
Prompt ID: {prompt_id}
Priority: {brief.get('priority_score', 5)}

## Angle
{brief.get('angle', '')}

## Required depth
{brief.get('required_depth', '')}

## Suggested headings
{brief.get('suggested_headings', '')}

## Entities to mention
{brief.get('entities_to_mention', '')}

## Schema to add
{brief.get('schema_to_add', '')}
"""
        (output_dir / f"brief_{bid}.md").write_text(md, encoding="utf-8")
        print("Brief {} created for prompt {}: {}".format(bid, prompt_id, brief.get("topic", "")[:50]))

    conn.close()
    print("Done. Briefs in DB and in {}.".format(output_dir))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--limit", type=int, default=10)
    args = p.parse_args()
    run(days=args.days, limit=args.limit)
