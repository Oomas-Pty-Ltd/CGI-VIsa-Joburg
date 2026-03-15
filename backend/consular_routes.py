from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
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
from knowledge_scraper import get_realtime_knowledge, search_knowledge, extract_service_content
from voice_service import voice_service
from dotenv import load_dotenv

# Security imports
from security.session_manager import session_manager
from security.input_sanitizer import sanitize_user_input, create_safe_system_prompt
from security.guardrail import guardrail_service, sanitize_logs
from security.rate_limiter import rate_limiter, check_rate_limit
from security.cost_monitor import cost_monitor, record_llm_usage

# Services imports
from services.intent_classifier import (
    intent_classifier, 
    classify_intent, 
    get_deterministic_response,
    IntentCategory
)
from services.escalation_service import (
    escalation_service,
    EscalationReason,
    EscalationPriority
)
from services.knowledge_service import knowledge_service
from services.application_flow import process_flow, flow_suffix, SERVICES, detect_service, get_flow_state

load_dotenv()

router = APIRouter(prefix="/consular", tags=["consular"])
import logging
logger = logging.getLogger(__name__)

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

@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(check_rate_limit)])
async def chat(request: ChatRequest, http_request: Request):
    db = await get_database()
    
    # Get client IP for rate limiting logging
    client_ip = http_request.client.host if http_request.client else "unknown"
    
    # Sanitize and validate user input
    sanitization_result = sanitize_user_input(request.message, context="web_chat")
    
    if not sanitization_result.is_safe:
        logger.warning(f"[SECURITY] Blocked unsafe input from {client_ip}: {sanitization_result.detected_patterns}")
        return ChatResponse(
            session_id=request.session_id or str(uuid.uuid4()),
            response="I cannot process that request. Please ask a question about consular services.",
            step="error"
        )
    
    sanitized_message = request.message

    # Intent classification - try rule-based first
    intent_result = classify_intent(sanitized_message)
    logger.info(f"[INTENT] Category: {intent_result.category.value}, Confidence: {intent_result.confidence:.2f}, Requires LLM: {intent_result.requires_llm}")
    
    # Check for escalation trigger
    if intent_result.escalation_needed:
        user_id = request.user_id or "guest"
        session_id = request.session_id or str(uuid.uuid4())
        
        # Get session for conversation history
        session = await session_manager.get_or_create_session(
            channel="web",
            user_identifier=user_id,
            session_id=session_id
        )
        
        # Create escalation
        escalation = await escalation_service.create_escalation(
            session_id=session['id'],
            user_identifier=user_id,
            channel="web",
            reason=EscalationReason.EMERGENCY if intent_result.category == IntentCategory.EMERGENCY else EscalationReason.USER_REQUEST,
            priority=EscalationPriority.URGENT if intent_result.category == IntentCategory.EMERGENCY else EscalationPriority.MEDIUM,
            description=sanitized_message,
            conversation_history=session.get('messages', [])
        )
        
        response = escalation_service.get_escalation_response(
            EscalationPriority.URGENT if intent_result.category == IntentCategory.EMERGENCY else EscalationPriority.MEDIUM
        )
        response += f"\n\n**Reference ID:** {escalation.id[:8].upper()}"
        
        return ChatResponse(
            session_id=session['id'],
            response=response,
            step="escalated"
        )
    
    # Try deterministic response first (no LLM cost)
    deterministic_response = get_deterministic_response(intent_result)
    if deterministic_response and not request.image_base64:
        user_id = request.user_id or "guest"
        session = await session_manager.get_or_create_session(
            channel="web",
            user_identifier=user_id,
            session_id=request.session_id
        )
        
        # Add source tag
        response_data = intent_classifier.get_structured_response(intent_result.suggested_response_key)
        source_tag = f"\n\n---\n*Source: {response_data.get('source', 'CGI Johannesburg')}*"
        final_response = deterministic_response + source_tag
        
        # Store messages
        await session_manager.add_message(session['id'], "user", request.message)
        await session_manager.add_message(session['id'], "assistant", final_response, 
                                          metadata={"intent": intent_result.category.value, "llm_used": False})
        
        logger.info(f"[INTENT] Served deterministic response for: {intent_result.category.value}")
        
        return ChatResponse(
            session_id=session['id'],
            response=final_response,
            step="complete"
        )
    
    # Fall through to LLM for complex queries
    user_id    = request.user_id or "guest"
    company_id = request.company_id

    # Use secure session management
    session = await session_manager.get_or_create_session(
        channel="web",
        user_identifier=user_id,
        session_id=request.session_id,
        metadata={"company_id": company_id, "language": request.language}
    )
    session_id = session['id']

    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if company_id:
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if company:
            llm_model = company.get('llm_model', llm_model)

    # ── Pre-fetch scrape + current flow state ─────────────────────────
    knowledge_base = await get_realtime_knowledge()
    context_info   = search_knowledge(sanitized_message, knowledge_base)

    current_flow   = await get_flow_state(session_id)
    current_state  = current_flow.get("state", "idle")

    # ── If in docs_uploading and an image was sent, scan it first ─────
    image_doc_data: dict | None = None
    if current_state == "docs_uploading" and request.image_base64:
        try:
            api_key = os.environ.get('EMERGENT_LLM_KEY')
            scan_chat = LlmChat(
                api_key=api_key,
                session_id=str(uuid.uuid4()),
                system_message=(
                    "You are a document OCR assistant. Extract all visible text and fields from "
                    "the document image. Return a JSON object with keys: "
                    "full_name, dob, document_number, nationality, issue_date, expiry_date, address. "
                    "Use null for missing fields. Output ONLY valid JSON."
                )
            ).with_model("openai", llm_model)
            raw = await scan_chat.send_message(
                UserMessage(
                    text="Extract all fields from this document.",
                    file_contents=[ImageContent(image_base64=request.image_base64)]
                )
            )
            import json as _json
            try:
                image_doc_data = _json.loads(raw)
            except Exception:
                image_doc_data = {"raw": raw}
            image_doc_data["filename"] = "uploaded_doc"
        except Exception as e:
            logger.warning(f"Doc scan failed during upload: {sanitize_logs(str(e))}")

    # ── Build service-specific scraped summary ─────────────────────────
    scraped_summary = ""
    active_service = detect_service(sanitized_message) or current_flow.get("service")
    if active_service:
        scraped_summary = extract_service_content(active_service, knowledge_base)

    # ── Application flow state machine ────────────────────────────────
    flow_response, needs_llm, current_step = await process_flow(
        session_id, sanitized_message,
        has_image=bool(request.image_base64),
        image_doc_data=image_doc_data,
        user_id=user_id,
        scraped_summary=scraped_summary,
    )

    if flow_response is not None and not needs_llm:
        # Pure state-machine response — no LLM needed
        bot_response = flow_response
    else:
        # LLM needed (info query, question during pause, etc.)

        # Detect service for info context
        detected_svc = detect_service(sanitized_message)
        svc_docs_hint = ""
        if detected_svc and detected_svc in SERVICES:
            svc = SERVICES[detected_svc]
            docs = "\n".join(f"  • {d}" for d in svc["documents"])
            svc_docs_hint = (
                f"\nDOCUMENTS REQUIRED FOR {svc['name'].upper()}:\n{docs}\n"
            )

        _base_system_message = f"""You are Seva Setu Bot, the official consular assistant for the Consulate General of India, Johannesburg.

LANGUAGE: Always respond in English only, regardless of what language the user writes in.

RESPONSE STYLE:
- Be concise, accurate, and helpful.
- Do NOT echo the user's question back.
- Do NOT add feedback/rating prompts or sign-off phrases.
- Use bullet points only when listing multiple items.
- Do NOT repeat information already shown in the conversation.
{svc_docs_hint}
OFFICIAL WEBSITE DATA (live scraped from cgijoburg.gov.in and vfsglobal.com):
{context_info}

FALLBACK RULE: If the information is not in the scraped data, say so briefly and direct the user to:
  📞 +27 6830 38144  |  📧 cons.joburg@mea.gov.in
  🏢 1st Floor, Cedar Square, Fourways, Johannesburg 2055
  🕐 Mon–Fri 09:00–17:00 | Consular services 09:00–12:00 (by appointment)
  VFS Global — Mon–Fri 08:00–15:00 (appointment mandatory) — visa.vfsglobal.com"""

        api_key = os.environ.get('EMERGENT_LLM_KEY')
        chat_instance = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=_base_system_message
        ).with_model("openai", llm_model)

        user_msg_content = []
        if request.image_base64:
            user_msg_content.append(ImageContent(image_base64=request.image_base64))

        user_message = UserMessage(
            text=sanitized_message,
            file_contents=user_msg_content if user_msg_content else None
        )

        try:
            bot_response = await chat_instance.send_message(user_message)
            await record_llm_usage(
                session_id=session_id,
                input_text=sanitized_message,
                output_text=bot_response,
                model=llm_model
            )
        except Exception as e:
            logger.error(f"AI service error: {sanitize_logs(str(e))}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI service error: {str(e)}"
            )

        # Append flow guidance suffix (e.g. "apply to start" or "continue/discard")
        # Reload session to get latest flow state (updated by process_flow)
        updated_session = await session_manager.get_session(session_id)
        flow_service = (updated_session or session).get("flow", {}).get("service") or detect_service(sanitized_message)
        suffix = flow_suffix(current_step, flow_service)
        if suffix:
            bot_response += suffix
    
    # Generate voice response if requested
    audio_base64 = None
    if request.enable_voice:
        try:
            # Detect language from message
            lang_code = request.language or "en"
            audio_base64 = await voice_service.text_to_speech(bot_response, lang_code)
        except Exception as e:
            logger.warning(f"Voice generation failed: {sanitize_logs(str(e))}")
    
    # Store messages using session manager
    await session_manager.add_message(
        session_id=session_id,
        role="user",
        content=request.message,  # Store original for user reference
        metadata={"sanitized": sanitized_message != request.message}
    )
    
    await session_manager.add_message(
        session_id=session_id,
        role="assistant", 
        content=bot_response,
        metadata={"has_audio": audio_base64 is not None}
    )
    
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
    ).with_model("openai", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    
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
    audio: UploadFile = File(...),
    language: str = "en",
    session_id: Optional[str] = None
):
    """
    Transcribe voice input using OpenAI Whisper.
    Accepts audio files (webm, mp3, wav, m4a) up to 25MB.
    """
    from speech_service import speech_service
    
    # Validate file type
    allowed_types = ['audio/webm', 'audio/mp3', 'audio/mpeg', 'audio/wav', 'audio/m4a', 'audio/ogg']
    content_type = audio.content_type or ''
    
    # Also check by extension as content_type can be unreliable
    filename = audio.filename or 'recording.webm'
    valid_extensions = ['.webm', '.mp3', '.wav', '.m4a', '.ogg', '.mpeg', '.mpga']
    has_valid_ext = any(filename.lower().endswith(ext) for ext in valid_extensions)
    
    if not has_valid_ext and content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid audio format. Supported: webm, mp3, wav, m4a, ogg. Got: {content_type}"
        )
    
    # Read audio bytes
    audio_bytes = await audio.read()
    
    # Check file size (25MB limit for Whisper)
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file too large. Maximum size is 25MB."
        )
    
    # Transcribe using Whisper
    result = await speech_service.transcribe_audio(
        audio_bytes=audio_bytes,
        language=language,
        filename=filename
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {result.get('error', 'Unknown error')}"
        )
    
    return {
        "success": True,
        "transcription": result["transcription"],
        "language": result["language"],
        "message": "Voice transcribed successfully"
    }


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
    With: Input sanitization, PII protection, session isolation
    """
    # Sanitize and validate user input
    sanitization_result = sanitize_user_input(request.message, context="widget")
    
    if not sanitization_result.is_safe:
        logger.warning(f"[SECURITY] Blocked unsafe widget input: {sanitization_result.detected_patterns}")
        return WidgetChatResponse(
            session_id=request.session_id or str(uuid.uuid4()),
            response="I cannot process that request. Please ask about consular services."
        )
    
    sanitized_message = request.message

    # Use secure session management for widgets
    session = await session_manager.get_or_create_session(
        channel="widget",
        user_identifier="widget_guest",
        session_id=request.session_id,
        metadata={"mode": request.mode, "source": "widget"}
    )
    session_id = session['id']
    
    # Concise system prompt - KEY TO BETTER BEHAVIOR (BASE)
    _base_system_message = """You are Seva Setu, a helpful consular assistant for the Consulate General of India, Johannesburg.

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

