"""Platform-level tuning knobs (global, not per-tenant).

A single document in the ``platform_config`` collection holds operator-level
tuning that affects every tenant: cache TTLs, the crawler refresh interval,
WhatsApp channel char limits, frontend HTTP timeouts, the session-cleanup
period. The new "Platform Settings" tab in the super-admin UI edits this
document; everything else reads it through :py:func:`get`.

Precedence (highest → lowest):
  1. ``platform_config`` document value (set via super-admin UI)
  2. Environment variable (operator-set at deploy time, see ``_ENV_OVERRIDES``)
  3. Hardcoded default in ``DEFAULTS`` (matches the previous in-code constant)

Caching:
  - In-process TTL cache (60s) keyed by the singleton doc id.
  - ``invalidate_cache()`` drops the cache so the next ``get()`` re-reads.
  - The super-admin PUT endpoint calls ``invalidate_cache()`` after saving.

This module is intentionally *synchronous* for the hot path: callers do a
single ``get("key")`` lookup. The DB read happens inside an async refresh
task that the first ``await`` triggers via ``ensure_loaded()``. Most
consumers never need to await — they just call ``get()`` and get either
the cached value, the env var, or the default.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("services.platform_config")

# Singleton doc id in the platform_config collection.
_DOC_ID = "platform"

# Hardcoded defaults — matches the original in-code constants so removing
# this module would not change behavior (other than re-enabling the
# hardcoded paths). Keep the keys flat (no nesting) so the UI can render
# one row per knob without recursion.
DEFAULTS: Dict[str, Any] = {
    # ── Cache TTLs (seconds) ──────────────────────────────────────────
    "cache_bot_config_ttl_seconds":         60,
    "cache_tenant_ttl_seconds":             60,
    "cache_service_registry_ttl_seconds":   60,
    "cache_messaging_channel_ttl_seconds":  60,
    "cache_token_blacklist_ttl_seconds":    60,

    # ── Knowledge scraper ─────────────────────────────────────────────
    "kb_cache_ttl_seconds":         1800,   # 30 min
    "kb_blocked_kw_ttl_seconds":    60,
    "kb_deep_scan_ttl_seconds":     1800,
    "kb_crawl_interval_seconds":    6 * 3600,   # 6 h
    "kb_hit_threshold":             3,
    "kb_max_deep_urls":             8,

    # ── Maintenance loops ─────────────────────────────────────────────
    "session_cleanup_interval_seconds": 3600,   # 1 h
    "notification_job_interval_seconds": 3600,  # 1 h — notification scheduler

    # ── Auth ──────────────────────────────────────────────────────────
    # Dev auth mode: when True, the seva services login + apply OTP is the
    # fixed dev value (security_config.otp_dev_value, default 123456) and no
    # email is sent — convenient for testing. Turn OFF for production: a real
    # random OTP is generated and emailed, and the dev value is rejected.
    "dev_auth_mode": False,

    # ── WhatsApp channel ──────────────────────────────────────────────
    "whatsapp_body_char_limit":     1024,
    "whatsapp_text_char_limit":     4000,
    "whatsapp_visible_service_categories": ["TYPE_A"],
    # WhatsApp UI-phrase replacement rules:
    # [{ "pattern": "<regex>", "replacement": "<str>", "flags": "i" }]
    # Empty list means "don't rewrite anything".
    "whatsapp_ui_phrase_mappings":  [],

    # ── Frontend HTTP timeouts (ms) + chunk size (chars) ──────────────
    "frontend_chat_stream_timeout_ms":  60000,
    "frontend_tts_timeout_ms":          30000,
    "frontend_inactivity_check_ms":     30000,
    "frontend_tts_chunk_size_chars":    250,

    # ── AI cost controls (response cache + per-tenant budget gate) ────
    # Master switches + knobs for the cost features. Default OFF so they
    # stay opt-in. The matching env vars below still work as the deploy-
    # time override layer (DB value set via the UI wins).
    "response_cache_enabled":       False,
    "response_cache_ttl_seconds":   21600,   # 6 h
    "budget_enforcement_enabled":   False,
    "budget_hard_multiplier":       1.0,     # decline at cap * this (>1 = grace band)
    "budget_cache_ttl_seconds":     60,
    "budget_exceeded_message":      "",      # blank → built-in polite default

    # ── Rate limits (platform-wide, enforced on /chat + /chat/stream) ──
    # Distributed fixed-window counters in Mongo (security/rate_limiter.py).
    # 0 on any row disables that dimension. The per-IP minute cap is
    # multiplied by the burst multiplier. Per-second rows default to 0
    # (off) — turn them on per deployment, mindful that many users can
    # share one IP behind NAT.
    "rate_limit_ip_per_sec":        0,
    "rate_limit_ip_per_min":        30,
    "rate_limit_ip_per_hour":       500,
    "rate_limit_burst_multiplier":  1.5,
    "rate_limit_user_per_sec":      0,
    "rate_limit_user_per_min":      20,
    "rate_limit_user_per_day":      500,
}

# Env-var overrides. Maps the ``platform_config`` key → env-var name.
# When the env var is set and the DB row hasn't overridden the key, the
# env value wins. Useful for staging/prod knobs without DB writes.
_ENV_OVERRIDES: Dict[str, str] = {
    "kb_crawl_interval_seconds":    "KB_CRAWL_INTERVAL_SECONDS",
    "kb_cache_ttl_seconds":         "KB_CACHE_TTL_SECONDS",
    "session_cleanup_interval_seconds": "SESSION_CLEANUP_INTERVAL_SECONDS",
    # AI cost controls — existing env-var names stay as the deploy-time layer.
    "response_cache_enabled":       "RESPONSE_CACHE_ENABLED",
    "response_cache_ttl_seconds":   "RESPONSE_CACHE_TTL_SECONDS",
    "budget_enforcement_enabled":   "BUDGET_ENFORCEMENT_ENABLED",
    "budget_hard_multiplier":       "BUDGET_HARD_MULTIPLIER",
    "budget_cache_ttl_seconds":     "BUDGET_CACHE_TTL_SECONDS",
    "budget_exceeded_message":      "BUDGET_EXCEEDED_MESSAGE",
    # Rate limits keep their existing env-var names as the deploy-time
    # override layer (DB value set via the UI still wins over these).
    "rate_limit_ip_per_sec":        "RATE_LIMIT_IP_PER_SEC",
    "rate_limit_ip_per_min":        "RATE_LIMIT_IP_PER_MIN",
    "rate_limit_ip_per_hour":       "RATE_LIMIT_IP_PER_HOUR",
    "rate_limit_burst_multiplier":  "RATE_LIMIT_BURST_MULTIPLIER",
    "rate_limit_user_per_sec":      "RATE_LIMIT_USER_PER_SEC",
    "rate_limit_user_per_min":      "RATE_LIMIT_USER_PER_MIN",
    "rate_limit_user_per_day":      "RATE_LIMIT_USER_PER_DAY",
}


# ── In-process cache ────────────────────────────────────────────────────────

_TTL = 60
_cache_value: Optional[Dict[str, Any]] = None
_cache_expiry: float = 0.0


def invalidate_cache() -> None:
    """Drop the in-process cache. Call after a super-admin PUT."""
    global _cache_value, _cache_expiry
    _cache_value = None
    _cache_expiry = 0.0


def _from_env(key: str) -> Optional[Any]:
    """Read ``key`` from its mapped env var if any. Returns the raw string
    coerced to the same type as the default (int for int defaults, list for
    JSON list defaults, otherwise str)."""
    env_name = _ENV_OVERRIDES.get(key)
    if not env_name:
        return None
    raw = os.environ.get(env_name)
    if raw is None:
        return None
    dflt = DEFAULTS.get(key)
    try:
        if isinstance(dflt, bool):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(dflt, int):
            return int(raw)
        if isinstance(dflt, float):
            return float(raw)
        if isinstance(dflt, list):
            import json
            return json.loads(raw)
        return raw
    except Exception as exc:
        logger.warning("[platform_config] env %s=%r could not be coerced: %s", env_name, raw, exc)
        return None


def _merge(stored: Dict[str, Any]) -> Dict[str, Any]:
    """Apply precedence: DB → env → default. Unknown keys in ``stored`` are
    preserved so a newer admin UI can introduce keys without an immediate
    code release (the consumer just gets the value via ``get``)."""
    out: Dict[str, Any] = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in stored and stored[key] not in (None, "", []):
            out[key] = stored[key]
            continue
        env_val = _from_env(key)
        if env_val is not None:
            out[key] = env_val
    # Pass through unknown keys from the stored doc as-is so the UI can
    # render them under "Other" and a future consumer reads them via get().
    for key, val in (stored or {}).items():
        if key not in out:
            out[key] = val
    return out


async def _load_from_db() -> Dict[str, Any]:
    """Async DB read. Returns the merged dict (DB → env → default)."""
    try:
        from database import get_database
        db = await get_database()
        stored = await db.platform_config.find_one(
            {"_id": _DOC_ID}, {"_id": 0}
        ) or {}
    except Exception as exc:
        logger.debug("[platform_config] DB read failed (%s) — using defaults", exc)
        stored = {}
    return _merge(stored)


async def ensure_loaded() -> Dict[str, Any]:
    """Async: refresh the cache from DB if stale, then return the resolved
    dict. Most consumers want :py:func:`get` instead; this is for super-admin
    routes that need the full dict for serialisation."""
    global _cache_value, _cache_expiry
    now = time.monotonic()
    if _cache_value is None or now >= _cache_expiry:
        _cache_value = await _load_from_db()
        _cache_expiry = now + _TTL
    return dict(_cache_value)


def get(key: str, default: Any = None) -> Any:
    """Synchronous getter — returns the cached value, or the platform
    default if the cache is empty / the key is unknown. Falls back to
    ``default`` only if the key is missing from ``DEFAULTS`` too.

    This never reads the DB. Call :py:func:`ensure_loaded` once at server
    startup (or rely on the first super-admin GET) to seed the cache.
    """
    if _cache_value is not None and key in _cache_value:
        return _cache_value[key]
    # Cache empty — fall through to env / hardcoded default so the bot
    # still works on cold start (e.g. before the lifespan task runs).
    env_val = _from_env(key)
    if env_val is not None:
        return env_val
    if key in DEFAULTS:
        return DEFAULTS[key]
    return default


async def save(patch: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert the singleton doc with the supplied patch (shallow merge
    against the existing row). Drops the cache. Returns the resolved
    config after the write."""
    from database import get_database
    db = await get_database()
    existing = await db.platform_config.find_one({"_id": _DOC_ID}, {"_id": 0}) or {}
    merged_doc = {**existing, **(patch or {})}
    await db.platform_config.update_one(
        {"_id": _DOC_ID},
        {"$set": merged_doc},
        upsert=True,
    )
    invalidate_cache()
    return await ensure_loaded()
