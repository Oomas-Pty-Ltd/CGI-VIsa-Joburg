"""Resolve which tenant owns an inbound messaging channel.

Used by WhatsApp / Facebook / ICS-WABA webhook handlers — those requests
come from a third party (Meta, Twilio, ICS) so they don't carry an
`X-Company-Id` header. Instead the tenant is inferred from the inbound
channel identity (phone number, page ID, etc.).

Sprint 5 flipped this from a hardcode to a real lookup against
``messaging_channel_map``. Operators configure mappings via the
super-admin channel-mapping endpoints; the resolver caches results
per-process (60s TTL) so the hot webhook path doesn't DB-roundtrip on
every inbound message.

Fallback: if no mapping exists for a given (channel_type, external_id)
the resolver returns the env-var default tenant (``config.COMPANY_ID``)
with a WARNING log. This keeps single-tenant deployments working
without any mappings being created, and gives multi-tenant deployments
a visible signal when an unmapped channel hits the webhook.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Tuple

import config
from database import get_database

logger = logging.getLogger("services.messaging_channel_resolver")

# Supported channel types. Keep in sync with the values handlers pass in.
CHANNEL_WHATSAPP_TWILIO = "whatsapp_twilio"
CHANNEL_ICS_WABA = "ics_waba"
CHANNEL_FACEBOOK = "facebook"


# ── Per-process TTL cache ───────────────────────────────────────────────────
# Same pattern as services.bot_config and services.service_registry. Caches
# both hits AND misses (fallback to default tenant) so an unmapped flood
# doesn't repeatedly DB-query + log-warn. invalidate_cache() drops a key
# when the super-admin CRUD writes — same contract as bot_config.
_CACHE_TTL_SECONDS = 60
_resolver_cache: Dict[Tuple[str, str], Tuple[float, str]] = {}


def _cache_key(channel_type: str, external_id: str) -> Tuple[str, str]:
    return (channel_type, external_id)


def invalidate_cache(channel_type: Optional[str] = None, external_id: Optional[str] = None) -> None:
    """Drop one entry from the cache, or the whole cache if both args are None.

    Called by the channel-mapping CRUD writes so the next inbound message
    sees the change immediately (otherwise the cached value lingers for
    up to ``_CACHE_TTL_SECONDS``)."""
    if channel_type is None and external_id is None:
        _resolver_cache.clear()
    elif channel_type is not None and external_id is not None:
        _resolver_cache.pop(_cache_key(channel_type, external_id), None)
    else:
        # Partial-key invalidation — drop every entry matching the given dimension
        keys_to_drop = [
            k for k in _resolver_cache
            if (channel_type is None or k[0] == channel_type)
            and (external_id is None or k[1] == external_id)
        ]
        for k in keys_to_drop:
            _resolver_cache.pop(k, None)


async def resolve_company_from_channel(channel_type: str, external_id: str) -> str:
    """Return the company_id that owns inbound traffic on this channel.

    Lookup order:
      1. Per-process TTL cache  (≤ 60s old)
      2. ``messaging_channel_map`` row
      3. ``config.COMPANY_ID`` fallback  (logged as WARNING)

    Args:
      channel_type: one of CHANNEL_*  (whatsapp_twilio / ics_waba / facebook)
      external_id:  channel-specific identifier — phone number for WhatsApp,
                    page ID for Facebook, business number for ICS.
    """
    if not config.COMPANY_ID:
        raise RuntimeError(
            "config.COMPANY_ID is not initialised — channel resolver has no "
            "default tenant to fall back to. Did server startup complete?"
        )

    key = _cache_key(channel_type, external_id)
    now = time.monotonic()

    # 1. Cache hit
    cached = _resolver_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    # 2. DB lookup
    db = await get_database()
    row = await db.messaging_channel_map.find_one(
        {"channel_type": channel_type, "external_id": external_id},
        {"_id": 0, "company_id": 1},
    )
    if row and row.get("company_id"):
        resolved = row["company_id"]
        _resolver_cache[key] = (now + _CACHE_TTL_SECONDS, resolved)
        logger.debug(
            "channel resolver: %s:%s → %s (mapped)",
            channel_type, external_id, resolved,
        )
        return resolved

    # 3. Fallback to default tenant — warn loudly so unmapped channels are visible
    logger.warning(
        "channel resolver: no mapping for %s:%s → falling back to default tenant %s. "
        "Create a mapping via the super-admin channel-mapping endpoint to silence this.",
        channel_type, external_id, config.COMPANY_ID,
    )
    _resolver_cache[key] = (now + _CACHE_TTL_SECONDS, config.COMPANY_ID)
    return config.COMPANY_ID


async def map_channel_to_company(
    channel_type: str,
    external_id: str,
    company_id: str,
    *,
    metadata: dict | None = None,
) -> None:
    """Register a (channel_type, external_id) → company_id mapping.

    Invalidates the resolver cache so the change takes effect on the very
    next inbound message rather than waiting for the TTL to expire."""
    db = await get_database()
    await db.messaging_channel_map.update_one(
        {"channel_type": channel_type, "external_id": external_id},
        {
            "$set":         {"company_id": company_id, "metadata": metadata or {}},
            "$setOnInsert": {"channel_type": channel_type, "external_id": external_id},
        },
        upsert=True,
    )
    invalidate_cache(channel_type, external_id)


async def delete_channel_mapping(channel_type: str, external_id: str) -> bool:
    """Remove a (channel_type, external_id) mapping. Returns True if a row
    was deleted, False if none existed. After deletion the resolver falls
    back to ``config.COMPANY_ID`` for that channel (with the usual warning)."""
    db = await get_database()
    result = await db.messaging_channel_map.delete_one(
        {"channel_type": channel_type, "external_id": external_id}
    )
    invalidate_cache(channel_type, external_id)
    return result.deleted_count > 0


async def list_channel_mappings(
    channel_type: Optional[str] = None,
    company_id: Optional[str] = None,
) -> list:
    """List channel mappings, optionally filtered by channel_type or by tenant.
    Used by the super-admin UI to inspect what's configured."""
    db = await get_database()
    query: Dict[str, str] = {}
    if channel_type is not None:
        query["channel_type"] = channel_type
    if company_id is not None:
        query["company_id"] = company_id
    return await db.messaging_channel_map.find(query, {"_id": 0}).to_list(500)
