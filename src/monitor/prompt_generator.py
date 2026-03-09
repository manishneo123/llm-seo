"""Generate high-intent prompts for a niche using Claude. Stores in DB or CSV."""
import os
import sys
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

try:
    from src.learning.load_hints import get_prompt_gen_hints
except ImportError:
    def get_prompt_gen_hints() -> str:
        return ""


def load_niche_from_config() -> str:
    config_path = Path(__file__).resolve().parents[2] / "config" / "domains.yaml"
    if config_path.exists():
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return data.get("niche", "blockchain and AI")
    return os.environ.get("NICHE", "blockchain and AI")


def load_domain_profiles() -> list[tuple[str, dict]] | None:
    """Load from DB first, else config/domain_profiles.yaml. Returns list of (domain, profile_dict) or None."""
    try:
        from src.domains_db import get_domain_profiles_from_db
        from_db = get_domain_profiles_from_db()
        if from_db:
            return from_db
    except Exception:
        pass
    profiles_path = Path(__file__).resolve().parents[2] / "config" / "domain_profiles.yaml"
    if not profiles_path.exists():
        return None
    import yaml
    with open(profiles_path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return None
    return [(domain, profile) for domain, profile in data.items() if isinstance(profile, dict)]


def _context_from_profile(domain: str, profile: dict) -> str:
    """Build rich context string for prompt generation from a domain profile."""
    parts = [
        f"Domain: {domain}",
        f"Category: {profile.get('category', '')}",
        f"Niche: {profile.get('niche', '')}",
        f"Value proposition: {profile.get('value_proposition', '')}",
        f"Target audience: {profile.get('target_audience', '')}",
    ]
    topics = profile.get("key_topics") or []
    if topics:
        parts.append("Key topics: " + ", ".join(str(t) for t in topics))
    return "\n".join(p for p in parts if p.split(":", 1)[-1].strip())


_PROMPT_INSTRUCTION = """Generate exactly {count} high-intent prompts that users might ask ChatGPT, Perplexity, or Claude about the following. Each prompt should be a single line, question or search-style. Focus on topics that would lead to recommendations, comparisons, or citations (e.g. "What are the best X?", "How does Y work?", "Compare A vs B").

Context (use this to tailor prompts to this specific site/domain):
{niche}

Output ONLY one prompt per line, no numbering or bullets. No other text."""


def _niche_with_learning_hints(niche: str) -> str:
    hints = get_prompt_gen_hints()
    if not hints:
        return niche
    return niche + "\n\nLearning from past citation success (prefer these): " + hints


def _generate_prompts_anthropic(niche: str, count: int, api_key: str) -> list[str]:
    from anthropic import Anthropic
    context = _niche_with_learning_hints(niche)
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=(os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": _PROMPT_INSTRUCTION.format(niche=context, count=count)}],
    )
    text = response.content[0].text if response.content else ""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[:count]


def _generate_prompts_openai(niche: str, count: int, api_key: str) -> list[str]:
    from openai import OpenAI
    context = _niche_with_learning_hints(niche)
    client = OpenAI(api_key=api_key)
    model = os.environ.get("OPENAI_MODEL", "gpt-5.4").strip() or "gpt-5.4"
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": _PROMPT_INSTRUCTION.format(niche=context, count=count)}],
    )
    text = (response.choices[0].message.content or "").strip()
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    return lines[:count]


def generate_prompts(
    niche: str | None = None,
    count: int = 100,
    api_key: str | None = None,
) -> list[str]:
    """Generate high-intent prompts for the niche using Claude or OpenAI. Uses ANTHROPIC_API_KEY if set, else OPENAI_API_KEY. Returns [] if neither is set."""
    niche = niche or load_niche_from_config()
    anthropic_key = (api_key or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if anthropic_key:
        return _generate_prompts_anthropic(niche, count, anthropic_key)
    if openai_key:
        return _generate_prompts_openai(niche, count, openai_key)
    return []


def _existing_prompt_texts(conn) -> set[str]:
    """Return set of normalized prompt texts already in the DB (for dedup)."""
    rows = conn.execute("SELECT text FROM prompts").fetchall()
    return {str(r[0]).strip() for r in rows if r[0]}


def store_prompts_in_db(prompts: list[str], conn, niche: str | None = None) -> int:
    """Insert prompts into the prompts table, skipping any that already exist. Returns count of newly inserted."""
    niche_val = niche or load_niche_from_config()
    existing = _existing_prompt_texts(conn)
    inserted = 0
    for text in prompts:
        t = (text or "").strip()
        if not t or t in existing:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO prompts (text, niche) VALUES (?, ?)",
            (t, niche_val),
        )
        if conn.total_changes:
            inserted += 1
            existing.add(t)
    conn.commit()
    return inserted


def store_prompts_with_niches(prompts_with_niche: list[tuple[str, str]], conn) -> int:
    """Insert (text, niche) pairs into the prompts table, skipping any text that already exists. Returns count of newly inserted."""
    existing = _existing_prompt_texts(conn)
    inserted = 0
    for text, niche in prompts_with_niche:
        t = (text or "").strip()
        if not t or t in existing:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO prompts (text, niche) VALUES (?, ?)",
            (t, niche),
        )
        if conn.total_changes:
            inserted += 1
            existing.add(t)
    conn.commit()
    return inserted


def main():
    try:
        import yaml
    except ImportError:
        print("Install PyYAML for config: pip install pyyaml")
        import yaml  # noqa: F401

    from src.db.connection import get_connection, init_db  # noqa: E402
    conn = get_connection()
    init_db(conn)

    from src.config_loader import get_prompts_per_domain, get_prompt_count_total  # noqa: E402

    profiles = load_domain_profiles()
    if profiles:
        # Domain-specific: generate prompts per domain using profile context (config-driven)
        per_domain_count = get_prompts_per_domain()
        all_prompts_with_niche = []
        for domain, profile in profiles:
            context = _context_from_profile(domain, profile)
            print(f"Generating {per_domain_count} prompts for {domain}...")
            prompts = generate_prompts(niche=context, count=per_domain_count)
            for p in prompts:
                all_prompts_with_niche.append((p, f"domain:{domain}"))
        if not all_prompts_with_niche:
            print("Neither ANTHROPIC_API_KEY nor OPENAI_API_KEY set; skipping prompt generation.")
            conn.close()
            return
        print(f"Generated {len(all_prompts_with_niche)} prompts across {len(profiles)} domains.")
        inserted = store_prompts_with_niches(all_prompts_with_niche, conn)
        skipped = len(all_prompts_with_niche) - inserted
        if skipped:
            print(f"  {inserted} new, {skipped} already in DB (skipped).")
    else:
        # Fallback: single niche from config (config-driven count)
        niche = load_niche_from_config()
        total_count = get_prompt_count_total()
        print(f"Niche: {niche}")
        prompts = generate_prompts(niche=niche, count=total_count)
        if not prompts:
            print("Neither ANTHROPIC_API_KEY nor OPENAI_API_KEY set; skipping prompt generation. Set one of them or add prompts manually to DB.")
            conn.close()
            return
        print(f"Generated {len(prompts)} prompts.")
        inserted = store_prompts_in_db(prompts, conn)
        skipped = len(prompts) - inserted
        if skipped:
            print(f"  {inserted} new, {skipped} already in DB (skipped).")
    conn.close()
    print("Stored in SQLite (prompts table).")


if __name__ == "__main__":
    main()
