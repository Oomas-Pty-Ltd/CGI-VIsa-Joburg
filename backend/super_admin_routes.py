from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from typing import Any, Dict, List, Optional
import uuid
import csv
import io
import re
import logging
from datetime import datetime, timezone, date
import bcrypt

logger = logging.getLogger("super_admin_routes")
from database import get_database
from auth_utils import verify_super_admin, verify_admin, enforce_tenant_scope
from knowledge_scraper import invalidate_knowledge_cache
from services.audit_service import audit_service, AuditCategory, AuditSeverity


async def _audit_safe(db, **kwargs):
    """Best-effort audit write — never block the request on audit failures."""
    try:
        await audit_service.log(db=db, **kwargs)
    except Exception:
        pass

router = APIRouter(prefix="/super-admin", tags=["super-admin"])

class CompanyCreate(BaseModel):
    name: str
    email: EmailStr
    admin_password: str
    llm_model: str = "gpt-5.2"
    features: dict = {"voice": True, "camera": True}

class Company(BaseModel):
    id: str
    name: str
    email: str
    llm_model: str
    features: dict
    created_at: str
    status: str

class LLMConfig(BaseModel):
    company_id: str
    model: str
    provider: str = "openai"

@router.post("/companies", response_model=Company)
async def create_company(
    company: CompanyCreate,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    db = await get_database()

    existing = await db.companies.find_one({"email": company.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company with this email already exists"
        )

    # Sprint 7: admin emails are globally unique across local_admins + super_admins
    # so the unified login can resolve a row from email alone. Without this
    # check the migration's unique index would reject the insert at the DB
    # layer, but a route-level guard gives a friendlier error.
    if await db.local_admins.find_one({"email": company.email}, {"_id": 0, "id": 1}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A local admin with email {company.email!r} already exists. Use a different email."
        )
    if await db.super_admins.find_one({"email": company.email}, {"_id": 0, "id": 1}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Email {company.email!r} is already in use by a super admin."
        )

    company_id = str(uuid.uuid4())
    admin_id = str(uuid.uuid4())
    
    company_doc = {
        "id": company_id,
        "name": company.name,
        "email": company.email,
        "llm_model": company.llm_model,
        "features": company.features,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active"
    }
    
    await db.companies.insert_one(company_doc)
    
    hashed_password = bcrypt.hashpw(company.admin_password.encode('utf-8'), bcrypt.gensalt())
    admin_doc = {
        "id": admin_id,
        "company_id": company_id,
        "email": company.email,
        "password": hashed_password.decode('utf-8'),
        # Sprint 10: super-admin types the initial password; the new
        # local-admin is forced to set their own on first login. The
        # flag is cleared in POST /api/auth/change-password.
        "password_change_required": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.local_admins.insert_one(admin_doc)

    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="create_company",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="company",
        resource_id=company_id,
        company_id=company_id,
        new_value={"name": company.name, "email": company.email, "llm_model": company.llm_model},
        ip_address=http_request.client.host if http_request.client else None,
    )

    try:
        from services.notification_dispatcher import notify
        await notify("tenant.created", company_id=company_id, context={
            "tenant_name": company.name, "admin_email": company.email, "org_name": company.name,
        })
    except Exception:
        logger.exception("tenant.created notify failed")

    return Company(**company_doc)

@router.get("/companies", response_model=List[Company])
async def get_companies(limit: int = 100, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    companies = await db.companies.find(
        {}, 
        {"_id": 0, "id": 1, "name": 1, "email": 1, "llm_model": 1, "features": 1, "created_at": 1, "status": 1}
    ).limit(limit).to_list(limit)
    return [Company(**company) for company in companies]

@router.get("/companies/{company_id}", response_model=Company)
async def get_company(company_id: str, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    company = await db.companies.find_one({"id": company_id}, {"_id": 0})
    
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    return Company(**company)

# =====================================================================
# Tenant admin management (Sprint 11) — list / add / remove / reset
# local_admins for a given company. Super-admin-only because adding an
# admin grants console access to that tenant.
# =====================================================================

class AdminCreate(BaseModel):
    email:            EmailStr
    initial_password: str


class AdminPasswordReset(BaseModel):
    new_password: str


@router.get("/companies/{company_id}/admins")
async def list_company_admins(company_id: str, payload: dict = Depends(verify_super_admin)):
    """List local_admins for a tenant. Passwords are never returned."""
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    admins = await db.local_admins.find(
        {"company_id": company_id},
        {"_id": 0, "password": 0},
    ).sort("created_at", 1).to_list(100)
    return {"admins": admins, "count": len(admins)}


@router.post("/companies/{company_id}/admins", status_code=201)
async def create_company_admin(
    company_id: str,
    body: AdminCreate,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Provision an additional admin for a tenant. The new admin is
    forced through `/change-password` on first login (Sprint 10 flow)."""
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    if len(body.initial_password) < 8:
        raise HTTPException(status_code=400, detail="initial_password must be at least 8 characters")

    # Reject cross-collection / cross-tenant duplicate emails the same way
    # POST /companies does — emails are globally unique post-Sprint-7.
    if await db.local_admins.find_one({"email": body.email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"Email {body.email!r} is already a local admin somewhere.")
    if await db.super_admins.find_one({"email": body.email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"Email {body.email!r} is a super admin.")

    admin_id = str(uuid.uuid4())
    hashed   = bcrypt.hashpw(body.initial_password.encode("utf-8"), bcrypt.gensalt())
    now      = datetime.now(timezone.utc).isoformat()
    doc = {
        "id":                       admin_id,
        "company_id":               company_id,
        "email":                    body.email,
        "password":                 hashed.decode("utf-8"),
        "password_change_required": True,  # Sprint 10 — forced first-login
        "created_at":               now,
        "created_by":               payload.get("user_id"),
    }
    await db.local_admins.insert_one(doc)
    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="create_local_admin",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="local_admin",
        resource_id=admin_id,
        company_id=company_id,
        new_value={"email": body.email},
        ip_address=http_request.client.host if http_request.client else None,
    )
    try:
        from services.notification_dispatcher import notify
        await notify("tenant.admin_added", company_id=company_id, context={
            "new_email": body.email, "role": "admin",
        })
    except Exception:
        logger.exception("tenant.admin_added notify failed")
    # Exclude both the password hash and the Mongo-injected ObjectId from
    # the response. insert_one mutates `doc` in place to add `_id`.
    return {k: v for k, v in doc.items() if k not in ("password", "_id")}


@router.delete("/companies/{company_id}/admins/{admin_id}")
async def delete_company_admin(
    company_id: str,
    admin_id: str,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Remove a local admin. Refuses to delete the last admin so a tenant
    can never be left with no one able to log in — super-admin can still
    manage their console, but tenant self-service would break."""
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    count = await db.local_admins.count_documents({"company_id": company_id})
    if count <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete the last admin for a tenant. Add another admin first.",
        )

    result = await db.local_admins.delete_one(
        {"id": admin_id, "company_id": company_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Admin not found for this tenant")
    await _audit_safe(
        db,
        category=AuditCategory.DATA_DELETION,
        action="delete_local_admin",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="local_admin",
        resource_id=admin_id,
        company_id=company_id,
        ip_address=http_request.client.host if http_request.client else None,
        severity=AuditSeverity.WARNING,
    )
    return {"deleted": True, "admin_id": admin_id}


@router.post("/companies/{company_id}/admins/{admin_id}/revoke-tokens")
async def revoke_admin_tokens(
    company_id: str,
    admin_id: str,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Force every existing token for this admin to be rejected at the
    very next protected request. Useful as a "log them out everywhere"
    action without rotating the password.

    Goes through ``compliance_service.invalidate_user_tokens`` so the
    auth_utils TTL cache is busted in the same process — no wait for
    the 60s cache to expire."""
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    admin = await db.local_admins.find_one(
        {"id": admin_id, "company_id": company_id}, {"_id": 0, "id": 1, "email": 1}
    )
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found for this tenant")

    from services.compliance_service import compliance_service
    await compliance_service.invalidate_user_tokens(db, admin_id, company_id)

    await _audit_safe(
        db,
        category=AuditCategory.SECURITY_EVENT,
        action="revoke_admin_tokens",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="local_admin",
        resource_id=admin_id,
        company_id=company_id,
        metadata={"target_email": admin.get("email")},
        ip_address=http_request.client.host if http_request.client else None,
        severity=AuditSeverity.WARNING,
    )
    return {"revoked": True, "admin_id": admin_id}


@router.post("/companies/{company_id}/admins/{admin_id}/reset-password")
async def reset_admin_password(
    company_id: str,
    admin_id: str,
    body: AdminPasswordReset,
    payload: dict = Depends(verify_super_admin),
):
    """Rotate an admin's password. The admin is forced through
    `/change-password` on their next login (Sprint 10 flow)."""
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="new_password must be at least 8 characters")

    hashed = bcrypt.hashpw(body.new_password.encode("utf-8"), bcrypt.gensalt())
    result = await db.local_admins.update_one(
        {"id": admin_id, "company_id": company_id},
        {"$set": {
            "password":                 hashed.decode("utf-8"),
            "password_change_required": True,
            "password_reset_at":        datetime.now(timezone.utc).isoformat(),
            "password_reset_by":        payload.get("user_id"),
        }},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Admin not found for this tenant")
    try:
        from services.notification_dispatcher import notify
        admin = await db.local_admins.find_one({"id": admin_id, "company_id": company_id}, {"_id": 0, "email": 1})
        await notify("tenant.password_reset", company_id=company_id, context={
            "admin_email": (admin or {}).get("email", ""),
        })
    except Exception:
        logger.exception("tenant.password_reset notify failed")
    return {"success": True, "admin_id": admin_id}


# ── Viewers (read-only tenant accounts) ─────────────────────────────────────
# Mirrors the admins surface above. The runtime gate that distinguishes
# the two is `auth_utils.verify_admin`, which rejects viewer tokens on
# any non-GET request — so a viewer can browse every tab a local-admin
# can, but every Save/Delete/Add button fails with a 403.


@router.get("/companies/{company_id}/viewers")
async def list_company_viewers(company_id: str, payload: dict = Depends(verify_super_admin)):
    """List read-only viewers for a tenant. Passwords are never returned."""
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    viewers = await db.local_viewers.find(
        {"company_id": company_id},
        {"_id": 0, "password": 0},
    ).sort("created_at", 1).to_list(100)
    return {"viewers": viewers, "count": len(viewers)}


@router.post("/companies/{company_id}/viewers", status_code=201)
async def create_company_viewer(
    company_id: str,
    body: AdminCreate,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Provision a viewer for a tenant. Same shape as create-admin —
    initial_password is hashed, password_change_required is true so the
    viewer must rotate the bootstrap password on first login."""
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    if len(body.initial_password) < 8:
        raise HTTPException(status_code=400, detail="initial_password must be at least 8 characters")

    # Same global-uniqueness invariant as create_company_admin — a single
    # email can't exist in more than one role, otherwise the login resolver
    # can't decide which row to authenticate.
    if await db.local_admins.find_one({"email": body.email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"Email {body.email!r} is already a local admin somewhere.")
    if await db.super_admins.find_one({"email": body.email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"Email {body.email!r} is a super admin.")
    if await db.local_viewers.find_one({"email": body.email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"Email {body.email!r} is already a viewer somewhere.")

    viewer_id = str(uuid.uuid4())
    hashed    = bcrypt.hashpw(body.initial_password.encode("utf-8"), bcrypt.gensalt())
    now       = datetime.now(timezone.utc).isoformat()
    doc = {
        "id":                       viewer_id,
        "company_id":               company_id,
        "email":                    body.email,
        "password":                 hashed.decode("utf-8"),
        "password_change_required": True,
        "created_at":               now,
        "created_by":               payload.get("user_id"),
    }
    await db.local_viewers.insert_one(doc)
    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="create_local_viewer",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="local_viewer",
        resource_id=viewer_id,
        company_id=company_id,
        new_value={"email": body.email},
        ip_address=http_request.client.host if http_request.client else None,
    )
    return {k: v for k, v in doc.items() if k not in ("password", "_id")}


@router.delete("/companies/{company_id}/viewers/{viewer_id}")
async def delete_company_viewer(
    company_id: str,
    viewer_id: str,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Remove a viewer. Unlike admins, a tenant may have zero viewers —
    they're a strictly additive role, so no last-row safety guard."""
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    result = await db.local_viewers.delete_one(
        {"id": viewer_id, "company_id": company_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Viewer not found for this tenant")
    await _audit_safe(
        db,
        category=AuditCategory.DATA_DELETION,
        action="delete_local_viewer",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="local_viewer",
        resource_id=viewer_id,
        company_id=company_id,
        ip_address=http_request.client.host if http_request.client else None,
        severity=AuditSeverity.WARNING,
    )
    return {"deleted": True, "viewer_id": viewer_id}


@router.post("/companies/{company_id}/viewers/{viewer_id}/reset-password")
async def reset_viewer_password(
    company_id: str,
    viewer_id: str,
    body: AdminPasswordReset,
    payload: dict = Depends(verify_super_admin),
):
    """Rotate a viewer's password and force a change on next login."""
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="new_password must be at least 8 characters")

    hashed = bcrypt.hashpw(body.new_password.encode("utf-8"), bcrypt.gensalt())
    result = await db.local_viewers.update_one(
        {"id": viewer_id, "company_id": company_id},
        {"$set": {
            "password":                 hashed.decode("utf-8"),
            "password_change_required": True,
            "password_reset_at":        datetime.now(timezone.utc).isoformat(),
            "password_reset_by":        payload.get("user_id"),
        }},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Viewer not found for this tenant")
    return {"success": True, "viewer_id": viewer_id}


@router.put("/companies/{company_id}/llm-config")
async def update_llm_config(company_id: str, config: LLMConfig, payload: dict = Depends(verify_super_admin)):
    db = await get_database()

    result = await db.companies.update_one(
        {"id": company_id},
        {"$set": {"llm_model": config.model}}
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )

    return {"success": True, "message": "LLM config updated"}


class CompanyStatusUpdate(BaseModel):
    """Allowed values: "active" or "suspended". Anything else is rejected
    so a typo doesn't accidentally take a tenant offline."""
    status: str


class CompanyBudgetUpdate(BaseModel):
    """Monthly LLM cost budget in USD. Validated >= 0."""
    llm_monthly_budget_usd: float


@router.put("/companies/{company_id}/llm-budget")
async def update_company_llm_budget(
    company_id: str,
    update: CompanyBudgetUpdate,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Per-tenant LLM cost budget. The local-admin Cost tab reads this
    via /local-admin/llm-usage and renders the gauge against it."""
    if update.llm_monthly_budget_usd < 0:
        raise HTTPException(status_code=400, detail="Budget must be >= 0")
    db = await get_database()
    existing = await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1, "llm_monthly_budget_usd": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Company not found")
    await db.companies.update_one(
        {"id": company_id},
        {"$set": {"llm_monthly_budget_usd": float(update.llm_monthly_budget_usd)}},
    )
    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="update_llm_budget",
        user_id=payload.get("user_id"),
        user_type=payload.get("user_type"),
        resource_type="company",
        resource_id=company_id,
        company_id=company_id,
        old_value={"llm_monthly_budget_usd": existing.get("llm_monthly_budget_usd")},
        new_value={"llm_monthly_budget_usd": update.llm_monthly_budget_usd},
        ip_address=http_request.client.host if http_request.client else None,
    )
    return {"id": company_id, "llm_monthly_budget_usd": update.llm_monthly_budget_usd}


@router.put("/companies/{company_id}/status")
async def update_company_status(
    company_id: str,
    update: CompanyStatusUpdate,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Activate or suspend a tenant. Suspended tenants are rejected at the
    `get_tenant_id` boundary, so the widget can't open sessions, the chat
    endpoint refuses inbound messages, and widget-config returns 400 —
    the embed effectively goes dark without any infra change on the host
    page.

    Cache invalidation is critical here: `tenant._validity_cache` holds
    a positive result for `cache_company_validity_ttl_seconds` (default
    60s), so without invalidating, a freshly-suspended tenant would keep
    serving for up to a minute.
    """
    desired = (update.status or "").strip().lower()
    if desired not in ("active", "suspended"):
        raise HTTPException(
            status_code=400,
            detail="status must be 'active' or 'suspended'",
        )
    db = await get_database()
    existing = await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1, "status": 1, "name": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Company not found")

    await db.companies.update_one(
        {"id": company_id},
        {"$set": {"status": desired, "status_updated_at": datetime.now(timezone.utc).isoformat()}},
    )

    # Bust the cache so the change takes effect immediately, not on the
    # next 60s expiry.
    import tenant
    tenant.invalidate_cache(company_id)

    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="update_company_status",
        user_id=payload.get("user_id"),
        user_type=payload.get("user_type"),
        resource_type="company",
        resource_id=company_id,
        company_id=company_id,
        old_value={"status": existing.get("status")},
        new_value={"status": desired},
        ip_address=http_request.client.host if http_request.client else None,
    )

    try:
        from services.notification_dispatcher import notify
        await notify("tenant.status_changed", company_id=company_id, context={
            "tenant_name": existing.get("name", ""),
            "status": "activated" if desired == "active" else "deactivated",
        })
    except Exception:
        logger.exception("tenant.status_changed notify failed")

    return {"id": company_id, "status": desired, "name": existing.get("name")}

@router.get("/analytics/overview")
async def get_analytics_overview(payload: dict = Depends(verify_super_admin)):
    db = await get_database()

    total_companies = await db.companies.count_documents({})
    total_sessions = await db.chat_sessions.count_documents({})
    total_documents = await db.documents.count_documents({})

    return {
        "total_companies": total_companies,
        "total_sessions": total_sessions,
        "total_documents": total_documents
    }


# ─── Sessions / Conversations ────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    company_id: Optional[str] = None,
    channel: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    payload: dict = Depends(verify_admin),
):
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    query = {}
    if company_id:
        query["company_id"] = company_id
    if channel:
        query["channel"] = channel

    skip = (page - 1) * limit
    total = await db.chat_sessions.count_documents(query)
    raw = await (
        db.chat_sessions.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    sessions = []
    for s in raw:
        msgs = s.get("messages", [])
        first_user = next((m["content"] for m in msgs if m.get("role") == "user"), "—")
        sessions.append({
            "id": s.get("id", ""),
            "channel": s.get("channel", "—"),
            "company_id": s.get("company_id") or s.get("metadata", {}).get("company_id", "—"),
            "user_identifier": s.get("user_identifier", "—"),
            "message_count": len(msgs),
            "first_message": first_user[:100],
            "created_at": s.get("created_at", ""),
            "last_activity": s.get("last_activity", ""),
            "is_active": s.get("is_active", False),
        })

    return {"sessions": sessions, "total": total, "page": page, "limit": limit}


@router.get("/sessions/export/csv")
async def export_sessions_csv(
    company_id: Optional[str] = None,
    channel: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    payload: dict = Depends(verify_admin),
):
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    query = {}
    if company_id:
        query["company_id"] = company_id
    if channel:
        query["channel"] = channel
    if from_date or to_date:
        query["created_at"] = {}
        if from_date:
            query["created_at"]["$gte"] = from_date
        if to_date:
            query["created_at"]["$lte"] = to_date + "T23:59:59Z"

    raw = await db.chat_sessions.find(query, {"_id": 0}).sort("created_at", -1).to_list(10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Session ID", "Channel", "Company ID", "User Identifier",
        "Total Messages", "First Message", "Created At", "Last Activity", "Active",
        "Role", "Message", "Timestamp"
    ])

    for s in raw:
        msgs = s.get("messages", [])
        first_user = next((m["content"] for m in msgs if m.get("role") == "user"), "—")
        # Summary row
        writer.writerow([
            s.get("id", ""), s.get("channel", ""),
            s.get("company_id") or s.get("metadata", {}).get("company_id", ""),
            s.get("user_identifier", ""), len(msgs), first_user[:200],
            s.get("created_at", ""), s.get("last_activity", ""), s.get("is_active", False),
            "", "", ""
        ])
        # One row per message
        for m in msgs:
            writer.writerow([
                s.get("id", ""), "", "", "", "", "", "", "", "",
                m.get("role", ""), m.get("content", "")[:500], m.get("timestamp", "")
            ])

    output.seek(0)
    filename = f"sessions_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str, payload: dict = Depends(verify_admin)):
    db = await get_database()
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    # Local admins can only see sessions belonging to their tenant.
    # 404 (not 403) so the response can't be used to confirm a session exists
    # under a different tenant.
    if payload.get("user_type") == "local_admin":
        jwt_tenant = payload.get("company_id")
        session_tenant = session.get("company_id") or session.get("metadata", {}).get("company_id")
        if jwt_tenant != session_tenant:
            raise HTTPException(status_code=404, detail="Session not found")
    return session


# ─── Audit Logs ──────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def list_audit_logs(
    company_id: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    payload: dict = Depends(verify_admin),
):
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    query = {}
    if company_id:
        query["company_id"] = company_id
    if category:
        query["category"] = category
    if severity:
        query["severity"] = severity

    skip = (page - 1) * limit
    total = await db.audit_logs.count_documents(query)
    logs = await (
        db.audit_logs.find(query, {"_id": 0})
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    return {"logs": logs, "total": total, "page": page, "limit": limit}


@router.get("/audit-logs/export/csv")
async def export_audit_logs_csv(
    company_id: Optional[str] = None,
    category: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    payload: dict = Depends(verify_admin),
):
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    query = {}
    if company_id:
        query["company_id"] = company_id
    if category:
        query["category"] = category
    if from_date or to_date:
        query["timestamp"] = {}
        if from_date:
            query["timestamp"]["$gte"] = from_date
        if to_date:
            query["timestamp"]["$lte"] = to_date + "T23:59:59Z"

    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).to_list(10000)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Timestamp", "Category", "Severity", "Action",
        "User ID", "User Type", "Company ID", "Resource Type", "Resource ID",
        "Success", "IP Address", "Error Message"
    ])

    for log in logs:
        writer.writerow([
            log.get("id", ""), log.get("timestamp", ""), log.get("category", ""),
            log.get("severity", ""), log.get("action", ""), log.get("user_id", ""),
            log.get("user_type", ""), log.get("company_id", ""), log.get("resource_type", ""),
            log.get("resource_id", ""), log.get("success", ""), log.get("ip_address", ""),
            log.get("error_message", ""),
        ])

    output.seek(0)
    filename = f"audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# PDF → KNOWLEDGE BASE
# ─────────────────────────────────────────────────────────────────────────────

_MONTHS = {
    "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
    "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
    "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,
    "sep":9,"oct":10,"nov":11,"dec":12,
}

_KB_STOP_WORDS = {
    "the","and","or","but","in","on","at","to","for","of","a","an","is","are",
    "was","were","be","been","being","have","has","had","do","does","did","will",
    "would","could","should","may","might","shall","can","this","that","these",
    "those","with","from","by","as","into","through","during","above","below",
    "between","each","further","then","once","here","there","all","both","few",
    "more","most","other","some","such","no","nor","not","only","same","than",
    "too","very","just","also","about","after","before","under","over","its",
    "it","if","we","you","he","she","they","our","their","your","his","her",
}


def _extract_pdf_text(file_bytes: bytes) -> str:
    """
    Extract plain text from PDF bytes.
    Tries three engines in order of capability:
      1. PyMuPDF (fitz)   — handles complex/compressed layouts best
      2. pdfplumber       — great for tables and unusual encodings
      3. pypdf            — lightweight fallback
    Returns empty string if the PDF has no text layer (scanned/image PDF).
    """
    # ── 1. PyMuPDF ────────────────────────────────────────────────────
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        parts = []
        for page in doc:
            text = page.get_text("text").strip()
            if text:
                parts.append(text)
        doc.close()
        result = "\n\n".join(parts)
        if result.strip():
            return result
    except ImportError:
        pass
    except Exception:
        pass

    # ── 2. pdfplumber ─────────────────────────────────────────────────
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text and text.strip():
                    parts.append(text.strip())
        result = "\n\n".join(parts)
        if result.strip():
            return result
    except ImportError:
        pass
    except Exception:
        pass

    # ── 3. pypdf ──────────────────────────────────────────────────────
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                parts.append(text.strip())
        result = "\n\n".join(parts)
        if result.strip():
            return result
    except ImportError:
        pass
    except Exception:
        pass

    return ""  # Scanned/image PDF — caller should try OCR


_OCR_MAX_PAGES = 30   # safety cap for vision-API cost
_OCR_RENDER_DPI = 150  # good OCR quality without huge images


async def _ocr_pdf_with_vision(file_bytes: bytes) -> str:
    """
    OCR a scanned (image-based) PDF using GPT-4o vision.
    Renders each page with PyMuPDF → sends as base64 PNG → extracts text.
    Returns combined text or empty string on failure.
    """
    import fitz
    import base64
    import os
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return ""

    client = AsyncOpenAI(api_key=api_key)
    scale = _OCR_RENDER_DPI / 72.0
    mat = fitz.Matrix(scale, scale)

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = min(len(doc), _OCR_MAX_PAGES)
        pages_text: List[str] = []

        for page_num in range(page_count):
            pix = doc[page_num].get_pixmap(matrix=mat, alpha=False)
            img_b64 = base64.b64encode(pix.tobytes("png")).decode()

            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract all text from this document page exactly as it appears. "
                                "Preserve headings, dates, lists, and table structure. "
                                "Return only the extracted text with no commentary."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }],
                max_tokens=2000,
            )
            text = response.choices[0].message.content.strip()
            if text:
                pages_text.append(f"[Page {page_num + 1}]\n{text}")

        doc.close()
        return "\n\n".join(pages_text)

    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(f"[OCR] Vision OCR failed: {exc}")
        return ""


def _find_dates_in_text(text: str) -> List[date]:
    """Parse every recognisable date from free-form text. Returns sorted unique dates."""
    found: List[date] = []
    text_lower = text.lower()

    # ISO: 2024-04-15
    for m in re.finditer(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', text):
        try:
            found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass

    # DD/MM/YYYY or DD-MM-YYYY
    for m in re.finditer(r'\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b', text):
        try:
            found.append(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass

    # "15 April 2026" / "15th April 2026"
    for m in re.finditer(
        r'\b(\d{1,2})(?:st|nd|rd|th)?\s+'
        r'(january|february|march|april|may|june|july|august|september|october|november|december'
        r'|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{4})\b',
        text_lower,
    ):
        try:
            found.append(date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1))))
        except ValueError:
            pass

    # "April 15, 2026" / "April 15 2026"
    for m in re.finditer(
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december'
        r'|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b',
        text_lower,
    ):
        try:
            found.append(date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2))))
        except ValueError:
            pass

    # "April 2026" (month + year only → first of month)
    for m in re.finditer(
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december'
        r'|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{4})\b',
        text_lower,
    ):
        try:
            found.append(date(int(m.group(2)), _MONTHS[m.group(1)], 1))
        except ValueError:
            pass

    return sorted(set(found))


def _classify_event_status(dates: List[date]) -> str:
    """Return 'past' | 'present' | 'future' | 'general'."""
    if not dates:
        return "general"
    today = date.today()
    if any(d == today for d in dates):
        return "present"
    if any(d > today for d in dates):
        return "future"
    return "past"


def _enrich_with_date_context(text: str, dates: List[date], status: str) -> str:
    """Prepend a date-awareness header so the LLM answers correctly."""
    if status == "general" or not dates:
        return text
    try:
        date_strs = ", ".join(d.strftime("%d %B %Y") for d in dates[:3])
    except Exception:
        date_strs = ", ".join(d.isoformat() for d in dates[:3])

    if status == "past":
        header = (
            f"[HISTORICAL — Event/information dated {date_strs}. "
            "This has already occurred. When asked, inform the user it has passed.]"
        )
    elif status == "present":
        header = f"[CURRENT — This event is happening today ({date_strs}).]"
    else:
        header = f"[UPCOMING — This event is scheduled for {date_strs}. Inform the user it is in the future.]"
    return f"{header}\n\n{text}"


def _split_into_sections(text: str, max_chars: int = 1500) -> List[str]:
    """Chunk PDF text into knowledge-base-sized pieces."""
    raw = re.split(r'\n\s*\n', text)
    sections: List[str] = []
    current = ""
    for s in raw:
        s = s.strip()
        if not s:
            continue
        if len(current) + len(s) + 2 <= max_chars:
            current = (current + "\n\n" + s).strip() if current else s
        else:
            if current:
                sections.append(current)
            if len(s) > max_chars:
                for i in range(0, len(s), max_chars):
                    sections.append(s[i : i + max_chars])
                current = ""
            else:
                current = s
    if current:
        sections.append(current)
    return [s for s in sections if len(s.strip()) > 60]


def _extract_keywords(text: str) -> List[str]:
    """Top-20 non-stop-word tokens from text.

    Also captures hyphenated compound terms (e.g. 'id-ul-fitr', 'eid-ul-adha')
    as whole keywords so they are searchable by their full or partial forms.
    """
    norm_text = re.sub(r'[-_]+', ' ', text.lower())
    words = re.findall(r'\b[a-zA-Z]{3,}\b', norm_text)
    freq: dict = {}
    for w in words:
        if w not in _KB_STOP_WORDS:
            freq[w] = freq.get(w, 0) + 1
    top_words = [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:15]]

    # Add full hyphenated tokens as extra keywords (e.g. "id-ul-fitr" alongside "fitr")
    compound = re.findall(r'\b[a-zA-Z]+-(?:[a-zA-Z]+-)*[a-zA-Z]+\b', text.lower())
    for c in compound:
        if c not in top_words:
            top_words.append(c)

    return top_words[:20]


