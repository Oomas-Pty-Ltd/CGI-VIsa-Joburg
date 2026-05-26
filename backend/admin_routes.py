"""
====================================================================
SEVA SETU BOT - ADMIN API ROUTES
====================================================================
Admin dashboard API for:
- Escalation management
- Knowledge base management
- AI observability
- System metrics
- Error reporting
====================================================================
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi import status as http_status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid
import logging

from database import get_database
from auth_utils import verify_super_admin, verify_local_admin, verify_admin, enforce_tenant_scope
from tenant import get_tenant_id
from services.audit_service import audit_service, AuditCategory, AuditSeverity


async def _audit_safe(db, **kwargs):
    """Best-effort audit write — never block the request on audit failures."""
    try:
        await audit_service.log(db=db, **kwargs)
    except Exception:
        pass


from services.escalation_service import (
    escalation_service, 
    EscalationStatus, 
    EscalationPriority
)
from services.knowledge_service import (
    knowledge_service,
    KnowledgeCategory,
    KnowledgeStatus,
    resolve_knowledge_categories,
)
from services.bot_config import get_bot_config
from services.intent_classifier import intent_classifier

logger = logging.getLogger(__name__)
from security.rate_limiter import rate_limiter
from security.cost_monitor import cost_monitor
from security.guardrail import guardrail_service

router = APIRouter(prefix="/admin", tags=["admin"])


# =====================================================================
# ESCALATION MANAGEMENT
# =====================================================================

class UpdateEscalationRequest(BaseModel):
    esc_status: Optional[str] = None
    assigned_to: Optional[str] = None
    resolution_notes: Optional[str] = None


@router.get("/escalations")
async def get_escalations(
    esc_status: Optional[str] = None,
    limit: int = 50,
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_admin)
):
    """List escalations.

    Super-admin: pass ``?company_id=<UUID>`` to scope to one tenant, or
    omit for the cross-tenant view. Local admins are forced to their
    own tenant."""
    company_id = enforce_tenant_scope(payload, company_id)
    if esc_status:
        try:
            status_enum = EscalationStatus(esc_status)
            escalations = await escalation_service.get_escalations_by_status(
                status_enum, limit, company_id=company_id,
            )
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {esc_status}")
    else:
        escalations = await escalation_service.get_open_escalations(
            limit, company_id=company_id,
        )

    return {
        "escalations": escalations,
        "count": len(escalations)
    }


@router.get("/escalations/stats")
async def get_escalation_stats(
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_admin),
):
    """Get escalation statistics. Local admins are forced to their own tenant."""
    company_id = enforce_tenant_scope(payload, company_id)
    return await escalation_service.get_escalation_stats(company_id=company_id)


@router.get("/escalations/{escalation_id}")
async def get_escalation(
    escalation_id: str,
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_admin)
):
    """Get single escalation details. Local admins are forced to their own tenant."""
    company_id = enforce_tenant_scope(payload, company_id)
    escalation = await escalation_service.get_escalation(escalation_id, company_id=company_id)
    if not escalation:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return escalation


@router.put("/escalations/{escalation_id}")
async def update_escalation(
    escalation_id: str,
    request: UpdateEscalationRequest,
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_admin)
):
    """Update escalation status. Local admins can only mutate their own
    tenant's tickets."""
    company_id = enforce_tenant_scope(payload, company_id)
    status_enum = None
    if request.esc_status:
        try:
            status_enum = EscalationStatus(request.esc_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {request.esc_status}")

    success = await escalation_service.update_escalation(
        escalation_id=escalation_id,
        status=status_enum,
        assigned_to=request.assigned_to,
        resolution_notes=request.resolution_notes,
        company_id=company_id,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Escalation not found")

    return {"success": True, "message": "Escalation updated"}


# =====================================================================
# KNOWLEDGE BASE MANAGEMENT
# =====================================================================

VALID_EVENT_STATUSES = {"past", "present", "future", "general"}


class CreateKnowledgeRequest(BaseModel):
    category: str
    title: str
    question: str
    answer: str
    keywords: List[str]
    source: Optional[str] = ""
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    event_status: Optional[str] = None


class UpdateKnowledgeRequest(BaseModel):
    title: Optional[str] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    keywords: Optional[List[str]] = None
    source: Optional[str] = None
    source_verified: Optional[bool] = None
    entry_status: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    event_status: Optional[str] = None


@router.get("/knowledge")
async def get_knowledge_entries(
    category: Optional[str] = None,
    entry_status: Optional[str] = None,
    limit: int = 100,
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_admin)
):
    """Get all knowledge entries. Pass ``?company_id`` to scope to one
    tenant; omit for the cross-tenant super-admin view. Local admins
    are forced to their own tenant regardless of the query param."""
    company_id = enforce_tenant_scope(payload, company_id)
    category_enum = None
    status_enum = None

    if category:
        # Accept either a legacy enum value or any category from the
        # tenant's configured ``knowledge_categories`` list. We pass the
        # raw string through to ``get_all_entries`` — knowledge_service
        # handles enum-vs-string for the Mongo filter.
        if company_id:
            cfg = await get_bot_config(company_id)
            allowed = resolve_knowledge_categories(cfg.raw.get("knowledge_categories") or [])
        else:
            allowed = resolve_knowledge_categories(None)
        cat_lc = str(category).strip().lower()
        if cat_lc not in allowed and not any(cat_lc == e.value for e in KnowledgeCategory):
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
        category_enum = cat_lc

    if entry_status:
        try:
            status_enum = KnowledgeStatus(entry_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {entry_status}")

    entries = await knowledge_service.get_all_entries(
        category_enum, status_enum, limit, company_id=company_id,
    )

    return {
        "entries": entries,
        "count": len(entries)
    }


@router.get("/knowledge/stats")
async def get_knowledge_stats(
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_admin),
):
    """Get knowledge base statistics. Pass ``?company_id`` to scope to one tenant."""
    company_id = enforce_tenant_scope(payload, company_id)
    return await knowledge_service.get_stats(company_id=company_id)


@router.get("/knowledge/{entry_id}")
async def get_knowledge_entry(
    entry_id: str,
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_admin)
):
    """Get single knowledge entry. Pass ``?company_id`` to require the
    entry belong to that tenant."""
    company_id = enforce_tenant_scope(payload, company_id)
    entry = await knowledge_service.get_entry(entry_id, company_id=company_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@router.get("/knowledge/{entry_id}/history")
async def get_knowledge_history(
    entry_id: str,
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_admin)
):
    """Get version history for knowledge entry, optionally scoped by tenant."""
    company_id = enforce_tenant_scope(payload, company_id)
    history = await knowledge_service.get_entry_history(entry_id, company_id=company_id)
    return {
        "entry_id": entry_id,
        "history": history,
        "count": len(history)
    }


