"""
====================================================================
SEVA SETU BOT - TEMPLATE MANAGEMENT SYSTEM
====================================================================
Manages templates for:
- Email notifications
- WhatsApp messages
- Alert notifications
- Custom user templates
====================================================================
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
import uuid
from datetime import datetime, timezone
from database import get_database
from auth_utils import verify_token
from tenant import get_tenant_id

router = APIRouter(prefix="/templates", tags=["templates"])


# =====================================================================
# MODELS
# =====================================================================
class TemplateCategory:
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    ALERT = "alert"
    SMS = "sms"
    CUSTOM = "custom"


class TemplateCreate(BaseModel):
    """Model for creating a new template"""
    name: str = Field(..., min_length=3, max_length=100)
    category: str = Field(..., description="email, whatsapp, alert, sms, custom")
    subject: Optional[str] = None  # For email templates
    body: str = Field(..., min_length=10)
    variables: Optional[List[str]] = None  # e.g., ["user_name", "date", "service"]
    language: str = "en"
    is_public: bool = False  # Public templates visible to all users
    tags: Optional[List[str]] = None


class TemplateUpdate(BaseModel):
    """Model for updating a template"""
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[List[str]] = None
    language: Optional[str] = None
    is_public: Optional[bool] = None
    tags: Optional[List[str]] = None


class TemplateResponse(BaseModel):
    """Response model for template"""
    id: str
    name: str
    category: str
    subject: Optional[str] = None
    body: str
    variables: Optional[List[str]] = None
    language: str
    is_public: bool
    tags: Optional[List[str]] = None
    created_by: str
    created_by_type: str
    created_at: str
    updated_at: Optional[str] = None


# =====================================================================
# DEFAULT TEMPLATES
# =====================================================================
DEFAULT_TEMPLATES = [
    # Email Templates
    {
        "name": "Welcome Email",
        "category": "email",
        "subject": "Welcome to Seva Setu - Your Consular Services Partner",
        "body": """🙏 Namaste {{user_name}},

Welcome to Seva Setu Bot - your trusted assistant for Indian consular services in South Africa.

Your account has been successfully created. You can now:
- Apply for passport services
- Request visa assistance
- Get document verification
- Access consular information 24/7

If you have any questions, simply chat with our bot or contact us.

Best regards,
Consulate General of India, Johannesburg""",
        "variables": ["user_name"],
        "language": "en",
        "is_public": True,
        "tags": ["welcome", "onboarding"]
    },
    {
        "name": "Application Status Update",
        "category": "email",
        "subject": "Update: Your {{service_type}} Application - {{application_id}}",
        "body": """Dear {{user_name}},

This is to inform you that your {{service_type}} application (ID: {{application_id}}) has been updated.

Current Status: {{status}}
Last Updated: {{update_date}}

{{additional_notes}}

For any queries, please contact us or use our chatbot.

Regards,
Seva Setu Bot""",
        "variables": ["user_name", "service_type", "application_id", "status", "update_date", "additional_notes"],
        "language": "en",
        "is_public": True,
        "tags": ["status", "application"]
    },
    {
        "name": "Appointment Reminder",
        "category": "email",
        "subject": "Reminder: Your Appointment on {{appointment_date}}",
        "body": """Dear {{user_name}},

This is a reminder for your upcoming appointment:

📅 Date: {{appointment_date}}
🕐 Time: {{appointment_time}}
📍 Location: {{location}}
📋 Service: {{service_type}}

Documents Required:
{{documents_list}}

Please arrive 15 minutes early with all required documents.

Regards,
Consulate General of India, Johannesburg""",
        "variables": ["user_name", "appointment_date", "appointment_time", "location", "service_type", "documents_list"],
        "language": "en",
        "is_public": True,
        "tags": ["appointment", "reminder"]
    },
    
    # WhatsApp Templates
    {
        "name": "WhatsApp Welcome",
        "category": "whatsapp",
        "body": """🙏 Namaste {{user_name}}!

Welcome to Seva Setu Bot. I'm here to help you with Indian consular services.

Reply with:
1️⃣ Passport
2️⃣ Visa
3️⃣ Documents
4️⃣ Other

Or simply type your question!""",
        "variables": ["user_name"],
        "language": "en",
        "is_public": True,
        "tags": ["welcome", "whatsapp"]
    },
    {
        "name": "WhatsApp Appointment Reminder",
        "category": "whatsapp",
        "body": """📅 Appointment Reminder

Hi {{user_name}}, your appointment is scheduled:

Date: {{appointment_date}}
Time: {{appointment_time}}
Service: {{service_type}}