LANGUAGE: Always respond in English only.

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
        system_message=_base_system_message
    ).with_model("openai", os.getenv("LLM_MODEL", "gpt-4o-mini"))
    
    user_message = UserMessage(text=sanitized_message)
    
    try:
        bot_response = await chat_instance.send_message(user_message)
    except Exception as e:
        logger.error(f"Widget service error: {sanitize_logs(str(e))}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Service error: {str(e)}"
        )
    
    # Store messages using session manager
    await session_manager.add_message(session_id, "user", request.message)
    await session_manager.add_message(session_id, "assistant", bot_response)
    
    return WidgetChatResponse(
        session_id=session_id,
        response=bot_response
    )


# =====================================================================
# APPLICATION TRACKING ENDPOINTS
# =====================================================================

class ApplicationStatusResponse(BaseModel):
    tracking_id: str
    service: str
    service_name: str
    status: str
    form_data: Dict[str, Any]
    documents: List[Dict[str, Any]]
    required_documents: List[str]
    created_at: str
    updated_at: str
    submitted_at: Optional[str] = None


@router.get("/application/{tracking_id}", response_model=ApplicationStatusResponse)
async def get_application_status(tracking_id: str):
    """Check the status of an application by tracking ID."""
    db = await get_database()
    app = await db.applications.find_one(
        {"tracking_id": tracking_id.upper()}, {"_id": 0}
    )
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {tracking_id} not found."
        )
    return ApplicationStatusResponse(
        tracking_id=app["tracking_id"],
        service=app["service"],
        service_name=app["service_name"],
        status=app["status"],
        form_data=app.get("form_data", {}),
        documents=app.get("documents", []),
        required_documents=app.get("required_documents", []),
        created_at=app["created_at"],
        updated_at=app["updated_at"],
        submitted_at=app.get("submitted_at"),
    )


@router.get("/applications/session/{session_id}")
async def get_session_applications(session_id: str):
    """List all applications linked to a session."""
    db = await get_database()
    cursor = db.applications.find({"session_id": session_id}, {"_id": 0})
    apps = await cursor.to_list(length=20)
    return {
        "session_id": session_id,
        "total": len(apps),
        "applications": [
            {
                "tracking_id":  a["tracking_id"],
                "service_name": a["service_name"],
                "status":       a["status"],
                "created_at":   a["created_at"],
                "submitted_at": a.get("submitted_at"),
                "documents_uploaded": sum(
                    1 for d in a.get("documents", []) if d.get("status") == "uploaded"
                ),
                "documents_required": len(a.get("required_documents", [])),
            }
            for a in apps
        ],
    }
