from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
import uuid
from datetime import datetime, timezone
from database import get_database

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

class WhatsAppMessage(BaseModel):
    phone_number: str
    message: str
    message_id: str
    timestamp: int

class WhatsAppResponse(BaseModel):
    reply: Optional[str] = None
    success: bool = True

@router.post("/webhook", response_model=WhatsAppResponse)
async def whatsapp_webhook(message: WhatsAppMessage):
    db = await get_database()
    
    phone_number = message.phone_number
    message_text = message.message.strip().lower()
    
    user = await db.whatsapp_users.find_one({"phone_number": phone_number})
    if not user:
        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "phone_number": phone_number,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.whatsapp_users.insert_one(user)
    
    if message_text in ["hi", "hello", "start", "help"]:
        reply = """🙏 Namaste! Welcome to Seva Setu Bot.

I can help you with:
1️⃣ Passport applications
2️⃣ Visa services
3️⃣ Document verification
4️⃣ Consular assistance

Reply with a number or describe your need."""
    else:
        reply = "Thank you for your message. Our team will assist you shortly. For immediate help, visit our web portal."
    
    await db.whatsapp_messages.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user['id'],
        "phone_number": phone_number,
        "message": message.message,
        "reply": reply,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    return WhatsAppResponse(reply=reply)

@router.get("/status")
async def whatsapp_status():
    return {"status": "webhook_ready", "message": "WhatsApp webhook is active"}