Reply YES to confirm or RESCHEDULE to change.""",
        "variables": ["user_name", "appointment_date", "appointment_time", "service_type"],
        "language": "en",
        "is_public": True,
        "tags": ["appointment", "whatsapp"]
    },
    
    # Alert Templates
    {
        "name": "System Alert - High Load",
        "category": "alert",
        "subject": "⚠️ High System Load Detected",
        "body": """ALERT: System load has exceeded threshold

Metric: {{metric_name}}
Current Value: {{current_value}}
Threshold: {{threshold}}
Time: {{timestamp}}

Please investigate immediately.""",
        "variables": ["metric_name", "current_value", "threshold", "timestamp"],
        "language": "en",
        "is_public": False,
        "tags": ["system", "alert"]
    },
    {
        "name": "Fraud Alert",
        "category": "alert",
        "subject": "🚨 Fraud Alert - Important Notice",
        "body": """⚠️ Important Advisory

{{alert_title}}

{{alert_message}}

If you have any concerns, please contact:
📞 Emergency: (+27) 11 581 9800
📧 Email: cons.joburg@mea.gov.in

Stay vigilant. Stay safe.""",
        "variables": ["alert_title", "alert_message"],
        "language": "en",
        "is_public": True,
        "tags": ["fraud", "alert", "advisory"]
    },
    
    # Hindi Templates
    {
        "name": "स्वागत ईमेल (Hindi Welcome)",
        "category": "email",
        "subject": "सेवा सेतु में आपका स्वागत है",
        "body": """🙏 नमस्ते {{user_name}} जी,

सेवा सेतु बॉट में आपका स्वागत है - दक्षिण अफ्रीका में भारतीय वाणिज्य दूतावास सेवाओं के लिए आपका विश्वसनीय सहायक।

आपका खाता सफलतापूर्वक बना दिया गया है।

किसी भी प्रश्न के लिए, हमारे बॉट से चैट करें।

