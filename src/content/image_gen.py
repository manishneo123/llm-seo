"""Generate images from text prompts (OpenAI DALL·E) and save to data/images."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMAGES_DIR = PROJECT_ROOT / "data" / "images"


def generate_image(
    prompt: str,
    size: str = "1024x1024",
    api_key: str | None = None,
    output_path: Path | None = None,
) -> str | None:
    """
    Generate one image via OpenAI Images API. Saves to output_path or data/images/gen_{slug}.png.
    Returns path relative to project root (e.g. data/images/brief_1_0.png) or None on failure.
    """
    key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.images.generate(
            model="dall-e-3",
            prompt=prompt[:4000],
            size=size,
            quality="standard",
            n=1,
        )
        url = resp.data[0].url
        if not url:
            return None
    except Exception:
        return None
    # Download and save
    import httpx
    r = httpx.get(url, timeout=30)
    if r.status_code != 200:
        return None
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in prompt[:40])
        output_path = IMAGES_DIR / f"gen_{slug}.png"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(r.content)
    try:
        rel = output_path.relative_to(PROJECT_ROOT)
        return str(rel)
    except ValueError:
        return str(output_path)


def generate_images_for_brief(
    brief_id: int,
    image_prompts: list[str],
    api_key: str | None = None,
) -> list[str]:
    """
    Generate images from a list of prompts; save as data/images/brief_{brief_id}_0.png, etc.
    Returns list of relative paths (or empty on failure).
    """
    if not image_prompts:
        return []
    paths = []
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for i, prompt in enumerate(image_prompts):
        out_path = IMAGES_DIR / f"brief_{brief_id}_{i}.png"
        p = generate_image(prompt, api_key=api_key, output_path=out_path)
        if p:
            paths.append(p)
    return paths
