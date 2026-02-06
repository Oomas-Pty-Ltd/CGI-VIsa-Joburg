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
from knowledge_scraper import get_realtime_knowledge, search_knowledge
from voice_service import voice_service
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/consular", tags=["consular"])

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    company_id: Optional[str] = None
    user_id: Optional[str] = None
    image_base64: Optional[str] = None
    enable_voice: Optional[bool] = False
    language: Optional[str] = "en"

class ChatResponse(BaseModel):
    session_id: str
    response: str
    step: str
    audio_base64: Optional[str] = None

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
    
    session = await db.chat_sessions.find_one(
        {"id": session_id}, 
        {"_id": 0, "id": 1, "user_id": 1, "company_id": 1, "step": 1, "created_at": 1}
    )
    
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
    
    # Get real-time knowledge base from official sources
    knowledge_base = await get_realtime_knowledge()
    context_info = search_knowledge(request.message, knowledge_base)
    
    # Build enhanced prompt with official source context
    system_message = f"""You are Seva Setu Bot, an ADVANCED AI-powered consular assistant with learning and analytical capabilities.

CORE CAPABILITIES:
1. **Real-time Learning**: Analyze user patterns and adapt responses
2. **Context Awareness**: Remember conversation history and user preferences
3. **Intelligent Analysis**: Use AI to provide personalized recommendations
4. **Multi-modal Processing**: Handle text, images, and documents intelligently

RESPONSE FORMAT - ALWAYS USE MARKDOWN:
- Use **bold** for important points
- Use bullet points (•) for lists
- Use numbered lists (1., 2., 3.) for steps
- Use --- for section breaks
- Use > for important quotes/notices
- Use proper spacing and line breaks

CRITICAL LANGUAGE INSTRUCTIONS:
1. ALWAYS respond in the EXACT SAME LANGUAGE and SCRIPT the user writes in
2. Hindi (मुझे) → Respond in Devanagari script (मैं आपकी मदद...)
3. Tamil (நான்) → Respond in Tamil script (நான் உங்களுக்கு...)
4. English → Respond in English
5. NEVER romanize native scripts

INTELLIGENT RESPONSE STRUCTURE:
```
**[Personalized Greeting]**

**Your Query:** [Summarize user's request]

**Here's what I found for you:**

1. **[Main Point]**
   • Detail 1
   • Detail 2
   
2. **[Second Point]**
   • Detail 1
   • Detail 2

---

**📞 Official Contact:**
• Emergency: +27 6830 38144
• Email: cons.joburg@mea.gov.in

---

**🤔 Did I help you?**
Please rate my response and share feedback for continuous improvement.
```

REAL-TIME OFFICIAL DATA (LIVE SCRAPED):
{context_info if context_info else 'Accessing live data from official sources...'}

LEARNING & ANALYSIS:
- Track user's language preference
- Note frequent queries
- Adapt response complexity to user level
- Provide proactive suggestions based on query patterns

Always cite sources, use proper formatting, and ask for feedback."""
    
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
    
    # Generate voice response if requested
    audio_base64 = None
    if request.enable_voice:
        try:
            # Detect language from message
            lang_code = request.language or "en"
            audio_base64 = await voice_service.text_to_speech(bot_response, lang_code)
        except Exception as e:
            print(f"Voice generation failed: {e}")
    
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "has_audio": audio_base64 is not None
    }
    
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$push": {"messages": {"$each": [message_entry, bot_message_entry]}}}
    )
    
    current_step = session.get('step', 'register')
    
    return ChatResponse(
        session_id=session_id,
        response=bot_response,
        step=current_step,
        audio_base64=audio_base64
    )