सादर,
भारतीय वाणिज्य दूतावास, जोहान्सबर्ग""",
        "variables": ["user_name"],
        "language": "hi",
        "is_public": True,
        "tags": ["welcome", "hindi"]
    }
]


# =====================================================================
# HELPER FUNCTIONS
# =====================================================================
async def init_default_templates():
    """Initialize default templates in database"""
    try:
        db = await get_database()
        
        for template in DEFAULT_TEMPLATES:
            existing = await db.templates.find_one({
                "name": template["name"],
                "category": template["category"]
            })
            
            if not existing:
                template_doc = {
                    "id": str(uuid.uuid4()),
                    **template,
                    "created_by": "system",
                    "created_by_type": "system",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await db.templates.insert_one(template_doc)
    except Exception as e:
        # Log error but don't crash - templates can be initialized later
        print(f"Warning: Failed to initialize default templates: {e}")


def render_template(template_body: str, variables: Dict[str, str]) -> str:
    """Render a template with variables"""
    result = template_body
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


# =====================================================================
# ENDPOINTS
# =====================================================================

# Note: Template initialization is handled by the main server.py lifespan function
# The @router.on_event("startup") decorator has been removed to avoid duplicate initialization


@router.post("/init")
async def initialize_templates():
    """Manually initialize default templates"""
    await init_default_templates()
    return {"message": "Default templates initialized"}


@router.get("/")
async def list_templates(
    category: Optional[str] = None,
    language: Optional[str] = None,
    search: Optional[str] = None,
    include_private: bool = False,
    tenant_id: str = Depends(get_tenant_id),
):
    """List templates visible to the calling tenant.

    Visibility rule:
      - Templates with no `company_id` are global system templates (seeded
        by `init_default_templates`) — visible to every tenant.
      - Templates with `company_id == tenant_id` are this tenant's own.
      - Custom templates owned by another tenant are NOT visible.
    """
    db = await get_database()

    base_query: Dict = {
        "$or": [
            {"company_id": tenant_id},
            {"company_id": {"$exists": False}},   # legacy global templates
            {"company_id": None},
        ]
    }

    if category:
        base_query["category"] = category

    if language:
        base_query["language"] = language

    if not include_private:
        base_query["is_public"] = True

    if search:
        # Combine the visibility OR with the search OR via $and.
        search_or = {
            "$or": [
                {"name": {"$regex": search, "$options": "i"}},
                {"body": {"$regex": search, "$options": "i"}},
                {"tags": {"$in": [search]}}
            ]
        }
        visibility = base_query.pop("$or")
        base_query = {**base_query, "$and": [{"$or": visibility}, search_or]}

    templates = await db.templates.find(base_query, {"_id": 0}).to_list(100)
    
    return {
        "templates": templates,
        "count": len(templates)
    }


@router.get("/categories")
async def get_template_categories():
    """Get available template categories with counts"""
    db = await get_database()
    
    pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    
    categories = await db.templates.aggregate(pipeline).to_list(10)
    
    return {
        "categories": [
            {"name": c["_id"], "count": c["count"]}
            for c in categories
        ]
    }


@router.get("/{template_id}")
async def get_template(template_id: str):
    """Get a specific template by ID"""
    db = await get_database()
    
    template = await db.templates.find_one({"id": template_id}, {"_id": 0})
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    return template


@router.post("/", response_model=TemplateResponse)
async def create_template(
    template: TemplateCreate,
    user_id: str = "guest",
    user_type: str = "user",
    tenant_id: str = Depends(get_tenant_id),
):
    """Create a new template owned by the calling tenant."""
    db = await get_database()

    # Duplicate-name check is scoped to this tenant — two tenants can each
    # have their own "Welcome" template in the same category.
    existing = await db.templates.find_one({
        "company_id": tenant_id,
        "name": template.name,
        "category": template.category
    })

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template with this name already exists in this category"
        )

    template_doc = {
        "id": str(uuid.uuid4()),
        "company_id": tenant_id,
        **template.model_dump(),
        "created_by": user_id,
        "created_by_type": user_type,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.templates.insert_one(template_doc)
    
    # Remove _id for response
    template_doc.pop("_id", None)
    
    return TemplateResponse(**template_doc)


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    update: TemplateUpdate,
    user_id: str = "guest",
    tenant_id: str = Depends(get_tenant_id),
):
    """Update an existing template.

    A tenant can only update templates they own. Global system templates
    (no `company_id`) cannot be edited via this endpoint — they're seeded
    by `init_default_templates` and modified there.
    """
    db = await get_database()

    template = await db.templates.find_one({"id": template_id})

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    # Tenant ownership check first — return 404 (not 403) for cross-tenant
    # to avoid leaking existence of foreign templates.
    if template.get("company_id") and template["company_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    if not template.get("company_id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit global system template via this endpoint"
        )

    # Only allow owner or admin to update
    if template["created_by"] != user_id and template["created_by"] != "system":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this template"
        )
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.templates.update_one(
        {"id": template_id},
        {"$set": update_data}
    )
    
    updated = await db.templates.find_one({"id": template_id}, {"_id": 0})
    return updated


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    user_id: str = "guest",
    tenant_id: str = Depends(get_tenant_id),
):
    """Delete a template. Tenant ownership enforced."""
    db = await get_database()

    template = await db.templates.find_one({"id": template_id})

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    # Cross-tenant → 404 to avoid leaking existence.
    if template.get("company_id") and template["company_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )

    # Only allow owner or admin to delete (not system templates)
    if template["created_by"] == "system":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete system templates"
        )

    if template["created_by"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this template"
        )
    
    await db.templates.delete_one({"id": template_id})
    
    return {"message": "Template deleted successfully"}


@router.post("/render")
async def render_template_endpoint(
    template_id: str,
    variables: Dict[str, str]
):
    """Render a template with provided variables"""
    db = await get_database()
    
    template = await db.templates.find_one({"id": template_id}, {"_id": 0})
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found"
        )
    
    rendered_body = render_template(template["body"], variables)
    rendered_subject = None
    
    if template.get("subject"):
        rendered_subject = render_template(template["subject"], variables)
    
    return {
        "template_id": template_id,
        "template_name": template["name"],
        "rendered_subject": rendered_subject,
        "rendered_body": rendered_body
    }


@router.post("/save-as-template")
async def save_message_as_template(
    name: str,
    category: str,
    body: str,
    subject: Optional[str] = None,
    user_id: str = "guest",
    user_type: str = "user",
    tenant_id: str = Depends(get_tenant_id),
):
    """Save a new message format as a template (for users to save custom formats)"""
    db = await get_database()

    # Extract variables from body (look for {{variable}} pattern)
    import re
    variables = re.findall(r'\{\{(\w+)\}\}', body)
    variables = list(set(variables))  # Remove duplicates

    template_doc = {
        "id": str(uuid.uuid4()),
        "company_id": tenant_id,
        "name": name,
        "category": category,
        "subject": subject,
        "body": body,
        "variables": variables if variables else None,
        "language": "en",
        "is_public": False,  # User templates are private by default
        "tags": ["user-created"],
        "created_by": user_id,
        "created_by_type": user_type,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.templates.insert_one(template_doc)
    template_doc.pop("_id", None)
    
    return {
        "message": "Template saved successfully",
        "template": template_doc
    }


@router.get("/user/{user_id}")
async def get_user_templates(
    user_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """Get templates created by a specific user (tenant-scoped)."""
    db = await get_database()

    templates = await db.templates.find(
        {"company_id": tenant_id, "created_by": user_id},
        {"_id": 0}
    ).to_list(100)
    
    return {
        "templates": templates,
        "count": len(templates)
    }
