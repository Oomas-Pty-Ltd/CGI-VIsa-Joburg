"""Periodic notification jobs.

Some scenarios aren't tied to a single request — they're computed by scanning
state on a schedule: LLM budget checks, stuck-application sweeps, and digests.
These functions do that computation and emit via the dispatcher. They're
written to be driven by a cron / scheduler (or the manual
``POST /notifications/run-job/{job}`` endpoint); running them per-request would
be far too expensive.

Each function is safe to call repeatedly — the dispatcher's per-scenario
cooldown prevents duplicate alerts (e.g. the budget warning won't re-fire for
12h once sent).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from database import get_database
from services import llm_usage
from services.notification_dispatcher import notify, get_setting

logger = logging.getLogger("notification_jobs")


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _mtd_spend(company_id: str, now: datetime) -> float:
    rows = await llm_usage.daily_totals(company_id, _month_start(now), now)
    return round(sum(float(r.get("cost_usd", 0) or 0) for r in rows), 4)


async def run_usage_checks() -> Dict[str, Any]:
    """For each tenant with a monthly budget, compare month-to-date spend and
    emit budget-exceeded or usage-threshold as appropriate."""
    db = await get_database()
    now = datetime.now(timezone.utc)
    setting = await get_setting("llm.usage_threshold")
    threshold_pct = float((setting.get("params") or {}).get("threshold_pct", 80))

    fired = {"threshold": 0, "exceeded": 0, "checked": 0}
    async for c in db.companies.find({"llm_monthly_budget_usd": {"$gt": 0}}, {"_id": 0, "id": 1, "name": 1, "llm_monthly_budget_usd": 1}):
        budget = float(c["llm_monthly_budget_usd"])
        spend = await _mtd_spend(c["id"], now)
        fired["checked"] += 1
        ctx = {"tenant_name": c.get("name", ""), "used": f"${spend:.2f}", "budget": f"${budget:.2f}",
               "pct": round(spend / budget * 100) if budget else 0}
        if spend >= budget:
            await notify("llm.budget_exceeded", company_id=c["id"], context=ctx)
            fired["exceeded"] += 1
        elif budget and (spend / budget * 100) >= threshold_pct:
            await notify("llm.usage_threshold", company_id=c["id"], context=ctx)
            fired["threshold"] += 1
    return fired


async def run_stuck_pending_check() -> Dict[str, Any]:
    """Per tenant, count applications stuck in submission_pending beyond the
    configured age and alert."""
    db = await get_database()
    setting = await get_setting("application.stuck_pending")
    hours = int((setting.get("params") or {}).get("hours", 24))
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    # Group pending-and-old applications by tenant.
    pipeline = [
        {"$match": {"status": "submission_pending", "updated_at": {"$lt": cutoff}}},
        {"$group": {"_id": "$company_id", "count": {"$sum": 1}}},
    ]
    fired = 0
    async for row in db.seva_setu_applications.aggregate(pipeline):
        cid = row["_id"]
        if not cid:
            continue
        await notify("application.stuck_pending", company_id=cid, context={"count": row["count"], "hours": hours})
        fired += 1
    return {"tenants_alerted": fired, "older_than_hours": hours}


async def run_usage_digest(period: str = "week") -> Dict[str, Any]:
    """Platform LLM spend digest for the period."""
    db = await get_database()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7 if period == "week" else 1)
    rows = await llm_usage.daily_totals(None, start, now)
    total = round(sum(float(r.get("cost_usd", 0) or 0) for r in rows), 2)
    # Top tenant by spend.
    per = {}
    async for c in db.companies.find({}, {"_id": 0, "id": 1, "name": 1}):
        s = await _mtd_spend(c["id"], now)
        if s > 0:
            per[c.get("name", c["id"])] = s
    top = max(per.items(), key=lambda kv: kv[1]) if per else ("—", 0)
    await notify("llm.usage_digest", context={
        "period": period, "total": f"${total:.2f}", "tenants": len(per), "top": f"{top[0]} (${top[1]:.2f})",
    })
    return {"total": total, "tenants": len(per)}


async def run_activity_digest(period: str = "week") -> Dict[str, Any]:
    """Platform activity digest for the period."""
    db = await get_database()
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=7 if period == "week" else 1)).isoformat()
    conversations = await db.chat_sessions.count_documents({"created_at": {"$gte": start}}) if "chat_sessions" in await db.list_collection_names() else 0
    applications = await db.seva_setu_applications.count_documents({"created_at": {"$gte": start}})
    crawls = await db.crawler_runs.count_documents({"started_at": {"$gte": start}})
    await notify("digest.activity", context={
        "period": period, "conversations": conversations, "applications": applications, "crawls": crawls,
    })
    return {"conversations": conversations, "applications": applications, "crawls": crawls}


JOBS = {
    "usage_checks":   run_usage_checks,
    "stuck_pending":  run_stuck_pending_check,
    "usage_digest":   run_usage_digest,
    "activity_digest": run_activity_digest,
}
