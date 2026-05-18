"""
====================================================================
SEVA SETU BOT - USER API ROUTES
====================================================================
User-facing endpoints for:
- Feedback submission
- Notifications
- Profile management
- GDPR data requests
====================================================================
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi import status as http_status
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from auth_utils import verify_token
from database import get_database
from services.feedback_service import feedback_service, FeedbackType
from services.notification_service import notification_service, NotificationChannel
from services.compliance_service import compliance_service
from services.audit_service import audit_service, AuditCategory

router = APIRouter(prefix="/user", tags=["user"])


# =====================================================================
# FEEDBACK ENDPOINTS
# =====================================================================

class FeedbackRequest(BaseModel):
    session_id: str
    feedback_type: str = "rating"  # rating, comment, issue_report, suggestion
    rating: Optional[int] = None  # 1-5
    comment: Optional[str] = None
    conversation_topic: Optional[str] = None
    bot_response_quality: Optional[int] = None  # 1-5
    resolved_query: Optional[bool] = None


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest, http_request: Request):
    """Submit user feedback (no auth required for anonymous feedback)"""
    db = await get_database()
    
    try:
        feedback_type = FeedbackType(request.feedback_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid feedback type: {request.feedback_type}")
    
    feedback = await feedback_service.submit_feedback(
        db=db,
        session_id=request.session_id,
        feedback_type=feedback_type,
        channel="web",
        rating=request.rating,
        comment=request.comment,
        conversation_topic=request.conversation_topic,
        bot_response_quality=request.bot_response_quality,
        resolved_query=request.resolved_query
    )
    
    return {
        "success": True,
        "feedback_id": feedback.id,
        "message": "Thank you for your feedback!"
    }


@router.get("/feedback/stats")
async def get_feedback_stats(payload: dict = Depends(verify_token)):
    """Get feedback statistics (admin only)"""
    if payload.get('user_type') not in ['super_admin', 'local_admin']:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    db = await get_database()
    stats = await feedback_service.get_feedback_stats(db)
    channel_stats = await feedback_service.get_channel_stats(db)
    
    return {
        "overall": stats,
        "by_channel": channel_stats
    }


# =====================================================================
# NOTIFICATION ENDPOINTS
# =====================================================================

@router.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    payload: dict = Depends(verify_token)
):
    """Get user's notifications"""
    db = await get_database()
    user_id = payload.get('user_id')
    
    notifications = await notification_service.get_user_notifications(
        db=db,
        user_id=user_id,
        unread_only=unread_only,
        limit=limit
    )
    
    return {
        "notifications": notifications,
        "count": len(notifications)
    }


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    payload: dict = Depends(verify_token)
):
    """Mark notification as read"""
    db = await get_database()
    user_id = payload.get('user_id')
    
    success = await notification_service.mark_as_read(db, notification_id, user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"success": True}


# =====================================================================
# PROFILE ENDPOINTS
# =====================================================================

class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    preferred_language: Optional[str] = None
    notification_preferences: Optional[Dict[str, bool]] = None


@router.get("/profile")
async def get_profile(
    http_request: Request,
    payload: dict = Depends(verify_token)
):
    """Get user profile"""
    db = await get_database()
    user_id = payload.get('user_id')
    
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "password": 0}
    )
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Log data access
    await audit_service.log_data_access(
        db=db,
        user_id=user_id,
        user_type=payload.get('user_type', 'user'),
        resource_type="profile",
        resource_id=user_id,
        ip_address=http_request.client.host if http_request.client else None
    )
    
    return user


@router.put("/profile")
async def update_profile(
    request: ProfileUpdateRequest,
    http_request: Request,
    payload: dict = Depends(verify_token)
):
    """Update user profile"""
    db = await get_database()
    user_id = payload.get('user_id')
    
    # Get current profile for audit
    current_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Build update dict
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.phone is not None:
        updates["phone"] = request.phone
    if request.preferred_language is not None:
        updates["preferred_language"] = request.preferred_language
    if request.notification_preferences is not None:
        updates["notification_preferences"] = request.notification_preferences
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    # Perform update
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": updates}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Update failed")
    
    # Log modification
    await audit_service.log_data_modification(
        db=db,
        user_id=user_id,
        user_type=payload.get('user_type', 'user'),
        resource_type="profile",
        resource_id=user_id,
        old_value={k: current_user.get(k) for k in updates.keys()},
        new_value=updates,
        ip_address=http_request.client.host if http_request.client else None
    )
    
    return {"success": True, "message": "Profile updated"}


