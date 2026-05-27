"""Notification dispatch + per-scenario settings store.

``notify(scenario_key, company_id=, context=)`` is the single entry point
every emit site calls. It:
  1. loads the scenario's merged setting (stored override → registry default),
  2. skips if disabled or still within the cooldown window,
  3. resolves recipient roles → concrete email addresses,
  4. renders the subject/body templates against the (enriched) context,
  5. sends one email per recipient via the existing email service, and
  6. writes a ``notification_log`` row (sent / skipped / failed) either way.

It never raises into the caller — a notification failure must not break the
business operation that triggered it.

Settings are platform-level (one ``notification_settings`` row per scenario
key). Channel handling is email-only today but structured so other channels
slot in at ``_send_one``.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database
from services import email_service
from services.notification_registry import (
    SCENARIOS, get_scenario, scenario_defaults,
)

logger = logging.getLogger("notifications")

_PLATFORM_NAME = os.environ.get("SITE_NAME") or os.environ.get("REACT_APP_SITE_NAME") or "Seva Setu"
_LOGIN_URL = (os.environ.get("FRONTEND_URL") or "http://localhost:3000").rstrip("/") + "/login"

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


# ── settings store ────────────────────────────────────────────────────────

async def get_setting(scenario_key: str) -> Dict[str, Any]:
    """Merged setting: stored override on top of the registry default."""
    scenario = get_scenario(scenario_key)
    if not scenario:
        return {}
    defaults = scenario_defaults(scenario)
    db = await get_database()
    stored = await db.notification_settings.find_one({"scenario_key": scenario_key}, {"_id": 0}) or {}
    merged = {**defaults, **{k: v for k, v in stored.items() if k in defaults}}
    # params is a dict — merge field-wise so a new registry param shows up.
    merged["params"] = {**defaults.get("params", {}), **(stored.get("params") or {})}
    return merged


async def list_settings() -> Dict[str, Dict[str, Any]]:
    """All scenarios merged with their stored overrides, keyed by scenario_key."""
    db = await get_database()
    stored = {r["scenario_key"]: r async for r in db.notification_settings.find({}, {"_id": 0})}
    out: Dict[str, Dict[str, Any]] = {}
    for s in SCENARIOS:
        defaults = scenario_defaults(s)
        ov = stored.get(s.key, {})
        merged = {**defaults, **{k: v for k, v in ov.items() if k in defaults}}
        merged["params"] = {**defaults.get("params", {}), **(ov.get("params") or {})}
        out[s.key] = merged
    return out


async def update_setting(scenario_key: str, fields: Dict[str, Any], updated_by: Optional[str] = None) -> Dict[str, Any]:
    """Persist an override for one scenario. Only known keys are written."""
    if not get_scenario(scenario_key):
        raise ValueError(f"Unknown scenario: {scenario_key}")
    allowed = {"enabled", "channels", "recipients", "custom_emails", "subject", "body", "params", "cooldown_minutes"}
    to_set = {k: v for k, v in fields.items() if k in allowed}
    to_set["updated_at"] = _now_iso()
    if updated_by:
        to_set["updated_by"] = updated_by
    db = await get_database()
    await db.notification_settings.update_one(
        {"scenario_key": scenario_key},
        {"$set": to_set, "$setOnInsert": {"scenario_key": scenario_key, "created_at": _now_iso()}},
        upsert=True,
    )
    return await get_setting(scenario_key)


# ── recipient resolution ────────────────────────────────────────────────────

async def _resolve_recipients(setting: Dict[str, Any], company_id: Optional[str], context: Dict[str, Any]) -> List[str]:
    db = await get_database()
    roles = setting.get("recipients") or []
    emails: List[str] = []

    if "super_admin" in roles:
        async for u in db.super_admins.find({}, {"_id": 0, "email": 1}):
            if u.get("email"):
                emails.append(u["email"])
    if "tenant_admin" in roles and company_id:
        async for u in db.local_admins.find({"company_id": company_id}, {"_id": 0, "email": 1}):
            if u.get("email"):
                emails.append(u["email"])
    if "applicant" in roles:
        # The end user — context must supply it (we never guess).
        addr = context.get("applicant_email") or context.get("email")
        if addr:
            emails.append(addr)
    if "custom" in roles:
        emails.extend(setting.get("custom_emails") or [])

    # De-dup, drop blanks, keep order.
    seen, out = set(), []
    for e in emails:
        e = (e or "").strip()
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


# ── template rendering ──────────────────────────────────────────────────────

def _render(template: str, ctx: Dict[str, Any]) -> str:
    def repl(m):
        val = ctx.get(m.group(1))
        return "" if val is None else str(val)
    return _VAR_RE.sub(repl, template or "")


def _to_html(text: str) -> str:
    # Plain-text templates → minimal HTML. Escape nothing fancy; our copy is
    # operator-authored, not user input.
    return "<div style=\"font-family:system-ui,sans-serif;font-size:14px;line-height:1.5\">" + \
        text.replace("\n", "<br>") + "</div>"


async def _enrich(context: Dict[str, Any], company_id: Optional[str]) -> Dict[str, Any]:
    ctx = dict(context or {})
    ctx.setdefault("platform_name", _PLATFORM_NAME)
    ctx.setdefault("login_url", _LOGIN_URL)
    ctx.setdefault("when", _now().strftime("%Y-%m-%d %H:%M UTC"))
    if company_id and not ctx.get("tenant_name"):
        try:
            db = await get_database()
            c = await db.companies.find_one({"id": company_id}, {"_id": 0, "name": 1})
            if c:
                ctx["tenant_name"] = c.get("name", "")
                ctx.setdefault("org_name", c.get("name", ""))
        except Exception:
            pass
    ctx.setdefault("org_name", ctx.get("tenant_name", _PLATFORM_NAME))
    return ctx


# ── logging ─────────────────────────────────────────────────────────────────

async def _log(scenario_key: str, company_id: Optional[str], status: str, *,
               recipients: List[str], subject: str, reason: str = "", severity: str = "info") -> None:
    db = await get_database()
    await db.notification_log.insert_one({
        "id":           str(uuid.uuid4()),
        "scenario_key": scenario_key,
        "company_id":   company_id,
        "status":       status,                 # sent | failed | skipped
        "reason":       reason,
        "severity":     severity,
        "channel":      "email",
        "recipients":   recipients,
        "subject":      subject,
        "created_at":   _now_iso(),
    })


async def _recent_send_within_cooldown(scenario_key: str, company_id: Optional[str], minutes: int) -> bool:
    if minutes <= 0:
        return False
    db = await get_database()
    last = await db.notification_log.find_one(
        {"scenario_key": scenario_key, "company_id": company_id, "status": "sent"},
        sort=[("created_at", -1)],
    )
    if not last:
        return False
    try:
        prev = datetime.fromisoformat(last["created_at"])
        return (_now() - prev).total_seconds() < minutes * 60
    except Exception:
        return False


# ── send ──────────────────────────────────────────────────────────────────

async def _send_one(to: str, subject: str, html: str) -> bool:
    loop = asyncio.get_event_loop()
    # email_service._send is blocking SMTP; run off-loop. In dev mode (no SMTP
    # configured) it logs the email to the console and returns False — that
    # console sink IS the delivery channel in dev, so we count it as sent.
    ok = await loop.run_in_executor(None, lambda: email_service._send(to, subject, html))
    if not ok and getattr(email_service, "_DEV_MODE", False):
        return True
    return ok


async def notify(
    scenario_key: str,
    *,
    company_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    force: bool = False,
    recipients_override: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Emit a notification for ``scenario_key``. Never raises.

    ``force=True`` bypasses the enabled + cooldown gates (used by "send test").
    ``recipients_override`` sends to exactly those addresses instead of the
    configured roles (used by "send test to me").
    Returns a small result dict for callers/tests that care.
    """
    scenario = get_scenario(scenario_key)
    if not scenario:
        logger.warning("notify() for unknown scenario %r", scenario_key)
        return {"status": "skipped", "reason": "unknown_scenario"}

    context = context or {}
    try:
        setting = await get_setting(scenario_key)

        if not force and not setting.get("enabled", False):
            await _log(scenario_key, company_id, "skipped", recipients=[], subject="", reason="disabled", severity=scenario.severity)
            return {"status": "skipped", "reason": "disabled"}

        if not force and await _recent_send_within_cooldown(scenario_key, company_id, int(setting.get("cooldown_minutes", 0) or 0)):
            await _log(scenario_key, company_id, "skipped", recipients=[], subject="", reason="cooldown", severity=scenario.severity)
            return {"status": "skipped", "reason": "cooldown"}

        ctx = await _enrich(context, company_id)
        recipients = recipients_override if recipients_override else await _resolve_recipients(setting, company_id, ctx)
        subject = _render(setting.get("subject", ""), ctx)

        if not recipients:
            await _log(scenario_key, company_id, "skipped", recipients=[], subject=subject, reason="no_recipients", severity=scenario.severity)
            return {"status": "skipped", "reason": "no_recipients"}

        html = _to_html(_render(setting.get("body", ""), ctx))
        ok_any = False
        for addr in recipients:
            try:
                ok = await _send_one(addr, subject, html)
                ok_any = ok_any or ok
            except Exception:
                logger.exception("notify send failed scenario=%s to=%s", scenario_key, addr)

        status = "sent" if ok_any else "failed"
        await _log(scenario_key, company_id, status, recipients=recipients, subject=subject,
                   reason="" if ok_any else "send_failed", severity=scenario.severity)
        return {"status": status, "recipients": recipients, "subject": subject}
    except Exception as exc:
        logger.exception("notify() error scenario=%s: %s", scenario_key, exc)
        try:
            await _log(scenario_key, company_id, "failed", recipients=[], subject="", reason=f"error:{exc}", severity=scenario.severity)
        except Exception:
            pass
        return {"status": "failed", "reason": str(exc)}


def notify_bg(scenario_key: str, *, company_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> None:
    """Fire-and-forget from an async context — schedules notify() without
    awaiting, so the caller's hot path isn't slowed by SMTP."""
    try:
        asyncio.get_event_loop().create_task(
            notify(scenario_key, company_id=company_id, context=context)
        )
    except RuntimeError:
        # No running loop (sync context) — best effort, skip.
        logger.debug("notify_bg called without a running loop for %s", scenario_key)
