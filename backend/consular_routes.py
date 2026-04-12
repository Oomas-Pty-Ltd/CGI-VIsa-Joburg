from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, AsyncGenerator
import asyncio
import re
import uuid
import json
from datetime import datetime, timezone
import base64
import os
from database import get_database
from auth_utils import verify_token
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from presidio_service import mask_pii
from knowledge_scraper import (
    get_realtime_knowledge,
    search_knowledge,
    extract_service_content,
)
from services.hybrid_retrieval import hybrid_search
from voice_service import voice_service
from dotenv import load_dotenv

# Security imports
from security.session_manager import session_manager
from security.input_sanitizer import sanitize_user_input, create_safe_system_prompt
from security.guardrail import guardrail_service, sanitize_logs
from security.rate_limiter import rate_limiter, check_rate_limit
from security.cost_monitor import cost_monitor, record_llm_usage
from config import get_company_id

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
from services.application_flow import process_flow, flow_suffix, SERVICES, detect_service, detect_website_service, get_flow_state, is_apply_intent, is_tracking_query
from services.pdf_service import generate_application_pdf
from fastapi.responses import Response as FastAPIResponse

load_dotenv()

# When False the application/form-filling flow is hidden from users.
# Set APPLICATION_FLOW_ENABLED=true in .env to re-enable it.
_FLOW_ENABLED: bool = os.getenv("APPLICATION_FLOW_ENABLED", "true").lower() == "true"

router = APIRouter(prefix="/consular", tags=["consular"])
import logging
import io
logger = logging.getLogger(__name__)


# ── Supported image format detection ─────────────────────────────────────────
_B64_MAGIC = {
    "/9j/":   "image/jpeg",
    "iVBORw": "image/png",
    "R0lGOD": "image/gif",
    "UklGR":  "image/webp",
}
_UNSUPPORTED_B64 = {
    "JVBER": "PDF",
    "Qk0":   "BMP",
    "SUkq":  "TIFF",
    "TU0A":  "TIFF",
    "AAAAF": "HEIC/HEIF",
}


