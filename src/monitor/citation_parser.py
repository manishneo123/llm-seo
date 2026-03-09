"""Parse LLM response text for domain mentions (citations). Tracks both our domains and other websites."""
import re
from urllib.parse import urlparse


def load_tracked_domains() -> list[str]:
    try:
        from src.domains_db import get_tracked_domains_from_db
        from_db = get_tracked_domains_from_db()
        if from_db:
            return from_db
    except Exception:
        pass
    from pathlib import Path
    import os
    config_path = Path(__file__).resolve().parents[2] / "config" / "domains.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
            return list(data.get("tracked_domains", []))
        except Exception:
            pass
    env = os.environ.get("TRACKED_DOMAINS", "example.com")
    return [d.strip() for d in env.split(",") if d.strip()]


def normalize_domain(domain: str) -> str:
    """Lowercase and strip www. for consistent matching."""
    d = domain.lower().strip()
    if d.startswith("www."):
        d = d[4:]
    return d


def find_citations_in_text(text: str, tracked_domains: list[str] | None = None) -> list[tuple[str, str]]:
    """
    Find which tracked domains appear in text. Returns list of (cited_domain, snippet).
    Uses simple substring match and optional URL extraction.
    """
    all_citations = find_all_citations_in_text(text, tracked_domains)
    return [(d, s) for d, s, is_own in all_citations if is_own]


# Primary URL pattern (strict: host with at least one dot, path with common chars)
_URL_PATTERN = re.compile(
    r"https?://([a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z0-9][-a-zA-Z0-9]*)+)(?:/[\w./?=&%-]*)?",
    re.IGNORECASE,
)
# Fallback: match URLs with more path characters (parentheses, etc.) or no path
_URL_PATTERN_PERMISSIVE = re.compile(
    r"https?://([^/\s\]\)\"\'<>]+)(?::[0-9]+)?(?:/[^\s\]\)\"\'<>]*)?",
    re.IGNORECASE,
)


def _host_from_match(m) -> str | None:
    """Extract normalized host (no port) from regex match; group 1 is host part."""
    try:
        host = m.group(1).lower().strip()
        if ":" in host:
            host = host.split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        # Require something that looks like a host (has a dot or is common TLD)
        if host and ("." in host or host in ("localhost",)):
            return host
    except Exception:
        pass
    return None


def find_all_citations_in_text(
    text: str, tracked_domains: list[str] | None = None
) -> list[tuple[str, str, bool]]:
    """
    Find all URL citations in text (our domains and other websites).
    Returns list of (cited_domain, snippet, is_own_domain).
    """
    if not text:
        return []
    tracked = tracked_domains or load_tracked_domains()
    normalized_tracked = {normalize_domain(d): d for d in tracked}
    seen: set[str] = set()
    found: list[tuple[str, str, bool]] = []

    def add_citation(match, cited_domain: str, norm: str, snippet: str) -> None:
        if norm in seen:
            return
        is_own = False
        for t_norm, t_orig in normalized_tracked.items():
            if norm == t_norm or norm.endswith("." + t_norm):
                cited_domain = t_orig
                is_own = True
                break
        seen.add(norm)
        found.append((cited_domain, snippet, is_own))

    for m in _URL_PATTERN.finditer(text):
        try:
            host = m.group(1).lower()
            if host.startswith("www."):
                host = host[4:]
            if ":" in host:
                host = host.split(":")[0]
            cited_domain = m.group(1).split("/")[0].split(":")[0]
            snippet = text[max(0, m.start() - 30) : m.end() + 50]
            add_citation(m, cited_domain, host, snippet)
        except Exception:
            pass

    for m in _URL_PATTERN_PERMISSIVE.finditer(text):
        try:
            norm = _host_from_match(m)
            if not norm or norm in seen:
                continue
            cited_domain = m.group(1).split(":")[0]
            if cited_domain.lower().startswith("www."):
                cited_domain = cited_domain[4:]
            snippet = text[max(0, m.start() - 30) : m.end() + 50]
            add_citation(m, cited_domain, norm, snippet)
        except Exception:
            pass

    # Substring match for tracked domain names without URLs (our domain only)
    text_lower = text.lower()
    for norm, orig in normalized_tracked.items():
        if norm in text_lower and norm not in seen:
            idx = text_lower.find(norm)
            snippet = text[max(0, idx - 30) : idx + len(orig) + 50]
            found.append((orig, snippet, True))
            seen.add(norm)

    return found


def parse_response(
    prompt_id: int, model: str, response_text: str, tracked_domains: list[str] | None = None, debug: bool = False
) -> list[tuple[int, str, str, str, int]]:
    """
    Returns list of (prompt_id, model, cited_domain, raw_snippet, is_own_domain) for DB insert.
    Includes both our tracked domains and other websites cited in the response.
    """
    citations = find_all_citations_in_text(response_text, tracked_domains)
    n_own = sum(1 for _, __, is_own in citations if is_own)
    n_other = len(citations) - n_own
    print(f"    citations: prompt_id={prompt_id} model={model} response_len={len(response_text or '')} found={len(citations)} (own={n_own} other={n_other})")
    if debug:
        if citations:
            for domain, _snippet, is_own in citations[:10]:
                print(f"      -> {domain} (is_own={is_own})")
            if len(citations) > 10:
                print(f"      ... and {len(citations) - 10} more")
        elif response_text and ("http" in response_text or "www." in response_text):
            print(f"    [citations] no URL match; response snippet: {repr((response_text or '')[:300])}")
    return [(prompt_id, model, domain, snippet, 1 if is_own else 0) for domain, snippet, is_own in citations]
