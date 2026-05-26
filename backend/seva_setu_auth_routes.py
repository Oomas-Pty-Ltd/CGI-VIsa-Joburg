"""
Seva Setu — Auth + Application Routes
======================================
Endpoints:
  POST /seva-setu/auth/start          – collect name+email, create/find user, send OTP
  POST /seva-setu/auth/verify-otp     – verify OTP, return session token
  POST /seva-setu/auth/logout         – destroy session

  POST /seva-setu/applications        – create new application (after OTP)
  GET  /seva-setu/applications        – list user applications
  GET  /seva-setu/applications/{id}   – get single application
  PUT  /seva-setu/applications/{id}   – update form_data / documents
  POST /seva-setu/applications/{id}/submit   – submit for review (sends review email)
  POST /seva-setu/applications/{id}/confirm  – confirm → lock, generate PDF, send conf email
  GET  /seva-setu/applications/{id}/pdf      – download PDF

  POST /seva-setu/upload-document     – upload + OCR a single document (returns extracted fields)

  GET  /seva-setu/review/{token}      – get application by edit token (review page)
  PUT  /seva-setu/review/{token}      – edit fields via review page
  POST /seva-setu/review/{token}/confirm – confirm from review page
"""

import logging
import os
import uuid
import base64
import re
import io
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Header, Depends, Query
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel, EmailStr, field_validator

from database import get_database
from services.email_service import (
    send_otp_email,
    send_account_created_email,
    send_review_email,
    send_confirmation_email,
)
from services.pdf_service import generate_application_pdf
from services.bot_config import get_bot_config
from tenant import get_tenant_id


async def _brand_for(company_id: str) -> tuple[str, str]:
    """Return ``(bot_name, org_name)`` for the tenant — both strings, possibly
    empty. Used to brand outbound emails without hardcoding any product name."""
    cfg = await get_bot_config(company_id)
    return (cfg.bot_name or "", cfg.org_name or "")


async def _pdf_branding_for(company_id: str) -> dict:
    """Return the tenant's pdf_branding dict. Falls back to ``{}`` so the
    pdf_service applies neutral defaults."""
    cfg = await get_bot_config(company_id)
    return dict(cfg.pdf_branding or {})


def _field_labels_for(svc: dict) -> dict:
    """Build a {field_key: display_label} dict from a tenant service's
    fields list. Used to pass per-tenant field labels into pdf_service."""
    out: dict = {}
    for f in (svc.get("fields") or []):
        if isinstance(f, dict) and f.get("key") and f.get("display_label"):
            out[f["key"]] = f["display_label"]
    return out

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/seva-setu", tags=["seva-setu"])

# ── Platform defaults ────────────────────────────────────────────────────────
# These are the platform-level fallbacks used when a tenant hasn't overridden
# the value on ``bot_config.security_config``. Read through ``_security_for()``
# at every call site so per-tenant overrides actually apply.

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "seva_setu")
os.makedirs(UPLOAD_DIR, exist_ok=True)


async def _security_for(company_id: str) -> dict:
    """Return resolved ``security_config`` for the tenant (with platform
    defaults filled in where the tenant left a value blank)."""
    cfg = await get_bot_config(company_id)
    return cfg.security()

# ── Helpers ──────────────────────────────────────────────────────────────────

_FORM_KEYWORDS = ("application form", "completed form", "completed application", "application form (available")

def _filter_required_docs(docs: list, form_data: dict) -> list:
    """Remove 'bring the application form' entries when user already filled it manually."""
    if len(form_data) <= 2:
        return docs
    return [d for d in docs if not any(kw in d.lower() for kw in _FORM_KEYWORDS)]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ref_id(prefix: str = "APP") -> str:
    year = _now().year
    suffix = uuid.uuid4().hex[:6].upper()
    safe_prefix = re.sub(r"[^A-Z0-9]+", "", (prefix or "APP").upper())[:8] or "APP"
    return f"{safe_prefix}-{year}-{suffix}"


def _verify_session(token: str, db_session: dict, ttl_minutes: int) -> bool:
    if not db_session or not db_session.get("active"):
        return False
    last_active = db_session.get("last_active")
    if isinstance(last_active, str):
        last_active = datetime.fromisoformat(last_active)
    if last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)
    return (_now() - last_active) < timedelta(minutes=ttl_minutes)


async def _get_session(authorization: str, db) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid session token")
    token = authorization[7:]
    session = await db.seva_setu_sessions.find_one({"session_id": token})
    # Look up the tenant's session TTL — defaults applied for legacy sessions
    # with no company_id yet.
    _co_id_for_ttl = (session or {}).get("company_id") or ""
    _sec = await _security_for(_co_id_for_ttl) if _co_id_for_ttl else {"session_inactivity_minutes": 10}
    _ttl = _sec["session_inactivity_minutes"]
    if not session or not _verify_session(token, session, _ttl):
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    await db.seva_setu_sessions.update_one(
        {"session_id": token},
        {"$set": {"last_active": _now().isoformat()}}
    )
    # Ensure company_id is on the session dict. New sessions write it at
    # creation time; legacy sessions fall back to their user row.
    if not session.get("company_id"):
        user = await db.seva_setu_users.find_one(
            {"id": session.get("user_id")},
            {"_id": 0, "company_id": 1},
        )
        if user and user.get("company_id"):
            session["company_id"] = user["company_id"]
            # Backfill so subsequent reads don't pay the join.
            await db.seva_setu_sessions.update_one(
                {"session_id": token},
                {"$set": {"company_id": user["company_id"]}},
            )
    return session