@router.post("/document-scan")
async def document_scan(request: DocumentScanRequest):
    db = await get_database()
    
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    
    chat_instance = LlmChat(
        api_key=api_key,
        session_id=str(uuid.uuid4()),
        system_message=f"""You are a document processing AI for Seva Setu Bot.

TASK: Extract ALL information from this {request.document_type} document in ANY language.

INSTRUCTIONS:
1. Read the document text in its ORIGINAL language (Hindi, English, Afrikaans, Zulu, Tamil, etc.)
2. Identify key fields: Name, Date of Birth, Document Number, Address, Nationality, Issue Date, Expiry Date, etc.
3. Translate ALL extracted information to ENGLISH for form filling
4. Return data in strict JSON format

OUTPUT FORMAT (MUST be valid JSON):
{{
  "original_language": "detected language",
  "document_type": "{request.document_type}",
  "extracted_fields": {{
    "full_name": "translated name",
    "full_name_original": "original script name",
    "date_of_birth": "YYYY-MM-DD",
    "document_number": "extracted number",
    "nationality": "country",
    "address": "translated address",
    "issue_date": "YYYY-MM-DD",
    "expiry_date": "YYYY-MM-DD",
    "place_of_birth": "city, country"
  }},
  "confidence_score": "high/medium/low",
  "translation_notes": "any important notes"
}}

Be accurate and thorough."""
    ).with_model("openai", "gpt-5.2")
    
    image_content = ImageContent(image_base64=request.image_base64)
    user_message = UserMessage(
        text=f"Extract all information from this {request.document_type}. Translate to English if needed.",
        file_contents=[image_content]
    )
    
    try:
        extracted_data = await chat_instance.send_message(user_message)
        
        # Save extracted data to session
        await db.chat_sessions.update_one(
            {"id": request.session_id},
            {
                "$set": {
                    "extracted_data": extracted_data,
                    "document_type": request.document_type,
                    "extraction_timestamp": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        return {
            "success": True,
            "extracted_data": extracted_data,
            "message": "Document processed successfully. Data extracted and translated to English for form filling."
        }
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


# =====================================================================
# WIDGET ENDPOINT - Concise, focused responses for embedded widget
# =====================================================================

class WidgetChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: Optional[str] = "concise"  # concise or detailed

class WidgetChatResponse(BaseModel):
    session_id: str
    response: str

@router.post("/chat-widget", response_model=WidgetChatResponse)
async def chat_widget(request: WidgetChatRequest):
    """
    Widget-specific chat endpoint with concise, focused responses.
    Designed for embedded chat widgets on external websites.
    """
    db = await get_database()
    
    session_id = request.session_id or str(uuid.uuid4())
    
    # Get or create session - only fetch required fields
    session = await db.chat_sessions.find_one(
        {"id": session_id}, 
        {"_id": 0, "id": 1, "user_id": 1, "source": 1, "created_at": 1}
    )
    if not session:
        session = {
            "id": session_id,
            "user_id": "widget_guest",
            "messages": [],
            "source": "widget",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_sessions.insert_one(session)
    
    # Concise system prompt - KEY TO BETTER BEHAVIOR
    system_message = """You are Seva Setu, a helpful consular assistant for the Consulate General of India, Johannesburg.

CRITICAL RULES:
1. WAIT for user's question. DO NOT volunteer information they didn't ask for.
2. Give SHORT, DIRECT answers (2-4 sentences max for simple questions).
3. Only provide step-by-step details when user asks "how to" or "what are the steps".
4. If user asks a specific question, answer ONLY that question.
5. Use bullet points only when listing multiple items.
6. NO lengthy introductions or conclusions.
7. NO "Is there anything else?" - let user ask.

RESPONSE LENGTH GUIDE:
- Simple question (what is OCI?) → 2-3 sentences
- Process question (how to apply?) → Numbered steps, brief
- Document question (what documents?) → Bullet list only

LANGUAGE: Match the user's language. Hindi → Hindi, English → English.

EXAMPLE GOOD RESPONSES:

User: "What is OCI?"
You: "OCI (Overseas Citizen of India) is a lifelong visa for foreign nationals of Indian origin. It allows unlimited travel to India without needing separate visas."

User: "How to renew passport?"
You: "**Passport Renewal Steps:**
1. Book appointment on passportindia.gov.in
2. Fill online application form
3. Visit with: old passport, photos, address proof
4. Pay fee (R800-1200)
Processing: 4-6 weeks"

User: "Office timings?"
You: "**CGI Johannesburg Hours:**
Mon-Fri: 9:00 AM - 5:30 PM
Consular services: 9:00 AM - 12:30 PM
Closed on Indian & SA public holidays"

NOW RESPOND TO THE USER'S QUERY CONCISELY:"""
    
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    chat_instance = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=system_message
    ).with_model("openai", "gpt-5.2")
    
    user_message = UserMessage(text=request.message)
    
    try:
        bot_response = await chat_instance.send_message(user_message)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Service error: {str(e)}"
        )
    
    # Store messages
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$push": {"messages": {
            "$each": [
                {"role": "user", "content": request.message, "timestamp": datetime.now(timezone.utc).isoformat()},
                {"role": "assistant", "content": bot_response, "timestamp": datetime.now(timezone.utc).isoformat()}
            ]
        }}}
    )
    
    return WidgetChatResponse(
        session_id=session_id,
        response=bot_response
    )
