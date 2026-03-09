"""Run Content agent: load pending briefs, run chain, generate schema, save draft to DB and file."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from src.db.connection import get_connection, init_db
from src.content.chain import run_chain
from src.content.schema_gen import generate_schema
import re
import json


def _inject_images_into_markdown(body_md: str, topic: str, image_urls: list[str]) -> str:
    """Insert markdown image tags into body. image_urls are paths like data/images/brief_1_0.png -> /api/images/brief_1_0.png."""
    parts = body_md.split("\n\n", 1)
    intro = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    blocks = []
    for i, path in enumerate(image_urls[:5]):
        path = (path or "").strip()
        if not path:
            continue
        basename = path.replace("\\", "/").split("/")[-1]
        url = f"/api/images/{basename}"
        alt = topic[:80] if i == 0 else f"{topic[:50]} image {i + 1}"
        blocks.append(f"![{alt}]({url})")
    if not blocks:
        return body_md
    img_block = "\n\n" + "\n\n".join(blocks) + "\n\n"
    return intro + img_block + rest


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def run(limit: int = 5, output_dir: Path | None = None):
    output_dir = output_dir or Path(__file__).resolve().parents[2] / "drafts"
    output_dir.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    init_db(conn)

    rows = conn.execute(
        "SELECT id, topic, angle, suggested_headings, entities_to_mention, schema_to_add, image_urls FROM content_briefs WHERE status = 'pending' ORDER BY priority_score DESC LIMIT ?",
        (limit,),
    ).fetchall()
    if not rows:
        print("No pending briefs.")
        conn.close()
        return

    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        print("ANTHROPIC_API_KEY not set; skipping content generation. Set the key to generate drafts from briefs.")
        conn.close()
        return

    for r in rows:
        brief_id = r["id"]
        topic = r["topic"] or ""
        angle = r["angle"] or ""
        headings = r["suggested_headings"] or ""
        entities = r["entities_to_mention"] or ""
        schema_type = r["schema_to_add"] or "Article"
        print("Drafting:", topic[:60])
        body_md = run_chain(topic, angle, headings, entities)
        if not (body_md or "").strip():
            print("  -> skipped (no content generated)")
            continue
        image_urls_json = r["image_urls"] if "image_urls" in r.keys() else None
        if image_urls_json:
            try:
                image_urls = json.loads(image_urls_json)
                if isinstance(image_urls, list) and image_urls:
                    body_md = _inject_images_into_markdown(body_md, topic, image_urls)
            except (TypeError, json.JSONDecodeError):
                pass
        title = topic
        slug = slugify(title)
        schema_json = generate_schema(schema_type, title, body_md, slug)
        cur = conn.execute(
            """INSERT INTO drafts (brief_id, title, slug, body_md, schema_json, status) VALUES (?, ?, ?, ?, ?, 'draft')""",
            (brief_id, title, slug, body_md, schema_json),
        )
        draft_id = cur.lastrowid
        conn.execute("UPDATE content_briefs SET status = 'in_progress' WHERE id = ?", (brief_id,))
        conn.commit()
        (output_dir / f"draft_{draft_id}.md").write_text(f"# {title}\n\n{body_md}", encoding="utf-8")
        print("  -> draft_{}.md".format(draft_id))
    conn.close()
    print("Drafts saved to DB and", output_dir)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=5)
    args = p.parse_args()
    run(limit=args.limit)
