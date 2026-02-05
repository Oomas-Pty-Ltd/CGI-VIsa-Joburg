"""
====================================================================
SEVA SETU BOT - WHATSAPP INTEGRATION (Twilio)
====================================================================
Full WhatsApp Business API integration for consular bot services.
Supports: Incoming messages, Outgoing messages, Templates, Media
====================================================================
"""

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Form
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, List, Dict
import uuid
import os
import logging
from datetime import datetime, timezone
from database import get_database

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

# Bot system prompt for WhatsApp (concise but knowledgeable)
WHATSAPP_SYSTEM_PROMPT = """You are Seva Setu, the official AI assistant for the Consulate General of India, Johannesburg (CGI Johannesburg).

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
5. Be helpful and professional

RESPOND TO USER:"""


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
async def generate_ai_response(user_message: str, session_id: str) -> str:
    """Generate AI response for WhatsApp user"""
    if not LLM_AVAILABLE or not EMERGENT_LLM_KEY:
        return "Thank you for your message. For detailed assistance, please visit our web portal."
    
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=WHATSAPP_SYSTEM_PROMPT
        ).with_model("openai", "gpt-5.2")
        
        response = await chat.send_message(UserMessage(text=user_message))
        return response
    except Exception as e:
        logger.error(f"AI response error: {e}")
        return "I apologize, I'm having trouble processing your request. Please try again or visit our web portal."


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
    """
    try:
        form_data = await request.form()
        
        # Extract message details
        from_number = form_data.get("From", "").replace("whatsapp:", "")
        to_number = form_data.get("To", "").replace("whatsapp:", "")
        message_body = form_data.get("Body", "").strip()
        message_sid = form_data.get("MessageSid", "")
        profile_name = form_data.get("ProfileName", "")
        num_media = int(form_data.get("NumMedia", 0))
        
        logger.info(f"WhatsApp message from {from_number}: {message_body[:50]}...")
        
        db = await get_database()
        
        # Get or create user
        user = await db.whatsapp_users.find_one({"phone_number": from_number}, {"_id": 0})
        if not user:
            user_id = str(uuid.uuid4())
            user = {
                "id": user_id,
                "phone_number": from_number,
                "profile_name": profile_name,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.whatsapp_users.insert_one(user)
        else:
            user_id = user['id']
        
        # Store incoming message
        await db.whatsapp_messages.insert_one({
            "id": str(uuid.uuid4()),
            "twilio_sid": message_sid,
            "user_id": user_id,
            "phone_number": from_number,
            "direction": "inbound",
            "message": message_body,
            "has_media": num_media > 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Generate AI response
        session_id = f"whatsapp_{user_id}"
        ai_response = await generate_ai_response(message_body, session_id)
        
        # Store outgoing message
        await db.whatsapp_messages.insert_one({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "phone_number": from_number,
            "direction": "outbound",
            "message": ai_response,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Return TwiML response
        if TWILIO_AVAILABLE:
            twiml = twilio_service.generate_twiml_response(ai_response)
            return Response(content=twiml, media_type="application/xml")
        else:
            return {"reply": ai_response}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return Response(status_code=200)  # Always return 200 to Twilio


@router.post("/send")
async def send_whatsapp_message(request: SendWhatsAppRequest):
    """Send a WhatsApp message to a user"""
    db = await get_database()
    
    result = twilio_service.send_message(request.to_number, request.message)
    
    # Store outgoing message
    await db.whatsapp_messages.insert_one({
        "id": str(uuid.uuid4()),
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
async def get_whatsapp_conversations():
    """Get all WhatsApp conversations for admin view"""
    db = await get_database()
    
    # Get unique users with their last message
    pipeline = [
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
async def get_conversation_messages(phone_number: str, limit: int = 50):
    """Get messages for a specific conversation"""
    db = await get_database()
    
    messages = await db.whatsapp_messages.find(
        {"phone_number": phone_number},
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
