"""Per-request tenant resolution for multi-tenant HTTP routes.

`get_tenant_id` is a FastAPI dependency. Use it on any route that
operates on tenant-scoped data:

    from tenant import get_tenant_id

    @router.get("/things")
    async def list_things(company_id: str = Depends(get_tenant_id)):
        return await db.things.find({"company_id": company_id}).to_list(100)

Resolution order:
  1. `X-Company-Id` HTTP header (multi-tenant clients — the widget, the
     super-admin dashboard, anything embedded in a tenant context)
  2. `config.COMPANY_ID` env var (back-compat for single-tenant routes
     during the Sprint 1 -> Sprint 2 migration)
  3. -> 400 Bad Request if neither is present.

Webhook routes (WhatsApp / Facebook) do not carry an X-Company-Id header
because the request comes from a third party. They should use
`services.messaging_channel_resolver.resolve_company_from_channel`
instead -- that path infers the tenant from the inbound channel identity.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import Header, HTTPException, status

import config
from database import get_database

logger = logging.getLogger("tenant")

# Small TTL cache so we don't hit Mongo for every authenticated request.
# A deactivated tenant is rejected within at most _cache_ttl() seconds.
_validity_cache: dict[str, float] = {}   # input_id -> expiry monotonic ts
_alias_cache: dict[str, str] = {}        # input_id -> resolved company_id (for bot_id aliases)


def _cache_ttl() -> int:
    try:
        from services import platform_config
        return int(platform_config.get("cache_tenant_ttl_seconds", 60))
    except Exception:
        return 60


async def _resolve_company(candidate: str):
    """Return the actual company id for a candidate (direct id or bot_id alias).
    Returns None if no active company matches."""
    now = time.monotonic()
    expiry = _validity_cache.get(candidate)
    if expiry is not None and expiry > now:
        return _alias_cache.get(candidate, candidate)

    db = await get_database()
    # 1. Direct id match
    found = await db.companies.find_one(
        {"id": candidate, "status": "active"},
        {"_id": 0, "id": 1},
    )
    if found:
        _validity_cache[candidate] = now + _cache_ttl()
        return candidate

    # 2. bot_id alias match (e.g. data-bot-id="1" on the embed script)
    found = await db.companies.find_one(
        {"bot_id": candidate, "status": "active"},
        {"_id": 0, "id": 1},
    )
    if not found:
        return None

    actual_id = found["id"]
    _validity_cache[candidate] = now + _cache_ttl()
    _alias_cache[candidate] = actual_id
    return actual_id


async def _is_active_company(company_id: str) -> bool:
    return await _resolve_company(company_id) is not None


def invalidate_cache(company_id: Optional[str] = None) -> None:
    """Drop a single tenant or the whole cache."""
    if company_id is None:
        _validity_cache.clear()
        _alias_cache.clear()
    else:
        _validity_cache.pop(company_id, None)
        _alias_cache.pop(company_id, None)


async def get_tenant_id(
    x_company_id: Optional[str] = Header(None, alias="X-Company-Id"),
) -> str:
    """FastAPI dependency: resolve and validate the calling tenant."""
    candidate = (x_company_id or "").strip() or (config.COMPANY_ID or "")
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Company-Id header (and no default tenant configured).",
        )

    resolved = await _resolve_company(candidate)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown or inactive tenant: {candidate!r}",
        )
    return resolved
