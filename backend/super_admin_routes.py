from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import uuid
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
    companies = await db.companies.find({}, {"_id": 0}).limit(limit).to_list(limit)
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
    total_applications = await db.applications.count_documents({})
    total_profiles = await db.user_profiles.count_documents({})
    
    return {
        "total_companies": total_companies,
        "total_sessions": total_sessions,
        "total_documents": total_documents,
        "total_applications": total_applications,
        "total_profiles": total_profiles
    }


# ============================================================================
# ADMIN CONFIGURATION ROUTES
# ============================================================================

class ServiceLinkUpdate(BaseModel):
    service_id: str
    name: str
    url: str
    category: str
    priority: int = 99
    active: bool = True

class WarningUpdate(BaseModel):
    warning_id: str
    message: str

class BotConfigUpdate(BaseModel):
    consent_required: bool = True
    one_question_per_turn: bool = True
    show_progress_indicator: bool = True
    personalize_with_name: bool = True
    track_session_history: bool = True
    greeting_message: Optional[str] = None
    top_services_count: int = 5

class DocumentRequirementUpdate(BaseModel):
    service_id: str
    required: List[dict]
    optional: List[dict] = []


@router.get("/config")
async def get_admin_configuration(payload: dict = Depends(verify_super_admin)):
    """Get all admin configuration"""
    from admin_config import get_admin_config
    config = await get_admin_config()
    return config


@router.put("/config/service-links")
async def update_service_links(
    links: List[ServiceLinkUpdate],
    payload: dict = Depends(verify_super_admin)
):
    """Update service links configuration"""
    from admin_config import update_admin_config
    
    links_dict = {
        link.service_id: {
            "name": link.name,
            "url": link.url,
            "category": link.category,
            "priority": link.priority,
            "active": link.active
        }
        for link in links
    }
    
    result = await update_admin_config("default", "service_links", links_dict)
    return result


@router.put("/config/warnings")
async def update_warnings(
    warnings: List[WarningUpdate],
    payload: dict = Depends(verify_super_admin)
):
    """Update warning messages"""
    from admin_config import update_admin_config
    
    warnings_dict = {w.warning_id: w.message for w in warnings}
    result = await update_admin_config("default", "warnings", warnings_dict)
    return result


@router.put("/config/bot")
async def update_bot_config(
    config: BotConfigUpdate,
    payload: dict = Depends(verify_super_admin)
):
    """Update bot behavior configuration"""
    from admin_config import update_admin_config
    
    config_dict = config.dict(exclude_none=True)
    result = await update_admin_config("default", "bot_config", config_dict)
    return result


@router.put("/config/document-requirements")
async def update_document_requirements(
    requirements: List[DocumentRequirementUpdate],
    payload: dict = Depends(verify_super_admin)
):
    """Update document requirements per service"""
    from admin_config import update_admin_config
    
    req_dict = {
        req.service_id: {
            "required": req.required,
            "optional": req.optional
        }
        for req in requirements
    }
    
    result = await update_admin_config("default", "document_requirements", req_dict)
    return result


# ============================================================================
# CONVERSATION VIEWING ROUTES
# ============================================================================

@router.get("/conversations")
async def get_all_conversations(
    limit: int = 100,
    status: Optional[str] = None,
    payload: dict = Depends(verify_super_admin)
):
    """Get all visitor conversations"""
    db = await get_database()
    
    query = {}
    if status:
        query["state"] = status
    
    conversations = await db.conversations.find(
        query, 
        {"_id": 0}
    ).sort("updated_at", -1).limit(limit).to_list(length=limit)
    
    return {
        "total": len(conversations),
        "conversations": conversations
    }


@router.get("/conversations/{session_id}")
async def get_conversation_detail(
    session_id: str,
    payload: dict = Depends(verify_super_admin)
):
    """Get detailed conversation with all messages"""
    db = await get_database()
    
    conversation = await db.conversations.find_one(
        {"session_id": session_id},
        {"_id": 0}
    )
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    return conversation


@router.get("/conversations/{session_id}/messages")
async def get_conversation_messages(
    session_id: str,
    payload: dict = Depends(verify_super_admin)
):
    """Get all messages from a conversation"""
    db = await get_database()
    
    conversation = await db.conversations.find_one(
        {"session_id": session_id},
        {"_id": 0, "messages": 1}
    )
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    return {
        "session_id": session_id,
        "messages": conversation.get("messages", [])
    }


