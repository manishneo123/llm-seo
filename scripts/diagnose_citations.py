#!/usr/bin/env python3
"""
Diagnose why citations may be missing: inspect raw API responses and parser output.
Run from project root: PYTHONPATH=. python scripts/diagnose_citations.py [--prompt-id 1]
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.db.connection import get_connection, init_db
from src.monitor.query_runner import run_one, get_available_models
from src.monitor.citation_parser import parse_response, find_all_citations_in_text


def main():
    import argparse
    p = argparse.ArgumentParser(description="Inspect API responses and citation parsing")
    p.add_argument("--prompt-id", type=int, default=None, help="Use this prompt ID (default: first in DB)")
    p.add_argument("--models", nargs="+", default=None, help="Models to test (default: all available)")
    args = p.parse_args()

    conn = get_connection()
    init_db(conn)
    if args.prompt_id is not None:
        cur = conn.execute("SELECT id, text FROM prompts WHERE id = ?", (args.prompt_id,))
    else:
        cur = conn.execute("SELECT id, text FROM prompts ORDER BY id LIMIT 1")
    row = cur.fetchone()
    if not row:
        print("No prompts in DB (or given prompt_id not found). Run prompt_generator first.")
        sys.exit(1)
    prompt_id, prompt_text = row["id"], row["text"]
    conn.close()

    models = args.models or get_available_models()
    if not models:
        print("No API keys set. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, PERPLEXITY_API_KEY, and/or GOOGLE_API_KEY in .env")
        sys.exit(1)

    print(f"Using prompt_id={prompt_id}, models={models}")
    print("Prompt (first 200 chars):", repr(prompt_text[:200]) if prompt_text else "")
    print()

    for model in models:
        print(f"--- {model} ---")
        if model == "anthropic":
            use_ws = os.environ.get("ANTHROPIC_USE_WEB_SEARCH", "").strip().lower() in ("1", "true", "yes")
            print(f"  ANTHROPIC_USE_WEB_SEARCH={os.environ.get('ANTHROPIC_USE_WEB_SEARCH', '')!r} -> request includes web_search tool: {use_ws}")
        if model == "gemini":
            print("  (Gemini uses Google Search grounding; citations from grounding_metadata.grounding_chunks)")
        try:
            response = run_one(prompt_text, model)
        except Exception as e:
            print(f"  API error: {e}")
            continue
        if not response:
            print("  Empty response")
            continue
        print(f"  response length: {len(response)}")
        print(f"  'http' in response: {'http' in response}")
        print(f"  first 400 chars: {repr(response[:400])}")
        # Show what parser sees
        citations = find_all_citations_in_text(response)
        if model == "anthropic" and citations:
            print(f"  (citation URLs from response.content web_search_result_location blocks + parser)")
        if model == "gemini" and citations:
            print(f"  (citation URLs from grounding_metadata.grounding_chunks + parser)")
        print(f"  parser found {len(citations)} citations:")
        for domain, snippet, is_own in citations[:15]:
            print(f"    - {domain} (is_own={is_own}) snippet: {repr(snippet[:80])}...")
        if len(citations) > 15:
            print(f"    ... and {len(citations) - 15} more")
        print()

    # Perplexity raw response shape (one extra request to show citations/search_results)
    if "perplexity" in models and os.environ.get("PERPLEXITY_API_KEY"):
        import httpx
        print("--- Perplexity raw response (one request) ---")
        try:
            resp = httpx.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.environ.get("PERPLEXITY_MODEL", "sonar").strip() or "sonar",
                    "messages": [{"role": "user", "content": prompt_text[:500]}],
                    "max_tokens": 256,
                },
                timeout=30,
            )
            data = resp.json() if resp.status_code == 200 else {}
            print(f"  status: {resp.status_code}, response keys: {list(data.keys())}")
            c = data.get("citations")
            print(f"  citations type: {type(c).__name__}, len: {len(c) if isinstance(c, list) else 'N/A'}")
            if isinstance(c, list) and c:
                print(f"  citations[:3]: {c[:3]}")
            sr = data.get("search_results")
            print(f"  search_results type: {type(sr).__name__}, len: {len(sr) if isinstance(sr, list) else 'N/A'}")
            if isinstance(sr, list) and sr:
                for i, item in enumerate(sr[:3]):
                    print(f"  search_results[{i}]: {item}")
        except Exception as e:
            print(f"  Error: {e}")
        print()
    print("Done. If citations/search_results are empty, the model or API may not return URLs.")


if __name__ == "__main__":
    main()
