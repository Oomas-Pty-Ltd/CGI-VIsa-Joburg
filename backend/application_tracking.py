"""
Application Tracking Module
Handles application lifecycle management
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from database import get_database
import uuid

# Application statuses
APPLICATION_STATUSES = {
    "draft": "Draft - Not submitted",
    "submitted": "Submitted - Awaiting processing",
    "documents_pending": "Documents Pending - Additional documents required",
    "under_review": "Under Review - Being processed",
    "appointment_scheduled": "Appointment Scheduled",
    "appointment_completed": "Appointment Completed",
    "approved": "Approved",
    "rejected": "Rejected",
    "completed": "Completed - Ready for collection",
    "collected": "Collected"
}


async def create_application(
    profile_id: str,
    service_type: str,
    service_name: str,
    form_data: Dict,
    documents: List[str] = None
) -> Dict:
    """Create a new application"""
    db = await get_database()
    
    # Generate application ID: APP-[SERVICE]-[DATE]-[RANDOM]
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_part = str(uuid.uuid4())[:6].upper()
    application_id = f"APP-{service_type[:4].upper()}-{date_part}-{random_part}"
    
    application = {
        "application_id": application_id,
        "profile_id": profile_id,
        "service_type": service_type,
        "service_name": service_name,
        "status": "draft",
        "status_history": [
            {
                "status": "draft",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "notes": "Application created"
            }
        ],
        "form_data": form_data,
        "documents": documents or [],
        "appointment": None,
        "admin_notes": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "submitted_at": None,
        "completed_at": None
    }
    
    await db.applications.insert_one(application)
    
    return {
        "success": True,
        "application_id": application_id,
        "message": "Application created successfully"
    }


async def update_application_status(
    application_id: str,
    new_status: str,
    notes: str = None,
    admin_id: str = None
) -> Dict:
    """Update application status"""
    db = await get_database()
    
    if new_status not in APPLICATION_STATUSES:
        return {"success": False, "error": f"Invalid status: {new_status}"}
    
    status_entry = {
        "status": new_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "notes": notes,
        "updated_by": admin_id
    }
    
    update_data = {
        "status": new_status,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if new_status == "submitted":
        update_data["submitted_at"] = datetime.now(timezone.utc).isoformat()
    elif new_status in ["completed", "collected"]:
        update_data["completed_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.applications.update_one(
        {"application_id": application_id},
        {
            "$set": update_data,
            "$push": {"status_history": status_entry}
        }
    )
    
    if result.modified_count == 0:
        return {"success": False, "error": "Application not found"}
    
    return {
        "success": True,
        "message": f"Status updated to: {APPLICATION_STATUSES[new_status]}"
    }


async def submit_application(application_id: str) -> Dict:
    """Submit a draft application"""
    db = await get_database()
    
    # Get application
    app = await db.applications.find_one({"application_id": application_id}, {"_id": 0})
    if not app:
        return {"success": False, "error": "Application not found"}
    
    if app["status"] != "draft":
        return {"success": False, "error": "Only draft applications can be submitted"}
    
    # Check required documents
    # This would check against document requirements
    
    return await update_application_status(
        application_id, 
        "submitted", 
        "Application submitted by user"
    )


async def get_application(application_id: str) -> Optional[Dict]:
    """Get application by ID"""
    db = await get_database()
    app = await db.applications.find_one({"application_id": application_id}, {"_id": 0})
    return app


async def get_user_applications(profile_id: str, status: str = None) -> List[Dict]:
    """Get all applications for a user"""
    db = await get_database()
    
    query = {"profile_id": profile_id}
    if status:
        query["status"] = status
    
    apps = await db.applications.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=100)
    return apps


async def get_all_applications(
    status: str = None,
    service_type: str = None,
    date_from: str = None,
    date_to: str = None,
    limit: int = 100
) -> List[Dict]:
    """Get all applications (for admin)"""
    db = await get_database()
    
    query = {}
    if status:
        query["status"] = status
    if service_type:
        query["service_type"] = service_type
    if date_from:
        query["created_at"] = {"$gte": date_from}
    if date_to:
        if "created_at" in query:
            query["created_at"]["$lte"] = date_to
        else:
            query["created_at"] = {"$lte": date_to}
    
    apps = await db.applications.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(length=limit)
    return apps


async def add_appointment(
    application_id: str,
    appointment_date: str,
    appointment_time: str,
    location: str = None,
    reference_number: str = None
) -> Dict:
    """Add appointment details to application"""
    db = await get_database()
    
    appointment = {
        "date": appointment_date,
        "time": appointment_time,
        "location": location,
        "reference_number": reference_number,
        "booked_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.applications.update_one(
        {"application_id": application_id},
        {
            "$set": {
                "appointment": appointment,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.modified_count == 0:
        return {"success": False, "error": "Application not found"}
    
    # Update status
    await update_application_status(
        application_id,
        "appointment_scheduled",
        f"Appointment booked for {appointment_date} at {appointment_time}"
    )
    
    return {"success": True, "message": "Appointment added successfully"}


async def add_admin_note(
    application_id: str,
    note: str,
    admin_id: str
) -> Dict:
    """Add admin note to application"""
    db = await get_database()
    
    note_entry = {
        "note": note,
        "admin_id": admin_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.applications.update_one(
        {"application_id": application_id},
        {
            "$push": {"admin_notes": note_entry},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    if result.modified_count == 0:
        return {"success": False, "error": "Application not found"}
    
    return {"success": True, "message": "Note added successfully"}


async def link_documents_to_application(
    application_id: str,
    document_ids: List[str]
) -> Dict:
    """Link documents to an application"""
    db = await get_database()
    
    result = await db.applications.update_one(
        {"application_id": application_id},
        {
            "$addToSet": {"documents": {"$each": document_ids}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    if result.modified_count == 0:
        return {"success": False, "error": "Application not found"}
    
    return {"success": True, "message": "Documents linked successfully"}


async def get_application_statistics() -> Dict:
    """Get application statistics for admin dashboard"""
    db = await get_database()
    
    # Get counts by status
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    status_counts = await db.applications.aggregate(pipeline).to_list(length=20)
    
    # Get counts by service type
    service_pipeline = [
        {"$group": {"_id": "$service_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    service_counts = await db.applications.aggregate(service_pipeline).to_list(length=20)
    
    # Get recent applications
    recent = await db.applications.find({}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(length=10)
    
    # Total counts
    total = await db.applications.count_documents({})
    pending = await db.applications.count_documents({"status": {"$in": ["submitted", "under_review", "documents_pending"]}})
    completed = await db.applications.count_documents({"status": {"$in": ["completed", "collected"]}})
    
    return {
        "total_applications": total,
        "pending_applications": pending,
        "completed_applications": completed,
        "by_status": {item["_id"]: item["count"] for item in status_counts},
        "by_service": {item["_id"]: item["count"] for item in service_counts},
        "recent_applications": recent
    }