# ============================================================================
# APPLICATION TRACKING ROUTES
# ============================================================================

@router.get("/applications")
async def get_all_applications(
    limit: int = 100,
    status: Optional[str] = None,
    service_type: Optional[str] = None,
    payload: dict = Depends(verify_super_admin)
):
    """Get all applications"""
    from application_tracking import get_all_applications as fetch_applications
    
    applications = await fetch_applications(
        status=status,
        service_type=service_type,
        limit=limit
    )
    
    return {
        "total": len(applications),
        "applications": applications
    }


@router.get("/applications/{application_id}")
async def get_application_detail(
    application_id: str,
    payload: dict = Depends(verify_super_admin)
):
    """Get application details"""
    from application_tracking import get_application
    
    application = await get_application(application_id)
    
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    return application


@router.put("/applications/{application_id}/status")
async def update_application_status(
    application_id: str,
    new_status: str,
    notes: Optional[str] = None,
    payload: dict = Depends(verify_super_admin)
):
    """Update application status"""
    from application_tracking import update_application_status as update_status
    
    result = await update_status(
        application_id,
        new_status,
        notes,
        payload.get("sub")
    )
    
    return result


@router.post("/applications/{application_id}/notes")
async def add_application_note(
    application_id: str,
    note: str,
    payload: dict = Depends(verify_super_admin)
):
    """Add admin note to application"""
    from application_tracking import add_admin_note
    
    result = await add_admin_note(
        application_id,
        note,
        payload.get("sub")
    )
    
    return result


@router.get("/applications/statistics")
async def get_application_statistics(payload: dict = Depends(verify_super_admin)):
    """Get application statistics"""
    from application_tracking import get_application_statistics
    
    stats = await get_application_statistics()
    return stats


# ============================================================================
# DOCUMENT ACCESS ROUTES
# ============================================================================

@router.get("/documents")
async def get_all_documents(
    limit: int = 100,
    profile_id: Optional[str] = None,
    payload: dict = Depends(verify_super_admin)
):
    """Get all submitted documents"""
    db = await get_database()
    
    query = {}
    if profile_id:
        query["profile_id"] = profile_id
    
    # Get document files
    documents = await db.document_files.find(
        query,
        {"_id": 0, "file_base64": 0}  # Exclude large base64 data in list
    ).sort("uploaded_at", -1).limit(limit).to_list(length=limit)
    
    return {
        "total": len(documents),
        "documents": documents
    }


@router.get("/documents/{document_id}")
async def get_document_detail(
    document_id: str,
    include_file: bool = False,
    payload: dict = Depends(verify_super_admin)
):
    """Get document details with optional file data"""
    db = await get_database()
    
    projection = {"_id": 0}
    if not include_file:
        projection["file_base64"] = 0
    
    document = await db.document_files.find_one(
        {"document_id": document_id},
        projection
    )
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return document


@router.get("/profiles/{profile_id}/documents")
async def get_profile_documents(
    profile_id: str,
    payload: dict = Depends(verify_super_admin)
):
    """Get all documents for a specific profile"""
    db = await get_database()
    
    profile = await db.user_profiles.find_one(
        {"profile_id": profile_id},
        {"_id": 0, "documents": 1, "name": 1, "email": 1}
    )
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    return {
        "profile_id": profile_id,
        "name": profile.get("name"),
        "email": profile.get("email"),
        "documents": profile.get("documents", [])
    }


# ============================================================================
# EXCEPTION LOGS ROUTES
# ============================================================================

@router.get("/exceptions")
async def get_exception_logs(
    limit: int = 100,
    resolved: Optional[bool] = None,
    payload: dict = Depends(verify_super_admin)
):
    """Get exception/error logs"""
    from admin_config import get_exception_logs
    
    logs = await get_exception_logs(resolved=resolved, limit=limit)
    
    return {
        "total": len(logs),
        "logs": logs
    }


@router.put("/exceptions/{log_id}/resolve")
async def resolve_exception(
    log_id: str,
    payload: dict = Depends(verify_super_admin)
):
    """Mark exception as resolved"""
    db = await get_database()
    
    from bson import ObjectId
    
    result = await db.exception_logs.update_one(
        {"_id": ObjectId(log_id)},
        {
            "$set": {
                "resolved": True,
                "resolved_by": payload.get("sub"),
                "resolved_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exception log not found"
        )
    
    return {"success": True, "message": "Exception marked as resolved"}