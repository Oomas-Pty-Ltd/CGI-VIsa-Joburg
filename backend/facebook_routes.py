"""
====================================================================
SEVA SETU BOT - FACEBOOK MESSENGER INTEGRATION
====================================================================
Facebook Messenger API integration for consular bot services.
Supports: Incoming messages, Outgoing messages, Quick Replies
====================================================================
"""

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import Response, PlainTextResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import uuid
import os
import logging
import httpx
from datetime import datetime, timezone
from database import get_database

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

# Bot system prompt for Facebook (concise but knowledgeable)
FB_SYSTEM_PROMPT = """You are Seva Setu, the official AI assistant for the Consulate General of India, Johannesburg (CGI Johannesburg).

KNOWLEDGE BASE - CGI JOHANNESBURG:

**Office Information:**
- Address: 2nd Floor, Sandown Mews East, 88 Stella Street, Sandton, Johannesburg
- Phone: +27 11 783 0202
- Emergency: +27 6830 38144 (24/7)
- Email: cons.joburg@mea.gov.in
- Website: https://www.cgijoburg.gov.in
- Hours: Mon-Fri 9:00 AM - 5:30 PM
- Consular Services: Mon-Fri 9:00 AM - 12:30 PM

**Services Offered:**
1. PASSPORT SERVICES:
   - New passport: R1,200 (normal), R2,400 (tatkal)
   - Renewal: R800 (normal), R1,600 (tatkal)
   - Lost passport: Police report + affidavit required
   - Processing: 4-6 weeks (normal), 1-2 weeks (tatkal)
   - Book appointment: passportindia.gov.in

2. OCI (Overseas Citizen of India):
   - Lifelong visa for Indian origin foreigners
   - Fee: R1,500 (adult), R750 (minor)
   - Documents: Current passport, proof of Indian origin, photos
   - Processing: 6-8 weeks

3. VISA SERVICES:
   - Tourist, Business, Medical, Student visas
   - Apply online: indianvisaonline.gov.in
   - Processing: 3-5 working days

4. CONSULAR SERVICES:
   - Birth/Death registration
   - Marriage registration
   - Power of Attorney attestation
   - Document attestation
   - Emergency certificates

5. PIO CARD CONVERSION:
   - Free conversion to OCI
   - Bring original PIO card

**FRAUD ALERT:**
The Consulate NEVER calls asking for money. Report scams to local police.

RESPONSE RULES:
1. Keep responses SHORT (3-5 sentences max for simple queries)
2. For complex queries, give brief answer + suggest web portal
3. Always provide relevant contact/link
4. Match user's language (Hindi/English/Zulu/Afrikaans)
5. Be friendly and professional

RESPOND TO USER:"""


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
async def generate_fb_ai_response(user_message: str, session_id: str) -> str:
    """Generate AI response for Facebook user"""
    if not LLM_AVAILABLE or not EMERGENT_LLM_KEY:
        return "Thank you for your message. For detailed assistance, visit our web portal."
    
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=FB_SYSTEM_PROMPT
        ).with_model("openai", "gpt-5.2")
        
        response = await chat.send_message(UserMessage(text=user_message))
        return response
    except Exception as e:
        logger.error(f"FB AI response error: {e}")
        return "I apologize, I'm having trouble right now. Please try again."


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
    """
    try:
        body = await request.json()
        
        # Verify this is a page subscription
        if body.get("object") != "page":
            return Response(status_code=404)
        
        db = await get_database()
        
        # Process each entry
        for entry in body.get("entry", []):
            for messaging_event in entry.get("messaging", []):
                sender_id = messaging_event.get("sender", {}).get("id")
                recipient_id = messaging_event.get("recipient", {}).get("id")
                timestamp = messaging_event.get("timestamp")
                
                # Handle message
                if "message" in messaging_event:
                    message = messaging_event["message"]
                    message_text = message.get("text", "")
                    message_id = message.get("mid")
                    
                    if not message_text:
                        continue
                    
                    logger.info(f"FB message from {sender_id}: {message_text[:50]}...")
                    
                    # Get or create user
                    user = await db.facebook_users.find_one(
                        {"fb_id": sender_id}, {"_id": 0}
                    )
                    if not user:
                        user_id = str(uuid.uuid4())
                        user = {
                            "id": user_id,
                            "fb_id": sender_id,
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db.facebook_users.insert_one(user)
                    else:
                        user_id = user['id']
                    
                    # Store incoming message
                    await db.facebook_messages.insert_one({
                        "id": str(uuid.uuid4()),
                        "fb_message_id": message_id,
                        "user_id": user_id,
                        "fb_sender_id": sender_id,
                        "direction": "inbound",
                        "message": message_text,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    
                    # Generate and send AI response
                    session_id = f"facebook_{user_id}"
                    ai_response = await generate_fb_ai_response(message_text, session_id)
                    
                    # Send response
                    result = await fb_service.send_message(sender_id, ai_response)
                    
                    # Store outgoing message
                    await db.facebook_messages.insert_one({
                        "id": str(uuid.uuid4()),
                        "fb_message_id": result.get("message_id"),
                        "user_id": user_id,
                        "fb_sender_id": sender_id,
                        "direction": "outbound",
                        "message": ai_response,
                        "status": "sent" if result["success"] else "failed",
                        "mock": result.get("mock", False),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                
                # Handle postback (button clicks)
                elif "postback" in messaging_event:
                    postback = messaging_event["postback"]
                    payload = postback.get("payload")
                    
                    # Handle different postback payloads
                    if payload == "GET_STARTED":
                        welcome_msg = "🙏 Namaste! Welcome to Seva Setu Bot. I can help you with Indian consular services. What do you need help with?"
                        await fb_service.send_message(sender_id, welcome_msg)
        
        return Response(status_code=200)
        
    except Exception as e:
        logger.error(f"FB webhook error: {e}")
        return Response(status_code=200)  # Always return 200 to Facebook


@router.post("/send")
async def send_facebook_message(request: SendFBMessageRequest):
    """Send a Facebook message to a user"""
    db = await get_database()
    
    result = await fb_service.send_message(request.recipient_id, request.message)
    
    # Store outgoing message
    await db.facebook_messages.insert_one({
        "id": str(uuid.uuid4()),
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
async def get_facebook_conversations():
    """Get all Facebook conversations for admin view"""
    db = await get_database()
    
    pipeline = [
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
async def get_fb_conversation_messages(fb_id: str, limit: int = 50):
    """Get messages for a specific Facebook conversation"""
    db = await get_database()
    
    messages = await db.facebook_messages.find(
        {"fb_sender_id": fb_id},
        {"_id": 0}
    ).sort("timestamp", 1).limit(limit).to_list(limit)
    
    return {"messages": messages}
