"""FastAPI app: endpoints for citations, trends, prompts visibility."""
import json
import os
import re
import sys
import threading
import time
import uuid
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import textwrap
import logging

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import openlit

from fastapi import FastAPI, HTTPException, Body, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from src.db.connection import get_connection, init_db

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
except Exception:  # pragma: no cover - optional dependency in some environments
    A4 = None
    mm = None
    canvas = None
from api.auth import (
    hash_password,
    verify_password,
    create_token,
    get_current_user_id,
)


logger = logging.getLogger("truseo.api")
if not logger.handlers:
    logging.basicConfig(
        level=os.environ.get("TRUSEO_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

# Initialize OpenLIT observability for the API process.
# Uses OTEL_* environment variables (OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_HEADERS, OTEL_SERVICE_NAME, etc.).
openlit.init()


def _rewrite_image_urls_in_markdown(body_md: str) -> str:
    """Replace relative image paths ](/file.png) or ](file.png) with absolute PUBLIC_URL/api/images/file.png so published content (e.g. Hashnode) can load images."""
    base = (os.environ.get("PUBLIC_URL") or os.environ.get("API_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return body_md

    def repl(m: re.Match) -> str:
        path = (m.group(1) or "") + (m.group(2) or "")
        path = path.lstrip("/")
        return f"]({base}/api/images/{path})"

    return re.sub(
        r'\]\((?!https?://)(/?)([^)\s]+\.(png|jpg|jpeg|gif|webp))\)',
        repl,
        body_md,
        flags=re.IGNORECASE,
    )


app = FastAPI(title="TRUSEO API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def _scheduler_loop():
    """Background loop: every 60s check monitoring_settings and prompt_generation_settings per user and run if due."""
    while True:
        time.sleep(60)
        try:
            conn = get_connection()
            try:
                # All users with enabled monitoring and due frequency
                rows = conn.execute(
                    "SELECT user_id, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds FROM monitoring_settings WHERE enabled = 1 AND frequency_minutes IS NOT NULL AND frequency_minutes > 0"
                ).fetchall()
                for row in rows:
                    user_id = row["user_id"]
                    freq_mins = int(row["frequency_minutes"] or 0)
                    if freq_mins <= 0:
                        continue
                    last = conn.execute(
                        """SELECT started_at FROM monitoring_executions
                           WHERE user_id = ? AND (trigger_type = 'scheduled' OR trigger_type = 'manual')
                           ORDER BY started_at DESC LIMIT 1""",
                        (user_id,),
                    ).fetchone()
                    if last and last["started_at"]:
                        from datetime import datetime, timezone
                        try:
                            if isinstance(last["started_at"], str):
                                last_ts = datetime.fromisoformat(last["started_at"].replace("Z", "+00:00"))
                            else:
                                last_ts = last["started_at"]
                            if last_ts.tzinfo is None:
                                last_ts = last_ts.replace(tzinfo=timezone.utc)
                            if (datetime.now(timezone.utc) - last_ts).total_seconds() < freq_mins * 60:
                                continue
                        except Exception:
                            pass
                    domain_ids = None
                    if row["domain_ids"]:
                        try:
                            domain_ids = json.loads(row["domain_ids"])
                        except (TypeError, ValueError):
                            pass
                    models = None
                    if row["models"]:
                        try:
                            models = json.loads(row["models"])
                        except (TypeError, ValueError):
                            pass
                    prompt_limit = row["prompt_limit"]
                    if prompt_limit is not None and prompt_limit != "":
                        try:
                            prompt_limit = int(prompt_limit)
                        except (TypeError, ValueError):
                            prompt_limit = None
                    else:
                        prompt_limit = None
                    delay_seconds = row["delay_seconds"]
                    settings_snapshot = {
                        "domain_ids": domain_ids,
                        "models": models,
                        "prompt_limit": prompt_limit,
                        "delay_seconds": delay_seconds,
                    }
                    conn.execute(
                        """INSERT INTO monitoring_executions (user_id, trigger_type, status, settings_snapshot)
                           VALUES (?, 'scheduled', 'running', ?)""",
                        (user_id, json.dumps(settings_snapshot)),
                    )
                    execution_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.commit()
                    conn.close()
                    from src.monitor.run_monitor import run
                    run(
                        execution_id=execution_id,
                        trigger_type="scheduled",
                        settings_snapshot=settings_snapshot,
                        models=models,
                        limit_prompts=prompt_limit,
                        domain_ids=domain_ids,
                        delay_seconds=delay_seconds,
                        skip_prompts_with_recent_win=True,
                        user_id=user_id,
                    )
                    _run_brief_and_content_after_monitor()
                    conn = get_connection()
            finally:
                conn.close()
        except Exception:
            pass
        try:
            conn = get_connection()
            try:
                from src.domains_db import discovery_done
                from datetime import datetime, timezone
                rows = conn.execute(
                    "SELECT user_id, enabled, frequency_days, last_run_at, prompts_per_domain FROM prompt_generation_settings WHERE enabled = 1"
                ).fetchall()
                for row in rows:
                    user_id = row["user_id"]
                    freq_days = float(row["frequency_days"] or 0)
                    if freq_days <= 0:
                        continue
                    last_run = row["last_run_at"]
                    due = True
                    if last_run:
                        try:
                            if isinstance(last_run, str):
                                last_ts = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                            else:
                                last_ts = last_run
                            if last_ts.tzinfo is None:
                                last_ts = last_ts.replace(tzinfo=timezone.utc)
                            if (datetime.now(timezone.utc) - last_ts).total_seconds() < freq_days * 86400:
                                due = False
                        except Exception:
                            pass
                    if due and discovery_done(conn, user_id=user_id):
                        conn.execute(
                            "INSERT INTO prompt_generation_runs (user_id, trigger_type, status) VALUES (?, 'scheduled', 'running')",
                            (user_id,),
                        )
                        run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                        prompts_per_domain = row["prompts_per_domain"]
                        if prompts_per_domain is not None:
                            prompts_per_domain = int(prompts_per_domain)
                        conn.commit()
                        try:
                            inserted = _run_prompt_generation_sync(conn, user_id, prompts_per_domain, prompt_generation_run_id=run_id)
                            conn.execute(
                                "UPDATE prompt_generation_settings SET last_run_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                                (user_id,),
                            )
                            conn.execute(
                                "UPDATE prompt_generation_runs SET finished_at = CURRENT_TIMESTAMP, status = 'finished', inserted_count = ? WHERE id = ?",
                                (inserted, run_id),
                            )
                            conn.commit()
                        except Exception:
                            conn.execute(
                                "UPDATE prompt_generation_runs SET finished_at = CURRENT_TIMESTAMP, status = 'failed' WHERE id = ?",
                                (run_id,),
                            )
                            conn.commit()
            finally:
                conn.close()
        except Exception:
            pass


@app.on_event("startup")
def startup():
    conn = get_connection()
    init_db(conn)
    conn.close()
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()


def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------- Auth (no JWT required) ----------
def _validate_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    return "@" in email and "." in email and len(email) <= 255


@app.post("/api/auth/signup")
def signup(body: dict = Body(...)):
    """Register: email, password; optional name. Returns JWT and user."""
    email = (body.get("email") or "").strip()
    password = body.get("password")
    name = (body.get("name") or "").strip() or None
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")
    if not _validate_email(email):
        raise HTTPException(status_code=400, detail="invalid email")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")
    conn = get_connection()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="email already registered")
        password_hash = hash_password(password)
        conn.execute(
            "INSERT INTO users (email, password_hash, name, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (email, password_hash, name),
        )
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        token = create_token(user_id)
        row = conn.execute("SELECT id, email, name FROM users WHERE id = ?", (user_id,)).fetchone()
        user = {"id": row["id"], "email": row["email"], "name": row["name"]}
        return {"token": token, "user": user}
    finally:
        conn.close()


@app.post("/api/auth/signin")
def signin(body: dict = Body(...)):
    """Login: email, password. Returns JWT and user."""
    email = (body.get("email") or "").strip()
    password = body.get("password")
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password required")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, email, password_hash, name FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="invalid email or password")
        token = create_token(row["id"])
        user = {"id": row["id"], "email": row["email"], "name": row["name"]}
        return {"token": token, "user": user}
    finally:
        conn.close()


@app.get("/api/auth/me")
def auth_me(user_id: int = Depends(get_current_user_id)):
    """Return current user (requires valid JWT)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, email, name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="user not found")
        return {"id": row["id"], "email": row["email"], "name": row["name"]}
    finally:
        conn.close()


@app.get("/api/dashboard/stats")
def get_dashboard_stats(user_id: int = Depends(get_current_user_id)):
    """Aggregate numbers for dashboard: citations, brand mentions, prompts, domains, last run."""
    conn = get_connection()
    try:
        total_prompts = conn.execute("SELECT COUNT(*) AS n FROM prompts WHERE user_id = ?", (user_id,)).fetchone()["n"] or 0
        domains_tracked = conn.execute("SELECT COUNT(*) AS n FROM domains WHERE user_id = ?", (user_id,)).fetchone()["n"] or 0
        run_rows = conn.execute(
            """SELECT r.id FROM runs r
               JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
               WHERE r.status = 'finished' ORDER BY r.started_at DESC LIMIT 3""",
            (user_id,),
        ).fetchall()
        run_ids = [r["id"] for r in run_rows]
        last_run = conn.execute(
            """SELECT r.started_at FROM runs r
               JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
               WHERE r.status = 'finished' ORDER BY r.started_at DESC LIMIT 1""",
            (user_id,),
        ).fetchone()
        last_run_at = last_run["started_at"] if last_run else None
        if not run_ids:
            return {
                "total_prompts": total_prompts,
                "domains_tracked": domains_tracked,
                "last_run_at": last_run_at,
                "prompts_with_own_citation": 0,
                "prompts_with_brand_mentioned": 0,
                "prompts_competitor_only": 0,
                "total_own_citations": 0,
                "citation_rate_pct": 0.0,
            }
        placeholders = ",".join("?" * len(run_ids))
        cited = conn.execute(
            f"SELECT COUNT(DISTINCT prompt_id) AS n FROM run_prompt_visibility WHERE run_id IN ({placeholders}) AND had_own_citation = 1",
            run_ids,
        ).fetchone()["n"] or 0
        brand = conn.execute(
            f"SELECT COUNT(DISTINCT prompt_id) AS n FROM run_prompt_visibility WHERE run_id IN ({placeholders}) AND brand_mentioned = 1",
            run_ids,
        ).fetchone()["n"] or 0
        comp_only = conn.execute(
            f"SELECT COUNT(DISTINCT prompt_id) AS n FROM run_prompt_visibility WHERE run_id IN ({placeholders}) AND competitor_only = 1",
            run_ids,
        ).fetchone()["n"] or 0
        total_citations = conn.execute(
            f"SELECT COUNT(*) AS n FROM citations WHERE run_id IN ({placeholders}) AND is_own_domain = 1",
            run_ids,
        ).fetchone()["n"] or 0
        rate = (cited / total_prompts * 100) if total_prompts else 0.0
        return {
            "total_prompts": total_prompts,
            "domains_tracked": domains_tracked,
            "last_run_at": last_run_at,
            "prompts_with_own_citation": cited,
            "prompts_with_brand_mentioned": brand,
            "prompts_competitor_only": comp_only,
            "total_own_citations": total_citations,
            "citation_rate_pct": round(rate, 1),
        }
    finally:
        conn.close()


@app.get("/api/learning/summary")
def get_learning_summary(user_id: int = Depends(get_current_user_id)):
    """Return current learning hints (from learning job) and top drafts by citation/brand uplift for the user."""
    hints = None
    try:
        from src.learning.load_hints import load_learning_hints
        hints = load_learning_hints()
    except Exception:
        pass
    conn = get_connection()
    try:
        init_db(conn)
        rows = conn.execute(
            """SELECT u.draft_id, u.citation_rate_before, u.citation_rate_after, u.brand_rate_before, u.brand_rate_after,
                      d.title AS draft_title
               FROM citation_uplift u
               JOIN drafts d ON d.id = u.draft_id AND d.user_id = ?
               ORDER BY (u.citation_rate_after - u.citation_rate_before) + (COALESCE(u.brand_rate_after, 0) - COALESCE(u.brand_rate_before, 0)) DESC
               LIMIT 3""",
            (user_id,),
        ).fetchall()
        top_uplift = []
        for r in rows:
            cite_delta = (r["citation_rate_after"] or 0) - (r["citation_rate_before"] or 0)
            brand_before = r["brand_rate_before"]
            brand_after = r["brand_rate_after"]
            brand_delta = (brand_after - brand_before) if (brand_before is not None and brand_after is not None) else None
            top_uplift.append({
                "draft_id": r["draft_id"],
                "draft_title": (r["draft_title"] or "")[:60],
                "citation_delta": round(cite_delta, 1),
                "brand_delta": round(brand_delta, 1) if brand_delta is not None else None,
            })
        h = hints or {}
        return {
            "hints": {
                "prompt_gen_hints": (h.get("prompt_gen_hints") or "").strip(),
                "brief_gen_system_extra": (h.get("brief_gen_system_extra") or "").strip(),
            },
            "top_uplift": top_uplift,
        }
    finally:
        conn.close()


# ---------- Domains (replaces config/domains.yaml) ----------
@app.get("/api/domains")
def list_domains(user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, domain, brand_names, created_at, updated_at FROM domains WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("brand_names"):
                try:
                    import json
                    d["brand_names"] = json.loads(d["brand_names"])
                except (TypeError, ValueError):
                    d["brand_names"] = []
            else:
                d["brand_names"] = []
            out.append(d)
        return {"domains": out}
    finally:
        conn.close()


@app.post("/api/domains")
def create_domain(body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    raw = (body.get("domain") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="domain is required")
    domain = _normalize_website_to_domain(raw) or raw
    # Verify the site exists before adding (normal website crawl check)
    try:
        from src.domain_discovery.crawl import check_domain_reachable
        ok, err_msg = check_domain_reachable(domain)
        if not ok:
            raise HTTPException(status_code=400, detail=err_msg or "Domain does not exist or is not reachable. Please check the URL and try again.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not verify domain: {e!s}")
    brand_names = body.get("brand_names")
    if brand_names is not None and not isinstance(brand_names, list):
        brand_names = [str(brand_names)] if brand_names else []
    brand_names_json = __import__("json").dumps(brand_names or [])
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO domains (user_id, domain, brand_names, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, domain, brand_names_json),
        )
        conn.commit()
        rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = conn.execute(
            "SELECT id, domain, brand_names, created_at, updated_at FROM domains WHERE id = ?",
            (rid,),
        ).fetchone()
        out = dict(row)
        out["brand_names"] = brand_names or []
        return out
    except Exception as e:
        if "UNIQUE" in str(e) or "unique" in str(e).lower():
            raise HTTPException(status_code=400, detail="Domain already exists")
        raise
    finally:
        conn.close()


@app.get("/api/domains/{domain_id}")
def get_domain(domain_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, domain, brand_names, created_at, updated_at FROM domains WHERE id = ? AND user_id = ?",
            (domain_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Domain not found")
        out = dict(row)
        if out.get("brand_names"):
            try:
                out["brand_names"] = __import__("json").loads(out["brand_names"])
            except (TypeError, ValueError):
                out["brand_names"] = []
        else:
            out["brand_names"] = []
        return out
    finally:
        conn.close()


@app.put("/api/domains/{domain_id}")
def update_domain(domain_id: int, body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM domains WHERE id = ? AND user_id = ?", (domain_id, user_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Domain not found")
        domain = (body.get("domain") or "").strip()
        brand_names = body.get("brand_names")
        if domain:
            conn.execute(
                "UPDATE domains SET domain = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (domain, domain_id),
            )
        if brand_names is not None:
            brand_names_json = __import__("json").dumps(brand_names if isinstance(brand_names, list) else [])
            conn.execute(
                "UPDATE domains SET brand_names = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (brand_names_json, domain_id),
            )
        conn.commit()
        row = conn.execute(
            "SELECT id, domain, brand_names, created_at, updated_at FROM domains WHERE id = ?",
            (domain_id,),
        ).fetchone()
        out = dict(row)
        if out.get("brand_names"):
            try:
                out["brand_names"] = __import__("json").loads(out["brand_names"])
            except (TypeError, ValueError):
                out["brand_names"] = []
        else:
            out["brand_names"] = []
        return out
    finally:
        conn.close()


@app.delete("/api/domains/{domain_id}")
def delete_domain(domain_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM domains WHERE id = ? AND user_id = ?", (domain_id, user_id))
        conn.execute("DELETE FROM domain_profiles WHERE domain_id = ?", (domain_id,))
        conn.execute("DELETE FROM domain_content_source WHERE domain_id = ?", (domain_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Domain not found")
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/domains/{domain_id}/profile")
def get_domain_profile(domain_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT dp.id, dp.domain_id, dp.category, dp.niche, dp.value_proposition, dp.key_topics,
                      dp.target_audience, dp.competitors, dp.discovered_at, d.domain
               FROM domain_profiles dp JOIN domains d ON d.id = dp.domain_id AND d.user_id = ?
               WHERE dp.domain_id = ?""",
            (user_id, domain_id),
        ).fetchone()
        if not row:
            row = conn.execute("SELECT id, domain FROM domains WHERE id = ? AND user_id = ?", (domain_id, user_id)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Domain not found")
            return {"domain_id": domain_id, "domain": row["domain"], "profile": None, "discovered_at": None}
        out = dict(row)
        for key in ("key_topics", "competitors"):
            if out.get(key):
                try:
                    out[key] = __import__("json").loads(out[key])
                except (TypeError, ValueError):
                    out[key] = []
            else:
                out[key] = []
        return out
    finally:
        conn.close()


@app.post("/api/domains/{domain_id}/discover")
def run_domain_discovery(domain_id: int, user_id: int = Depends(get_current_user_id)):
    """Run discovery for this domain only (crawl + extract profile)."""
    conn = get_connection()
    try:
        if not conn.execute("SELECT id FROM domains WHERE id = ? AND user_id = ?", (domain_id, user_id)).fetchone():
            raise HTTPException(status_code=404, detail="Domain not found")
        from src.domain_discovery.run_discovery import run_discovery_for_domain
        result = run_discovery_for_domain(conn, domain_id)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Discovery failed"))
        return result
    finally:
        conn.close()


@app.put("/api/domains/{domain_id}/profile")
def update_domain_profile(domain_id: int, body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    """Create or update profile for this domain. Body: category, niche, value_proposition, key_topics (array), target_audience, competitors (array)."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM domains WHERE id = ? AND user_id = ?", (domain_id, user_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Domain not found")
        category = (body.get("category") or "").strip()
        categories = body.get("categories")
        if isinstance(categories, list):
            categories = [str(x).strip() for x in categories[:3] if x]
        else:
            categories = [category] if category else []
        while len(categories) < 3:
            categories.append("General")
        categories = categories[:3]
        niche = (body.get("niche") or "").strip()
        value_proposition = (body.get("value_proposition") or "").strip()
        target_audience = (body.get("target_audience") or "").strip()
        key_topics = body.get("key_topics")
        competitors = body.get("competitors")
        if not isinstance(key_topics, list):
            key_topics = []
        if not isinstance(competitors, list):
            competitors = []
        key_topics = [str(x).strip() for x in key_topics if x]
        competitors = [str(x).strip() for x in competitors if x]
        key_topics_json = __import__("json").dumps(key_topics)
        competitors_json = __import__("json").dumps(competitors)
        categories_json = json.dumps(categories)
        conn.execute(
            """INSERT INTO domain_profiles (domain_id, category, categories, niche, value_proposition, key_topics, target_audience, competitors, discovered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT discovered_at FROM domain_profiles WHERE domain_id = ?), CURRENT_TIMESTAMP))
               ON CONFLICT(domain_id) DO UPDATE SET
                 category=excluded.category, categories=excluded.categories, niche=excluded.niche, value_proposition=excluded.value_proposition,
                 key_topics=excluded.key_topics, target_audience=excluded.target_audience, competitors=excluded.competitors""",
            (domain_id, category, categories_json, niche, value_proposition, key_topics_json, target_audience, competitors_json, domain_id),
        )
        conn.commit()
        row = conn.execute(
            """SELECT dp.id, dp.domain_id, dp.category, dp.categories, dp.niche, dp.value_proposition, dp.key_topics,
                      dp.target_audience, dp.competitors, dp.discovered_at, d.domain
               FROM domain_profiles dp JOIN domains d ON d.id = dp.domain_id WHERE dp.domain_id = ?""",
            (domain_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Profile not saved")
        out = dict(row)
        for key in ("key_topics", "competitors", "categories"):
            if out.get(key):
                try:
                    out[key] = __import__("json").loads(out[key])
                except (TypeError, ValueError):
                    out[key] = []
            else:
                out[key] = []
        return out
    finally:
        conn.close()


# ---------- Content sources (Hashnode, Ghost, etc.) and domain mapping ----------
CONTENT_SOURCE_TYPES = ("hashnode", "ghost", "wordpress", "webflow", "linkedin", "devto", "notion")


@app.get("/api/content-sources")
def list_content_sources(user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, type, config, created_at, updated_at FROM content_sources WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("config"):
                try:
                    d["config"] = json.loads(d["config"])
                except (TypeError, ValueError):
                    d["config"] = None
            out.append(d)
        return {"content_sources": out}
    finally:
        conn.close()


@app.post("/api/content-sources")
def create_content_source(body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    name = (body.get("name") or "").strip()
    source_type = (body.get("type") or "").strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if source_type not in CONTENT_SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"type must be one of: {', '.join(CONTENT_SOURCE_TYPES)}")
    config = body.get("config")
    config_json = json.dumps(config) if config is not None else None
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO content_sources (user_id, name, type, config, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, name, source_type, config_json),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, type, config, created_at, updated_at FROM content_sources WHERE id = last_insert_rowid()"
        ).fetchone()
        out = dict(row)
        if out.get("config"):
            try:
                out["config"] = json.loads(out["config"])
            except (TypeError, ValueError):
                out["config"] = None
        return out
    finally:
        conn.close()


@app.get("/api/content-sources/{source_id}")
def get_content_source(source_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, type, config, created_at, updated_at FROM content_sources WHERE id = ? AND user_id = ?",
            (source_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Content source not found")
        out = dict(row)
        if out.get("config"):
            try:
                out["config"] = json.loads(out["config"])
            except (TypeError, ValueError):
                out["config"] = None
        return out
    finally:
        conn.close()


@app.put("/api/content-sources/{source_id}")
def update_content_source(source_id: int, body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM content_sources WHERE id = ? AND user_id = ?", (source_id, user_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Content source not found")
        updates = []
        params = []
        if "name" in body:
            name = (body.get("name") or "").strip()
            if name:
                updates.append("name = ?")
                params.append(name)
        if "type" in body:
            source_type = (body.get("type") or "").strip().lower()
            if source_type in CONTENT_SOURCE_TYPES:
                updates.append("type = ?")
                params.append(source_type)
        if "config" in body:
            config = body.get("config")
            if isinstance(config, dict):
                cur = conn.execute("SELECT config FROM content_sources WHERE id = ?", (source_id,)).fetchone()
                current = {}
                if cur and cur["config"]:
                    try:
                        current = json.loads(cur["config"]) or {}
                    except (TypeError, ValueError):
                        pass
                if not isinstance(current, dict):
                    current = {}
                merged = dict(current)
                for k, v in config.items():
                    if v is not None and str(v).strip():
                        merged[k] = v
                config = merged
            updates.append("config = ?")
            params.append(json.dumps(config) if config else None)
        if updates:
            params.append(source_id)
            conn.execute(
                "UPDATE content_sources SET " + ", ".join(updates) + ", updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                params,
            )
            conn.commit()
        row = conn.execute(
            "SELECT id, name, type, config, created_at, updated_at FROM content_sources WHERE id = ?",
            (source_id,),
        ).fetchone()
        out = dict(row)
        if out.get("config"):
            try:
                out["config"] = json.loads(out["config"])
            except (TypeError, ValueError):
                out["config"] = None
        return out
    finally:
        conn.close()


@app.delete("/api/content-sources/{source_id}")
def delete_content_source(source_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM content_sources WHERE id = ? AND user_id = ?", (source_id, user_id))
        conn.execute("DELETE FROM domain_content_source WHERE content_source_id = ?", (source_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Content source not found")
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/content-sources/{source_id}/validate")
def validate_content_source_credentials(source_id: int, user_id: int = Depends(get_current_user_id)):
    """Test CMS credentials for this content source (uses saved config). Returns { ok, message }."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, type, config FROM content_sources WHERE id = ? AND user_id = ?",
            (source_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Content source not found")
        dest = (row["type"] or "").strip().lower()
        source_config = None
        if row["config"]:
            try:
                source_config = json.loads(row["config"])
            except (TypeError, ValueError):
                pass
        from src.content.cms import validate_credentials
        ok, message = validate_credentials(dest, config=source_config)
        return {"ok": ok, "message": message}
    finally:
        conn.close()


@app.post("/api/cms/validate")
def validate_cms_credentials(body: dict = Body(...)):
    """Test CMS credentials (e.g. from form). Body: { destination: str, config?: dict }. Returns { ok, message }."""
    destination = (body.get("destination") or "").strip().lower()
    if not destination:
        raise HTTPException(status_code=400, detail="destination is required")
    config = body.get("config")
    if config is not None and not isinstance(config, dict):
        config = None
    from src.content.cms import validate_credentials
    ok, message = validate_credentials(destination, config=config)
    return {"ok": ok, "message": message}


@app.get("/api/content-sources/{source_id}/domains")
def list_content_source_domains(source_id: int, user_id: int = Depends(get_current_user_id)):
    """Domains mapped to this content source."""
    conn = get_connection()
    try:
        if not conn.execute("SELECT id FROM content_sources WHERE id = ? AND user_id = ?", (source_id, user_id)).fetchone():
            raise HTTPException(status_code=404, detail="Content source not found")
        rows = conn.execute(
            """SELECT d.id, d.domain FROM domains d
               JOIN domain_content_source dcs ON dcs.domain_id = d.id
               WHERE dcs.content_source_id = ? AND d.user_id = ? ORDER BY d.domain""",
            (source_id, user_id),
        ).fetchall()
        return {"domains": [{"id": r["id"], "domain": r["domain"]} for r in rows]}
    finally:
        conn.close()


@app.get("/api/domains/{domain_id}/content-sources")
def list_domain_content_sources(domain_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM domains WHERE id = ? AND user_id = ?", (domain_id, user_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Domain not found")
        rows = conn.execute(
            """SELECT cs.id, cs.name, cs.type, cs.config, cs.created_at
               FROM content_sources cs
               JOIN domain_content_source dcs ON dcs.content_source_id = cs.id
               WHERE dcs.domain_id = ? AND cs.user_id = ? ORDER BY cs.name""",
            (domain_id, user_id),
        ).fetchall()
        out = [dict(r) for r in rows]
        for d in out:
            if d.get("config"):
                try:
                    d["config"] = json.loads(d["config"])
                except (TypeError, ValueError):
                    d["config"] = None
        return {"content_sources": out}
    finally:
        conn.close()


@app.post("/api/domains/{domain_id}/content-sources")
def add_domain_content_source(domain_id: int, body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    source_id = body.get("content_source_id")
    if source_id is None:
        raise HTTPException(status_code=400, detail="content_source_id is required")
    try:
        source_id = int(source_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="content_source_id must be an integer")
    conn = get_connection()
    try:
        if not conn.execute("SELECT id FROM domains WHERE id = ? AND user_id = ?", (domain_id, user_id)).fetchone():
            raise HTTPException(status_code=404, detail="Domain not found")
        if not conn.execute("SELECT id FROM content_sources WHERE id = ? AND user_id = ?", (source_id, user_id)).fetchone():
            raise HTTPException(status_code=404, detail="Content source not found")
        conn.execute(
            "INSERT OR IGNORE INTO domain_content_source (domain_id, content_source_id) VALUES (?, ?)",
            (domain_id, source_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.delete("/api/domains/{domain_id}/content-sources/{content_source_id}")
def remove_domain_content_source(domain_id: int, content_source_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        if not conn.execute("SELECT id FROM domains WHERE id = ? AND user_id = ?", (domain_id, user_id)).fetchone():
            raise HTTPException(status_code=404, detail="Domain not found")
        cur = conn.execute(
            "DELETE FROM domain_content_source WHERE domain_id = ? AND content_source_id = ?",
            (domain_id, content_source_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Mapping not found")
        return {"ok": True}
    finally:
        conn.close()


# ---------- Discovery status and run ----------
@app.get("/api/discovery/status")
def discovery_status(user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        from src.domains_db import discovery_done, get_tracked_domains_from_db, get_domain_profiles_from_db
        domains_count = len(get_tracked_domains_from_db(conn, user_id=user_id))
        profiles = get_domain_profiles_from_db(conn, user_id=user_id)
        profiles_count = len(profiles) if profiles else 0
        discovery_done_flag = discovery_done(conn, user_id=user_id)
        return {
            "domains_count": domains_count,
            "profiles_count": profiles_count,
            "discovery_done": discovery_done_flag,
        }
    finally:
        conn.close()


@app.post("/api/discovery/run")
def run_discovery(user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        from src.domain_discovery.run_discovery import run_discovery_to_db
        result = run_discovery_to_db(conn, user_id=user_id)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Discovery failed"))
        return result
    finally:
        conn.close()


# ---------- Prompt generation (gated: only after discovery) ----------
@app.post("/api/prompts/generate")
def generate_prompts_api(body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        from src.domains_db import discovery_done
        if not discovery_done(conn, user_id=user_id):
            raise HTTPException(
                status_code=400,
                detail="Run domain discovery first. Add domains and click Run discovery.",
            )
        count = body.get("count")
        prompts_per_domain = body.get("prompts_per_domain")
        if count is not None:
            count = int(count)
        if prompts_per_domain is not None:
            prompts_per_domain = int(prompts_per_domain)

        from src.monitor.prompt_generator import (
            load_domain_profiles,
            generate_prompts,
            store_prompts_in_db,
            store_prompts_with_niches,
            _context_from_profile,
        )
        from src.config_loader import get_prompts_per_domain, get_prompt_count_total

        profiles = load_domain_profiles(conn=conn, user_id=user_id)
        if not profiles:
            raise HTTPException(status_code=400, detail="No domain profiles in DB.")
        if prompts_per_domain is not None and prompts_per_domain > 0:
            all_prompts_with_niche = []
            for domain, profile in profiles:
                context = _context_from_profile(domain, profile)
                brand_names = _brand_names_for_domain(conn, user_id, domain)
                prompts = generate_prompts(niche=context, count=prompts_per_domain, domain=domain, brand_names=brand_names)
                for p in prompts:
                    all_prompts_with_niche.append((p, f"domain:{domain}"))
            inserted = store_prompts_with_niches(all_prompts_with_niche, conn, user_id=user_id)
        elif count is not None and count > 0:
            domain, profile = profiles[0]
            context = _context_from_profile(domain, profile)
            brand_names = _brand_names_for_domain(conn, user_id, domain)
            prompts = generate_prompts(niche=context, count=count, domain=domain, brand_names=brand_names)
            inserted = store_prompts_in_db(prompts, conn, niche=profile.get("niche") or "domain:" + domain, user_id=user_id)
        else:
            per_domain = get_prompts_per_domain()
            all_prompts_with_niche = []
            for domain, profile in profiles:
                context = _context_from_profile(domain, profile)
                brand_names = _brand_names_for_domain(conn, user_id, domain)
                prompts = generate_prompts(niche=context, count=per_domain, domain=domain, brand_names=brand_names)
                for p in prompts:
                    all_prompts_with_niche.append((p, f"domain:{domain}"))
            inserted = store_prompts_with_niches(all_prompts_with_niche, conn, user_id=user_id)
        conn.commit()
        return {"ok": True, "inserted": inserted}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


def _brand_names_for_domain(conn, user_id: int, domain: str) -> list[str] | None:
    """Return brand_names list for this user's domain, or None."""
    try:
        row = conn.execute(
            "SELECT brand_names FROM domains WHERE user_id = ? AND domain = ?",
            (user_id, domain),
        ).fetchone()
        if not row:
            return None
        raw = row["brand_names"]
        if raw is None:
            return None
        out = json.loads(raw) if isinstance(raw, str) else (raw or [])
        return out if isinstance(out, list) else None
    except (TypeError, ValueError):
        return None


def _run_prompt_generation_sync(conn, user_id: int, prompts_per_domain: int | None = None, prompt_generation_run_id: int | None = None) -> int:
    """Run prompt generation (domain profiles → prompts). Uses prompts_per_domain or config default. Returns inserted count. Caller must commit."""
    from src.monitor.prompt_generator import (
        load_domain_profiles,
        generate_prompts,
        store_prompts_with_niches,
        _context_from_profile,
    )
    from src.config_loader import get_prompts_per_domain
    profiles = load_domain_profiles(conn=conn, user_id=user_id)
    if not profiles:
        return 0
    per_domain = prompts_per_domain if prompts_per_domain is not None and prompts_per_domain > 0 else get_prompts_per_domain()
    all_prompts_with_niche = []
    for domain, profile in profiles:
        context = _context_from_profile(domain, profile)
        brand_names = _brand_names_for_domain(conn, user_id, domain)
        prompts = generate_prompts(niche=context, count=per_domain, domain=domain, brand_names=brand_names)
        for p in prompts:
            all_prompts_with_niche.append((p, f"domain:{domain}"))
    if not all_prompts_with_niche:
        return 0
    return store_prompts_with_niches(all_prompts_with_niche, conn, prompt_generation_run_id=prompt_generation_run_id, user_id=user_id)


# ---------- Prompt generation schedule (settings + run) ----------
@app.get("/api/prompt-generation/settings")
def get_prompt_generation_settings(user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT user_id, enabled, frequency_days, prompts_per_domain, last_run_at, updated_at FROM prompt_generation_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT OR IGNORE INTO prompt_generation_settings (user_id, enabled, frequency_days) VALUES (?, 0, 7)",
                (user_id,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT user_id, enabled, frequency_days, prompts_per_domain, last_run_at, updated_at FROM prompt_generation_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return {
                "enabled": 0,
                "frequency_days": 7,
                "prompts_per_domain": None,
                "last_run_at": None,
                "updated_at": None,
            }
        out = dict(row)
        if out.get("enabled") is not None:
            out["enabled"] = bool(out["enabled"])
        return out
    finally:
        conn.close()


@app.put("/api/prompt-generation/settings")
def update_prompt_generation_settings(body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO prompt_generation_settings (user_id, enabled, frequency_days) VALUES (?, 0, 7)",
            (user_id,),
        )
        updates = []
        params = []
        if "enabled" in body:
            v = 1 if body.get("enabled") else 0
            updates.append("enabled = ?")
            params.append(v)
        if "frequency_days" in body:
            v = body.get("frequency_days")
            v = float(v) if v is not None else 7
            updates.append("frequency_days = ?")
            params.append(v)
        if "prompts_per_domain" in body:
            v = body.get("prompts_per_domain")
            updates.append("prompts_per_domain = ?")
            params.append(int(v) if v is not None else None)
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(user_id)
            conn.execute(
                "UPDATE prompt_generation_settings SET " + ", ".join(updates) + " WHERE user_id = ?",
                params,
            )
        conn.commit()
        return get_prompt_generation_settings(user_id)
    finally:
        conn.close()


@app.get("/api/prompt-generation/runs")
def list_prompt_generation_runs(limit: int = 20, offset: int = 0, user_id: int = Depends(get_current_user_id)):
    """List prompt generation runs (scheduled or manual) with pagination."""
    conn = get_connection()
    try:
        count_row = conn.execute("SELECT COUNT(*) AS n FROM prompt_generation_runs WHERE user_id = ?", (user_id,)).fetchone()
        total = count_row["n"] if count_row else 0
        rows = conn.execute(
            """SELECT id, started_at, finished_at, trigger_type, status, inserted_count
               FROM prompt_generation_runs WHERE user_id = ? ORDER BY started_at DESC LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ).fetchall()
        runs = [dict(r) for r in rows]
        return {"runs": runs, "total": total}
    finally:
        conn.close()


@app.post("/api/prompt-generation/run")
def run_prompt_generation_now(user_id: int = Depends(get_current_user_id)):
    """Run prompt generation now and update last_run_at. Records a run in prompt_generation_runs."""
    conn = get_connection()
    try:
        from src.domains_db import discovery_done
        if not discovery_done(conn, user_id=user_id):
            raise HTTPException(
                status_code=400,
                detail="Run domain discovery first. Add domains and click Run discovery.",
            )
        conn.execute(
            "INSERT INTO prompt_generation_runs (user_id, trigger_type, status) VALUES (?, 'manual', 'running')",
            (user_id,),
        )
        run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        row = conn.execute(
            "SELECT prompts_per_domain FROM prompt_generation_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        prompts_per_domain = None
        if row and row["prompts_per_domain"] is not None:
            prompts_per_domain = int(row["prompts_per_domain"])
        try:
            inserted = _run_prompt_generation_sync(conn, user_id, prompts_per_domain, prompt_generation_run_id=run_id)
            conn.execute(
                "UPDATE prompt_generation_settings SET last_run_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,),
            )
            conn.execute(
                "UPDATE prompt_generation_runs SET finished_at = CURRENT_TIMESTAMP, status = 'finished', inserted_count = ? WHERE id = ?",
                (inserted, run_id),
            )
            conn.commit()
            return {"ok": True, "inserted": inserted, "run_id": run_id}
        except Exception as e:
            conn.execute(
                "UPDATE prompt_generation_runs SET finished_at = CURRENT_TIMESTAMP, status = 'failed' WHERE id = ?",
                (run_id,),
            )
            conn.commit()
            raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ---------- Monitoring settings and executions ----------
@app.get("/api/monitoring/settings")
def get_monitoring_settings(user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT user_id, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds, updated_at FROM monitoring_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT OR IGNORE INTO monitoring_settings (user_id, enabled) VALUES (?, 1)",
                (user_id,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT user_id, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds, updated_at FROM monitoring_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return {
                "enabled": 1,
                "frequency_minutes": None,
                "domain_ids": None,
                "models": None,
                "prompt_limit": None,
                "delay_seconds": None,
                "updated_at": None,
            }
        out = dict(row)
        for key in ("domain_ids", "models"):
            if out.get(key):
                try:
                    out[key] = __import__("json").loads(out[key])
                except (TypeError, ValueError):
                    out[key] = None
        out["enabled"] = bool(out.get("enabled", 1))
        return out
    finally:
        conn.close()


@app.put("/api/monitoring/settings")
def update_monitoring_settings(body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        domain_ids_raw = body.get("domain_ids")
        domain_ids_to_store = domain_ids_raw
        if domain_ids_raw is not None:
            domain_ids_list = domain_ids_raw if isinstance(domain_ids_raw, list) else [domain_ids_raw]
            try:
                domain_ids_list = [int(d) for d in domain_ids_list]
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="domain_ids must be a list of integers.")
            _validate_domain_ids(conn, domain_ids_list, user_id)
            domain_ids_to_store = domain_ids_list
        conn.execute(
            """INSERT INTO monitoring_settings (user_id, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                 enabled=excluded.enabled,
                 frequency_minutes=excluded.frequency_minutes,
                 domain_ids=excluded.domain_ids,
                 models=excluded.models,
                 prompt_limit=excluded.prompt_limit,
                 delay_seconds=excluded.delay_seconds,
                 updated_at=CURRENT_TIMESTAMP""",
            (
                user_id,
                1 if body.get("enabled", True) else 0,
                body.get("frequency_minutes"),
                json.dumps(domain_ids_to_store) if domain_ids_to_store is not None else None,
                __import__("json").dumps(body.get("models")) if body.get("models") is not None else None,
                body.get("prompt_limit"),
                body.get("delay_seconds"),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT user_id, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds, updated_at FROM monitoring_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        out = dict(row) if row else {}
        for key in ("domain_ids", "models"):
            if out.get(key):
                try:
                    out[key] = __import__("json").loads(out[key])
                except (TypeError, ValueError):
                    out[key] = None
        out["enabled"] = bool(out.get("enabled", 1))
        return out
    finally:
        conn.close()


# ---------- Settings: LLM provider API keys (OpenAI, Perplexity, Anthropic, Gemini) ----------
from api.validate_providers import validate_provider


def _mask_api_key(value: str | None) -> str | None:
    """Return masked value for display (e.g. sk-••••••••••xyz)."""
    if not value or not value.strip():
        return None
    s = value.strip()
    if len(s) <= 8:
        return "••••••••"
    return "••••••••••••" + s[-4:]


@app.get("/api/settings/llm-providers")
def get_llm_provider_settings(user_id: int = Depends(get_current_user_id)):
    """Return stored API keys (masked) and model names."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT openai_api_key, perplexity_api_key, anthropic_api_key, gemini_api_key,
                      openai_model, perplexity_model, anthropic_model, gemini_model, updated_at
               FROM llm_provider_settings WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        if not row:
            return {
                "openai": None,
                "perplexity": None,
                "anthropic": None,
                "gemini": None,
                "openai_model": None,
                "perplexity_model": None,
                "anthropic_model": None,
                "gemini_model": None,
                "updated_at": None,
            }
        return {
            "openai": _mask_api_key(row["openai_api_key"]),
            "perplexity": _mask_api_key(row["perplexity_api_key"]),
            "anthropic": _mask_api_key(row["anthropic_api_key"]),
            "gemini": _mask_api_key(row["gemini_api_key"]),
            "openai_model": row["openai_model"] or None,
            "perplexity_model": row["perplexity_model"] or None,
            "anthropic_model": row["anthropic_model"] or None,
            "gemini_model": row["gemini_model"] or None,
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()


@app.put("/api/settings/llm-providers")
def update_llm_provider_settings(body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    """Update stored API keys and model names. Omit a key to leave unchanged; empty string clears API key."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT openai_api_key, perplexity_api_key, anthropic_api_key, gemini_api_key,
                      openai_model, perplexity_model, anthropic_model, gemini_model
               FROM llm_provider_settings WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        current = dict(row) if row else {}
        openai = body.get("openai")
        perplexity = body.get("perplexity")
        anthropic = body.get("anthropic")
        gemini = body.get("gemini")
        openai_model = body.get("openai_model")
        perplexity_model = body.get("perplexity_model")
        anthropic_model = body.get("anthropic_model")
        gemini_model = body.get("gemini_model")
        new_openai = (openai.strip() or None) if openai is not None else current.get("openai_api_key")
        new_perplexity = (perplexity.strip() or None) if perplexity is not None else current.get("perplexity_api_key")
        new_anthropic = (anthropic.strip() or None) if anthropic is not None else current.get("anthropic_api_key")
        new_gemini = (gemini.strip() or None) if gemini is not None else current.get("gemini_api_key")
        new_openai_model = (openai_model.strip() or None) if openai_model is not None else current.get("openai_model")
        new_perplexity_model = (perplexity_model.strip() or None) if perplexity_model is not None else current.get("perplexity_model")
        new_anthropic_model = (anthropic_model.strip() or None) if anthropic_model is not None else current.get("anthropic_model")
        new_gemini_model = (gemini_model.strip() or None) if gemini_model is not None else current.get("gemini_model")
        conn.execute(
            """INSERT INTO llm_provider_settings (user_id, openai_api_key, perplexity_api_key, anthropic_api_key, gemini_api_key,
               openai_model, perplexity_model, anthropic_model, gemini_model, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                 openai_api_key=excluded.openai_api_key,
                 perplexity_api_key=excluded.perplexity_api_key,
                 anthropic_api_key=excluded.anthropic_api_key,
                 gemini_api_key=excluded.gemini_api_key,
                 openai_model=excluded.openai_model,
                 perplexity_model=excluded.perplexity_model,
                 anthropic_model=excluded.anthropic_model,
                 gemini_model=excluded.gemini_model,
                 updated_at=CURRENT_TIMESTAMP""",
            (user_id, new_openai, new_perplexity, new_anthropic, new_gemini,
             new_openai_model, new_perplexity_model, new_anthropic_model, new_gemini_model),
        )
        conn.commit()
        row = conn.execute(
            """SELECT openai_api_key, perplexity_api_key, anthropic_api_key, gemini_api_key,
                      openai_model, perplexity_model, anthropic_model, gemini_model, updated_at
               FROM llm_provider_settings WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        out = dict(row) if row else {}
        return {
            "openai": _mask_api_key(out.get("openai_api_key")),
            "perplexity": _mask_api_key(out.get("perplexity_api_key")),
            "anthropic": _mask_api_key(out.get("anthropic_api_key")),
            "gemini": _mask_api_key(out.get("gemini_api_key")),
            "openai_model": out.get("openai_model") or None,
            "perplexity_model": out.get("perplexity_model") or None,
            "anthropic_model": out.get("anthropic_model") or None,
            "gemini_model": out.get("gemini_model") or None,
            "updated_at": out.get("updated_at"),
        }
    finally:
        conn.close()


def _get_llm_settings_for_validation(user_id: int, body: dict) -> dict:
    """Merge body (form) with stored settings: body overrides stored for keys present in body."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT openai_api_key, perplexity_api_key, anthropic_api_key, gemini_api_key,
                      openai_model, perplexity_model, anthropic_model, gemini_model
               FROM llm_provider_settings WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
        stored = dict(row) if row else {}
    finally:
        conn.close()
    key_map = {
        "openai": ("openai_api_key", "openai_model"),
        "perplexity": ("perplexity_api_key", "perplexity_model"),
        "anthropic": ("anthropic_api_key", "anthropic_model"),
        "gemini": ("gemini_api_key", "gemini_model"),
    }
    out = {}
    for provider, (key_col, model_col) in key_map.items():
        raw_key = body.get(provider)
        if raw_key is None or (isinstance(raw_key, str) and not raw_key.strip()):
            api_key = (stored.get(key_col) or "").strip() if stored.get(key_col) else ""
        else:
            api_key = (raw_key or "").strip()
        model = body.get(f"{provider}_model") if f"{provider}_model" in body else stored.get(model_col)
        model = (model or "").strip() or None
        if api_key:
            out[provider] = {"api_key": api_key, "model": model}
    return out


@app.post("/api/settings/llm-providers/validate")
def validate_llm_provider_settings(body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    """Validate API key and model for each provider. Body can include openai, openai_model, etc.; missing keys use stored settings. Returns { openai: { ok: bool, error?: str }, ... } for each provider that has an API key."""
    merged = _get_llm_settings_for_validation(user_id, body)
    result = {}
    for provider, creds in merged.items():
        api_key = creds.get("api_key") or ""
        model = creds.get("model")
        if not api_key.strip():
            result[provider] = {"ok": False, "error": "API key is required"}
            continue
        ok, err = validate_provider(provider, api_key, model)
        result[provider] = {"ok": ok, "error": err} if not ok else {"ok": True}
    return result


def _run_brief_and_content_after_monitor():
    """Run brief agent (create briefs from uncited prompts) then content agent (create drafts from pending briefs)."""
    try:
        from src.gap_brief.run_brief_agent import run as run_brief
        run_brief(days=7, limit=10)
    except Exception:
        pass
    try:
        from src.content.run_content_agent import run as run_content
        run_content(limit=5)
    except Exception:
        pass


def _run_monitor_async(execution_id: int, body: dict, user_id: int | None = None):
    models = body.get("models")
    prompt_limit = body.get("prompt_limit")
    if prompt_limit is not None and prompt_limit != "":
        try:
            prompt_limit = int(prompt_limit)
        except (TypeError, ValueError):
            prompt_limit = None
    else:
        prompt_limit = None
    domain_ids = body.get("domain_ids")
    delay_seconds = body.get("delay_seconds")
    if models is not None and not isinstance(models, list):
        models = [models]
    if domain_ids is not None and not isinstance(domain_ids, list):
        domain_ids = [domain_ids]
    try:
        from src.monitor.run_monitor import run
        run(
            execution_id=execution_id,
            trigger_type="manual",
            settings_snapshot=body,
            models=models,
            limit_prompts=prompt_limit,
            domain_ids=domain_ids,
            delay_seconds=delay_seconds,
            skip_prompts_with_recent_win=True,
            user_id=user_id,
            use_queue=True,
        )
        _run_brief_and_content_after_monitor()
    except Exception:
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE monitoring_executions SET status = 'failed', finished_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (execution_id,),
            )
            conn.commit()
        finally:
            conn.close()


def _validate_domain_ids(conn, domain_ids: list[int], user_id: int) -> None:
    """Raise HTTPException 400 if any domain_id does not exist or does not belong to the user."""
    if not domain_ids:
        return
    placeholders = ",".join("?" * len(domain_ids))
    if user_id is not None:
        rows = conn.execute(
            f"SELECT id FROM domains WHERE id IN ({placeholders}) AND user_id = ?",
            (*domain_ids, user_id),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT id FROM domains WHERE id IN ({placeholders})",
            tuple(domain_ids),
        ).fetchall()
    found = {r["id"] for r in rows}
    missing = [did for did in domain_ids if did not in found]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"One or more domain IDs do not exist or do not belong to your account: {missing}. Please use valid domain IDs from your Domains list.",
        )


@app.post("/api/monitoring/run")
def run_monitoring_now(body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    """Trigger a monitoring run manually (runs in background). Optional body: models, prompt_limit, domain_ids."""
    conn = get_connection()
    try:
        domain_ids = body.get("domain_ids") if body else None
        if domain_ids is not None and not isinstance(domain_ids, list):
            domain_ids = [domain_ids]
        if domain_ids:
            try:
                domain_ids = [int(d) for d in domain_ids]
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="domain_ids must be a list of integers.")
            _validate_domain_ids(conn, domain_ids, user_id)
        conn.execute(
            """INSERT INTO monitoring_executions (user_id, trigger_type, status, settings_snapshot)
               VALUES (?, 'manual', 'running', ?)""",
            (user_id, json.dumps(body or {})),
        )
        execution_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    t = threading.Thread(target=_run_monitor_async, args=(execution_id, body or {}, user_id), daemon=True)
    t.start()
    return {"ok": True, "execution_id": execution_id}


@app.get("/api/monitoring/executions")
def list_monitoring_executions(limit: int = 20, offset: int = 0, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        count_row = conn.execute("SELECT COUNT(*) AS n FROM monitoring_executions WHERE user_id = ?", (user_id,)).fetchone()
        total = count_row["n"] if count_row else 0
        rows = conn.execute(
            """SELECT id, started_at, finished_at, trigger_type, status, settings_snapshot
               FROM monitoring_executions WHERE user_id = ? ORDER BY started_at DESC LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("settings_snapshot"):
                try:
                    d["settings_snapshot"] = __import__("json").loads(d["settings_snapshot"])
                except (TypeError, ValueError):
                    d["settings_snapshot"] = None
            out.append(d)
        return {"executions": out, "total": total}
    finally:
        conn.close()


@app.get("/api/monitoring/executions/{execution_id}")
def get_monitoring_execution(execution_id: int, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT id, started_at, finished_at, trigger_type, status, settings_snapshot
               FROM monitoring_executions WHERE id = ? AND user_id = ?""",
            (execution_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Execution not found")
        out = dict(row)
        if out.get("settings_snapshot"):
            try:
                out["settings_snapshot"] = __import__("json").loads(out["settings_snapshot"])
            except (TypeError, ValueError):
                out["settings_snapshot"] = None
        runs = conn.execute(
            """SELECT id, execution_id, model, started_at, finished_at, prompt_count, status
               FROM runs WHERE execution_id = ? ORDER BY model""",
            (execution_id,),
        ).fetchall()
        out["runs"] = [dict(r) for r in runs]
        run_ids = [r["id"] for r in out["runs"]]
        run_id_to_model = {r["id"]: r["model"] for r in out["runs"]}
        out["prompt_visibility"] = []
        if run_ids:
            placeholders = ",".join("?" * len(run_ids))
            # brand_mentioned column in run_prompt_visibility may be stale for older runs; recompute it
            # based on run_prompt_mentions (is_own_domain=1) so UI always reflects correct logic.
            vis_rows = conn.execute(
                f"""SELECT
                           v.prompt_id,
                           v.run_id,
                           v.had_own_citation,
                           CASE
                               WHEN EXISTS (
                                   SELECT 1
                                   FROM run_prompt_mentions m
                                   WHERE m.run_id = v.run_id
                                     AND m.prompt_id = v.prompt_id
                                     AND m.is_own_domain = 1
                               ) THEN 1
                               ELSE 0
                           END AS brand_mentioned_effective,
                           v.competitor_only,
                           p.text AS prompt_text,
                           p.niche AS prompt_niche
                    FROM run_prompt_visibility v
                    JOIN prompts p ON p.id = v.prompt_id
                    WHERE v.run_id IN ({placeholders})
                    ORDER BY v.prompt_id, v.run_id""",
                run_ids,
            ).fetchall()
            by_prompt = {}
            for r in vis_rows:
                pid = r["prompt_id"]
                if pid not in by_prompt:
                    by_prompt[pid] = {
                        "prompt_id": pid,
                        "text": r["prompt_text"] or "",
                        "niche": r["prompt_niche"] or "",
                        "visibility_by_run": [],
                    }
                by_prompt[pid]["visibility_by_run"].append({
                    "run_id": r["run_id"],
                    "model": run_id_to_model.get(r["run_id"], ""),
                    "had_own_citation": bool(r["had_own_citation"]),
                    "brand_mentioned": bool(r["brand_mentioned_effective"]),
                    "competitor_only": bool(r["competitor_only"]),
                })
            out["prompt_visibility"] = list(by_prompt.values())
        return out
    finally:
        conn.close()


# ---------- Trial (unauthenticated): enter website → generate prompts + run monitoring ----------
TRIAL_USER_EMAIL = "trial@llmseo.internal"


def _trial_prompts_count() -> int:
    """Number of prompts to generate and run per trial. Code default for now; env ignored."""
    return 5


def _trial_delay_seconds() -> float:
    """Delay in seconds between LLM calls during trial monitoring. From TRIAL_DELAY_SECONDS (default 3.5)."""
    try:
        n = float(os.environ.get("TRIAL_DELAY_SECONDS", "3.5").strip())
        return max(0.5, min(30.0, n))
    except (TypeError, ValueError):
        return 3.5


def _get_client_ip(request: Request) -> str:
    """Client IP for rate limiting; respects X-Forwarded-For when behind a proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def _trial_rate_limit_window_minutes() -> int:
    try:
        return max(1, int(os.environ.get("TRIAL_RATE_LIMIT_WINDOW_MINUTES", "30").strip()))
    except (TypeError, ValueError):
        return 30


def _trial_rate_limit_max_per_window() -> int:
    try:
        return max(1, int(os.environ.get("TRIAL_RATE_LIMIT_PER_IP", "1").strip()))
    except (TypeError, ValueError):
        return 1


def _trial_rate_limit_check(conn, ip: str) -> None:
    """Raise HTTPException 429 if this IP has exceeded trial rate limit."""
    init_db(conn)
    window_min = _trial_rate_limit_window_minutes()
    max_per = _trial_rate_limit_max_per_window()
    # Prune old rows (older than 2x window)
    conn.execute(
        "DELETE FROM trial_rate_limit WHERE requested_at < datetime('now', ?)",
        (f"-{min(window_min * 2, 1440)} minutes",),  # cap at 24h
    )
    conn.commit()
    row = conn.execute(
        """SELECT COUNT(*) AS cnt FROM trial_rate_limit
           WHERE ip = ? AND requested_at > datetime('now', ?)""",
        (ip, f"-{window_min} minutes"),
    ).fetchone()
    count = row["cnt"] if row else 0
    if count >= max_per:
        logger.warning(
            "trial_rate_limit_block ip=%s count=%s window_min=%s max_per=%s",
            ip,
            count,
            window_min,
            max_per,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Too many analyses. Please try again in {window_min} minutes.",
        )


def _trial_rate_limit_record(conn, ip: str) -> None:
    """Record a successful trial start for rate limiting."""
    conn.execute(
        "INSERT INTO trial_rate_limit (ip, requested_at) VALUES (?, CURRENT_TIMESTAMP)",
        (ip,),
    )
    conn.commit()


def _trial_max_queue_pending() -> int:
    """Max global pending+running LLM tasks before rejecting new trials (backpressure)."""
    try:
        return max(10, int(os.environ.get("TRIAL_MAX_QUEUE_PENDING", "80").strip()))
    except (TypeError, ValueError):
        return 80


def _trial_max_concurrent_runs() -> int:
    """Max concurrent trial executions before rejecting new trials."""
    try:
        return max(1, int(os.environ.get("TRIAL_MAX_CONCURRENT_RUNS", "15").strip()))
    except (TypeError, ValueError):
        return 15


def _trial_queue_backpressure(conn) -> None:
    """Raise HTTPException 503 if queue or concurrent trial runs are over limit."""
    init_db(conn)
    from src.monitor.llm_task_queue import get_queue_status
    status = get_queue_status(conn, execution_id=None)
    pending = status.get("pending", 0) or 0
    running = status.get("running", 0) or 0
    if (pending + running) > _trial_max_queue_pending():
        logger.warning(
            "trial_queue_block_too_many_tasks pending=%s running=%s max_pending=%s",
            pending,
            running,
            _trial_max_queue_pending(),
        )
        raise HTTPException(
            status_code=503,
            detail="Too many analyses in progress. Please try again in a few minutes.",
        )
    row = conn.execute(
        """SELECT COUNT(*) AS cnt FROM monitoring_executions
           WHERE trigger_type = 'trial' AND status = 'running'""",
        (),
    ).fetchone()
    concurrent = row["cnt"] if row else 0
    if concurrent >= _trial_max_concurrent_runs():
        logger.warning(
            "trial_queue_block_too_many_runs concurrent=%s max_concurrent=%s",
            concurrent,
            _trial_max_concurrent_runs(),
        )
        raise HTTPException(
            status_code=503,
            detail="Too many analyses in progress. Please try again in a few minutes.",
        )


def _verify_turnstile(token: str | None, remote_ip: str | None) -> None:
    """Turnstile verification temporarily disabled."""
    return


def _domain_to_slug(domain: str) -> str:
    """Convert domain to URL-safe slug for canonical trial URL (e.g. www.spydra.app -> www-spydra-app)."""
    if not domain or not isinstance(domain, str):
        return ""
    return domain.lower().strip().replace(".", "-")


def _normalize_website_to_domain(website: str) -> str | None:
    """Normalize input to a domain: strip protocol, path, lowercase, optional strip www. Returns None if invalid."""
    if not website or not isinstance(website, str):
        return None
    s = website.strip()
    if not s:
        return None
    if "://" not in s:
        s = "https://" + s
    try:
        parsed = urlparse(s)
        netloc = (parsed.netloc or "").strip().lower()
        if not netloc:
            return None
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if len(netloc) > 253:
            return None
        return netloc
    except Exception:
        return None


def _get_or_create_trial_user(conn) -> int:
    """Get or create the shared trial user. Returns user_id."""
    row = conn.execute("SELECT id FROM users WHERE email = ?", (TRIAL_USER_EMAIL,)).fetchone()
    if row:
        return row["id"]
    password_hash = hash_password("trial-internal-no-login")
    conn.execute(
        "INSERT INTO users (email, password_hash, name, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
        (TRIAL_USER_EMAIL, password_hash, "Trial"),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM users WHERE email = ?", (TRIAL_USER_EMAIL,)).fetchone()
    return row["id"]


def _run_trial_background(execution_id: int, trial_user_id: int, domain_id: int, domain: str) -> None:
    """Background thread: run monitoring for trial (reuse run_monitor.run)."""
    try:
        from src.monitor.run_monitor import run
        prompt_count = _trial_prompts_count()
        delay = _trial_delay_seconds()
        settings_snapshot = {
            "website": domain,
            "delay_seconds": delay,
            "limit_prompts": prompt_count,
            "domain_ids": [domain_id],
        }
        run(
            execution_id=execution_id,
            trigger_type="trial",
            settings_snapshot=settings_snapshot,
            user_id=trial_user_id,
            models=None,
            limit_prompts=prompt_count,
            domain_ids=[domain_id],
            delay_seconds=delay,
            skip_prompts_with_recent_win=True,
            use_queue=True,
        )
    except Exception:
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE monitoring_executions SET status = 'failed', finished_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (execution_id,),
            )
            conn.commit()
        finally:
            conn.close()


def _get_trial_discovery(conn, execution_id: int) -> dict | None:
    """Return domain discovery profile for this trial execution (website from trial_sessions, profile from domain_profiles)."""
    row = conn.execute(
        "SELECT t.website FROM trial_sessions t WHERE t.execution_id = ? LIMIT 1",
        (execution_id,),
    ).fetchone()
    if not row:
        return None
    website = (row["website"] or "").strip()
    if not website:
        return None
    exec_row = conn.execute(
        "SELECT user_id FROM monitoring_executions WHERE id = ?",
        (execution_id,),
    ).fetchone()
    if not exec_row:
        return None
    user_id = exec_row["user_id"]
    prof = conn.execute(
        """SELECT dp.category, dp.categories, dp.niche, dp.value_proposition, dp.key_topics, dp.target_audience, dp.competitors, dp.discovered_at
           FROM domain_profiles dp
           JOIN domains d ON d.id = dp.domain_id AND d.user_id = ? AND d.domain = ?""",
        (user_id, website),
    ).fetchone()
    if not prof:
        return None
    try:
        categories = json.loads(prof["categories"]) if (prof["categories"] or "").strip() else []
    except (TypeError, ValueError):
        categories = []
    try:
        competitors = json.loads(prof["competitors"]) if (prof["competitors"] or "").strip() else []
    except (TypeError, ValueError):
        competitors = []
    return {
        "category": prof["category"] or "",
        "categories": list(categories) if isinstance(categories, list) else [],
        "niche": prof["niche"] or "",
        "value_proposition": prof["value_proposition"] or "",
        "key_topics": json.loads(prof["key_topics"]) if (prof["key_topics"] or "").strip() else [],
        "target_audience": prof["target_audience"] or "",
        "competitors": list(competitors) if isinstance(competitors, list) else [],
        "discovered_at": prof["discovered_at"] or "",
    }


def _reconcile_execution_if_done(conn, execution_id: int) -> None:
    """If execution is still 'running' but has no pending/running tasks in the queue, mark it and its runs finished."""
    row = conn.execute(
        "SELECT status FROM monitoring_executions WHERE id = ?",
        (execution_id,),
    ).fetchone()
    if not row or (row["status"] or "").lower() != "running":
        return
    try:
        from src.monitor.llm_task_queue import get_queue_status
        init_db(conn)
        status = get_queue_status(conn, execution_id=execution_id)
        pending = status.get("pending", 0) or 0
        running = status.get("running", 0) or 0
        if pending > 0 or running > 0:
            return
        conn.execute(
            "UPDATE runs SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE execution_id = ?",
            (execution_id,),
        )
        conn.execute(
            "UPDATE monitoring_executions SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (execution_id,),
        )
        conn.commit()
    except Exception:
        pass


def _execution_detail_by_id(conn, execution_id: int) -> dict | None:
    """Return execution detail (same shape as get_monitoring_execution) by execution_id, no user check."""
    row = conn.execute(
        """SELECT id, started_at, finished_at, trigger_type, status, settings_snapshot
           FROM monitoring_executions WHERE id = ?""",
        (execution_id,),
    ).fetchone()
    if not row:
        return None
    out = dict(row)
    if out.get("settings_snapshot"):
        try:
            out["settings_snapshot"] = json.loads(out["settings_snapshot"])
        except (TypeError, ValueError):
            out["settings_snapshot"] = None
    runs = conn.execute(
        """SELECT id, execution_id, model, started_at, finished_at, prompt_count, status
           FROM runs WHERE execution_id = ? ORDER BY model""",
        (execution_id,),
    ).fetchall()
    out["runs"] = [dict(r) for r in runs]
    run_ids = [r["id"] for r in out["runs"]]
    run_id_to_model = {r["id"]: r["model"] for r in out["runs"]}
    out["prompt_visibility"] = []
    if run_ids:
        placeholders = ",".join("?" * len(run_ids))
        # Recompute brand_mentioned based on run_prompt_mentions (is_own_domain=1) for robustness.
        vis_rows = conn.execute(
            f"""SELECT
                       v.prompt_id,
                       v.run_id,
                       v.had_own_citation,
                       CASE
                           WHEN EXISTS (
                               SELECT 1
                               FROM run_prompt_mentions m
                               WHERE m.run_id = v.run_id
                                 AND m.prompt_id = v.prompt_id
                                 AND m.is_own_domain = 1
                           ) THEN 1
                           ELSE 0
                       END AS brand_mentioned_effective,
                       v.competitor_only,
                       p.text AS prompt_text,
                       p.niche AS prompt_niche
                FROM run_prompt_visibility v
                JOIN prompts p ON p.id = v.prompt_id
                WHERE v.run_id IN ({placeholders})
                ORDER BY v.prompt_id, v.run_id""",
            run_ids,
        ).fetchall()
        by_prompt = {}
        for r in vis_rows:
            pid = r["prompt_id"]
            if pid not in by_prompt:
                by_prompt[pid] = {
                    "prompt_id": pid,
                    "text": r["prompt_text"] or "",
                    "niche": r["prompt_niche"] or "",
                    "visibility_by_run": [],
                }
            by_prompt[pid]["visibility_by_run"].append({
                "run_id": r["run_id"],
                "model": run_id_to_model.get(r["run_id"], ""),
                "had_own_citation": bool(r["had_own_citation"]),
                "brand_mentioned": bool(r["brand_mentioned_effective"]),
                "competitor_only": bool(r["competitor_only"]),
            })
        out["prompt_visibility"] = list(by_prompt.values())
        # Citations, mentions, and LLM responses for full trial results
        cite_rows = conn.execute(
            f"""SELECT c.run_id, c.prompt_id, c.model, c.cited_domain, c.raw_snippet, c.is_own_domain
                FROM citations c WHERE c.run_id IN ({placeholders}) ORDER BY c.prompt_id, c.run_id""",
            run_ids,
        ).fetchall()
        out["citations"] = [dict(r) for r in cite_rows]
        mention_rows = conn.execute(
            f"""SELECT run_id, prompt_id, model, mentioned, is_own_domain
                FROM run_prompt_mentions WHERE run_id IN ({placeholders}) ORDER BY prompt_id, run_id""",
            run_ids,
        ).fetchall()
        out["mentions"] = [
            {
                "run_id": r["run_id"],
                "prompt_id": r["prompt_id"],
                "model": r["model"] or "",
                "mentioned": r["mentioned"] or "",
                "is_own_domain": bool(r["is_own_domain"]),
            }
            for r in mention_rows
        ]
        resp_rows = conn.execute(
            f"""SELECT prompt_id, run_id, model, response_text
                FROM run_prompt_responses WHERE run_id IN ({placeholders}) ORDER BY prompt_id, run_id""",
            run_ids,
        ).fetchall()
        out["prompt_responses"] = [
            {
                "prompt_id": r["prompt_id"],
                "run_id": r["run_id"],
                "model": r["model"] or "",
                "response_text": r["response_text"] or "",
            }
            for r in resp_rows
        ]
    else:
        out["citations"] = []
        out["mentions"] = []
        out["prompt_responses"] = []
    discovery = _get_trial_discovery(conn, execution_id)
    if discovery is not None:
        out["discovery"] = discovery
    return out


def _build_execution_pdf(execution: dict) -> bytes:
    """Build a multi-section PDF that mirrors the main monitoring/trial views."""
    if canvas is None or A4 is None or mm is None:
        raise HTTPException(status_code=500, detail="PDF generation not available")

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    x_margin = 20 * mm
    y = height - 30 * mm

    def line(text: str, size: int = 11, bold: bool = False):
        nonlocal y
        if y < 30 * mm:
            c.showPage()
            y = height - 30 * mm
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x_margin, y, text)
        y -= 6 * mm

    def para(text: str, size: int = 10, bold: bool = False, width_chars: int = 95):
        """Simple paragraph with manual wrapping."""
        if not text:
            return
        for chunk in textwrap.wrap(text, width=width_chars):
            line(chunk, size=size, bold=bold)

    # Header – execution metadata
    line("TRUSEO – Monitoring report", 14, bold=True)
    line(f"Execution ID: {execution.get('id')}", 11)
    line(f"Trigger: {execution.get('trigger_type', '')}", 11)
    line(f"Status: {execution.get('status', '')}", 11)
    line(f"Started: {execution.get('started_at', '')}", 11)
    line(f"Finished: {execution.get('finished_at', '') or '—'}", 11)
    y -= 4 * mm

    # Runs by model (like the Runs table)
    runs = execution.get("runs") or []
    if runs:
        line("Runs by model", 12, bold=True)
        for r in runs:
            para(
                f"- {r.get('model','')} · prompts: {r.get('prompt_count',0)} · status: {r.get('status','')} · started: {r.get('started_at','')}",
                size=10,
            )
        y -= 4 * mm

    # Domain discovery (trial results)
    discovery = execution.get("discovery") or {}
    if discovery:
        line("Domain discovery", 12, bold=True)
        para(f"Categories: {', '.join(discovery.get('categories') or []) or (discovery.get('category') or '—')}", 10)
        para(f"Niche: {discovery.get('niche') or '—'}", 10)
        para(f"Value proposition: {discovery.get('value_proposition') or '—'}", 10)
        para(f"Target audience: {discovery.get('target_audience') or '—'}", 10)
        para(f"Key topics: {', '.join(discovery.get('key_topics') or []) or '—'}", 10)
        competitors = discovery.get("competitors") or []
        para(f"Competitors: {', '.join(competitors) or '—'}", 10)
        y -= 4 * mm

    # Prompt visibility – per prompt and model (mirrors grid in UI)
    vis = execution.get("prompt_visibility") or []
    if vis:
        line("Prompt visibility (by prompt and model)", 12, bold=True)
        line(f"Prompts tracked in this execution: {len(vis)}", 10)
        runs_by_model = [(r.get("model", ""), r) for r in runs]
        max_prompts = 30  # keep PDFs bounded
        for idx, pv in enumerate(vis):
            if idx >= max_prompts:
                para("… (additional prompts omitted for brevity)", 9)
                break
            prompt_text = pv.get("text") or ""
            short = prompt_text if len(prompt_text) <= 110 else prompt_text[:107] + "…"
            line(f"Prompt #{pv.get('prompt_id')}:", 10, bold=True)
            para(short, 9)
            by_run_list = pv.get("visibility_by_run") or []
            by_model = {v.get("model", ""): v for v in by_run_list}
            for model, _ in runs_by_model:
                v = by_model.get(model) or {}
                flags = []
                if v.get("had_own_citation"):
                    flags.append("cited")
                if v.get("brand_mentioned"):
                    flags.append("brand mentioned")
                if v.get("competitor_only"):
                    flags.append("competitor-only")
                if not flags:
                    flags.append("no visibility")
                para(f"- {model}: {', '.join(flags)}", 9)
            y -= 2 * mm

    # Citations overview (summary similar to what you see in UI)
    citations = execution.get("citations") or []
    if citations:
        y -= 2 * mm
        line("Citations overview", 12, bold=True)
        line(f"Total citations: {len(citations)}", 10)
        counts: dict[str, int] = {}
        for c_row in citations:
            domain = (c_row.get("cited_domain") or "").strip()
            if not domain:
                continue
            counts[domain] = counts.get(domain, 0) + 1
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
        for domain, cnt in top:
            para(f"- {domain}: {cnt} citation(s)", 9)

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


def _trial_run_sync(execution_id: int, trial_user_id: int, domain_id: int, domain: str) -> None:
    """Run monitoring for trial in the current thread (sync mode). Same logic as _run_trial_background but use_queue=False."""
    from src.monitor.run_monitor import run
    prompt_count = _trial_prompts_count()
    delay = _trial_delay_seconds()
    settings_snapshot = {
        "website": domain,
        "delay_seconds": delay,
        "limit_prompts": prompt_count,
        "domain_ids": [domain_id],
    }
    run(
        execution_id=execution_id,
        trigger_type="trial",
        settings_snapshot=settings_snapshot,
        user_id=trial_user_id,
        models=None,
        limit_prompts=prompt_count,
        domain_ids=[domain_id],
        delay_seconds=delay,
        skip_prompts_with_recent_win=True,
        use_queue=False,
    )


@app.post("/api/trial/run")
def trial_run(request: Request, body: dict = Body(...)):
    """Start a trial: normalize website, add domain + minimal profile, generate 5 prompts, run monitoring. No auth.
    Rate-limited per IP; CAPTCHA required if TURNSTILE_SECRET_KEY is set; queue backpressure when busy.
    If the same domain was run in the last 7 days, returns existing results (reused). Returns token, execution_id, slug for canonical URL /try/<slug>.
    Optional body field sync=true: run discovery, prompts and monitoring in the request (blocking); response includes full execution detail so no polling needed."""
    website = (body.get("website") or "").strip()
    sync_mode = body.get("sync") in (True, "true", "1")
    client_ip = _get_client_ip(request)
    logger.info("trial_run_start ip=%s website=%s", client_ip, website)
    domain = _normalize_website_to_domain(website)
    if not domain:
        logger.warning("trial_run_invalid_website ip=%s website=%s", client_ip, website)
        raise HTTPException(status_code=400, detail="Invalid or missing website")
    conn = get_connection()
    try:
        init_db(conn)
        _trial_rate_limit_check(conn, client_ip)
        _verify_turnstile(body.get("captcha_token"), client_ip)
    except HTTPException:
        conn.close()
        raise
    # Verify the site exists before creating profile or running AI (normal website crawl check)
    try:
        from src.domain_discovery.crawl import check_domain_reachable
        ok, err_msg = check_domain_reachable(domain)
        if not ok:
            logger.warning(
                "trial_run_unreachable_domain ip=%s domain=%s error=%s",
                client_ip,
                domain,
                err_msg,
            )
            raise HTTPException(status_code=400, detail=err_msg or "Domain does not exist or is not reachable. Please check the URL and try again.")
    except HTTPException:
        conn.close()
        raise
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Could not verify domain: {e!s}")
    slug = _domain_to_slug(domain)
    logger.info("trial_run_domain_ok ip=%s domain=%s slug=%s", client_ip, domain, slug)
    try:
        # Reuse finished result for this slug if within 7 days
        cur = conn.execute(
            """SELECT t.execution_id FROM trial_sessions t
               JOIN monitoring_executions e ON e.id = t.execution_id
               WHERE t.slug = ? AND e.status = 'finished' AND e.finished_at >= datetime('now', '-7 days')
               ORDER BY e.finished_at DESC LIMIT 1""",
            (slug,),
        )
        row = cur.fetchone()
        if row:
            execution_id = row["execution_id"]
            logger.info(
                "trial_run_reuse_execution ip=%s domain=%s slug=%s execution_id=%s",
                client_ip,
                domain,
                slug,
                execution_id,
            )
            token = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO trial_sessions (token, website, slug, execution_id) VALUES (?, ?, ?, ?)",
                (token, domain, slug, execution_id),
            )
            conn.commit()
            _trial_rate_limit_record(conn, client_ip)
            discovery = _get_trial_discovery(conn, execution_id)
            out = {"token": token, "execution_id": execution_id, "slug": slug, "reused": True}
            if discovery:
                out["discovery"] = discovery
            if body.get("sync") in (True, "true", "1"):
                detail = _execution_detail_by_id(conn, execution_id)
                if detail is not None:
                    detail["slug"] = slug
                out["execution"] = detail
            conn.close()
            return out
        _trial_queue_backpressure(conn)
        trial_user_id = _get_or_create_trial_user(conn)
        conn.execute(
            "INSERT OR IGNORE INTO domains (user_id, domain, brand_names, updated_at) VALUES (?, ?, '[]', CURRENT_TIMESTAMP)",
            (trial_user_id, domain),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM domains WHERE user_id = ? AND domain = ?",
            (trial_user_id, domain),
        ).fetchone()
        if not row:
            logger.error(
                "trial_run_missing_domain_row ip=%s domain=%s trial_user_id=%s",
                client_ip,
                domain,
                trial_user_id,
            )
            raise HTTPException(status_code=500, detail="Internal error: domain row not found after insert.")
        domain_id = row["id"]
        from src.domain_discovery.run_discovery import run_discovery_for_domain
        logger.info(
            "trial_run_start_discovery ip=%s domain_id=%s domain=%s",
            client_ip,
            domain_id,
            domain,
        )
        run_discovery_for_domain(conn, domain_id)
        row = conn.execute(
            """SELECT dp.category, dp.categories, dp.niche, dp.value_proposition, dp.key_topics, dp.target_audience, dp.competitors, dp.discovered_at
               FROM domain_profiles dp WHERE dp.domain_id = ?""",
            (domain_id,),
        ).fetchone()
        discovery = None
        if row:
            try:
                categories = json.loads(row["categories"]) if (row["categories"] or "").strip() else []
            except (TypeError, ValueError):
                categories = []
            try:
                competitors = json.loads(row["competitors"]) if (row["competitors"] or "").strip() else []
            except (TypeError, ValueError):
                competitors = []
            discovery = {
                "category": row["category"] or "",
                "categories": list(categories) if isinstance(categories, list) else [],
                "niche": row["niche"] or "",
                "value_proposition": row["value_proposition"] or "",
                "key_topics": json.loads(row["key_topics"]) if (row["key_topics"] or "").strip() else [],
                "target_audience": row["target_audience"] or "",
                "competitors": list(competitors) if isinstance(competitors, list) else [],
                "discovered_at": row["discovered_at"] or "",
            }
        inserted = _run_prompt_generation_sync(conn, trial_user_id, prompts_per_domain=_trial_prompts_count())
        logger.info(
            "trial_run_prompt_generation ip=%s domain=%s trial_user_id=%s prompts_inserted=%s",
            client_ip,
            domain,
            trial_user_id,
            inserted,
        )
        if inserted == 0:
            from src.monitor.query_runner import get_available_models
            from src.monitor.prompt_generator import load_domain_profiles
            profiles = load_domain_profiles(conn=conn, user_id=trial_user_id)
            if not profiles:
                raise HTTPException(status_code=400, detail="Could not create domain profile")
            if not get_available_models():
                raise HTTPException(status_code=503, detail="Trial is not available right now. No API keys configured.")
            raise HTTPException(status_code=503, detail="Trial is not available right now. Prompt generation failed.")
        prompt_count = _trial_prompts_count()
        delay = _trial_delay_seconds()
        settings_snapshot = {
            "website": domain,
            "delay_seconds": delay,
            "limit_prompts": prompt_count,
            "domain_ids": [domain_id],
        }
        conn.execute(
            """INSERT INTO monitoring_executions (user_id, trigger_type, status, settings_snapshot)
               VALUES (?, 'trial', 'running', ?)""",
            (trial_user_id, json.dumps(settings_snapshot)),
        )
        execution_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        logger.info(
            "trial_run_execution_created ip=%s domain=%s execution_id=%s",
            client_ip,
            domain,
            execution_id,
        )
        token = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO trial_sessions (token, website, slug, execution_id) VALUES (?, ?, ?, ?)",
            (token, domain, slug, execution_id),
        )
        conn.commit()
        _trial_rate_limit_record(conn, client_ip)

        if sync_mode:
            conn.close()
            logger.info(
                "trial_run_sync_start ip=%s domain=%s execution_id=%s",
                client_ip,
                domain,
                execution_id,
            )
            try:
                _trial_run_sync(execution_id, trial_user_id, domain_id, domain)
            except Exception as e:
                logger.exception("trial_run_sync_error ip=%s domain=%s execution_id=%s", client_ip, domain, execution_id)
                conn = get_connection()
                try:
                    conn.execute(
                        """UPDATE monitoring_executions SET status = 'failed', finished_at = CURRENT_TIMESTAMP WHERE id = ?""",
                        (execution_id,),
                    )
                    conn.commit()
                finally:
                    conn.close()
                raise HTTPException(status_code=500, detail=f"Trial run failed: {e!s}")
            conn = get_connection()
            try:
                detail = _execution_detail_by_id(conn, execution_id)
                if detail is not None:
                    detail["slug"] = slug
                out = {"token": token, "execution_id": execution_id, "slug": slug, "reused": False, "execution": detail}
                if discovery is not None:
                    out["discovery"] = discovery
                return out
            finally:
                conn.close()
        else:
            t = threading.Thread(
                target=_run_trial_background,
                args=(execution_id, trial_user_id, domain_id, domain),
                daemon=True,
            )
            t.start()
            logger.info(
                "trial_run_background_started ip=%s domain=%s execution_id=%s",
                client_ip,
                domain,
                execution_id,
            )
            out = {"token": token, "execution_id": execution_id, "slug": slug, "reused": False}
            if discovery is not None:
                out["discovery"] = discovery
            return out
    except HTTPException as e:
        logger.warning(
            "trial_run_http_error ip=%s domain=%s detail=%s status=%s",
            client_ip,
            domain,
            getattr(e, "detail", None),
            e.status_code,
        )
        raise
    except Exception as e:
        logger.exception("trial_run_unexpected_error ip=%s domain=%s", client_ip, domain)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/reports/executions/{execution_id}.pdf")
def download_execution_report(execution_id: int, user_id: int = Depends(get_current_user_id)):
    """Download a PDF summary report for a monitoring execution (authenticated)."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM monitoring_executions WHERE id = ? AND user_id = ?",
            (execution_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Execution not found")
        detail = _execution_detail_by_id(conn, execution_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Execution not found")
        pdf_bytes = _build_execution_pdf(detail)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="truseo-execution-{execution_id}.pdf"'
            },
        )
    finally:
        conn.close()


@app.get("/api/trial/report/{slug}.pdf")
def download_trial_report(slug: str):
    """Download a PDF summary report for a public trial execution (by slug, no auth)."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT t.execution_id FROM trial_sessions t
               JOIN monitoring_executions e ON e.id = t.execution_id
               WHERE t.slug = ? AND e.status = 'finished'
               ORDER BY e.finished_at DESC LIMIT 1""",
            (slug.strip(),),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Trial result not found")
        detail = _execution_detail_by_id(conn, row["execution_id"])
        if not detail:
            raise HTTPException(status_code=404, detail="Trial result not found")
        pdf_bytes = _build_execution_pdf(detail)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename=\"truseo-trial-{slug}.pdf\"'
            },
        )
    finally:
        conn.close()


@app.get("/api/queue/status")
def queue_status(
    token: str | None = Query(None, description="Trial token to get queue status for that execution"),
    execution_id: int | None = Query(None, description="Execution ID to get queue status for"),
):
    """Return LLM task queue stats (pending/done/failed). Use to debug stuck runs. No auth."""
    conn = get_connection()
    try:
        init_db(conn)
        eid = execution_id
        if eid is None and token:
            row = conn.execute(
                "SELECT execution_id FROM trial_sessions WHERE token = ?",
                (token.strip(),),
            ).fetchone()
            if row:
                eid = row["execution_id"]
        from src.monitor.llm_task_queue import get_queue_status
        status = get_queue_status(conn, execution_id=eid)
        if status.get("pending", 0) > 0:
            status["hint"] = "Pending tasks are processed by the queue worker. If runs are stuck, start it: python3 -m src.monitor.llm_task_queue"
        return status
    finally:
        conn.close()


@app.get("/api/trial/status")
def trial_status(token: str = Query(..., alias="token")):
    """Get trial execution status by token. No auth. Returns same shape as GET /api/monitoring/executions/{id}."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT execution_id FROM trial_sessions WHERE token = ?",
            (token,),
        ).fetchone()
        if not row:
            logger.warning("trial_status_token_not_found token_prefix=%s", (token[:8] + "…") if token and len(token) > 8 else token)
            raise HTTPException(status_code=404, detail="Trial session not found")
        execution_id = row["execution_id"]
        _reconcile_execution_if_done(conn, execution_id)
        out = _execution_detail_by_id(conn, execution_id)
        if not out:
            logger.warning("trial_status_execution_not_found execution_id=%s", execution_id)
            raise HTTPException(status_code=404, detail="Execution not found")
        logger.info("trial_status_ok execution_id=%s status=%s", execution_id, out.get("status"))
        return out
    finally:
        conn.close()


@app.get("/api/trial/by-slug/{slug}")
def trial_by_slug(slug: str):
    """Get the latest finished trial result for this slug (canonical URL). Only returns results from the last 7 days. No auth."""
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT t.execution_id FROM trial_sessions t
               JOIN monitoring_executions e ON e.id = t.execution_id
               WHERE t.slug = ? AND e.status = 'finished' AND e.finished_at >= datetime('now', '-7 days')
               ORDER BY e.finished_at DESC LIMIT 1""",
            (slug.strip(),),
        ).fetchone()
        if not row:
            running_row = conn.execute(
                """SELECT t.execution_id FROM trial_sessions t
                   JOIN monitoring_executions e ON e.id = t.execution_id
                   WHERE t.slug = ? AND e.status = 'running'
                   ORDER BY e.started_at DESC LIMIT 1""",
                (slug.strip(),),
            ).fetchone()
            if running_row:
                _reconcile_execution_if_done(conn, running_row["execution_id"])
                row = conn.execute(
                    """SELECT t.execution_id FROM trial_sessions t
                       JOIN monitoring_executions e ON e.id = t.execution_id
                       WHERE t.slug = ? AND e.status = 'finished' AND e.finished_at >= datetime('now', '-7 days')
                       ORDER BY e.finished_at DESC LIMIT 1""",
                    (slug.strip(),),
                ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No recent results for this domain")
        out = _execution_detail_by_id(conn, row["execution_id"])
        if not out:
            raise HTTPException(status_code=404, detail="Execution not found")
        return out
    finally:
        conn.close()


@app.get("/api/trial/directory")
def trial_directory(
    q: str | None = Query(None, description="Search by domain or slug"),
    category: str | None = Query(None, description="Filter by category text"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List trial results (slug, website, finished_at, categories). No auth. Supports server-side search and pagination."""
    conn = get_connection()
    try:
        params: list[object] = []
        where_clauses = ["e.status = 'finished'"]
        if q:
            q_like = f"%{q.lower().strip()}%"
            where_clauses.append("(LOWER(t.website) LIKE ? OR LOWER(t.slug) LIKE ?)")
            params.extend([q_like, q_like])

        base_sql = f"""
            SELECT t.slug, t.website, MAX(e.finished_at) AS finished_at
            FROM trial_sessions t
            JOIN monitoring_executions e ON e.id = t.execution_id
            WHERE {' AND '.join(where_clauses)}
            GROUP BY t.slug
        """

        # Total count (before pagination, before category filter)
        count_sql = f"SELECT COUNT(*) AS n FROM ({base_sql}) sub"
        total_row = conn.execute(count_sql, params).fetchone()
        total_base = int(total_row["n"] if total_row and total_row["n"] is not None else 0)

        base_rows = conn.execute(
            base_sql + " ORDER BY finished_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()

        trials: list[dict] = []
        for r in base_rows:
            slug = r["slug"]
            website = r["website"]
            # Get discovery categories for this slug's latest execution (if available)
            disc = None
            exec_row = conn.execute(
                """SELECT e.id FROM trial_sessions t
                   JOIN monitoring_executions e ON e.id = t.execution_id
                   WHERE t.slug = ? AND e.status = 'finished'
                   ORDER BY e.finished_at DESC LIMIT 1""",
                (slug,),
            ).fetchone()
            if exec_row:
                disc = _get_trial_discovery(conn, exec_row["id"])
            cats = disc.get("categories") if disc else None
            primary_cat = disc.get("category") if disc else None
            item = {
                "slug": slug,
                "website": website,
                "finished_at": r["finished_at"],
                "categories": cats or [],
                "category": primary_cat or (cats[0] if cats else None),
            }
            trials.append(item)

        # Optional category filter (applied after pagination since it depends on discovery JSON)
        if category:
            c_lower = category.lower().strip()
            trials = [
                t
                for t in trials
                if any(c_lower in (c or "").lower() for c in (t.get("categories") or []))
                or c_lower in (t.get("category") or "").lower()
            ]

        # total_base is total rows matching domain/slug search; category filter may reduce this page
        return {"trials": trials, "total": total_base}
    finally:
        conn.close()


@app.get("/api/citations/trends")
def get_citation_trends(run_limit: int = 30, user_id: int = Depends(get_current_user_id)):
    """Citation rate over time, by model."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT r.id, r.model, r.started_at, r.prompt_count,
                   (SELECT COUNT(DISTINCT c.prompt_id) FROM citations c WHERE c.run_id = r.id AND c.is_own_domain = 1) AS cited_count
            FROM runs r
            JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
            WHERE r.status = 'finished' AND r.prompt_count > 0
            ORDER BY r.started_at DESC
            LIMIT ?
        """, (user_id, run_limit)).fetchall()
        out = []
        for r in rows:
            rate = (r["cited_count"] / r["prompt_count"] * 100) if r["prompt_count"] else 0
            out.append({
                "run_id": r["id"],
                "model": r["model"],
                "started_at": r["started_at"],
                "prompt_count": r["prompt_count"],
                "cited_prompt_count": r["cited_count"],
                "citation_rate_pct": round(rate, 2),
            })
        return {"runs": out}
    finally:
        conn.close()


@app.get("/api/prompts/visibility")
def get_prompts_visibility(
    run_id: int | None = None,
    limit: int = 200,
    competitor_only: bool | None = None,
    user_id: int = Depends(get_current_user_id),
):
    """Prompts with visibility: cited, brand_mentioned, competitor_only in latest run(s). competitor_only=true returns only prompts where answer was competitor-only."""
    conn = get_connection()
    try:
        if run_id:
            row = conn.execute(
                "SELECT r.id FROM runs r JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ? WHERE r.id = ?",
                (user_id, run_id),
            ).fetchone()
            run_ids = [row["id"]] if row else []
        else:
            run_ids = [r["id"] for r in conn.execute(
                """SELECT r.id FROM runs r
                   JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
                   WHERE r.status = 'finished' ORDER BY r.started_at DESC LIMIT 3""",
                (user_id,),
            ).fetchall()]
        if not run_ids:
            return {"prompts": [], "run_ids": []}

        placeholders = ",".join("?" * len(run_ids))
        q = f"""
            SELECT p.id, p.text,
                   MAX(CASE WHEN c.id IS NOT NULL AND c.is_own_domain = 1 THEN 1 ELSE 0 END) AS cited,
                   MAX(v.brand_mentioned) AS brand_mentioned,
                   MAX(v.competitor_only) AS competitor_only
            FROM prompts p
            LEFT JOIN citations c ON c.prompt_id = p.id AND c.run_id IN ({placeholders}) AND c.is_own_domain = 1
            LEFT JOIN run_prompt_visibility v ON v.prompt_id = p.id AND v.run_id IN ({placeholders})
            WHERE p.user_id = ?
            GROUP BY p.id
        """
        if competitor_only is True:
            q += " HAVING MAX(v.competitor_only) = 1"
        q += " ORDER BY p.id LIMIT ?"
        params = list(run_ids) + list(run_ids) + [user_id, limit]
        rows = conn.execute(q, params).fetchall()
        return {
            "run_ids": run_ids,
            "prompts": [
                {
                    "id": r["id"],
                    "text": r["text"],
                    "cited": bool(r["cited"]),
                    "brand_mentioned": bool(r["brand_mentioned"]),
                    "competitor_only": bool(r["competitor_only"]),
                }
                for r in rows
            ],
        }
    finally:
        conn.close()


@app.get("/api/runs")
def get_runs(limit: int = 20, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT r.id, r.model, r.started_at, r.finished_at, r.prompt_count, r.status
            FROM runs r
            JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
            ORDER BY r.started_at DESC LIMIT ?
        """, (user_id, limit)).fetchall()
        return {"runs": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/citations")
def get_citations(
    run_id: int | None = None,
    prompt_id: int | None = None,
    own_only: bool | None = None,
    limit: int = 500,
    user_id: int = Depends(get_current_user_id),
):
    """Citations: own_only=true for our domain only, own_only=false for other websites only, omit for all."""
    conn = get_connection()
    try:
        q = """SELECT c.run_id, c.prompt_id, c.model, c.cited_domain, c.raw_snippet, c.is_own_domain, c.created_at
                FROM citations c
                JOIN runs r ON r.id = c.run_id
                JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
                WHERE 1=1"""
        params = [user_id]
        if run_id:
            q += " AND c.run_id = ?"
            params.append(run_id)
        if prompt_id:
            q += " AND c.prompt_id = ?"
            params.append(prompt_id)
        if own_only is not None:
            q += " AND c.is_own_domain = ?"
            params.append(1 if own_only else 0)
        q += " ORDER BY c.created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        return {"citations": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/briefs")
def get_briefs(limit: int = 50, status: str | None = None, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        q = """SELECT b.id, b.prompt_id, b.topic, b.angle, b.priority_score, b.suggested_headings,
                     b.entities_to_mention, b.schema_to_add, b.image_prompts, b.image_urls, b.status, b.created_at,
                     (SELECT id FROM drafts WHERE brief_id = b.id ORDER BY id DESC LIMIT 1) AS draft_id
               FROM content_briefs b WHERE b.user_id = ?"""
        params = [user_id]
        if status:
            q += " AND b.status = ?"
            params.append(status)
        q += " ORDER BY b.priority_score DESC, b.id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("draft_id") is not None:
                d["draft"] = {"id": d["draft_id"]}
            else:
                d["draft"] = None
            del d["draft_id"]
            out.append(d)
        return {"briefs": out}
    finally:
        conn.close()


@app.get("/api/drafts")
def get_drafts(limit: int = 50, status: str | None = None, user_id: int = Depends(get_current_user_id)):
    conn = get_connection()
    try:
        q = "SELECT id, brief_id, title, slug, body_md, status, created_at, updated_at, published_at, published_url, verification_status, image_urls FROM drafts WHERE user_id = ?"
        params = [user_id]
        if status:
            q += " AND status = ?"
            params.append(status)
        q += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        return {"drafts": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/drafts/{draft_id}")
def get_draft_by_id(draft_id: int, user_id: int = Depends(get_current_user_id)):
    """Full draft detail with linked brief and prompt."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, brief_id, title, slug, body_md, body_html, schema_json, status, created_at, updated_at, published_at, published_url, verification_status, verified_at, image_urls FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Draft not found")
        out = dict(row)
        if row["brief_id"]:
            brief = conn.execute(
                "SELECT id, prompt_id, topic, angle, priority_score, suggested_headings, entities_to_mention, schema_to_add, image_prompts, image_urls, status, created_at FROM content_briefs WHERE id = ?",
                (row["brief_id"],),
            ).fetchone()
            out["brief"] = dict(brief) if brief else None
            if brief and brief["prompt_id"]:
                prompt = conn.execute("SELECT id, text, niche, created_at FROM prompts WHERE id = ?", (brief["prompt_id"],)).fetchone()
                out["prompt"] = dict(prompt) if prompt else None
            else:
                out["prompt"] = None
        else:
            out["brief"] = None
            out["prompt"] = None
        pub_rows = conn.execute(
            """SELECT dp.id, dp.draft_id, dp.content_source_id, dp.published_url, dp.status, dp.error_message, dp.published_at, dp.created_at,
                      cs.name AS content_source_name, cs.type AS content_source_type
               FROM draft_publications dp
               LEFT JOIN content_sources cs ON cs.id = dp.content_source_id
               WHERE dp.draft_id = ? ORDER BY dp.created_at DESC""",
            (draft_id,),
        ).fetchall()
        out["publications"] = [
            {
                "id": r["id"],
                "content_source_id": r["content_source_id"],
                "content_source_name": r["content_source_name"],
                "content_source_type": r["content_source_type"],
                "published_url": r["published_url"],
                "status": r["status"],
                "error_message": r["error_message"],
                "published_at": r["published_at"],
                "created_at": r["created_at"],
            }
            for r in pub_rows
        ]
        return out
    finally:
        conn.close()


@app.put("/api/drafts/{draft_id}")
def update_draft(draft_id: int, body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    """Update draft title, body_md, slug. Body: title?, body_md?, slug?."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM drafts WHERE id = ? AND user_id = ?", (draft_id, user_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Draft not found")
        updates = []
        params = []
        if "title" in body and body["title"] is not None:
            updates.append("title = ?")
            params.append(str(body["title"]).strip())
        if "body_md" in body and body["body_md"] is not None:
            updates.append("body_md = ?")
            params.append(str(body["body_md"]))
        if "slug" in body and body["slug"] is not None:
            updates.append("slug = ?")
            params.append(str(body["slug"]).strip() or None)
        if "image_urls" in body and body["image_urls"] is not None:
            urls = body["image_urls"]
            updates.append("image_urls = ?")
            params.append(json.dumps(urls) if isinstance(urls, list) else str(urls))
        if updates:
            params.append(draft_id)
            conn.execute(
                "UPDATE drafts SET " + ", ".join(updates) + ", updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                params,
            )
            conn.commit()
        row = conn.execute(
            "SELECT id, brief_id, title, slug, body_md, body_html, status, created_at, updated_at, image_urls FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.post("/api/drafts/{draft_id}/publish")
def publish_draft_to_source(draft_id: int, body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    """Publish draft to a content source. Body: content_source_id (int), optional title, body_md. Uses provided content or draft's saved content. Records to draft_publications."""
    content_source_id = body.get("content_source_id")
    if content_source_id is None:
        raise HTTPException(status_code=400, detail="content_source_id is required")
    try:
        content_source_id = int(content_source_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="content_source_id must be an integer")
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, title, slug, body_md FROM drafts WHERE id = ? AND user_id = ?", (draft_id, user_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Draft not found")
        title = body.get("title")
        body_md = body.get("body_md")
        if title is not None:
            title = str(title).strip()
        if body_md is not None:
            body_md = str(body_md)
        use_title = title if (title is not None and title) else (row["title"] or "")
        use_body_md = body_md if body_md is not None else (row["body_md"] or "")
        slug = row["slug"] or ""
        src_row = conn.execute(
            "SELECT id, name, type, config FROM content_sources WHERE id = ? AND user_id = ?", (content_source_id, user_id)
        ).fetchone()
        if not src_row:
            raise HTTPException(status_code=404, detail="Content source not found")
        dest = (src_row["type"] or "").strip().lower()
        source_config = None
        if src_row["config"]:
            try:
                source_config = json.loads(src_row["config"])
                if isinstance(source_config, dict):
                    source_config = {k: v for k, v in source_config.items() if k != "_type"}
            except (TypeError, ValueError):
                pass
        use_body_md = _rewrite_image_urls_in_markdown(use_body_md or "")
        try:
            import markdown as md
            html = md.markdown(use_body_md or "")
        except ImportError:
            html = (use_body_md or "").replace("\n", "<p>")
        from src.content.cms import publish_draft as cms_publish_draft
        try:
            ok, published_url, err_msg = cms_publish_draft(
                draft_id, html, use_title, slug,
                destination=dest, source_config=source_config,
                body_md=use_body_md,
            )
        except Exception as e:
            ok, published_url, err_msg = False, None, str(e)
        pub_status = "published" if ok else "failed"
        conn.execute(
            """INSERT INTO draft_publications (draft_id, content_source_id, published_url, status, error_message, published_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (draft_id, content_source_id, published_url, pub_status, err_msg, None),
        )
        if ok:
            conn.execute(
                "UPDATE draft_publications SET published_at = CURRENT_TIMESTAMP WHERE id = last_insert_rowid()",
                (),
            )
        conn.commit()
        if not ok:
            raise HTTPException(status_code=400, detail=err_msg or "Publish failed")
        if title is not None or body_md is not None:
            conn.execute(
                "UPDATE drafts SET title = ?, body_md = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (use_title, use_body_md, draft_id),
            )
        conn.execute(
            """UPDATE drafts SET status = 'published', published_at = CURRENT_TIMESTAMP,
               published_url = COALESCE(?, published_url), updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (published_url, draft_id),
        )
        conn.commit()
        try:
            from src.distribution.learning_loop import compute_and_store_uplift_for_draft
            compute_and_store_uplift_for_draft(draft_id, conn=conn)
        except Exception:
            pass
        return {"ok": True, "published_url": published_url}
    finally:
        conn.close()


IMAGES_DIR = Path(__file__).resolve().parents[1] / "data" / "images"


@app.get("/api/images/{filename}")
def serve_image(filename: str):
    """Serve generated images from data/images/. Filename must be a single segment (no path traversal)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = (IMAGES_DIR / filename).resolve()
    if not path.is_file() or not str(path).startswith(str(IMAGES_DIR.resolve())):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path, media_type="image/png")


@app.post("/api/briefs/{brief_id}/generate-images")
def generate_brief_images(brief_id: int, user_id: int = Depends(get_current_user_id)):
    """Generate images from brief's image_prompts (OpenAI DALL·E), save to data/images, update brief.image_urls."""
    import json
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, topic, image_prompts, image_urls FROM content_briefs WHERE id = ? AND user_id = ?",
            (brief_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Brief not found")
        raw = row["image_prompts"]
        if not raw:
            raise HTTPException(status_code=400, detail="No image_prompts on this brief. Add prompts in the brief first.")
        try:
            prompts = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="Invalid image_prompts JSON")
        if not isinstance(prompts, list) or not prompts:
            raise HTTPException(status_code=400, detail="image_prompts is empty")
        from src.content.image_gen import generate_images_for_brief
        paths = generate_images_for_brief(brief_id, prompts[:5])
        if not paths:
            return {"ok": False, "error": "Image generation failed. Check OPENAI_API_KEY and prompt content."}
        paths_json = json.dumps(paths)
        conn.execute(
            "UPDATE content_briefs SET image_urls = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (paths_json, brief_id),
        )
        conn.execute(
            "UPDATE drafts SET image_urls = ?, updated_at = CURRENT_TIMESTAMP WHERE brief_id = ?",
            (paths_json, brief_id),
        )
        conn.commit()
        return {"ok": True, "image_urls": paths}
    finally:
        conn.close()


@app.get("/api/briefs/{brief_id}")
def get_brief_by_id(brief_id: int, user_id: int = Depends(get_current_user_id)):
    """Full brief detail with linked prompt."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, prompt_id, topic, angle, priority_score, suggested_headings, entities_to_mention, schema_to_add, image_prompts, image_urls, status, created_at FROM content_briefs WHERE id = ? AND user_id = ?",
            (brief_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Brief not found")
        out = dict(row)
        if row["prompt_id"]:
            prompt = conn.execute("SELECT id, text, niche, created_at FROM prompts WHERE id = ?", (row["prompt_id"],)).fetchone()
            out["prompt"] = dict(prompt) if prompt else None
        else:
            out["prompt"] = None
        draft = conn.execute("SELECT id, title, slug, status, created_at FROM drafts WHERE brief_id = ? ORDER BY id DESC LIMIT 1", (brief_id,)).fetchone()
        out["draft"] = dict(draft) if draft else None
        return out
    finally:
        conn.close()


@app.get("/api/prompts")
def get_prompts(
    limit: int = 100,
    offset: int = 0,
    niche: str | None = None,
    competitor_only: bool | None = None,
    run_id: int | None = None,
    prompt_generation_run_id: int | None = Query(None, description="Filter by prompt generation run ID"),
    user_id: int = Depends(get_current_user_id),
):
    """List prompts with pagination. competitor_only=true and run_id=X return only prompts that were competitor-only in that run. prompt_generation_run_id filters to prompts created in that run."""
    conn = get_connection()
    try:
        base_q = "SELECT id, text, niche, created_at FROM prompts WHERE user_id = ?"
        params = [user_id]
        if niche:
            base_q += " AND niche LIKE ?"
            params.append(f"%{niche}%")
        if competitor_only is True and run_id is not None:
            base_q += " AND id IN (SELECT prompt_id FROM run_prompt_visibility WHERE run_id = ? AND competitor_only = 1)"
            params.append(run_id)
        if prompt_generation_run_id is not None:
            base_q += " AND prompt_generation_run_id = ?"
            params.append(prompt_generation_run_id)
        count_q = "SELECT COUNT(*) AS n FROM prompts WHERE user_id = ?"
        count_params = [user_id]
        if niche:
            count_q += " AND niche LIKE ?"
            count_params.append(f"%{niche}%")
        if competitor_only is True and run_id is not None:
            count_q += " AND id IN (SELECT prompt_id FROM run_prompt_visibility WHERE run_id = ? AND competitor_only = 1)"
            count_params.append(run_id)
        if prompt_generation_run_id is not None:
            count_q += " AND prompt_generation_run_id = ?"
            count_params.append(prompt_generation_run_id)
        count_row = conn.execute(count_q, count_params).fetchone()
        total = count_row["n"] if count_row else 0
        q = base_q + " ORDER BY id DESC LIMIT ? OFFSET ?"
        params_ext = params + [limit, offset]
        rows = conn.execute(q, params_ext).fetchall()
        prompts = [dict(r) for r in rows]
        if not prompts:
            return {"prompts": [], "total": total}
        prompt_ids = [p["id"] for p in prompts]
        placeholders = ",".join("?" * len(prompt_ids))
        count_rows = conn.execute(
            """
            SELECT prompt_id, model, is_own_domain, COUNT(*) AS cnt
            FROM citations
            WHERE prompt_id IN (""" + placeholders + """)
            GROUP BY prompt_id, model, is_own_domain
            """,
            prompt_ids,
        ).fetchall()
        mention_count_rows = conn.execute(
            """
            SELECT prompt_id, model, is_own_domain, COUNT(*) AS cnt
            FROM run_prompt_mentions
            WHERE prompt_id IN (""" + placeholders + """)
            GROUP BY prompt_id, model, is_own_domain
            """,
            prompt_ids,
        ).fetchall()
        competitor_mention_rows = conn.execute(
            """
            SELECT prompt_id, mentioned FROM run_prompt_mentions
            WHERE prompt_id IN (""" + placeholders + """) AND is_own_domain = 0
            """,
            prompt_ids,
        ).fetchall()
        default_counts = {k: {"own": 0, "other": 0} for k in ["openai", "anthropic", "perplexity", "gemini"]}
        competitors_by_prompt: dict[int, list[str]] = {pid: [] for pid in prompt_ids}
        seen_per_prompt: dict[int, set[str]] = {pid: set() for pid in prompt_ids}
        for r in competitor_mention_rows:
            pid = r["prompt_id"]
            m = (r["mentioned"] or "").strip()
            if m and m.lower() not in seen_per_prompt.get(pid, set()):
                seen_per_prompt.setdefault(pid, set()).add(m.lower())
                competitors_by_prompt.setdefault(pid, []).append(m)
        counts_by_prompt = {pid: {k: {"own": 0, "other": 0} for k in default_counts} for pid in prompt_ids}
        mention_counts_by_prompt = {pid: {k: {"own": 0, "other": 0} for k in default_counts} for pid in prompt_ids}
        for r in count_rows:
            pid = r["prompt_id"]
            model = (r["model"] or "").lower() or "other"
            is_own = 1 if r["is_own_domain"] else 0
            cnt = r["cnt"]
            if pid not in counts_by_prompt:
                counts_by_prompt[pid] = {k: {"own": 0, "other": 0} for k in default_counts}
            if model not in counts_by_prompt[pid]:
                counts_by_prompt[pid][model] = {"own": 0, "other": 0}
            key = "own" if is_own else "other"
            counts_by_prompt[pid][model][key] = cnt
        for r in mention_count_rows:
            pid = r["prompt_id"]
            model = (r["model"] or "").lower() or "other"
            is_own = 1 if r["is_own_domain"] else 0
            cnt = r["cnt"]
            if pid not in mention_counts_by_prompt:
                mention_counts_by_prompt[pid] = {k: {"own": 0, "other": 0} for k in default_counts}
            if model not in mention_counts_by_prompt[pid]:
                mention_counts_by_prompt[pid][model] = {"own": 0, "other": 0}
            key = "own" if is_own else "other"
            mention_counts_by_prompt[pid][model][key] = cnt
        for p in prompts:
            p["citation_counts"] = counts_by_prompt.get(p["id"], default_counts)
            p["mention_counts"] = mention_counts_by_prompt.get(p["id"], default_counts)
            p["mentioned_competitors"] = competitors_by_prompt.get(p["id"], [])
        return {"prompts": prompts, "total": total}
    finally:
        conn.close()


@app.get("/api/prompts/{prompt_id}")
def get_prompt_by_id(prompt_id: int, user_id: int = Depends(get_current_user_id)):
    """Full prompt detail with latest visibility and citations."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, text, niche, created_at FROM prompts WHERE id = ? AND user_id = ?", (prompt_id, user_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        out = dict(row)
        runs = conn.execute(
            """SELECT r.id, r.execution_id, r.model, r.started_at, r.prompt_count FROM runs r
               JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
               WHERE r.status = 'finished' ORDER BY r.execution_id DESC, r.started_at DESC LIMIT 50""",
            (user_id,),
        ).fetchall()
        out["runs"] = [dict(r) for r in runs]
        visibility = conn.execute(
            "SELECT run_id, had_own_citation, brand_mentioned, competitor_only FROM run_prompt_visibility WHERE prompt_id = ?",
            (prompt_id,),
        ).fetchall()
        vis_by_run = {v["run_id"]: dict(v) for v in visibility}
        citations = conn.execute(
            "SELECT c.run_id, c.model, c.cited_domain, c.raw_snippet, c.is_own_domain, c.created_at FROM citations c WHERE c.prompt_id = ? ORDER BY c.created_at DESC LIMIT 100",
            (prompt_id,),
        ).fetchall()
        out["citations"] = [dict(c) for c in citations]
        mentions = conn.execute(
            "SELECT run_id, model, mentioned, is_own_domain FROM run_prompt_mentions WHERE prompt_id = ? ORDER BY run_id, model",
            (prompt_id,),
        ).fetchall()
        # Normalize is_own_domain to 0 or 1 so frontend never sees null
        out["mentions"] = [
            {"run_id": m["run_id"], "model": m["model"], "mentioned": m["mentioned"] or "", "is_own_domain": 1 if m["is_own_domain"] else 0}
            for m in mentions
        ]
        out["mentioned_competitors"] = list(dict.fromkeys((m["mentioned"] or "").strip() for m in mentions if (m["is_own_domain"] or 0) == 0 and (m["mentioned"] or "").strip()))
        responses = conn.execute(
            "SELECT run_id, model, response_text FROM run_prompt_responses WHERE prompt_id = ? ORDER BY run_id",
            (prompt_id,),
        ).fetchall()
        out["response_by_run"] = {r["run_id"]: {"model": r["model"], "response_text": r["response_text"] or ""} for r in responses}
        cited_run_ids = {c["run_id"] for c in citations if c["is_own_domain"]}
        # For each run, list "other" cited domains (is_own_domain=0) — shown when competitor_only=Yes
        others_cited_by_run: dict[int, list[str]] = {}
        for c in citations:
            if (c["is_own_domain"] or 0) == 0 and (c["cited_domain"] or "").strip():
                run_id = c["run_id"]
                domain = (c["cited_domain"] or "").strip()
                if run_id not in others_cited_by_run:
                    others_cited_by_run[run_id] = []
                if domain not in others_cited_by_run[run_id]:
                    others_cited_by_run[run_id].append(domain)
        for r in out["runs"]:
            r["cited"] = r["id"] in cited_run_ids
            v = vis_by_run.get(r["id"], {})
            r["had_own_citation"] = v.get("had_own_citation", 0)
            r["brand_mentioned"] = v.get("brand_mentioned", 0)
            r["competitor_only"] = v.get("competitor_only", 0)
            r["others_cited"] = others_cited_by_run.get(r["id"], [])
        return out
    finally:
        conn.close()


@app.post("/api/drafts/{draft_id}/approve")
def approve_draft(draft_id: int, publish: bool = False, destination: str | None = None, content_source_id: int | None = None, user_id: int = Depends(get_current_user_id)):
    """Mark draft as approved; optionally push to CMS. When publishing, use content_source_id (preferred) or destination string. Records to draft_publications."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, title, slug, body_md FROM drafts WHERE id = ? AND user_id = ?", (draft_id, user_id)).fetchone()
        if not row:
            return {"ok": False, "error": "Draft not found"}
        if publish:
            dest = destination
            source_id = content_source_id
            source_config = None
            if source_id is not None:
                src_row = conn.execute(
                    "SELECT id, name, type, config FROM content_sources WHERE id = ? AND user_id = ?", (source_id, user_id)
                ).fetchone()
                if not src_row:
                    return {"ok": False, "published": False, "error": "Content source not found"}
                dest = (src_row["type"] or "").strip().lower()
                if src_row["config"]:
                    try:
                        source_config = json.loads(src_row["config"])
                        if isinstance(source_config, dict):
                            source_config = {k: v for k, v in source_config.items() if k != "_type"}
                    except (TypeError, ValueError):
                        source_config = None
            from src.content.cms import publish_draft
            body_md_rewritten = _rewrite_image_urls_in_markdown(row["body_md"] or "")
            try:
                import markdown as md
                html = md.markdown(body_md_rewritten or "")
            except ImportError:
                html = (body_md_rewritten or "").replace("\n", "<p>")
            try:
                ok, published_url, err_msg = publish_draft(
                    draft_id, html, row["title"], row["slug"] or "",
                    destination=dest, source_config=source_config,
                    body_md=body_md_rewritten,
                )
            except Exception as e:
                ok, published_url, err_msg = False, None, str(e)
            pub_status = "published" if ok else "failed"
            conn.execute(
                """INSERT INTO draft_publications (draft_id, content_source_id, published_url, status, error_message, published_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (draft_id, source_id if source_id is not None else None, published_url, pub_status, err_msg, None),
            )
            if ok:
                conn.execute(
                    "UPDATE draft_publications SET published_at = CURRENT_TIMESTAMP WHERE id = last_insert_rowid()",
                    (),
                )
            conn.commit()
            if not ok:
                return {"ok": False, "published": False, "error": err_msg or "Publish failed. Check CMS credentials in .env."}
            conn.execute(
                """UPDATE drafts SET status = 'published', published_at = CURRENT_TIMESTAMP,
                   published_url = COALESCE(?, published_url), updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (published_url, draft_id),
            )
            conn.commit()
            try:
                from src.distribution.learning_loop import compute_and_store_uplift_for_draft
                compute_and_store_uplift_for_draft(draft_id, conn=conn)
            except Exception:
                pass
            return {"ok": True, "published": True}
        conn.execute("UPDATE drafts SET status = 'approved', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (draft_id,))
        conn.commit()
        return {"ok": True, "published": False}
    finally:
        conn.close()


def _verify_published_url(url: str, expected_title: str | None) -> tuple[str, str | None]:
    """Fetch URL; return (verification_status, error_message). Status: verified, failed, or pending."""
    try:
        import httpx
        import re
        resp = httpx.get(url, follow_redirects=True, timeout=15)
        if resp.status_code != 200:
            return ("failed", f"URL returned status {resp.status_code}")
        text = resp.text or ""
        # Try to find <title>...</title>
        m = re.search(r"<title[^>]*>([^<]+)</title>", text, re.IGNORECASE | re.DOTALL)
        page_title = (m.group(1).strip() if m else "").replace("\n", " ")[:200]
        if expected_title and page_title:
            # Normalize: lowercase, collapse spaces; check if expected title appears in page title
            norm = lambda s: " ".join(s.lower().split())
            if norm(expected_title) in norm(page_title) or norm(page_title) in norm(expected_title):
                return ("verified", None)
            return ("failed", "Page title does not match draft title")
        # No expected title or no title on page: consider verified if we got 200
        return ("verified", None)
    except Exception as e:
        return ("failed", str(e))


@app.post("/api/drafts/{draft_id}/submit-url")
def submit_published_url(draft_id: int, body: dict = Body(...), user_id: int = Depends(get_current_user_id)):
    """Record a URL where this draft was manually published; verify, save status, and record in draft_publications."""
    url = (body.get("url") or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Body must include a valid 'url' (http or https)")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, title FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Draft not found")
        conn.execute(
            "UPDATE drafts SET published_url = ?, verification_status = 'pending', verified_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (url, draft_id),
        )
        conn.commit()
        status, err = _verify_published_url(url, row["title"])
        conn.execute(
            "UPDATE drafts SET verification_status = ?, verified_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, draft_id),
        )
        conn.execute(
            """INSERT INTO draft_publications (draft_id, content_source_id, published_url, status, error_message, published_at)
               VALUES (?, NULL, ?, 'manual', ?, CURRENT_TIMESTAMP)""",
            (draft_id, url, err),
        )
        conn.commit()
        return {"ok": True, "url": url, "verification_status": status, "error": err}
    finally:
        conn.close()


@app.post("/api/drafts/{draft_id}/verify")
def verify_draft_url(draft_id: int, user_id: int = Depends(get_current_user_id)):
    """Re-run verification for the draft's published_url."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, title, published_url FROM drafts WHERE id = ? AND user_id = ?",
            (draft_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Draft not found")
        if not row["published_url"]:
            raise HTTPException(status_code=400, detail="No published_url set. Submit a URL first.")
        status, err = _verify_published_url(row["published_url"], row["title"])
        conn.execute(
            "UPDATE drafts SET verification_status = ?, verified_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, draft_id),
        )
        conn.commit()
        return {"ok": True, "verification_status": status, "error": err}
    finally:
        conn.close()


@app.get("/api/cms/options")
def get_cms_options(user_id: int = Depends(get_current_user_id)):
    """Which CMS types are configured (env) and list of content sources (DB) for publish targets."""
    import os
    env_flags = {
        "wordpress": bool(os.environ.get("WORDPRESS_URL") and os.environ.get("WORDPRESS_APP_PASSWORD")),
        "webflow": bool(os.environ.get("WEBFLOW_API_TOKEN") and os.environ.get("WEBFLOW_COLLECTION_ID")),
        "ghost": bool(os.environ.get("GHOST_URL") and os.environ.get("GHOST_ADMIN_API_KEY")),
        "hashnode": bool(os.environ.get("HASHNODE_API_KEY") and os.environ.get("HASHNODE_PUBLICATION_ID")),
        "linkedin": bool(os.environ.get("LINKEDIN_ACCESS_TOKEN") and os.environ.get("LINKEDIN_AUTHOR_URN")),
        "devto": bool(os.environ.get("DEVTO_API_KEY")),
        "notion": bool(os.environ.get("NOTION_INTEGRATION_TOKEN") and os.environ.get("NOTION_PARENT_ID")),
    }
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, type FROM content_sources WHERE user_id = ? ORDER BY name",
            (user_id,),
        ).fetchall()
        content_sources = [{"id": r["id"], "name": r["name"], "type": r["type"]} for r in rows]
    finally:
        conn.close()
    return {
        **env_flags,
        "content_sources": content_sources,
    }


@app.get("/api/reports/weekly")
def get_weekly_report(
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    user_id: int = Depends(get_current_user_id),
):
    """Learning summary: citation trends and what worked."""
    from src.distribution.learning_loop import generate_weekly_summary
    return {"summary": generate_weekly_summary(from_date=from_date, to_date=to_date, user_id=user_id)}


def _report_date_filter(where_parts: list, params: list, from_date: str | None, to_date: str | None, column: str) -> None:
    """Append date filter clauses for report queries."""
    if from_date:
        where_parts.append(f"date({column}) >= date(?)")
        params.append(from_date)
    if to_date:
        where_parts.append(f"date({column}) <= date(?)")
        params.append(to_date)


@app.get("/api/reports/monitoring-runs")
def get_reports_monitoring_runs(
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    user_id: int = Depends(get_current_user_id),
):
    """List monitoring executions in date range for reporting."""
    conn = get_connection()
    try:
        where_parts = ["user_id = ?"]
        params: list = [user_id]
        _report_date_filter(where_parts, params, from_date, to_date, "started_at")
        q = f"""SELECT id, started_at, finished_at, status, trigger_type
                FROM monitoring_executions WHERE {' AND '.join(where_parts)} ORDER BY started_at DESC"""
        rows = conn.execute(q, tuple(params)).fetchall()
        return {
            "rows": [
                {
                    "id": r["id"],
                    "started_at": r["started_at"],
                    "finished_at": r["finished_at"],
                    "status": r["status"],
                    "trigger_type": r["trigger_type"],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.get("/api/reports/citations")
def get_reports_citations(
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    user_id: int = Depends(get_current_user_id),
):
    """List citation records for runs in date range (for CSV export)."""
    conn = get_connection()
    try:
        where_parts = ["r.status = 'finished'"]
        params: list = [user_id]
        if from_date:
            where_parts.append("date(r.started_at) >= date(?)")
            params.append(from_date)
        if to_date:
            where_parts.append("date(r.started_at) <= date(?)")
            params.append(to_date)
        q = f"""
            SELECT r.id AS run_id, r.started_at AS run_date, r.model, c.prompt_id, c.cited_domain, c.is_own_domain, c.raw_snippet
            FROM runs r
            JOIN monitoring_executions e ON e.id = r.execution_id AND e.user_id = ?
            JOIN citations c ON c.run_id = r.id
            WHERE {' AND '.join(where_parts)}
            ORDER BY r.started_at DESC, c.id
        """
        rows = conn.execute(q, tuple(params)).fetchall()
        return {
            "rows": [
                {
                    "run_id": r["run_id"],
                    "run_date": r["run_date"],
                    "model": r["model"],
                    "prompt_id": r["prompt_id"],
                    "cited_domain": r["cited_domain"],
                    "is_own_domain": bool(r["is_own_domain"]),
                    "raw_snippet": (r["raw_snippet"] or "")[:200],
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


@app.get("/api/reports/drafts")
def get_reports_drafts(
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    user_id: int = Depends(get_current_user_id),
):
    """List drafts in date range (by created_at) for reporting."""
    conn = get_connection()
    try:
        where_parts = ["user_id = ?"]
        params: list = [user_id]
        _report_date_filter(where_parts, params, from_date, to_date, "created_at")
        q = f"""SELECT id, title, slug, status, created_at, updated_at, published_at, published_url, image_urls
                FROM drafts WHERE {' AND '.join(where_parts)} ORDER BY created_at DESC"""
        rows = conn.execute(q, tuple(params)).fetchall()
        return {
            "rows": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "slug": r["slug"] or "",
                    "status": r["status"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "published_at": r["published_at"],
                    "published_url": r["published_url"] or "",
                    "image_urls": r["image_urls"] or "",
                }
                for r in rows
            ]
        }
    finally:
        conn.close()


# SPA fallback: register last so /api/* and other routes take precedence. Serves frontend dist for non-API paths.
if _FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str = ""):
        index_path = _FRONTEND_DIST / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Frontend not built")
        return FileResponse(index_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