def _make_title(section_text: str, doc_title: str, idx: int) -> str:
    """Derive a short title for a knowledge entry from the first line of the section."""
    first_line = section_text.split("\n")[0].strip()
    # Use the first line if it looks like a heading (short, mostly caps or title-case)
    if 5 < len(first_line) < 100 and not first_line.endswith("."):
        return first_line
    if doc_title:
        return f"{doc_title} — Part {idx + 1}"
    return f"PDF Upload — Part {idx + 1}"


# Q&A patterns: "Q: ...", "Question: ...", numbered "1. ..." followed by "A: ..."
_QA_QUESTION_RE = re.compile(
    r'^(?:Q(?:uestion)?[\s\d]*[:\.\)]\s*|(\d+[\.\)]\s+))',
    re.IGNORECASE,
)
_QA_ANSWER_RE = re.compile(
    r'^A(?:nswer)?[\s]*[:\.\)]\s*',
    re.IGNORECASE,
)


def _parse_faq_pairs(text: str) -> List[Dict]:
    """
    Detect and extract Q&A pairs from text.
    Returns list of {"question": str, "answer": str} dicts.
    Returns empty list if the text doesn't look like a FAQ.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    pairs: List[Dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        q_match = _QA_QUESTION_RE.match(line)
        if q_match:
            question = _QA_QUESTION_RE.sub("", line).strip()
            # Collect multi-line question text until we hit an answer marker or next question
            i += 1
            while i < len(lines) and not _QA_ANSWER_RE.match(lines[i]) and not _QA_QUESTION_RE.match(lines[i]):
                question += " " + lines[i]
                i += 1
            # Collect answer
            answer_parts: List[str] = []
            if i < len(lines) and _QA_ANSWER_RE.match(lines[i]):
                answer_parts.append(_QA_ANSWER_RE.sub("", lines[i]).strip())
                i += 1
                while i < len(lines) and not _QA_QUESTION_RE.match(lines[i]) and not _QA_ANSWER_RE.match(lines[i]):
                    answer_parts.append(lines[i])
                    i += 1
            if question and answer_parts:
                pairs.append({"question": question.strip(), "answer": " ".join(answer_parts).strip()})
        else:
            i += 1
    return pairs


def _is_faq_text(text: str) -> bool:
    """Return True if the text contains at least 2 Q&A pairs."""
    return len(_parse_faq_pairs(text)) >= 2


# ─── PDF Upload endpoint ──────────────────────────────────────────────────────

@router.post("/knowledge/upload-pdf")
async def upload_pdf_to_knowledge(
    file: UploadFile = File(...),
    title: str = Form(""),
    category: str = Form("general"),
    company_id: Optional[str] = Form(None),
    payload: dict = Depends(verify_admin),
):
    """
    Upload a PDF; extract its text; parse dates; classify events as
    past / present / future; store each logical section as a knowledge_base entry.

    Auth: either super_admin (must pass ``company_id`` for the target tenant)
    or local_admin (``company_id`` is taken from the JWT and any mismatched
    value is rejected). A local_admin can only ever upload to their own tenant.
    """
    company_id = enforce_tenant_scope(payload, company_id)
    if not company_id:
        raise HTTPException(status_code=400, detail="company_id is required")
    db_check = await get_database()
    if not await _company_exists(db_check, company_id):
        raise HTTPException(status_code=404, detail=f"company_id {company_id!r} not found")
    created_by_label = payload.get("user_type") or "admin"
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    MAX_SIZE = 50 * 1024 * 1024  # 50 MB
    file_bytes = await file.read()
    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="PDF exceeds 50 MB limit.")

    # ── Step 1: try fast text-layer extraction ────────────────────────
    raw_text = _extract_pdf_text(file_bytes)
    ocr_used = False

    # ── Step 2: fall back to vision OCR for scanned/image PDFs ───────
    if not raw_text.strip():
        raw_text = await _ocr_pdf_with_vision(file_bytes)
        ocr_used = bool(raw_text.strip())

    if not raw_text.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not extract text from this PDF. "
                "It appears to be a scanned image and OCR also failed. "
                "Please ensure OPENAI_API_KEY is set, or use a PDF with a text layer."
            ),
        )

    doc_title = title.strip() or file.filename.replace(".pdf", "").replace("_", " ").strip()
    doc_title = re.sub(r'^\d+', '', doc_title).strip()  # strip leading numeric prefix from filename

    db = await get_database()
    created_entries = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Detect FAQ format and parse into precise Q&A pairs ────────────
    faq_pairs = _parse_faq_pairs(raw_text)
    if faq_pairs:
        # Store each Q&A pair as its own knowledge entry with the real question
        for idx, pair in enumerate(faq_pairs):
            q_text = pair["question"]
            a_text = pair["answer"]
            full_text = f"Q: {q_text}\nA: {a_text}"
            dates = _find_dates_in_text(full_text)
            status_label = _classify_event_status(dates)
            enriched = _enrich_with_date_context(a_text, dates, status_label)
            keywords = _extract_keywords(q_text + " " + a_text)
            entry_id = str(uuid.uuid4())

            entry_doc = {
                "id": entry_id,
                "company_id": company_id,
                "category": category,
                "title": q_text[:120],
                "question": q_text,
                "answer": enriched,
                "keywords": keywords,
                "source": f"pdf_upload:{file.filename}",
                "source_verified": True,
                "version": 1,
                "status": "active",
                "language": "en",
                "created_by": created_by_label,
                "created_at": now_iso,
                "updated_at": now_iso,
                "updated_by": None,
                "valid_from": dates[0].isoformat() if dates else None,
                "valid_until": dates[-1].isoformat() if dates else None,
                "event_status": status_label,
                "pdf_filename": file.filename,
                "pdf_doc_title": doc_title,
                "faq_entry": True,
            }
            await db.knowledge_base.insert_one(entry_doc)
            created_entries.append({
                "id": entry_id,
                "title": q_text[:80],
                "category": category,
                "event_status": status_label,
                "dates_found": [d.isoformat() for d in dates],
                "keywords": keywords[:8],
                "source": f"pdf_upload:{file.filename}",
            })
    else:
        # Regular document — split into sections as before
        sections = _split_into_sections(raw_text)
        if not sections:
            raise HTTPException(status_code=400, detail="PDF contained no usable text sections.")

        for idx, section in enumerate(sections):
            dates = _find_dates_in_text(section)
            status_label = _classify_event_status(dates)
            enriched = _enrich_with_date_context(section, dates, status_label)
            keywords = _extract_keywords(section)
            entry_title = _make_title(section, doc_title, idx)
            entry_id = str(uuid.uuid4())

            entry_doc = {
                "id": entry_id,
                "company_id": company_id,
                "category": category,
                "title": entry_title,
                "question": f"What is the information about: {entry_title}?",
                "answer": enriched,
                "keywords": keywords,
                "source": f"pdf_upload:{file.filename}",
                "source_verified": True,
                "version": 1,
                "status": "active",
                "language": "en",
                "created_by": created_by_label,
                "created_at": now_iso,
                "updated_at": now_iso,
                "updated_by": None,
                "valid_from": dates[0].isoformat() if dates else None,
                "valid_until": dates[-1].isoformat() if dates else None,
                "event_status": status_label,
                "pdf_filename": file.filename,
                "pdf_doc_title": doc_title,
            }
            await db.knowledge_base.insert_one(entry_doc)
            created_entries.append({
                "id": entry_id,
                "title": entry_title,
                "category": category,
                "event_status": status_label,
                "dates_found": [d.isoformat() for d in dates],
                "keywords": keywords[:8],
                "source": f"pdf_upload:{file.filename}",
            })

    # Invalidate the scraper cache so the next chat request picks up the new content
    invalidate_knowledge_cache()

    return {
        "success": True,
        "filename": file.filename,
        "doc_title": doc_title,
        "sections_created": len(created_entries),
        "ocr_used": ocr_used,
        "faq_mode": bool(faq_pairs),
        "entries": created_entries,
    }


# ─── List knowledge entries from PDF uploads ──────────────────────────────────

# Source-provenance helpers. `source_type` is reliably set on crawl rows but
# legacy PDF/manual rows may lack it, so we derive from the `source` field
# (which is always set: "pdf_upload:…", an http(s) URL for crawls, or other).
_SOURCE_TYPE_QUERY = {
    "pdf":    {"source": {"$regex": "^pdf_upload:"}},
    "crawl":  {"source": {"$regex": "^https?://"}},
    "manual": {"source": {"$not": {"$regex": "^(pdf_upload:|https?://)"}}},
}


def _derive_source_type(e: dict) -> str:
    src = (e.get("source") or "")
    if e.get("source_type") in ("crawl", "pdf", "manual"):
        return e["source_type"]
    if src.startswith("pdf_upload:"):
        return "pdf"
    if src.startswith("http://") or src.startswith("https://"):
        return "crawl"
    return "manual"


@router.get("/knowledge/entries")
async def list_knowledge_entries(
    event_status: Optional[str] = None,   # past | present | future | general
    category: Optional[str] = None,
    pdf_filename: Optional[str] = None,
    source_type: Optional[str] = None,    # manual | crawl | pdf  (omit = all)
    company_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    payload: dict = Depends(verify_admin),
):
    """List knowledge-base entries across all provenances (manual, crawler,
    PDF). Filter by ``source_type`` to narrow to one. Each entry carries its
    derived ``source_type`` + source detail (URL for crawls, filename for
    PDFs) so the UI can show where the bot's knowledge came from.

    Super-admins may pass ``?company_id`` (or omit for the cross-tenant view);
    local-admins are always scoped to their own tenant."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    query: dict = {}
    if source_type in _SOURCE_TYPE_QUERY:
        query.update(_SOURCE_TYPE_QUERY[source_type])
    if event_status:
        query["event_status"] = event_status
    if category:
        query["category"] = category
    if pdf_filename:
        query["pdf_filename"] = pdf_filename
    if company_id:
        query["company_id"] = company_id

    skip = (page - 1) * limit
    total = await db.knowledge_base.count_documents(query)
    raw = await (
        db.knowledge_base.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )

    entries = []
    for e in raw:
        st = _derive_source_type(e)
        entries.append({
            "id": e.get("id", ""),
            "company_id": e.get("company_id"),
            "title": e.get("title", ""),
            "category": e.get("category", ""),
            "event_status": e.get("event_status", "general"),
            "source_type": st,
            # Human-readable source detail: filename for PDFs, URL for crawls.
            "source_detail": (
                e.get("pdf_filename", "") if st == "pdf"
                else e.get("url") or e.get("source", "") if st == "crawl"
                else ""
            ),
            "url": e.get("url"),
            "pdf_filename": e.get("pdf_filename", ""),
            "pdf_doc_title": e.get("pdf_doc_title", ""),
            "valid_from": e.get("valid_from"),
            "valid_until": e.get("valid_until"),
            "keywords": e.get("keywords", [])[:6],
            "answer_preview": (e.get("answer", "")[:200] + "…") if len(e.get("answer", "")) > 200 else e.get("answer", ""),
            "version": e.get("version"),
            "last_seen_at": e.get("last_seen_at"),
            "created_at": e.get("created_at", ""),
            "status": e.get("status", "active"),
        })

    # Provenance breakdown for the current filter scope (minus source_type
    # filter) so the UI can show counts per source.
    scope = {k: v for k, v in query.items() if k != "source"}
    if company_id:
        scope["company_id"] = company_id
    counts = {}
    for st, q in _SOURCE_TYPE_QUERY.items():
        counts[st] = await db.knowledge_base.count_documents({**scope, **q})

    return {"entries": entries, "total": total, "page": page, "limit": limit, "source_counts": counts}


