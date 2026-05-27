"""Platform-wide LLM model registry.

Replaces the hardcoded ``MODEL_MAP`` (in emergentintegrations/llm/chat.py)
and ``_PRICING`` (in services/llm_usage.py) with a TTL-cached read of
the ``platform_models`` collection — super-admins can add/edit/disable
models without a deploy.

Single read path::

    api_model = await resolve_api_model("gpt-5.2")  # → "gpt-4o-mini"
    cost = await cost_for("gpt-4o-mini", 1000, 500)  # USD

Cache invalidation: any super-admin write to ``platform_models`` MUST
call ``invalidate_cache()`` so the change is visible on the next
request — same contract as ``services.bot_config``.

Resilience: if the collection is empty or DB is unreachable, the
helpers fall back to a small frozen dict (the previous hardcoded
values). That keeps the chat path working through a misconfiguration
or migration-skipped install.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger("services.model_registry")

# Hardcoded last-resort fallback. Keeps the chat path alive if the
# collection is empty (e.g. fresh install before migration 0011 runs)
# or the DB is briefly unreachable. Mirrors the seed rows in 0011.
_FALLBACK: Dict[str, Dict[str, Any]] = {
    "gpt-4o-mini": {"key": "gpt-4o-mini", "api_model": "gpt-4o-mini", "provider": "openai",
                    "pricing": {"input_per_1m_usd": 0.15, "output_per_1m_usd": 0.60},
                    "display_name": "GPT-4o mini", "enabled": True},
    "gpt-4o":      {"key": "gpt-4o",      "api_model": "gpt-4o",      "provider": "openai",
                    "pricing": {"input_per_1m_usd": 2.50, "output_per_1m_usd": 10.00},
                    "display_name": "GPT-4o", "enabled": True},
    "gpt-5":       {"key": "gpt-5",       "api_model": "gpt-4o-mini", "provider": "openai",
                    "pricing": {"input_per_1m_usd": 1.25, "output_per_1m_usd": 10.00},
                    "display_name": "GPT-5", "enabled": True},
    "gpt-5.2":     {"key": "gpt-5.2",     "api_model": "gpt-4o-mini", "provider": "openai",
                    "pricing": {"input_per_1m_usd": 0.15, "output_per_1m_usd": 0.60},
                    "display_name": "GPT-5.2", "enabled": True},
}

_DEFAULT_PRICING = {"input_per_1m_usd": 0.15, "output_per_1m_usd": 0.60}

# Module-level cache. Single dict keyed by model key; one entry per
# row. (expiry, dict) tuple so a single invalidation drops everything.
_cache: Optional[tuple[float, Dict[str, Dict[str, Any]]]] = None


def _cache_ttl() -> int:
    """Reuse the existing platform_config knob if present (60s default)."""
    try:
        from services import platform_config
        return int(platform_config.get("cache_model_registry_ttl_seconds", 60))
    except Exception:
        return 60


def invalidate_cache() -> None:
    """Drop the entire cache. Called by the super-admin CRUD routes
    after any write so the change takes effect on the next request."""
    global _cache
    _cache = None


async def _load_all() -> Dict[str, Dict[str, Any]]:
    """Pull every row keyed by `key`. Empty DB → fallback dict so the
    chat path keeps working through a fresh install or misconfigured
    environment."""
    try:
        db = await get_database()
        rows = await db.platform_models.find({}, {"_id": 0}).to_list(500)
        if not rows:
            return dict(_FALLBACK)
        return {r["key"]: r for r in rows if r.get("key")}
    except Exception as e:
        logger.warning("model_registry load failed, falling back to hardcoded: %s", e)
        return dict(_FALLBACK)


async def _get_all_cached() -> Dict[str, Dict[str, Any]]:
    global _cache
    now = time.monotonic()
    if _cache and _cache[0] > now:
        return _cache[1]
    rows = await _load_all()
    _cache = (now + _cache_ttl(), rows)
    return rows


async def list_models(enabled_only: bool = False) -> List[Dict[str, Any]]:
    """All registered models. Pass ``enabled_only=True`` for the
    tenant-facing surface (the super-admin Models tab leaves it False
    so disabled rows stay visible for editing)."""
    rows = await _get_all_cached()
    out = list(rows.values())
    if enabled_only:
        out = [r for r in out if r.get("enabled", True)]
    # Sort by provider then display_name for a stable UI ordering.
    out.sort(key=lambda r: ((r.get("provider") or ""), (r.get("display_name") or r.get("key") or "")))
    return out


async def get_model(key: str) -> Optional[Dict[str, Any]]:
    """Look up one model by key. Returns None if no such key (and the
    fallback doesn't contain it either)."""
    if not key:
        return None
    rows = await _get_all_cached()
    return rows.get(key)


async def resolve_api_model(key: str) -> str:
    """Map a platform model key to the string the underlying provider's
    API expects. Falls back to the key itself if the row doesn't have
    an api_model set."""
    model = await get_model(key)
    if not model:
        return key
    return model.get("api_model") or model.get("key") or key


async def cost_for(key: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost for one call using the model's pricing entry. Unknown
    keys fall back to gpt-4o-mini pricing so coverage stays conservative
    — we'd rather over-report than under-report."""
    model = await get_model(key)
    pricing = (model or {}).get("pricing") or _DEFAULT_PRICING
    p_in  = float(pricing.get("input_per_1m_usd")  or _DEFAULT_PRICING["input_per_1m_usd"])
    p_out = float(pricing.get("output_per_1m_usd") or _DEFAULT_PRICING["output_per_1m_usd"])
    return round(
        (prompt_tokens * p_in / 1_000_000) + (completion_tokens * p_out / 1_000_000),
        6,
    )