def _normalize_image(image_base64: str) -> tuple[str, str]:
    """
    Detect image format from base64 magic bytes.
    - Supported formats (JPEG, PNG, WEBP, GIF): return as-is with correct media_type.
    - Convertible formats (BMP, TIFF): convert to JPEG via Pillow.
    - PDF: raise ValueError with a user-friendly message.
    - Unknown: attempt Pillow conversion to JPEG.

    Returns (image_base64, media_type).
    Raises ValueError for unrecoverable formats.
    """
    prefix = image_base64[:10]

    # Already a supported format
    for magic, mime in _B64_MAGIC.items():
        if prefix.startswith(magic):
            return image_base64, mime

    # PDF — cannot convert without poppler
    if prefix.startswith("JVBER"):
        raise ValueError(
            "PDF files cannot be scanned directly. "
            "Please take a **photo or screenshot** of the document and upload that instead."
        )

    # HEIC — not supported
    if prefix.startswith("AAAAF"):
        raise ValueError(
            "HEIC/HEIF images are not supported. "
            "Please convert to JPEG or PNG before uploading."
        )

    # Attempt Pillow conversion for BMP, TIFF, and any other Pillow-readable format
    try:
        from PIL import Image
        raw = base64.b64decode(image_base64)
        img = Image.open(io.BytesIO(raw))
        # Convert palette/RGBA modes for JPEG compatibility
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        converted = base64.b64encode(buf.getvalue()).decode()
        return converted, "image/jpeg"
    except Exception as e:
        raise ValueError(
            f"Unsupported image format. Please upload a JPEG, PNG, WEBP, or GIF file. ({e})"
        )

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
    
    # Map intent categories that have a direct application flow
    _INTENT_TO_SERVICE = {
        IntentCategory.PASSPORT: "passport",
        IntentCategory.VISA:     "visa",
        IntentCategory.OCI:      "oci",
        IntentCategory.PIO:      "oci",  # PIO converts to OCI
    }

    # Try deterministic response first (no LLM cost)
    deterministic_response = get_deterministic_response(intent_result)
    if deterministic_response and not request.image_base64 and not is_tracking_query(sanitized_message):
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

        # TC 1.2 — always ask if the information is sufficient
        final_response += "\n\n---\nIs this sufficient information, or do you need more details?"

        # TC 1.3 — if this is a core service, invite them to start the application
        if _FLOW_ENABLED:
            matched_service = _INTENT_TO_SERVICE.get(intent_result.category)
            if matched_service and matched_service in SERVICES:
                svc_name = SERVICES[matched_service]["name"]
                final_response += (
                    f"\n\n**Are you interested in starting the application process for {svc_name}?** "
                    f"Type **apply** to begin."
                )

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
    company_id = request.company_id or get_company_id()

    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # ── Parallel: session creation + knowledge fetch ───────────────────
    session, knowledge_base = await asyncio.gather(
        session_manager.get_or_create_session(
            channel="web",
            user_identifier=user_id,
            session_id=request.session_id,
            metadata={"company_id": company_id, "language": request.language}
        ),
        get_realtime_knowledge(),
    )
    session_id = session['id']

    if company_id:
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if company:
            llm_model = company.get('llm_model', llm_model)

    # ── Parallel: hybrid search + flow state ──────────────────────────
    context_info, current_flow = await asyncio.gather(
        hybrid_search(sanitized_message, knowledge_base),
        get_flow_state(session_id),
    )
    current_state = current_flow.get("state", "idle")

    # ── If in docs_uploading and an image was sent, mark as uploaded ──
    image_doc_data: dict | None = None
    if current_state == "docs_uploading" and request.image_base64:
        image_doc_data = {
            "filename": "uploaded_doc",
            "file_id": str(uuid.uuid4()),
            "status": "uploaded",
        }

    # ── Build service-specific scraped summary ─────────────────────────
    scraped_summary = ""
    active_service = detect_service(sanitized_message) or current_flow.get("service")
    if active_service:
        scraped_summary = extract_service_content(active_service, knowledge_base, user_query=sanitized_message)
    elif detect_website_service(sanitized_message):
        # Website-only service — keyword search from scraped pages (no visa fallback)
        words = [w for w in sanitized_message.lower().split() if len(w) > 3]
        cgi_text = knowledge_base.get("cgi_joburg", {}).get("page_content", "")
        vfs_text = knowledge_base.get("vfs_global", {}).get("page_content", "")
        relevant = [
            l.strip() for l in (cgi_text + "\n" + vfs_text).split("\n")
            if l.strip() and any(w in l.lower() for w in words)
        ]
        scraped_summary = "\n".join(relevant[:15])

    # ── Application flow state machine ────────────────────────────────
    if _FLOW_ENABLED:
        flow_response, needs_llm, current_step = await process_flow(
            session_id, sanitized_message,
            has_image=bool(request.image_base64),
            image_doc_data=image_doc_data,
            user_id=user_id,
            scraped_summary=scraped_summary,
            knowledge_base=knowledge_base,
            preloaded_flow=current_flow,
        )
    else:
        flow_response, needs_llm, current_step = None, True, "idle"

    if flow_response is not None and not needs_llm:
        bot_response = flow_response
    elif flow_response is not None and current_step == "info_shown":
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
OFFICIAL DATA (sourced from cgijoburg.gov.in, vfsglobal.com, and admin-uploaded documents):
{context_info}

