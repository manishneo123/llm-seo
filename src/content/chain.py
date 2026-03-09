"""Multi-step prompt chain: research -> outline -> draft -> self-critique -> revise."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _anthropic_key(api_key: str | None = None) -> str:
    return (api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def step_outline(topic: str, angle: str, headings: str, api_key: str | None = None) -> str:
    if not _anthropic_key(api_key):
        return ""
    from anthropic import Anthropic
    client = Anthropic(api_key=_anthropic_key(api_key))
    r = client.messages.create(
        model=(os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""Topic: {topic}\nAngle: {angle}\nSuggested headings (use or adapt): {headings}\n\nProduce a clear article outline (H2/H3 only, one per line). Output only the outline, no intro."""
        }]
    )
    return (r.content[0].text if r.content else "").strip()


def step_draft(topic: str, outline: str, entities: str, api_key: str | None = None) -> str:
    if not _anthropic_key(api_key):
        return ""
    from anthropic import Anthropic
    client = Anthropic(api_key=_anthropic_key(api_key))
    r = client.messages.create(
        model=(os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""Write a full long-form article in Markdown. Outline to follow:\n{outline}\n\nEntities/terms to naturally mention: {entities}\n\nOutput only the article body in Markdown, no frontmatter."""
        }]
    )
    return (r.content[0].text if r.content else "").strip()


def step_critique(body_md: str, api_key: str | None = None) -> str:
    if not _anthropic_key(api_key):
        return ""
    from anthropic import Anthropic
    client = Anthropic(api_key=_anthropic_key(api_key))
    r = client.messages.create(
        model=(os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""Review this article for clarity, depth, and LLM-citation friendliness (clear definitions, structure, authority). List 3–5 specific improvements. Be concise.\n\n{body_md[:6000]}"""
        }]
    )
    return (r.content[0].text if r.content else "").strip()


def step_revise(body_md: str, critique: str, api_key: str | None = None) -> str:
    if not _anthropic_key(api_key):
        return ""
    from anthropic import Anthropic
    client = Anthropic(api_key=_anthropic_key(api_key))
    r = client.messages.create(
        model=(os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""Apply these improvements to the article. Output the revised article in Markdown only.\n\nImprovements:\n{critique}\n\nCurrent article:\n{body_md[:6000]}"""
        }]
    )
    return (r.content[0].text if r.content else "").strip()


def run_chain(topic: str, angle: str, suggested_headings: str, entities_to_mention: str, api_key: str | None = None) -> str:
    if not _anthropic_key(api_key):
        return ""
    outline = step_outline(topic, angle, suggested_headings, api_key)
    draft = step_draft(topic, outline, entities_to_mention, api_key)
    if not draft:
        return ""
    critique = step_critique(draft, api_key)
    revised = step_revise(draft, critique, api_key)
    return revised or draft
