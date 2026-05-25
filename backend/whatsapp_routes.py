"""
====================================================================
SEVA SETU BOT - WHATSAPP INTEGRATION (Twilio)
====================================================================
Full WhatsApp Business API integration for consular bot services.
Supports: Incoming messages, Outgoing messages, Templates, Media
With: Webhook signature validation, session management, guardrails
====================================================================
"""

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Form, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, List, Dict
import uuid
import os
import logging
from datetime import datetime, timezone
from database import get_database
from tenant import get_tenant_id
from services.bot_config import get_bot_config
from services.messaging_channel_resolver import (
    resolve_company_from_channel,
    CHANNEL_WHATSAPP_TWILIO,
)

# Security imports
from security.webhook_validator import verify_twilio_webhook, log_webhook_attempt
from security.session_manager import session_manager
from security.input_sanitizer import sanitize_user_input, create_safe_system_prompt
from security.guardrail import guardrail_service, sanitize_logs

# Twilio imports
try:
    from twilio.rest import Client
    from twilio.twiml.messaging_response import MessagingResponse
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    
# LLM imports for AI responses
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])
logger = logging.getLogger(__name__)

# =====================================================================
# CONFIGURATION
# =====================================================================
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', '')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# Bot system prompt is now per-tenant: loaded from `tenant_bot_config` via
# the bot_config service. The legacy hardcoded `_WHATSAPP_BASE_PROMPT` /
# `WHATSAPP_SYSTEM_PROMPT` constants moved into migration 0005's seed row
# (under `system_prompt_template`) — see services/bot_config.py.
#
# generate_ai_response() resolves it per request and wraps with
# create_safe_system_prompt() for security hardening, same as before.


# =====================================================================
# MODELS
# =====================================================================
class WhatsAppIncomingMessage(BaseModel):
    """Model for incoming WhatsApp webhook data"""
    From: str
    To: str
    Body: str
    MessageSid: str
    NumMedia: int = 0
    ProfileName: Optional[str] = None

class SendWhatsAppRequest(BaseModel):
    """Request model for sending WhatsApp messages"""
    to_number: str
    message: str
    template_name: Optional[str] = None

class WhatsAppMessageResponse(BaseModel):
    """Response model for WhatsApp operations"""
    success: bool
    message_sid: Optional[str] = None
    error: Optional[str] = None


# =====================================================================
# TWILIO SERVICE
# =====================================================================
class TwilioWhatsAppService:
    """Service class for Twilio WhatsApp operations"""
    
    def __init__(self):
        if TWILIO_AVAILABLE and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            self.whatsapp_number = f"whatsapp:{TWILIO_WHATSAPP_NUMBER}"
            self.enabled = True
        else:
            self.client = None
            self.enabled = False
            logger.warning("Twilio not configured - WhatsApp will use mock mode")
    
    def send_message(self, to_number: str, body: str) -> Dict:
        """Send a WhatsApp message"""
        if not self.enabled:
            # Mock response for testing
            return {
                "success": True,
                "message_sid": f"mock_{uuid.uuid4().hex[:12]}",
                "mock": True
            }
        
        try:
            message = self.client.messages.create(
                body=body,
                from_=self.whatsapp_number,
                to=f"whatsapp:{to_number}"
            )
            return {
                "success": True,
                "message_sid": message.sid,
                "mock": False
            }
        except Exception as e:
            logger.error(f"Twilio send error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def generate_twiml_response(self, message: str) -> str:
        """Generate TwiML response for webhook"""
        response = MessagingResponse()
        response.message(message)
        return str(response)


# Initialize service
twilio_service = TwilioWhatsAppService()


# =====================================================================
# AI RESPONSE GENERATION
# =====================================================================
async def generate_ai_response(user_message: str, session_id: str, company_id: str) -> str:
    """Generate AI response for WhatsApp user. System prompt is per-tenant
    (resolved from tenant_bot_config) and wrapped with security hardening
    on every call."""
    cfg = await get_bot_config(company_id)

    if not LLM_AVAILABLE or not EMERGENT_LLM_KEY:
        # cfg.fallback("error") covers this case; fall back to a generic
        # message only if the tenant hasn't customised one.
        return cfg.fallback("error") or "Thank you for your message. For detailed assistance, please visit our web portal."

    try:
        system_prompt = create_safe_system_prompt(cfg.system_prompt())
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_prompt
        ).with_model("openai", "gpt-5.2")

        response = await chat.send_message(UserMessage(text=user_message))
        return response
    except Exception as e:
        logger.error(f"AI response error: {e}")
        return cfg.fallback("error") or "I apologize, I'm having trouble processing your request. Please try again or visit our web portal."


