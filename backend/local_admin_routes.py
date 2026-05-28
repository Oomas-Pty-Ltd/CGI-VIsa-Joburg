from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from database import get_database
from auth_utils import verify_local_admin, verify_admin
from presidio_service import mask_pii
import aiofiles
import os

router = APIRouter(prefix="/local-admin", tags=["local-admin"])

class FeatureToggle(BaseModel):
    voice: bool
    camera: bool

class ChatLog(BaseModel):
    id: str
    user_id: str
    message: str
    masked_message: str
    timestamp: str

class AnalyticsReport(BaseModel):
    period: str
    total_sessions: int
    total_messages: int
    total_documents: int

@router.get("/llm-usage")
async def get_llm_usage(
    days: int = 30,
    company_id: Optional[str] = None,
    payload: dict = Depends(verify_admin),
):
    """Per-tenant LLM cost summary for the Cost dashboard.

    Returns:
      * ``daily``  — one row per day for the requested window (gaps filled with 0)
      * ``models`` — per-model breakdown for the same window
      * ``mtd``    — month-to-date totals (cost + tokens + calls)
      * ``budget`` — monthly budget USD; pulled from companies.llm_monthly_budget_usd
                    or platform_config default (50)
      * ``pace``   — calendar % of month elapsed (0–100), so the UI gauge can
                    overlay a "you should be here by now" tick on top of the
                    cost-consumed bar without rolling its own date math.

    Scope:
      * local_admin / viewer — JWT's company_id is used; any query param is ignored
      * super_admin           — pass `?company_id=<UUID>` for one tenant, or
                               `?company_id=all` for the platform-wide aggregate
                               (no budget gauge, includes per-tenant ranking)
    """
    user_type = payload.get("user_type")
    aggregate = False
    if user_type == "super_admin":
        if not company_id:
            raise HTTPException(
                status_code=400,
                detail="super_admin must specify ?company_id=<UUID> or ?company_id=all",
            )
        if company_id == "all":
            aggregate = True
            company_id = None  # service helpers treat None as "all tenants"
    elif user_type in ("local_admin", "viewer"):
        company_id = payload["company_id"]
    else:
        raise HTTPException(status_code=403, detail="Admin or viewer role required")
    days = max(1, min(int(days or 30), 90))

    db = await get_database()
    now = datetime.now(timezone.utc)

    # Window for the bars chart (last N days, inclusive of today).
    window_start = now - timedelta(days=days - 1)
    window_start = window_start.replace(hour=0, minute=0, second=0, microsecond=0)

    # Month-to-date window for the budget gauge — always anchored to
    # the first of the current month so the percentage matches the
    # operator's calendar intuition.
    mtd_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    from services import llm_usage as _llm_usage
    daily   = await _llm_usage.daily_totals(company_id, window_start, now)
    models  = await _llm_usage.model_breakdown(company_id, mtd_start, now)
    tenants = await _llm_usage.tenant_breakdown(mtd_start, now) if aggregate else []

    mtd_cost = round(sum(m["cost_usd"] for m in models), 4)
    mtd_calls = sum(m["calls"] for m in models)
    mtd_prompt_tokens = sum(m["prompt_tokens"] for m in models)
    mtd_completion_tokens = sum(m["completion_tokens"] for m in models)
    mtd_cached_tokens = sum(m.get("cached_tokens", 0) for m in models)

    # Calendar pace (0–100) — current day-of-month / days-in-month.
    if now.month == 12:
        next_month_start = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month_start = now.replace(month=now.month + 1, day=1)
    days_in_month = (next_month_start - mtd_start).days
    elapsed_days = (now - mtd_start).total_seconds() / 86400.0
    calendar_pct = round(100.0 * elapsed_days / days_in_month, 1) if days_in_month else 0.0

    if elapsed_days > 0:
        projected_total = round(mtd_cost / elapsed_days * days_in_month, 2)
    else:
        projected_total = mtd_cost

    # Aggregate (platform-wide) mode has no per-tenant budget concept,
    # so we omit the gauge block — the frontend hides BudgetGauge when
    # budget is null. Per-tenant mode renders the full gauge + forecast.
    if aggregate:
        budget_block = None
    else:
        company = await db.companies.find_one(
            {"id": company_id}, {"_id": 0, "llm_monthly_budget_usd": 1}
        )
        budget = float((company or {}).get("llm_monthly_budget_usd") or 50.0)
        days_of_runway = None
        if mtd_cost > 0 and elapsed_days > 0:
            daily_avg = mtd_cost / elapsed_days
            if daily_avg > 0:
                remaining = max(0.0, budget - mtd_cost)
                days_of_runway = round(remaining / daily_avg, 1)
        used_pct = round(100.0 * mtd_cost / budget, 1) if budget else 0.0
        budget_block = {
            "monthly_usd":    budget,
            "used_pct":       used_pct,
            "calendar_pct":   calendar_pct,
            "projected":      projected_total,
            "days_of_runway": days_of_runway,
            "over_pace":      (mtd_cost / budget) > (calendar_pct / 100.0) if budget else False,
            "pace_delta_pp":  round(used_pct - calendar_pct, 1),
        }

    return {
        "aggregate":    aggregate,
        "calendar_pct": calendar_pct,
        "projected":    projected_total,
        "daily":         daily,
        "models":        models,
        "tenants":       tenants,
        "mtd": {
            "cost_usd":          mtd_cost,
            "calls":             mtd_calls,
            "prompt_tokens":     mtd_prompt_tokens,
            "completion_tokens": mtd_completion_tokens,
            "cached_tokens":     mtd_cached_tokens,
        },
        "budget": budget_block,
    }


