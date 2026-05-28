"""Per-tenant monthly LLM budget enforcement (opt-in).

Turns ``companies.llm_monthly_budget_usd`` from an informational dashboard
number into a real PRE-FLIGHT gate: once a tenant's month-to-date LLM spend
(from the ``llm_usage`` ledger) reaches its configured monthly budget, further
LLM calls are soft-declined by the route. Cache hits still serve — the chat
routes consult ``response_cache`` BEFORE this gate, so a repeat FAQ is answered
for free even when the tenant is capped (graceful degradation, not a hard wall).

Design / safety:
- Default OFF (``BUDGET_ENFORCEMENT_ENABLED``) — opt-in per environment, in line
  with the other cost features.
- A tenant with no / zero / negative budget is treated as UNLIMITED (never
  gated), so enabling the feature can't accidentally block tenants who never
  opted into a cap.
- The decision is per-process TTL-cached (``BUDGET_CACHE_TTL_SECONDS``, default
  60s) so the hot chat path doesn't aggregate the ledger on every request. Worst
  case a tenant overspends for up to one TTL window — fine for a soft monthly
  cap, and the same trade-off the other per-process caches make.
- Fails OPEN: any error (DB hiccup, bad config) returns "not over budget" so a
  limiter fault never blocks real users.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Dict, Optional, Tuple

from database import get_database

logger = logging.getLogger("services.budget_guard")

_CACHE_TTL = int(os.environ.get("BUDGET_CACHE_TTL_SECONDS", "60"))
_DEFAULT_MSG = (
    "We've reached the current usage limit for this assistant. Please try again "
    "later, or contact the office directly if your matter is urgent."
)

# company_id -> (over_budget, expires_at_epoch)
_decision_cache: Dict[str, Tuple[bool, float]] = {}


def enabled() -> bool:
    """Master switch — default OFF so rollout is opt-in per environment."""
    return os.environ.get("BUDGET_ENFORCEMENT_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )


def exceeded_message() -> str:
    """The message returned to the user when a tenant is over budget. Override
    per deployment via ``BUDGET_EXCEEDED_MESSAGE``."""
    return os.environ.get("BUDGET_EXCEEDED_MESSAGE") or _DEFAULT_MSG


def _hard_multiplier() -> float:
    """Block at ``budget * multiplier``. 1.0 = decline exactly at the configured
    cap; set >1.0 to allow a grace band before hard-declining."""
    try:
        return float(os.environ.get("BUDGET_HARD_MULTIPLIER", "1.0"))
    except ValueError:
        return 1.0


def invalidate_cache(company_id: Optional[str] = None) -> None:
    """Drop a tenant's cached decision (or all). Call after a budget change so a
    new cap takes effect without waiting out the TTL."""
    if company_id is None:
        _decision_cache.clear()
    else:
        _decision_cache.pop(company_id, None)


async def is_over_budget(company_id: str) -> bool:
    """True when the tenant should be gated for this request.

    No-op (False) when disabled, no company, or the tenant has no positive
    budget configured. TTL-cached per process. Fails OPEN on any error.
    """
    if not enabled() or not company_id:
        return False

    now = time.time()
    cached = _decision_cache.get(company_id)
    if cached and cached[1] > now:
        return cached[0]

    try:
        db = await get_database()
        company = await db.companies.find_one(
            {"id": company_id}, {"_id": 0, "llm_monthly_budget_usd": 1}
        )
        budget = float((company or {}).get("llm_monthly_budget_usd") or 0.0)
        if budget <= 0:
            decision = False  # no cap configured → unlimited
        else:
            from services import llm_usage
            spent = await llm_usage.month_to_date_cost(company_id)
            decision = spent >= budget * _hard_multiplier()
            if decision:
                logger.warning(
                    "tenant %s over LLM budget: MTD $%.4f >= cap $%.2f — gating LLM calls",
                    company_id, spent, budget,
                )
    except Exception as e:
        logger.warning("budget_guard.is_over_budget failed for %s (failing open): %s", company_id, e)
        return False

    _decision_cache[company_id] = (decision, now + _CACHE_TTL)
    return decision
