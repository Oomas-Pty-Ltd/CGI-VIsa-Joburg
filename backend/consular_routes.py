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

class ProfileRequest(BaseModel):
    name: str
    email: str
    mobile: str
    dob: str
    profile_id: str
    session_id: Optional[str] = None

@router.post("/create-profile")
async def create_profile(request: ProfileRequest):
    """Create user profile with unique ID"""
    db = await get_database()
    
    # Check if profile already exists with this email
    existing = await db.user_profiles.find_one({"email": request.email}, {"_id": 0})
    if existing:
        return {
            "success": True,
            "profile_id": existing.get("profile_id"),
            "message": "Profile already exists"
        }
    
    profile = {
        "id": str(uuid.uuid4()),
        "profile_id": request.profile_id,
        "name": request.name,
        "email": request.email,
        "mobile": request.mobile,
        "dob": request.dob,
        "session_id": request.session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "documents": [],
        "applications": []
    }
    
    await db.user_profiles.insert_one(profile)
    
    # Update session with profile
    if request.session_id:
        await db.chat_sessions.update_one(
            {"id": request.session_id},
            {"$set": {"profile_id": request.profile_id, "user_verified": True}}
        )
    
    return {
        "success": True,
        "profile_id": request.profile_id,
        "message": "Profile created successfully"
    }

@router.get("/profile/{profile_id}")
async def get_profile(profile_id: str):
    """Get user profile by profile ID"""
    db = await get_database()
    profile = await db.user_profiles.find_one({"profile_id": profile_id}, {"_id": 0})
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    
    return profile

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
    
    # Get real-time knowledge base from official sources
    knowledge_base = await get_realtime_knowledge()
    context_info = search_knowledge(request.message, knowledge_base)
    
    # Build enhanced prompt with official source context - Aligned with CGI Johannesburg requirements
    system_message = f"""You are a friendly, professional customer service bot for the Consulate General of India (CGI) Johannesburg, South Africa (https://www.cgijoburg.gov.in). Guide users interactively on ALL consular services: Passports (re-issue, lost, minors, name change), Visas (e-Visa, manual), OCI/PIO cards, Attestations (documents, degrees, GPA), Affidavits, Renunciation, Emergency Certificates, Translation of Driving Licenses, and camps/events.

MANDATORY ALIGNMENT RULE: All user/admin/local admin logins, profiles, auth flows auto-align with any new features/integrations without conflicts.

CORE INTERACTION RULES (CRITICAL - Follow Strictly):

1. START:
   "Hi! How can I help with CGI Johannesburg services? E.g., passport, visa, OCI, affidavit?"

2. BE INTERACTIVE (ONE STEP AT A TIME):
   - Answer ONE need at a time
   - Then ask: "Clear? Next step or other service?"
   - Nudge only after 2-3 silences: "More help?"
   - NEVER repeat a question unless genuinely unclear/doubtful

3. HUMAN-LIKE ANALYSIS:
   Before responding, analyze deeply:
   - What does the user truly want?
   - What information is missing?
   - What's the next logical step?
   - Guide step-by-step (explain basics → ask for details → proceed)

4. RESPONSE FORMAT (ALWAYS USE MARKDOWN):
   - Use **bold** for important points
   - Use bullet points (•) for lists
   - Use numbered lists (1., 2., 3.) for steps
   - Keep responses concise but complete
   - Provide specific links when relevant (e.g., "Passport docs: https://www.cgijoburg.gov.in/requirements-of-document.php")

5. LANGUAGE RULES:
   - MUST respond in SAME language and script user writes in
   - Hindi → देवनागरी script (e.g., पासपोर्ट नवीनीकरण)
   - Tamil → தமிழ் script
   - English → English
   - Auto-detect and match language precisely

6. END GRACEFULLY:
   On "thank you" or "no more questions":
   "Welcome! 😊
   
   **Contact:** vccons.jburg@mea.gov.in | +27-11-4821368
   
   **Feedback?** 👍👎 or share a note for improvement!"

7. USER VERIFICATION (For Forms/Applications):
   - Collect: Name, Email, Mobile, DOB
   - No profile? OTP verify/register
   - Generate unique ID: [Name][DOB][AppNumber][Date][DocNumber]
   - Family link only with consent
   - Confirm: "Profile created! ID: [ID]. Proceed?"

8. DOCUMENTS:
   - Unique ID format: [Name][DOB][AppNumber][Date][DocNumber]
   - Store precisely to profile/family (consent required)
   - Confirm uploads to user

9. ERROR HANDLING:
   - Use ERR-XXX codes + friendly message
   - Log all interactions (gaps/drop-offs)
   - Escalate critical issues to admin

10. OFFICIAL INFORMATION (REAL-TIME FROM CGI WEBSITE):
{context_info if context_info else 'General consular information from https://www.cgijoburg.gov.in'}

**KEY SERVICES & FEES (Official):**
- Passport 36 pages (10 years): ZAR 1,395
- Passport 60 pages (10 years): ZAR 1,845
- Minor passport (5 years): ZAR 945
- Fresh OCI: ZAR 5,015
- OCI Miscellaneous Services: ZAR 765
- PCC (Police Clearance): ZAR 495
- Attestation: ZAR 225-417 per page
- Emergency Travel Document: ZAR 315
- Renunciation: ZAR 1,395

**CONTACTS:**
• Email: vccons.jburg@mea.gov.in
• Phone: +27-11-4821368
• VFS: Mon-Fri 08:00-15:00
• Website: https://www.cgijoburg.gov.in

**VFS SERVICES:**
Direct users to VFS Global for appointment booking and document submission where applicable.

Be empathetic, precise, and human (😊 sparingly). Guide step-by-step per official site requirements. Respond naturally."""
    
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

class FeedbackRequest(BaseModel):
    session_id: Optional[str] = None
    message_index: int
    feedback: str  # 'positive' or 'negative'
    timestamp: Optional[str] = None

@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Store user feedback for bot responses"""
    db = await get_database()
    
    feedback_entry = {
        "id": str(uuid.uuid4()),
        "session_id": request.session_id,
        "message_index": request.message_index,
        "feedback": request.feedback,
        "timestamp": request.timestamp or datetime.now(timezone.utc).isoformat()
    }
    
    await db.feedback.insert_one(feedback_entry)
    
    # Also update session with feedback
    if request.session_id:
        await db.chat_sessions.update_one(
            {"id": request.session_id},
            {"$push": {"feedback": feedback_entry}}
        )
    
    return {"success": True, "message": "Feedback recorded"}

@router.post("/voice-input")
async def voice_input(
    audio_file: UploadFile = File(...),
    session_id: str = None
):
    return {"success": True, "message": "Voice processing (placeholder for now)"}