"""Tenant-scoped exact-match response cache.

Serves repeat FAQ questions ("office hours", "OCI documents", "visa fee")
without an LLM call. For a consular bot these recur constantly across users,
so a cache hit eliminates the whole chat-completion round-trip.

Design / safety:
- Keyed by ``(company_id, language, normalized_query)`` — never crosses tenants
  or languages.
- Backed by a Mongo collection with a TTL index, so entries auto-expire (KB
  edits propagate within the TTL) and the cache is shared across workers /
  survives restarts (unlike the in-process ``_sessions`` history).
- Conservative: callers decide *when* a turn is cacheable (the route only
  caches context-free opening questions with no image and idle flow state).
  This module just does normalize → key → get/put. It caches nothing on its
  own and no-ops entirely unless ``RESPONSE_CACHE_ENABLED`` is truthy.

Enable with env ``RESPONSE_CACHE_ENABLED=true``. TTL via
``RESPONSE_CACHE_TTL_SECONDS`` (default 21600 = 6h).
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from database import get_database
from services import platform_config

logger = logging.getLogger("services.response_cache")


def enabled() -> bool:
    """Master switch — default OFF so rollout is opt-in. Read from
    platform_config (DB → env ``RESPONSE_CACHE_ENABLED`` → default), so a
    super-admin can toggle it in the UI without a redeploy."""
    return bool(platform_config.get("response_cache_enabled", False))


def _ttl_seconds() -> int:
    """Cache TTL, resolved at call time (platform_config → env → default 6h)."""
    try:
        return int(platform_config.get("response_cache_ttl_seconds", 21600) or 21600)
    except (TypeError, ValueError):
        return 21600


def _normalize(query: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace. Conservative on
    purpose: two phrasings only share a cache entry when they reduce to the
    same token string, so we avoid false hits between distinct questions."""
    q = (query or "").lower().strip()
    q = re.sub(r"[^\w\s]", " ", q)   # punctuation → space
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _key(company_id: str, lang: Optional[str], query: str) -> str:
    raw = f"{company_id}\x00{(lang or 'en')}\x00{_normalize(query)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def get(company_id: str, lang: Optional[str], query: str) -> Optional[str]:
    """Return a cached answer, or None on miss / disabled / empty-query."""
    if not enabled() or not company_id or not (query or "").strip():
        return None
    try:
        db = await get_database()
        row = await db.response_cache.find_one({"_id": _key(company_id, lang, query)}, {"answer": 1})
        return (row or {}).get("answer")
    except Exception as e:
        logger.debug("response_cache.get failed: %s", e)
        return None


async def put(company_id: str, lang: Optional[str], query: str, answer: str,
              ttl_seconds: Optional[int] = None) -> None:
    """Store an answer. No-ops when disabled or any field is empty. TTL falls
    back to the platform_config / env value when the caller doesn't specify."""
    if not enabled() or not company_id or not (query or "").strip() or not (answer or "").strip():
        return
    if ttl_seconds is None:
        ttl_seconds = _ttl_seconds()
    try:
        db = await get_database()
        now = datetime.now(timezone.utc)
        await db.response_cache.update_one(
            {"_id": _key(company_id, lang, query)},
            {"$set": {
                "company_id": company_id,
                "lang": lang or "en",
                "query_norm": _normalize(query),
                "answer": answer,
                "created_at": now,
                "expires_at": now + timedelta(seconds=ttl_seconds),
            }},
            upsert=True,
        )
    except Exception as e:
        logger.debug("response_cache.put failed: %s", e)


async def invalidate_tenant(company_id: str) -> int:
    """Drop all cached responses for a tenant. Call this after a KB edit so a
    correction can't be masked by a stale cached answer. Returns rows removed.
    No-ops when the cache is disabled (nothing is stored then)."""
    if not enabled() or not company_id:
        return 0
    try:
        db = await get_database()
        res = await db.response_cache.delete_many({"company_id": company_id})
        return int(res.deleted_count or 0)
    except Exception as e:
        logger.warning("response_cache.invalidate_tenant failed for %s: %s", company_id, e)
        return 0


async def ensure_indexes(db) -> None:
    """Create the TTL + tenant indexes. Idempotent; safe to call on startup.
    The TTL index on ``expires_at`` lets Mongo auto-delete expired rows."""
    await db.response_cache.create_index("expires_at", expireAfterSeconds=0)
    await db.response_cache.create_index("company_id")
