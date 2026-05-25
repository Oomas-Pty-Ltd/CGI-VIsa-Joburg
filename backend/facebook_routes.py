"""
====================================================================
SEVA SETU BOT - FACEBOOK MESSENGER INTEGRATION
====================================================================
Facebook Messenger API integration for consular bot services.
Supports: Incoming messages, Outgoing messages, Quick Replies
With: Webhook signature validation, session management, guardrails
====================================================================
"""

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from fastapi.responses import Response, PlainTextResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import uuid
import os
import logging
import httpx
from datetime import datetime, timezone
from database import get_database
from tenant import get_tenant_id
from services.bot_config import get_bot_config
from services.messaging_channel_resolver import (
    resolve_company_from_channel,
    CHANNEL_FACEBOOK,
)

# Security imports
from security.webhook_validator import verify_facebook_webhook, log_webhook_attempt
from security.session_manager import session_manager
from security.input_sanitizer import sanitize_user_input, create_safe_system_prompt
from security.guardrail import guardrail_service, sanitize_logs

# LLM imports for AI responses
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

router = APIRouter(prefix="/facebook", tags=["facebook"])
logger = logging.getLogger(__name__)

# =====================================================================
# CONFIGURATION
# =====================================================================
FB_PAGE_ACCESS_TOKEN = os.environ.get('FB_PAGE_ACCESS_TOKEN', '')
FB_VERIFY_TOKEN = os.environ.get('FB_VERIFY_TOKEN', 'seva_setu_verify_token')
FB_APP_SECRET = os.environ.get('FB_APP_SECRET', '')
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# Facebook Graph API URL
FB_GRAPH_API = "https://graph.facebook.com/v18.0"

# Bot system prompt is now per-tenant: loaded from `tenant_bot_config` via
# the bot_config service. The legacy hardcoded `_FB_BASE_PROMPT` /
# `FB_SYSTEM_PROMPT` constants moved into migration 0005's seed row (under
# `system_prompt_template`) — see services/bot_config.py.


# =====================================================================
# MODELS
# =====================================================================
class SendFBMessageRequest(BaseModel):
    """Request to send Facebook message"""
    recipient_id: str
    message: str
    
class FBMessageResponse(BaseModel):
    """Response for FB operations"""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


# =====================================================================
# FACEBOOK MESSENGER SERVICE
# =====================================================================
class FacebookMessengerService:
    """Service class for Facebook Messenger operations"""
    
    def __init__(self):
        self.access_token = FB_PAGE_ACCESS_TOKEN
        self.enabled = bool(FB_PAGE_ACCESS_TOKEN)
        if not self.enabled:
            logger.warning("Facebook not configured - will use mock mode")
    
    async def send_message(self, recipient_id: str, message_text: str) -> Dict:
        """Send a message via Facebook Messenger"""
        if not self.enabled:
            return {
                "success": True,
                "message_id": f"mock_{uuid.uuid4().hex[:12]}",
                "mock": True
            }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{FB_GRAPH_API}/me/messages",
                    params={"access_token": self.access_token},
                    json={
                        "recipient": {"id": recipient_id},
                        "message": {"text": message_text}
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "message_id": data.get("message_id"),
                        "mock": False
                    }
                else:
                    logger.error(f"FB send error: {response.text}")
                    return {
                        "success": False,
                        "error": response.text
                    }
        except Exception as e:
            logger.error(f"Facebook send error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def send_quick_replies(self, recipient_id: str, message_text: str, 
                                  quick_replies: List[Dict]) -> Dict:
        """Send a message with quick reply buttons"""
        if not self.enabled:
            return {"success": True, "mock": True}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{FB_GRAPH_API}/me/messages",
                    params={"access_token": self.access_token},
                    json={
                        "recipient": {"id": recipient_id},
                        "message": {
                            "text": message_text,
                            "quick_replies": quick_replies
                        }
                    }
                )
                return {"success": response.status_code == 200}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Initialize service
fb_service = FacebookMessengerService()


# =====================================================================
# AI RESPONSE GENERATION
# =====================================================================
async def generate_fb_ai_response(user_message: str, session_id: str, company_id: str) -> str:
    """Generate AI response for Facebook user. System prompt is per-tenant
    via the bot_config service, wrapped with security hardening on every call."""
    cfg = await get_bot_config(company_id)

    if not LLM_AVAILABLE or not EMERGENT_LLM_KEY:
        return cfg.fallback("error") or "Thank you for your message. For detailed assistance, visit our web portal."

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
        logger.error(f"FB AI response error: {e}")
        return cfg.fallback("error") or "I apologize, I'm having trouble right now. Please try again."


