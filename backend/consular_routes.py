from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import base64
import os
from database import get_database
from auth_utils import verify_token
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from presidio_service import mask_pii
from knowledge_scraper import get_knowledge_base, search_knowledge
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/consular", tags=["consular"])

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    company_id: Optional[str] = None
    user_id: Optional[str] = None
    image_base64: Optional[str] = None

class ChatResponse(BaseModel):
    session_id: str
    response: str
    step: str

class DocumentScanRequest(BaseModel):
    image_base64: str
    document_type: str
    session_id: str

class FormData(BaseModel):
    session_id: str
    form_data: Dict[str, Any]

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    db = await get_database()
    
    # Allow guest access without token verification for consular bot
    session_id = request.session_id or str(uuid.uuid4())
    user_id = request.user_id or "guest"
    company_id = request.company_id
    
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    
    if not session:
        session = {
            "id": session_id,
            "user_id": user_id,
            "company_id": company_id,
            "messages": [],
            "step": "register",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_sessions.insert_one(session)
    
    llm_model = "gpt-5.2"
    if company_id:
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if company:
            llm_model = company.get('llm_model', 'gpt-5.2')
    
    # Get knowledge base from official sources
    knowledge_base = get_knowledge_base()
    context_info = search_knowledge(request.message, knowledge_base)
    
    # Build enhanced prompt with official source context
    system_message = f"""You are Sevasetu, a multilingual consular assistant for the Consulate General of India, Johannesburg.

CRITICAL INSTRUCTIONS:
1. You MUST respond in the SAME LANGUAGE the user writes in
2. You support: English, Hindi, Afrikaans, Zulu, Tamil, Telugu, Marathi, Bengali, Gujarati, Punjabi, Urdu, and other Indian/South African languages
3. ONLY provide information from these official sources:
   - Consulate General of India Johannesburg (cgijoburg.gov.in)
   - VFS Global Visa Application Centre (visa.vfsglobal.com)
4. If you don't have specific information from these sources, say: "Please visit cgijoburg.gov.in or contact VFS for official information"

OFFICIAL INFORMATION FROM SOURCES:
{context_info if context_info else 'No specific context found. Guide user to official websites.'}

KEY CONTACT INFORMATION:
- Emergency: +27 6830 38144
- Email: cons.joburg@mea.gov.in
- VFS Johannesburg: https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/

LANGUAGE EXAMPLES:
- Hindi: "मैं आपकी मदद करने के लिए तैयार हूं"
- Afrikaans: "Ek is gereed om jou te help"
- Zulu: "Ngilungele ukukusiza"

Always maintain formal, professional tone and cite official sources."""
    
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    chat_instance = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=system_message
    ).with_model("openai", llm_model)
    
    user_msg_content = []
    if request.image_base64:
        image_content = ImageContent(image_base64=request.image_base64)
        user_msg_content.append(image_content)
    
    user_message = UserMessage(
        text=request.message,
        file_contents=user_msg_content if user_msg_content else None
    )
    
    try:
        bot_response = await chat_instance.send_message(user_message)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI service error: {str(e)}"
        )
    
    message_entry = {
        "id": str(uuid.uuid4()),
        "role": "user",
        "content": request.message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    bot_message_entry = {
        "id": str(uuid.uuid4()),
        "role": "assistant",
        "content": bot_response,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$push": {"messages": {"$each": [message_entry, bot_message_entry]}}}
    )
    
    current_step = session.get('step', 'register')
    
    return ChatResponse(
        session_id=session_id,
        response=bot_response,
        step=current_step
    )

@router.post("/document-scan")
async def document_scan(request: DocumentScanRequest):
    db = await get_database()
    
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    
    chat_instance = LlmChat(
        api_key=api_key,
        session_id=str(uuid.uuid4()),
        system_message=f"""You are a document processing AI. Extract all information from this {request.document_type}.
        Return the data in JSON format with fields like: full_name, date_of_birth, document_number, nationality, etc."""
    ).with_model("openai", "gpt-5.2")
    
    image_content = ImageContent(image_base64=request.image_base64)
    user_message = UserMessage(
        text=f"Extract all information from this {request.document_type} document.",
        file_contents=[image_content]
    )
    
    try:
        extracted_data = await chat_instance.send_message(user_message)
        
        await db.chat_sessions.update_one(
            {"id": request.session_id},
            {"$set": {"extracted_data": extracted_data}}
        )
        
        return {"success": True, "extracted_data": extracted_data}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document scan error: {str(e)}"
        )

@router.post("/form-submit")
async def form_submit(form: FormData):
    db = await get_database()
    
    await db.chat_sessions.update_one(
        {"id": form.session_id},
        {
            "$set": {
                "form_data": form.form_data,
                "status": "submitted",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "step": "sign"
            }
        }
    )
    
    return {"success": True, "message": "Form submitted successfully"}

@router.get("/session/{session_id}")
async def get_session(session_id: str):
    db = await get_database()
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return session

@router.post("/voice-input")
async def voice_input(
    audio_file: UploadFile = File(...),
    session_id: str = None
):
    return {"success": True, "message": "Voice processing (placeholder for now)"}