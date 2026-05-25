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
from tenant import get_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/seva-setu", tags=["seva-setu"])

# ── Constants ────────────────────────────────────────────────────────────────

OTP_DEV = "123456"          # hardcoded for dev; replace with secrets.token_digits(6) in prod
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 3
OTP_LOCKOUT_MINUTES = 5
SESSION_TTL_MINUTES = 10    # inactivity timeout per spec

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads", "seva_setu")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_MIME = {"application/pdf", "image/jpeg", "image/png", "image/jpg"}
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB

# ── Service catalogue ────────────────────────────────────────────────────────

SERVICE_CATALOGUE = {
    "passport": {
        "name": "Passport Services",
        "category": "TYPE_A",
        "gov_url": "https://passportindia.gov.in",
        "documents": [
            "Valid / Expired Indian Passport (original + copy)",
            "Completed Application Form (available on Govt. portal)",
            "2 recent passport-size photographs (white background)",
            "Proof of South African address (utility bill / lease)",
            "Birth Certificate (for new applicants)",
            "Proof of name change (if applicable)",
        ],
    },
    "visa": {
        "name": "Indian Visa",
        "category": "TYPE_A",
        "gov_url": "https://indianvisaonline.gov.in",
        "documents": [
            "Valid Passport (minimum 6 months validity)",
            "Completed Visa Application Form",
            "2 recent passport-size photographs",
            "Travel itinerary / confirmed tickets",
            "Hotel booking / invitation letter",
            "Bank statement (last 3 months)",
            "Travel insurance (for tourist visa)",
        ],
    },
    "pcc": {
        "name": "Police Clearance Certificate (PCC)",
        "category": "TYPE_A",
        "gov_url": "https://passportindia.gov.in/pcc",
        "documents": [
            "Valid Indian Passport (original + copy)",
            "Completed PCC Application Form",
            "Proof of current South African residential address",
            "Copy of South African Permanent Residence / Visa",
            "2 passport-size photographs",
            "Fee payment receipt",
        ],
    },
    "oci": {
        "name": "OCI (Overseas Citizen of India)",
        "category": "TYPE_B",
        "documents": [
            "Proof of Indian origin (old Indian passport / parent's Indian passport)",
            "Current valid foreign passport (copy)",
            "2 recent passport-size photographs (50×50mm, white background)",
            "Renunciation / Surrender Certificate (if applicable)",
            "Marriage certificate (if applying on spouse basis)",
            "Birth certificate",
            "South African ID / Residence permit",
        ],
        "fields": [
            {"key": "full_name",       "label": "Full Name",            "required": True},
            {"key": "email",           "label": "Email Address",        "required": True},
            {"key": "dob",             "label": "Date of Birth (DD/MM/YYYY)", "required": True},
            {"key": "phone",           "label": "Mobile Number",        "required": True},
            {"key": "passport_number", "label": "Indian Passport Number", "required": True},
            {"key": "address",         "label": "Residential Address in SA", "required": True},
            {"key": "indian_connection", "label": "Proof of Indian Origin (describe)", "required": True},
        ],
    },
    "ec_death": {
        "name": "EC / Death Certificate",
        "category": "TYPE_B",
        "documents": [
            "Indian Passport of the deceased (copy)",
            "South African Death Certificate (original + notarised copy)",
            "Proof of relationship to deceased",
            "Applicant's valid Indian Passport or OCI card",
            "Two passport-size photographs of applicant",
            "Completed application form",
            "Police report (in case of unnatural death)",
        ],
        "fields": [
            {"key": "full_name",       "label": "Applicant Full Name",  "required": True},
            {"key": "email",           "label": "Email Address",        "required": True},
            {"key": "dob",             "label": "Date of Birth (DD/MM/YYYY)", "required": True},
            {"key": "phone",           "label": "Mobile Number",        "required": True},
            {"key": "passport_number", "label": "Passport / OCI Number", "required": True},
            {"key": "address",         "label": "Residential Address in SA", "required": True},
            {"key": "doc_type",        "label": "Certificate Type (EC or Death Certificate)", "required": True},
            {"key": "doc_purpose",     "label": "Purpose / Relationship to Deceased", "required": True},
        ],
    },
    "surrender": {
        "name": "Surrender / Renunciation of Indian Citizenship",
        "category": "TYPE_B",
        "documents": [
            "Original Indian Passport (to be surrendered)",
            "Copy of acquired foreign citizenship / naturalisation certificate",
            "Completed Renunciation Form (Form I)",
            "Two passport-size photographs",
            "Proof of South African citizenship",
            "Birth certificate",
            "Marriage certificate (if applicable)",
            "Fee payment receipt",
        ],
        "fields": [
            {"key": "full_name",          "label": "Full Name",                       "required": True},
            {"key": "email",              "label": "Email Address",                   "required": True},
            {"key": "dob",                "label": "Date of Birth (DD/MM/YYYY)",      "required": True},
            {"key": "phone",              "label": "Mobile Number",                   "required": True},
            {"key": "passport_number",    "label": "Indian Passport Number",          "required": True},
            {"key": "address",            "label": "Residential Address in SA",       "required": True},
            {"key": "new_citizenship",    "label": "New Citizenship / Nationality",   "required": True},
            {"key": "new_passport",       "label": "New Foreign Passport Number",     "required": True},
        ],
    },
    "marriage": {
        "name": "Marriage Certificate",
        "category": "TYPE_B",
        "documents": [
            "Valid Indian Passport or OCI card (copy)",
            "South African Marriage Certificate (original + copy)",
            "Two passport-size photographs of both spouses",
            "Proof of address",
            "Completed application form",
            "Fee payment receipt (if applicable)",
        ],
        "fields": [
            {"key": "full_name",      "label": "Applicant Full Name",        "required": True},
            {"key": "email",          "label": "Email Address",              "required": True},
            {"key": "dob",            "label": "Date of Birth (DD/MM/YYYY)", "required": True},
            {"key": "phone",          "label": "Mobile Number",              "required": True},
            {"key": "passport_number","label": "Passport / OCI Number",      "required": True},
            {"key": "address",        "label": "Residential Address in SA",  "required": True},
            {"key": "spouse_name",    "label": "Spouse Full Name",           "required": True},
            {"key": "marriage_date",  "label": "Date of Marriage (DD/MM/YYYY)", "required": True},
            {"key": "marriage_place", "label": "Place of Marriage",          "required": True},
        ],
    },
    "misc": {
        "name": "Miscellaneous / Other Consular Forms",
        "category": "TYPE_B",
        "documents": [
            "Valid Indian Passport or OCI card (copy)",
            "Relevant supporting documents (case-specific)",
            "Two passport-size photographs",
            "Completed applicable form",
            "Affidavit / Notarised documents (where required)",
            "Fee payment receipt (if applicable)",
        ],
        "fields": [
            {"key": "full_name",    "label": "Full Name",                   "required": True},
            {"key": "email",        "label": "Email Address",               "required": True},
            {"key": "dob",          "label": "Date of Birth (DD/MM/YYYY)",  "required": True},
            {"key": "phone",        "label": "Mobile Number",               "required": True},
            {"key": "passport_number","label": "Passport / OCI Number",     "required": True},
            {"key": "address",      "label": "Residential Address in SA",   "required": True},
            {"key": "doc_purpose",  "label": "Nature / Purpose of Request", "required": True},
        ],
    },
}


