"""Use LLM to extract structured domain profile from crawled text."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PROFILE_PROMPT = """Analyze the following website content and extract a structured profile for TRUSEO (generating search prompts that could lead to citing this site).

Output valid JSON only, with these exact keys:
- "domain": the domain name (e.g. example.com)
- "category": the single best broad category (e.g. "Blockchain compliance", "AI dev tools")
- "categories": array of exactly 3 possible broad categories, ordered by relevance (first is best fit). Use short, consistent labels (e.g. "SaaS", "Developer tools", "API platform")
- "niche": short niche label (e.g. "Crypto KYC", "ML ops")
- "value_proposition": 1-2 sentences describing what the product/service offers
- "key_topics": array of 5-10 key topics or product areas (strings)
- "target_audience": short description of who the product is for
- "competitors": array of 5-15 main competitors: brand names and/or domain names (e.g. "Chainlink", "competitor.com"). Only include direct competitors in the same space.

Website content:
---
{crawled_text}
---
JSON:"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    return json.loads(text)


def extract_profile_with_openai(domain: str, crawled_text: str, api_key: str | None = None) -> dict:
    api_key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return _default_profile(domain)
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    content = PROFILE_PROMPT.format(crawled_text=crawled_text[:15000])
    model = os.environ.get("OPENAI_MODEL", "gpt-5.4").strip() or "gpt-5.4"
    r = client.chat.completions.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )
    raw = (r.choices[0].message.content or "").strip()
    try:
        data = _extract_json(raw)
        data["domain"] = domain
        data["competitors"] = list(data.get("competitors") or [])
        data["categories"] = _normalize_categories(data.get("categories"), data.get("category"))
        return data
    except json.JSONDecodeError:
        return _default_profile(domain)


def extract_profile_with_anthropic(domain: str, crawled_text: str, api_key: str | None = None) -> dict:
    api_key = (api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return _default_profile(domain)
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    content = PROFILE_PROMPT.format(crawled_text=crawled_text[:15000])
    r = client.messages.create(
        model=(os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )
    raw = (r.content[0].text if r.content else "").strip()
    try:
        data = _extract_json(raw)
        data["domain"] = domain
        data["competitors"] = list(data.get("competitors") or [])
        data["categories"] = _normalize_categories(data.get("categories"), data.get("category"))
        return data
    except json.JSONDecodeError:
        return _default_profile(domain)


def _normalize_categories(categories: list | None, primary_category: str | None = None) -> list[str]:
    """Ensure we have exactly 3 category strings; use primary_category if provided to fill or lead."""
    out = []
    if primary_category and (primary_category or "").strip():
        out.append((primary_category or "").strip())
    for c in (categories or [])[:3]:
        s = (c or "").strip() if isinstance(c, str) else str(c).strip()
        if s and s not in out:
            out.append(s)
    while len(out) < 3:
        out.append("General")
    return out[:3]


def extract_profile(domain: str, crawled_text: str) -> dict:
    """Extract profile using Anthropic if key set, else OpenAI. Fallback to default if neither."""
    if (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        return extract_profile_with_anthropic(domain, crawled_text)
    if (os.environ.get("OPENAI_API_KEY") or "").strip():
        return extract_profile_with_openai(domain, crawled_text)
    return _default_profile(domain)


def _default_profile(domain: str) -> dict:
    return {
        "domain": domain,
        "category": "Unknown",
        "categories": ["Unknown", "General", "Other"],
        "niche": "General",
        "value_proposition": "",
        "key_topics": [],
        "target_audience": "",
        "competitors": [],
    }


def get_merged_competitors() -> list[str]:
    """Load from DB first, else domain_profiles.yaml; return merged list of all competitor names/domains."""
    try:
        from src.domains_db import get_merged_competitors_from_db
        from_db = get_merged_competitors_from_db()
        if from_db:
            return from_db
    except Exception:
        pass
    from pathlib import Path
    profiles_path = Path(__file__).resolve().parents[2] / "config" / "domain_profiles.yaml"
    if not profiles_path.exists():
        return []
    try:
        import yaml
        with open(profiles_path) as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for profile in (data.values() if isinstance(data, dict) else []):
        if not isinstance(profile, dict):
            continue
        for c in profile.get("competitors") or []:
            s = (c or "").strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
    return out
