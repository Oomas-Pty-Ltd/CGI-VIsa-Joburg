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
     during the Sprint 1 → Sprint 2 migration)
  3. → 400 Bad Request if neither is present.

Webhook routes (WhatsApp / Facebook) don't carry an X-Company-Id header
because the request comes from a third party. They should use
`services.messaging_channel_resolver.resolve_company_from_channel`
instead — that path infers the tenant from the inbound channel identity.
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
# A deactivated tenant is rejected within at most _CACHE_TTL_SECONDS.
_CACHE_TTL_SECONDS = 60
_validity_cache: dict[str, float] = {}   # company_id -> expiry monotonic ts


async def _is_active_company(company_id: str) -> bool:
    now = time.monotonic()
    expiry = _validity_cache.get(company_id)
    if expiry is not None and expiry > now:
        return True

    db = await get_database()
    found = await db.companies.find_one(
        {"id": company_id, "status": "active"},
        {"_id": 0, "id": 1},
    )
    if not found:
        # Don't cache negatives — let the next request re-check in case the
        # tenant was just (re-)activated.
        return False

    _validity_cache[company_id] = now + _CACHE_TTL_SECONDS
    return True


def invalidate_cache(company_id: Optional[str] = None) -> None:
    """Drop a single tenant or the whole cache. Call after a company is
    deactivated or its `status` flips, so the change is picked up immediately."""
    if company_id is None:
        _validity_cache.clear()
    else:
        _validity_cache.pop(company_id, None)


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

    if not await _is_active_company(candidate):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown or inactive tenant: {candidate!r}",
        )
    return candidate