# ─── Delete a knowledge entry ─────────────────────────────────────────────────

@router.delete("/knowledge/entries/{entry_id}")
async def delete_knowledge_entry(
    entry_id: str,
    payload: dict = Depends(verify_admin),
):
    """Permanently delete a knowledge entry. Local-admins can only delete
    entries belonging to their own tenant."""
    db = await get_database()
    if payload.get("user_type") != "super_admin":
        # Scope the delete to the caller's tenant.
        tenant = enforce_tenant_scope(payload, None)
        entry = await db.knowledge_base.find_one({"id": entry_id}, {"_id": 0, "company_id": 1})
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found.")
        if entry.get("company_id") != tenant:
            raise HTTPException(status_code=404, detail="Entry not found.")
    result = await db.knowledge_base.delete_one({"id": entry_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return {"success": True, "deleted_id": entry_id}


# ─── List distinct PDF filenames uploaded ────────────────────────────────────

@router.get("/knowledge/pdf-files")
async def list_uploaded_pdfs(company_id: Optional[str] = None, payload: dict = Depends(verify_admin)):
    """Return the distinct PDF filenames that have been uploaded. Local-admins
    are scoped to their tenant; super-admins see all (or one if company_id is
    given)."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    q: dict = {"source": {"$regex": "^pdf_upload:"}}
    if company_id:
        q["company_id"] = company_id
    filenames = await db.knowledge_base.distinct("pdf_filename", q)
    return {"files": sorted(f for f in filenames if f)}


# ─── Seva Setu Applications with Documents ───────────────────────────────────

@router.get("/seva-setu/applications")
async def get_all_applications_with_documents(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    with_documents: bool = Query(True, description="Filter only applications with documents"),
    company_id: Optional[str] = None,
    status: Optional[str] = Query(None, description="Filter by application status (e.g. created, submitted, confirmed)"),
    service_type: Optional[str] = Query(None, description="Filter by service_type / service_key"),
    search: Optional[str] = Query(None, description="Case-insensitive substring match on reference_id"),
    from_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) — keep applications created on/after this date"),
    to_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) — keep applications created on/before this date"),
    payload: dict = Depends(verify_admin),
):
    """
    List Seva Setu applications with optional filtering.

    Super-admin can pass ``?company_id`` to scope to one tenant; omitting
    gives the cross-tenant view. Local admins are forced to their own tenant.

    Filters compose with AND. ``from_date`` / ``to_date`` are inclusive and
    interpreted in UTC. ``search`` is a case-insensitive substring match
    against ``reference_id``.
    """
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()

    query: Dict[str, Any] = {}
    if with_documents:
        query["documents"] = {"$exists": True, "$ne": []}
    if company_id:
        query["company_id"] = company_id
    if status:
        query["status"] = status
    if service_type:
        query["service_type"] = service_type
    if search:
        # reference_id is stored as a plain string; escape regex special chars
        # so the user typing "PASS-2024" doesn't accidentally inject metacharacters.
        query["reference_id"] = {"$regex": re.escape(search), "$options": "i"}
    if from_date or to_date:
        date_range: Dict[str, Any] = {}
        if from_date:
            date_range["$gte"] = from_date  # created_at is stored as ISO string; lexicographic compare works
        if to_date:
            # inclusive end-of-day
            date_range["$lte"] = f"{to_date}T23:59:59.999999+00:00"
        query["created_at"] = date_range

    skip = (page - 1) * limit
    total = await db.seva_setu_applications.count_documents(query)
    
    applications = await (
        db.seva_setu_applications.find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
    
    # Format applications with document summaries
    formatted_apps = []
    for app in applications:
        docs = app.get("documents", [])
        formatted_app = {
            "id": app.get("id"),
            "reference_id": app.get("reference_id"),
            "user_id": app.get("user_id"),
            "service_type": app.get("service_type"),
            "service_name": app.get("service_name"),
            "status": app.get("status"),
            "created_at": app.get("created_at"),
            "updated_at": app.get("updated_at"),
            "document_count": len(docs),
            "documents": [
                {
                    "id": doc.get("id"),
                    "name": doc.get("name"),
                    "filename": doc.get("filename"),
                    "content_type": doc.get("content_type"),
                    "status": doc.get("status"),
                    "uploaded_at": doc.get("uploaded_at"),
                }
                for doc in docs
            ],
            "form_data_fields": len(app.get("form_data", {})),
            "form_data": app.get("form_data", {}),
            # External processing-service round-trips (recorded at confirm).
            "service_status": app.get("service_status"),
            "gov_processing_ref": app.get("gov_processing_ref"),
            "service_invocations": app.get("service_invocations", []),
        }
        formatted_apps.append(formatted_app)
    
    return {
        "applications": formatted_apps,
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/seva-setu/applications/{app_id}")
async def get_application_with_documents(
    app_id: str,
    payload: dict = Depends(verify_admin),
):
    """
    Get a specific Seva Setu application with all document details.
    Local admins can only view applications belonging to their tenant.
    """
    db = await get_database()

    app = await db.seva_setu_applications.find_one(
        {"id": app_id},
        {"_id": 0}
    )

    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )

    # 404 (not 403) on cross-tenant access to avoid confirming the app
    # exists under another tenant.
    if payload.get("user_type") == "local_admin":
        if app.get("company_id") != payload.get("company_id"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Application not found",
            )
    
    # Format with full document details
    docs = app.get("documents", [])
    formatted_app = {
        "id": app.get("id"),
        "reference_id": app.get("reference_id"),
        "user_id": app.get("user_id"),
        "service_type": app.get("service_type"),
        "service_name": app.get("service_name"),
        "service_category": app.get("service_category"),
        "status": app.get("status"),
        "created_at": app.get("created_at"),
        "updated_at": app.get("updated_at"),
        "submitted_at": app.get("submitted_at"),
        "confirmed_at": app.get("confirmed_at"),
        "form_data": app.get("form_data", {}),
        "documents": [
            {
                "id": doc.get("id"),
                "name": doc.get("name"),
                "filename": doc.get("filename"),
                "path": doc.get("path"),
                "content_type": doc.get("content_type"),
                "status": doc.get("status"),
                "uploaded_at": doc.get("uploaded_at"),
            }
            for doc in docs
        ],
        # External processing-service round-trips recorded at confirm time.
        # Surfaced so operators can audit the downstream submission and
        # diagnose failures without DB access.
        "service_status": app.get("service_status"),
        "gov_processing_ref": app.get("gov_processing_ref"),
        "service_invocations": app.get("service_invocations", []),
        "edit_token": app.get("edit_token"),
    }

    return formatted_app


# ─── Keyword search & blocking ───────────────────────────────────────────────

class BlockKeywordRequest(BaseModel):
    keyword: str

@router.get("/knowledge/keyword-search")
async def search_knowledge_by_keyword(
    q: str = Query(..., min_length=1),
    payload: dict = Depends(verify_super_admin),
):
    """Search all knowledge base entries containing the given keyword."""
    db = await get_database()
    q_lower = q.strip().lower()
    cursor = db.knowledge_base.find(
        {"$or": [
            {"keywords": {"$elemMatch": {"$regex": q_lower, "$options": "i"}}},
            {"title": {"$regex": q_lower, "$options": "i"}},
            {"question": {"$regex": q_lower, "$options": "i"}},
            {"answer": {"$regex": q_lower, "$options": "i"}},
        ]},
        {"_id": 0, "id": 1, "title": 1, "category": 1, "keywords": 1,
         "pdf_filename": 1, "source": 1, "event_status": 1},
    ).limit(100)
    entries = await cursor.to_list(100)
    return {"query": q, "matches": entries, "total": len(entries)}


@router.get("/knowledge/blocked-keywords")
async def list_blocked_keywords(payload: dict = Depends(verify_super_admin)):
    """Return all currently blocked keywords."""
    db = await get_database()
    keywords = await db.blocked_keywords.find({}, {"_id": 0}).sort("blocked_at", -1).to_list(500)
    return {"keywords": keywords}


@router.post("/knowledge/blocked-keywords")
async def block_keyword(body: BlockKeywordRequest, payload: dict = Depends(verify_super_admin)):
    """Add a keyword to the blocked list so the bot returns no information for it."""
    keyword = body.keyword.strip().lower()
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty.")
    db = await get_database()
    existing = await db.blocked_keywords.find_one({"keyword": keyword})
    if existing:
        raise HTTPException(status_code=409, detail="Keyword is already blocked.")
    match_count = await db.knowledge_base.count_documents({"$or": [
        {"keywords": {"$elemMatch": {"$regex": keyword, "$options": "i"}}},
        {"title": {"$regex": keyword, "$options": "i"}},
    ]})
    await db.blocked_keywords.insert_one({
        "keyword": keyword,
        "blocked_at": datetime.now(timezone.utc).isoformat(),
        "blocked_by": "super_admin",
        "matches_count": match_count,
    })
    invalidate_knowledge_cache()
    return {"success": True, "keyword": keyword, "matches_count": match_count}


@router.delete("/knowledge/blocked-keywords/{keyword:path}")
async def unblock_keyword(keyword: str, payload: dict = Depends(verify_super_admin)):
    """Remove a keyword from the blocked list."""
    db = await get_database()
    result = await db.blocked_keywords.delete_one({"keyword": keyword.lower()})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Keyword not found in blocked list.")
    invalidate_knowledge_cache()
    return {"success": True, "keyword": keyword}


# ─────────────────────────────────────────────────────────────────────────────

@router.get("/seva-setu/applications-export/csv")
async def export_applications_with_documents_csv(
    with_documents: bool = Query(True, description="Export only applications with documents"),
    company_id: Optional[str] = None,
    status: Optional[str] = Query(None, description="Filter by application status"),
    service_type: Optional[str] = Query(None, description="Filter by service_type / service_key"),
    search: Optional[str] = Query(None, description="Case-insensitive substring match on reference_id"),
    from_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) — keep applications created on/after this date"),
    to_date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD) — keep applications created on/before this date"),
    payload: dict = Depends(verify_admin),
):
    """
    Export applications to CSV format. Same filters as the list endpoint
    so an operator can export exactly what they see. Local admins are
    forced to their own tenant.
    """
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()

    query: Dict[str, Any] = {}
    if with_documents:
        query["documents"] = {"$exists": True, "$ne": []}
    if company_id:
        query["company_id"] = company_id
    if status:
        query["status"] = status
    if service_type:
        query["service_type"] = service_type
    if search:
        query["reference_id"] = {"$regex": re.escape(search), "$options": "i"}
    if from_date or to_date:
        date_range: Dict[str, Any] = {}
        if from_date:
            date_range["$gte"] = from_date
        if to_date:
            date_range["$lte"] = f"{to_date}T23:59:59.999999+00:00"
        query["created_at"] = date_range

    applications = await db.seva_setu_applications.find(
        query, {"_id": 0}
    ).sort("created_at", -1).to_list(10000)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header row
    writer.writerow([
        "Application ID",
        "Reference ID",
        "User ID",
        "Service Type",
        "Service Name",
        "Status",
        "Document Count",
        "Documents",
        "Form Fields",
        "Created At",
        "Updated At",
        "Submitted At",
        "Confirmed At",
    ])
    
    # Data rows
    for app in applications:
        docs = app.get("documents", [])
        doc_names = "; ".join([doc.get("name", "") for doc in docs])
        
        writer.writerow([
            app.get("id", ""),
            app.get("reference_id", ""),
            app.get("user_id", ""),
            app.get("service_type", ""),
            app.get("service_name", ""),
            app.get("status", ""),
            len(docs),
            doc_names,
            len(app.get("form_data", {})),
            app.get("created_at", ""),
            app.get("updated_at", ""),
            app.get("submitted_at", ""),
            app.get("confirmed_at", ""),
        ])
    
    output.seek(0)
    filename = f"applications_with_documents_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# =============================================================================
# Scraper config — super-admin management of per-tenant crawler settings.
#
# The crawler itself runs out-of-process (see backend/crawler/ + CLAUDE.md).
# These endpoints expose the same surface as `python -m crawler.main` so the
# dashboard can drive everything via HTTP. The "run now" endpoint kicks off
# an in-process FastAPI background task — fine for the rare manual trigger,
# but bulk/periodic crawling should still happen via cron + the CLI.
# =============================================================================

from fastapi import BackgroundTasks  # noqa: E402


class ScraperConfigUpdate(BaseModel):
    """All fields optional — only what's sent is applied. Unspecified fields
    retain their stored value or fall back to defaults (see crawler/config.py)."""
    enabled: Optional[bool] = None
    seed_urls: Optional[List[str]] = None
    allowed_domains: Optional[List[str]] = None
    max_depth: Optional[int] = None
    max_pages: Optional[int] = None
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None
    respect_robots: Optional[bool] = None
    use_sitemap: Optional[bool] = None
    fetch_timeout_seconds: Optional[int] = None
    fetch_delay_ms: Optional[int] = None
    concurrency: Optional[int] = None
    use_playwright: Optional[bool] = None
    user_agent: Optional[str] = None
    schedule_cron: Optional[str] = None


async def _company_exists(db, company_id: str) -> bool:
    return await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1}) is not None


@router.get("/scrapers")
async def list_scrapers(payload: dict = Depends(verify_super_admin)):
    """List scraper configs across all tenants (with last-run summary cached)."""
    db = await get_database()
    rows = await db.scraper_config.find({}, {"_id": 0}).to_list(500)
    # Join company names for the dashboard
    company_ids = [r["company_id"] for r in rows if r.get("company_id")]
    if company_ids:
        company_docs = await db.companies.find(
            {"id": {"$in": company_ids}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(500)
        name_by_id = {c["id"]: c["name"] for c in company_docs}
    else:
        name_by_id = {}
    return {
        "scrapers": [
            {**r, "company_name": name_by_id.get(r.get("company_id"))}
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/scrapers/{company_id}")
async def get_scraper(
    company_id: str,
    soft_404: int = 0,
    payload: dict = Depends(verify_admin),
):
    """Get one tenant's scraper config. Returns 404 if no row exists yet,
    or 200 + ``{exists: false}`` when called with ``?soft_404=1`` (UI uses
    this to keep the DevTools console clean on the expected no-row path)."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    doc = await db.scraper_config.find_one({"company_id": company_id}, {"_id": 0})
    if not doc:
        if soft_404:
            return {"exists": False, "company_id": company_id}
        raise HTTPException(
            status_code=404,
            detail="No scraper_config for this tenant yet — PUT to create one.",
        )
    return doc


@router.put("/scrapers/{company_id}")
async def upsert_scraper(
    company_id: str,
    update: ScraperConfigUpdate,
    payload: dict = Depends(verify_admin),
):
    """Create or update a tenant's scraper config. Only fields present in the
    request body are written — others retain their stored value."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    from crawler.config import upsert_config

    # Strip None values so we only persist what the caller actually sent.
    fields = {k: v for k, v in update.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        doc = await upsert_config(company_id, **fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return doc


@router.post("/scrapers/{company_id}/run")
async def run_scraper_now(
    company_id: str,
    background_tasks: BackgroundTasks,
    http_request: Request,
    payload: dict = Depends(verify_admin),
):
    """Trigger an immediate crawl for a tenant.

    Returns immediately. The crawl runs in a FastAPI background task — fine
    for the rare manual trigger, but periodic crawling should go through the
    deployed cron + `python -m crawler.main run` (which runs out-of-process).
    """
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    cfg = await db.scraper_config.find_one({"company_id": company_id}, {"_id": 0})
    if not cfg:
        raise HTTPException(
            status_code=400,
            detail="No scraper_config exists for this tenant — create one first via PUT /scrapers/{company_id}.",
        )
    if not cfg.get("enabled", True):
        raise HTTPException(status_code=400, detail="Scraper is disabled for this tenant.")
    if not cfg.get("seed_urls"):
        raise HTTPException(status_code=400, detail="No seed_urls configured.")

    from crawler.runner import run_crawl

    # Fire-and-forget; the runner writes its own crawler_runs row + summary.
    # Caller polls GET /scrapers/{company_id}/runs to see progress.
    trigger_label = "super_admin_manual" if payload.get("user_type") == "super_admin" else "local_admin_manual"
    background_tasks.add_task(run_crawl, company_id, trigger_label)

    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="scraper_run_triggered",
        user_id=payload.get("user_id"),
        user_type=payload.get("user_type"),
        resource_type="scraper_config",
        resource_id=company_id,
        company_id=company_id,
        metadata={"trigger": trigger_label, "seed_count": len(cfg.get("seed_urls", []))},
        ip_address=http_request.client.host if http_request.client else None,
    )

    return {
        "success": True,
        "message": "Crawl triggered. Poll /scrapers/{company_id}/runs for status.",
        "company_id": company_id,
    }


@router.get("/scrapers/{company_id}/runs")
async def list_scraper_runs(
    company_id: str,
    limit: int = 20,
    payload: dict = Depends(verify_admin),
):
    """Recent crawl runs for a tenant, newest first."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    runs = await db.crawler_runs.find(
        {"company_id": company_id},
        {"_id": 0},
    ).sort("started_at", -1).limit(min(limit, 200)).to_list(min(limit, 200))
    return {"runs": runs, "count": len(runs)}


@router.get("/scrapers/{company_id}/runs/{run_id}")
async def get_scraper_run(
    company_id: str,
    run_id: str,
    payload: dict = Depends(verify_admin),
):
    """Single run detail including live frontier breakdown."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    run = await db.crawler_runs.find_one(
        {"company_id": company_id, "run_id": run_id}, {"_id": 0}
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    from crawler import frontier as _frontier
    stats = await _frontier.run_stats(run_id)
    return {**run, "frontier_now": stats}


@router.get("/scrapers/{company_id}/runs/{run_id}/pages")
async def list_scraper_run_pages(
    company_id: str,
    run_id: str,
    payload: dict = Depends(verify_admin),
):
    """Per-page results for a run: status, http_status, attempts, and a
    processing summary (chunk count, keywords, summary, embedding dim). Raw
    HTML and full chunk text are omitted here — fetch a single page for those."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    rows = await db.crawler_pages.find(
        {"company_id": company_id, "run_id": run_id},
        {"_id": 0, "raw_html": 0, "extracted_text": 0, "processing.chunks": 0, "processing.log": 0},
    ).sort([("depth", 1), ("url", 1)]).to_list(1000)
    return {"pages": rows, "count": len(rows)}