@router.get("/dashboard")
async def get_dashboard(payload: dict = Depends(verify_admin)):
    """Dashboard summary — accessible to local_admin AND viewer roles
    (both render the same Overview page). super_admin tokens are
    rejected because they have no `company_id` claim to scope by."""
    if payload.get("user_type") not in ("local_admin", "viewer"):
        raise HTTPException(status_code=403, detail="Tenant-scoped role required")
    db = await get_database()
    company_id = payload['company_id']

    company = await db.companies.find_one({"id": company_id}, {"_id": 0})

    today = datetime.now(timezone.utc).date()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc).isoformat()

    sessions_today = await db.chat_sessions.count_documents({
        "company_id": company_id,
        "created_at": {"$gte": today_start}
    })

    total_documents = await db.documents.count_documents({"company_id": company_id})

    # The JWT carries `user_id` but not the admin's email — surface it
    # here so the sidebar can show "alice@tenant.com" instead of "Signed
    # in". Viewer accounts live in `local_viewers`; check both rather
    # than guessing the role from the JWT.
    admin = await db.local_admins.find_one(
        {"id": payload['user_id']}, {"_id": 0, "email": 1}
    )
    if not admin:
        admin = await db.local_viewers.find_one(
            {"id": payload['user_id']}, {"_id": 0, "email": 1}
        )

    # Onboarding completion signals — used by the Overview "Setup guide"
    # card to mark each step done. Cheap counts; the dashboard query is
    # already a multi-collection hit so adding three more `count_documents`
    # calls is negligible against the existing latency.
    bot_cfg = await db.tenant_bot_config.find_one(
        {"company_id": company_id}, {"_id": 0, "bot_name": 1}
    )
    has_bot_config = bool(bot_cfg and (bot_cfg.get("bot_name") or "").strip())
    services_count = await db.tenant_services.count_documents({"company_id": company_id})
    total_sessions = await db.chat_sessions.count_documents({"company_id": company_id})

    return {
        "company": company,
        "sessions_today": sessions_today,
        "total_documents": total_documents,
        "admin_email": (admin or {}).get("email", ""),
        "onboarding": {
            "has_bot_config":  has_bot_config,
            "services_count":  services_count,
            "has_sessions":    total_sessions > 0,
        },
    }

