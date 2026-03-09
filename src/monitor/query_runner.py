"""Query OpenAI, Anthropic, and Perplexity with prompts; return raw responses for citation parsing."""
import os
import time
from pathlib import Path
from typing import Callable

# Optional: add project root
try:
    from src.db.connection import get_connection
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.db.connection import get_connection

from openai import OpenAI
from anthropic import Anthropic


def _extract_openai_content_and_urls(message) -> str:
    """Extract full text and any citation URLs from OpenAI message (content can be string or list of parts)."""
    content = getattr(message, "content", None)
    if content is None:
        return ""
    text_parts = []
    urls = []
    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                text_parts.append(part.get("text") or "")
                for ann in part.get("annotations") or []:
                    if isinstance(ann, dict) and ann.get("type") == "url_citation" and ann.get("url"):
                        urls.append(ann["url"])
            else:
                # SDK object with .text and/or .annotations
                if hasattr(part, "text") and part.text:
                    text_parts.append(part.text)
                if getattr(part, "annotations", None):
                    for ann in part.annotations or []:
                        if getattr(ann, "type", None) == "url_citation" and getattr(ann, "url", None):
                            urls.append(ann.url)
    text = "\n".join(p for p in text_parts if p).strip()
    if urls:
        text = text + "\n\n" + "\n".join(urls)
    return text


def query_openai(prompt: str, api_key: str | None = None) -> str:
    client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
    use_web_search = os.environ.get("OPENAI_USE_WEB_SEARCH", "").strip().lower() in ("1", "true", "yes")
    if use_web_search:
        # Web search models return url_citation annotations; use search model + web_search_options.
        model = os.environ.get("OPENAI_SEARCH_MODEL", "gpt-4o-mini-search-preview").strip() or "gpt-4o-mini-search-preview"
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "web_search_options": {"search_context_size": "medium"},
        }
    else:
        model = os.environ.get("OPENAI_MODEL", "gpt-5.4").strip() or "gpt-5.4"
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        }
    r = client.chat.completions.create(**kwargs)
    if not r.choices:
        return ""
    return _extract_openai_content_and_urls(r.choices[0].message).strip()


def query_anthropic(prompt: str, api_key: str | None = None) -> str:
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or ""
    if not api_key.strip():
        return ""
    client = Anthropic(api_key=api_key)
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"
    use_web_search = os.environ.get("ANTHROPIC_USE_WEB_SEARCH", "").strip().lower() in ("1", "true", "yes")
    kwargs = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if use_web_search:
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]
        kwargs["tool_choice"] = {"type": "any"}
    r = client.messages.create(**kwargs)
    # Collect text from all content blocks (not just the first) so we don't miss URLs in the body.
    text_parts = []
    if r.content:
        for block in r.content:
            if hasattr(block, "text") and block.text:
                text_parts.append(block.text)
    text = "\n".join(text_parts).strip()
    # Extract citation URLs from web_search_result_location so the citation parser can store them.
    urls = []
    if r.content:
        for block in r.content:
            citations = getattr(block, "citations", None) or []
            for c in citations:
                if getattr(c, "type", None) == "web_search_result_location":
                    u = getattr(c, "url", None)
                    if u and (u.startswith("http://") or u.startswith("https://")):
                        urls.append(u)
    if urls:
        text = text + "\n\n" + "\n".join(urls)
    return text


