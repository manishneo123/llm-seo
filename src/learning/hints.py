"""Call LLM to turn success summary into structured hints (prompt_gen, brief_gen, channel_weights)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_HINTS_PROMPT = """You are analyzing outcomes from an LLM-SEO pipeline: we monitor which prompts get our domain cited and our brand name mentioned, create content briefs, publish drafts, and measure citation uplift and brand-mention uplift (when published content led to more citations or brand mentions).

Data summary:
{summary}

Produce exactly one JSON object with these keys (all strings except channel_weights):
- "prompt_gen_hints": 2-4 sentences telling the prompt generator what topics or question styles led to more citations and/or brand mentions. Consider both citation_delta and brand_delta when present. If data is sparse, give generic best-practice hints.
- "brief_gen_system_extra": 2-4 sentences to add to the brief generator so it prefers structure/schema/angles that led to citation or brand uplift. Prefer prompt styles and brief structures that coincided with positive brand uplift when that data exists. If no uplift data, give generic advice.
- "channel_weights": object with keys "devto" and "reddit" and number values (e.g. 0.7 and 0.3) that sum to 1.0, indicating preferred distribution. If unclear, use {"devto": 0.6, "reddit": 0.4}.

Output ONLY valid JSON, no markdown or extra text."""


def _get_api_key() -> str:
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if key:
        return key
    return (os.environ.get("OPENAI_API_KEY") or "").strip()


def generate_hints_with_anthropic(summary: str, api_key: str) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=(os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6",
        max_output_tokens=1024,
        messages=[{"role": "user", "content": _HINTS_PROMPT.format(summary=summary)}],
    )
    text = response.content[0].text if response.content else ""
    return _parse_hints_json(text)


def generate_hints_with_openai(summary: str, api_key: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    model = os.environ.get("OPENAI_MODEL", "gpt-5.4").strip() or "gpt-5.4"
    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=1024,
        messages=[{"role": "user", "content": _HINTS_PROMPT.format(summary=summary)}],
    )
    text = (response.choices[0].message.content or "").strip()
    return _parse_hints_json(text)


def _parse_hints_json(raw: str) -> dict:
    raw = raw.strip()
    for start in ("```json", "```"):
        if raw.startswith(start):
            raw = raw[len(start):].strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _default_hints()
    if not isinstance(data, dict):
        return _default_hints()
    return {
        "prompt_gen_hints": data.get("prompt_gen_hints") or "",
        "brief_gen_system_extra": data.get("brief_gen_system_extra") or "",
        "channel_weights": data.get("channel_weights") if isinstance(data.get("channel_weights"), dict) else {"devto": 0.6, "reddit": 0.4},
    }


def _default_hints() -> dict:
    return {
        "prompt_gen_hints": "",
        "brief_gen_system_extra": "",
        "channel_weights": {"devto": 0.6, "reddit": 0.4},
    }


def generate_hints(summary: str) -> dict:
    """Generate structured hints from summary. Uses Anthropic if available, else OpenAI. Else returns defaults."""
    anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not anthropic_key and not openai_key:
        return _default_hints()
    try:
        if anthropic_key:
            return generate_hints_with_anthropic(summary, anthropic_key)
        return generate_hints_with_openai(summary, openai_key)
    except Exception:
        return _default_hints()