@router.get("/scrapers/{company_id}/pages/{page_id}")
async def get_scraper_page(
    company_id: str,
    page_id: str,
    payload: dict = Depends(verify_admin),
):
    """Full per-page record including raw HTML, extracted text, all chunks and
    the processing log. Tenant-scoped."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    page = await db.crawler_pages.find_one(
        {"company_id": company_id, "id": page_id}, {"_id": 0}
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


# =============================================================================
# Notifications — super-admin config for all platform notification scenarios.
# The scenario catalog lives in services.notification_registry; per-scenario
# overrides in `notification_settings`; deliveries in `notification_log`.
# =============================================================================

class NotificationSettingUpdate(BaseModel):
    enabled:          Optional[bool] = None
    recipients:       Optional[List[str]] = None
    custom_emails:    Optional[List[str]] = None
    subject:          Optional[str] = None
    body:             Optional[str] = None
    params:           Optional[Dict[str, Any]] = None
    cooldown_minutes: Optional[int] = None


@router.get("/notifications/scenarios")
async def list_notification_scenarios(payload: dict = Depends(verify_super_admin)):
    """Full catalog: scenario metadata (grouped by category) merged with the
    current stored settings, so the UI can render one editable card each."""
    from services import notification_registry as reg
    from services.notification_dispatcher import list_settings
    settings = await list_settings()
    scenarios = []
    for s in reg.SCENARIOS:
        scenarios.append({
            "key": s.key, "name": s.name, "description": s.description,
            "category": s.category, "scope": s.scope, "severity": s.severity,
            "available_recipients": reg.ROLE_CHOICES,
            "setting": settings.get(s.key, {}),
        })
    return {
        "categories": [{"key": k, "label": v} for k, v in reg.CATEGORIES],
        "roles": reg.ROLE_CHOICES,
        "scenarios": scenarios,
    }


@router.put("/notifications/settings/{scenario_key}")
async def update_notification_setting(
    scenario_key: str,
    body: NotificationSettingUpdate,
    payload: dict = Depends(verify_super_admin),
):
    from services.notification_dispatcher import update_setting
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        merged = await update_setting(scenario_key, fields, updated_by=payload.get("user_id"))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"scenario_key": scenario_key, "setting": merged}


@router.post("/notifications/test/{scenario_key}")
async def test_notification(
    scenario_key: str,
    email: str = Query(..., description="Address to send the test to"),
    payload: dict = Depends(verify_super_admin),
):
    """Send a test using the scenario's sample context to one address,
    bypassing the enabled/cooldown gates."""
    from services import notification_registry as reg
    from services.notification_dispatcher import notify
    s = reg.get_scenario(scenario_key)
    if not s:
        raise HTTPException(status_code=404, detail="Unknown scenario")
    res = await notify(
        scenario_key, context=dict(s.sample_context),
        force=True, recipients_override=[email],
    )
    return {"scenario_key": scenario_key, "result": res}


@router.post("/notifications/run-job/{job}")
async def run_notification_job(job: str, payload: dict = Depends(verify_super_admin)):
    """Run a periodic notification job now (usage_checks, stuck_pending,
    usage_digest, activity_digest). Intended for cron; exposed for manual
    trigger + testing. Emits notifications per the job's findings."""
    from services.notification_jobs import JOBS
    fn = JOBS.get(job)
    if not fn:
        raise HTTPException(status_code=404, detail=f"Unknown job. Options: {sorted(JOBS)}")
    result = await fn()
    return {"job": job, "result": result}


