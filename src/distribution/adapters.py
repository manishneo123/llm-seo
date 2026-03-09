"""Distribution adapters: Reddit, dev.to, etc. Post title + URL + summary."""
import os

try:
    from src.learning.load_hints import get_channel_weights
except ImportError:
    def get_channel_weights():
        return {"devto": 0.6, "reddit": 0.4}


def _channels_from_weights() -> list[str]:
    """Return channel names ordered by weight descending (e.g. ['devto', 'reddit'])."""
    w = get_channel_weights()
    return [c for c in sorted(w.keys(), key=lambda k: w.get(k, 0), reverse=True) if w.get(c, 0) > 0]


def post_reddit(title: str, url: str, summary: str, subreddit: str = "ethereum") -> bool:
    """Submit a link post to Reddit (requires PRAW or Reddit API credentials)."""
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT", "LLM-SEO-Agent/1.0")
    if not all([client_id, client_secret]):
        return False
    try:
        import httpx
        auth = httpx.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            headers={"User-Agent": user_agent},
            timeout=10,
        )
        if auth.status_code != 200:
            return False
        token = auth.json().get("access_token")
        resp = httpx.post(
            f"https://oauth.reddit.com/r/{subreddit}/api/submit",
            headers={"Authorization": f"Bearer {token}", "User-Agent": user_agent},
            data={"kind": "link", "url": url, "title": title},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False


def post_devto(title: str, url: str, summary: str, api_key: str | None = None) -> bool:
    """Create dev.to article that links to the main piece (or cross-post body)."""
    api_key = api_key or os.environ.get("DEVTO_API_KEY")
    if not api_key:
        return False
    try:
        import httpx
        body = f"{summary}\n\nRead more: {url}"
        resp = httpx.post(
            "https://dev.to/api/articles",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={"title": title, "body_markdown": body, "published": True},
            timeout=15,
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


def distribute(title: str, url: str, summary: str, channels: list[str] | None = None) -> dict[str, bool]:
    """Post to selected channels. Returns {channel: success}. Uses learning_hints channel_weights when channels is None."""
    if channels is None:
        channels = _channels_from_weights() or ["devto"]
    results = {}
    if "reddit" in channels:
        results["reddit"] = post_reddit(title, url, summary)
    if "devto" in channels:
        results["devto"] = post_devto(title, url, summary)
    return results
