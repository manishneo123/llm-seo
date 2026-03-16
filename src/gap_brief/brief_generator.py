"""Generate content briefs from uncited prompts + research using Claude."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from src.learning.load_hints import get_brief_gen_system_extra
except ImportError:
    def get_brief_gen_system_extra() -> str:
        return ""


def generate_brief(
    prompt_text: str,
    research_response: str,
    cited_urls: list[str],
    api_key: str | None = None,
) -> dict:
    """
    Use Claude to produce a structured content brief.
    Returns dict: topic, angle, required_depth, suggested_headings, entities_to_mention, schema_to_add, priority_score.
    If ANTHROPIC_API_KEY is not set, returns a minimal brief from the prompt text.
    """
    api_key = (api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return {
            "topic": prompt_text[:100] if prompt_text else "Untitled",
            "angle": "",
            "required_depth": "medium",
            "suggested_headings": "",
            "entities_to_mention": "",
            "schema_to_add": "Article",
            "priority_score": 5,
            "image_prompts": [],
        }
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    urls_blob = "\n".join(cited_urls[:15]) if cited_urls else "No URLs extracted."
    brief_extra = get_brief_gen_system_extra()
    system_extra = "\n\nAdditional guidance from past performance (prefer these): " + brief_extra if brief_extra else ""
    response = client.messages.create(
        model=(os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6",
        max_output_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""The following user query currently does NOT cite our site. We want to create content that could be cited for this query.

User query: {prompt_text}

What competitors/sources are being cited (from the research response and URLs below)?
Research response (excerpt): {research_response[:2000]}
URLs mentioned: {urls_blob}

Produce a content brief for a new article that could win this citation. Output valid JSON only, with these keys:
- "topic": string (clear topic title)
- "angle": string (unique angle or positioning)
- "required_depth": string (how deep the article should go)
- "suggested_headings": string (comma-separated or newline list of H2/H3 headings)
- "entities_to_mention": string (key entities, terms, or brands to mention)
- "schema_to_add": string (e.g. FAQ, Article, HowTo)
- "priority_score": number 1-10 (10 = high citation opportunity)
- "image_prompts": array of 1-3 strings: short image prompts for AI image generation (e.g. "Professional hero image of ...", "Diagram showing ..."). Each will be used to generate a blog image.
{system_extra}
"""
        }]
    )
    text = response.content[0].text if response.content else "{}"
    # Strip markdown code block if present
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {"topic": prompt_text[:100], "angle": "", "required_depth": "medium", "suggested_headings": "", "entities_to_mention": "", "schema_to_add": "Article", "priority_score": 5, "image_prompts": []}
    if "image_prompts" not in data or not isinstance(data["image_prompts"], list):
        data["image_prompts"] = []
    data["image_prompts"] = [str(p).strip() for p in data["image_prompts"][:5] if p]
    return data


def store_brief_in_db(prompt_id: int, brief: dict, conn) -> int:
    """Insert into content_briefs; return brief id. image_prompts stored as JSON array. user_id from prompt."""
    row = conn.execute("SELECT user_id FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
    user_id = row["user_id"] if row and row["user_id"] is not None else 1
    image_prompts = brief.get("image_prompts") or []
    image_prompts_json = json.dumps(image_prompts) if image_prompts else None
    cur = conn.execute(
        """INSERT INTO content_briefs (user_id, prompt_id, topic, angle, priority_score, suggested_headings, entities_to_mention, schema_to_add, image_prompts, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
        (
            user_id,
            prompt_id,
            brief.get("topic", ""),
            brief.get("angle", ""),
            float(brief.get("priority_score", 5)),
            brief.get("suggested_headings", ""),
            brief.get("entities_to_mention", ""),
            brief.get("schema_to_add", "Article"),
            image_prompts_json,
        ),
    )
    conn.commit()
    return cur.lastrowid