@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = "general",
    payload: dict = Depends(verify_local_admin)
):
    db = await get_database()
    company_id = payload['company_id']
    
    upload_base = os.environ.get('UPLOAD_DIR', '/app/uploads')
    upload_dir = os.path.join(upload_base, company_id)
    os.makedirs(upload_dir, exist_ok=True)
    
    file_id = str(uuid.uuid4())
    file_extension = file.filename.split('.')[-1]
    file_path = f"{upload_dir}/{file_id}.{file_extension}"
    
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    doc = {
        "id": file_id,
        "company_id": company_id,
        "filename": file.filename,
        "file_path": file_path,
        "category": category,
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.documents.insert_one(doc)
    
    return {"success": True, "document_id": file_id, "message": "Document uploaded"}

@router.get("/documents")
async def get_documents(limit: int = 100, payload: dict = Depends(verify_local_admin)):
    db = await get_database()
    company_id = payload['company_id']
    
    documents = await db.documents.find(
        {"company_id": company_id}, 
        {"_id": 0, "id": 1, "filename": 1, "category": 1, "uploaded_at": 1}
    ).limit(limit).to_list(limit)
    return documents

@router.get("/chat-logs", response_model=List[ChatLog])
async def get_chat_logs(
    limit: int = 100,
    payload: dict = Depends(verify_local_admin)
):
    db = await get_database()
    company_id = payload['company_id']
    
    sessions = await db.chat_sessions.find(
        {"company_id": company_id},
        {"_id": 0, "user_id": 1, "messages": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    
    logs = []
    for session in sessions:
        for msg in session.get('messages', []):
            masked_text = mask_pii(msg['content'])
            logs.append(ChatLog(
                id=msg['id'],
                user_id=session.get('user_id', 'anonymous'),
                message=msg['content'],
                masked_message=masked_text,
                timestamp=msg['timestamp']
            ))
    
    return logs[:limit]

@router.put("/feature-toggles")
async def update_feature_toggles(
    toggles: FeatureToggle,
    payload: dict = Depends(verify_local_admin)
):
    db = await get_database()
    company_id = payload['company_id']
    
    result = await db.companies.update_one(
        {"id": company_id},
        {"$set": {"features": toggles.model_dump()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found"
        )
    
    return {"success": True, "message": "Features updated"}

@router.get("/analytics/{period}", response_model=AnalyticsReport)
async def get_analytics(
    period: str,
    payload: dict = Depends(verify_local_admin)
):
    db = await get_database()
    company_id = payload['company_id']
    
    now = datetime.now(timezone.utc)
    
    if period == "daily":
        start_date = (now - timedelta(days=1)).isoformat()
    elif period == "weekly":
        start_date = (now - timedelta(days=7)).isoformat()
    elif period == "monthly":
        start_date = (now - timedelta(days=30)).isoformat()
    else:
        raise HTTPException(status_code=400, detail="Invalid period")
    
    total_sessions = await db.chat_sessions.count_documents({
        "company_id": company_id,
        "created_at": {"$gte": start_date}
    })
    
    # Use aggregation pipeline for efficient message counting
    pipeline = [
        {"$match": {"company_id": company_id, "created_at": {"$gte": start_date}}},
        {"$project": {"message_count": {"$size": {"$ifNull": ["$messages", []]}}}},
        {"$group": {"_id": None, "total_messages": {"$sum": "$message_count"}}}
    ]
    result = await db.chat_sessions.aggregate(pipeline).to_list(1)
    total_messages = result[0]['total_messages'] if result else 0
    
    total_documents = await db.documents.count_documents({
        "company_id": company_id,
        "uploaded_at": {"$gte": start_date}
    })
    
    return AnalyticsReport(
        period=period,
        total_sessions=total_sessions,
        total_messages=total_messages,
        total_documents=total_documents
    )