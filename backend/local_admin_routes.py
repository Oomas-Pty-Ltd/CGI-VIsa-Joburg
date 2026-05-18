from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from database import get_database
from auth_utils import verify_local_admin
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

@router.get("/dashboard")
async def get_dashboard(payload: dict = Depends(verify_local_admin)):
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
    
    return {
        "company": company,
        "sessions_today": sessions_today,
        "total_documents": total_documents
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