FALLBACK RULE: If the information is not in the data above, say so briefly and direct the user to:
  📞 +27 11-4828484 / +27 11 581 9800  |  📧 ccom.jburg@mea.gov.in
  🏢 No. 1, Eton Road (Corner Jan Smuts Avenue & Eton Road), Park Town 2193, Johannesburg
  🕐 Mon–Fri 08:30–17:00 (Lunch: 13:00–13:30)
  VFS Global — Submission: Mon–Fri 08:00–15:00 | Collection: 11:00–16:00 — https://services.vfsglobal.com/zaf/en/ind/"""

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
            # Fire-and-forget: don't block the response on usage tracking
            asyncio.create_task(record_llm_usage(
                session_id=session_id,
                input_text=sanitized_message,
                output_text=bot_response,
                model=llm_model
            ))
        except Exception as e:
            logger.error(f"AI service error: {sanitize_logs(str(e))}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI service error: {str(e)}"
            )

        if _FLOW_ENABLED:
            flow_service = detect_service(sanitized_message)
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
    
    # Store both messages in parallel — no need to wait before returning
    asyncio.create_task(session_manager.add_message(
        session_id=session_id,
        role="user",
        content=request.message,
        metadata={"sanitized": sanitized_message != request.message}
    ))
    asyncio.create_task(session_manager.add_message(
        session_id=session_id,
        role="assistant",
        content=bot_response,
        metadata={"has_audio": audio_base64 is not None}
    ))
    
    return ChatResponse(
        session_id=session_id,
        response=bot_response,
        step=current_step,
        audio_base64=audio_base64
    )


