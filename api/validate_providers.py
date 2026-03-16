"""Validate LLM provider API keys and models with a minimal API call. Used by Settings validation endpoint."""
from __future__ import annotations

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "perplexity": "sonar",
    "gemini": "gemini-2.0-flash",
}


def validate_openai(api_key: str, model: str | None = None) -> tuple[bool, str | None]:
    """Return (True, None) if key and model work, else (False, error_message)."""
    if not (api_key or "").strip():
        return False, "API key is required"
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key.strip())
        use_model = (model or "").strip() or DEFAULT_MODELS["openai"]
        client.chat.completions.create(
            model=use_model,
            messages=[{"role": "user", "content": "Hi"}],
            max_completion_tokens=5,
        )
        return True, None
    except Exception as e:
        msg = str(e).strip() or "Unknown error"
        if "invalid_api_key" in msg.lower() or "authentication" in msg.lower() or "401" in msg:
            return False, "Invalid API key"
        if "model" in msg.lower() or "404" in msg:
            return False, f"Model not found or invalid: {msg[:120]}"
        return False, msg[:200]


def validate_anthropic(api_key: str, model: str | None = None) -> tuple[bool, str | None]:
    if not (api_key or "").strip():
        return False, "API key is required"
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key.strip())
        use_model = (model or "").strip() or DEFAULT_MODELS["anthropic"]
        client.messages.create(
            model=use_model,
            max_output_tokens=5,
            messages=[{"role": "user", "content": "Hi"}],
        )
        return True, None
    except Exception as e:
        msg = str(e).strip() or "Unknown error"
        if "invalid_api_key" in msg.lower() or "authentication" in msg.lower() or "401" in msg:
            return False, "Invalid API key"
        if "model" in msg.lower() or "404" in msg or "not_found" in msg.lower():
            return False, f"Model not found or invalid: {msg[:120]}"
        return False, msg[:200]


def validate_perplexity(api_key: str, model: str | None = None) -> tuple[bool, str | None]:
    if not (api_key or "").strip():
        return False, "API key is required"
    try:
        import httpx
        use_model = (model or "").strip() or DEFAULT_MODELS["perplexity"]
        resp = httpx.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"},
            json={
                "model": use_model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return True, None
        body = resp.text
        if resp.status_code == 401:
            return False, "Invalid API key"
        if resp.status_code == 400 and ("model" in body.lower() or "invalid" in body.lower()):
            return False, f"Model not found or invalid: {body[:120]}"
        return False, f"API error ({resp.status_code}): {body[:150]}"
    except Exception as e:
        return False, (str(e).strip() or "Unknown error")[:200]


def validate_gemini(api_key: str, model: str | None = None) -> tuple[bool, str | None]:
    if not (api_key or "").strip():
        return False, "API key is required"
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key.strip())
        use_model = (model or "").strip() or DEFAULT_MODELS["gemini"]
        client.models.generate_content(
            model=use_model,
            contents="Hi",
            config=types.GenerateContentConfig(max_output_tokens=5),
        )
        return True, None
    except Exception as e:
        msg = str(e).strip() or "Unknown error"
        if "invalid" in msg.lower() and "key" in msg.lower() or "401" in msg or "403" in msg:
            return False, "Invalid API key"
        if "model" in msg.lower() or "404" in msg or "not found" in msg.lower():
            return False, f"Model not found or invalid: {msg[:120]}"
        return False, msg[:200]


VALIDATORS = {
    "openai": validate_openai,
    "anthropic": validate_anthropic,
    "perplexity": validate_perplexity,
    "gemini": validate_gemini,
}


def validate_provider(provider: str, api_key: str, model: str | None = None) -> tuple[bool, str | None]:
    fn = VALIDATORS.get(provider)
    if not fn:
        return False, f"Unknown provider: {provider}"
    return fn(api_key, model)