@router.get("/notifications/log")
async def notification_log(
    scenario_key: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    payload: dict = Depends(verify_super_admin),
):
    db = await get_database()
    query: dict = {}
    if scenario_key:
        query["scenario_key"] = scenario_key
    if status:
        query["status"] = status
    rows = await db.notification_log.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"log": rows, "count": len(rows)}


# =============================================================================
# Tenant bot config — super-admin management of bot identity, contact info,
# system prompt template, languages, branding, and fallback responses.
#
# Route code (whatsapp/facebook/consular) reads from the same store via
# services.bot_config.get_bot_config(), which has a 60s TTL cache. Writes
# here invalidate that cache so changes are visible on the next request.
#
# Seeded for the default tenant by migration 0005. Other tenants get a row
# the first time the super-admin saves config for them via the PUT below.
# =============================================================================


class _ContactUpdate(BaseModel):
    address:         Optional[str] = None
    phone:           Optional[str] = None
    emergency_phone: Optional[str] = None
    email:           Optional[str] = None
    website:         Optional[str] = None
    office_hours:    Optional[str] = None
    consular_hours:  Optional[str] = None


class _BrandingUpdate(BaseModel):
    primary_color:   Optional[str] = None
    secondary_color: Optional[str] = None
    logo_url:        Optional[str] = None
    favicon_url:     Optional[str] = None


class _KnowledgeSourcesUpdate(BaseModel):
    """Per-tenant scrape sources used by ``knowledge_scraper``."""
    primary_url:    Optional[str]       = None
    sub_pages:      Optional[List[str]] = None
    secondary_urls: Optional[List[str]] = None


class _SecurityConfigUpdate(BaseModel):
    """Per-tenant security & limits — OTP, session, upload caps.

    Use 0 / empty string / empty list to revert to platform defaults
    (see :py:meth:`services.bot_config.BotConfig.security` for resolution).
    """
    otp_ttl_minutes:            Optional[int]       = None
    otp_max_attempts:           Optional[int]       = None
    otp_lockout_minutes:        Optional[int]       = None
    otp_dev_value:              Optional[str]       = None
    session_inactivity_minutes: Optional[int]       = None
    client_inactivity_minutes:  Optional[int]       = None
    upload_max_bytes:           Optional[int]       = None
    upload_max_pdf_pages:       Optional[int]       = None
    upload_allowed_mime_types:  Optional[List[str]] = None


class _PdfBrandingUpdate(BaseModel):
    """PDF-specific colours/strings used by services.pdf_service.

    All fields optional — missing keys fall back to neutral defaults inside
    pdf_service. ``stripe_colors`` is the optional top-of-page accent stripes
    (e.g. a flag tricolour); leave empty for a single-colour brand.
    """
    header_color:    Optional[str] = None
    accent_color:    Optional[str] = None
    highlight_color: Optional[str] = None
    stripe_colors:   Optional[List[str]] = None
    notice_bg:       Optional[str] = None
    muted_text:      Optional[str] = None
    border:          Optional[str] = None
    footer_text:     Optional[str] = None
    notice_text:     Optional[str] = None


class _LanguageEntry(BaseModel):
    """One supported-language row on bot_config.supported_languages.

    ``code`` is the language ID used internally (``en``, ``hi``, ``zu`` etc.).
    ``name`` is the display label shown in the language picker — supply it
    in the target language if you want a native-script label.
    ``native_name`` (optional) is the script-native label used by the
    WhatsApp menu when different from the English display name
    (e.g. ``Hindi`` vs ``हिंदी``).
    ``aliases`` (optional) is extra phrases the language-switch detector
    should recognise ("hindi", "हिन्दी", "हिंदी" → ``hi``).
    ``bcp47_code`` (optional) is the BCP-47 code passed to browser TTS /
    Whisper (e.g. ``en-GB``, ``hi-IN``). Defaults to ``code`` if blank.
    ``flag`` (optional) is a single emoji shown in the picker.
    ``tts_voice_preference`` (optional) is one of ``female``, ``male``,
    ``neutral`` — used by browser TTS voice selection.
    ``tts_voice`` (optional) is the explicit voice ID for backend TTS
    (e.g. OpenAI ``nova`` / ``shimmer`` / ``alloy``).
    ``script_hint`` (optional) is appended to the WhatsApp / web system
    prompt to force a specific script (e.g. "MUST write in Devanagari").
    """
    code: str
    name: str
    native_name:           Optional[str]       = ""
    aliases:               Optional[List[str]] = None
    bcp47_code:            Optional[str]       = ""
    flag:                  Optional[str]       = ""
    tts_voice_preference:  Optional[str]       = ""
    tts_voice:             Optional[str]       = ""
    script_hint:           Optional[str]       = ""


