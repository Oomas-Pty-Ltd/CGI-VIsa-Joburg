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