# =====================================================================
# ENDPOINTS
# =====================================================================

@router.get("/status")
async def facebook_status():
    """Check Facebook integration status"""
    return {
        "status": "active",
        "facebook_configured": fb_service.enabled,
        "llm_available": LLM_AVAILABLE and bool(EMERGENT_LLM_KEY),
        "webhook_url": "/api/facebook/webhook"
    }


@router.get("/webhook")
async def facebook_webhook_verify(request: Request):
    """
    Webhook verification endpoint for Facebook.
    Facebook sends a GET request to verify the webhook.
    """
    params = request.query_params
    
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    
    if mode == "subscribe" and token == FB_VERIFY_TOKEN:
        logger.info("Facebook webhook verified successfully")
        return PlainTextResponse(content=challenge)
    else:
        logger.warning(f"Facebook webhook verification failed - token: {token}")
        raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def facebook_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint for incoming Facebook messages.
    With: Signature validation, input sanitization, PII protection
    """
    source_ip = request.client.host if request.client else "unknown"
    
    try:
        # Validate Facebook webhook signature (skip in dev mode)
        if os.environ.get('WEBHOOK_VALIDATION_DISABLED', '').lower() != 'true':
            # Get raw body for signature validation
            body_bytes = await request.body()
            
            from security.webhook_validator import facebook_validator
            signature = request.headers.get('X-Hub-Signature-256', '')
            
            if not facebook_validator.validate_signature(body_bytes, signature):
                log_webhook_attempt("facebook", source_ip, False, "Invalid signature")
                raise HTTPException(status_code=403, detail="Invalid webhook signature")
            
            log_webhook_attempt("facebook", source_ip, True, "Signature valid")
            
            # Parse JSON from cached body
            import json
            body = json.loads(body_bytes)
        else:
            body = await request.json()
        
        # Verify this is a page subscription
        if body.get("object") != "page":
            return Response(status_code=404)
        
        db = await get_database()
        
        # Process each entry. Facebook sends `recipient.id` = the FB Page ID
        # the user messaged, which identifies the owning tenant via the
        # channel resolver (today returns the env-var default).
        for entry in body.get("entry", []):
            page_id = entry.get("id") or ""
            company_id = await resolve_company_from_channel(CHANNEL_FACEBOOK, page_id)

            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")

                # Handle message
                if "message" in messaging_event:
                    message = messaging_event["message"]
                    message_text = message.get("text", "")
                    message_id = message.get("mid")
                    
                    if not message_text:
                        continue
                    
                    # Sanitize and validate input
                    sanitization_result = sanitize_user_input(message_text, context="facebook")
                    
                    if not sanitization_result.is_safe:
                        logger.warning(f"[SECURITY] Blocked unsafe FB input from {sanitize_logs(sender_id)}: {sanitization_result.detected_patterns}")
                        _cfg = await get_bot_config(company_id)
                        ai_response = _cfg.fallback("blocked_input") or "I cannot process that request."
                        await fb_service.send_message(sender_id, ai_response)
                        continue
                    
                    # Mask PII in input
                    input_result = guardrail_service.validate_input(message_text)
                    sanitized_message = input_result.sanitized_text
                    
                    logger.info(f"FB message from {sanitize_logs(sender_id)}: {sanitize_logs(message_text[:50])}...")
                    
                    # Get or create user (tenant-scoped)
                    user = await db.facebook_users.find_one(
                        {"company_id": company_id, "fb_id": sender_id}, {"_id": 0}
                    )
                    if not user:
                        user_id = str(uuid.uuid4())
                        user = {
                            "id": user_id,
                            "company_id": company_id,
                            "fb_id": sender_id,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "last_interaction": datetime.now(timezone.utc).isoformat()
                        }
                        await db.facebook_users.insert_one(user)
                    else:
                        user_id = user['id']
                        await db.facebook_users.update_one(
                            {"company_id": company_id, "fb_id": sender_id},
                            {"$set": {"last_interaction": datetime.now(timezone.utc).isoformat()}}
                        )

                    # Get or create secure session — thread company_id
                    session = await session_manager.get_or_create_session(
                        channel="facebook",
                        user_identifier=sender_id,
                        metadata={"fb_message_id": message_id, "company_id": company_id}
                    )
                    session_id = session['id']

                    # Store incoming message
                    await db.facebook_messages.insert_one({
                        "id": str(uuid.uuid4()),
                        "company_id": company_id,
                        "fb_message_id": message_id,
                        "user_id": user_id,
                        "fb_sender_id": sender_id,
                        "direction": "inbound",
                        "message": message_text,
                        "message_sanitized": sanitized_message,
                        "session_id": session_id,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    
                    # Generate and send AI response
                    ai_response = await generate_fb_ai_response(sanitized_message, session_id, company_id)
                    
                    # Validate and sanitize output
                    output_result = guardrail_service.validate_output(ai_response)
                    ai_response = output_result.sanitized_text
                    
                    if output_result.pii_detected:
                        logger.warning(f"[GUARDRAIL] PII detected in FB output, masked: {output_result.pii_detected}")
                    
                    # Send response
                    result = await fb_service.send_message(sender_id, ai_response)
                    
                    # Store outgoing message
                    await db.facebook_messages.insert_one({
                        "id": str(uuid.uuid4()),
                        "company_id": company_id,
                        "fb_message_id": result.get("message_id"),
                        "user_id": user_id,
                        "fb_sender_id": sender_id,
                        "direction": "outbound",
                        "message": ai_response,
                        "session_id": session_id,
                        "status": "sent" if result["success"] else "failed",
                        "mock": result.get("mock", False),
                        "guardrail_flags": output_result.unsafe_patterns,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                
                # Handle postback (button clicks)
                elif "postback" in messaging_event:
                    postback = messaging_event["postback"]
                    payload = postback.get("payload")
                    
                    # Handle different postback payloads
                    if payload == "GET_STARTED":
                        _cfg = await get_bot_config(company_id)
                        welcome_msg = _cfg.fallback("greeting") or "Hello! How can I help?"
                        await fb_service.send_message(sender_id, welcome_msg)
        
        return Response(status_code=200)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FB webhook error: {sanitize_logs(str(e))}")
        return Response(status_code=200)  # Always return 200 to Facebook


@router.post("/send")
async def send_facebook_message(
    request: SendFBMessageRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """Send a Facebook message to a user (admin endpoint, tenant-scoped)."""
    db = await get_database()

    result = await fb_service.send_message(request.recipient_id, request.message)

    # Store outgoing message
    await db.facebook_messages.insert_one({
        "id": str(uuid.uuid4()),
        "company_id": tenant_id,
        "fb_sender_id": request.recipient_id,
        "direction": "outbound",
        "message": request.message,
        "fb_message_id": result.get("message_id"),
        "status": "sent" if result["success"] else "failed",
        "mock": result.get("mock", False),
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    return FBMessageResponse(
        success=result["success"],
        message_id=result.get("message_id"),
        error=result.get("error")
    )


@router.get("/conversations")
async def get_facebook_conversations(tenant_id: str = Depends(get_tenant_id)):
    """Get all Facebook conversations for admin view (tenant-scoped)."""
    db = await get_database()

    pipeline = [
        {"$match": {"company_id": tenant_id}},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$fb_sender_id",
            "last_message": {"$first": "$message"},
            "last_timestamp": {"$first": "$timestamp"},
            "message_count": {"$sum": 1}
        }},
        {"$sort": {"last_timestamp": -1}},
        {"$limit": 50}
    ]

    conversations = await db.facebook_messages.aggregate(pipeline).to_list(50)
    
    return {
        "conversations": [
            {
                "fb_id": c["_id"],
                "last_message": c["last_message"][:100] if c["last_message"] else "",
                "last_timestamp": c["last_timestamp"],
                "message_count": c["message_count"]
            }
            for c in conversations
        ]
    }


@router.get("/messages/{fb_id}")
async def get_fb_conversation_messages(
    fb_id: str,
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
):
    """Get messages for a specific Facebook conversation (tenant-scoped)."""
    db = await get_database()

    messages = await db.facebook_messages.find(
        {"company_id": tenant_id, "fb_sender_id": fb_id},
        {"_id": 0}
    ).sort("timestamp", 1).limit(limit).to_list(limit)
    
    return {"messages": messages}