@router.post("/chat/stream", dependencies=[Depends(check_rate_limit)])
async def chat_stream(request: ChatRequest):
    """
    Streaming version of /chat.
    Returns Server-Sent Events so the frontend can render text progressively.
    Non-LLM (deterministic) responses are sent as a single chunk + done event.
    """
    db = await get_database()

    _san = sanitize_user_input(request.message or "", context="web_chat")
    if not _san.is_safe:
        async def _blocked():
            yield f"data: {json.dumps({'error': 'Message blocked for security reasons'})}\n\n"
        return StreamingResponse(_blocked(), media_type="text/event-stream")
    sanitized_message = _san.sanitized_text
    if not sanitized_message:
        async def _empty():
            yield f"data: {json.dumps({'error': 'Empty message'})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    # ── Intent classification (fast, no I/O) ─────────────────────────
    intent_result  = classify_intent(sanitized_message)
    deterministic  = get_deterministic_response(intent_result)

    async def _stream_deterministic(text: str, sid: str, step: str, pdf_url: str = None) -> AsyncGenerator:
        yield f"data: {json.dumps({'chunk': text})}\n\n"
        done_event = {'done': True, 'session_id': sid, 'step': step}
        if pdf_url:
            done_event['pdf_url'] = pdf_url
        yield f"data: {json.dumps(done_event)}\n\n"

    # Only use deterministic shortcut for pure greetings / FAQs with NO active
    # flow and NO apply intent.  "apply visa", "yes", "no" etc. must always
    # reach process_flow so the application state-machine runs correctly.
    if deterministic and not is_apply_intent(sanitized_message) and not is_tracking_query(sanitized_message):
        # Quick peek at flow state — skip deterministic if user is mid-flow
        _quick_flow = await get_flow_state(request.session_id) if request.session_id else {}
        if _quick_flow.get("state", "idle") == "idle":
            session = await session_manager.get_or_create_session(
                channel="web", user_identifier=request.user_id or "guest",
                session_id=request.session_id,
                metadata={"language": request.language}
            )
            return StreamingResponse(
                _stream_deterministic(deterministic, session["id"], "complete"),
                media_type="text/event-stream"
            )

    # ── Full LLM path ─────────────────────────────────────────────────
    user_id   = request.user_id or "guest"
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    session, knowledge_base = await asyncio.gather(
        session_manager.get_or_create_session(
            channel="web", user_identifier=user_id,
            session_id=request.session_id,
            metadata={"language": request.language}
        ),
        get_realtime_knowledge(),
    )
    session_id = session["id"]

    context_info, current_flow = await asyncio.gather(
        hybrid_search(sanitized_message, knowledge_base),
        get_flow_state(session_id),
    )
    current_state = current_flow.get("state", "idle")

    # ── Virus scan + mark as uploaded ────────────────────────────────
    image_doc_data = None
    if request.image_base64:
        from virus_scanner import scan_base64 as _virus_scan_b64
        _scan = await _virus_scan_b64(request.image_base64, "uploaded_doc")
        if not _scan["clean"]:
            threat = _scan.get("threat", "unknown threat")
            logger.warning("[SECURITY] Virus scan blocked upload in chat/stream: %s", threat)
            async def _virus_blocked():
                import json as _json
                yield f"data: {_json.dumps({'chunk': f'🚫 **Security Alert:** This file was flagged as a threat ({threat}) and cannot be processed. Please upload a different document.'})}\n\n"
                yield f"data: {_json.dumps({'done': True, 'session_id': session_id, 'step': 'error'})}\n\n"
            return StreamingResponse(_virus_blocked(), media_type="text/event-stream")

        if current_state == "docs_uploading":
            image_doc_data = {
                "filename": "uploaded_doc",
                "file_id": str(uuid.uuid4()),
                "status": "uploaded",
            }

    active_service = detect_service(sanitized_message) if _FLOW_ENABLED else None
    scraped_summary = extract_service_content(active_service, knowledge_base, user_query=sanitized_message) if active_service else ""

    if _FLOW_ENABLED:
        flow_response, needs_llm, current_step = await process_flow(
            session_id, sanitized_message,
            has_image=bool(request.image_base64),
            image_doc_data=image_doc_data,
            user_id=user_id,
            scraped_summary=scraped_summary,
            knowledge_base=knowledge_base,
            preloaded_flow=current_flow,
        )
    else:
        flow_response, needs_llm, current_step = None, True, "idle"

    # ── Non-LLM flow response ─────────────────────────────────────────
    if _FLOW_ENABLED and flow_response is not None and not needs_llm:
        full_text = flow_response
        asyncio.create_task(session_manager.add_message(session_id, "user", request.message, {}))
        asyncio.create_task(session_manager.add_message(session_id, "assistant", full_text, {}))
        pdf_url = None
        if current_step == "submitted":
            _tid_match = re.search(r"`([A-Z]+-\d{8}-[A-Z0-9]+)`", full_text)
            if _tid_match:
                pdf_url = f"/api/consular/download-pdf/{_tid_match.group(1)}"
        return StreamingResponse(
            _stream_deterministic(full_text, session_id, current_step, pdf_url=pdf_url),
            media_type="text/event-stream"
        )

    # ── Build LLM context ─────────────────────────────────────────────
    llm_context = context_info or ""
    if _FLOW_ENABLED and current_step == "info_shown" and flow_response:
        llm_context = (llm_context + "\n\n---\n\n" + flow_response) if llm_context else flow_response

    detected_svc = detect_service(sanitized_message) if _FLOW_ENABLED else None
    svc_docs_hint = ""
    if detected_svc and detected_svc in SERVICES:
        svc = SERVICES[detected_svc]
        docs = "\n".join(f"  • {d}" for d in svc["documents"])
        svc_docs_hint = f"\nDOCUMENTS REQUIRED FOR {svc['name'].upper()}:\n{docs}\n"

    system_msg = f"""You are Seva Setu Bot, the official consular assistant for the Consulate General of India, Johannesburg.

CRITICAL — DATA SOURCE RULE:
Answer ONLY using the OFFICIAL DATA provided below.
The data comes from: www.cgijoburg.gov.in, vfsglobal.com, and admin-uploaded documents (FAQs, events, notices).
Do NOT use general training knowledge. Do NOT invent or add information not in the data below.
If the answer is not in the data, say so and direct the user to contact the Consulate directly.

LANGUAGE: Always respond in English only.

RESPONSE STYLE:
- Be concise, accurate, and helpful.
- Do NOT echo the user's question back.
- Do NOT add feedback/rating prompts or sign-off phrases.
- Use bullet points only when listing multiple items.
- Do NOT repeat information already shown in the conversation.

KEY CONSULATE FACTS (always use these for contact/location questions):
- Acting Consul General: Mr. Harish Kumar
- Address: No. 1, Eton Road (Corner Jan Smuts Avenue & Eton Road), Park Town 2193, Johannesburg
- Phone: +27 11-4828484 / +27 11-4828485 / +27 11-4828486 / +27 11 581 9800
- Email: ccom.jburg@mea.gov.in (general) | cons.jburg@mea.gov.in (consular/OCI)
- Website: www.cgijoburg.gov.in
- Office Hours: Mon–Fri 08:30–17:00 (Lunch: 13:00–13:30)
- Jurisdiction: Gauteng, North West, Limpopo and Mpumalanga provinces
- VFS Global (Passport/PCC): 2nd Floor, Harrow Court 1, Isle of Houghton, Park Town, JHB — Tel: 012 425 3007
- VFS Global (Visa): 1st Floor, Rivonia Village Office Block, Rivonia, JHB — Tel: 012 425 3007
- VFS Hours: Submission Mon–Fri 08:00–15:00 | Collection 11:00–16:00
{svc_docs_hint}
OFFICIAL DATA (cgijoburg.gov.in | vfsglobal.com | uploaded documents):
{llm_context}

IF NOT IN OFFICIAL DATA: Say "This information is not available in our current records. Please contact the Consulate directly:"
  📞 +27 11-4828484 / +27 11 581 9800  |  📧 ccom.jburg@mea.gov.in
  🏢 No. 1, Eton Road (Corner Jan Smuts Avenue & Eton Road), Park Town 2193, Johannesburg
  🕐 Mon–Fri 08:30–17:00 (Lunch: 13:00–13:30)
  VFS Global — Submission: Mon–Fri 08:00–15:00 | Collection: 11:00–16:00 — https://services.vfsglobal.com/zaf/en/ind/"""

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    chat_instance = LlmChat(
        api_key=api_key, session_id=session_id, system_message=system_msg
    ).with_model("openai", llm_model)

    user_msg_content = []
    if request.image_base64:
        user_msg_content.append(ImageContent(image_base64=request.image_base64))
    user_message = UserMessage(
        text=sanitized_message,
        file_contents=user_msg_content if user_msg_content else None
    )

    # ── Stream generator ──────────────────────────────────────────────
    async def _llm_stream() -> AsyncGenerator:
        full_text = ""
        try:
            if hasattr(chat_instance, "send_message_stream"):
                async for chunk in chat_instance.send_message_stream(user_message):
                    full_text += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            else:
                # Fallback for older LlmChat without streaming support
                full_text = await chat_instance.send_message(user_message)
                yield f"data: {json.dumps({'chunk': full_text})}\n\n"
        except Exception as e:
            logger.error(f"[STREAM] LLM error: {sanitize_logs(str(e))}")
            yield f"data: {json.dumps({'error': 'AI service error, please try again.'})}\n\n"
            return

        if _FLOW_ENABLED:
            flow_service = detect_service(sanitized_message)
            suffix = flow_suffix(current_step, flow_service)
            if suffix:
                full_text += suffix
                yield f"data: {json.dumps({'chunk': suffix})}\n\n"

        yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'step': current_step})}\n\n"

        # Fire-and-forget persistence + usage tracking
        asyncio.create_task(record_llm_usage(
            session_id=session_id, input_text=sanitized_message,
            output_text=full_text, model=llm_model
        ))
        asyncio.create_task(session_manager.add_message(session_id, "user", request.message, {}))
        asyncio.create_task(session_manager.add_message(session_id, "assistant", full_text, {}))

    return StreamingResponse(_llm_stream(), media_type="text/event-stream")


