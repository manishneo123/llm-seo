"""CMS adapters: WordPress, Webflow, Ghost, Hashnode. Publish approved draft."""
import os


def publish_ghost(title: str, body_html: str, slug: str | None = None) -> bool:
    """Publish to Ghost via Admin API. Requires GHOST_URL and GHOST_ADMIN_API_KEY."""
    url = (os.environ.get("GHOST_URL") or "").rstrip("/")
    key = (os.environ.get("GHOST_ADMIN_API_KEY") or "").strip()
    if not url or not key:
        return False
    import httpx
    payload = {
        "posts": [{
            "title": title,
            "html": body_html,
            "status": "published",
        }]
    }
    if slug:
        payload["posts"][0]["slug"] = slug
    resp = httpx.post(
        f"{url}/ghost/api/admin/posts/?source=html",
        headers={"Authorization": f"Ghost {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    return resp.status_code in (200, 201)


def publish_hashnode(title: str, body_html: str, slug: str | None = None) -> bool:
    """Publish to Hashnode via GraphQL (publishPost). Uses markdown; converts HTML to markdown roughly if needed."""
    api_key = (os.environ.get("HASHNODE_API_KEY") or "").strip()
    publication_id = (os.environ.get("HASHNODE_PUBLICATION_ID") or "").strip()
    if not api_key or not publication_id:
        return False
    import httpx
    # Hashnode expects contentMarkdown; we have HTML so strip tags for a simple fallback
    content_md = body_html
    try:
        import re
        content_md = re.sub(r"<[^>]+>", "\n", body_html).strip()
        content_md = re.sub(r"\n{3,}", "\n\n", content_md)
    except Exception:
        pass
    query = """
    mutation PublishPost($input: PublishPostInput!) {
      publishPost(input: $input) {
        post { id slug url }
      }
    }
    """
    variables = {
        "input": {
            "title": title,
            "publicationId": publication_id,
            "contentMarkdown": content_md[:100_000],
        }
    }
    if slug:
        variables["input"]["slug"] = slug
    resp = httpx.post(
        "https://gql.hashnode.com/",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"query": query, "variables": variables},
        timeout=30,
    )
    if resp.status_code != 200:
        return False
    data = resp.json()
    return "data" in data and data.get("data", {}).get("publishPost", {}).get("post") is not None


def publish_wordpress(title: str, body_html: str, slug: str | None = None) -> bool:
    url = os.environ.get("WORDPRESS_URL", "").rstrip("/")
    app_password = os.environ.get("WORDPRESS_APP_PASSWORD")
    if not url or not app_password:
        return False
    import httpx
    import base64
    auth = base64.b64encode(f":{app_password}".encode()).decode()
    resp = httpx.post(
        f"{url}/wp-json/wp/v2/posts",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json={"title": title, "content": body_html, "status": "publish", "slug": slug or None},
        timeout=30,
    )
    return resp.status_code in (200, 201)


def publish_webflow(title: str, body_html: str, slug: str | None = None) -> bool:
    token = os.environ.get("WEBFLOW_API_TOKEN")
    collection_id = os.environ.get("WEBFLOW_COLLECTION_ID")
    if not token or not collection_id:
        return False
    import httpx
    resp = httpx.post(
        f"https://api.webflow.com/v2/collections/{collection_id}/items",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"fieldData": {"name": title, "slug": slug or slug or title.lower().replace(" ", "-"), "post-body": body_html}},
        timeout=30,
    )
    return resp.status_code in (200, 201)


def publish_draft(
    draft_id: int,
    body_html: str,
    title: str,
    slug: str,
    destination: str | None = None,
) -> bool:
    """Publish to the given CMS. If destination is None, use first configured: wordpress, webflow, ghost, hashnode."""
    if destination:
        dest = destination.lower()
        if dest == "wordpress":
            return publish_wordpress(title, body_html, slug)
        if dest == "webflow":
            return publish_webflow(title, body_html, slug)
        if dest == "ghost":
            return publish_ghost(title, body_html, slug)
        if dest == "hashnode":
            return publish_hashnode(title, body_html, slug)
        return False
    if os.environ.get("WORDPRESS_URL"):
        return publish_wordpress(title, body_html, slug)
    if os.environ.get("WEBFLOW_API_TOKEN"):
        return publish_webflow(title, body_html, slug)
    if os.environ.get("GHOST_URL") and os.environ.get("GHOST_ADMIN_API_KEY"):
        return publish_ghost(title, body_html, slug)
    if os.environ.get("HASHNODE_API_KEY") and os.environ.get("HASHNODE_PUBLICATION_ID"):
        return publish_hashnode(title, body_html, slug)
    return False