class _AdvisoryEntry(BaseModel):
    """One advisory card shown above the chat. Operators add these via the
    Bot Config tab; the widget renders them on every fresh session."""
    model_config = {"extra": "allow"}  # keep room for future fields without a schema change

    id:      Optional[str] = None
    type:    Optional[str] = "info"   # info | warning | error — drives styling
    title:   Optional[str] = ""
    content: Optional[str] = ""
    active:  Optional[bool] = True


class TenantBotConfigUpdate(BaseModel):
    """Partial update — only fields actually sent are persisted. Nested dicts
    (`contact`, `branding`) are deep-merged with the stored values so a PUT
    with just `{"contact": {"phone": "..."}}` doesn't blank out the email.
    Lists (`supported_languages`, `advisories`) and `fallback_responses`
    are replaced wholesale when provided."""
    bot_name:                Optional[str] = None
    bot_avatar_url:          Optional[str] = None
    org_name:                Optional[str] = None
    org_short_name:          Optional[str] = None
    header_tagline:          Optional[str] = None
    footer_copy:             Optional[str] = None
    advisories:              Optional[List[_AdvisoryEntry]] = None
    contact:                 Optional[_ContactUpdate] = None
    phone_country_code:      Optional[str] = None
    system_prompt_template:  Optional[str] = None
    supported_languages:     Optional[List[_LanguageEntry]] = None
    default_language:        Optional[str] = None
    branding:                Optional[_BrandingUpdate] = None
    pdf_branding:            Optional[_PdfBrandingUpdate] = None
    knowledge_sources:       Optional[_KnowledgeSourcesUpdate] = None
    # Phase-5 additions: tenant KB taxonomy + OCR heuristics. Loose dict
    # types because both have small free-form schemas; the backend reader
    # in services.bot_config + services.knowledge_service does the
    # validation and platform-default fallback at consumption time.
    knowledge_categories:    Optional[List[str]] = None
    ocr_patterns:            Optional[Dict[str, Any]] = None
    intent_keywords:         Optional[Dict[str, List[str]]] = None
    flow_keywords:           Optional[Dict[str, List[str]]] = None
    escalation_rules:        Optional[Dict[str, Any]] = None
    security_config:         Optional[_SecurityConfigUpdate] = None
    fallback_responses:      Optional[Dict[str, str]] = None
    features:                Optional[Dict[str, bool]] = None


def _strip_none(d: Dict[str, Any]) -> Dict[str, Any]:
    """Drop top-level None values so the PUT body only carries what the
    caller intended to change."""
    return {k: v for k, v in d.items() if v is not None}