@router.post("/document-scan")
async def document_scan(request: DocumentScanRequest):
    db = await get_database()

    # ── TC 3.1 — Virus / malware scan before any processing ──────────
    from virus_scanner import scan_base64 as _virus_scan_b64
    _scan = await _virus_scan_b64(request.image_base64, f"document_scan/{request.document_type}")
    if not _scan["clean"]:
        threat = _scan.get("threat", "unknown threat")
        logger.warning("[SECURITY] Virus scan blocked document-scan upload: %s", threat)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"🚫 Security Alert: This file was flagged as a threat ({threat}) "
                "and cannot be processed. Please upload a different document."
            ),
        )

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
    
    try:
        normalized_b64, media_type = _normalize_image(request.image_base64)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    image_content = ImageContent(image_base64=normalized_b64, media_type=media_type)
    user_message = UserMessage(
        text=f"Extract all information from this {request.document_type}. Translate to English if needed.",
        file_contents=[image_content]
    )

    try:
        extracted_data = await chat_instance.send_message(user_message)

        # ── TC 3.2 / 3.3 — Parse OCR JSON and store doc_context in session flow ──
        doc_context: dict = {}
        try:
            import re as _re
            _json_str = extracted_data
            # Strip markdown code fences if LLM wrapped the JSON
            _fence = _re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", _json_str)
            if _fence:
                _json_str = _fence.group(1)
            _parsed = json.loads(_json_str)
            doc_context = _parsed.get("extracted_fields", {})
        except Exception:
            pass  # Non-JSON response — doc_context stays empty; raw text still stored

        # Persist: raw extracted text + structured doc_context into session
        _update: dict = {
            "extracted_data":        extracted_data,
            "document_type":         request.document_type,
            "extraction_timestamp":  datetime.now(timezone.utc).isoformat(),
        }
        if doc_context:
            # Merge into the flow's doc_context so auto-fill can use it (TC 3.4)
            _update["flow.doc_context"] = doc_context

        await db.chat_sessions.update_one(
            {"id": request.session_id},
            {"$set": _update},
        )

        # Build a human-readable confirmation for the user (TC 3.2)
        _confirm_lines = []
        _field_labels = {
            "full_name":       "Name",
            "date_of_birth":   "Date of Birth",
            "document_number": "Document Number",
            "nationality":     "Nationality",
            "address":         "Address",
            "place_of_birth":  "Place of Birth",
            "issue_date":      "Issue Date",
            "expiry_date":     "Expiry Date",
        }
        for k, label in _field_labels.items():
            v = doc_context.get(k)
            if v and str(v).strip().lower() not in ("", "n/a", "null", "none", "unknown"):
                _confirm_lines.append(f"  • **{label}:** {v}")
        _confirm_msg = (
            "✅ Document scanned successfully. Here are the details we extracted:\n\n"
            + "\n".join(_confirm_lines)
            + "\n\nThese details will be used to pre-fill your application form."
            if _confirm_lines
            else "✅ Document scanned. We'll use the extracted data to assist with your application."
        )

        return {
            "success": True,
            "extracted_data": extracted_data,
            "doc_context": doc_context,
            "confirmation_message": _confirm_msg,
            "message": "Document processed successfully. Data extracted and translated to English for form filling."
        }
    except HTTPException:
        raise
    except Exception as e:
        err = str(e)
        if "unsupported image" in err.lower() or "invalid_image_format" in err.lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid document format. Please upload a JPEG, PNG, WEBP, or GIF image."
            )
        logger.error(f"Document scan error: {sanitize_logs(err)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Document scan failed. Please try again."
        )

