"""CMS adapters: WordPress, Webflow, Ghost, Hashnode. Publish approved draft.
   All publish_* functions return (success: bool, published_url: str | None, error_message: str | None).
   validate_* functions return (success: bool, message: str) for credential checks."""
import os
import re


def _ghost_post_url(ghost_url: str, resp_json: dict) -> str | None:
    """Extract canonical URL of the created post from Ghost API response."""
    try:
        posts = resp_json.get("posts") or []
        if posts and isinstance(posts[0], dict):
            u = (posts[0].get("url") or posts[0].get("canonical_url") or "").strip()
            if u:
                return u
            # Ghost sometimes returns relative path
            path = (posts[0].get("url") or "").strip() or (posts[0].get("slug") and f"/{posts[0]['slug']}/") or ""
            if path:
                return (ghost_url.rstrip("/") + path) if not path.startswith("http") else path
    except Exception:
        pass
    return None


def publish_ghost(
    title: str,
    body_html: str,
    slug: str | None = None,
    config: dict | None = None,
) -> tuple[bool, str | None, str | None]:
    """Publish to Ghost via Admin API. Returns (success, post_url, error_message). config: url, admin_api_key."""
    if config and isinstance(config, dict):
        url = (config.get("url") or "").strip().rstrip("/")
        key = (config.get("admin_api_key") or "").strip()
    else:
        url = (os.environ.get("GHOST_URL") or "").rstrip("/")
        key = (os.environ.get("GHOST_ADMIN_API_KEY") or "").strip()
    if not url or not key:
        return (False, None, "Set Ghost URL and Admin API key (in content source config or GHOST_URL and GHOST_ADMIN_API_KEY in .env)")
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
    if resp.status_code not in (200, 201):
        return (False, None, f"Ghost API: {resp.status_code} {resp.text[:200] if resp.text else ''}")
    try:
        post_url = _ghost_post_url(url, resp.json())
        return (True, post_url, None)
    except Exception:
        return (True, None, None)


