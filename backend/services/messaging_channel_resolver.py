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
# TTL is platform-config driven (cache_messaging_channel_ttl_seconds).
_resolver_cache: Dict[Tuple[str, str], Tuple[float, str]] = {}

# Separate cache for per-channel SENDING credentials (decrypted {user,pass,from}
# or None). Kept apart from the company-id cache because it's read on the
# outbound hot path (possibly several sends per inbound message) and holds
# decrypted secrets only in-process. Same TTL + invalidation contract.
_creds_cache: Dict[Tuple[str, str], Tuple[float, Optional[dict]]] = {}


def _cache_ttl() -> int:
    try:
        from services import platform_config
        return int(platform_config.get("cache_messaging_channel_ttl_seconds", 60))
    except Exception:
        return 60


def _cache_key(channel_type: str, external_id: str) -> Tuple[str, str]:
    return (channel_type, external_id)


def invalidate_cache(channel_type: Optional[str] = None, external_id: Optional[str] = None) -> None:
    """Drop one entry from the cache, or the whole cache if both args are None.

    Called by the channel-mapping CRUD writes so the next inbound message
    sees the change immediately (otherwise the cached value lingers for
    up to ``_cache_ttl()``)."""
    if channel_type is None and external_id is None:
        _resolver_cache.clear()
        _creds_cache.clear()
    elif channel_type is not None and external_id is not None:
        k = _cache_key(channel_type, external_id)
        _resolver_cache.pop(k, None)
        _creds_cache.pop(k, None)
    else:
        # Partial-key invalidation — drop every entry matching the given dimension
        for cache in (_resolver_cache, _creds_cache):
            keys_to_drop = [
                k for k in cache
                if (channel_type is None or k[0] == channel_type)
                and (external_id is None or k[1] == external_id)
            ]
            for k in keys_to_drop:
                cache.pop(k, None)


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
        _resolver_cache[key] = (now + _cache_ttl(), resolved)
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
    _resolver_cache[key] = (now + _cache_ttl(), config.COMPANY_ID)
    return config.COMPANY_ID


async def resolve_channel_credentials(channel_type: str, external_id: str) -> Optional[dict]:
    """Return the SENDING credentials for this channel/number, or None when no
    per-tenant credentials are configured (caller falls back to env globals).

    Shape: ``{"user": str, "pass": str, "from": external_id}``. The password is
    stored Fernet-encrypted (``send_pass_enc``) and decrypted here; a missing
    key or undecryptable value yields None (→ env fallback, logged once).
    TTL-cached per-process like :func:`resolve_company_from_channel`."""
    if not external_id:
        return None
    key = _cache_key(channel_type, external_id)
    now = time.monotonic()
    cached = _creds_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    creds: Optional[dict] = None
    try:
        db = await get_database()
        row = await db.messaging_channel_map.find_one(
            {"channel_type": channel_type, "external_id": external_id},
            {"_id": 0, "send_user": 1, "send_pass_enc": 1},
        )
        if row and row.get("send_user") and row.get("send_pass_enc"):
            from security.crypto import decrypt_secret
            pw = decrypt_secret(row.get("send_pass_enc"))
            if pw:
                creds = {"user": row["send_user"], "pass": pw, "from": external_id}
    except Exception as e:
        logger.warning("resolve_channel_credentials failed for %s:%s — %s", channel_type, external_id, e)

    _creds_cache[key] = (now + _cache_ttl(), creds)
    return creds


async def map_channel_to_company(
    channel_type: str,
    external_id: str,
    company_id: str,
    *,
    metadata: dict | None = None,
    send_user: str | None = None,
    send_pass: str | None = None,
) -> None:
    """Register a (channel_type, external_id) → company_id mapping.

    Optional per-tenant sending credentials: pass ``send_user`` + ``send_pass``
    (the raw password is Fernet-encrypted before storage). Either both or
    neither — omit to leave existing credentials untouched. ``encrypt_secret``
    raises if no ``CHANNEL_CRED_KEY`` is configured, so a plaintext secret is
    never persisted.

    Invalidates the resolver cache so the change takes effect on the very
    next inbound message rather than waiting for the TTL to expire."""
    set_doc: dict = {"company_id": company_id, "metadata": metadata or {}}
    if send_user is not None:
        set_doc["send_user"] = send_user
    if send_pass is not None:
        from security.crypto import encrypt_secret
        set_doc["send_pass_enc"] = encrypt_secret(send_pass)

    db = await get_database()
    await db.messaging_channel_map.update_one(
        {"channel_type": channel_type, "external_id": external_id},
        {
            "$set":         set_doc,
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