@router.get("/generate-pdf")
async def generate_pdf(session_id: str):
    """
    TC 4.1 — Generate an editable AcroForm PDF preview of the applicant's form.

    Called by the frontend when the user is in docs_pending state.
    Returns the PDF as a binary file download.
    """
    db = await get_database()

    # Load session and flow
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    flow = session.get("flow", {})
    service_key  = flow.get("service")
    form_data    = flow.get("data", {})
    tracking_id  = flow.get("tracking_id", "UNKNOWN")
    uploaded_docs = flow.get("uploaded_docs", [])

    if not service_key or service_key not in SERVICES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No active application found for this session.",
        )

    service_name = SERVICES[service_key]["name"]

    try:
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None,
            lambda: generate_application_pdf(
                service_name=service_name,
                form_data=form_data,
                tracking_id=tracking_id,
                uploaded_docs=uploaded_docs,
            ),
        )
    except Exception as e:
        logger.error(f"PDF generation error: {sanitize_logs(str(e))}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF generation failed. Please try again.",
        )

    safe_name = service_name.lower().replace(" ", "_")
    filename = f"application_preview_{safe_name}_{tracking_id}.pdf"

    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download-pdf/{tracking_id}")
async def download_pdf_by_tracking(tracking_id: str):
    """
    Generate and download the submitted application PDF using tracking ID.
    Called automatically after submission (session flow may already be cleared).
    """
    db = await get_database()

    app = await db.applications.find_one({"tracking_id": tracking_id.upper()}, {"_id": 0})
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")

    service_key   = app.get("service")
    form_data     = app.get("form_data", {})
    uploaded_docs = [
        {"name": d.get("name", "Document"), "status": d.get("status", "uploaded")}
        for d in app.get("documents", [])
    ]

    if not service_key or service_key not in SERVICES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Service information not available for this application.",
        )

    service_name = SERVICES[service_key]["name"]

    try:
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None,
            lambda: generate_application_pdf(
                service_name=service_name,
                form_data=form_data,
                tracking_id=tracking_id.upper(),
                uploaded_docs=uploaded_docs,
            ),
        )
    except Exception as e:
        logger.error(f"PDF generation error: {sanitize_logs(str(e))}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF generation failed. Please try again.",
        )

    safe_name = service_name.lower().replace(" ", "_")
    filename = f"application_{safe_name}_{tracking_id.upper()}.pdf"

    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