def validate_ghost(config: dict | None = None) -> tuple[bool, str]:
    """Verify Ghost URL and Admin API key. Returns (success, message)."""
    if config and isinstance(config, dict):
        url = (config.get("url") or "").strip().rstrip("/")
        key = (config.get("admin_api_key") or "").strip()
    else:
        url = (os.environ.get("GHOST_URL") or "").rstrip("/")
        key = (os.environ.get("GHOST_ADMIN_API_KEY") or "").strip()
    if not url or not key:
        return (False, "Ghost URL and Admin API key are required")
    try:
        import httpx
        resp = httpx.get(
            f"{url}/ghost/api/admin/site/",
            headers={"Authorization": f"Ghost {key}", "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code == 200:
            return (True, "Ghost credentials are valid")
        return (False, f"Ghost API: {resp.status_code} — {resp.text[:200] if resp.text else 'Invalid key or URL'}")
    except Exception as e:
        return (False, str(e))


def publish_hashnode(
    title: str,
    body_html: str,
    slug: str | None = None,
    config: dict | None = None,
    content_md: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """Publish to Hashnode via GraphQL (publishPost). If content_md is provided, use it for contentMarkdown (keeps images); else strip body_html."""
    if config and isinstance(config, dict):
        api_key = (config.get("api_key") or "").strip()
        publication_id = (config.get("publication_id") or "").strip()
    else:
        api_key = (os.environ.get("HASHNODE_API_KEY") or "").strip()
        publication_id = (os.environ.get("HASHNODE_PUBLICATION_ID") or "").strip()
    if not api_key or not publication_id:
        return (False, None, "Set API key and Publication ID (in content source config or HASHNODE_* in .env). Get token at hashnode.com/settings/developer")
    import httpx
    if content_md is not None and content_md.strip():
        use_content_md = content_md.strip()
    else:
        use_content_md = body_html
        try:
            use_content_md = re.sub(r"<[^>]+>", "\n", body_html).strip()
            use_content_md = re.sub(r"\n{3,}", "\n\n", use_content_md)
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
            "contentMarkdown": use_content_md[:100_000],
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
        return (False, None, f"Hashnode API: HTTP {resp.status_code} — {resp.text[:300] if resp.text else 'No response body'}")
    try:
        data = resp.json()
        errors = data.get("errors") or []
        if errors:
            msgs = [e.get("message", str(e)) for e in errors if isinstance(e, dict)]
            return (False, None, "Hashnode: " + (msgs[0] if msgs else str(errors)[:200]))
        post = (data.get("data") or {}).get("publishPost", {}).get("post")
        if not post:
            return (False, None, "Hashnode: no post in response. Check publication ID and API token.")
        post_url = (post.get("url") or "").strip() if isinstance(post, dict) else None
        return (True, post_url or None, None)
    except Exception as e:
        return (False, None, f"Hashnode: {e!s}")


def validate_hashnode(config: dict | None = None) -> tuple[bool, str]:
    """Verify Hashnode API key and publication access. Returns (success, message)."""
    if config and isinstance(config, dict):
        api_key = (config.get("api_key") or "").strip()
        publication_id = (config.get("publication_id") or "").strip()
    else:
        api_key = (os.environ.get("HASHNODE_API_KEY") or "").strip()
        publication_id = (os.environ.get("HASHNODE_PUBLICATION_ID") or "").strip()
    if not api_key:
        return (False, "API key is required")
    try:
        import httpx
        # Verify token with me query
        resp = httpx.post(
            "https://gql.hashnode.com/",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"query": "query { me { id username } }"},
            timeout=15,
        )
        if resp.status_code != 200:
            return (False, f"Hashnode API: HTTP {resp.status_code}")
        data = resp.json()
        if data.get("errors"):
            msgs = [e.get("message", str(e)) for e in data["errors"] if isinstance(e, dict)]
            return (False, msgs[0] if msgs else "Invalid API key")
        if not publication_id:
            return (True, "API key is valid (no publication ID to verify)")
        # Verify publication access
        resp2 = httpx.post(
            "https://gql.hashnode.com/",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "query": "query($id: String!) { publication(id: $id) { id title } }",
                "variables": {"id": publication_id},
            },
            timeout=15,
        )
        if resp2.status_code != 200:
            return (False, f"Publication check: HTTP {resp2.status_code}")
        data2 = resp2.json()
        if data2.get("errors"):
            return (False, "Publication ID not found or access denied")
        pub = (data2.get("data") or {}).get("publication")
        if not pub:
            return (False, "Publication ID not found or access denied")
        return (True, f"Credentials valid for publication: {pub.get('title', publication_id)}")
    except Exception as e:
        return (False, str(e))


def publish_wordpress(
    title: str,
    body_html: str,
    slug: str | None = None,
    config: dict | None = None,
) -> tuple[bool, str | None, str | None]:
    """Publish to WordPress via REST API. Returns (success, post_url, error_message). config: url, app_password."""
    if config and isinstance(config, dict):
        url = (config.get("url") or "").strip().rstrip("/")
        app_password = config.get("app_password") or ""
    else:
        url = os.environ.get("WORDPRESS_URL", "").rstrip("/")
        app_password = os.environ.get("WORDPRESS_APP_PASSWORD") or ""
    if not url or not app_password:
        return (False, None, "Set WordPress URL and App password (in content source config or WORDPRESS_* in .env)")
    import httpx
    import base64
    auth = base64.b64encode(f":{app_password}".encode()).decode()
    resp = httpx.post(
        f"{url}/wp-json/wp/v2/posts",
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        json={"title": title, "content": body_html, "status": "publish", "slug": slug or None},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        return (False, None, f"WordPress API: {resp.status_code} — {resp.text[:200] if resp.text else ''}")
    try:
        j = resp.json()
        link = (j.get("link") or "").strip() if isinstance(j, dict) else None
        return (True, link or None, None)
    except Exception:
        return (True, None, None)


def validate_wordpress(config: dict | None = None) -> tuple[bool, str]:
    """Verify WordPress URL and application password. Returns (success, message)."""
    if config and isinstance(config, dict):
        url = (config.get("url") or "").strip().rstrip("/")
        app_password = config.get("app_password") or ""
    else:
        url = os.environ.get("WORDPRESS_URL", "").rstrip("/")
        app_password = os.environ.get("WORDPRESS_APP_PASSWORD") or ""
    if not url or not app_password:
        return (False, "WordPress URL and application password are required")
    try:
        import httpx
        import base64
        auth = base64.b64encode(f":{app_password}".encode()).decode()
        resp = httpx.get(
            f"{url}/wp-json/wp/v2/users/me",
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code == 200:
            j = resp.json()
            name = j.get("name") or j.get("slug") or "User"
            return (True, f"Credentials valid (logged in as {name})")
        return (False, f"WordPress API: {resp.status_code} — {resp.text[:200] if resp.text else 'Invalid URL or password'}")
    except Exception as e:
        return (False, str(e))


def publish_webflow(
    title: str,
    body_html: str,
    slug: str | None = None,
    config: dict | None = None,
) -> tuple[bool, str | None, str | None]:
    """Publish to Webflow CMS collection. Returns (success, item_url, error_message). config: api_token, collection_id."""
    if config and isinstance(config, dict):
        token = (config.get("api_token") or "").strip()
        collection_id = (config.get("collection_id") or "").strip()
    else:
        token = (os.environ.get("WEBFLOW_API_TOKEN") or "").strip()
        collection_id = (os.environ.get("WEBFLOW_COLLECTION_ID") or "").strip()
    if not token or not collection_id:
        return (False, None, "Set API token and Collection ID (in content source config or WEBFLOW_* in .env)")
    import httpx
    resp = httpx.post(
        f"https://api.webflow.com/v2/collections/{collection_id}/items",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"fieldData": {"name": title, "slug": slug or title.lower().replace(" ", "-"), "post-body": body_html}},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        return (False, None, f"Webflow API: {resp.status_code} — {resp.text[:200] if resp.text else ''}")
    return (True, None, None)


def validate_webflow(config: dict | None = None) -> tuple[bool, str]:
    """Verify Webflow API token and collection access. Returns (success, message)."""
    if config and isinstance(config, dict):
        token = (config.get("api_token") or "").strip()
        collection_id = (config.get("collection_id") or "").strip()
    else:
        token = (os.environ.get("WEBFLOW_API_TOKEN") or "").strip()
        collection_id = (os.environ.get("WEBFLOW_COLLECTION_ID") or "").strip()
    if not token:
        return (False, "API token is required")
    try:
        import httpx
        if not collection_id:
            resp = httpx.get(
                "https://api.webflow.com/v2/sites",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code == 200:
                return (True, "API token is valid (no collection ID to verify)")
            return (False, f"Webflow API: {resp.status_code} — {resp.text[:200] if resp.text else 'Invalid token'}")
        resp = httpx.get(
            f"https://api.webflow.com/v2/collections/{collection_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code == 200:
            j = resp.json()
            name = j.get("displayName") or j.get("name") or collection_id
            return (True, f"Credentials valid for collection: {name}")
        return (False, f"Webflow API: {resp.status_code} — {resp.text[:200] if resp.text else 'Invalid token or collection ID'}")
    except Exception as e:
        return (False, str(e))


def publish_devto(
    title: str,
    body_html: str,
    slug: str | None = None,
    config: dict | None = None,
    content_md: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """Publish to Dev.to via API. Uses content_md (markdown) when provided, else strips body_html to plain text for body_markdown."""
    if config and isinstance(config, dict):
        api_key = (config.get("api_key") or "").strip()
    else:
        api_key = (os.environ.get("DEVTO_API_KEY") or "").strip()
    if not api_key:
        return (False, None, "Set API key (in content source config or DEVTO_API_KEY in .env). Get key from dev.to/settings/extensions")
    import httpx
    body_md = content_md if (content_md and content_md.strip()) else ""
    if not body_md and body_html:
        body_md = re.sub(r"<[^>]+>", "\n", body_html).strip()
        body_md = re.sub(r"\n{3,}", "\n\n", body_md)
    payload = {
        "article": {
            "title": title,
            "body_markdown": body_md[:100_000] or title,
            "published": True,
        }
    }
    resp = httpx.post(
        "https://dev.to/api/articles",
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        return (False, None, f"Dev.to API: {resp.status_code} — {resp.text[:300] if resp.text else ''}")
    try:
        j = resp.json()
        url = (j.get("url") or "").strip() if isinstance(j, dict) else None
        return (True, url, None)
    except Exception:
        return (True, None, None)


def validate_devto(config: dict | None = None) -> tuple[bool, str]:
    """Verify Dev.to API key. Returns (success, message)."""
    if config and isinstance(config, dict):
        api_key = (config.get("api_key") or "").strip()
    else:
        api_key = (os.environ.get("DEVTO_API_KEY") or "").strip()
    if not api_key:
        return (False, "API key is required")
    try:
        import httpx
        resp = httpx.get(
            "https://dev.to/api/users/me",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            timeout=15,
        )
        if resp.status_code == 200:
            return (True, "Dev.to API key is valid")
        return (False, f"Dev.to API: {resp.status_code} — {resp.text[:200] if resp.text else 'Invalid key'}")
    except Exception as e:
        return (False, str(e))


def publish_linkedin(
    title: str,
    body_html: str,
    slug: str | None = None,
    config: dict | None = None,
) -> tuple[bool, str | None, str | None]:
    """Publish a post to LinkedIn via REST Posts API. config: access_token, author_urn (e.g. urn:li:person:ID or urn:li:organization:ID)."""
    if config and isinstance(config, dict):
        access_token = (config.get("access_token") or "").strip()
        author_urn = (config.get("author_urn") or "").strip()
    else:
        access_token = (os.environ.get("LINKEDIN_ACCESS_TOKEN") or "").strip()
        author_urn = (os.environ.get("LINKEDIN_AUTHOR_URN") or "").strip()
    if not access_token or not author_urn:
        return (False, None, "Set access_token and author_urn (in content source config or LINKEDIN_* in .env). Use OAuth to get token; author_urn is urn:li:person:ID or urn:li:organization:ID")
    import httpx
    # Combine title and body (strip HTML to plain text for commentary)
    text = title + "\n\n" + (re.sub(r"<[^>]+>", "\n", body_html).strip() if body_html else "")
    text = (text[:3000] + "...") if len(text) > 3000 else text
    payload = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    resp = httpx.post(
        "https://api.linkedin.com/rest/posts",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202401",
        },
        json=payload,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        return (False, None, f"LinkedIn API: {resp.status_code} — {resp.text[:300] if resp.text else ''}")
    post_id = resp.headers.get("x-restli-id") or resp.headers.get("X-Restli-Id")
    if post_id:
        return (True, f"https://www.linkedin.com/feed/update/{post_id}", None)
    return (True, None, None)


def validate_linkedin(config: dict | None = None) -> tuple[bool, str]:
    """Verify LinkedIn access token. Returns (success, message)."""
    if config and isinstance(config, dict):
        access_token = (config.get("access_token") or "").strip()
    else:
        access_token = (os.environ.get("LINKEDIN_ACCESS_TOKEN") or "").strip()
    if not access_token:
        return (False, "Access token is required")
    try:
        import httpx
        resp = httpx.get(
            "https://api.linkedin.com/rest/me",
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return (True, "LinkedIn token is valid")
        return (False, f"LinkedIn API: {resp.status_code} — {resp.text[:200] if resp.text else 'Invalid token'}")
    except Exception as e:
        return (False, str(e))


def publish_notion(
    title: str,
    body_html: str,
    slug: str | None = None,
    config: dict | None = None,
    content_md: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """Create a Notion page with title and markdown content. config: integration_token (or api_key), parent_id (page or database ID), optional parent_type (page_id or database_id)."""
    if config and isinstance(config, dict):
        token = (config.get("integration_token") or config.get("api_key") or "").strip()
        parent_id = (config.get("parent_id") or "").strip().replace("-", "")
        parent_type = (config.get("parent_type") or "page_id").strip().lower() or "page_id"
    else:
        token = (os.environ.get("NOTION_INTEGRATION_TOKEN") or "").strip()
        parent_id = (os.environ.get("NOTION_PARENT_ID") or "").strip().replace("-", "")
        parent_type = "page_id"
    if not token or not parent_id:
        return (False, None, "Set integration_token and parent_id (in content source config or NOTION_* in .env). Parent is the page or database ID where the new page will be created.")
    import httpx
    body_md = content_md if (content_md and content_md.strip()) else ""
    if not body_md and body_html:
        body_md = re.sub(r"<[^>]+>", "\n", body_html).strip()
        body_md = re.sub(r"\n{3,}", "\n\n", body_md)
    if parent_type == "database_id":
        parent = {"type": "database_id", "database_id": parent_id}
    else:
        parent = {"type": "page_id", "page_id": parent_id}
    payload = {
        "parent": parent,
        "properties": {
            "title": {"type": "title", "title": [{"type": "text", "text": {"content": title[:2000]}}]},
        },
        "markdown": (body_md or "")[:100_000],
    }
    resp = httpx.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        json=payload,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        return (False, None, f"Notion API: {resp.status_code} — {resp.text[:300] if resp.text else ''}")
    try:
        j = resp.json()
        url = (j.get("url") or "").strip() if isinstance(j, dict) else None
        return (True, url, None)
    except Exception:
        return (True, None, None)


def validate_notion(config: dict | None = None) -> tuple[bool, str]:
    """Verify Notion integration token and parent access. Returns (success, message)."""
    if config and isinstance(config, dict):
        token = (config.get("integration_token") or config.get("api_key") or "").strip()
        parent_id = (config.get("parent_id") or "").strip().replace("-", "")
    else:
        token = (os.environ.get("NOTION_INTEGRATION_TOKEN") or "").strip()
        parent_id = (os.environ.get("NOTION_PARENT_ID") or "").strip().replace("-", "")
    if not token:
        return (False, "Integration token is required")
    try:
        import httpx
        if not parent_id:
            resp = httpx.get(
                "https://api.notion.com/v1/users/me",
                headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"},
                timeout=15,
            )
            return (True, "Token valid (no parent_id to verify)") if resp.status_code == 200 else (False, f"Notion API: {resp.status_code}")
        resp = httpx.get(
            f"https://api.notion.com/v1/pages/{parent_id}",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28"},
            timeout=15,
        )
        if resp.status_code == 200:
            return (True, "Notion token and parent access are valid")
        return (False, f"Notion API: {resp.status_code} — {resp.text[:200] if resp.text else 'Invalid token or parent ID'}")
    except Exception as e:
        return (False, str(e))


def validate_credentials(destination: str, config: dict | None = None) -> tuple[bool, str]:
    """Validate CMS credentials for the given destination. Returns (success, message)."""
    dest = (destination or "").strip().lower()
    if dest == "ghost":
        return validate_ghost(config=config)
    if dest == "hashnode":
        return validate_hashnode(config=config)
    if dest == "wordpress":
        return validate_wordpress(config=config)
    if dest == "webflow":
        return validate_webflow(config=config)
    if dest == "devto":
        return validate_devto(config=config)
    if dest == "linkedin":
        return validate_linkedin(config=config)
    if dest == "notion":
        return validate_notion(config=config)
    return (False, f"Unknown destination: {destination}")


def publish_draft(
    draft_id: int,
    body_html: str,
    title: str,
    slug: str,
    destination: str | None = None,
    source_config: dict | None = None,
    body_md: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """Publish to the given CMS. If body_md is provided, Hashnode uses it for contentMarkdown (keeps image URLs)."""
    if destination:
        dest = destination.lower()
        if dest == "wordpress":
            return publish_wordpress(title, body_html, slug, config=source_config)
        if dest == "webflow":
            return publish_webflow(title, body_html, slug, config=source_config)
        if dest == "ghost":
            return publish_ghost(title, body_html, slug, config=source_config)
        if dest == "hashnode":
            return publish_hashnode(title, body_html, slug, config=source_config, content_md=body_md)
        if dest == "devto":
            return publish_devto(title, body_html, slug, config=source_config, content_md=body_md)
        if dest == "linkedin":
            return publish_linkedin(title, body_html, slug, config=source_config)
        if dest == "notion":
            return publish_notion(title, body_html, slug, config=source_config, content_md=body_md)
        return (False, None, f"Unknown destination: {destination}")
    if os.environ.get("WORDPRESS_URL"):
        return publish_wordpress(title, body_html, slug)
    if os.environ.get("WEBFLOW_API_TOKEN"):
        return publish_webflow(title, body_html, slug)
    if os.environ.get("GHOST_URL") and os.environ.get("GHOST_ADMIN_API_KEY"):
        return publish_ghost(title, body_html, slug)
    if os.environ.get("HASHNODE_API_KEY") and os.environ.get("HASHNODE_PUBLICATION_ID"):
        return publish_hashnode(title, body_html, slug)
    return (
        False,
        None,
        "No CMS configured. Add credentials in the content source config or set env vars: "
        "WORDPRESS_URL + WORDPRESS_APP_PASSWORD | WEBFLOW_API_TOKEN + WEBFLOW_COLLECTION_ID | "
        "GHOST_URL + GHOST_ADMIN_API_KEY | HASHNODE_API_KEY + HASHNODE_PUBLICATION_ID.",
    )