# ── Pydantic models ───────────────────────────────────────────────────────────

class StartAuthRequest(BaseModel):
    name: str
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Invalid email format")
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v


class VerifyOtpRequest(BaseModel):
    email: str
    otp: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.strip().lower()


class CreateApplicationRequest(BaseModel):
    service_type: str
    visa_subtype: Optional[str] = None  # tourist/business/medical/student for visa


class UpdateApplicationRequest(BaseModel):
    form_data: Optional[Dict[str, Any]] = None
    documents: Optional[List[Dict[str, Any]]] = None


class ReviewEditRequest(BaseModel):
    form_data: Dict[str, Any]


class LogoutRequest(BaseModel):
    chat_history: Optional[List[Dict[str, str]]] = None


# ── Auth endpoints ────────────────────────────────────────────────────────────

# ── Tenant service lookup ────────────────────────────────────────────────────
#
# `tenant_services` is the source of truth. SERVICE_CATALOGUE (the hardcoded
# Python dict above) was the original CGI-only catalogue; it stays in the file
# as historical seed data but the live code never reads from it any more.
#
# _load_tenant_services() returns the catalogue as `{service_key: {...}}` so
# call sites that used to index `SERVICE_CATALOGUE[key]` can swap to
# `services[key]` with no shape change. We map `external_url` → `gov_url`
# because that's what the existing call sites read; both names point at the
# same thing.

async def _load_tenant_services(db, company_id: str) -> Dict[str, Dict[str, Any]]:
    """Return this tenant's enabled service rows keyed by service_key."""
    rows = await db.tenant_services.find(
        {"company_id": company_id, "enabled": True},
        {"_id": 0},
    ).sort("display_order", 1).to_list(200)
    return {
        r["service_key"]: {
            "name":      r.get("name", ""),
            "category":  r.get("category", "TYPE_A"),
            "documents": list(r.get("documents") or []),
            "fields":    list(r.get("fields") or []),
            "gov_url":   r.get("external_url"),
        }
        for r in rows
        if r.get("service_key")
    }


@router.get("/services")
async def get_services(company_id: str = Depends(get_tenant_id)):
    """Return this tenant's service catalogue. Tenant comes from
    X-Company-Id (the widget's data-company-id attribute)."""
    db = await get_database()
    return await _load_tenant_services(db, company_id)


@router.post("/auth/start")
async def start_auth(
    req: StartAuthRequest,
    company_id: str = Depends(get_tenant_id),
):
    """
    Step 1: collect name + email, create/find user, send OTP.
    Returns whether this is a new or existing user.

    The tenant comes from X-Company-Id (the widget's data-company-id attribute).
    A user with the same email can exist independently in different tenants.
    """
    db = await get_database()
    email = req.email
    name = req.name

    # Check lockout (tenant-scoped — one tenant's lockout doesn't affect another)
    lockout = await db.otp_tokens.find_one({
        "company_id": company_id,
        "email": email,
        "locked_until": {"$exists": True, "$gt": _now().isoformat()}
    })
    if lockout:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again in 5 minutes.")

    # Check existing user within this tenant
    user = await db.seva_setu_users.find_one({"company_id": company_id, "email": email})
    is_new = user is None

    if is_new:
        user_id = str(uuid.uuid4())
        await db.seva_setu_users.insert_one({
            "id": user_id,
            "company_id": company_id,
            "name": name,
            "email": email,
            "created_at": _now().isoformat(),
        })
    else:
        user_id = user["id"]
        # Update name in case it changed (scoped — no cross-tenant write)
        await db.seva_setu_users.update_one(
            {"company_id": company_id, "email": email},
            {"$set": {"name": name}},
        )

    # Invalidate any previous unused OTPs for this email (tenant-scoped)
    await db.otp_tokens.delete_many({"company_id": company_id, "email": email, "used": False})

    # Per-tenant security config (TTL + dev OTP value)
    _sec = await _security_for(company_id)
    _otp_value  = _sec["otp_dev_value"]
    _otp_ttl    = _sec["otp_ttl_minutes"]

    # Create OTP record
    otp_id = str(uuid.uuid4())
    expires_at = (_now() + timedelta(minutes=_otp_ttl)).isoformat()
    await db.otp_tokens.insert_one({
        "id": otp_id,
        "company_id": company_id,
        "email": email,
        "otp": _otp_value,  # replace with random in prod — use security_config.otp_dev_value for testing
        "expires_at": expires_at,
        "used": False,
        "attempts": 0,
    })

    # Send OTP — if email is not configured the fallback dev OTP applies.
    _bot_name, _org_name = await _brand_for(company_id)
    email_sent = send_otp_email(email, _otp_value, bot_name=_bot_name, org_name=_org_name)
    if email_sent:
        msg = f"OTP sent to {email}. Please enter it to continue."
    else:
        logger.warning(f"[AUTH] OTP email failed for {email}. Using dev OTP: {_otp_value}")
        msg = f"Email delivery unavailable — use OTP: {_otp_value} to continue."

    return {
        "success": True,
        "is_new_user": is_new,
        "message": msg,
        "email_sent": email_sent,
    }


