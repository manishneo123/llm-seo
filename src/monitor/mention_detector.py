"""Detect brand/domain mention in LLM response text (for run_prompt_visibility.brand_mentioned)."""
import re
from pathlib import Path


# Return type: list of (mentioned_string, is_own_domain)
MentionResult = list[tuple[str, bool]]


def _norm_identity_token(value: str) -> str:
    """Normalize a brand/domain token for robust own-vs-competitor comparison."""
    s = (value or "").strip().lower()
    if not s:
        return ""
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[0].split(":", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    return s


def _identity_aliases(value: str) -> set[str]:
    """
    Return aliases for identity matching.
    Example:
      - "trustradius.com" -> {"trustradius.com", "trustradius"}
      - "Trust Radius" -> {"trust radius", "trustradius"}
    """
    base = _norm_identity_token(value)
    if not base:
        return set()
    out = {base}
    if "." in base:
        first = base.split(".", 1)[0].strip()
        if first:
            out.add(first)
    compact = re.sub(r"[^a-z0-9]+", "", base)
    if compact:
        out.add(compact)
    return out


def load_brand_names() -> list[str]:
    """Load brand_names from DB (all domains) or config/domains.yaml. Returns empty list if not set."""
    try:
        from src.domains_db import get_brand_names_from_db
        from_db = get_brand_names_from_db()
        if from_db:
            return from_db
    except Exception:
        pass
    config_path = Path(__file__).resolve().parents[2] / "config" / "domains.yaml"
    if not config_path.exists():
        return []
    try:
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        names = data.get("brand_names")
        if names is None:
            return []
        return [str(n).strip() for n in names if n and str(n).strip()]
    except Exception:
        return []


def brand_mentioned_in_text(
    response_text: str,
    tracked_domains: list[str] | None = None,
    brand_names: list[str] | None = None,
) -> bool:
    """
    Return True if the response text contains any of our brand names or tracked domain strings
    (case-insensitive substring match). Used to set run_prompt_visibility.brand_mentioned.
    """
    if not (response_text or "").strip():
        return False
    text_lower = response_text.lower()

    # Check tracked domains (with and without www.)
    if tracked_domains is None:
        from src.monitor.citation_parser import load_tracked_domains
        tracked_domains = load_tracked_domains()
    for d in tracked_domains:
        if not d:
            continue
        d_clean = d.lower().strip()
        if d_clean in text_lower:
            return True
        if d_clean.startswith("www.") and d_clean[4:] in text_lower:
            return True
        if not d_clean.startswith("www.") and ("www." + d_clean in text_lower or d_clean in text_lower):
            return True

    # Check brand names
    if brand_names is None:
        brand_names = load_brand_names()
    for name in brand_names:
        if name and name.lower() in text_lower:
            return True

    return False


def get_mentions_in_text(
    response_text: str,
    tracked_domains: list[str] | None = None,
    brand_names: list[str] | None = None,
    competitors: list[str] | None = None,
) -> MentionResult:
    """
    Return list of (mentioned_string, is_own_domain) for each brand/domain/competitor
    found in the response text (case-insensitive). is_own_domain=True for our
    tracked_domains and brand_names; False for competitors/others.
    """
    if not (response_text or "").strip():
        return []
    text_lower = response_text.lower()
    seen: set[tuple[str, bool]] = set()
    out: MentionResult = []
    own_norm: set[str] = set()

    if tracked_domains is None:
        from src.monitor.citation_parser import load_tracked_domains
        tracked_domains = load_tracked_domains()
    for d in tracked_domains:
        if not d:
            continue
        d_clean = d.lower().strip()
        own_norm.update(_identity_aliases(d_clean))
        key = (d, True)
        if key in seen:
            continue
        if d_clean in text_lower:
            seen.add(key)
            out.append((d, True))
            continue
        if d_clean.startswith("www.") and d_clean[4:] in text_lower:
            seen.add(key)
            out.append((d, True))
            continue
        if not d_clean.startswith("www.") and ("www." + d_clean in text_lower or d_clean in text_lower):
            seen.add(key)
            out.append((d, True))

    if brand_names is None:
        brand_names = load_brand_names()
    for name in brand_names:
        if not name:
            continue
        n_clean = name.strip().lower()
        own_norm.update(_identity_aliases(n_clean))
        key = (name, True)
        if key in seen:
            continue
        if name.lower() in text_lower:
            seen.add(key)
            out.append((name, True))

    if competitors is None:
        try:
            from src.domain_discovery.profile import get_merged_competitors
            competitors = get_merged_competitors()
        except Exception:
            competitors = []
    for c in competitors:
        if not c or not (c.strip()):
            continue
        c_clean = c.strip().lower()
        c_aliases = _identity_aliases(c_clean)
        # Never classify own tracked domain/brand aliases as competitor mentions.
        if any(a in own_norm for a in c_aliases):
            continue
        key = (c.strip(), False)
        if key in seen:
            continue
        if c_clean in text_lower:
            seen.add(key)
            out.append((c.strip(), False))

    return out