@router.get("/bot-config")
async def list_bot_configs(payload: dict = Depends(verify_super_admin)):
    """List bot configs across all tenants (joined with company names for UI)."""
    db = await get_database()
    rows = await db.tenant_bot_config.find({}, {"_id": 0}).to_list(500)
    company_ids = [r["company_id"] for r in rows if r.get("company_id")]
    if company_ids:
        companies = await db.companies.find(
            {"id": {"$in": company_ids}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(500)
        name_by_id = {c["id"]: c["name"] for c in companies}
    else:
        name_by_id = {}
    return {
        "bot_configs": [
            {**r, "company_name": name_by_id.get(r.get("company_id"))}
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/bot-config/{company_id}")
async def get_bot_config_endpoint(
    company_id: str,
    soft_404: int = 0,
    payload: dict = Depends(verify_admin),
):
    """Get one tenant's bot config — raw stored row only (404 if none).

    For the *effective* config (with defaults merged in), use the bot_config
    service from inside Python code; this endpoint exposes the raw row so
    the super-admin UI can show "what's actually configured" vs "what's
    defaulted".

    Pass ``?soft_404=1`` to receive 200 + ``{exists: false}`` instead of
    a 404 when no row exists — the UI uses this to avoid the browser's
    automatic "Failed to load resource" DevTools warning on the expected
    no-row-yet path.
    """
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    doc = await db.tenant_bot_config.find_one(
        {"company_id": company_id}, {"_id": 0}
    )
    if not doc:
        if soft_404:
            return {"exists": False, "company_id": company_id}
        raise HTTPException(
            status_code=404,
            detail="No tenant_bot_config for this tenant yet — PUT to create one.",
        )
    return doc


@router.put("/bot-config/{company_id}")
async def upsert_bot_config(
    company_id: str,
    update: TenantBotConfigUpdate,
    http_request: Request,
    payload: dict = Depends(verify_admin),
):
    """Create or partial-update a tenant's bot config. Returns the stored row.

    Behaviour:
      - Top-level fields set to None are skipped (preserve existing).
      - `contact` and `branding` are deep-merged: sending one nested field
        does NOT clear the others.
      - `supported_languages`, `fallback_responses` are replaced wholesale
        when provided (None to skip).
      - Cache is invalidated so the next request sees the change.
    """
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    incoming = _strip_none(update.model_dump())
    if not incoming:
        raise HTTPException(status_code=400, detail="No fields to update")

    existing = await db.tenant_bot_config.find_one(
        {"company_id": company_id}, {"_id": 0}
    ) or {}

    # Deep-merge nested dicts so PUT-ing one nested field doesn't blank peers.
    set_fields: Dict[str, Any] = {}
    for key, val in incoming.items():
        if key in ("contact", "branding", "pdf_branding", "knowledge_sources", "ocr_patterns", "security_config", "intent_keywords", "flow_keywords", "escalation_rules") and isinstance(val, dict):
            merged = {**(existing.get(key) or {}), **_strip_none(val)}
            set_fields[key] = merged
        else:
            set_fields[key] = val

    now = datetime.now(timezone.utc).isoformat()
    set_fields["updated_at"] = now

    await db.tenant_bot_config.update_one(
        {"company_id": company_id},
        {
            "$set":         set_fields,
            "$setOnInsert": {"company_id": company_id, "created_at": now, "created_by": "super_admin"},
        },
        upsert=True,
    )

    # Drop the bot_config TTL cache so the next chat request sees the change.
    from services.bot_config import invalidate_cache
    invalidate_cache(company_id)

    await _audit_safe(
        db,
        category=AuditCategory.DATA_MODIFICATION,
        action="upsert_bot_config",
        user_id=payload.get("user_id"),
        user_type=payload.get("user_type"),
        resource_type="tenant_bot_config",
        resource_id=company_id,
        company_id=company_id,
        new_value={k: incoming[k] for k in list(incoming.keys())[:10]},  # cap, audit shouldn't bloat
        ip_address=http_request.client.host if http_request.client else None,
    )

    return await db.tenant_bot_config.find_one(
        {"company_id": company_id}, {"_id": 0}
    )


# =====================================================================
# TENANT SERVICES (Sprint 4D) — CRUD over the `tenant_services` collection
# that drives the application_flow state machine.
# =====================================================================

_VALID_CATEGORIES = {"TYPE_A", "TYPE_B", "INFO"}
# Mirrors the regex used by tenant.validate_company_id — keys must be
# url-safe and stable since they appear in tracking IDs (PASSPORT-...).
_SERVICE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


class _ServiceField(BaseModel):
    """One step in the `state=collecting` walk.

    ``type`` (default ``"input"``) selects the behaviour — see
    ``services.flow_steps`` for the full schema:

      * ``input``       — ask the user the ``question``, validate, store.
      * ``conditional`` — evaluate ``condition`` against prior answers and
        either continue or short-circuit to docs upload. No user prompt.
      * ``api_call``    — make an HTTP request defined by ``api_config``,
        optionally store the response under ``api_config.store_response_as``.

    ``key`` is always required (it's the form-data key for inputs and the
    identifier in logs for non-input steps)."""
    key:        str
    type:       Optional[str]              = "input"
    question:   Optional[str]              = None
    # Display + matching metadata used by PDF rendering and the
    # ``correct <field>:`` command. All optional.
    display_label: Optional[str]           = None    # PDF / review label override
    aliases:       Optional[List[str]]     = None    # user-phrase synonyms for this key
    # Validation rules — applied by services.application_flow._validate_field.
    # Use ``validation_type`` (one of ``name|date|email|phone|passport|free_text``)
    # for the common patterns, or pass a custom ``validation_regex`` for
    # tenant-specific formats. ``error_message`` is shown when validation fails.
    validation_type:    Optional[str]      = None
    validation_regex:   Optional[str]      = None
    validation_min:     Optional[int]      = None
    validation_max:     Optional[int]      = None
    error_message:      Optional[str]      = None
    required:           Optional[bool]     = True
    # conditional config (only used when type == "conditional")
    condition:  Optional[Dict[str, Any]]   = None
    on_match:   Optional[str]              = None  # "continue" | "skip_to_docs"
    on_no_match: Optional[str]             = None
    # api_call config (only used when type == "api_call")
    api_config: Optional[Dict[str, Any]]   = None

    model_config = {"extra": "allow"}  # don't reject forward-compatible extras


class _ServiceSubtype(BaseModel):
    """One ramification of a service — e.g. for a ``passport`` service the
    subtypes might be ``lost / damaged / emergency / urgent``. When the
    user's query matches any of ``keywords``, the subtype's description
    + extra_docs are prepended to the service info card. Used by
    :py:func:`services.application_flow._detect_subtype`."""
    key:         str
    label:       Optional[str]       = None
    description: Optional[str]       = None
    extra_docs:  Optional[List[str]] = None
    keywords:    Optional[List[str]] = None
    model_config = {"extra": "allow"}


class TenantServiceCreate(BaseModel):
    """Required fields to register a new service on a tenant."""
    service_key:   str
    name:          str
    description:   Optional[str]              = ""
    documents:     Optional[List[str]]        = None
    fields:        Optional[List[_ServiceField]] = None
    subtypes:      Optional[List[_ServiceSubtype]] = None
    category:      Optional[str]              = "TYPE_A"
    external_url:  Optional[str]              = None
    emoji:         Optional[str]              = ""
    keywords:      Optional[List[str]]        = None
    enabled:       Optional[bool]             = True
    display_order: Optional[int]              = None
    # Optional reminder shown to the user after they confirm an application.
    # Empty/omitted → no extra bot message. Use this for service-specific
    # post-submit instructions (e.g. "visit in person to surrender passport").
    post_confirm_message: Optional[str] = ""
    # Optional workflow hooks. See `services.service_hooks` for the
    # rule schema. Loose typing because the rule format is free-form
    # JSON; validation happens at evaluation time.
    hooks: Optional[Dict[str, List[Dict[str, Any]]]] = None
    # INFO services carry a typed sections payload + optional CTA.
    # Free-form dict; the consumer renderer falls back to defaults on
    # malformed shapes so a bad blob never breaks the chat.
    info_content: Optional[Dict[str, Any]] = None


class TenantServiceUpdate(BaseModel):
    """Partial update — only fields actually sent are persisted. Lists
    (`documents`, `fields`, `subtypes`, `keywords`) are replaced wholesale
    when provided so the operator has a clear "set this exact list"
    semantic."""
    name:          Optional[str]              = None
    description:   Optional[str]              = None
    documents:     Optional[List[str]]        = None
    fields:        Optional[List[_ServiceField]] = None
    subtypes:      Optional[List[_ServiceSubtype]] = None
    category:      Optional[str]              = None
    external_url:  Optional[str]              = None
    emoji:         Optional[str]              = None
    keywords:      Optional[List[str]]        = None
    enabled:       Optional[bool]             = None
    display_order: Optional[int]              = None
    post_confirm_message: Optional[str]       = None
    hooks:                Optional[Dict[str, List[Dict[str, Any]]]] = None
    info_content:         Optional[Dict[str, Any]] = None


def _validate_service_payload(payload: Dict[str, Any]) -> None:
    """Shared validation for create and update bodies. Raises 400 on bad data."""
    if "category" in payload and payload["category"] not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"category must be one of {sorted(_VALID_CATEGORIES)}",
        )
    if payload.get("category") == "TYPE_B" and not payload.get("external_url") and "external_url" in payload:
        # Explicitly set to None on a TYPE_B service makes no sense; soft-warn
        # by rejecting. Omit the field entirely if you intend to leave the
        # existing value alone (PUT is partial).
        raise HTTPException(
            status_code=400,
            detail="TYPE_B services must include an external_url (the redirect target).",
        )
    fields = payload.get("fields")
    if fields is not None:
        from services.flow_steps import validate_field_definition
        seen = set()
        for f in fields:
            if not isinstance(f, dict):
                raise HTTPException(status_code=400, detail="Each field must be an object.")
            k = f.get("key")
            if not k:
                raise HTTPException(status_code=400, detail="Every field needs a non-empty key.")
            if k in seen:
                raise HTTPException(status_code=400, detail=f"Duplicate field key: {k!r}")
            seen.add(k)
            err = validate_field_definition(f)
            if err:
                raise HTTPException(status_code=400, detail=err)


@router.get("/services")
async def list_all_services(payload: dict = Depends(verify_super_admin)):
    """List tenant_services across all tenants (joined with company names)."""
    db = await get_database()
    rows = await db.tenant_services.find({}, {"_id": 0}).sort(
        [("company_id", 1), ("display_order", 1)]
    ).to_list(2000)
    company_ids = list({r["company_id"] for r in rows if r.get("company_id")})
    if company_ids:
        companies = await db.companies.find(
            {"id": {"$in": company_ids}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(500)
        name_by_id = {c["id"]: c["name"] for c in companies}
    else:
        name_by_id = {}
    return {
        "services": [
            {**r, "company_name": name_by_id.get(r.get("company_id"))}
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/services/{company_id}")
async def list_tenant_services(
    company_id: str,
    include_disabled: bool = True,
    payload: dict = Depends(verify_admin),
):
    """List one tenant's services, ordered by display_order. By default
    includes disabled services so the operator can see the full catalogue;
    pass `include_disabled=false` for the chatbot's view.

    Local admins can only read their own tenant's catalogue (403 otherwise)."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    query: Dict[str, Any] = {"company_id": company_id}
    if not include_disabled:
        query["enabled"] = True
    rows = await db.tenant_services.find(query, {"_id": 0}).sort(
        "display_order", 1
    ).to_list(500)
    return {"services": rows, "count": len(rows)}


@router.get("/services/{company_id}/{service_key}")
async def get_tenant_service(
    company_id: str,
    service_key: str,
    payload: dict = Depends(verify_admin),
):
    """Get one service row by (company_id, service_key)."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    doc = await db.tenant_services.find_one(
        {"company_id": company_id, "service_key": service_key}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Service not found for this tenant")
    return doc


@router.post("/services/{company_id}", status_code=201)
async def create_tenant_service(
    company_id: str,
    body: TenantServiceCreate,
    http_request: Request,
    payload: dict = Depends(verify_admin),
):
    """Create a new service for a tenant. Fails 409 if (company_id, service_key)
    already exists — use PUT to modify. The compound unique index on
    `tenant_services` enforces this at the DB layer too."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    incoming = body.model_dump(exclude_none=False)
    service_key = (incoming.get("service_key") or "").strip()
    if not _SERVICE_KEY_RE.match(service_key):
        raise HTTPException(
            status_code=400,
            detail=(
                "service_key must be 2-41 chars, lower-case, start with a letter, "
                "and contain only [a-z0-9_]. It is embedded in tracking IDs and URLs."
            ),
        )
    _validate_service_payload(incoming)

    if await db.tenant_services.find_one(
        {"company_id": company_id, "service_key": service_key}, {"_id": 0, "service_key": 1}
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Service {service_key!r} already exists for this tenant — use PUT to update.",
        )

    # Default display_order to "next slot" so menus stay stable when the
    # caller doesn't specify one.
    if incoming.get("display_order") is None:
        last = await db.tenant_services.find(
            {"company_id": company_id}, {"_id": 0, "display_order": 1}
        ).sort("display_order", -1).limit(1).to_list(1)
        incoming["display_order"] = (last[0].get("display_order", -1) + 1) if last else 0

    now = datetime.now(timezone.utc).isoformat()
    doc: Dict[str, Any] = {
        "id":            str(uuid.uuid4()),
        "company_id":    company_id,
        "service_key":   service_key,
        "name":          incoming["name"],
        "description":   incoming.get("description") or "",
        "documents":     list(incoming.get("documents") or []),
        "fields":        list(incoming.get("fields") or []),
        "subtypes":      list(incoming.get("subtypes") or []),
        "category":      incoming.get("category") or "TYPE_A",
        "external_url":  incoming.get("external_url"),
        "emoji":         (incoming.get("emoji") or "").strip(),
        "keywords":      list(incoming.get("keywords") or []),
        "enabled":       bool(incoming.get("enabled", True)),
        "display_order": int(incoming["display_order"]),
        "post_confirm_message": (incoming.get("post_confirm_message") or "").strip(),
        "hooks":         dict(incoming.get("hooks") or {}),
        "info_content":  dict(incoming.get("info_content") or {"sections": [], "primary_action": None}),
        "created_at":    now,
        "updated_at":    now,
        "created_by":    payload.get("sub") or payload.get("user_type") or "admin",
    }
    await db.tenant_services.insert_one(doc)

    from services.service_registry import invalidate_cache
    invalidate_cache(company_id)

    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="create_tenant_service",
        user_id=payload.get("user_id"),
        user_type=payload.get("user_type"),
        resource_type="tenant_service",
        resource_id=f"{company_id}::{service_key}",
        company_id=company_id,
        new_value={"name": doc["name"], "category": doc["category"], "enabled": doc["enabled"]},
        ip_address=http_request.client.host if http_request.client else None,
    )

    return await db.tenant_services.find_one(
        {"company_id": company_id, "service_key": service_key}, {"_id": 0}
    )


@router.put("/services/{company_id}/{service_key}")
async def update_tenant_service(
    company_id: str,
    service_key: str,
    update: TenantServiceUpdate,
    http_request: Request,
    payload: dict = Depends(verify_admin),
):
    """Partial update — only fields actually sent are persisted. `documents`
    and `fields` are replaced wholesale when provided. Returns 404 if the
    service doesn't exist (use POST to create)."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    existing = await db.tenant_services.find_one(
        {"company_id": company_id, "service_key": service_key}, {"_id": 0}
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Service not found — POST to create.")

    incoming = _strip_none(update.model_dump())
    if not incoming:
        raise HTTPException(status_code=400, detail="No fields to update")
    # Run validation against the would-be merged state so a partial PUT
    # that flips TYPE_A → TYPE_B without external_url is caught.
    _validate_service_payload({**existing, **incoming})

    set_fields: Dict[str, Any] = dict(incoming)
    set_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    await db.tenant_services.update_one(
        {"company_id": company_id, "service_key": service_key},
        {"$set": set_fields},
    )

    from services.service_registry import invalidate_cache
    invalidate_cache(company_id)

    await _audit_safe(
        db,
        category=AuditCategory.DATA_MODIFICATION,
        action="update_tenant_service",
        user_id=payload.get("user_id"),
        user_type=payload.get("user_type"),
        resource_type="tenant_service",
        resource_id=f"{company_id}::{service_key}",
        company_id=company_id,
        old_value={k: existing.get(k) for k in incoming.keys()},
        new_value=incoming,
        ip_address=http_request.client.host if http_request.client else None,
    )

    return await db.tenant_services.find_one(
        {"company_id": company_id, "service_key": service_key}, {"_id": 0}
    )


@router.delete("/services/{company_id}/{service_key}")
async def delete_tenant_service(
    company_id: str,
    service_key: str,
    http_request: Request,
    payload: dict = Depends(verify_admin),
):
    """Hard-delete a service. Sessions mid-flow on this service will be
    abandoned with a friendly "no longer available" message on their next
    turn (handled by application_flow's graceful-degradation branch).

    Existing `applications` rows are NOT touched — they have `service_name`
    denormalised, so historical tracking lookups keep working."""
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()
    if not await _company_exists(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")

    result = await db.tenant_services.delete_one(
        {"company_id": company_id, "service_key": service_key}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Service not found")

    from services.service_registry import invalidate_cache
    invalidate_cache(company_id)

    await _audit_safe(
        db,
        category=AuditCategory.DATA_DELETION,
        action="delete_tenant_service",
        user_id=payload.get("user_id"),
        user_type=payload.get("user_type"),
        resource_type="tenant_service",
        resource_id=f"{company_id}::{service_key}",
        company_id=company_id,
        ip_address=http_request.client.host if http_request.client else None,
        severity=AuditSeverity.WARNING,
    )

    return {"deleted": True, "service_key": service_key, "company_id": company_id}


# =====================================================================
# MESSAGING CHANNEL MAPPINGS (Sprint 5) — routes inbound webhook traffic
# from WhatsApp / Facebook / ICS to the owning tenant. Without a mapping
# the resolver falls back to the env-var default tenant with a WARNING.
# =====================================================================

_VALID_CHANNEL_TYPES = {"whatsapp_twilio", "ics_waba", "facebook"}


class ChannelMappingUpsert(BaseModel):
    company_id: str
    metadata:   Optional[Dict[str, Any]] = None


@router.get("/channel-mappings")
async def list_channel_mappings_endpoint(
    channel_type: Optional[str] = None,
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_super_admin),
):
    """List all channel→tenant mappings. Optional ``?channel_type`` /
    ``?company_id`` filters scope the result. Joins on companies so the
    UI can show a human-readable tenant name."""
    from services.messaging_channel_resolver import list_channel_mappings
    rows = await list_channel_mappings(channel_type=channel_type, company_id=company_id)

    cids = list({r["company_id"] for r in rows if r.get("company_id")})
    if cids:
        db = await get_database()
        companies = await db.companies.find(
            {"id": {"$in": cids}}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(500)
        name_by_id = {c["id"]: c["name"] for c in companies}
    else:
        name_by_id = {}

    return {
        "mappings": [
            {**r, "company_name": name_by_id.get(r.get("company_id"))}
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/channel-mappings/{channel_type}/{external_id:path}")
async def get_channel_mapping(
    channel_type: str,
    external_id: str,
    payload: dict = Depends(verify_super_admin),
):
    """Look up one mapping by ``(channel_type, external_id)``. Returns 404
    if not configured — at runtime the resolver would fall back to the
    default tenant for the same key."""
    if channel_type not in _VALID_CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"channel_type must be one of {sorted(_VALID_CHANNEL_TYPES)}",
        )
    db = await get_database()
    row = await db.messaging_channel_map.find_one(
        {"channel_type": channel_type, "external_id": external_id}, {"_id": 0}
    )
    if not row:
        raise HTTPException(status_code=404, detail="Channel mapping not configured")
    return row


@router.put("/channel-mappings/{channel_type}/{external_id:path}")
async def upsert_channel_mapping(
    channel_type: str,
    external_id: str,
    body: ChannelMappingUpsert,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Create or overwrite a (channel_type, external_id) → company_id
    mapping. Invalidates the resolver's per-process cache so the change
    takes effect on the very next inbound webhook."""
    if channel_type not in _VALID_CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"channel_type must be one of {sorted(_VALID_CHANNEL_TYPES)}",
        )
    db = await get_database()
    if not await _company_exists(db, body.company_id):
        raise HTTPException(status_code=404, detail=f"company_id {body.company_id!r} not found")

    from services.messaging_channel_resolver import map_channel_to_company
    await map_channel_to_company(
        channel_type, external_id, body.company_id, metadata=body.metadata
    )
    # Sprint 12 — audit channel-mapping changes since they route real
    # inbound traffic to a tenant. Severity=WARNING because mis-routing
    # has cross-tenant blast radius.
    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="upsert_channel_mapping",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="channel_mapping",
        resource_id=f"{channel_type}::{external_id}",
        company_id=body.company_id,
        new_value={"channel_type": channel_type, "external_id": external_id, "company_id": body.company_id},
        ip_address=http_request.client.host if http_request.client else None,
        severity=AuditSeverity.WARNING,
    )
    return await db.messaging_channel_map.find_one(
        {"channel_type": channel_type, "external_id": external_id}, {"_id": 0}
    )


@router.delete("/channel-mappings/{channel_type}/{external_id:path}")
async def delete_channel_mapping_endpoint(
    channel_type: str,
    external_id: str,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Remove a channel mapping. After deletion the resolver falls back
    to ``config.COMPANY_ID`` for that channel (with a WARNING log on
    every inbound message — create a new mapping to silence it)."""
    if channel_type not in _VALID_CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"channel_type must be one of {sorted(_VALID_CHANNEL_TYPES)}",
        )
    from services.messaging_channel_resolver import delete_channel_mapping
    deleted = await delete_channel_mapping(channel_type, external_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Channel mapping not found")
    db = await get_database()
    await _audit_safe(
        db,
        category=AuditCategory.DATA_DELETION,
        action="delete_channel_mapping",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="channel_mapping",
        resource_id=f"{channel_type}::{external_id}",
        ip_address=http_request.client.host if http_request.client else None,
        severity=AuditSeverity.WARNING,
    )
    return {"deleted": True, "channel_type": channel_type, "external_id": external_id}


# =====================================================================
# PLATFORM CONFIG (Sprint 4 — Phase 4)
# Singleton ops-level tuning: cache TTLs, crawler interval, WhatsApp
# channel limits, frontend HTTP timeouts. Edited via the "Platform
# Settings" tab in the super-admin UI; consumed across the backend via
# services.platform_config.get().
# =====================================================================


@router.get("/platform-config")
async def get_platform_config(payload: dict = Depends(verify_super_admin)):
    """Return the resolved platform_config dict — DB → env → defaults
    merged. Also returns `defaults` and `env_overrides` so the UI can
    show "currently using default" hints to the operator."""
    from services.platform_config import ensure_loaded, DEFAULTS, _ENV_OVERRIDES
    resolved = await ensure_loaded()
    return {
        "config":        resolved,
        "defaults":      DEFAULTS,
        "env_overrides": dict(_ENV_OVERRIDES),
    }


@router.put("/platform-config")
async def put_platform_config(
    body: Dict[str, Any],
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Upsert platform_config. ``body`` is a shallow patch of the keys
    in :py:attr:`services.platform_config.DEFAULTS`. Unknown keys are
    persisted as-is (forward-compatibility). Invalidates the in-process
    cache after the write."""
    from services.platform_config import save, DEFAULTS
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    # Light validation: numeric fields stay numeric, lists stay lists.
    # Type errors here yield a clear 400 instead of a confusing runtime
    # surprise downstream.
    patch: Dict[str, Any] = {}
    for k, v in body.items():
        if k in DEFAULTS:
            dflt = DEFAULTS[k]
            if isinstance(dflt, bool) and not isinstance(v, bool):
                raise HTTPException(status_code=400, detail=f"{k} must be a boolean")
            if isinstance(dflt, int) and not isinstance(dflt, bool) and not isinstance(v, int):
                raise HTTPException(status_code=400, detail=f"{k} must be an integer")
            if isinstance(dflt, list) and not isinstance(v, list):
                raise HTTPException(status_code=400, detail=f"{k} must be a list")
        patch[k] = v

    resolved = await save(patch)
    db = await get_database()
    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="update_platform_config",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="platform_config",
        resource_id="platform",
        new_value={k: v for k, v in patch.items() if not k.endswith("_value")},
        ip_address=http_request.client.host if http_request.client else None,
        severity=AuditSeverity.WARNING,
    )
    return {"config": resolved}


# ─── Platform model registry ────────────────────────────────────────────────
# Replaces the hardcoded MODEL_MAP + _PRICING. Super-admin CRUD over the
# ``platform_models`` collection; tenants are then assigned an allowlist
# via ``PUT /companies/{id}/models``. See migration 0011 for the schema
# and ``services.model_registry`` for the read path.

_MODEL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._\-]{0,63}$", re.IGNORECASE)


class _ModelPricing(BaseModel):
    input_per_1m_usd:  float
    output_per_1m_usd: float


class _ModelCapabilities(BaseModel):
    vision:     Optional[bool] = None
    streaming:  Optional[bool] = None
    max_tokens: Optional[int]  = None
    model_config = {"extra": "allow"}


class PlatformModelCreate(BaseModel):
    key:          str
    display_name: str
    provider:     str
    api_model:    str
    description:  Optional[str]              = ""
    pricing:      _ModelPricing
    capabilities: Optional[_ModelCapabilities] = None
    enabled:      Optional[bool]             = True


class PlatformModelUpdate(BaseModel):
    display_name: Optional[str]              = None
    provider:     Optional[str]              = None
    api_model:    Optional[str]              = None
    description:  Optional[str]              = None
    pricing:      Optional[_ModelPricing]    = None
    capabilities: Optional[_ModelCapabilities] = None
    enabled:      Optional[bool]             = None


def _strip_none_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _sdk_installed(module_name: str) -> bool:
    """Best-effort runtime check: try importing the provider SDK. True
    if importable, False if missing. Used by the providers/status
    endpoint and the model-create validator so we never let a
    super-admin register a provider that the runtime can't actually
    talk to."""
    import importlib.util
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


# Single source of truth for provider runtime metadata. Adding a new
# provider means: list it here, install its SDK, add its key to .env,
# and wire its dispatch in LlmChat.
_PROVIDER_SPECS = [
    {
        "provider":         "openai",
        "label":            "OpenAI",
        "env_var":          "OPENAI_API_KEY",
        "fallback_env_var": "EMERGENT_LLM_KEY",
        "sdk_module":       "openai",
        "wired_in_llmchat": True,
        "install_hint":     "Already shipped. Set OPENAI_API_KEY (or EMERGENT_LLM_KEY) in backend/.env.",
    },
    {
        "provider":         "google",
        "label":            "Google (Gemini)",
        "env_var":          "GOOGLE_API_KEY",
        "fallback_env_var": "GEMINI_API_KEY",
        "sdk_module":       "google.genai",
        "wired_in_llmchat": True,
        "install_hint":     "pip install google-genai · set GOOGLE_API_KEY in backend/.env",
    },
    {
        "provider":         "anthropic",
        "label":            "Anthropic (Claude)",
        "env_var":          "ANTHROPIC_API_KEY",
        "fallback_env_var": None,
        "sdk_module":       "anthropic",
        "wired_in_llmchat": False,
        "install_hint":     "pip install anthropic · set ANTHROPIC_API_KEY · wire provider dispatch in LlmChat",
    },
]


def _resolve_provider_status() -> List[Dict[str, Any]]:
    """Compute live status for each known provider. ``ready`` = all
    three conditions hold (env key set, SDK importable, LlmChat
    dispatch wired). Used by the GET endpoint AND by the create-model
    validator so the two answers can't drift."""
    import os
    out = []
    for spec in _PROVIDER_SPECS:
        primary    = bool(os.environ.get(spec["env_var"]))
        fallback   = bool(os.environ.get(spec["fallback_env_var"])) if spec["fallback_env_var"] else False
        configured = primary or fallback
        sdk_ok     = _sdk_installed(spec["sdk_module"])
        wired      = spec["wired_in_llmchat"]
        out.append({
            **spec,
            "configured":        configured,
            "sdk_installed":     sdk_ok,
            "runtime_supported": wired and sdk_ok,
            "matched_env_var":   spec["env_var"] if primary else (spec["fallback_env_var"] if fallback else None),
            "ready":             configured and wired and sdk_ok,
        })
    return out


@router.get("/providers/status")
async def get_provider_status(payload: dict = Depends(verify_super_admin)):
    """Reports which LLM providers are runtime-ready right now.

    A provider is ``ready`` when ALL three are true:
      * env key set (``configured``)
      * SDK importable in the running venv (``sdk_installed``)
      * dispatch logic wired in ``LlmChat`` (``runtime_supported``)

    The Models tab uses this to gate the Add Model dialog — operators
    can only register a model whose provider is fully ready, so we
    don't end up with rows that 500 at chat time.
    """
    return {"providers": _resolve_provider_status()}


@router.get("/models")
async def list_platform_models(payload: dict = Depends(verify_super_admin)):
    """All registered models, ordered by provider + display_name.
    Disabled rows are included so the operator can edit them in the
    super-admin UI."""
    db = await get_database()
    rows = await db.platform_models.find({}, {"_id": 0}).to_list(500)
    rows.sort(key=lambda r: ((r.get("provider") or ""), (r.get("display_name") or r.get("key") or "")))
    return {"models": rows, "count": len(rows)}


def _require_provider_ready(provider: str) -> None:
    """Raise 400 if the provider isn't fully wired up (env key set,
    SDK installed, dispatch wired). This is the gate that stops a
    super-admin from registering a model whose runtime would 500.
    Called by both POST and PUT handlers; the check is provider-level
    so changing the `provider` field on an existing row re-validates."""
    status_rows = _resolve_provider_status()
    spec = next((p for p in status_rows if p["provider"] == provider.lower()), None)
    if spec is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider {provider!r}. Supported: {', '.join(p['provider'] for p in status_rows)}",
        )
    if not spec["ready"]:
        missing = []
        if not spec["configured"]:        missing.append(f"set {spec['env_var']} in backend/.env")
        if not spec["sdk_installed"]:     missing.append(f"install SDK ({spec['sdk_module']})")
        if not spec["wired_in_llmchat"]:  missing.append("wire provider dispatch in LlmChat")
        raise HTTPException(
            status_code=400,
            detail=(
                f"Provider {provider!r} is not runtime-ready. Missing: " + "; ".join(missing) +
                ". Check the Providers status banner on the Models tab."
            ),
        )


@router.post("/models", status_code=201)
async def create_platform_model(
    body: PlatformModelCreate,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Register a new model. ``key`` must be globally unique — it's the
    identifier tenants pick when assigning models. The provider must be
    fully runtime-ready (env key + SDK + dispatch)."""
    if not _MODEL_KEY_RE.match(body.key):
        raise HTTPException(
            status_code=400,
            detail="key must be lowercase alphanumeric / hyphen / dot / underscore (max 64 chars)",
        )
    _require_provider_ready(body.provider)
    db = await get_database()
    if await db.platform_models.find_one({"key": body.key}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=400, detail=f"Model {body.key!r} already exists.")

    now = datetime.now(timezone.utc).isoformat()
    doc: Dict[str, Any] = {
        "id":           str(uuid.uuid4()),
        "key":          body.key,
        "display_name": body.display_name,
        "provider":     body.provider,
        "api_model":    body.api_model,
        "description":  body.description or "",
        "pricing":      body.pricing.model_dump(),
        "capabilities": (body.capabilities.model_dump() if body.capabilities else {}),
        "enabled":      bool(body.enabled if body.enabled is not None else True),
        "created_at":   now,
        "updated_at":   now,
        "created_by":   payload.get("user_id"),
    }
    await db.platform_models.insert_one(doc)

    from services.model_registry import invalidate_cache
    invalidate_cache()

    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="create_platform_model",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="platform_model",
        resource_id=body.key,
        new_value={"key": body.key, "provider": body.provider, "api_model": body.api_model},
        ip_address=http_request.client.host if http_request.client else None,
    )
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/models/{key}")
async def update_platform_model(
    key: str,
    body: PlatformModelUpdate,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Partial update — only fields supplied are written. The ``key``
    column is immutable (it's used as a foreign key by tenants and the
    cost ledger); rename by creating a new row + reassigning tenants."""
    db = await get_database()
    existing = await db.platform_models.find_one({"key": key}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Model not found")

    incoming = _strip_none_dict(body.model_dump())
    if not incoming:
        raise HTTPException(status_code=400, detail="No fields to update")
    # If the operator's changing the provider, re-validate that the
    # new one is runtime-ready (same gate as POST).
    if "provider" in incoming and incoming["provider"] != existing.get("provider"):
        _require_provider_ready(incoming["provider"])
    # Pricing comes through as a dict from model_dump; serialize the
    # nested model the same way for storage.
    if "pricing" in incoming and incoming["pricing"] is not None:
        incoming["pricing"] = body.pricing.model_dump() if body.pricing else existing.get("pricing")
    if "capabilities" in incoming and incoming["capabilities"] is not None:
        incoming["capabilities"] = body.capabilities.model_dump() if body.capabilities else existing.get("capabilities") or {}

    incoming["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.platform_models.update_one({"key": key}, {"$set": incoming})

    from services.model_registry import invalidate_cache
    invalidate_cache()

    await _audit_safe(
        db,
        category=AuditCategory.DATA_MODIFICATION,
        action="update_platform_model",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="platform_model",
        resource_id=key,
        old_value={k: existing.get(k) for k in incoming.keys()},
        new_value=incoming,
        ip_address=http_request.client.host if http_request.client else None,
    )
    return await db.platform_models.find_one({"key": key}, {"_id": 0})


@router.delete("/models/{key}")
async def delete_platform_model(
    key: str,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Remove a model. Refuses if any tenant currently has the key in
    their ``allowed_model_keys`` or ``default_model_key`` — re-assign
    those tenants first."""
    db = await get_database()
    in_use = await db.companies.count_documents({
        "$or": [
            {"allowed_model_keys": key},
            {"default_model_key": key},
        ],
    })
    if in_use > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Model {key!r} is assigned to {in_use} tenant(s). Re-assign them before deleting.",
        )
    result = await db.platform_models.delete_one({"key": key})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Model not found")

    from services.model_registry import invalidate_cache
    invalidate_cache()

    await _audit_safe(
        db,
        category=AuditCategory.DATA_DELETION,
        action="delete_platform_model",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="platform_model",
        resource_id=key,
        ip_address=http_request.client.host if http_request.client else None,
        severity=AuditSeverity.WARNING,
    )
    return {"deleted": True, "key": key}


# ─── Per-tenant model assignment ────────────────────────────────────────────


class CompanyModelAssignment(BaseModel):
    """Which model keys this tenant can pick from at runtime.
    ``default`` MUST be one of the keys in ``allowed``."""
    allowed: List[str]
    default: str


@router.get("/companies/{company_id}/models")
async def get_company_model_assignment(
    company_id: str,
    payload: dict = Depends(verify_super_admin),
):
    db = await get_database()
    company = await db.companies.find_one(
        {"id": company_id},
        {"_id": 0, "id": 1, "name": 1, "allowed_model_keys": 1, "default_model_key": 1, "llm_model": 1},
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return {
        "company_id":         company_id,
        "name":               company.get("name"),
        "allowed":            list(company.get("allowed_model_keys") or []),
        "default":            company.get("default_model_key") or company.get("llm_model") or "",
    }


@router.put("/companies/{company_id}/models")
async def set_company_model_assignment(
    company_id: str,
    body: CompanyModelAssignment,
    http_request: Request,
    payload: dict = Depends(verify_super_admin),
):
    """Assign an allowlist + default to a tenant. The default key must
    be in the allowlist, and every key must exist as an *enabled* row
    in ``platform_models``."""
    if not body.allowed:
        raise HTTPException(status_code=400, detail="At least one model must be allowed")
    if body.default not in body.allowed:
        raise HTTPException(status_code=400, detail="default must be one of the allowed keys")

    db = await get_database()
    existing_company = await db.companies.find_one(
        {"id": company_id},
        {"_id": 0, "id": 1, "allowed_model_keys": 1, "default_model_key": 1},
    )
    if not existing_company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Validate every key exists and is enabled. Disabled models can be
    # un-assigned but not newly-assigned — the chat path silently
    # rejects them otherwise.
    rows = await db.platform_models.find(
        {"key": {"$in": body.allowed}},
        {"_id": 0, "key": 1, "enabled": 1},
    ).to_list(100)
    known_keys = {r["key"]: r.get("enabled", True) for r in rows}
    missing = [k for k in body.allowed if k not in known_keys]
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown model keys: {missing}")
    disabled = [k for k in body.allowed if not known_keys[k]]
    if disabled:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot assign disabled model keys: {disabled}. Re-enable them first or pick different models.",
        )

    update = {
        "$set": {
            "allowed_model_keys": body.allowed,
            "default_model_key":  body.default,
            # Keep the legacy column in sync — old code paths and
            # existing analytics queries still read it. Will deprecate
            # once everything migrates to default_model_key.
            "llm_model":          body.default,
        },
    }
    await db.companies.update_one({"id": company_id}, update)

    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="update_company_models",
        user_id=payload.get("user_id"),
        user_type="super_admin",
        resource_type="company",
        resource_id=company_id,
        company_id=company_id,
        old_value={
            "allowed": list(existing_company.get("allowed_model_keys") or []),
            "default": existing_company.get("default_model_key"),
        },
        new_value={"allowed": body.allowed, "default": body.default},
        ip_address=http_request.client.host if http_request.client else None,
    )
    return {
        "company_id": company_id,
        "allowed":    body.allowed,
        "default":    body.default,
    }