@router.post("/knowledge")
async def create_knowledge_entry(
    request: CreateKnowledgeRequest,
    company_id: str,
    http_request: Request,
    payload: dict = Depends(verify_admin)
):
    """Create new knowledge entry for a specific tenant. ``company_id``
    is required — super-admin must explicitly pick which tenant the
    entry belongs to (entries without a tenant would never be searchable).
    Local admins can only create entries for their own tenant."""
    company_id = enforce_tenant_scope(payload, company_id)
    cfg = await get_bot_config(company_id)
    allowed = resolve_knowledge_categories(cfg.raw.get("knowledge_categories") or [])
    cat_lc = str(request.category or "").strip().lower()
    if cat_lc not in allowed and not any(cat_lc == e.value for e in KnowledgeCategory):
        raise HTTPException(status_code=400, detail=f"Invalid category: {request.category}")
    category_enum = cat_lc

    if request.event_status and request.event_status not in VALID_EVENT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"event_status must be one of {sorted(VALID_EVENT_STATUSES)} or omitted",
        )

    entry = await knowledge_service.create_entry(
        company_id=company_id,
        category=category_enum,
        title=request.title,
        question=request.question,
        answer=request.answer,
        keywords=request.keywords,
        source=request.source,
        created_by=payload.get("user_id", "admin"),
        valid_from=request.valid_from or None,
        valid_until=request.valid_until or None,
        event_status=request.event_status or None,
    )

    db = await get_database()
    await _audit_safe(
        db,
        category=AuditCategory.ADMIN_ACTION,
        action="create_knowledge_entry",
        user_id=payload.get("user_id"),
        user_type=payload.get("user_type"),
        resource_type="knowledge_entry",
        resource_id=entry.id,
        company_id=company_id,
        new_value={"title": request.title, "category": request.category},
        ip_address=http_request.client.host if http_request.client else None,
    )

    return {
        "success": True,
        "entry_id": entry.id,
        "message": "Knowledge entry created"
    }