@router.post("/auth/verify-otp")
async def verify_otp(
    req: VerifyOtpRequest,
    company_id: str = Depends(get_tenant_id),
):
    """
    Step 2: verify OTP → create session, return session_token + user info.

    OTP + user lookup are scoped to the tenant from X-Company-Id, so an OTP
    issued for tenant A can't be exchanged for a session under tenant B.
    """
    db = await get_database()
    email = req.email.strip().lower()
    otp_input = req.otp.strip()

    token_doc = await db.otp_tokens.find_one({"company_id": company_id, "email": email, "used": False})
    if not token_doc:
        raise HTTPException(status_code=400, detail="No active OTP found. Please request a new one.")

    # Check expiry
    expires_at = token_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if _now() > expires_at:
        await db.otp_tokens.delete_one({"id": token_doc["id"]})
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new one.")

    attempts = token_doc.get("attempts", 0)

    # Per-tenant security config (max attempts + lockout)
    _sec = await _security_for(company_id)
    _max_attempts    = _sec["otp_max_attempts"]
    _lockout_minutes = _sec["otp_lockout_minutes"]

    if token_doc["otp"] != otp_input:
        new_attempts = attempts + 1
        if new_attempts >= _max_attempts:
            locked_until = (_now() + timedelta(minutes=_lockout_minutes)).isoformat()
            await db.otp_tokens.update_one(
                {"id": token_doc["id"]},
                {"$set": {"attempts": new_attempts, "locked_until": locked_until}}
            )
            raise HTTPException(status_code=429, detail=f"Too many failed attempts. Account locked for {_lockout_minutes} minutes.")
        await db.otp_tokens.update_one({"id": token_doc["id"]}, {"$set": {"attempts": new_attempts}})
        remaining = _max_attempts - new_attempts
        raise HTTPException(status_code=400, detail=f"Invalid OTP. {remaining} attempt(s) remaining.")

    # Mark OTP used
    await db.otp_tokens.update_one({"id": token_doc["id"]}, {"$set": {"used": True}})

    # Fetch user within this tenant
    user = await db.seva_setu_users.find_one({"company_id": company_id, "email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Create session — store company_id so downstream queries don't need a join
    session_token = str(uuid.uuid4())
    await db.seva_setu_sessions.insert_one({
        "session_id": session_token,
        "user_id": user["id"],
        "company_id": company_id,
        "email": email,
        "active": True,
        "last_active": _now().isoformat(),
        "created_at": _now().isoformat(),
    })

    # Get existing applications (tenant-scoped)
    existing_apps = await db.seva_setu_applications.find(
        {"company_id": company_id, "user_id": user["id"]}
    ).sort("created_at", -1).to_list(length=20)

    return {
        "success": True,
        "session_token": session_token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
        },
        "has_existing_applications": len(existing_apps) > 0,
        "existing_applications_count": len(existing_apps),
    }


@router.post("/auth/logout")
async def logout(req: Optional[LogoutRequest] = None, authorization: str = Header(default="")):
    db = await get_database()
    if not authorization.startswith("Bearer "):
        return {"success": True}
    token = authorization[7:]

    session = await db.seva_setu_sessions.find_one({"session_id": token})

    # Save chat history if provided
    if req and req.chat_history and session:
        await db.seva_setu_chat_history.insert_one({
            "user_id": session.get("user_id"),
            "company_id": session.get("company_id"),
            "email": session.get("email"),
            "session_id": token,
            "messages": req.chat_history,
            "saved_at": _now().isoformat(),
        })

    await db.seva_setu_sessions.update_one(
        {"session_id": token},
        {"$set": {"active": False, "ended_at": _now().isoformat()}}
    )
    return {"success": True}


# ── Application endpoints ─────────────────────────────────────────────────────

@router.post("/applications")
async def create_application(req: CreateApplicationRequest, authorization: str = Header(default="")):
    db = await get_database()
    session = await _get_session(authorization, db)

    service_type = req.service_type.lower()
    tenant_services = await _load_tenant_services(db, session["company_id"])
    if service_type not in tenant_services:
        raise HTTPException(status_code=400, detail=f"Unknown service: {service_type}")

    svc = tenant_services[service_type]
    user = await db.seva_setu_users.find_one({"id": session["user_id"], "company_id": session["company_id"]})
    _cfg = await get_bot_config(session["company_id"])
    reference_id = _ref_id(_cfg.org_short_name or _cfg.org_name or _cfg.bot_name)

    app_id = str(uuid.uuid4())
    edit_token = str(uuid.uuid4())
    edit_token_expires = (_now() + timedelta(hours=24)).isoformat()

    app_doc = {
        "id": app_id,
        "reference_id": reference_id,
        "user_id": session["user_id"],
        "company_id": session["company_id"],
        "service_type": service_type,
        "service_category": svc["category"],
        "service_name": svc["name"],
        "visa_subtype": req.visa_subtype,
        "status": "created",
        "form_data": {
            "full_name": user.get("name", ""),
            "email": user.get("email", ""),
        },
        "documents": [],
        "pdf_path": None,
        "edit_token": edit_token,
        "edit_token_expires_at": edit_token_expires,
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }
    await db.seva_setu_applications.insert_one(app_doc)

    # Send account creation email
    _bot_name, _org_name = await _brand_for(session["company_id"])
    send_account_created_email(user["email"], user["name"], reference_id, svc["name"], bot_name=_bot_name, org_name=_org_name)

    return {
        "success": True,
        "application_id": app_id,
        "reference_id": reference_id,
        "service_type": service_type,
        "service_category": svc["category"],
        "service_name": svc["name"],
        "fields": svc.get("fields", []),
        "documents_required": svc.get("documents", []),
        "gov_url": svc.get("gov_url"),
        "form_data": app_doc["form_data"],
    }


@router.get("/applications")
async def list_applications(authorization: str = Header(default="")):
    db = await get_database()
    session = await _get_session(authorization, db)

    apps = await db.seva_setu_applications.find(
        {"company_id": session["company_id"], "user_id": session["user_id"]}
    ).sort("created_at", -1).to_list(length=50)

    return {
        "applications": [
            {
                "id": a["id"],
                "reference_id": a["reference_id"],
                "service_type": a["service_type"],
                "service_name": a.get("service_name", a["service_type"]),
                "service_category": a["service_category"],
                "status": a["status"],
                "created_at": a["created_at"],
                "has_pdf": bool(a.get("pdf_path")),
            }
            for a in apps
        ]
    }


@router.get("/applications/{app_id}")
async def get_application(app_id: str, authorization: str = Header(default="")):
    db = await get_database()
    session = await _get_session(authorization, db)

    app = await db.seva_setu_applications.find_one({"id": app_id, "user_id": session["user_id"], "company_id": session["company_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    svc = (await _load_tenant_services(db, app["company_id"])).get(app["service_type"], {})
    return {
        "id": app["id"],
        "reference_id": app["reference_id"],
        "service_type": app["service_type"],
        "service_name": app.get("service_name"),
        "service_category": app["service_category"],
        "status": app["status"],
        "form_data": app.get("form_data", {}),
        "documents": app.get("documents", []),
        "fields": svc.get("fields", []),
        "documents_required": svc.get("documents", []),
        "has_pdf": bool(app.get("pdf_path")),
        "created_at": app["created_at"],
        "updated_at": app.get("updated_at"),
    }


@router.put("/applications/{app_id}")
async def update_application(app_id: str, req: UpdateApplicationRequest, authorization: str = Header(default="")):
    db = await get_database()
    session = await _get_session(authorization, db)

    app = await db.seva_setu_applications.find_one({"id": app_id, "user_id": session["user_id"], "company_id": session["company_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if app["status"] in ("confirmed", "cancelled"):
        raise HTTPException(status_code=400, detail="Application is locked and cannot be edited.")

    updates: Dict[str, Any] = {"updated_at": _now().isoformat()}
    if req.form_data is not None:
        merged = {**app.get("form_data", {}), **req.form_data}
        updates["form_data"] = merged
    if req.documents is not None:
        updates["documents"] = req.documents

    await db.seva_setu_applications.update_one(
        {"id": app_id, "company_id": session["company_id"]},
        {"$set": updates},
    )
    updated = await db.seva_setu_applications.find_one(
        {"id": app_id, "company_id": session["company_id"]}
    )
    return {"success": True, "form_data": updated.get("form_data", {}), "documents": updated.get("documents", [])}


@router.delete("/applications/{app_id}/documents/{doc_id}")
async def remove_document(app_id: str, doc_id: str, authorization: str = Header(default="")):
    db = await get_database()
    session = await _get_session(authorization, db)

    app = await db.seva_setu_applications.find_one({"id": app_id, "user_id": session["user_id"], "company_id": session["company_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if app["status"] in ("confirmed", "cancelled"):
        raise HTTPException(status_code=400, detail="Application is locked and cannot be edited.")

    doc = next((d for d in app.get("documents", []) if d["id"] == doc_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Delete file from disk silently
    try:
        if doc.get("path") and os.path.exists(doc["path"]):
            os.remove(doc["path"])
    except Exception:
        pass

    await db.seva_setu_applications.update_one(
        {"id": app_id, "company_id": session["company_id"]},
        {"$pull": {"documents": {"id": doc_id}}, "$set": {"updated_at": _now().isoformat()}}
    )
    return {"success": True, "message": f"Document '{doc.get('name', '')}' removed."}


@router.post("/applications/{app_id}/submit")
async def submit_application(app_id: str, authorization: str = Header(default="")):
    """
    Submit for review — sends review email with 24h edit link, sets status = submitted.
    """
    db = await get_database()
    session = await _get_session(authorization, db)

    app = await db.seva_setu_applications.find_one({"id": app_id, "user_id": session["user_id"], "company_id": session["company_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if app["status"] in ("confirmed", "cancelled"):
        raise HTTPException(status_code=400, detail="Application already finalised.")

    user = await db.seva_setu_users.find_one({"id": session["user_id"], "company_id": session["company_id"]})

    # Refresh edit token (reset 24h window from now)
    edit_token = str(uuid.uuid4())
    edit_token_expires = (_now() + timedelta(hours=24)).isoformat()

    await db.seva_setu_applications.update_one(
        {"id": app_id, "company_id": session["company_id"]},
        {"$set": {
            "status": "submitted",
            "edit_token": edit_token,
            "edit_token_expires_at": edit_token_expires,
            "updated_at": _now().isoformat(),
        }}
    )

    _bot_name, _org_name = await _brand_for(session["company_id"])
    send_review_email(
        user["email"],
        user["name"],
        app["reference_id"],
        edit_token,
        app.get("form_data", {}),
        bot_name=_bot_name,
        org_name=_org_name,
    )

    return {
        "success": True,
        "status": "submitted",
        "reference_id": app["reference_id"],
        "message": "Application submitted. A review email has been sent to your registered address.",
    }


@router.post("/applications/{app_id}/confirm")
async def confirm_application(app_id: str, authorization: str = Header(default="")):
    """
    Confirm application — generates PDF, sends confirmation email, locks application.
    """
    db = await get_database()
    session = await _get_session(authorization, db)

    app = await db.seva_setu_applications.find_one({"id": app_id, "user_id": session["user_id"], "company_id": session["company_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if app["status"] == "confirmed":
        raise HTTPException(status_code=400, detail="Application already confirmed.")

    user = await db.seva_setu_users.find_one({"id": session["user_id"], "company_id": session["company_id"]})
    svc = (await _load_tenant_services(db, app["company_id"])).get(app["service_type"], {})
    form_data = app.get("form_data", {})

    _bot_name, _org_name = await _brand_for(session["company_id"])

    # Generate PDF
    pdf_bytes = generate_application_pdf(
        service_name=app.get("service_name", svc.get("name", app["service_type"])),
        form_data=form_data,
        tracking_id=app["reference_id"],
        uploaded_docs=[
            {"name": d.get("name", "Document"), "status": "uploaded"}
            for d in app.get("documents", [])
        ],
        required_docs=_filter_required_docs(svc.get("documents", []), form_data),
        org_name=_org_name or _bot_name,
        branding=await _pdf_branding_for(app["company_id"]),
        field_labels=_field_labels_for(svc),
    )

    # Save PDF to disk
    pdf_filename = f"{app['reference_id']}.pdf"
    pdf_path = os.path.join(UPLOAD_DIR, pdf_filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    await db.seva_setu_applications.update_one(
        {"id": app_id, "company_id": session["company_id"]},
        {"$set": {
            "status": "confirmed",
            "pdf_path": pdf_path,
            "updated_at": _now().isoformat(),
        }}
    )

    send_confirmation_email(user["email"], user["name"], app["reference_id"], svc.get("name", app["service_type"]), pdf_bytes, bot_name=_bot_name, org_name=_org_name)

    return {
        "success": True,
        "status": "confirmed",
        "reference_id": app["reference_id"],
        "message": "Application confirmed! A confirmation email with your PDF has been sent.",
    }


@router.get("/applications/{app_id}/preview")
async def preview_application_pdf(
    app_id: str,
    authorization: str = Header(default=""),
    token: Optional[str] = Query(default=None),
):
    """Generate an inline PDF preview without confirming the application."""
    if token and not authorization:
        authorization = f"Bearer {token}"
    db = await get_database()
    session = await _get_session(authorization, db)

    app = await db.seva_setu_applications.find_one({"id": app_id, "user_id": session["user_id"], "company_id": session["company_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    svc = (await _load_tenant_services(db, app["company_id"])).get(app["service_type"], {})
    form_data = app.get("form_data", {})
    _bot_name, _org_name = await _brand_for(app["company_id"])
    pdf_bytes = generate_application_pdf(
        service_name=app.get("service_name", svc.get("name", app["service_type"])),
        form_data=form_data,
        tracking_id=app["reference_id"],
        uploaded_docs=[
            {"name": d.get("name", "Document"), "status": "uploaded"}
            for d in app.get("documents", [])
        ],
        required_docs=_filter_required_docs(svc.get("documents", []), form_data),
        org_name=_org_name or _bot_name,
        branding=await _pdf_branding_for(app["company_id"]),
        field_labels=_field_labels_for(svc),
    )
    filename = f"preview_{app['reference_id']}.pdf"
    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/applications/{app_id}/pdf")
async def download_pdf(app_id: str, authorization: str = Header(default=""), token: Optional[str] = None):
    db = await get_database()
    # Accept token as query param (for direct browser downloads) or Authorization header
    if token and not authorization:
        authorization = f"Bearer {token}"
    session = await _get_session(authorization, db)

    app = await db.seva_setu_applications.find_one({"id": app_id, "user_id": session["user_id"], "company_id": session["company_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if not app.get("pdf_path"):
        raise HTTPException(status_code=404, detail="PDF not yet generated. Please confirm your application first.")

    try:
        with open(app["pdf_path"], "rb") as f:
            pdf_bytes = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="PDF file not found on server.")

    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{app["reference_id"]}.pdf"'},
    )


# ── Document upload + OCR ─────────────────────────────────────────────────────

@router.post("/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    app_id: str = Form(...),
    doc_name: str = Form(...),
    authorization: str = Header(default=""),
):
    db = await get_database()
    session = await _get_session(authorization, db)

    # Validate file against per-tenant upload limits
    _sec = await _security_for(session["company_id"])
    _allowed_mime = set(_sec["upload_allowed_mime_types"])
    _max_bytes    = int(_sec["upload_max_bytes"])

    content_type = file.content_type or ""
    if content_type not in _allowed_mime:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type {content_type or '(unknown)'}. Allowed: {sorted(_allowed_mime)}",
        )

    raw = await file.read()
    if len(raw) > _max_bytes:
        _max_mb = _max_bytes / (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"File too large. Max size is {_max_mb:.1f} MB.")

    app = await db.seva_setu_applications.find_one({"id": app_id, "user_id": session["user_id"], "company_id": session["company_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    # Save file
    file_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    saved_name = f"{app_id}_{uuid.uuid4().hex[:8]}.{file_ext}"
    saved_path = os.path.join(UPLOAD_DIR, saved_name)
    with open(saved_path, "wb") as f:
        f.write(raw)

    # OCR extraction — tenant-scoped so each tenant can configure its own
    # passport / date / name patterns via bot_config.ocr_patterns.
    ocr_fields: Dict[str, str] = {}
    try:
        ocr_fields = await _run_ocr(raw, content_type, company_id=session.get("company_id"))
    except Exception as e:
        logger.warning(f"OCR failed for {saved_name}: {e}")

    # Append document record to application
    doc_record = {
        "id": str(uuid.uuid4()),
        "name": doc_name,
        "filename": saved_name,
        "path": saved_path,
        "content_type": content_type,
        "status": "uploaded",
        "uploaded_at": _now().isoformat(),
    }
    await db.seva_setu_applications.update_one(
        {"id": app_id},
        {
            "$push": {"documents": doc_record},
            "$set": {"updated_at": _now().isoformat()},
        }
    )

    return {
        "success": True,
        "document": doc_record,
        "ocr_fields": ocr_fields,
        "message": f"'{doc_name}' uploaded successfully." + (
            " Fields extracted via OCR — please review and correct if needed." if ocr_fields else ""
        ),
    }


async def _run_ocr(raw: bytes, content_type: str, company_id: Optional[str] = None) -> Dict[str, str]:
    """Extract key fields from uploaded document using pytesseract or fallback.

    ``company_id`` enables per-tenant OCR pattern overrides via
    ``bot_config.ocr_patterns`` (passport regex, name blocklist, etc.).
    """
    try:
        import pytesseract
        from PIL import Image

        if content_type == "application/pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(stream=raw, filetype="pdf")
                text = "\n".join(page.get_text() for page in doc)
            except Exception:
                return {}
        else:
            img = Image.open(io.BytesIO(raw))
            text = pytesseract.image_to_string(img)

        return await _parse_ocr_text(text, company_id)
    except ImportError:
        logger.debug("pytesseract not installed — OCR skipped")
        return {}


# Platform-default OCR heuristics. The passport regex is intentionally
# permissive (1-2 letters + 6-8 digits — matches Indian and several other
# passport formats); tenants override via ``bot_config.ocr_patterns``.
_DEFAULT_OCR_PASSPORT_REGEX = r"\b[A-Z]{1,2}\d{6,8}\b"
_DEFAULT_OCR_DATE_REGEX     = r"\b(\d{2}[/\-]\d{2}[/\-]\d{4})\b"
_DEFAULT_OCR_NAME_BLOCKLIST = [
    "PASSPORT", "REPUBLIC", "NATIONALITY", "SURNAME", "GIVEN",
    "GOVERNMENT", "OFFICIAL", "IDENTITY", "CITIZEN", "DRIVING", "LICENSE",
]


async def _parse_ocr_text(text: str, company_id: Optional[str] = None) -> Dict[str, str]:
    """Heuristic extraction of common fields from OCR text.

    Per-tenant overrides via ``bot_config.ocr_patterns`` — when unset, the
    platform defaults above apply.

    **Important behaviour fix (audit P0)**: this function no longer hard-
    codes ``nationality = "Indian"`` when the word "INDIAN" appears in the
    OCR text. It now extracts whatever value follows a "Nationality:"
    label in the document (which is the only sane source) and writes
    nothing otherwise — operators can still fill it in manually.
    """
    fields: Dict[str, str] = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Per-tenant overrides — fall back to platform default when blank.
    passport_re   = _DEFAULT_OCR_PASSPORT_REGEX
    date_re       = _DEFAULT_OCR_DATE_REGEX
    name_blocklist = _DEFAULT_OCR_NAME_BLOCKLIST
    if company_id:
        try:
            from services.bot_config import get_bot_config
            cfg = await get_bot_config(company_id)
            patterns = (cfg.raw or {}).get("ocr_patterns") or {}
            passport_re    = (patterns.get("passport_regex") or "").strip() or passport_re
            date_re        = (patterns.get("date_regex") or "").strip() or date_re
            blocklist_cfg  = patterns.get("name_blocklist") or []
            if blocklist_cfg:
                name_blocklist = [str(b).upper() for b in blocklist_cfg if b]
        except Exception:
            pass  # fall through to platform defaults

    # Passport / document number
    try:
        m = re.search(passport_re, text)
        if m:
            fields["passport_number"] = m.group(0)
    except re.error:
        logger.warning("[_parse_ocr_text] invalid passport_regex; falling back to default")
        m = re.search(_DEFAULT_OCR_PASSPORT_REGEX, text)
        if m:
            fields["passport_number"] = m.group(0)

    # Date of birth (or first DD/MM/YYYY we find)
    try:
        m = re.search(date_re, text)
        if m:
            fields["dob"] = m.group(0).replace("-", "/")
    except re.error:
        pass

    # Name: scan the first ~15 lines for an ALL-CAPS line of 2+ tokens
    # that doesn't look like a label. Skip lines containing any
    # blocklisted token (case-insensitive).
    for line in lines[:15]:
        if re.match(r'^[A-Z][A-Z\s]{4,50}$', line) and len(line.split()) >= 2:
            upper = line.upper()
            if not any(kw in upper for kw in name_blocklist):
                fields.setdefault("full_name", line.title())
                break

    # Nationality — extract the value AFTER a "Nationality:" / "Nationalité:"
    # label. **Never** auto-set a hard-coded value when only the word
    # appears in the text (the previous P0 bug).
    nat_match = re.search(
        r"(?:Nationality|Nationalit[eé])\s*[:\-]\s*([A-Za-z][A-Za-z\s\-]{1,40})",
        text,
        re.IGNORECASE,
    )
    if nat_match:
        nat = nat_match.group(1).strip().strip(",;.")
        # Trim at the first run of >=2 spaces or newline (OCR fragments).
        nat = re.split(r"\s{2,}|\n", nat, maxsplit=1)[0].strip()
        if nat:
            fields["nationality"] = nat.title()

    return fields


# ── Review endpoints (email link flow) ───────────────────────────────────────

@router.get("/review/{edit_token}")
async def get_review(edit_token: str):
    db = await get_database()
    app = await db.seva_setu_applications.find_one({"edit_token": edit_token})
    if not app:
        raise HTTPException(status_code=404, detail="Review link not found.")

    expires = app.get("edit_token_expires_at", "")
    if isinstance(expires, str) and expires:
        exp_dt = datetime.fromisoformat(expires)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if _now() > exp_dt:
            return {
                "expired": True,
                "reference_id": app["reference_id"],
                "message": "This link has expired. Your application has been submitted as-is.",
            }

    svc = (await _load_tenant_services(db, app["company_id"])).get(app["service_type"], {})
    return {
        "expired": False,
        "id": app["id"],
        "reference_id": app["reference_id"],
        "service_type": app["service_type"],
        "service_name": app.get("service_name", svc.get("name")),
        "status": app["status"],
        "form_data": app.get("form_data", {}),
        "documents": app.get("documents", []),
        "fields": svc.get("fields", []),
    }


@router.put("/review/{edit_token}")
async def edit_review(edit_token: str, req: ReviewEditRequest):
    db = await get_database()
    app = await db.seva_setu_applications.find_one({"edit_token": edit_token})
    if not app:
        raise HTTPException(status_code=404, detail="Review link not found.")

    expires = app.get("edit_token_expires_at", "")
    if isinstance(expires, str) and expires:
        exp_dt = datetime.fromisoformat(expires)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if _now() > exp_dt:
            raise HTTPException(status_code=400, detail="Review link expired.")

    if app["status"] == "confirmed":
        raise HTTPException(status_code=400, detail="Application already confirmed.")

    merged = {**app.get("form_data", {}), **req.form_data}
    await db.seva_setu_applications.update_one(
        {"edit_token": edit_token},
        {"$set": {"form_data": merged, "updated_at": _now().isoformat()}}
    )
    return {"success": True, "form_data": merged}


@router.post("/review/{edit_token}/confirm")
async def confirm_via_review(edit_token: str):
    """Confirm application from the review email link."""
    db = await get_database()
    app = await db.seva_setu_applications.find_one({"edit_token": edit_token})
    if not app:
        raise HTTPException(status_code=404, detail="Review link not found.")

    expires = app.get("edit_token_expires_at", "")
    if isinstance(expires, str) and expires:
        exp_dt = datetime.fromisoformat(expires)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if _now() > exp_dt:
            raise HTTPException(status_code=400, detail="Review link expired. Application submitted as-is.")

    if app["status"] == "confirmed":
        return {"success": True, "already_confirmed": True, "reference_id": app["reference_id"]}

    # Scope the user lookup by the application's tenant — the edit_token
    # entry-point doesn't carry session context, but the loaded app row does.
    user = await db.seva_setu_users.find_one(
        {"id": app["user_id"], "company_id": app.get("company_id")}
    )
    svc = (await _load_tenant_services(db, app["company_id"])).get(app["service_type"], {})
    form_data = app.get("form_data", {})

    _bot_name, _org_name = await _brand_for(app["company_id"])

    pdf_bytes = generate_application_pdf(
        service_name=app.get("service_name", svc.get("name", app["service_type"])),
        form_data=form_data,
        tracking_id=app["reference_id"],
        uploaded_docs=[
            {"name": d.get("name", "Document"), "status": "uploaded"}
            for d in app.get("documents", [])
        ],
        required_docs=_filter_required_docs(svc.get("documents", []), form_data),
        org_name=_org_name or _bot_name,
        branding=await _pdf_branding_for(app["company_id"]),
        field_labels=_field_labels_for(svc),
    )

    pdf_filename = f"{app['reference_id']}.pdf"
    pdf_path = os.path.join(UPLOAD_DIR, pdf_filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    await db.seva_setu_applications.update_one(
        {"edit_token": edit_token},
        {"$set": {"status": "confirmed", "pdf_path": pdf_path, "updated_at": _now().isoformat()}}
    )

    if user:
        send_confirmation_email(user["email"], user["name"], app["reference_id"], svc.get("name", app["service_type"]), pdf_bytes, bot_name=_bot_name, org_name=_org_name)

    return {"success": True, "reference_id": app["reference_id"], "message": "Application confirmed!"}


class TypeAFinalizeRequest(BaseModel):
    gov_reference: str


@router.post("/applications/{app_id}/type-a-finalize")
async def type_a_finalize(app_id: str, req: TypeAFinalizeRequest, authorization: str = Header(default=""), token: Optional[str] = Query(default=None)):
    """
    TYPE A finalization: user returns from gov portal with their gov reference number.
    Generates a PDF summary (name, email, gov ref, required docs) and sends confirmation email.
    """
    if token and not authorization:
        authorization = f"Bearer {token}"
    db = await get_database()
    session = await _get_session(authorization, db)

    app = await db.seva_setu_applications.find_one({"id": app_id, "user_id": session["user_id"], "company_id": session["company_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    user = await db.seva_setu_users.find_one({"id": session["user_id"], "company_id": session["company_id"]})
    svc = (await _load_tenant_services(db, app["company_id"])).get(app["service_type"], {})

    gov_ref = req.gov_reference.strip()

    # Build form_data that includes the gov reference + required doc list
    form_data_for_pdf = {
        **app.get("form_data", {}),
        "gov_reference_number": gov_ref,
    }

    # Build uploaded_docs list to show required documents in the PDF
    required_docs = [{"name": d, "status": "required"} for d in svc.get("documents", [])]

    _bot_name, _org_name = await _brand_for(session["company_id"])

    pdf_bytes = generate_application_pdf(
        service_name=app.get("service_name", svc.get("name", app["service_type"])),
        form_data=form_data_for_pdf,
        tracking_id=app["reference_id"],
        uploaded_docs=required_docs,
        org_name=_org_name or _bot_name,
        branding=await _pdf_branding_for(session["company_id"]),
        field_labels=_field_labels_for(svc),
    )

    pdf_filename = f"{app['reference_id']}.pdf"
    pdf_path = os.path.join(UPLOAD_DIR, pdf_filename)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    await db.seva_setu_applications.update_one(
        {"id": app_id, "company_id": session["company_id"]},
        {"$set": {
            "status": "confirmed",
            "form_data": form_data_for_pdf,
            "pdf_path": pdf_path,
            "updated_at": _now().isoformat(),
        }}
    )

    if user:
        send_confirmation_email(
            user["email"], user["name"],
            app["reference_id"],
            svc.get("name", app["service_type"]),
            pdf_bytes,
            bot_name=_bot_name,
            org_name=_org_name,
        )

    return {
        "success": True,
        "reference_id": app["reference_id"],
        "message": "Application recorded. Confirmation email with PDF sent.",
    }