# ── Helpers ──────────────────────────────────────────────────────────────────

_FORM_KEYWORDS = ("application form", "completed form", "completed application", "application form (available")

def _filter_required_docs(docs: list, form_data: dict) -> list:
    """Remove 'bring the application form' entries when user already filled it manually."""
    if len(form_data) <= 2:
        return docs
    return [d for d in docs if not any(kw in d.lower() for kw in _FORM_KEYWORDS)]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ref_id() -> str:
    year = _now().year
    suffix = uuid.uuid4().hex[:6].upper()
    return f"SEVA-{year}-{suffix}"


def _verify_session(token: str, db_session: dict) -> bool:
    if not db_session or not db_session.get("active"):
        return False
    last_active = db_session.get("last_active")
    if isinstance(last_active, str):
        last_active = datetime.fromisoformat(last_active)
    if last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)
    return (_now() - last_active) < timedelta(minutes=SESSION_TTL_MINUTES)


async def _get_session(authorization: str, db) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid session token")
    token = authorization[7:]
    session = await db.seva_setu_sessions.find_one({"session_id": token})
    if not session or not _verify_session(token, session):
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

@router.get("/services")
async def get_services():
    """Return service catalogue (names, categories, documents required)."""
    return {
        k: {
            "name": v["name"],
            "category": v["category"],
            "documents": v.get("documents", []),
            "fields": v.get("fields", []),
            "gov_url": v.get("gov_url"),
        }
        for k, v in SERVICE_CATALOGUE.items()
    }


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

    # Create OTP record
    otp_id = str(uuid.uuid4())
    expires_at = (_now() + timedelta(minutes=OTP_TTL_MINUTES)).isoformat()
    await db.otp_tokens.insert_one({
        "id": otp_id,
        "company_id": company_id,
        "email": email,
        "otp": OTP_DEV,  # replace with random in prod
        "expires_at": expires_at,
        "used": False,
        "attempts": 0,
    })

    # Send OTP — if email is not configured the fallback OTP is 123456
    email_sent = send_otp_email(email, OTP_DEV)
    if email_sent:
        msg = f"OTP sent to {email}. Please enter it to continue."
    else:
        logger.warning(f"[AUTH] OTP email failed for {email}. Using dev OTP: {OTP_DEV}")
        msg = f"Email delivery unavailable — use OTP: {OTP_DEV} to continue."

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

    if token_doc["otp"] != otp_input:
        new_attempts = attempts + 1
        if new_attempts >= OTP_MAX_ATTEMPTS:
            locked_until = (_now() + timedelta(minutes=OTP_LOCKOUT_MINUTES)).isoformat()
            await db.otp_tokens.update_one(
                {"id": token_doc["id"]},
                {"$set": {"attempts": new_attempts, "locked_until": locked_until}}
            )
            raise HTTPException(status_code=429, detail="Too many failed attempts. Account locked for 5 minutes.")
        await db.otp_tokens.update_one({"id": token_doc["id"]}, {"$set": {"attempts": new_attempts}})
        remaining = OTP_MAX_ATTEMPTS - new_attempts
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
    if service_type not in SERVICE_CATALOGUE:
        raise HTTPException(status_code=400, detail=f"Unknown service: {service_type}")

    svc = SERVICE_CATALOGUE[service_type]
    user = await db.seva_setu_users.find_one({"id": session["user_id"], "company_id": session["company_id"]})
    reference_id = _ref_id()

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
    send_account_created_email(user["email"], user["name"], reference_id, svc["name"])

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

    svc = SERVICE_CATALOGUE.get(app["service_type"], {})
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

    send_review_email(
        user["email"],
        user["name"],
        app["reference_id"],
        edit_token,
        app.get("form_data", {}),
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
    svc = SERVICE_CATALOGUE.get(app["service_type"], {})
    form_data = app.get("form_data", {})

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

    send_confirmation_email(user["email"], user["name"], app["reference_id"], svc.get("name", app["service_type"]), pdf_bytes)

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

    svc = SERVICE_CATALOGUE.get(app["service_type"], {})
    form_data = app.get("form_data", {})
    pdf_bytes = generate_application_pdf(
        service_name=app.get("service_name", svc.get("name", app["service_type"])),
        form_data=form_data,
        tracking_id=app["reference_id"],
        uploaded_docs=[
            {"name": d.get("name", "Document"), "status": "uploaded"}
            for d in app.get("documents", [])
        ],
        required_docs=_filter_required_docs(svc.get("documents", []), form_data),
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

    # Validate file
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Only PDF, JPG, PNG files are accepted.")

    raw = await file.read()
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="File too large. Max size is 5MB.")

    app = await db.seva_setu_applications.find_one({"id": app_id, "user_id": session["user_id"], "company_id": session["company_id"]})
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    # Save file
    file_ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else "bin"
    saved_name = f"{app_id}_{uuid.uuid4().hex[:8]}.{file_ext}"
    saved_path = os.path.join(UPLOAD_DIR, saved_name)
    with open(saved_path, "wb") as f:
        f.write(raw)

    # OCR extraction
    ocr_fields: Dict[str, str] = {}
    try:
        ocr_fields = await _run_ocr(raw, content_type)
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


async def _run_ocr(raw: bytes, content_type: str) -> Dict[str, str]:
    """Extract key fields from uploaded document using pytesseract or fallback."""
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

        return _parse_ocr_text(text)
    except ImportError:
        logger.debug("pytesseract not installed — OCR skipped")
        return {}


def _parse_ocr_text(text: str) -> Dict[str, str]:
    """Heuristic extraction of common fields from OCR text."""
    fields: Dict[str, str] = {}
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Passport number pattern: e.g. A1234567 or P1234567
    passport_match = re.search(r'\b[A-Z]{1,2}\d{6,8}\b', text)
    if passport_match:
        fields["passport_number"] = passport_match.group()

    # Date of birth: DD/MM/YYYY or DD-MM-YYYY
    dob_match = re.search(r'\b(\d{2}[/\-]\d{2}[/\-]\d{4})\b', text)
    if dob_match:
        fields["dob"] = dob_match.group().replace("-", "/")

    # Name: lines that are ALL CAPS and plausibly a name
    for line in lines[:15]:
        if re.match(r'^[A-Z][A-Z\s]{4,50}$', line) and len(line.split()) >= 2:
            if not any(kw in line for kw in ["PASSPORT", "INDIA", "REPUBLIC", "NATIONALITY", "SURNAME", "GIVEN"]):
                fields.setdefault("full_name", line.title())
                break

    # Nationality
    if "NATIONALITY" in text.upper() or "INDIAN" in text.upper():
        fields["nationality"] = "Indian"

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

    svc = SERVICE_CATALOGUE.get(app["service_type"], {})
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
    svc = SERVICE_CATALOGUE.get(app["service_type"], {})
    form_data = app.get("form_data", {})

    pdf_bytes = generate_application_pdf(
        service_name=app.get("service_name", svc.get("name", app["service_type"])),
        form_data=form_data,
        tracking_id=app["reference_id"],
        uploaded_docs=[
            {"name": d.get("name", "Document"), "status": "uploaded"}
            for d in app.get("documents", [])
        ],
        required_docs=_filter_required_docs(svc.get("documents", []), form_data),
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
        send_confirmation_email(user["email"], user["name"], app["reference_id"], svc.get("name", app["service_type"]), pdf_bytes)

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
    svc = SERVICE_CATALOGUE.get(app["service_type"], {})

    gov_ref = req.gov_reference.strip()

    # Build form_data that includes the gov reference + required doc list
    form_data_for_pdf = {
        **app.get("form_data", {}),
        "gov_reference_number": gov_ref,
    }

    # Build uploaded_docs list to show required documents in the PDF
    required_docs = [{"name": d, "status": "required"} for d in svc.get("documents", [])]

    pdf_bytes = generate_application_pdf(
        service_name=app.get("service_name", svc.get("name", app["service_type"])),
        form_data=form_data_for_pdf,
        tracking_id=app["reference_id"],
        uploaded_docs=required_docs,
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
            pdf_bytes
        )

    return {
        "success": True,
        "reference_id": app["reference_id"],
        "message": "Application recorded. Confirmation email with PDF sent.",
    }
