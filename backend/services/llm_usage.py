"""Per-tenant LLM cost tracking.

Every chat-stream call that touches the LLM writes a small row into
``llm_usage`` keyed by tenant + day, so the local-admin Cost tab can
render daily bars + month-to-date totals without re-running expensive
aggregations on raw chat sessions.

Schema (one document per LLM call):
    {
        company_id:   str,
        ts:           ISO-8601 UTC,
        day:          "YYYY-MM-DD" (denormalised for cheap day-grouping),
        model:        "gpt-4o-mini" / etc,
        prompt_tokens:     int,
        completion_tokens: int,
        cost_usd:     float,
    }

Pricing is a hardcoded table for v1. Models we map through the SDK shim
(see emergentintegrations/llm/chat.MODEL_MAP) are billed at the rate of
the *real* model they resolve to.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from database import get_database

logger = logging.getLogger("services.llm_usage")


# OpenAI public pricing as of 2026-05 (USD per 1M tokens). Update here
# when OpenAI moves prices, or move into platform_config later. Any
# model not listed falls back to the gpt-4o-mini rate so a new SKU
# doesn't silently log $0 — usage will still over-report rather than
# under-report.
_PRICING: Dict[str, Tuple[float, float]] = {
    # (input_per_1M, output_per_1M)
    "gpt-4o":          (2.50, 10.00),
    "gpt-4o-mini":     (0.15,  0.60),
    "gpt-4.1":         (2.00,  8.00),
    "gpt-4.1-mini":    (0.40,  1.60),
    "gpt-4.1-nano":    (0.10,  0.40),
    "gpt-5":           (1.25, 10.00),
    "gpt-5-mini":      (0.25,  2.00),
    # The shim's MODEL_MAP routes "gpt-5.2" → "gpt-4o-mini", so it
    # never lands here at log time, but list it for documentation.
    "gpt-5.2":         (0.15,  0.60),
}
_DEFAULT_PRICE = _PRICING["gpt-4o-mini"]


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Synchronous cost calculation — last-resort fallback used when
    the async registry path can't be awaited (legacy callers).

    Defaults to gpt-4o-mini pricing on unknown models so coverage stays
    conservative. Prefer ``cost_for_async`` from any async context — it
    consults the up-to-date platform_models row super-admins edit at
    runtime.
    """
    p_in, p_out = _PRICING.get(model, _DEFAULT_PRICE)
    return round(
        (prompt_tokens * p_in / 1_000_000) + (completion_tokens * p_out / 1_000_000),
        6,
    )


