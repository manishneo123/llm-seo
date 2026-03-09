"""Research what content is cited for a query (e.g. via Perplexity or web search)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def search_perplexity(query: str, api_key: str | None = None) -> str:
    """Return raw response from Perplexity for the query (includes citations/sources). Returns empty string if key not set."""
    api_key = (api_key or os.environ.get("PERPLEXITY_API_KEY") or "").strip()
    if not api_key:
        return ""
    import httpx
    resp = httpx.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.1-sonar-small-128k-online",
            "messages": [{"role": "user", "content": query}],
            "max_tokens": 1024,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        return ""
    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        return ""
    return (choices[0].get("message", {}).get("content") or "").strip()


def extract_cited_urls_from_response(response_text: str) -> list[str]:
    """Simple heuristic: find URLs in the response (Perplexity often includes source URLs)."""
    import re
    url_pattern = re.compile(r"https?://[^\s\)\]\"]+")
    return list(dict.fromkeys(url_pattern.findall(response_text)))


def research_query(query: str) -> tuple[str, list[str]]:
    """Run Perplexity for the query; return (response_text, list of URLs found)."""
    text = search_perplexity(query)
    urls = extract_cited_urls_from_response(text)
    return text, urls