@router.put("/knowledge/{entry_id}")
async def update_knowledge_entry(
    entry_id: str,
    request: UpdateKnowledgeRequest,
    http_request: Request,
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_admin)
):
    """Update knowledge entry (creates new version). Pass ``?company_id``
    to restrict the update to a specific tenant's entry. Local admins
    are forced to their own tenant."""
    company_id = enforce_tenant_scope(payload, company_id)
    updates = {}

    if request.title:
        updates["title"] = request.title
    if request.question:
        updates["question"] = request.question
    if request.answer:
        updates["answer"] = request.answer
    if request.keywords:
        updates["keywords"] = request.keywords
    if request.source:
        updates["source"] = request.source
    if request.source_verified is not None:
        updates["source_verified"] = request.source_verified
    if request.entry_status:
        try:
            KnowledgeStatus(request.entry_status)
            updates["status"] = request.entry_status
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {request.entry_status}")
    # valid_from / valid_until / event_status — distinguish "not provided"
    # from "explicitly cleared". An empty string clears the field; ``None``
    # leaves it alone. Pydantic v2 lets us see which keys were set.
    if "valid_from" in request.model_fields_set:
        updates["valid_from"] = request.valid_from or None
    if "valid_until" in request.model_fields_set:
        updates["valid_until"] = request.valid_until or None
    if "event_status" in request.model_fields_set:
        if request.event_status and request.event_status not in VALID_EVENT_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"event_status must be one of {sorted(VALID_EVENT_STATUSES)} or omitted",
            )
        updates["event_status"] = request.event_status or None

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    success = await knowledge_service.update_entry(
        entry_id=entry_id,
        updates=updates,
        updated_by=payload.get("user_id", "admin"),
        company_id=company_id,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Entry not found")

    db = await get_database()
    await _audit_safe(
        db,
        category=AuditCategory.DATA_MODIFICATION,
        action="update_knowledge_entry",
        user_id=payload.get("user_id"),
        user_type=payload.get("user_type"),
        resource_type="knowledge_entry",
        resource_id=entry_id,
        company_id=company_id,
        new_value=updates,
        ip_address=http_request.client.host if http_request.client else None,
    )

    return {"success": True, "message": "Knowledge entry updated"}


# =====================================================================
# AI OBSERVABILITY
# =====================================================================

@router.get("/observability")
async def get_ai_observability(payload: dict = Depends(verify_super_admin)):
    """Get comprehensive AI observability metrics"""
    intent_stats = intent_classifier.get_stats()
    rate_stats = rate_limiter.get_stats()
    cost_stats = cost_monitor.get_daily_stats()
    guardrail_stats = guardrail_service.get_stats()
    escalation_stats = await escalation_service.get_escalation_stats()
    knowledge_stats = await knowledge_service.get_stats()
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "intent_classification": {
            "total_classifications": intent_stats["total_classifications"],
            "llm_fallbacks": intent_stats["llm_fallbacks"],
            "rule_based_rate": intent_stats["rule_based_rate"],
            "efficiency": f"{intent_stats['rule_based_rate']}% handled without LLM"
        },
        "rate_limiting": {
            "total_requests": rate_stats["total_requests"],
            "blocked_requests": rate_stats["blocked_requests"],
            "block_rate": rate_stats["block_rate"]
        },
        "cost_tracking": {
            "daily_cost": cost_stats["total_cost_usd"],
            "daily_tokens": cost_stats["total_tokens"],
            "budget_remaining": cost_stats["budget"]["remaining"],
            "budget_used_pct": cost_stats["budget"]["used_percentage"]
        },
        "guardrails": {
            "pii_detections": guardrail_stats["pii_detections"],
            "unsafe_outputs_blocked": guardrail_stats["unsafe_output_detections"]
        },
        "escalations": {
            "open": escalation_stats["by_status"]["open"],
            "in_progress": escalation_stats["by_status"]["in_progress"],
            "urgent": escalation_stats["by_priority"]["urgent"]
        },
        "knowledge_base": {
            "total_entries": knowledge_stats["total_entries"],
            "verified_entries": knowledge_stats["verified_entries"],
            "verification_rate": knowledge_stats["verification_rate"]
        }
    }


@router.get("/observability/intent-stats")
async def get_intent_stats(payload: dict = Depends(verify_super_admin)):
    """Get intent classification statistics"""
    return intent_classifier.get_stats()


@router.get("/observability/cost-breakdown")
async def get_cost_breakdown(payload: dict = Depends(verify_super_admin)):
    """Get detailed cost breakdown"""
    daily_stats = cost_monitor.get_daily_stats()
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "daily": daily_stats,
        "model_info": {
            "model": cost_monitor.config["default_model"],
            "provider": cost_monitor.config["provider"],
            "input_cost_per_1k": cost_monitor.config["input_cost_per_1k"],
            "output_cost_per_1k": cost_monitor.config["output_cost_per_1k"]
        },
        "budget_config": {
            "daily_budget": cost_monitor.config["daily_budget"],
            "monthly_budget": cost_monitor.config["monthly_budget"],
            "session_limit": cost_monitor.config["per_session_limit"]
        }
    }


# =====================================================================
# DASHBOARD SUMMARY
# =====================================================================

