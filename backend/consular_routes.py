from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import base64
import os
from database import get_database
from auth_utils import verify_token
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from presidio_service import mask_pii
from knowledge_scraper import get_realtime_knowledge, search_knowledge
from voice_service import voice_service
from structured_conversation import process_user_input, get_or_create_conversation
from admin_config import get_admin_config, log_exception
from application_tracking import create_application, get_user_applications, get_application
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
    profile_id: Optional[str] = None
    user_name: Optional[str] = None
    use_structured_flow: Optional[bool] = True  # New: Use structured conversation

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

# Enhanced Profile with Family Support
class ProfileRequest(BaseModel):
    name: str
    email: str
    mobile: str
    dob: str
    profile_id: str
    session_id: Optional[str] = None
    # Extended fields for comprehensive profile
    gender: Optional[str] = None
    nationality: Optional[str] = "Indian"
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    spouse_name: Optional[str] = None
    place_of_birth: Optional[str] = None
    current_address: Optional[str] = None
    permanent_address: Optional[str] = None
    passport_number: Optional[str] = None
    aadhar_number: Optional[str] = None
    pan_number: Optional[str] = None
    emergency_contact: Optional[str] = None
    occupation: Optional[str] = None

class FamilyMemberRequest(BaseModel):
    parent_profile_id: str
    name: str
    relationship: str  # spouse, child, parent, sibling
    dob: str
    gender: Optional[str] = None
    passport_number: Optional[str] = None

class DocumentUploadRequest(BaseModel):
    profile_id: str
    document_type: str
    document_name: str
    is_original: bool = False
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    document_number: Optional[str] = None
    issuing_authority: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    file_base64: Optional[str] = None

# Document validity rules
DOCUMENT_VALIDITY_RULES = {
    "passport": {"validity_type": "expiry", "copy_valid_days": 90},
    "birth_certificate": {"validity_type": "permanent", "copy_valid_days": 90},
    "death_certificate": {"validity_type": "permanent", "copy_valid_days": 90},
    "marriage_certificate": {"validity_type": "affidavit", "copy_valid_days": 90, "needs_affidavit": True},
    "driving_license": {"validity_type": "expiry", "copy_valid_days": 90},
    "national_id": {"validity_type": "permanent", "copy_valid_days": 90},
    "pan_card": {"validity_type": "permanent", "copy_valid_days": 90},
    "voter_card": {"validity_type": "permanent", "copy_valid_days": 90},
    "address_proof": {"validity_type": "expiry", "copy_valid_days": 90},
    "photograph": {"validity_type": "expiry", "max_age_days": 180, "copy_valid_days": 90},
    "police_report": {"validity_type": "expiry", "max_age_days": 90, "copy_valid_days": 90},
    "affidavit": {"validity_type": "expiry", "max_age_days": 90, "copy_valid_days": 90}
}

def calculate_document_validity(doc_type: str, is_original: bool, issue_date: str, expiry_date: str = None) -> Dict:
    """Calculate document validity status"""
    rules = DOCUMENT_VALIDITY_RULES.get(doc_type, {"validity_type": "expiry", "copy_valid_days": 90})
    now = datetime.now(timezone.utc)
    
    result = {
        "is_valid": True,
        "validity_type": rules["validity_type"],
        "status": "active",
        "message": "",
        "days_remaining": None,
        "needs_affidavit": rules.get("needs_affidavit", False)
    }
    
    def parse_date(date_str):
        """Parse date string and ensure it's timezone aware"""
        if not date_str:
            return None
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except:
            # Try parsing as simple date
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                return dt.replace(tzinfo=timezone.utc)
            except:
                return None
    
    if not is_original:
        # Copy validity - 90 days from issue
        issue = parse_date(issue_date)
        if issue:
            copy_expiry = issue + timedelta(days=rules.get("copy_valid_days", 90))
            days_remaining = (copy_expiry - now).days
            
            if days_remaining <= 0:
                result["is_valid"] = False
                result["status"] = "expired"
                result["message"] = f"Copy expired. Valid only for {rules.get('copy_valid_days', 90)} days from issue."
            elif days_remaining <= 15:
                result["status"] = "expiring_soon"
                result["message"] = f"Copy expires in {days_remaining} days. Please renew."
            else:
                result["message"] = f"Copy valid for {days_remaining} more days."
            result["days_remaining"] = max(0, days_remaining)
    else:
        # Original document validity
        if rules["validity_type"] == "permanent":
            result["message"] = "Original document - No expiry (permanent)"
            result["status"] = "permanent"
        elif rules["validity_type"] == "affidavit":
            result["message"] = "Original document - May need affidavit for reproduction"
            result["status"] = "active"
            if rules.get("needs_affidavit"):
                result["needs_affidavit"] = True
        elif expiry_date:
            expiry = parse_date(expiry_date)
            if expiry:
                days_remaining = (expiry - now).days
                
                if days_remaining <= 0:
                    result["is_valid"] = False
                    result["status"] = "expired"
                    result["message"] = f"Document expired on {expiry_date}"
                elif days_remaining <= 30:
                    result["status"] = "expiring_soon"
                    result["message"] = f"Expires in {days_remaining} days. Please renew."
                else:
                    result["message"] = f"Valid until {expiry_date}"
                result["days_remaining"] = max(0, days_remaining)
    
    return result

