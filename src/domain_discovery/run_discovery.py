"""Run domain discovery: crawl tracked domains, extract profiles with AI; write to DB or config/domain_profiles.yaml."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import yaml

from src.monitor.citation_parser import load_tracked_domains
from src.domain_discovery.crawl import crawl_domain
from src.domain_discovery.profile import extract_profile, _normalize_categories


def _ensure_categories(categories: list | None, primary: str | None = None) -> list[str]:
    """Return exactly 3 category strings."""
    return _normalize_categories(categories, primary)


def _upsert_categories(conn, categories: list[str]) -> None:
    """Insert each category name into the categories table (ignore if exists)."""
    for name in (categories or [])[:3]:
        s = (name or "").strip()
        if s:
            conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (s,))


def run(output_path: Path | None = None):
    output_path = output_path or Path(__file__).resolve().parents[2] / "config" / "domain_profiles.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    domains = load_tracked_domains()
    if not domains:
        print("No tracked domains. Set TRACKED_DOMAINS in .env or tracked_domains in config/domains.yaml")
        return

    profiles = _run_discovery_for_domains(domains)
    with open(output_path, "w") as f:
        yaml.dump(profiles, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"Wrote {len(profiles)} profiles to {output_path}")


def _run_discovery_for_domains(domains: list[str], log=None) -> dict[str, dict]:
    """Crawl and extract profile for each domain. Returns {domain: profile_dict}."""
    if log is None:
        log = print
    profiles = {}
    for domain in domains:
        log(f"Crawling {domain}...")
        text = crawl_domain(domain)
        if not text.strip():
            log(f"  No content for {domain}; using default profile.")
            profiles[domain] = {
                "domain": domain,
                "category": "Unknown",
                "niche": "General",
                "value_proposition": "",
                "key_topics": [],
                "target_audience": "",
                "competitors": [],
            }
            continue
        log(f"  Extracting profile ({len(text)} chars)...")
        profile = extract_profile(domain, text)
        profile["key_topics"] = list(profile.get("key_topics") or [])
        profile["competitors"] = list(profile.get("competitors") or [])
        profiles[domain] = profile
    return profiles


def run_discovery_to_db(conn, user_id: int | None = None):
    """Load domains from DB, run discovery, write profiles to domain_profiles table. If user_id set, only that user's domains."""
    from src.domains_db import get_tracked_domains_from_db
    domains = get_tracked_domains_from_db(conn, user_id=user_id)
    if not domains:
        return {"ok": False, "error": "No domains in database. Add domains first.", "profiles_updated": []}
    results = []
    for domain in domains:
        if user_id is not None:
            row = conn.execute("SELECT id FROM domains WHERE domain = ? AND user_id = ?", (domain, user_id)).fetchone()
        else:
            row = conn.execute("SELECT id FROM domains WHERE domain = ?", (domain,)).fetchone()
        if not row:
            continue
        domain_id = row["id"]
        text = crawl_domain(domain)
        if not text.strip():
            profile = {
                "domain": domain,
                "category": "Unknown",
                "categories": ["Unknown", "General", "Other"],
                "niche": "General",
                "value_proposition": "",
                "key_topics": [],
                "target_audience": "",
                "competitors": [],
            }
        else:
            profile = extract_profile(domain, text)
            profile["key_topics"] = list(profile.get("key_topics") or [])
            profile["competitors"] = list(profile.get("competitors") or [])
            profile["categories"] = _ensure_categories(profile.get("categories"), profile.get("category"))
            _upsert_categories(conn, profile["categories"])
        key_topics_json = json.dumps(profile.get("key_topics") or [])
        competitors_json = json.dumps(profile.get("competitors") or [])
        categories_json = json.dumps(profile.get("categories") or [])
        conn.execute(
            """INSERT INTO domain_profiles (domain_id, category, categories, niche, value_proposition, key_topics, target_audience, competitors, discovered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(domain_id) DO UPDATE SET
                 category=excluded.category, categories=excluded.categories, niche=excluded.niche, value_proposition=excluded.value_proposition,
                 key_topics=excluded.key_topics, target_audience=excluded.target_audience, competitors=excluded.competitors,
                 discovered_at=CURRENT_TIMESTAMP""",
            (
                domain_id,
                profile.get("category") or "",
                categories_json,
                profile.get("niche") or "",
                profile.get("value_proposition") or "",
                key_topics_json,
                profile.get("target_audience") or "",
                competitors_json,
            ),
        )
        results.append(domain)
    conn.commit()
    return {"ok": True, "profiles_updated": results}


def run_discovery_for_domain(conn, domain_id: int):
    """Run discovery for a single domain by id. Returns {"ok": True, "domain": str} or {"ok": False, "error": str}."""
    row = conn.execute("SELECT id, domain FROM domains WHERE id = ?", (domain_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "Domain not found"}
    domain = row["domain"]
    text = crawl_domain(domain)
    if not text.strip():
        profile = {
            "domain": domain,
            "category": "Unknown",
            "categories": ["Unknown", "General", "Other"],
            "niche": "General",
            "value_proposition": "",
            "key_topics": [],
            "target_audience": "",
            "competitors": [],
        }
    else:
        profile = extract_profile(domain, text)
        profile["key_topics"] = list(profile.get("key_topics") or [])
        profile["competitors"] = list(profile.get("competitors") or [])
        profile["categories"] = _ensure_categories(profile.get("categories"), profile.get("category"))
        _upsert_categories(conn, profile["categories"])
    key_topics_json = json.dumps(profile.get("key_topics") or [])
    competitors_json = json.dumps(profile.get("competitors") or [])
    categories_json = json.dumps(profile.get("categories") or [])
    conn.execute(
        """INSERT INTO domain_profiles (domain_id, category, categories, niche, value_proposition, key_topics, target_audience, competitors, discovered_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(domain_id) DO UPDATE SET
             category=excluded.category, categories=excluded.categories, niche=excluded.niche, value_proposition=excluded.value_proposition,
             key_topics=excluded.key_topics, target_audience=excluded.target_audience, competitors=excluded.competitors,
             discovered_at=CURRENT_TIMESTAMP""",
        (
            domain_id,
            profile.get("category") or "",
            categories_json,
            profile.get("niche") or "",
            profile.get("value_proposition") or "",
            key_topics_json,
            profile.get("target_audience") or "",
            competitors_json,
        ),
    )
    conn.commit()
    return {"ok": True, "domain": domain}


if __name__ == "__main__":
    run()