# =====================================================================
# ENDPOINTS
# =====================================================================

@router.get("/status")
async def whatsapp_status():
    """Check WhatsApp integration status"""
    return {
        "status": "active",
        "twilio_configured": twilio_service.enabled,
        "llm_available": LLM_AVAILABLE and bool(EMERGENT_LLM_KEY),
        "webhook_url": "/api/whatsapp/webhook"
    }


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Webhook endpoint for incoming WhatsApp messages from Twilio.
    Twilio sends form-encoded data.
    With: Signature validation, input sanitization, PII protection
    """
    source_ip = request.client.host if request.client else "unknown"
    
    try:
        # Validate Twilio webhook signature (skip in dev mode)
        if os.environ.get('WEBHOOK_VALIDATION_DISABLED', '').lower() != 'true':
            try:
                await verify_twilio_webhook(request)
                log_webhook_attempt("whatsapp", source_ip, True, "Signature valid")
            except HTTPException:
                log_webhook_attempt("whatsapp", source_ip, False, "Invalid signature")
                raise
        
        form_data = await request.form()

        # Extract message details
        from_number = form_data.get("From", "").replace("whatsapp:", "")
        to_number = form_data.get("To", "").replace("whatsapp:", "")   # tenant channel
        message_body = form_data.get("Body", "").strip()
        message_sid = form_data.get("MessageSid", "")
        profile_name = form_data.get("ProfileName", "")
        num_media = int(form_data.get("NumMedia", 0))

        # Resolve which company owns the inbound channel. Today the resolver
        # ignores its args and returns the env-var default; the contract is
        # in place so flipping to a real channel map is a single-function change.
        company_id = await resolve_company_from_channel(CHANNEL_WHATSAPP_TWILIO, to_number)
        
        # Sanitize and validate input
        sanitization_result = sanitize_user_input(message_body, context="whatsapp")
        
        if not sanitization_result.is_safe:
            logger.warning(f"[SECURITY] Blocked unsafe input from {sanitize_logs(from_number)}: {sanitization_result.detected_patterns}")
            _cfg = await get_bot_config(company_id)
            ai_response = sanitization_result.warnings[0] if sanitization_result.warnings else (_cfg.fallback("blocked_input") or "I cannot process that request.")
        else:
            # Mask PII in input before processing
            input_result = guardrail_service.validate_input(message_body)
            sanitized_message = input_result.sanitized_text
            
            logger.info(f"WhatsApp message from {sanitize_logs(from_number)}: {sanitize_logs(message_body[:50])}...")
            
            db = await get_database()
            
            # Get or create user (tenant-scoped lookup)
            user = await db.whatsapp_users.find_one(
                {"company_id": company_id, "phone_number": from_number}, {"_id": 0}
            )
            if not user:
                user_id = str(uuid.uuid4())
                user = {
                    "id": user_id,
                    "company_id": company_id,
                    "phone_number": from_number,
                    "profile_name": profile_name,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_interaction": datetime.now(timezone.utc).isoformat()
                }
                await db.whatsapp_users.insert_one(user)
            else:
                user_id = user['id']
                # Update last interaction for WhatsApp 24-hour window tracking
                await db.whatsapp_users.update_one(
                    {"company_id": company_id, "phone_number": from_number},
                    {"$set": {"last_interaction": datetime.now(timezone.utc).isoformat()}}
                )

            # Get or create secure session — thread company_id into metadata
            session = await session_manager.get_or_create_session(
                channel="whatsapp",
                user_identifier=from_number,
                metadata={"profile_name": profile_name, "twilio_sid": message_sid, "company_id": company_id}
            )
            session_id = session['id']

            # Store incoming message (with PII masked in logs)
            await db.whatsapp_messages.insert_one({
                "id": str(uuid.uuid4()),
                "company_id": company_id,
                "twilio_sid": message_sid,
                "user_id": user_id,
                "phone_number": from_number,
                "direction": "inbound",
                "message": message_body,  # Store original for user reference
                "message_sanitized": sanitized_message,  # Store sanitized for processing
                "has_media": num_media > 0,
                "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Generate AI response using sanitized input
            ai_response = await generate_ai_response(sanitized_message, session_id, company_id)
            
            # Validate and sanitize output
            output_result = guardrail_service.validate_output(ai_response)
            ai_response = output_result.sanitized_text
            
            if output_result.pii_detected:
                logger.warning(f"[GUARDRAIL] PII detected in output, masked: {output_result.pii_detected}")
            
            # Store outgoing message
            await db.whatsapp_messages.insert_one({
                "id": str(uuid.uuid4()),
                "company_id": company_id,
                "user_id": user_id,
                "phone_number": from_number,
                "direction": "outbound",
                "message": ai_response,
                "session_id": session_id,
                "guardrail_flags": output_result.unsafe_patterns,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        
        # Return TwiML response
        if TWILIO_AVAILABLE:
            twiml = twilio_service.generate_twiml_response(ai_response)
            return Response(content=twiml, media_type="application/xml")
        else:
            return {"reply": ai_response}
        
    except HTTPException:
        raise  # Re-raise authentication errors
    except Exception as e:
        logger.error(f"Webhook error: {sanitize_logs(str(e))}")
        return Response(status_code=200)  # Always return 200 to Twilio


@router.post("/send")
async def send_whatsapp_message(
    request: SendWhatsAppRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """Send a WhatsApp message to a user (admin endpoint, tenant-scoped)."""
    db = await get_database()

    result = twilio_service.send_message(request.to_number, request.message)

    # Store outgoing message
    await db.whatsapp_messages.insert_one({
        "id": str(uuid.uuid4()),
        "company_id": tenant_id,
        "phone_number": request.to_number,
        "direction": "outbound",
        "message": request.message,
        "twilio_sid": result.get("message_sid"),
        "status": "sent" if result["success"] else "failed",
        "mock": result.get("mock", False),
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    return WhatsAppMessageResponse(
        success=result["success"],
        message_sid=result.get("message_sid"),
        error=result.get("error")
    )


@router.get("/conversations")
async def get_whatsapp_conversations(tenant_id: str = Depends(get_tenant_id)):
    """Get all WhatsApp conversations for admin view (tenant-scoped)."""
    db = await get_database()

    # Get unique users with their last message — scoped to caller's tenant
    pipeline = [
        {"$match": {"company_id": tenant_id}},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$phone_number",
            "last_message": {"$first": "$message"},
            "last_timestamp": {"$first": "$timestamp"},
            "message_count": {"$sum": 1}
        }},
        {"$sort": {"last_timestamp": -1}},
        {"$limit": 50}
    ]

    conversations = await db.whatsapp_messages.aggregate(pipeline).to_list(50)
    
    return {
        "conversations": [
            {
                "phone_number": c["_id"],
                "last_message": c["last_message"][:100] if c["last_message"] else "",
                "last_timestamp": c["last_timestamp"],
                "message_count": c["message_count"]
            }
            for c in conversations
        ]
    }


@router.get("/messages/{phone_number}")
async def get_conversation_messages(
    phone_number: str,
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
):
    """Get messages for a specific conversation (tenant-scoped)."""
    db = await get_database()

    messages = await db.whatsapp_messages.find(
        {"company_id": tenant_id, "phone_number": phone_number},
        {"_id": 0}
    ).sort("timestamp", 1).limit(limit).to_list(limit)
    
    return {"messages": messages}


# =====================================================================
# STATUS CALLBACK (for delivery receipts)
# =====================================================================
@router.post("/status-callback")
async def whatsapp_status_callback(request: Request):
    """Handle Twilio message status callbacks"""
    try:
        form_data = await request.form()
        
        message_sid = form_data.get("MessageSid")
        message_status = form_data.get("MessageStatus")
        error_code = form_data.get("ErrorCode")
        
        db = await get_database()
        
        await db.whatsapp_messages.update_one(
            {"twilio_sid": message_sid},
            {"$set": {
                "status": message_status,
                "error_code": error_code,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"Message {message_sid} status: {message_status}")
        return Response(status_code=200)
        
    except Exception as e:
        logger.error(f"Status callback error: {e}")
        return Response(status_code=200)
