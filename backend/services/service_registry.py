"""Per-tenant service catalogue (passport, visa, OCI, PCC, ...).

Reads the ``tenant_services`` collection. Replaces the hardcoded
``SERVICES`` dict that used to live in ``services/application_flow.py``
(Sprint 4C). The application_flow state machine now loads service
definitions through this registry on every request.

Single read path:
    services = await list_services(company_id)         # ordered, enabled-only
    svc      = await get_service(company_id, "passport")

Caching: 60s TTL, per-tenant. Super-admin writes (4D) MUST call
``invalidate_cache(company_id)`` so the change is visible on the next
request — same contract as ``services.bot_config``.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger("services.service_registry")


# ── Service dataclass ───────────────────────────────────────────────────────

@dataclass
class Service:
    """In-memory view of one ``tenant_services`` row.

    Mirrors the migration-0006 schema. Fields without a stored value get
    sensible defaults so the engine never crashes on a partially-defined
    service (operators can add missing pieces incrementally via the
    super-admin UI in 4D)."""
    company_id:    str
    service_key:   str
    name:          str
    description:   str  = ""
    documents:     List[str]                = field(default_factory=list)
    fields:        List[Dict[str, Any]]     = field(default_factory=list)
    category:      str  = "TYPE_A"
    external_url:  Optional[str]            = None
    enabled:       bool = True
    display_order: int  = 0
    raw:           Dict[str, Any]           = field(default_factory=dict)

    def field_keys(self) -> List[str]:
        return [f.get("key") for f in self.fields if f.get("key")]

    def field_at(self, index: int) -> Optional[Dict[str, Any]]:
        if 0 <= index < len(self.fields):
            return self.fields[index]
        return None

    def is_redirect_only(self) -> bool:
        """TYPE_B services hand the user off to an external portal (VFS Global,
        passportindia.gov.in) rather than collecting data in-house."""
        return self.category == "TYPE_B"


def _row_to_service(row: Dict[str, Any]) -> Service:
    return Service(
        company_id=row["company_id"],
        service_key=row["service_key"],
        name=row.get("name") or row["service_key"].title(),
        description=row.get("description") or "",
        documents=list(row.get("documents") or []),
        fields=list(row.get("fields") or []),
        category=row.get("category") or "TYPE_A",
        external_url=row.get("external_url"),
        enabled=bool(row.get("enabled", True)),
        display_order=int(row.get("display_order") or 0),
        raw=row,
    )


# ── TTL cache ───────────────────────────────────────────────────────────────

_CACHE_TTL_SECONDS = 60
_list_cache:   Dict[str, tuple[float, List[Service]]] = {}   # (company_id, all-enabled) → (expiry, services)
_lookup_cache: Dict[str, tuple[float, Dict[str, Service]]] = {}  # company_id → (expiry, {key: Service})


def invalidate_cache(company_id: Optional[str] = None) -> None:
    """Drop one tenant from the cache, or the whole cache if None."""
    if company_id is None:
        _list_cache.clear()
        _lookup_cache.clear()
    else:
        _list_cache.pop(company_id, None)
        _lookup_cache.pop(company_id, None)


# ── Public API ──────────────────────────────────────────────────────────────

async def _load_all(company_id: str) -> List[Service]:
    """Load all rows (enabled and disabled) for a tenant, sorted by
    ``display_order``. Used by both list_services() and get_service() so
    we keep a single cache key per tenant."""
    db = await get_database()
    rows = await db.tenant_services.find(
        {"company_id": company_id}, {"_id": 0},
    ).sort("display_order", 1).to_list(500)
    return [_row_to_service(r) for r in rows]


async def list_services(company_id: str, enabled_only: bool = True) -> List[Service]:
    """All services for a tenant, ordered by display_order. By default
    only ``enabled=True`` services are returned (what the chatbot offers);
    pass ``enabled_only=False`` from the super-admin UI to see the full set."""
    now = time.monotonic()
    cached = _list_cache.get(company_id)
    if cached and cached[0] > now:
        services = cached[1]
    else:
        services = await _load_all(company_id)
        _list_cache[company_id] = (now + _CACHE_TTL_SECONDS, services)
        # warm the lookup cache too — same DB round-trip
        _lookup_cache[company_id] = (now + _CACHE_TTL_SECONDS, {s.service_key: s for s in services})

    if enabled_only:
        return [s for s in services if s.enabled]
    return list(services)


async def get_service(company_id: str, service_key: str) -> Optional[Service]:
    """One service by key (or None). Returns disabled services too — let
    the caller decide whether to skip them, since deep-links into a
    disabled service should still be resolvable for status checks."""
    now = time.monotonic()
    cached = _lookup_cache.get(company_id)
    if cached and cached[0] > now:
        return cached[1].get(service_key)

    # Cache miss → load all (warms the list cache as a side effect)
    services = await list_services(company_id, enabled_only=False)
    return next((s for s in services if s.service_key == service_key), None)


async def service_keys(company_id: str, enabled_only: bool = True) -> List[str]:
    """Convenience: just the keys, in display order."""
    services = await list_services(company_id, enabled_only=enabled_only)
    return [s.service_key for s in services]
