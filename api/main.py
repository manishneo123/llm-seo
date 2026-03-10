"""FastAPI app: endpoints for citations, trends, prompts visibility."""
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.db.connection import get_connection, init_db


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


app = FastAPI(title="LLM SEO Agent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _scheduler_loop():
    """Background loop: every 60s check monitoring_settings and run if due."""
    while True:
        time.sleep(60)
        try:
            conn = get_connection()
            try:
                row = conn.execute(
                    "SELECT enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds FROM monitoring_settings WHERE id = 1"
                ).fetchone()
                if not row or not row["enabled"] or not row["frequency_minutes"]:
                    continue
                freq_mins = int(row["frequency_minutes"] or 0)
                if freq_mins <= 0:
                    continue
                last = conn.execute(
                    """SELECT started_at FROM monitoring_executions
                       WHERE trigger_type = 'scheduled' OR trigger_type = 'manual'
                       ORDER BY started_at DESC LIMIT 1"""
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
                        elapsed = (datetime.now(timezone.utc) - last_ts).total_seconds()
                        if elapsed < freq_mins * 60:
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
                delay_seconds = row["delay_seconds"]
                settings_snapshot = {
                    "domain_ids": domain_ids,
                    "models": models,
                    "prompt_limit": prompt_limit,
                    "delay_seconds": delay_seconds,
                }
                conn.execute(
                    """INSERT INTO monitoring_executions (trigger_type, status, settings_snapshot)
                       VALUES ('scheduled', 'running', ?)""",
                    (json.dumps(settings_snapshot),),
                )
                execution_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.commit()
            finally:
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
            )
            _run_brief_and_content_after_monitor()
        except Exception:
            pass
        try:
            conn = get_connection()
            try:
                from src.domains_db import discovery_done
                from datetime import datetime, timezone
                row = conn.execute(
                    "SELECT enabled, frequency_days, last_run_at FROM prompt_generation_settings WHERE id = 1"
                ).fetchone()
                if not row or not row["enabled"]:
                    pass
                else:
                    freq_days = float(row["frequency_days"] or 0)
                    if freq_days <= 0:
                        pass
                    else:
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
                        if due and discovery_done(conn):
                            conn.execute(
                                "INSERT INTO prompt_generation_runs (trigger_type, status) VALUES ('scheduled', 'running')"
                            )
                            run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                            conn.commit()
                            try:
                                inserted = _run_prompt_generation_sync(conn, None)
                                conn.execute(
                                    "UPDATE prompt_generation_settings SET last_run_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = 1"
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


@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    """Aggregate numbers for dashboard: citations, brand mentions, prompts, domains, last run."""
    conn = get_connection()
    try:
        total_prompts = conn.execute("SELECT COUNT(*) AS n FROM prompts").fetchone()["n"] or 0
        domains_tracked = conn.execute("SELECT COUNT(*) AS n FROM domains").fetchone()["n"] or 0
        last_run = conn.execute(
            "SELECT started_at FROM runs WHERE status = 'finished' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        last_run_at = last_run["started_at"] if last_run else None

        run_rows = conn.execute(
            "SELECT id FROM runs WHERE status = 'finished' ORDER BY started_at DESC LIMIT 3"
        ).fetchall()
        run_ids = [r["id"] for r in run_rows]
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


# ---------- Domains (replaces config/domains.yaml) ----------
@app.get("/api/domains")
def list_domains():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, domain, brand_names, created_at, updated_at FROM domains ORDER BY id"
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
def create_domain(body: dict = Body(...)):
    domain = (body.get("domain") or "").strip()
    if not domain:
        raise HTTPException(status_code=400, detail="domain is required")
    brand_names = body.get("brand_names")
    if brand_names is not None and not isinstance(brand_names, list):
        brand_names = [str(brand_names)] if brand_names else []
    brand_names_json = __import__("json").dumps(brand_names or [])
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO domains (domain, brand_names, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (domain, brand_names_json),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, domain, brand_names, created_at, updated_at FROM domains WHERE id = ?",
            (cur.lastrowid,),
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
def get_domain(domain_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, domain, brand_names, created_at, updated_at FROM domains WHERE id = ?",
            (domain_id,),
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
def update_domain(domain_id: int, body: dict = Body(...)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM domains WHERE id = ?", (domain_id,)).fetchone()
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
def delete_domain(domain_id: int):
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM domains WHERE id = ?", (domain_id,))
        conn.execute("DELETE FROM domain_profiles WHERE domain_id = ?", (domain_id,))
        conn.execute("DELETE FROM domain_content_source WHERE domain_id = ?", (domain_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Domain not found")
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/domains/{domain_id}/profile")
def get_domain_profile(domain_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT dp.id, dp.domain_id, dp.category, dp.niche, dp.value_proposition, dp.key_topics,
                      dp.target_audience, dp.competitors, dp.discovered_at, d.domain
               FROM domain_profiles dp JOIN domains d ON d.id = dp.domain_id
               WHERE dp.domain_id = ?""",
            (domain_id,),
        ).fetchone()
        if not row:
            row = conn.execute("SELECT id, domain FROM domains WHERE id = ?", (domain_id,)).fetchone()
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
def run_domain_discovery(domain_id: int):
    """Run discovery for this domain only (crawl + extract profile)."""
    conn = get_connection()
    try:
        from src.domain_discovery.run_discovery import run_discovery_for_domain
        result = run_discovery_for_domain(conn, domain_id)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Discovery failed"))
        return result
    finally:
        conn.close()


@app.put("/api/domains/{domain_id}/profile")
def update_domain_profile(domain_id: int, body: dict = Body(...)):
    """Create or update profile for this domain. Body: category, niche, value_proposition, key_topics (array), target_audience, competitors (array)."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM domains WHERE id = ?", (domain_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Domain not found")
        category = (body.get("category") or "").strip()
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
        conn.execute(
            """INSERT INTO domain_profiles (domain_id, category, niche, value_proposition, key_topics, target_audience, competitors, discovered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT discovered_at FROM domain_profiles WHERE domain_id = ?), CURRENT_TIMESTAMP))
               ON CONFLICT(domain_id) DO UPDATE SET
                 category=excluded.category, niche=excluded.niche, value_proposition=excluded.value_proposition,
                 key_topics=excluded.key_topics, target_audience=excluded.target_audience, competitors=excluded.competitors""",
            (domain_id, category, niche, value_proposition, key_topics_json, target_audience, competitors_json, domain_id),
        )
        conn.commit()
        row = conn.execute(
            """SELECT dp.id, dp.domain_id, dp.category, dp.niche, dp.value_proposition, dp.key_topics,
                      dp.target_audience, dp.competitors, dp.discovered_at, d.domain
               FROM domain_profiles dp JOIN domains d ON d.id = dp.domain_id WHERE dp.domain_id = ?""",
            (domain_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="Profile not saved")
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


# ---------- Content sources (Hashnode, Ghost, etc.) and domain mapping ----------
CONTENT_SOURCE_TYPES = ("hashnode", "ghost", "wordpress", "webflow", "linkedin", "devto", "notion")


@app.get("/api/content-sources")
def list_content_sources():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name, type, config, created_at, updated_at FROM content_sources ORDER BY name"
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
def create_content_source(body: dict = Body(...)):
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
            "INSERT INTO content_sources (name, type, config, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (name, source_type, config_json),
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
def get_content_source(source_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, type, config, created_at, updated_at FROM content_sources WHERE id = ?",
            (source_id,),
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
def update_content_source(source_id: int, body: dict = Body(...)):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM content_sources WHERE id = ?", (source_id,)).fetchone()
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
def delete_content_source(source_id: int):
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM content_sources WHERE id = ?", (source_id,))
        conn.execute("DELETE FROM domain_content_source WHERE content_source_id = ?", (source_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Content source not found")
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/content-sources/{source_id}/validate")
def validate_content_source_credentials(source_id: int):
    """Test CMS credentials for this content source (uses saved config). Returns { ok, message }."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, name, type, config FROM content_sources WHERE id = ?",
            (source_id,),
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
def list_content_source_domains(source_id: int):
    """Domains mapped to this content source."""
    conn = get_connection()
    try:
        if not conn.execute("SELECT id FROM content_sources WHERE id = ?", (source_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Content source not found")
        rows = conn.execute(
            """SELECT d.id, d.domain FROM domains d
               JOIN domain_content_source dcs ON dcs.domain_id = d.id
               WHERE dcs.content_source_id = ? ORDER BY d.domain""",
            (source_id,),
        ).fetchall()
        return {"domains": [{"id": r["id"], "domain": r["domain"]} for r in rows]}
    finally:
        conn.close()


@app.get("/api/domains/{domain_id}/content-sources")
def list_domain_content_sources(domain_id: int):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM domains WHERE id = ?", (domain_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Domain not found")
        rows = conn.execute(
            """SELECT cs.id, cs.name, cs.type, cs.config, cs.created_at
               FROM content_sources cs
               JOIN domain_content_source dcs ON dcs.content_source_id = cs.id
               WHERE dcs.domain_id = ? ORDER BY cs.name""",
            (domain_id,),
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
def add_domain_content_source(domain_id: int, body: dict = Body(...)):
    source_id = body.get("content_source_id")
    if source_id is None:
        raise HTTPException(status_code=400, detail="content_source_id is required")
    try:
        source_id = int(source_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="content_source_id must be an integer")
    conn = get_connection()
    try:
        if not conn.execute("SELECT id FROM domains WHERE id = ?", (domain_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Domain not found")
        if not conn.execute("SELECT id FROM content_sources WHERE id = ?", (source_id,)).fetchone():
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
def remove_domain_content_source(domain_id: int, content_source_id: int):
    conn = get_connection()
    try:
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
def discovery_status():
    conn = get_connection()
    try:
        from src.domains_db import discovery_done, get_tracked_domains_from_db, get_domain_profiles_from_db
        domains_count = len(get_tracked_domains_from_db(conn))
        profiles = get_domain_profiles_from_db(conn)
        profiles_count = len(profiles) if profiles else 0
        discovery_done_flag = discovery_done(conn)
        return {
            "domains_count": domains_count,
            "profiles_count": profiles_count,
            "discovery_done": discovery_done_flag,
        }
    finally:
        conn.close()


@app.post("/api/discovery/run")
def run_discovery():
    conn = get_connection()
    try:
        from src.domain_discovery.run_discovery import run_discovery_to_db
        result = run_discovery_to_db(conn)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "Discovery failed"))
        return result
    finally:
        conn.close()


# ---------- Prompt generation (gated: only after discovery) ----------
@app.post("/api/prompts/generate")
def generate_prompts_api(body: dict = Body(...)):
    conn = get_connection()
    try:
        from src.domains_db import discovery_done
        if not discovery_done(conn):
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

        profiles = load_domain_profiles()
        if not profiles:
            raise HTTPException(status_code=400, detail="No domain profiles in DB.")
        if prompts_per_domain is not None and prompts_per_domain > 0:
            all_prompts_with_niche = []
            for domain, profile in profiles:
                context = _context_from_profile(domain, profile)
                prompts = generate_prompts(niche=context, count=prompts_per_domain)
                for p in prompts:
                    all_prompts_with_niche.append((p, f"domain:{domain}"))
            inserted = store_prompts_with_niches(all_prompts_with_niche, conn)
        elif count is not None and count > 0:
            domain, profile = profiles[0]
            context = _context_from_profile(domain, profile)
            prompts = generate_prompts(niche=context, count=count)
            inserted = store_prompts_in_db(prompts, conn, niche=profile.get("niche") or "domain:" + domain)
        else:
            per_domain = get_prompts_per_domain()
            all_prompts_with_niche = []
            for domain, profile in profiles:
                context = _context_from_profile(domain, profile)
                prompts = generate_prompts(niche=context, count=per_domain)
                for p in prompts:
                    all_prompts_with_niche.append((p, f"domain:{domain}"))
            inserted = store_prompts_with_niches(all_prompts_with_niche, conn)
        conn.commit()
        return {"ok": True, "inserted": inserted}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


def _run_prompt_generation_sync(conn, prompts_per_domain: int | None = None) -> int:
    """Run prompt generation (domain profiles → prompts). Uses prompts_per_domain or config default. Returns inserted count. Caller must commit."""
    from src.monitor.prompt_generator import (
        load_domain_profiles,
        generate_prompts,
        store_prompts_with_niches,
        _context_from_profile,
    )
    from src.config_loader import get_prompts_per_domain
    profiles = load_domain_profiles()
    if not profiles:
        return 0
    per_domain = prompts_per_domain if prompts_per_domain is not None and prompts_per_domain > 0 else get_prompts_per_domain()
    all_prompts_with_niche = []
    for domain, profile in profiles:
        context = _context_from_profile(domain, profile)
        prompts = generate_prompts(niche=context, count=per_domain)
        for p in prompts:
            all_prompts_with_niche.append((p, f"domain:{domain}"))
    if not all_prompts_with_niche:
        return 0
    return store_prompts_with_niches(all_prompts_with_niche, conn)


# ---------- Prompt generation schedule (settings + run) ----------
@app.get("/api/prompt-generation/settings")
def get_prompt_generation_settings():
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, enabled, frequency_days, prompts_per_domain, last_run_at, updated_at FROM prompt_generation_settings WHERE id = 1"
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
def update_prompt_generation_settings(body: dict = Body(...)):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO prompt_generation_settings (id, enabled, frequency_days) VALUES (1, 0, 7)"
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
            params.append(1)
            conn.execute(
                "UPDATE prompt_generation_settings SET " + ", ".join(updates) + " WHERE id = ?",
                params,
            )
        conn.commit()
        return get_prompt_generation_settings()
    finally:
        conn.close()


@app.get("/api/prompt-generation/runs")
def list_prompt_generation_runs(limit: int = 20, offset: int = 0):
    """List prompt generation runs (scheduled or manual) with pagination."""
    conn = get_connection()
    try:
        count_row = conn.execute("SELECT COUNT(*) AS n FROM prompt_generation_runs").fetchone()
        total = count_row["n"] if count_row else 0
        rows = conn.execute(
            """SELECT id, started_at, finished_at, trigger_type, status, inserted_count
               FROM prompt_generation_runs ORDER BY started_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
        runs = [dict(r) for r in rows]
        return {"runs": runs, "total": total}
    finally:
        conn.close()


@app.post("/api/prompt-generation/run")
def run_prompt_generation_now():
    """Run prompt generation now and update last_run_at. Records a run in prompt_generation_runs."""
    conn = get_connection()
    try:
        from src.domains_db import discovery_done
        if not discovery_done(conn):
            raise HTTPException(
                status_code=400,
                detail="Run domain discovery first. Add domains and click Run discovery.",
            )
        conn.execute(
            "INSERT INTO prompt_generation_runs (trigger_type, status) VALUES ('manual', 'running')"
        )
        run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        row = conn.execute(
            "SELECT prompts_per_domain FROM prompt_generation_settings WHERE id = 1"
        ).fetchone()
        prompts_per_domain = None
        if row and row["prompts_per_domain"] is not None:
            prompts_per_domain = int(row["prompts_per_domain"])
        try:
            inserted = _run_prompt_generation_sync(conn, prompts_per_domain)
            conn.execute(
                "UPDATE prompt_generation_settings SET last_run_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = 1"
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
def get_monitoring_settings():
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds, updated_at FROM monitoring_settings WHERE id = 1"
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
def update_monitoring_settings(body: dict = Body(...)):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO monitoring_settings (id, enabled, frequency_minutes, domain_ids, models, prompt_limit, delay_seconds, updated_at)
               VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(id) DO UPDATE SET
                 enabled=excluded.enabled,
                 frequency_minutes=excluded.frequency_minutes,
                 domain_ids=excluded.domain_ids,
                 models=excluded.models,
                 prompt_limit=excluded.prompt_limit,
                 delay_seconds=excluded.delay_seconds,
                 updated_at=CURRENT_TIMESTAMP""",
            (
                1 if body.get("enabled", True) else 0,
                body.get("frequency_minutes"),
                __import__("json").dumps(body.get("domain_ids")) if body.get("domain_ids") is not None else None,
                __import__("json").dumps(body.get("models")) if body.get("models") is not None else None,
                body.get("prompt_limit"),
                body.get("delay_seconds"),
            ),
        )
        conn.commit()
        return get_monitoring_settings()
    finally:
        conn.close()


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


def _run_monitor_async(execution_id: int, body: dict):
    models = body.get("models")
    prompt_limit = body.get("prompt_limit")
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


@app.post("/api/monitoring/run")
def run_monitoring_now(body: dict = Body(...)):
    """Trigger a monitoring run manually (runs in background). Optional body: models, prompt_limit, domain_ids."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO monitoring_executions (trigger_type, status, settings_snapshot)
               VALUES ('manual', 'running', ?)""",
            (json.dumps(body or {}),),
        )
        execution_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    t = threading.Thread(target=_run_monitor_async, args=(execution_id, body or {}), daemon=True)
    t.start()
    return {"ok": True, "execution_id": execution_id}


@app.get("/api/monitoring/executions")
def list_monitoring_executions(limit: int = 20, offset: int = 0):
    conn = get_connection()
    try:
        count_row = conn.execute("SELECT COUNT(*) AS n FROM monitoring_executions").fetchone()
        total = count_row["n"] if count_row else 0
        rows = conn.execute(
            """SELECT id, started_at, finished_at, trigger_type, status, settings_snapshot
               FROM monitoring_executions ORDER BY started_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
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
def get_monitoring_execution(execution_id: int):
    conn = get_connection()
    try:
        row = conn.execute(
            """SELECT id, started_at, finished_at, trigger_type, status, settings_snapshot
               FROM monitoring_executions WHERE id = ?""",
            (execution_id,),
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
            vis_rows = conn.execute(
                f"""SELECT v.prompt_id, v.run_id, v.had_own_citation, v.brand_mentioned, v.competitor_only,
                           p.text AS prompt_text, p.niche AS prompt_niche
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
                    "brand_mentioned": bool(r["brand_mentioned"]),
                    "competitor_only": bool(r["competitor_only"]),
                })
            out["prompt_visibility"] = list(by_prompt.values())
        return out
    finally:
        conn.close()


@app.get("/api/citations/trends")
def get_citation_trends(run_limit: int = 30):
    """Citation rate over time, by model."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT r.id, r.model, r.started_at, r.prompt_count,
                   (SELECT COUNT(DISTINCT c.prompt_id) FROM citations c WHERE c.run_id = r.id AND c.is_own_domain = 1) AS cited_count
            FROM runs r
            WHERE r.status = 'finished' AND r.prompt_count > 0
            ORDER BY r.started_at DESC
            LIMIT ?
        """, (run_limit,)).fetchall()
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
):
    """Prompts with visibility: cited, brand_mentioned, competitor_only in latest run(s). competitor_only=true returns only prompts where answer was competitor-only."""
    conn = get_connection()
    try:
        if run_id:
            run_ids = [run_id]
        else:
            run_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM runs WHERE status = 'finished' ORDER BY started_at DESC LIMIT 3"
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
            GROUP BY p.id
        """
        if competitor_only is True:
            q += " HAVING MAX(v.competitor_only) = 1"
        q += " ORDER BY p.id LIMIT ?"
        params = list(run_ids) + list(run_ids) + [limit]
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
def get_runs(limit: int = 20):
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, model, started_at, finished_at, prompt_count, status
            FROM runs ORDER BY started_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return {"runs": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/citations")
def get_citations(
    run_id: int | None = None,
    prompt_id: int | None = None,
    own_only: bool | None = None,
    limit: int = 500,
):
    """Citations: own_only=true for our domain only, own_only=false for other websites only, omit for all."""
    conn = get_connection()
    try:
        q = "SELECT run_id, prompt_id, model, cited_domain, raw_snippet, is_own_domain, created_at FROM citations WHERE 1=1"
        params = []
        if run_id:
            q += " AND run_id = ?"
            params.append(run_id)
        if prompt_id:
            q += " AND prompt_id = ?"
            params.append(prompt_id)
        if own_only is not None:
            q += " AND is_own_domain = ?"
            params.append(1 if own_only else 0)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchall()
        return {"citations": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/briefs")
def get_briefs(limit: int = 50, status: str | None = None):
    conn = get_connection()
    try:
        q = """SELECT b.id, b.prompt_id, b.topic, b.angle, b.priority_score, b.suggested_headings,
                     b.entities_to_mention, b.schema_to_add, b.image_prompts, b.image_urls, b.status, b.created_at,
                     (SELECT id FROM drafts WHERE brief_id = b.id ORDER BY id DESC LIMIT 1) AS draft_id
               FROM content_briefs b WHERE 1=1"""
        params = []
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
def get_drafts(limit: int = 50, status: str | None = None):
    conn = get_connection()
    try:
        q = "SELECT id, brief_id, title, slug, body_md, status, created_at, updated_at, published_at, published_url, verification_status, image_urls FROM drafts WHERE 1=1"
        params = []
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
def get_draft_by_id(draft_id: int):
    """Full draft detail with linked brief and prompt."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, brief_id, title, slug, body_md, body_html, schema_json, status, created_at, updated_at, published_at, published_url, verification_status, verified_at, image_urls FROM drafts WHERE id = ?",
            (draft_id,),
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
def update_draft(draft_id: int, body: dict = Body(...)):
    """Update draft title, body_md, slug. Body: title?, body_md?, slug?."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM drafts WHERE id = ?", (draft_id,)).fetchone()
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
            "SELECT id, brief_id, title, slug, body_md, body_html, status, created_at, updated_at, image_urls FROM drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@app.post("/api/drafts/{draft_id}/publish")
def publish_draft_to_source(draft_id: int, body: dict = Body(...)):
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
        row = conn.execute("SELECT id, title, slug, body_md FROM drafts WHERE id = ?", (draft_id,)).fetchone()
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
            "SELECT id, name, type, config FROM content_sources WHERE id = ?", (content_source_id,)
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
def generate_brief_images(brief_id: int):
    """Generate images from brief's image_prompts (OpenAI DALL·E), save to data/images, update brief.image_urls."""
    import json
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, topic, image_prompts, image_urls FROM content_briefs WHERE id = ?",
            (brief_id,),
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
def get_brief_by_id(brief_id: int):
    """Full brief detail with linked prompt."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, prompt_id, topic, angle, priority_score, suggested_headings, entities_to_mention, schema_to_add, image_prompts, image_urls, status, created_at FROM content_briefs WHERE id = ?",
            (brief_id,),
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
):
    """List prompts with pagination. competitor_only=true and run_id=X return only prompts that were competitor-only in that run."""
    conn = get_connection()
    try:
        base_q = "SELECT id, text, niche, created_at FROM prompts WHERE 1=1"
        params = []
        if niche:
            base_q += " AND niche LIKE ?"
            params.append(f"%{niche}%")
        if competitor_only is True and run_id is not None:
            base_q += " AND id IN (SELECT prompt_id FROM run_prompt_visibility WHERE run_id = ? AND competitor_only = 1)"
            params.append(run_id)
        count_q = "SELECT COUNT(*) AS n FROM prompts WHERE 1=1"
        count_params = []
        if niche:
            count_q += " AND niche LIKE ?"
            count_params.append(f"%{niche}%")
        if competitor_only is True and run_id is not None:
            count_q += " AND id IN (SELECT prompt_id FROM run_prompt_visibility WHERE run_id = ? AND competitor_only = 1)"
            count_params.append(run_id)
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
def get_prompt_by_id(prompt_id: int):
    """Full prompt detail with latest visibility and citations."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, text, niche, created_at FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prompt not found")
        out = dict(row)
        runs = conn.execute(
            "SELECT id, model, started_at, prompt_count FROM runs WHERE status = 'finished' ORDER BY started_at DESC LIMIT 10"
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
def approve_draft(draft_id: int, publish: bool = False, destination: str | None = None, content_source_id: int | None = None):
    """Mark draft as approved; optionally push to CMS. When publishing, use content_source_id (preferred) or destination string. Records to draft_publications."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT id, title, slug, body_md FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "Draft not found"}
        if publish:
            dest = destination
            source_id = content_source_id
            source_config = None
            if source_id is not None:
                src_row = conn.execute(
                    "SELECT id, name, type, config FROM content_sources WHERE id = ?", (source_id,)
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
def submit_published_url(draft_id: int, body: dict = Body(...)):
    """Record a URL where this draft was manually published; verify, save status, and record in draft_publications."""
    url = (body.get("url") or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Body must include a valid 'url' (http or https)")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, title FROM drafts WHERE id = ?",
            (draft_id,),
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
def verify_draft_url(draft_id: int):
    """Re-run verification for the draft's published_url."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, title, published_url FROM drafts WHERE id = ?",
            (draft_id,),
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
def get_cms_options():
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
            "SELECT id, name, type FROM content_sources ORDER BY name"
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
):
    """Learning summary: citation trends and what worked."""
    from src.distribution.learning_loop import generate_weekly_summary
    return {"summary": generate_weekly_summary(from_date=from_date, to_date=to_date)}


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
):
    """List monitoring executions in date range for reporting."""
    conn = get_connection()
    try:
        where_parts = ["1=1"]
        params: list = []
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
):
    """List citation records for runs in date range (for CSV export)."""
    conn = get_connection()
    try:
        where_parts = ["r.status = 'finished'"]
        params: list = []
        if from_date:
            where_parts.append("date(r.started_at) >= date(?)")
            params.append(from_date)
        if to_date:
            where_parts.append("date(r.started_at) <= date(?)")
            params.append(to_date)
        q = f"""
            SELECT r.id AS run_id, r.started_at AS run_date, r.model, c.prompt_id, c.cited_domain, c.is_own_domain, c.raw_snippet
            FROM runs r
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
):
    """List drafts in date range (by created_at) for reporting."""
    conn = get_connection()
    try:
        where_parts = ["1=1"]
        params: list = []
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
