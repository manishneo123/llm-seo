"""Run Content agent: load pending briefs, run chain, generate schema, save draft to DB only."""
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
    """Insert markdown image tags into body. image_urls can be S3 URLs (https://...) or local paths -> /api/images/basename."""
    parts = body_md.split("\n\n", 1)
    intro = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    blocks = []
    for i, path in enumerate(image_urls[:5]):
        path = (path or "").strip()
        if not path:
            continue
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
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


def run(limit: int = 5):
    conn = get_connection()
    init_db(conn)

    rows = conn.execute(
        "SELECT id, topic, angle, suggested_headings, entities_to_mention, schema_to_add, image_prompts, image_urls FROM content_briefs WHERE status = 'pending' ORDER BY priority_score DESC LIMIT ?",
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
        image_urls = []
        image_prompts_json = r.get("image_prompts") if "image_prompts" in r.keys() else None
        image_urls_json = r.get("image_urls") if "image_urls" in r.keys() else None
        if image_prompts_json:
            try:
                prompts = json.loads(image_prompts_json)
                if isinstance(prompts, list) and prompts:
                    from src.content.image_gen import generate_images_for_brief
                    generated = generate_images_for_brief(brief_id, prompts[:5])
                    if generated:
                        conn.execute(
                            "UPDATE content_briefs SET image_urls = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (json.dumps(generated), brief_id),
                        )
                        conn.commit()
                        image_urls = generated
                        print("  -> generated {} images".format(len(generated)))
            except (TypeError, json.JSONDecodeError, Exception):
                pass
        if not image_urls and image_urls_json:
            try:
                image_urls = json.loads(image_urls_json)
                if not isinstance(image_urls, list):
                    image_urls = []
            except (TypeError, json.JSONDecodeError):
                image_urls = []
        if image_urls:
            body_md = _inject_images_into_markdown(body_md, topic, image_urls)
        title = topic
        slug = slugify(title)
        schema_json = generate_schema(schema_type, title, body_md, slug)
        image_urls_json = json.dumps(image_urls) if image_urls else None
        cur = conn.execute(
            """INSERT INTO drafts (brief_id, title, slug, body_md, schema_json, status, image_urls) VALUES (?, ?, ?, ?, ?, 'draft', ?)""",
            (brief_id, title, slug, body_md, schema_json, image_urls_json),
        )
        draft_id = cur.lastrowid
        conn.execute("UPDATE content_briefs SET status = 'in_progress' WHERE id = ?", (brief_id,))
        conn.commit()
        print("  -> draft {} saved to DB".format(draft_id))
    conn.close()
    print("Drafts saved to DB.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=5)
    args = p.parse_args()
    run(limit=args.limit)