You: "OCI (Overseas Citizen of India) provides a multi-purpose, multi-entry life-long visa to India. Eligible persons include those who were citizens of India on or after 26 Jan 1950, or whose parents/grandparents were Indian citizens, or spouses of Indian citizens/OCI holders (married ≥2 years), or minor children of Indian citizens. Apply online at ociservices.gov.in and submit documents at the Consulate (appointment via cons.jburg@mea.gov.in). Fees as per MEA notification."

User: "How to renew passport?"
You: "**Passport Renewal Steps:**
1. Book appointment on passportindia.gov.in
2. Fill online application form
3. Visit with: old passport, photos, address proof
4. Pay fee (ZAR 2,280 for 36-page / ZAR 2,655 for 60-page / ZAR 780 for minor/ETD)
Processing: as per Consulate schedule"

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


@router.get("/applications/lookup")
async def lookup_applications_by_contact(contact: str):
    """
    Find applications by email or phone number.
    GET /api/consular/applications/lookup?contact=user@example.com
    GET /api/consular/applications/lookup?contact=+27811234567
    """
    import re as _re
    db = await get_database()
    contact = contact.strip()
    is_email = bool(_re.match(r'.+@.+\..+', contact))
    field = "form_data.email" if is_email else "form_data.phone"
    cursor = db.applications.find(
        {field: {"$regex": _re.escape(contact), "$options": "i"}},
        {"_id": 0}
    ).sort("created_at", -1).limit(20)
    apps = await cursor.to_list(length=20)
    if not apps:
        raise HTTPException(status_code=404, detail=f"No applications found for '{contact}'.")
    return {
        "contact": contact,
        "total": len(apps),
        "applications": [
            {
                "tracking_id":        a["tracking_id"],
                "service":            a["service"],
                "service_name":       a["service_name"],
                "status":             a["status"],
                "created_at":         a["created_at"],
                "submitted_at":       a.get("submitted_at"),
                "form_data":          a.get("form_data", {}),
                "documents_uploaded": sum(1 for d in a.get("documents", []) if d.get("status") == "uploaded"),
                "documents_required": len(a.get("required_documents", [])),
                "documents":          a.get("documents", []),
            }
            for a in apps
        ],
    }
