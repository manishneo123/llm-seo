"""Load domains and domain profiles from DB (replaces YAML when tables exist)."""
import json
import sqlite3
from pathlib import Path

from src.db.connection import get_connection


def _get_conn(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    return conn or get_connection()


def get_tracked_domains_from_db(conn: sqlite3.Connection | None = None, user_id: int | None = None) -> list[str]:
    """Return list of domain strings from domains table. If user_id is set, only that user's domains."""
    c = _get_conn(conn)
    try:
        if user_id is not None:
            rows = c.execute("SELECT domain FROM domains WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
        else:
            rows = c.execute("SELECT domain FROM domains ORDER BY id").fetchall()
        return [r[0] for r in rows if r[0]]
    except sqlite3.OperationalError:
        return []
    finally:
        if conn is None:
            c.close()


def get_brand_names_from_db(conn: sqlite3.Connection | None = None, user_id: int | None = None) -> list[str]:
    """Return merged list of brand_names from all domains. If user_id is set, only that user's domains."""
    c = _get_conn(conn)
    try:
        if user_id is not None:
            rows = c.execute(
                "SELECT brand_names FROM domains WHERE user_id = ? AND brand_names IS NOT NULL AND brand_names != ''",
                (user_id,),
            ).fetchall()
        else:
            rows = c.execute("SELECT brand_names FROM domains WHERE brand_names IS NOT NULL AND brand_names != ''").fetchall()
        seen: set[str] = set()
        out: list[str] = []
        for r in rows:
            try:
                names = json.loads(r[0]) if isinstance(r[0], str) else r[0]
                if not isinstance(names, list):
                    continue
                for n in names:
                    s = (n or "").strip()
                    if s and s.lower() not in seen:
                        seen.add(s.lower())
                        out.append(s)
            except (json.JSONDecodeError, TypeError):
                continue
        return out
    except sqlite3.OperationalError:
        return []
    finally:
        if conn is None:
            c.close()


def get_domain_profiles_from_db(conn: sqlite3.Connection | None = None, user_id: int | None = None) -> list[tuple[str, dict]] | None:
    """Return list of (domain_string, profile_dict) from domain_profiles. If user_id is set, only that user's domains."""
    c = _get_conn(conn)
    try:
        if user_id is not None:
            rows = c.execute("""
                SELECT d.domain, dp.category, dp.categories, dp.niche, dp.value_proposition, dp.key_topics,
                       dp.target_audience, dp.competitors, dp.discovered_at
                FROM domain_profiles dp
                JOIN domains d ON d.id = dp.domain_id AND d.user_id = ?
                ORDER BY d.id
            """, (user_id,)).fetchall()
        else:
            rows = c.execute("""
                SELECT d.domain, dp.category, dp.categories, dp.niche, dp.value_proposition, dp.key_topics,
                       dp.target_audience, dp.competitors, dp.discovered_at
                FROM domain_profiles dp
                JOIN domains d ON d.id = dp.domain_id
                ORDER BY d.id
            """).fetchall()
        if not rows:
            return None
        out = []
        for r in rows:
            domain = r[0] or ""
            try:
                key_topics = json.loads(r[5]) if r[5] else []
            except (json.JSONDecodeError, TypeError):
                key_topics = []
            try:
                competitors = json.loads(r[7]) if r[7] else []
            except (json.JSONDecodeError, TypeError):
                competitors = []
            try:
                categories = json.loads(r[2]) if r[2] else []
            except (json.JSONDecodeError, TypeError):
                categories = []
            profile = {
                "domain": domain,
                "category": r[1] or "",
                "categories": list(categories) if isinstance(categories, list) else [],
                "niche": r[3] or "",
                "value_proposition": r[4] or "",
                "key_topics": list(key_topics) if isinstance(key_topics, list) else [],
                "target_audience": r[6] or "",
                "competitors": list(competitors) if isinstance(competitors, list) else [],
            }
            out.append((domain, profile))
        return out if out else None
    except sqlite3.OperationalError:
        return None
    finally:
        if conn is None:
            c.close()


def get_merged_competitors_from_db(conn: sqlite3.Connection | None = None, user_id: int | None = None) -> list[str]:
    """Return merged list of competitor names from all domain_profiles."""
    profiles = get_domain_profiles_from_db(conn, user_id=user_id)
    if not profiles:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for _domain, profile in profiles:
        for c in profile.get("competitors") or []:
            s = (c or "").strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
    return out


def discovery_done(conn: sqlite3.Connection | None = None, user_id: int | None = None) -> bool:
    """True if at least one domain has a profile (discovery has been run). If user_id is set, only that user's domains."""
    profiles = get_domain_profiles_from_db(conn, user_id=user_id)
    return bool(profiles)
