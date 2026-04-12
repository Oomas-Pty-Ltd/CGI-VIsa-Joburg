from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import uuid
import csv
import io
from datetime import datetime, timezone
import bcrypt
from database import get_database
from auth_utils import verify_super_admin

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
async def create_company(company: CompanyCreate, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    
    existing = await db.companies.find_one({"email": company.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company with this email already exists"
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
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.local_admins.insert_one(admin_doc)
    
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
    payload: dict = Depends(verify_super_admin),
):
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
    payload: dict = Depends(verify_super_admin),
):
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
async def get_session_detail(session_id: str, payload: dict = Depends(verify_super_admin)):
    db = await get_database()
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
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
    payload: dict = Depends(verify_super_admin),
):
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
    payload: dict = Depends(verify_super_admin),
):
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