@router.post("/create-profile")
async def create_profile(request: ProfileRequest):
    """Create comprehensive user profile with unique ID"""
    db = await get_database()
    
    # Check if profile already exists with this email
    existing = await db.user_profiles.find_one({"email": request.email}, {"_id": 0})
    if existing:
        return {
            "success": True,
            "profile_id": existing.get("profile_id"),
            "message": "Profile already exists",
            "profile": existing
        }
    
    profile = {
        "id": str(uuid.uuid4()),
        "profile_id": request.profile_id,
        "name": request.name,
        "email": request.email,
        "mobile": request.mobile,
        "dob": request.dob,
        "gender": request.gender,
        "nationality": request.nationality,
        "father_name": request.father_name,
        "mother_name": request.mother_name,
        "spouse_name": request.spouse_name,
        "place_of_birth": request.place_of_birth,
        "current_address": request.current_address,
        "permanent_address": request.permanent_address,
        "passport_number": request.passport_number,
        "aadhar_number": request.aadhar_number,
        "pan_number": request.pan_number,
        "emergency_contact": request.emergency_contact,
        "occupation": request.occupation,
        "session_id": request.session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "documents": [],
        "applications": [],
        "family_members": [],
        "is_verified": False
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

@router.put("/profile/{profile_id}")
async def update_profile(profile_id: str, request: ProfileRequest):
    """Update existing profile"""
    db = await get_database()
    
    update_data = {
        "name": request.name,
        "email": request.email,
        "mobile": request.mobile,
        "dob": request.dob,
        "gender": request.gender,
        "nationality": request.nationality,
        "father_name": request.father_name,
        "mother_name": request.mother_name,
        "spouse_name": request.spouse_name,
        "place_of_birth": request.place_of_birth,
        "current_address": request.current_address,
        "permanent_address": request.permanent_address,
        "passport_number": request.passport_number,
        "aadhar_number": request.aadhar_number,
        "pan_number": request.pan_number,
        "emergency_contact": request.emergency_contact,
        "occupation": request.occupation,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Remove None values
    update_data = {k: v for k, v in update_data.items() if v is not None}
    
    result = await db.user_profiles.update_one(
        {"profile_id": profile_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {"success": True, "message": "Profile updated successfully"}

@router.post("/profile/{profile_id}/family")
async def add_family_member(profile_id: str, request: FamilyMemberRequest):
    """Add family member to profile"""
    db = await get_database()
    
    # Generate family member ID
    family_id = f"FAM-{request.name[:4].upper()}-{request.dob.replace('-', '')}-{str(uuid.uuid4())[:4].upper()}"
    
    family_member = {
        "id": family_id,
        "name": request.name,
        "relationship": request.relationship,
        "dob": request.dob,
        "gender": request.gender,
        "passport_number": request.passport_number,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "documents": []
    }
    
    result = await db.user_profiles.update_one(
        {"profile_id": profile_id},
        {"$push": {"family_members": family_member}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {
        "success": True,
        "family_member_id": family_id,
        "message": f"Family member {request.name} added successfully"
    }

@router.get("/profile/{profile_id}/family")
async def get_family_members(profile_id: str):
    """Get all family members for a profile"""
    db = await get_database()
    profile = await db.user_profiles.find_one({"profile_id": profile_id}, {"_id": 0, "family_members": 1})
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {
        "success": True,
        "family_members": profile.get("family_members", [])
    }

@router.post("/profile/{profile_id}/document")
async def add_document(profile_id: str, request: DocumentUploadRequest):
    """Add document to profile with validity tracking"""
    db = await get_database()
    
    # Generate document unique ID: [ProfileID]-[DocType]-[Date]-[Hash]
    doc_date = datetime.now(timezone.utc).strftime("%Y%m%d")
    doc_hash = str(uuid.uuid4())[:6].upper()
    document_id = f"{profile_id}-{request.document_type.upper()[:4]}-{doc_date}-{doc_hash}"
    
    # Calculate validity
    validity = calculate_document_validity(
        request.document_type,
        request.is_original,
        request.issue_date or datetime.now(timezone.utc).isoformat(),
        request.expiry_date
    )
    
    document = {
        "id": document_id,
        "document_type": request.document_type,
        "document_name": request.document_name,
        "document_number": request.document_number,
        "is_original": request.is_original,
        "issue_date": request.issue_date,
        "expiry_date": request.expiry_date,
        "issuing_authority": request.issuing_authority,
        "extracted_data": request.extracted_data,
        "validity": validity,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "has_file": request.file_base64 is not None
    }
    
    # Store file separately if provided
    if request.file_base64:
        await db.document_files.insert_one({
            "document_id": document_id,
            "profile_id": profile_id,
            "file_base64": request.file_base64,
            "uploaded_at": datetime.now(timezone.utc).isoformat()
        })
    
    result = await db.user_profiles.update_one(
        {"profile_id": profile_id},
        {"$push": {"documents": document}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    return {
        "success": True,
        "document_id": document_id,
        "validity": validity,
        "message": f"Document added successfully. Status: {validity['status']}"
    }

@router.get("/profile/{profile_id}/documents")
async def get_documents(profile_id: str):
    """Get all documents for a profile with current validity status"""
    db = await get_database()
    profile = await db.user_profiles.find_one({"profile_id": profile_id}, {"_id": 0, "documents": 1})
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    documents = profile.get("documents", [])
    
    # Recalculate validity for each document
    for doc in documents:
        doc["validity"] = calculate_document_validity(
            doc.get("document_type", ""),
            doc.get("is_original", False),
            doc.get("issue_date"),
            doc.get("expiry_date")
        )
    
    # Summary
    summary = {
        "total": len(documents),
        "valid": sum(1 for d in documents if d["validity"]["is_valid"]),
        "expired": sum(1 for d in documents if not d["validity"]["is_valid"]),
        "expiring_soon": sum(1 for d in documents if d["validity"]["status"] == "expiring_soon"),
        "needs_affidavit": sum(1 for d in documents if d["validity"].get("needs_affidavit", False))
    }
    
    return {
        "success": True,
        "documents": documents,
        "summary": summary
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

# =============================================================================
# INTERACTIVE FORM-FILLING SYSTEM
# =============================================================================

# Miscellaneous services types (from official CGI form)
MISC_SERVICE_TYPES = [
    "Birth Certificate",
    "Marriage Certificate", 
    "Death Certificate",
    "NRI Certificate",
    "One & the Same Person Certificate",
    "Life Certificate",
    "Attestation",
    "NOC (No Objection Certificate)",
    "GPA Certificate",
    "PCC (Police Clearance - Foreign National)"
]

# Form templates for different services
FORM_TEMPLATES = {
    # =========================================================================
    # MISCELLANEOUS SERVICES FORM (Official CGI Johannesburg Form)
    # =========================================================================
    "misc_services": {
        "name": "Miscellaneous Services Application",
        "description": "Official CGI Johannesburg form for Birth/Marriage/Death/NRI/One & the Same/Life/Attestation/NOC/GPA Certificate/PCC",
        "total_steps": 20,
        "fee_range": "ZAR 225 - 495",
        "processing_time": "1-4 weeks",
        "fields": [
            # Service Selection
            {"id": "service_type", "label": "Service Required (Birth/Marriage/Death/NRI/One & the Same/Life/Attestation/NOC/GPA Certificate/PCC)", "source": "manual", "required": True, "type": "select", "options": MISC_SERVICE_TYPES},
            # Applicant Details
            {"id": "full_name", "label": "Full Name", "source": "profile.name", "required": True},
            {"id": "nationality", "label": "Nationality of Applicant", "source": "profile.nationality", "required": True},
            {"id": "father_name_nationality", "label": "Full Name of Father & Nationality", "source": "profile.father_name", "required": True, "note": "Format: Name, Nationality"},
            {"id": "mother_name_nationality", "label": "Full Name of Mother & Nationality", "source": "profile.mother_name", "required": True, "note": "Format: Name, Nationality"},
            {"id": "dob", "label": "Date of Birth", "source": "profile.dob", "required": True},
            {"id": "place_country_birth", "label": "Place & Country of Birth", "source": "profile.place_of_birth", "required": True},
            {"id": "spouse_name_nationality", "label": "Name of Spouse & Nationality", "source": "profile.spouse_name", "required": False},
            {"id": "present_address_sa", "label": "Present Address in South Africa", "source": "profile.current_address", "required": True},
            {"id": "phone_number", "label": "Phone Number", "source": "profile.mobile", "required": True},
            {"id": "email_address", "label": "Email Address", "source": "profile.email", "required": True},
            {"id": "profession_employer", "label": "Profession/Employer's Details", "source": "profile.occupation", "required": True},
            # Visa/Immigration Details
            {"id": "visa_immigration_status", "label": "Visa / Immigration Status", "source": "manual", "required": True},
            {"id": "permanent_address_india", "label": "Permanent Address in India", "source": "profile.permanent_address", "required": True},
            # Passport Details
            {"id": "passport_number", "label": "Passport Number", "source": "profile.passport_number", "required": True},
            {"id": "passport_issue_date", "label": "Passport Date of Issue", "source": "document.passport.issue_date", "required": True},
            {"id": "passport_validity", "label": "Passport Validity/Expiry Date", "source": "document.passport.expiry_date", "required": True},
            {"id": "passport_place_of_issue", "label": "Passport Place of Issue", "source": "manual", "required": True},
            # Registration Details
            {"id": "mission_registration", "label": "Are you registered with Indian Mission? (If yes, provide registration number and date)", "source": "manual", "required": False},
            # Declaration
            {"id": "declaration_place", "label": "Declaration Place (City where you're signing)", "source": "manual", "required": True}
        ]
    },
    
    # =========================================================================
    # BIRTH CERTIFICATE (Using Misc Form)
    # =========================================================================
    "birth_certificate": {
        "name": "Birth Certificate Application",
        "description": "Registration of birth for Indian citizens born abroad",
        "total_steps": 22,
        "fee": "ZAR 405",
        "processing_time": "1-4 weeks",
        "fields": [
            # Service pre-selected
            {"id": "service_type", "label": "Service Type", "source": "auto", "required": True, "default": "Birth Certificate"},
            # Child Details
            {"id": "child_full_name", "label": "Child's Full Name", "source": "manual", "required": True},
            {"id": "child_dob", "label": "Child's Date of Birth", "source": "manual", "required": True},
            {"id": "child_place_birth", "label": "Child's Place & Country of Birth", "source": "manual", "required": True},
            {"id": "child_gender", "label": "Child's Gender", "source": "manual", "required": True},
            # Father (Applicant) Details
            {"id": "father_name", "label": "Father's Full Name", "source": "profile.name", "required": True},
            {"id": "father_nationality", "label": "Father's Nationality", "source": "profile.nationality", "required": True},
            {"id": "father_passport", "label": "Father's Passport Number", "source": "profile.passport_number", "required": True},
            {"id": "father_passport_issue", "label": "Father's Passport Issue Date", "source": "document.passport.issue_date", "required": True},
            {"id": "father_passport_expiry", "label": "Father's Passport Expiry Date", "source": "document.passport.expiry_date", "required": True},
            # Mother Details
            {"id": "mother_name", "label": "Mother's Full Name", "source": "family.spouse.name", "required": True},
            {"id": "mother_nationality", "label": "Mother's Nationality", "source": "manual", "required": True},
            {"id": "mother_passport", "label": "Mother's Passport Number", "source": "family.spouse.passport_number", "required": False},
            # Parents Marriage Details
            {"id": "marriage_date", "label": "Parents' Marriage Date", "source": "document.marriage_certificate.issue_date", "required": True},
            {"id": "marriage_place", "label": "Parents' Marriage Place", "source": "manual", "required": True},
            # Contact Details
            {"id": "present_address_sa", "label": "Present Address in South Africa", "source": "profile.current_address", "required": True},
            {"id": "phone_number", "label": "Phone Number", "source": "profile.mobile", "required": True},
            {"id": "email_address", "label": "Email Address", "source": "profile.email", "required": True},
            {"id": "permanent_address_india", "label": "Permanent Address in India", "source": "profile.permanent_address", "required": True},
            # Immigration & Declaration
            {"id": "visa_status", "label": "Visa / Immigration Status", "source": "manual", "required": True},
            {"id": "mission_registration", "label": "Indian Mission Registration Number (if registered)", "source": "manual", "required": False},
            {"id": "declaration_place", "label": "Declaration Place", "source": "manual", "required": True}
        ]
    },
    
    # =========================================================================
    # MARRIAGE CERTIFICATE (Using Misc Form)
    # =========================================================================
    "marriage_certificate": {
        "name": "Marriage Certificate Application",
        "description": "Registration of marriage for Indian citizens",
        "total_steps": 24,
        "fee": "ZAR 492",
        "processing_time": "1-2 weeks",
        "fields": [
            {"id": "service_type", "label": "Service Type", "source": "auto", "required": True, "default": "Marriage Certificate"},
            # Groom Details
            {"id": "groom_name", "label": "Groom's Full Name", "source": "profile.name", "required": True},
            {"id": "groom_nationality", "label": "Groom's Nationality", "source": "profile.nationality", "required": True},
            {"id": "groom_dob", "label": "Groom's Date of Birth", "source": "profile.dob", "required": True},
            {"id": "groom_place_birth", "label": "Groom's Place of Birth", "source": "profile.place_of_birth", "required": True},
            {"id": "groom_father_name", "label": "Groom's Father's Name & Nationality", "source": "profile.father_name", "required": True},
            {"id": "groom_mother_name", "label": "Groom's Mother's Name & Nationality", "source": "profile.mother_name", "required": True},
            {"id": "groom_passport", "label": "Groom's Passport Number", "source": "profile.passport_number", "required": True},
            {"id": "groom_passport_issue", "label": "Groom's Passport Issue Date", "source": "document.passport.issue_date", "required": True},
            {"id": "groom_passport_expiry", "label": "Groom's Passport Expiry Date", "source": "document.passport.expiry_date", "required": True},
            # Bride Details
            {"id": "bride_name", "label": "Bride's Full Name", "source": "family.spouse.name", "required": True},
            {"id": "bride_nationality", "label": "Bride's Nationality", "source": "manual", "required": True},
            {"id": "bride_dob", "label": "Bride's Date of Birth", "source": "family.spouse.dob", "required": True},
            {"id": "bride_place_birth", "label": "Bride's Place of Birth", "source": "manual", "required": True},
            {"id": "bride_father_name", "label": "Bride's Father's Name & Nationality", "source": "manual", "required": True},
            {"id": "bride_mother_name", "label": "Bride's Mother's Name & Nationality", "source": "manual", "required": True},
            {"id": "bride_passport", "label": "Bride's Passport Number", "source": "family.spouse.passport_number", "required": False},
            # Marriage Details
            {"id": "marriage_date", "label": "Date of Marriage", "source": "manual", "required": True},
            {"id": "marriage_place", "label": "Place of Marriage", "source": "manual", "required": True},
            # Contact & Address
            {"id": "present_address_sa", "label": "Present Address in South Africa", "source": "profile.current_address", "required": True},
            {"id": "phone_number", "label": "Phone Number", "source": "profile.mobile", "required": True},
            {"id": "email_address", "label": "Email Address", "source": "profile.email", "required": True},
            {"id": "permanent_address_india", "label": "Permanent Address in India", "source": "profile.permanent_address", "required": True},
            {"id": "declaration_place", "label": "Declaration Place", "source": "manual", "required": True}
        ]
    },
    
    # =========================================================================
    # DEATH CERTIFICATE (Using Misc Form)
    # =========================================================================
    "death_certificate": {
        "name": "Death Certificate Application",
        "description": "Registration of death for Indian citizens who died abroad",
        "total_steps": 18,
        "fee": "ZAR 405",
        "processing_time": "1-4 weeks",
        "fields": [
            {"id": "service_type", "label": "Service Type", "source": "auto", "required": True, "default": "Death Certificate"},
            # Deceased Person Details
            {"id": "deceased_name", "label": "Deceased Person's Full Name", "source": "manual", "required": True},
            {"id": "deceased_nationality", "label": "Deceased's Nationality", "source": "manual", "required": True},
            {"id": "deceased_dob", "label": "Deceased's Date of Birth", "source": "manual", "required": True},
            {"id": "deceased_date_of_death", "label": "Date of Death", "source": "manual", "required": True},
            {"id": "deceased_place_of_death", "label": "Place of Death", "source": "manual", "required": True},
            {"id": "deceased_cause_of_death", "label": "Cause of Death", "source": "manual", "required": True},
            {"id": "deceased_passport", "label": "Deceased's Passport Number", "source": "manual", "required": True},
            {"id": "deceased_father_name", "label": "Deceased's Father's Name", "source": "manual", "required": True},
            {"id": "deceased_mother_name", "label": "Deceased's Mother's Name", "source": "manual", "required": True},
            # Applicant Details
            {"id": "applicant_name", "label": "Applicant's Full Name", "source": "profile.name", "required": True},
            {"id": "relationship_to_deceased", "label": "Relationship to Deceased", "source": "manual", "required": True},
            {"id": "applicant_passport", "label": "Applicant's Passport Number", "source": "profile.passport_number", "required": True},
            {"id": "present_address_sa", "label": "Present Address in South Africa", "source": "profile.current_address", "required": True},
            {"id": "phone_number", "label": "Phone Number", "source": "profile.mobile", "required": True},
            {"id": "email_address", "label": "Email Address", "source": "profile.email", "required": True},
            {"id": "permanent_address_india", "label": "Permanent Address in India", "source": "profile.permanent_address", "required": True},
            {"id": "declaration_place", "label": "Declaration Place", "source": "manual", "required": True}
        ]
    },
    
    # =========================================================================
    # ATTESTATION SERVICE (Using Misc Form)
    # =========================================================================
    "attestation": {
        "name": "Document Attestation Application",
        "description": "Attestation of documents by the Consulate",
        "total_steps": 16,
        "fee": "ZAR 225-417 per page",
        "processing_time": "1-2 weeks",
        "fields": [
            {"id": "service_type", "label": "Service Type", "source": "auto", "required": True, "default": "Attestation"},
            {"id": "document_type", "label": "Type of Document to be Attested", "source": "manual", "required": True, "note": "e.g., Educational certificate, Power of Attorney, Affidavit, etc."},
            {"id": "number_of_pages", "label": "Number of Pages to be Attested", "source": "manual", "required": True},
            {"id": "purpose_of_attestation", "label": "Purpose of Attestation", "source": "manual", "required": True},
            # Applicant Details
            {"id": "full_name", "label": "Applicant's Full Name", "source": "profile.name", "required": True},
            {"id": "nationality", "label": "Nationality", "source": "profile.nationality", "required": True},
            {"id": "dob", "label": "Date of Birth", "source": "profile.dob", "required": True},
            {"id": "father_name_nationality", "label": "Father's Name & Nationality", "source": "profile.father_name", "required": True},
            {"id": "mother_name_nationality", "label": "Mother's Name & Nationality", "source": "profile.mother_name", "required": True},
            {"id": "passport_number", "label": "Passport Number", "source": "profile.passport_number", "required": True},
            {"id": "passport_validity", "label": "Passport Validity", "source": "document.passport.expiry_date", "required": True},
            {"id": "present_address_sa", "label": "Present Address in South Africa", "source": "profile.current_address", "required": True},
            {"id": "phone_number", "label": "Phone Number", "source": "profile.mobile", "required": True},
            {"id": "email_address", "label": "Email Address", "source": "profile.email", "required": True},
            {"id": "permanent_address_india", "label": "Permanent Address in India", "source": "profile.permanent_address", "required": True},
            {"id": "declaration_place", "label": "Declaration Place", "source": "manual", "required": True}
        ]
    },
    
    # =========================================================================
    # LIFE CERTIFICATE (Using Misc Form)
    # =========================================================================
    "life_certificate": {
        "name": "Life Certificate Application",
        "description": "Life certificate for pensioners",
        "total_steps": 14,
        "fee": "ZAR 225",
        "processing_time": "1 week",
        "fields": [
            {"id": "service_type", "label": "Service Type", "source": "auto", "required": True, "default": "Life Certificate"},
            {"id": "full_name", "label": "Full Name", "source": "profile.name", "required": True},
            {"id": "nationality", "label": "Nationality", "source": "profile.nationality", "required": True},
            {"id": "dob", "label": "Date of Birth", "source": "profile.dob", "required": True},
            {"id": "father_name_nationality", "label": "Father's Name & Nationality", "source": "profile.father_name", "required": True},
            {"id": "mother_name_nationality", "label": "Mother's Name & Nationality", "source": "profile.mother_name", "required": True},
            {"id": "pension_account_number", "label": "Pension Account Number / PPO Number", "source": "manual", "required": True},
            {"id": "pension_disbursing_authority", "label": "Pension Disbursing Authority/Bank", "source": "manual", "required": True},
            {"id": "passport_number", "label": "Passport Number", "source": "profile.passport_number", "required": True},
            {"id": "passport_validity", "label": "Passport Validity", "source": "document.passport.expiry_date", "required": True},
            {"id": "present_address_sa", "label": "Present Address in South Africa", "source": "profile.current_address", "required": True},
            {"id": "phone_number", "label": "Phone Number", "source": "profile.mobile", "required": True},
            {"id": "email_address", "label": "Email Address", "source": "profile.email", "required": True},
            {"id": "declaration_place", "label": "Declaration Place", "source": "manual", "required": True}
        ]
    },
    
    # =========================================================================
    # PASSPORT SERVICES
    # =========================================================================
    "passport_renewal": {
        "name": "Passport Renewal Application",
        "total_steps": 12,
        "fields": [
            {"id": "full_name", "label": "Full Name", "source": "profile.name", "required": True},
            {"id": "dob", "label": "Date of Birth", "source": "profile.dob", "required": True},
            {"id": "place_of_birth", "label": "Place of Birth", "source": "profile.place_of_birth", "required": True},
            {"id": "gender", "label": "Gender", "source": "profile.gender", "required": True},
            {"id": "current_address", "label": "Current Address", "source": "profile.current_address", "required": True},
            {"id": "permanent_address", "label": "Permanent Address", "source": "profile.permanent_address", "required": True},
            {"id": "father_name", "label": "Father's Name", "source": "profile.father_name", "required": True},
            {"id": "mother_name", "label": "Mother's Name", "source": "profile.mother_name", "required": True},
            {"id": "old_passport_number", "label": "Current Passport Number", "source": "profile.passport_number", "required": True},
            {"id": "old_passport_issue_date", "label": "Passport Issue Date", "source": "document.passport.issue_date", "required": True},
            {"id": "old_passport_expiry_date", "label": "Passport Expiry Date", "source": "document.passport.expiry_date", "required": True},
            {"id": "emergency_contact", "label": "Emergency Contact", "source": "profile.emergency_contact", "required": True}
        ]
    },
    "tourist_visa": {
        "name": "Tourist Visa Application",
        "total_steps": 15,
        "fields": [
            {"id": "full_name", "label": "Full Name", "source": "profile.name", "required": True},
            {"id": "dob", "label": "Date of Birth", "source": "profile.dob", "required": True},
            {"id": "nationality", "label": "Nationality", "source": "profile.nationality", "required": True},
            {"id": "passport_number", "label": "Passport Number", "source": "profile.passport_number", "required": True},
            {"id": "passport_issue_date", "label": "Passport Issue Date", "source": "document.passport.issue_date", "required": True},
            {"id": "passport_expiry_date", "label": "Passport Expiry Date", "source": "document.passport.expiry_date", "required": True},
            {"id": "current_address", "label": "Current Address", "source": "profile.current_address", "required": True},
            {"id": "occupation", "label": "Occupation", "source": "profile.occupation", "required": True},
            {"id": "email", "label": "Email Address", "source": "profile.email", "required": True},
            {"id": "mobile", "label": "Mobile Number", "source": "profile.mobile", "required": True},
            {"id": "purpose_of_visit", "label": "Purpose of Visit", "source": "manual", "required": True},
            {"id": "intended_date_of_entry", "label": "Intended Date of Entry", "source": "manual", "required": True},
            {"id": "duration_of_stay", "label": "Duration of Stay (days)", "source": "manual", "required": True},
            {"id": "places_to_visit", "label": "Places to Visit in India", "source": "manual", "required": True},
            {"id": "accommodation_address", "label": "Accommodation Address in India", "source": "manual", "required": True}
        ]
    },
    "oci_application": {
        "name": "OCI Card Application",
        "total_steps": 18,
        "fields": [
            {"id": "full_name", "label": "Full Name", "source": "profile.name", "required": True},
            {"id": "dob", "label": "Date of Birth", "source": "profile.dob", "required": True},
            {"id": "place_of_birth", "label": "Place of Birth", "source": "profile.place_of_birth", "required": True},
            {"id": "gender", "label": "Gender", "source": "profile.gender", "required": True},
            {"id": "current_nationality", "label": "Current Nationality", "source": "profile.nationality", "required": True},
            {"id": "father_name", "label": "Father's Name", "source": "profile.father_name", "required": True},
            {"id": "father_nationality", "label": "Father's Nationality", "source": "manual", "required": True},
            {"id": "mother_name", "label": "Mother's Name", "source": "profile.mother_name", "required": True},
            {"id": "mother_nationality", "label": "Mother's Nationality", "source": "manual", "required": True},
            {"id": "spouse_name", "label": "Spouse's Name", "source": "profile.spouse_name", "required": False},
            {"id": "spouse_nationality", "label": "Spouse's Nationality", "source": "manual", "required": False},
            {"id": "current_passport_number", "label": "Current Passport Number", "source": "profile.passport_number", "required": True},
            {"id": "previous_indian_passport", "label": "Previous Indian Passport Number", "source": "manual", "required": True},
            {"id": "renunciation_date", "label": "Date of Renunciation", "source": "manual", "required": True},
            {"id": "current_address", "label": "Current Address", "source": "profile.current_address", "required": True},
            {"id": "email", "label": "Email Address", "source": "profile.email", "required": True},
            {"id": "mobile", "label": "Mobile Number", "source": "profile.mobile", "required": True},
            {"id": "emergency_contact", "label": "Emergency Contact", "source": "profile.emergency_contact", "required": True}
        ]
    },
    "pcc_application": {
        "name": "Police Clearance Certificate Application",
        "total_steps": 10,
        "fields": [
            {"id": "full_name", "label": "Full Name", "source": "profile.name", "required": True},
            {"id": "dob", "label": "Date of Birth", "source": "profile.dob", "required": True},
            {"id": "place_of_birth", "label": "Place of Birth", "source": "profile.place_of_birth", "required": True},
            {"id": "gender", "label": "Gender", "source": "profile.gender", "required": True},
            {"id": "passport_number", "label": "Passport Number", "source": "profile.passport_number", "required": True},
            {"id": "father_name", "label": "Father's Name", "source": "profile.father_name", "required": True},
            {"id": "current_address", "label": "Current Address", "source": "profile.current_address", "required": True},
            {"id": "permanent_address", "label": "Permanent Address in India", "source": "profile.permanent_address", "required": True},
            {"id": "purpose", "label": "Purpose of PCC", "source": "manual", "required": True},
            {"id": "country_required_for", "label": "Country Required For", "source": "manual", "required": True}
        ]
    }
}

class FormFillingRequest(BaseModel):
    session_id: str
    profile_id: str
    service_type: str
    message: str
    current_step: Optional[int] = 0
    form_data: Optional[Dict[str, Any]] = None

class FormFillingResponse(BaseModel):
    session_id: str
    response: str
    current_step: int
    total_steps: int
    progress_percent: int
    status: str  # consent_pending, in_progress, paused, review, completed
    current_field: Optional[str] = None
    form_data: Optional[Dict[str, Any]] = None
    waiting_for: str  # consent, confirmation, input, edit, submit

def extract_value_from_source(source: str, profile: Dict, documents: List, family: List) -> Optional[str]:
    """Extract value from profile, documents, or family based on source path"""
    if source == "manual":
        return None
    
    parts = source.split(".")
    
    if parts[0] == "profile" and len(parts) > 1:
        return profile.get(parts[1])
    
    elif parts[0] == "document" and len(parts) > 2:
        doc_type = parts[1]
        field = parts[2]
        for doc in documents:
            if doc.get("document_type") == doc_type:
                if field == "issue_date":
                    return doc.get("issue_date")
                elif field == "expiry_date":
                    return doc.get("expiry_date")
                elif field == "document_number":
                    return doc.get("document_number")
                # Check extracted_data
                extracted = doc.get("extracted_data", {})
                if extracted and field in extracted:
                    return extracted.get(field)
        return None
    
    elif parts[0] == "family" and len(parts) > 2:
        relationship = parts[1]
        field = parts[2]
        for member in family:
            if member.get("relationship") == relationship:
                return member.get(field)
        return None
    
    return None

@router.post("/form-filling", response_model=FormFillingResponse)
async def interactive_form_filling(request: FormFillingRequest):
    """Interactive, step-by-step form filling using existing documents"""
    db = await get_database()
    
    # Get or create form session
    form_session = await db.form_sessions.find_one({"session_id": request.session_id}, {"_id": 0})
    
    if not form_session:
        # Initialize new form session
        form_session = {
            "session_id": request.session_id,
            "profile_id": request.profile_id,
            "service_type": request.service_type,
            "status": "consent_pending",
            "current_step": 0,
            "consent_given": False,
            "form_data": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "messages": []
        }
        await db.form_sessions.insert_one(form_session)
    
    # Get profile and documents
    profile = await db.user_profiles.find_one({"profile_id": request.profile_id}, {"_id": 0})
    if not profile:
        return FormFillingResponse(
            session_id=request.session_id,
            response="❌ **Profile not found.** Please create a profile first before starting a form application.",
            current_step=0,
            total_steps=0,
            progress_percent=0,
            status="error",
            waiting_for="profile"
        )
    
    documents = profile.get("documents", [])
    family = profile.get("family_members", [])
    
    # Get form template
    template = FORM_TEMPLATES.get(request.service_type)
    if not template:
        available_services = ", ".join(FORM_TEMPLATES.keys())
        return FormFillingResponse(
            session_id=request.session_id,
            response=f"❌ **Unknown service type.** Available services: {available_services}",
            current_step=0,
            total_steps=0,
            progress_percent=0,
            status="error",
            waiting_for="service_selection"
        )
    
    total_steps = template["total_steps"]
    fields = template["fields"]
    user_message = request.message.strip().lower()
    
    # Handle different states
    status = form_session.get("status", "consent_pending")
    current_step = form_session.get("current_step", 0)
    form_data = form_session.get("form_data", {})
    
    # Handle STOP command
    if user_message in ["stop", "pause", "wait"]:
        await db.form_sessions.update_one(
            {"session_id": request.session_id},
            {"$set": {"status": "paused"}}
        )
        
        completed_fields = [f for f in fields[:current_step] if form_data.get(f["id"])]
        progress = int((current_step / total_steps) * 100)
        
        return FormFillingResponse(
            session_id=request.session_id,
            response=f"""⏸️ **Application Paused**

**Progress Summary:**
- Service: **{template['name']}**
- Completed: **{len(completed_fields)}** of **{total_steps}** fields
- Progress: **{progress}%**

Your progress has been saved. Say **"continue"** or **"resume"** when you're ready to proceed.

**Completed Fields:**
{chr(10).join([f"✅ {f['label']}: {form_data.get(f['id'], 'N/A')}" for f in fields[:current_step] if form_data.get(f['id'])])}""",
            current_step=current_step,
            total_steps=total_steps,
            progress_percent=progress,
            status="paused",
            form_data=form_data,
            waiting_for="resume"
        )
    
    # Handle CONTINUE/RESUME command
    if user_message in ["continue", "resume", "proceed"] and status == "paused":
        # Update status to in_progress
        await db.form_sessions.update_one(
            {"session_id": request.session_id},
            {"$set": {"status": "in_progress"}}
        )
        
        # Get current step info and return proper response
        current_step = form_session.get("current_step", 1)
        form_data = form_session.get("form_data", {})
        
        if current_step <= len(fields):
            current_field = fields[current_step - 1]
            current_field_id = current_field["id"]
            current_value = form_data.get(current_field_id)
            
            # Try to get value from documents if not in form_data
            if not current_value:
                current_value = extract_value_from_source(current_field["source"], profile, documents, family)
                if current_value:
                    form_data[current_field_id] = current_value
                    await db.form_sessions.update_one(
                        {"session_id": request.session_id},
                        {"$set": {"form_data": form_data}}
                    )
            
            progress = int((current_step / total_steps) * 100)
            progress_bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
            
            if current_value:
                return FormFillingResponse(
                    session_id=request.session_id,
                    response=f"""▶️ **Resuming Application**

---

**Step {current_step}/{total_steps}** | Progress: **{progress}%** {progress_bar}

📌 **{current_field['label']}**: `{current_value}`

**Is this correct?** Reply YES, NO, or provide a different value.""",
                    current_step=current_step,
                    total_steps=total_steps,
                    progress_percent=progress,
                    status="in_progress",
                    current_field=current_field_id,
                    form_data=form_data,
                    waiting_for="confirmation"
                )
            else:
                return FormFillingResponse(
                    session_id=request.session_id,
                    response=f"""▶️ **Resuming Application**

---

**Step {current_step}/{total_steps}** | Progress: **{progress}%** {progress_bar}

❓ **{current_field['label']}**

{"*(Optional)*" if not current_field.get("required") else "*(Required)*"}

Please provide this information:""",
                    current_step=current_step,
                    total_steps=total_steps,
                    progress_percent=progress,
                    status="in_progress",
                    current_field=current_field_id,
                    form_data=form_data,
                    waiting_for="input"
                )
    
    # =========================================================================
    # STATE: CONSENT PENDING
    # =========================================================================
    if status == "consent_pending":
        if user_message == "yes" or user_message == "i agree" or user_message == "agree":
            # Start with first field
            field = fields[0]
            extracted_value = extract_value_from_source(field["source"], profile, documents, family)
            
            # Prepare form_data with first field value
            initial_form_data = {}
            if extracted_value:
                initial_form_data[field["id"]] = extracted_value
            
            # Consent given - archive documents and store initial form_data
            await db.form_sessions.update_one(
                {"session_id": request.session_id},
                {"$set": {
                    "consent_given": True,
                    "consent_timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "in_progress",
                    "current_step": 1,
                    "form_data": initial_form_data,
                    "archived_documents": [d.get("id") for d in documents]
                }}
            )
            
            progress = int((1 / total_steps) * 100)
            
            if extracted_value:
                return FormFillingResponse(
                    session_id=request.session_id,
                    response=f"""✅ **Thank you for your consent!**

📋 Documents archived securely for admin staff.
🔄 Starting **{template['name']}**...

---

**Step 1/{total_steps}** | Progress: **{progress}%** ████░░░░░░

From your documents, I found:
📌 **{field['label']}**: `{extracted_value}`

**Is this correct?** Reply:
- **YES** to confirm and continue
- **NO** to edit this field
- **STOP** to pause anytime""",
                    current_step=1,
                    total_steps=total_steps,
                    progress_percent=progress,
                    status="in_progress",
                    current_field=field["id"],
                    form_data={field["id"]: extracted_value},
                    waiting_for="confirmation"
                )
            else:
                return FormFillingResponse(
                    session_id=request.session_id,
                    response=f"""✅ **Thank you for your consent!**

📋 Documents archived securely for admin staff.
🔄 Starting **{template['name']}**...

---

**Step 1/{total_steps}** | Progress: **{progress}%** ████░░░░░░

❓ **{field['label']}**

I couldn't find this in your documents. Please provide this information:""",
                    current_step=1,
                    total_steps=total_steps,
                    progress_percent=progress,
                    status="in_progress",
                    current_field=field["id"],
                    form_data={},
                    waiting_for="input"
                )
        else:
            # Initial consent prompt
            doc_summary = []
            if documents:
                for doc in documents[:5]:  # Show first 5
                    validity = doc.get("validity", {}).get("status", "unknown")
                    emoji = "✅" if validity in ["active", "permanent"] else "⚠️"
                    doc_summary.append(f"   {emoji} {doc.get('document_name', 'Unknown')}")
            
            return FormFillingResponse(
                session_id=request.session_id,
                response=f"""🙏 **Namaste! Welcome to the {template['name']} Assistant**

I'll help you complete your application **step-by-step** using the documents already in your profile.

**📁 Your Available Documents:**
{chr(10).join(doc_summary) if doc_summary else "   ⚠️ No documents found in profile"}

**📋 What I'll Do:**
1. Extract information from your documents
2. Show you each field ONE at a time
3. Ask for your confirmation before proceeding
4. Allow edits at any step
5. Archive documents securely for admin staff

**⚠️ CONSENT REQUIRED:**
Do I have your permission to:
- ✅ Read your uploaded documents
- ✅ Extract information to auto-fill this form
- ✅ Archive documents for admin processing

**Reply YES to proceed or NO to cancel.**""",
                current_step=0,
                total_steps=total_steps,
                progress_percent=0,
                status="consent_pending",
                waiting_for="consent"
            )
    
    # =========================================================================
    # STATE: IN PROGRESS
    # =========================================================================
    if status == "in_progress":
        current_step = form_session.get("current_step", 1)
        form_data = form_session.get("form_data", {})
        
        # Check if current step is valid
        if current_step > len(fields):
            # All fields complete - go to review
            await db.form_sessions.update_one(
                {"session_id": request.session_id},
                {"$set": {"status": "review"}}
            )
            status = "review"
        else:
            current_field = fields[current_step - 1]
            current_field_id = current_field["id"]
            
            # Handle YES (confirm current value)
            if user_message == "yes" or user_message == "correct" or user_message == "confirm":
                # Get the pending value
                pending_value = form_data.get(current_field_id)
                if pending_value:
                    # Move to next step
                    next_step = current_step + 1
                    
                    if next_step > len(fields):
                        # All done - go to review
                        await db.form_sessions.update_one(
                            {"session_id": request.session_id},
                            {"$set": {
                                "status": "review",
                                "current_step": next_step,
                                "form_data": form_data
                            }}
                        )
                        
                        # Generate review summary
                        review_lines = []
                        for i, f in enumerate(fields):
                            value = form_data.get(f["id"], "Not provided")
                            review_lines.append(f"{i+1}. **{f['label']}**: {value}")
                        
                        return FormFillingResponse(
                            session_id=request.session_id,
                            response=f"""🎉 **All Fields Complete!**

**📋 {template['name']} - Final Review**

{chr(10).join(review_lines)}

---

**Please review all information carefully.**

Reply:
- **SUBMIT** to submit the application
- **EDIT [number]** to change a specific field (e.g., "EDIT 3")
- **STOP** to save and continue later""",
                            current_step=len(fields),
                            total_steps=total_steps,
                            progress_percent=100,
                            status="review",
                            form_data=form_data,
                            waiting_for="submit"
                        )
                    
                    # Get next field
                    next_field = fields[next_step - 1]
                    extracted_value = extract_value_from_source(next_field["source"], profile, documents, family)
                    
                    # Update form_data with next field value
                    new_form_data = {**form_data}
                    if extracted_value:
                        new_form_data[next_field["id"]] = extracted_value
                    
                    await db.form_sessions.update_one(
                        {"session_id": request.session_id},
                        {"$set": {
                            "current_step": next_step,
                            "form_data": new_form_data
                        }}
                    )
                    
                    progress = int((next_step / total_steps) * 100)
                    progress_bar = "█" * (progress // 10) + "░" * (10 - progress // 10)
                    
                    if extracted_value:
                        return FormFillingResponse(
                            session_id=request.session_id,
                            response=f"""✅ **Confirmed:** {current_field['label']} = `{pending_value}`

---

**Step {next_step}/{total_steps}** | Progress: **{progress}%** {progress_bar}

From your documents, I found:
📌 **{next_field['label']}**: `{extracted_value}`

**Is this correct?** Reply YES, NO, or provide a different value.""",
                            current_step=next_step,
                            total_steps=total_steps,
                            progress_percent=progress,
                            status="in_progress",
                            current_field=next_field["id"],
                            form_data=new_form_data,
                            waiting_for="confirmation"
                        )
                    else:
                        return FormFillingResponse(
                            session_id=request.session_id,
                            response=f"""✅ **Confirmed:** {current_field['label']} = `{pending_value}`

---

**Step {next_step}/{total_steps}** | Progress: **{progress}%** {progress_bar}

❓ **{next_field['label']}**

{"*(Optional)*" if not next_field.get("required") else "*(Required)*"}

Please provide this information (or type SKIP if optional):""",
                            current_step=next_step,
                            total_steps=total_steps,
                            progress_percent=progress,
                            status="in_progress",
                            current_field=next_field["id"],
                            form_data=new_form_data,
                            waiting_for="input"
                        )
            
            # Handle NO (want to edit)
            elif user_message == "no" or user_message == "edit" or user_message == "change":
                return FormFillingResponse(
                    session_id=request.session_id,
                    response=f"""✏️ **Edit Mode**

Current value for **{current_field['label']}**: `{form_data.get(current_field_id, 'Not set')}`

Please type the correct value:""",
                    current_step=current_step,
                    total_steps=total_steps,
                    progress_percent=int((current_step / total_steps) * 100),
                    status="in_progress",
                    current_field=current_field_id,
                    form_data=form_data,
                    waiting_for="input"
                )
            
            # Handle SKIP (for optional fields)
            elif user_message == "skip" and not current_field.get("required"):
                next_step = current_step + 1
                new_form_data = {**form_data}
                new_form_data[current_field_id] = "N/A (Skipped)"
                
                await db.form_sessions.update_one(
                    {"session_id": request.session_id},
                    {"$set": {
                        "current_step": next_step,
                        "form_data": new_form_data
                    }}
                )
                
                if next_step > len(fields):
                    # Move to review
                    await db.form_sessions.update_one(
                        {"session_id": request.session_id},
                        {"$set": {"status": "review"}}
                    )
                    status = "review"
                    # Will be handled in review section
                else:
                    next_field = fields[next_step - 1]
                    extracted_value = extract_value_from_source(next_field["source"], profile, documents, family)
                    
                    if extracted_value:
                        new_form_data[next_field["id"]] = extracted_value
                    
                    progress = int((next_step / total_steps) * 100)
                    
                    return FormFillingResponse(
                        session_id=request.session_id,
                        response=f"""⏭️ **Skipped:** {current_field['label']}

---

**Step {next_step}/{total_steps}** | Progress: **{progress}%**

{'📌 **' + next_field['label'] + '**: `' + str(extracted_value) + '`' if extracted_value else '❓ **' + next_field['label'] + '**'}

{"**Is this correct?** Reply YES or NO." if extracted_value else "Please provide this information:"}""",
                        current_step=next_step,
                        total_steps=total_steps,
                        progress_percent=progress,
                        status="in_progress",
                        current_field=next_field["id"],
                        form_data=new_form_data,
                        waiting_for="confirmation" if extracted_value else "input"
                    )
            
            # Handle user providing a new value
            else:
                # User provided a value - store it
                new_form_data = {**form_data}
                new_form_data[current_field_id] = request.message.strip()
                
                await db.form_sessions.update_one(
                    {"session_id": request.session_id},
                    {"$set": {"form_data": new_form_data}}
                )
                
                progress = int((current_step / total_steps) * 100)
                
                return FormFillingResponse(
                    session_id=request.session_id,
                    response=f"""📝 **Field Updated**

**{current_field['label']}**: `{request.message.strip()}`

**Is this correct?** Reply:
- **YES** to confirm and proceed
- **NO** to edit again""",
                    current_step=current_step,
                    total_steps=total_steps,
                    progress_percent=progress,
                    status="in_progress",
                    current_field=current_field_id,
                    form_data=new_form_data,
                    waiting_for="confirmation"
                )
    
    # =========================================================================
    # STATE: REVIEW
    # =========================================================================
    if status == "review":
        form_data = form_session.get("form_data", {})
        
        # Handle SUBMIT
        if user_message == "submit" or user_message == "yes" or user_message == "confirm":
            # Generate application ID
            app_id = f"APP-{request.service_type.upper()[:4]}-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
            
            # Store completed application
            application = {
                "application_id": app_id,
                "profile_id": request.profile_id,
                "service_type": request.service_type,
                "service_name": template["name"],
                "form_data": form_data,
                "status": "submitted",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "session_id": request.session_id
            }
            
            await db.applications.insert_one(application)
            
            # Update form session
            await db.form_sessions.update_one(
                {"session_id": request.session_id},
                {"$set": {
                    "status": "completed",
                    "application_id": app_id,
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Add to user profile
            await db.user_profiles.update_one(
                {"profile_id": request.profile_id},
                {"$push": {"applications": {"id": app_id, "service": request.service_type, "status": "submitted", "date": datetime.now(timezone.utc).isoformat()}}}
            )
            
            return FormFillingResponse(
                session_id=request.session_id,
                response=f"""🎉 **Application Submitted Successfully!**

**Application ID:** `{app_id}`

**📋 {template['name']}**

---

**What's Next:**
1. ✅ Your application has been received
2. 📧 You'll receive a confirmation email at `{profile.get('email')}`
3. 📞 Our admin team will contact you if additional info is needed
4. 📊 Track your application status using the Application ID

**Estimated Processing Time:** {FORM_TEMPLATES.get(request.service_type, {}).get('processing_time', '2-4 weeks')}

---

Thank you for using Seva Setu Bot! 🙏

**Was this helpful?** 👍 👎""",
                current_step=total_steps,
                total_steps=total_steps,
                progress_percent=100,
                status="completed",
                form_data=form_data,
                waiting_for="feedback"
            )
        
        # Handle EDIT [number]
        elif user_message.startswith("edit"):
            parts = user_message.split()
            if len(parts) > 1:
                try:
                    edit_step = int(parts[1])
                    if 1 <= edit_step <= len(fields):
                        field_to_edit = fields[edit_step - 1]
                        
                        await db.form_sessions.update_one(
                            {"session_id": request.session_id},
                            {"$set": {
                                "status": "in_progress",
                                "current_step": edit_step
                            }}
                        )
                        
                        return FormFillingResponse(
                            session_id=request.session_id,
                            response=f"""✏️ **Editing Field {edit_step}**

**{field_to_edit['label']}**
Current value: `{form_data.get(field_to_edit['id'], 'Not set')}`

Please type the new value:""",
                            current_step=edit_step,
                            total_steps=total_steps,
                            progress_percent=int((edit_step / total_steps) * 100),
                            status="in_progress",
                            current_field=field_to_edit["id"],
                            form_data=form_data,
                            waiting_for="input"
                        )
                except ValueError:
                    pass
            
            return FormFillingResponse(
                session_id=request.session_id,
                response=f"""❓ **Which field do you want to edit?**

Reply with **EDIT [number]** (e.g., "EDIT 3" to edit field 3)

Or reply **SUBMIT** to submit the application.""",
                current_step=len(fields),
                total_steps=total_steps,
                progress_percent=100,
                status="review",
                form_data=form_data,
                waiting_for="edit_selection"
            )
        
        # Show review again
        else:
            review_lines = []
            for i, f in enumerate(fields):
                value = form_data.get(f["id"], "Not provided")
                review_lines.append(f"{i+1}. **{f['label']}**: {value}")
            
            return FormFillingResponse(
                session_id=request.session_id,
                response=f"""📋 **{template['name']} - Review**

{chr(10).join(review_lines)}

---

Reply:
- **SUBMIT** to submit the application
- **EDIT [number]** to change a field (e.g., "EDIT 3")
- **STOP** to save and continue later""",
                current_step=len(fields),
                total_steps=total_steps,
                progress_percent=100,
                status="review",
                form_data=form_data,
                waiting_for="submit"
            )
    
    # Default response
    return FormFillingResponse(
        session_id=request.session_id,
        response="I'm not sure how to proceed. Please try again or type STOP to pause.",
        current_step=current_step,
        total_steps=total_steps,
        progress_percent=int((current_step / total_steps) * 100) if total_steps > 0 else 0,
        status=status,
        form_data=form_data,
        waiting_for="input"
    )

@router.get("/form-session/{session_id}")
async def get_form_session(session_id: str):
    """Get form filling session status"""
    db = await get_database()
    session = await db.form_sessions.find_one({"session_id": session_id}, {"_id": 0})
    
    if not session:
        raise HTTPException(status_code=404, detail="Form session not found")
    
    return session

@router.get("/applications/{profile_id}")
async def get_applications(profile_id: str):
    """Get all applications for a profile"""
    db = await get_database()
    applications = await db.applications.find({"profile_id": profile_id}, {"_id": 0}).to_list(100)
    
    return {
        "success": True,
        "applications": applications,
        "total": len(applications)
    }