"""Crawl domain pages and extract plain text for AI profile extraction."""
import re
import sys
from pathlib import Path

# Project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx

# Max bytes to read per page
MAX_PAGE_BYTES = 100 * 1024
# Max total chars per domain to send to LLM
MAX_TEXT_PER_DOMAIN = 20_000
# Timeout per request
REQUEST_TIMEOUT = 15.0

# Key paths to try per domain (after /)
KEY_PATHS = ["", "/about", "/product", "/features", "/solutions", "/use-cases"]


def _strip_html(html: str) -> str:
    """Remove script/style, then tags; collapse whitespace."""
    if not html:
        return ""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_domain(domain: str) -> str:
    d = domain.strip().lower()
    if not d.startswith("http"):
        d = "https://" + d
    return d.rstrip("/")


def check_domain_reachable(domain: str) -> tuple[bool, str]:
    """
    Verify that the domain exists and is reachable (e.g. responds to HTTP).
    Returns (True, "") if reachable, (False, "error message") if not.
    Tries HTTPS first, then HTTP. Any response (2xx, 3xx, 4xx, 5xx) counts as reachable.
    """
    base = _normalize_domain(domain)
    if not base.startswith("https://"):
        base = "https://" + base
    urls_to_try = [base]
    if base.startswith("https://"):
        urls_to_try.append("http://" + base.replace("https://", "", 1))
    last_error = "Domain does not exist or is not reachable. Please check the URL and try again."
    for url in urls_to_try:
        try:
            with httpx.Client(follow_redirects=True, timeout=REQUEST_TIMEOUT) as client:
                client.get(url)
                return True, ""
        except httpx.ConnectError:
            # DNS failure, connection refused, etc. — use a friendly message
            last_error = "Domain does not exist or could not be found. Please check the URL and try again."
        except httpx.TimeoutException:
            last_error = "Domain did not respond in time. Please try again later."
        except httpx.RequestError:
            last_error = "Could not reach the website. Please check the URL and try again."
    return False, last_error


def fetch_page(url: str) -> str:
    """Fetch URL and return plain text; empty string on failure."""
    try:
        with httpx.Client(follow_redirects=True, timeout=REQUEST_TIMEOUT) as client:
            resp = client.get(url)
            resp.raise_for_status()
            body = resp.content[:MAX_PAGE_BYTES].decode("utf-8", errors="replace")
            return _strip_html(body)
    except Exception:
        return ""


def crawl_domain(domain: str) -> str:
    """
    Crawl homepage and a few key paths for the domain. Returns concatenated plain text
    labeled by page, truncated to MAX_TEXT_PER_DOMAIN chars.
    """
    base = _normalize_domain(domain)
    if not base.startswith("https://"):
        base = "https://" + base
    parts = []
    total = 0
    for path in KEY_PATHS:
        url = base if path == "" else (base + path)
        text = fetch_page(url)
        if text:
            label = "Homepage" if path == "" else path.strip("/").replace("-", " ").title()
            block = f"[{label}]\n{text}\n\n"
            if total + len(block) > MAX_TEXT_PER_DOMAIN:
                block = block[: MAX_TEXT_PER_DOMAIN - total]
                parts.append(block)
                break
            parts.append(block)
            total += len(block)
        if total >= MAX_TEXT_PER_DOMAIN:
            break
    return "".join(parts).strip() if parts else ""