# =====================================================================
# GDPR/COMPLIANCE ENDPOINTS
# =====================================================================

@router.get("/data-summary")
async def get_data_summary(
    http_request: Request,
    payload: dict = Depends(verify_token)
):
    """Get summary of user's data (GDPR transparency)"""
    db = await get_database()
    user_id = payload.get('user_id')
    
    summary = await compliance_service.get_user_data_summary(db, user_id)
    
    return summary


@router.post("/data-export")
async def request_data_export(
    http_request: Request,
    payload: dict = Depends(verify_token)
):
    """Request data export (GDPR Article 15 & 20)"""
    db = await get_database()
    user_id = payload.get('user_id')
    
    # Create export request
    request_obj = await compliance_service.create_export_request(db, user_id)
    
    # Process immediately (could be async in production)
    result = await compliance_service.process_export_request(db, request_obj.id)
    
    # Log export
    await audit_service.log_data_export(
        db=db,
        user_id=user_id,
        user_type=payload.get('user_type', 'user'),
        export_type="full",
        ip_address=http_request.client.host if http_request.client else None
    )
    
    if result.get('success'):
        return {
            "success": True,
            "request_id": request_obj.id,
            "records_exported": result.get('records_exported'),
            "message": "Your data export is ready. Use the download endpoint to retrieve it."
        }
    else:
        raise HTTPException(status_code=500, detail=result.get('error'))


@router.get("/data-export/{request_id}/download")
async def download_data_export(
    request_id: str,
    payload: dict = Depends(verify_token)
):
    """Download data export"""
    db = await get_database()
    user_id = payload.get('user_id')
    
    data = await compliance_service.download_export(db, request_id, user_id)
    
    if not data:
        raise HTTPException(status_code=404, detail="Export not found or expired")
    
    from fastapi.responses import Response
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=seva_setu_data_export_{request_id[:8]}.zip"
        }
    )


@router.post("/data-delete")
async def request_data_deletion(
    http_request: Request,
    payload: dict = Depends(verify_token)
):
    """Request data deletion (GDPR Article 17 - Right to Erasure)"""
    db = await get_database()
    user_id = payload.get('user_id')
    
    # Create deletion request
    request_obj = await compliance_service.create_deletion_request(db, user_id)
    
    return {
        "success": True,
        "request_id": request_obj.id,
        "message": "Deletion request created. Use /data-delete/{request_id}/confirm to confirm deletion.",
        "warning": "This action is irreversible. All your data will be permanently deleted."
    }


@router.post("/data-delete/{request_id}/confirm")
async def confirm_data_deletion(
    request_id: str,
    http_request: Request,
    payload: dict = Depends(verify_token)
):
    """Confirm and process data deletion"""
    db = await get_database()
    user_id = payload.get('user_id')
    
    # Verify request belongs to user
    request_doc = await db.data_requests.find_one({
        "id": request_id,
        "user_id": user_id,
        "request_type": "delete",
        "status": "pending"
    })
    
    if not request_doc:
        raise HTTPException(status_code=404, detail="Deletion request not found")
    
    # Process deletion
    result = await compliance_service.process_deletion_request(db, request_id, confirm=True)
    
    if result.get('success'):
        # Invalidate all user tokens
        await compliance_service.invalidate_user_tokens(db, user_id)
        
        return {
            "success": True,
            "records_deleted": result.get('records_deleted'),
            "message": "Your data has been deleted. You have been logged out of all sessions."
        }
    else:
        raise HTTPException(status_code=500, detail=result.get('error'))


# =====================================================================
# DOCUMENTS ENDPOINT
# =====================================================================

@router.get("/documents")
async def get_user_documents(
    http_request: Request,
    payload: dict = Depends(verify_token)
):
    """Get user's uploaded documents"""
    from services.document_service import document_service
    
    db = await get_database()
    user_id = payload.get('user_id')
    
    documents = await document_service.get_user_documents(db, user_id)
    
    return {
        "documents": documents,
        "count": len(documents)
    }