def query_perplexity(prompt: str, api_key: str | None = None) -> str:
    """Perplexity API (chat completions style). Returns empty string if key not set."""
    api_key = (api_key or os.environ.get("PERPLEXITY_API_KEY") or "").strip()
    if not api_key:
        return ""
    import httpx
    # Use "sonar" or "sonar-pro" (current API); legacy name may return 400.
    model = (os.environ.get("PERPLEXITY_MODEL") or "sonar").strip() or "sonar"
    resp = httpx.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
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
    content = (choices[0].get("message", {}).get("content") or "").strip()
    # Perplexity can return source URLs in top-level "citations" (array of strings) and/or
    # "search_results" (array of objects with "url"). Use both so we don't miss citations.
    urls = []
    citations = data.get("citations") or []
    if isinstance(citations, list):
        urls.extend(c for c in citations if isinstance(c, str) and (c.startswith("http://") or c.startswith("https://")))
    search_results = data.get("search_results") or []
    if isinstance(search_results, list):
        for item in search_results:
            if isinstance(item, dict) and item.get("url"):
                u = item["url"]
                if u.startswith("http://") or u.startswith("https://"):
                    urls.append(u)
    if urls:
        content = content + "\n\n" + "\n".join(urls)
    return content


def query_gemini(prompt: str, api_key: str | None = None) -> str:
    """Query Gemini with Google Search grounding for citations. Returns text + citation URLs for parser."""
    api_key = (api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return ""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return ""
    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    config = types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=1024,
        tools=[types.Tool(google_search=types.GoogleSearch())],
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    text = (getattr(response, "text", None) or "").strip()
    if not text and getattr(response, "candidates", None):
        cand = response.candidates[0] if response.candidates else None
        if cand and getattr(cand, "content", None) and getattr(cand.content, "parts", None):
            text = " ".join(
                getattr(p, "text", "") or ""
                for p in cand.content.parts
            ).strip()
    urls = []
    meta = getattr(response, "grounding_metadata", None)
    if not meta and getattr(response, "candidates", None) and response.candidates:
        cand = response.candidates[0]
        meta = getattr(cand, "grounding_metadata", None)
    if meta is not None:
        chunks = getattr(meta, "grounding_chunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            if web is not None:
                uri = getattr(web, "uri", None)
                if uri and isinstance(uri, str) and (uri.startswith("http://") or uri.startswith("https://")):
                    urls.append(uri)
    if urls:
        text = (text or "") + "\n\n" + "\n".join(urls)
    return text or ""


MODELS = {
    "openai": query_openai,
    "anthropic": query_anthropic,
    "perplexity": query_perplexity,
    "gemini": query_gemini,
}


def get_available_models() -> list[str]:
    """Return model names that have a non-empty API key set."""
    return [m for m in MODELS if _get_api_key(m)]


def _get_api_key(model: str, api_keys: dict | None = None) -> str:
    api_keys = api_keys or {}
    key_name = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
        "gemini": "GOOGLE_API_KEY",
    }.get(model)
    if not key_name:
        return ""
    return (api_keys.get(key_name) or os.environ.get(key_name) or "").strip()


def run_one(prompt_text: str, model: str, api_keys: dict | None = None) -> str:
    fn = MODELS.get(model)
    if not fn:
        return ""
    api_key = _get_api_key(model, api_keys)
    if not api_key and model in ("anthropic", "perplexity", "gemini"):
        return ""
    if not api_key and model == "openai":
        return ""
    return fn(prompt_text, api_key=api_key)


def run_all_prompts(
    prompts: list[tuple[int, str]],
    models: list[str] | None = None,
    delay_seconds: float = 0.5,
    progress_callback: Callable[[int, int, int, str], None] | None = None,
) -> list[tuple[int, str, str, str]]:
    """Run (prompt_id, prompt_text, model, response_text). Uses only models with API keys if models not provided.
    progress_callback(current_queries, total_queries, prompt_id, model) is called before each API call if provided.
    """
    models = models or get_available_models()
    total = len(prompts) * len(models)
    out = []
    current = 0
    for prompt_id, text in prompts:
        for model in models:
            if progress_callback is not None:
                progress_callback(current + 1, total, prompt_id, model)
            time.sleep(delay_seconds)
            try:
                response = run_one(text, model)
            except Exception as e:
                response = f"[Error: {e}]"
            out.append((prompt_id, text, model, response))
            current += 1
    return out