@router.get("/dashboard")
async def get_admin_dashboard(payload: dict = Depends(verify_super_admin)):
    """Get admin dashboard summary"""
    from database import get_database
    db = await get_database()
    
    # Get counts
    total_sessions = await db.chat_sessions.count_documents({})
    total_companies = await db.companies.count_documents({})
    total_users = await db.users.count_documents({})
    
    # Get today's activity
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    today_sessions = await db.chat_sessions.count_documents({
        "created_at": {"$regex": f"^{today}"}
    })
    
    # Get escalation summary
    escalation_stats = await escalation_service.get_escalation_stats()
    
    # Get cost summary
    cost_stats = cost_monitor.get_daily_stats()
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overview": {
            "total_sessions": total_sessions,
            "total_companies": total_companies,
            "total_users": total_users,
            "today_sessions": today_sessions
        },
        "escalations": {
            "open": escalation_stats["by_status"]["open"],
            "urgent": escalation_stats["by_priority"]["urgent"],
            "total": escalation_stats["total"]
        },
        "costs": {
            "today_usd": cost_stats["total_cost_usd"],
            "budget_remaining": cost_stats["budget"]["remaining"],
            "budget_used_pct": cost_stats["budget"]["used_percentage"]
        },
        "health": {
            "status": "healthy",
            "llm_available": True,
            "db_connected": True
        }
    }



# =====================================================================
# ERROR REPORTING ENDPOINT
# =====================================================================

class ErrorReport(BaseModel):
    error_type: str
    error_message: str
    stack_trace: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    severity: str = "medium"


@router.post("/error-report")
async def receive_error_report(
    report: ErrorReport,
    company_id: str = Depends(get_tenant_id),
):
    """
    Receive error reports from frontend for monitoring and alerting.
    No auth required to ensure errors are always reported.
    Tenant comes from X-Company-Id (widget sets it), falling back to env-var
    default so legacy clients keep working.
    """
    db = await get_database()

    now = datetime.now(timezone.utc).isoformat()

    # Store error report
    error_doc = {
        "id": str(uuid.uuid4()),
        "company_id": company_id,
        "error_type": report.error_type,
        "error_message": report.error_message,
        "stack_trace": report.stack_trace,
        "context": report.context or {},
        "severity": report.severity,
        "status": "new",
        "created_at": now,
        "acknowledged_at": None,
        "resolved_at": None
    }

    await db.error_reports.insert_one(error_doc)
    
    # For critical/high severity, notify admin via notification service
    if report.severity in ["critical", "high"]:
        from services.notification_service import notification_service, NotificationType, NotificationChannel, NotificationPriority
        
        # Find super admin to notify
        super_admin = await db.users.find_one({"user_type": "super_admin"}, {"_id": 0, "id": 1})
        if super_admin:
            try:
                await notification_service.create_notification(
                    db=db,
                    user_id=super_admin["id"],
                    notification_type=NotificationType.SYSTEM_ALERT,
                    channel=NotificationChannel.IN_APP,
                    priority=NotificationPriority.URGENT if report.severity == "critical" else NotificationPriority.HIGH,
                    data={
                        "message": f"🚨 {report.severity.upper()} ERROR: {report.error_type}\n{report.error_message[:200]}"
                    }
                )
            except Exception as e:
                logger.error(f"Failed to send error notification: {e}")
    
    logger.warning(f"[ERROR_REPORT] {report.severity}: {report.error_type} - {report.error_message[:100]}")
    
    return {
        "success": True,
        "report_id": error_doc["id"],
        "message": "Error report received"
    }


@router.get("/error-reports")
async def get_error_reports(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    payload: dict = Depends(verify_super_admin)
):
    """Get error reports (super admin only)"""
    db = await get_database()
    
    query = {}
    if status:
        query["status"] = status
    if severity:
        query["severity"] = severity
    
    cursor = db.error_reports.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    
    reports = await cursor.to_list(length=limit)
    
    # Get stats
    total_new = await db.error_reports.count_documents({"status": "new"})
    total_critical = await db.error_reports.count_documents({"severity": "critical", "status": "new"})
    
    return {
        "reports": reports,
        "stats": {
            "total_new": total_new,
            "critical_unresolved": total_critical
        }
    }


@router.put("/error-reports/{report_id}/acknowledge")
async def acknowledge_error_report(
    report_id: str,
    payload: dict = Depends(verify_super_admin)
):
    """Acknowledge an error report"""
    db = await get_database()
    
    result = await db.error_reports.update_one(
        {"id": report_id},
        {
            "$set": {
                "status": "acknowledged",
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
                "acknowledged_by": payload.get("user_id")
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Report not found")
    
    return {"success": True}


@router.put("/error-reports/{report_id}/resolve")
async def resolve_error_report(
    report_id: str,
    payload: dict = Depends(verify_super_admin)
):
    """Mark an error report as resolved"""
    db = await get_database()
    
    result = await db.error_reports.update_one(
        {"id": report_id},
        {
            "$set": {
                "status": "resolved",
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": payload.get("user_id")
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Report not found")
    
    return {"success": True}
