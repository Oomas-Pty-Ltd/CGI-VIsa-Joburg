"""
Admin Configuration Module
Handles all admin-configurable settings for the bot
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from database import get_database
import json

# Default service links configuration
DEFAULT_SERVICE_LINKS = {
    "tourist_visa": {
        "name": "Tourist Visa",
        "url": "https://vfs.matchlessmfs.com/visa-tourist",
        "category": "visa",
        "priority": 1,
        "active": True
    },
    "business_visa": {
        "name": "Business Visa", 
        "url": "https://vfs.matchlessmfs.com/visa-business",
        "category": "visa",
        "priority": 2,
        "active": True
    },
    "student_visa": {
        "name": "Student Visa",
        "url": "https://vfs.matchlessmfs.com/visa-student",
        "category": "visa",
        "priority": 3,
        "active": True
    },
    "passport_renewal": {
        "name": "Passport Renewal",
        "url": "https://vfs.matchlessmfs.com/passport",
        "category": "passport",
        "priority": 4,
        "active": True
    },
    "pcc": {
        "name": "Police Clearance Certificate (PCC)",
        "url": "https://vfs.matchlessmfs.com/pcc",
        "category": "pcc",
        "priority": 5,
        "active": True
    },
    "work_visa": {
        "name": "Work Visa",
        "url": "https://vfs.matchlessmfs.com/visa-work",
        "category": "visa",
        "priority": 6,
        "active": True
    },
    "family_reunion": {
        "name": "Family Reunion Visa",
        "url": "https://vfs.matchlessmfs.com/visa-family",
        "category": "visa",
        "priority": 7,
        "active": True
    },
    "document_attestation": {
        "name": "Document Attestation",
        "url": "https://vfs.matchlessmfs.com/attestation",
        "category": "attestation",
        "priority": 8,
        "active": True
    },
    "oci_pio": {
        "name": "OCI/PIO Card",
        "url": "https://vfs.matchlessmfs.com/oci",
        "category": "oci",
        "priority": 9,
        "active": True
    },
    "renunciation": {
        "name": "Renunciation of Citizenship",
        "url": "https://vfs.matchlessmfs.com/renunciation",
        "category": "other",
        "priority": 10,
        "active": True
    },
    "appointment_booking": {
        "name": "Appointment Booking",
        "url": "https://vfs.matchlessmfs.com/appointment",
        "category": "appointment",
        "priority": 0,
        "active": True
    },
    "status_tracking": {
        "name": "Application Status Tracking",
        "url": "https://vfs.matchlessmfs.com/track",
        "category": "tracking",
        "priority": 0,
        "active": True
    }
}

# Default document requirements per service
DEFAULT_DOCUMENT_REQUIREMENTS = {
    "tourist_visa": {
        "required": [
            {"type": "passport", "description": "Valid passport (6+ months validity)", "original_required": True},
            {"type": "photo", "description": "2 passport-size photographs (white background)", "original_required": True},
            {"type": "itinerary", "description": "Flight itinerary/booking", "original_required": False},
            {"type": "hotel_booking", "description": "Hotel reservation", "original_required": False},
            {"type": "bank_statement", "description": "Bank statement (last 3 months)", "original_required": True}
        ],
        "optional": [
            {"type": "invitation_letter", "description": "Invitation letter from host"}
        ]
    },
    "business_visa": {
        "required": [
            {"type": "passport", "description": "Valid passport (6+ months validity)", "original_required": True},
            {"type": "photo", "description": "2 passport-size photographs", "original_required": True},
            {"type": "business_letter", "description": "Business invitation letter", "original_required": True},
            {"type": "company_registration", "description": "Company registration documents", "original_required": True}
        ],
        "optional": []
    },
    "passport_renewal": {
        "required": [
            {"type": "old_passport", "description": "Current/expired passport", "original_required": True},
            {"type": "photo", "description": "2 passport-size photographs", "original_required": True},
            {"type": "address_proof", "description": "Proof of address in South Africa", "original_required": True},
            {"type": "visa_permit", "description": "Valid SA visa/work permit", "original_required": True}
        ],
        "optional": []
    },
    "pcc": {
        "required": [
            {"type": "passport", "description": "Valid passport", "original_required": True},
            {"type": "photo", "description": "2 passport-size photographs", "original_required": True},
            {"type": "address_proof", "description": "Proof of address", "original_required": True},
            {"type": "application_form", "description": "Completed PCC application form", "original_required": True}
        ],
        "optional": []
    }
}

# Default bot warnings
DEFAULT_WARNINGS = {
    "document_expiry": "⚠️ Your passport must have at least 6 months validity from your travel date.",
    "original_required": "⚠️ Please bring ORIGINAL documents at the time of submission.",
    "appointment_required": "⚠️ An appointment is mandatory. Please book before visiting.",
    "fees_notice": "⚠️ Fees are non-refundable. Please verify all information before payment.",
    "processing_time": "⚠️ Processing times may vary. Please apply well in advance."
}

# Bot behavior configuration
DEFAULT_BOT_CONFIG = {
    "consent_required": True,
    "one_question_per_turn": True,
    "show_progress_indicator": True,
    "personalize_with_name": True,
    "track_session_history": True,
    "max_questions_per_service": 10,
    "greeting_message": "Hi! 👋 I'm Seva Setu Bot, your consular services assistant. I'll guide you step-by-step for Visa, Passport, PCC, or other services.\n\nDo I have your consent to proceed and assist you? (YES/NO)",
    "top_services_count": 5,
    "supported_languages": ["en"],
    "default_language": "en"
}


async def get_admin_config(company_id: str = None) -> Dict:
    """Get admin configuration for a company or default"""
    db = await get_database()
    
    if company_id:
        config = await db.admin_configs.find_one({"company_id": company_id}, {"_id": 0})
        if config:
            return config
    
    # Return default config
    default_config = await db.admin_configs.find_one({"company_id": "default"}, {"_id": 0})
    if default_config:
        return default_config
    
    # Create and return default if none exists
    default = {
        "company_id": "default",
        "service_links": DEFAULT_SERVICE_LINKS,
        "document_requirements": DEFAULT_DOCUMENT_REQUIREMENTS,
        "warnings": DEFAULT_WARNINGS,
        "bot_config": DEFAULT_BOT_CONFIG,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    await db.admin_configs.insert_one(default)
    return {k: v for k, v in default.items() if k != "_id"}


async def update_admin_config(company_id: str, config_type: str, config_data: Dict) -> Dict:
    """Update specific admin configuration"""
    db = await get_database()
    
    valid_types = ["service_links", "document_requirements", "warnings", "bot_config"]
    if config_type not in valid_types:
        raise ValueError(f"Invalid config type. Must be one of: {valid_types}")
    
    result = await db.admin_configs.update_one(
        {"company_id": company_id},
        {
            "$set": {
                config_type: config_data,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    return {"success": True, "message": f"{config_type} updated successfully"}


async def get_service_links(company_id: str = None, top_only: bool = False) -> List[Dict]:
    """Get service links, optionally filtered to top services"""
    config = await get_admin_config(company_id)
    links = config.get("service_links", DEFAULT_SERVICE_LINKS)
    
    # Convert to list and sort by priority
    link_list = [
        {"id": k, **v} for k, v in links.items() 
        if v.get("active", True) and v.get("priority", 99) > 0
    ]
    link_list.sort(key=lambda x: x.get("priority", 99))
    
    if top_only:
        top_count = config.get("bot_config", {}).get("top_services_count", 5)
        return link_list[:top_count]
    
    return link_list


async def get_document_requirements(service_id: str, company_id: str = None) -> Dict:
    """Get document requirements for a service"""
    config = await get_admin_config(company_id)
    requirements = config.get("document_requirements", DEFAULT_DOCUMENT_REQUIREMENTS)
    return requirements.get(service_id, {"required": [], "optional": []})


async def log_exception(
    exception_type: str,
    message: str,
    session_id: str = None,
    user_id: str = None,
    details: Dict = None
):
    """Log an exception/error for admin review"""
    db = await get_database()
    
    log_entry = {
        "type": exception_type,
        "message": message,
        "session_id": session_id,
        "user_id": user_id,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "resolved": False
    }
    
    await db.exception_logs.insert_one(log_entry)
    return log_entry


async def get_exception_logs(
    company_id: str = None,
    resolved: bool = None,
    limit: int = 100
) -> List[Dict]:
    """Get exception logs for admin"""
    db = await get_database()
    
    query = {}
    if company_id:
        query["company_id"] = company_id
    if resolved is not None:
        query["resolved"] = resolved
    
    logs = await db.exception_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(length=limit)
    return logs