async def cost_for_async(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Look up pricing from the platform_models registry (TTL-cached).
    Falls back to the synchronous _PRICING table if the registry doesn't
    know this key — keeps the chat path resilient through a fresh
    install or a misconfigured row."""
    try:
        from services import model_registry
        return await model_registry.cost_for(model, prompt_tokens, completion_tokens)
    except Exception as e:
        logger.warning("model_registry cost_for failed for %s, using static fallback: %s", model, e)
        return cost_for(model, prompt_tokens, completion_tokens)


async def log(company_id: str, usage: Optional[Dict[str, Any]]) -> None:
    """Insert one usage row. Tolerant of missing / partial usage payloads
    so the chat path can call it unconditionally without if-guards."""
    if not company_id or not usage:
        return
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    if prompt + completion == 0:
        # Don't write empty rows — keeps the collection lean and the
        # daily grouping queries faster.
        return
    # Cached prompt tokens (OpenAI prompt cache). Billed at ~50% on gpt-4o-mini;
    # tracking it lets the Cost tab show prompt-cache effectiveness over time.
    cached = int(usage.get("cached_tokens") or 0)
    model = (usage.get("model") or "unknown")[:64]
    now = datetime.now(timezone.utc)
    # Pull pricing from the registry (TTL-cached) so a super-admin's
    # price edit takes effect on the next request. Synchronous fallback
    # is used if the registry can't be reached.
    cost = await cost_for_async(model, prompt, completion)
    doc = {
        "company_id":         company_id,
        "ts":                 now.isoformat(),
        "day":                now.strftime("%Y-%m-%d"),
        "model":              model,
        "prompt_tokens":      prompt,
        "completion_tokens":  completion,
        "cached_tokens":      cached,
        "cost_usd":           cost,
    }
    try:
        db = await get_database()
        await db.llm_usage.insert_one(doc)
    except Exception as e:
        # Never let logging break the chat path. The cost dashboard
        # will under-count, which is preferable to a 500.
        logger.warning("llm_usage.log failed for tenant %s: %s", company_id, e)


async def daily_totals(
    company_id: Optional[str],
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    """Per-day spend between [start, end] inclusive. Returns rows
    ordered by date, one per day even if the day had zero usage (the
    UI's bar chart needs the gaps filled).

    ``company_id=None`` aggregates across all tenants (super-admin
    platform-wide view).
    """
    db = await get_database()
    match: Dict[str, Any] = {
        "ts": {
            "$gte": start.isoformat(),
            "$lte": end.isoformat(),
        },
    }
    if company_id:
        match["company_id"] = company_id
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$day",
            "cost_usd":          {"$sum": "$cost_usd"},
            "prompt_tokens":     {"$sum": "$prompt_tokens"},
            "completion_tokens": {"$sum": "$completion_tokens"},
            "cached_tokens":     {"$sum": "$cached_tokens"},
            "calls":             {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    raw = {r["_id"]: r async for r in db.llm_usage.aggregate(pipeline)}

    # Fill missing days with zeros so the consumer chart doesn't have to.
    out: List[Dict[str, Any]] = []
    cur = start.date()
    end_date = end.date()
    while cur <= end_date:
        key = cur.strftime("%Y-%m-%d")
        row = raw.get(key)
        out.append({
            "day":               key,
            "cost_usd":          round(row["cost_usd"], 4) if row else 0.0,
            "prompt_tokens":     row["prompt_tokens"] if row else 0,
            "completion_tokens": row["completion_tokens"] if row else 0,
            "cached_tokens":     row.get("cached_tokens", 0) if row else 0,
            "calls":             row["calls"] if row else 0,
        })
        cur += timedelta(days=1)
    return out


async def model_breakdown(
    company_id: Optional[str],
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    """Per-model spend between [start, end] inclusive. Useful for the
    "which model is eating the budget" chip row.

    ``company_id=None`` aggregates across all tenants.
    """
    db = await get_database()
    match: Dict[str, Any] = {"ts": {"$gte": start.isoformat(), "$lte": end.isoformat()}}
    if company_id:
        match["company_id"] = company_id
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$model",
            "cost_usd":          {"$sum": "$cost_usd"},
            "prompt_tokens":     {"$sum": "$prompt_tokens"},
            "completion_tokens": {"$sum": "$completion_tokens"},
            "cached_tokens":     {"$sum": "$cached_tokens"},
            "calls":             {"$sum": 1},
        }},
        {"$sort": {"cost_usd": -1}},
    ]
    return [
        {
            "model":             r["_id"],
            "cost_usd":          round(r["cost_usd"], 4),
            "prompt_tokens":     r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "cached_tokens":     r.get("cached_tokens", 0),
            "calls":             r["calls"],
        }
        async for r in db.llm_usage.aggregate(pipeline)
    ]


async def tenant_breakdown(
    start: datetime,
    end: datetime,
) -> List[Dict[str, Any]]:
    """Per-tenant spend ranking for the platform-wide super-admin view.
    Returns the company name alongside the spend so the UI doesn't have
    to look up each id separately."""
    db = await get_database()
    pipeline = [
        {"$match": {"ts": {"$gte": start.isoformat(), "$lte": end.isoformat()}}},
        {"$group": {
            "_id": "$company_id",
            "cost_usd":          {"$sum": "$cost_usd"},
            "prompt_tokens":     {"$sum": "$prompt_tokens"},
            "completion_tokens": {"$sum": "$completion_tokens"},
            "cached_tokens":     {"$sum": "$cached_tokens"},
            "calls":             {"$sum": 1},
        }},
        {"$sort": {"cost_usd": -1}},
    ]
    rows = [r async for r in db.llm_usage.aggregate(pipeline)]
    if not rows:
        return []

    # Look up company names in one query rather than N. Tenants that
    # have since been deleted still appear (with an "unknown" label) so
    # the totals stay accounting-honest.
    ids = [r["_id"] for r in rows]
    name_by_id = {
        c["id"]: c.get("name", "")
        async for c in db.companies.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1})
    }
    return [
        {
            "company_id":        r["_id"],
            "name":              name_by_id.get(r["_id"]) or "(unknown tenant)",
            "cost_usd":          round(r["cost_usd"], 4),
            "prompt_tokens":     r["prompt_tokens"],
            "completion_tokens": r["completion_tokens"],
            "cached_tokens":     r.get("cached_tokens", 0),
            "calls":             r["calls"],
        }
        for r in rows
    ]


def budget_config() -> Dict[str, Any]:
    """Informational budget/model config for the cost dashboards (read from
    env). The retired in-memory cost_monitor enforced nothing live; these are
    surfaced so dashboards can show remaining headroom."""
    import os
    return {
        "daily_budget":   float(os.environ.get("DAILY_TOKEN_BUDGET", "50.0")),
        "monthly_budget": float(os.environ.get("MONTHLY_TOKEN_BUDGET", "1000.0")),
        "session_limit":  float(os.environ.get("SESSION_TOKEN_BUDGET", "1.0")),
        "model":          os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        "provider":       "openai",
        # gpt-4o-mini public rates (per 1k tokens) by default; pricing is really
        # per-model in the platform_models registry — these are indicative.
        "input_cost_per_1k":  float(os.environ.get("LLM_INPUT_COST_PER_1K", "0.00015")),
        "output_cost_per_1k": float(os.environ.get("LLM_OUTPUT_COST_PER_1K", "0.0006")),
    }


async def month_to_date_cost(company_id: str) -> float:
    """Total LLM spend (USD) for one tenant from the 1st of the current month
    (UTC) through now — the figure the budget gate compares against the tenant's
    monthly cap. Anchored to the 1st to match the operator's calendar intuition
    (same window as the local-admin budget gauge). One indexed aggregation;
    callers on the hot path should cache the result (see services.budget_guard).
    Returns 0.0 for an empty tenant."""
    if not company_id:
        return 0.0
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = await daily_totals(company_id, start, now)
    return round(sum(float(r.get("cost_usd", 0.0) or 0.0) for r in rows), 6)


async def today_totals(company_id: Optional[str] = None) -> Dict[str, Any]:
    """Today's (UTC) usage summary from the ledger — the accurate, all-channel
    replacement for the retired in-memory ``cost_monitor.get_daily_stats()``.
    ``company_id=None`` is platform-wide. Shape is compatible with the old
    dashboard consumers (``total_cost_usd`` / ``total_tokens`` / ``budget``)."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await daily_totals(company_id, start, now)
    row = rows[-1] if rows else {}
    prompt = int(row.get("prompt_tokens", 0) or 0)
    completion = int(row.get("completion_tokens", 0) or 0)
    cached = int(row.get("cached_tokens", 0) or 0)
    cost = round(float(row.get("cost_usd", 0.0) or 0.0), 4)
    cfg = budget_config()
    daily_budget = cfg["daily_budget"] or 1.0
    return {
        "date": now.strftime("%Y-%m-%d"),
        "total_cost_usd": cost,
        "total_tokens": prompt + completion,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_tokens": cached,
        "calls": int(row.get("calls", 0) or 0),
        "budget": {
            "daily_limit": cfg["daily_budget"],
            "remaining": round(cfg["daily_budget"] - cost, 2),
            "used_percentage": round(cost / daily_budget * 100, 1),
        },
    }
