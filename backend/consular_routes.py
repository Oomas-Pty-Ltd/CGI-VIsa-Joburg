from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, AsyncGenerator
import asyncio
import re
import uuid
import json
import logging as _logging
import time as _time
from datetime import datetime, timezone
import base64
import hashlib
import os


# Standard SSE response headers — disable proxy/CDN/browser buffering so chunks
# reach the client as they're yielded.
#   - X-Accel-Buffering: no       → nginx disables buffering for THIS response only
#   - Cache-Control: no-cache,no-transform → tells Cloudflare/CDNs not to cache or transform
#   - Connection: keep-alive       → keep the SSE connection open
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse(generator, status_code: int = 200) -> StreamingResponse:
    """Build an SSE StreamingResponse with anti-buffering headers."""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        status_code=status_code,
        headers=_SSE_HEADERS,
    )


class _StageTimer:
    """Lightweight per-request stage timer.

    Usage:
        t = _StageTimer("chat_stream")
        t.mark("sanitize"); ... ; t.mark("hybrid_flow")
        t.flush(extra="msg_len=42")
    """
    _log = _logging.getLogger("timing.chat")
    _enabled = os.environ.get("TIMING_LOGS", "1") != "0"

    __slots__ = ("label", "t0", "last", "parts", "ttft_ms", "_done")

    def __init__(self, label: str):
        self.label = label
        self.t0 = _time.perf_counter()
        self.last = self.t0
        self.parts: list[str] = []
        self.ttft_ms: int | None = None
        self._done = False

    def mark(self, name: str) -> None:
        if not self._enabled:
            return
        now = _time.perf_counter()
        self.parts.append(f"{name}={int((now - self.last) * 1000)}")
        self.last = now

    def mark_ttft(self) -> None:
        """Call once when the first LLM token is received."""
        if not self._enabled or self.ttft_ms is not None:
            return
        self.ttft_ms = int((_time.perf_counter() - self.t0) * 1000)

    def flush(self, extra: str = "") -> None:
        if not self._enabled or self._done:
            return
        self._done = True
        total_ms = int((_time.perf_counter() - self.t0) * 1000)
        line = f"[CHAT-TIMING:{self.label}] " + " ".join(self.parts)
        if self.ttft_ms is not None:
            line += f" ttft={self.ttft_ms}"
        line += f" total={total_ms}"
        if extra:
            line += f" {extra}"
        self._log.info(line)
from database import get_database
from auth_utils import verify_token
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from knowledge_scraper import (
    get_realtime_knowledge,
    search_knowledge,
    extract_service_content,
    BLOCKED_SENTINEL,
    _get_blocked_keywords,
    filter_blocked_lines,
    blocked_prohibition,
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
from tenant import get_tenant_id
from services.bot_config import get_bot_config

# Services imports
from services.intent_classifier import detect_target_language
from services.escalation_service import (
    escalation_service,
    EscalationReason,
    EscalationPriority
)
from services.knowledge_service import knowledge_service
from services.application_flow import process_flow, flow_suffix, detect_service, detect_website_service, get_flow_state, is_apply_intent, is_tracking_query, preload_flow_keywords, preload_service_patterns, ui_hints_for_state
from services.service_registry import get_service
from services.pdf_service import generate_application_pdf
from fastapi.responses import Response as FastAPIResponse

load_dotenv()

# ── Language support ──────────────────────────────────────────────────────────
_LANG_NAMES: dict[str, str] = {
    # English
    "en":  "English",
    # Indian languages
    "hi":  "Hindi",
    "bn":  "Bengali",
    "mr":  "Marathi",
    "te":  "Telugu",
    "ta":  "Tamil",
    "gu":  "Gujarati",
    "ur":  "Urdu",
    "kn":  "Kannada",
    "or":  "Odia",
    "ml":  "Malayalam",
    "pa":  "Punjabi",
    "as":  "Assamese",
    "mai": "Maithili",
    "sa":  "Sanskrit",
    "sat": "Santali",
    "ks":  "Kashmiri",
    "ne":  "Nepali",
    "sd":  "Sindhi",
    "doi": "Dogri",
    "kok": "Konkani",
    "mni": "Manipuri",
    "brx": "Bodo",
    "mwr": "Marwari",
    # South African languages
    "zu":  "Zulu",
    "xh":  "Xhosa",
    "af":  "Afrikaans",
    "nso": "Sepedi",
    "tn":  "Setswana",
    "st":  "Sesotho",
    "ts":  "Xitsonga",
    "ss":  "siSwati",
    "ve":  "Tshivenda",
    "nr":  "isiNdebele",
    # International languages
    "ar":  "Arabic",
    "fr":  "French",
    "sw":  "Swahili",
    "ha":  "Hausa",
    "yo":  "Yoruba",
    "ig":  "Igbo",
    "am":  "Amharic",
    "om":  "Oromo",
}

_LANG_SCRIPT_HINT: dict[str, str] = {
    # Devanagari-script languages — must NOT use Urdu/Perso-Arabic script
    "hi":  "You MUST write in Devanagari script (देवनागरी). Do NOT use Urdu/Perso-Arabic script (اردو). Do NOT mix languages.",
    "mr":  "You MUST write in Devanagari script (देवनागरी). Do NOT use Urdu/Perso-Arabic script.",
    "ne":  "You MUST write in Devanagari script (देवनागरी).",
    "sa":  "You MUST write in Devanagari script (देवनागरी).",
    "doi": "You MUST write in Devanagari script (देवनागरी).",
    # Urdu — Perso-Arabic script
    "ur":  "You MUST write in Perso-Arabic script (اردو رسم الخط). Do NOT use Devanagari script.",
    # Punjabi — Gurmukhi script (not Shahmukhi/Arabic)
    "pa":  "You MUST write in Gurmukhi script (ਗੁਰਮੁਖੀ). Do NOT use Shahmukhi/Perso-Arabic script.",
    # Tamil — ensure Tamil script not Telugu or similar
    "ta":  "You MUST write in Tamil script (தமிழ் எழுத்து). Do NOT use any other South Indian script.",
    "te":  "You MUST write in Telugu script (తెలుగు లిపి).",
    "kn":  "You MUST write in Kannada script (ಕನ್ನಡ ಲಿಪಿ).",
    "ml":  "You MUST write in Malayalam script (മലയാളം ലിപി).",
    "gu":  "You MUST write in Gujarati script (ગુજરાતી લિપિ).",
    "bn":  "You MUST write in Bengali script (বাংলা লিপি).",
    "or":  "You MUST write in Odia script (ଓଡ଼ିଆ ଲିପି).",
    "as":  "You MUST write in Bengali-Assamese script (অসমীয়া লিপি).",
}

def _lang_instruction(code: str) -> str:
    """Return the LANGUAGE system-prompt line for the given language code."""
    code = (code or "en").lower()
    name = _LANG_NAMES.get(code, "English")
    if code == "en":
        return "LANGUAGE: Respond in English."
    script_hint = _LANG_SCRIPT_HINT.get(code, "")
    script_line = f" {script_hint}" if script_hint else ""
    return (
        f"LANGUAGE: The user has selected {name} as their preferred language. "
        f"You MUST respond entirely in {name}.{script_line} "
        f"Even if the user writes in English, always reply in {name}. "
        f"Proper nouns, addresses, phone numbers, email addresses, URLs, and "
        f"tracking IDs must remain unchanged (do not translate them)."
    )

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


# Platform defaults — used when a tenant hasn't overridden the value on
# bot_config.security_config. Resolution happens via cfg.security() at the
# call site so per-tenant overrides actually apply.
DEFAULT_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_PDF_PAGES    = 5
PDF_RENDER_DPI = 144   # not tenant-configurable: 144 DPI is a render quality, not a policy

def _build_scope_rules(out_of_scope_refusal: str, service_names: list[str]) -> str:
    """Build per-tenant SCOPE block for the LLM system prompt.

    ``service_names`` is the list of enabled services for this tenant (from
    ``tenant_services``). ``out_of_scope_refusal`` comes from the tenant's
    ``fallback_responses.out_of_scope`` bot-config field.
    """
    if service_names:
        svc_list = "\n".join(f"  • {n}" for n in service_names)
        scope_clause = (
            f"- You answer questions about the services this organisation offers:\n"
            f"{svc_list}\n"
            "  Also answer questions about appointments, fees, required documents, "
            "office hours, contact info, and any related procedure for the services above."
        )
    else:
        scope_clause = (
            "- You answer questions about the services, procedures, and information "
            "offered by this organisation."
        )

    return f"""SCOPE — STRICT:
{scope_clause}
- Greetings ("hi", "hello", "good morning"), thanks, and farewells are ALWAYS allowed. Reply with a brief, warm one-line acknowledgement and invite the user to ask about available services. Do NOT use the scope refusal line for these.
- For genuinely off-topic questions — general knowledge, math, arithmetic, jokes, riddles, weather, coding, politics, role-play, hypotheticals, or "what if" trivia — reply with EXACTLY this one line and nothing else:
  "{out_of_scope_refusal}"
- Do not perform calculations. Do not entertain off-topic premises even when the user pushes back. Repeat the scope line."""


def _build_contact_facts(bot_cfg, blocked_kws: list[str]) -> str:
    """Build the CONSULATE FACTS block from the tenant's configured contact info."""
    c = bot_cfg.contact or {}
    lines = []
    if c.get("address"):      lines.append(f"- Address: {c['address']}")
    if c.get("phone"):        lines.append(f"- Phone: {c['phone']}")
    if c.get("email"):        lines.append(f"- Email: {c['email']}")
    if c.get("website"):      lines.append(f"- Website: {c['website']}")
    if c.get("office_hours"): lines.append(f"- Office Hours: {c['office_hours']}")
    if c.get("consular_hours"): lines.append(f"- Consular Hours: {c['consular_hours']}")
    return filter_blocked_lines("\n".join(lines), blocked_kws)


def _build_footer_contact(bot_cfg, blocked_kws: list[str]) -> str:
    """Build the fallback contact footer shown when the bot can't answer."""
    c = bot_cfg.contact or {}
    parts = []
    if c.get("phone"):        parts.append(f"📞 {c['phone']}")
    if c.get("email"):        parts.append(f"📧 {c['email']}")
    if c.get("address"):      parts.append(f"🏢 {c['address']}")
    if c.get("office_hours"): parts.append(f"🕐 {c['office_hours']}")
    raw = "  " + "\n  ".join(parts) if parts else f"  Contact {bot_cfg.org_name or 'the organisation'} directly."
    return filter_blocked_lines(raw, blocked_kws)


def _resolve_user_id(
    req_user_id: Optional[str],
    http_request: Optional[Request],
    visitor_id: Optional[str] = None,
) -> str:
    """Resolve the session-manager ``user_identifier`` for a request.

    Priority (highest first):
      1. ``req_user_id`` — explicit user_id from an authenticated client
         (e.g. ``seva_user_id`` after OTP login).
      2. ``visitor_id`` — stable per-browser token persisted in
         localStorage by ChatWidget. Two anonymous visitors on the same
         IP get different identifiers — without this they share a
         session because the IP-hash fallback bucketed them together.
      3. ``"guest:<sha256(client_ip)[:16]>"`` — last-ditch fallback so
         legacy callers without a visitor_id keep working. Two users
         behind the same NAT still collide here; tell new clients to
         send a visitor_id to avoid that.
    """
    if req_user_id and req_user_id != "guest":
        return req_user_id
    if visitor_id and visitor_id.strip():
        return "visitor:" + visitor_id.strip()
    client_ip = "unknown"
    if http_request and http_request.client:
        client_ip = http_request.client.host or "unknown"
    return "guest:" + hashlib.sha256(client_ip.encode("utf-8")).hexdigest()[:16]


def _render_pdf_pages(image_base64: str, max_pages: int = DEFAULT_MAX_PDF_PAGES) -> list[tuple[str, str]]:
    """Render a base64-encoded PDF into up to ``max_pages`` PNG pages.
    Returns a list of (page_b64, "image/png"). Raises ValueError on failure.
    """
    import fitz  # PyMuPDF — already in requirements.txt
    try:
        raw = base64.b64decode(image_base64)
    except Exception as e:
        raise ValueError(f"Invalid PDF data (could not decode base64). ({e})")
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as e:
        raise ValueError(f"Could not open PDF. ({e})")
    try:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages.")
        page_count = min(doc.page_count, max_pages)
        scale = PDF_RENDER_DPI / 72.0
        mat = fitz.Matrix(scale, scale)
        pages: list[tuple[str, str]] = []
        for i in range(page_count):
            pix = doc[i].get_pixmap(matrix=mat, alpha=False)
            pages.append((base64.b64encode(pix.tobytes("png")).decode(), "image/png"))
        return pages
    finally:
        doc.close()


def _validate_and_normalize_upload(
    image_base64: str,
    max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    max_pdf_pages: int = DEFAULT_MAX_PDF_PAGES,
) -> list[tuple[str, str]]:
    """Enforce the size cap, then expand the upload into one or more
    (b64, media_type) pages ready to attach to a vision-model message.

    Limits come from the tenant's ``bot_config.security_config``; callers
    that already have a ``BotConfig`` instance should pass the resolved
    values from ``cfg.security()``. Defaults match the previous platform
    behaviour so legacy callers keep working unchanged.

    Raises ValueError on rejection (oversize, unrecoverable format, etc.).
    """
    approx_bytes = (len(image_base64) * 3) // 4
    if approx_bytes > max_bytes:
        max_mb = max_bytes / (1024 * 1024)
        raise ValueError(
            f"File too large. Maximum upload size is {max_mb:.1f} MB "
            f"(your file is approximately {approx_bytes / (1024 * 1024):.1f} MB). "
            f"Please compress the file or send a smaller one."
        )
    # PDF magic bytes — render each page as a PNG so the vision model can read it.
    if image_base64[:10].startswith("JVBER"):
        return _render_pdf_pages(image_base64, max_pages=max_pdf_pages)
    b64, mime = _normalize_image(image_base64)
    return [(b64, mime)]


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
    # Stable per-browser visitor token (uuid stored in localStorage by
    # ChatWidget). Used as the session-manager ``user_identifier`` so two
    # anonymous visitors on the same IP / behind the same NAT don't get
    # bucketed into the same session.
    visitor_id: Optional[str] = None
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
async def chat(
    request: ChatRequest,
    http_request: Request,
    tenant_id: str = Depends(get_tenant_id),
):
    db = await get_database()

    # Get client IP for rate limiting logging
    client_ip = http_request.client.host if http_request.client else "unknown"

    _resolved_user_id = _resolve_user_id(request.user_id, http_request, getattr(request, "visitor_id", None))

    # Preload tenant flow-keywords so sync is_apply_intent / is_yes / etc.
    # below use per-tenant overrides.
    await preload_flow_keywords(tenant_id)
    await preload_service_patterns(tenant_id)

    # Sanitize and validate user input
    sanitization_result = sanitize_user_input(request.message, context="web_chat")

    if not sanitization_result.is_safe:
        logger.warning(f"[SECURITY] Blocked unsafe input from {client_ip}: {sanitization_result.detected_patterns}")
        _cfg = await get_bot_config(tenant_id)
        try:
            from services.notification_dispatcher import notify
            await notify("security.guardrail_triggered", company_id=tenant_id, context={
                "rule": ", ".join(sanitization_result.detected_patterns or []) or "unsafe_input",
            })
        except Exception:
            logger.exception("security.guardrail_triggered notify failed")
        return ChatResponse(
            session_id=request.session_id or str(uuid.uuid4()),
            response=_cfg.fallback("blocked_input") or "I cannot process that request.",
            step="error"
        )

    # Validate upload size + format up-front so we don't pay for a virus scan
    # or LLM call on a doomed request. We keep request.image_base64 as the
    # *original* bytes so downstream virus-scan / has_image checks still work;
    # _validated_pages holds the renderings sent to the vision model.
    _validated_pages: list[tuple[str, str]] = []
    if request.image_base64:
        try:
            _sec = _cfg.security()
            _validated_pages = _validate_and_normalize_upload(
                request.image_base64,
                max_bytes=_sec["upload_max_bytes"],
                max_pdf_pages=_sec["upload_max_pdf_pages"],
            )
        except ValueError as _ve:
            return ChatResponse(
                session_id=request.session_id or str(uuid.uuid4()),
                response=str(_ve),
                step="error"
            )

    sanitized_message = request.message

    # Escalation check — keyword-based, no LLM cost. Tenant-scoped so
    # per-tenant keyword/pattern overrides on bot_config apply.
    _should_escalate, _esc_reason, _esc_priority = await escalation_service.should_escalate(
        sanitized_message, company_id=tenant_id
    )
    if _should_escalate:
        user_id = _resolved_user_id
        session_id = request.session_id or str(uuid.uuid4())
        session = await session_manager.get_or_create_session(
            channel="web",
            user_identifier=user_id,
            session_id=session_id
        )
        escalation = await escalation_service.create_escalation(
            session_id=session['id'],
            user_identifier=user_id,
            channel="web",
            reason=_esc_reason,
            priority=_esc_priority,
            description=sanitized_message,
            company_id=tenant_id,
            conversation_history=session.get('messages', [])
        )
        response = await escalation_service.get_escalation_response(_esc_priority, company_id=tenant_id)
        response += f"\n\n**Reference ID:** {escalation.id[:8].upper()}"
        try:
            from services.notification_dispatcher import notify
            await notify("chat.escalation_requested", company_id=tenant_id, context={
                "session_id": session['id'], "reason": _esc_reason,
            })
        except Exception:
            logger.exception("chat.escalation_requested notify failed")
        return ChatResponse(
            session_id=session['id'],
            response=response,
            step="escalated"
        )

    # All other messages → LLM with tenant-specific context
    user_id    = _resolved_user_id
    # tenant_id is the canonical company_id (from X-Company-Id header, falling
    # back to the env var inside get_tenant_id). The request.company_id body
    # field is preserved on the Pydantic model for back-compat but no longer
    # affects behavior.
    company_id = tenant_id

    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # ── Parallel: session creation + knowledge fetch ───────────────────
    session, knowledge_base = await asyncio.gather(
        session_manager.get_or_create_session(
            channel="web",
            user_identifier=user_id,
            session_id=request.session_id,
            metadata={"company_id": company_id, "language": request.language}
        ),
        get_realtime_knowledge(company_id),
    )
    session_id = session['id']

    if company_id:
        company = await db.companies.find_one({"id": company_id}, {"_id": 0})
        if company:
            llm_model = company.get('llm_model', llm_model)

    # ── Parallel: hybrid search + flow state ──────────────────────────
    context_info, current_flow = await asyncio.gather(
        hybrid_search(sanitized_message, knowledge_base, tenant_id),
        get_flow_state(session_id),
    )
    current_state = current_flow.get("state", "idle")

    # ── Blocked keyword: return immediately without calling LLM ────────
    if context_info == BLOCKED_SENTINEL:
        _blk_cfg = await get_bot_config(company_id)
        _blk_footer = _build_footer_contact(_blk_cfg, [])
        bot_response = f"I'm sorry, I don't have information on that topic. For assistance, please contact us directly:\n{_blk_footer}"
        await session_manager.add_message(session_id, "user", sanitized_message)
        await session_manager.add_message(session_id, "assistant", bot_response)
        return JSONResponse({"response": bot_response, "session_id": session_id})

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
            session_id, sanitized_message, tenant_id,
            has_image=bool(request.image_base64),
            image_doc_data=image_doc_data,
            user_id=user_id,
            scraped_summary=scraped_summary,
            knowledge_base=knowledge_base,
            preloaded_flow=current_flow,
        )
    else:
        flow_response, needs_llm, current_step = None, True, "idle"

    # For non-English: flow hardcoded strings are English — route through LLM to translate
    if flow_response is not None and not needs_llm and request.language and request.language != "en":
        needs_llm = True

    if flow_response is not None and not needs_llm:
        bot_response = flow_response
    elif flow_response is not None and current_step == "info_shown" and (not request.language or request.language == "en"):
        bot_response = flow_response
    else:
        # LLM needed (info query, question during pause, etc.)

        # Detect service for info context
        detected_svc_key = detect_service(sanitized_message)
        detected_svc_obj = await get_service(tenant_id, detected_svc_key) if detected_svc_key else None
        svc_docs_hint = ""
        if detected_svc_obj:
            docs = "\n".join(f"  • {d}" for d in detected_svc_obj.documents)
            svc_docs_hint = (
                f"\nDOCUMENTS REQUIRED FOR {detected_svc_obj.name.upper()}:\n{docs}\n"
            )

        # When a known-good English answer exists (flow or deterministic), pass it as
        # translation context so the LLM translates it rather than searching from scratch.
        _flow_translate_hint = ""
        if request.language and request.language != "en":
            _translate_source = flow_response if flow_response is not None else deterministic_response
            if _translate_source:
                _flow_translate_hint = (
                    f"\nINTENDED RESPONSE (translate this exactly into the user's selected language, "
                    f"keeping all proper nouns, addresses, phone numbers, email addresses, URLs, "
                    f"and IDs unchanged):\n{_translate_source}\n"
                )

        _blocked_kws = await _get_blocked_keywords()
        _clean_ctx = filter_blocked_lines(context_info, _blocked_kws)
        _clean_svc_hint = filter_blocked_lines(svc_docs_hint, _blocked_kws)
        _prohibition = blocked_prohibition(_blocked_kws)

        _bot_cfg = await get_bot_config(company_id)
        _ns_svc_rows = await db.tenant_services.find(
            {"company_id": company_id, "enabled": True}, {"_id": 0, "name": 1}
        ).sort("display_order", 1).to_list(50)
        _ns_svc_names = [r["name"] for r in _ns_svc_rows if r.get("name")]

        _consulate_facts = _build_contact_facts(_bot_cfg, _blocked_kws)
        _footer_contact  = _build_footer_contact(_bot_cfg, _blocked_kws)
        _ns_scope        = _build_scope_rules(
            _bot_cfg.fallback("out_of_scope"), _ns_svc_names
        )
        _org_label_ns = _bot_cfg.org_name or _bot_cfg.bot_name
        _base_system_message = f"""You are {_bot_cfg.bot_name}, the official assistant for {_org_label_ns}.
{_prohibition}
{_lang_instruction(request.language or "en")}

{_ns_scope}

RESPONSE STYLE:
- Be concise, accurate, and helpful.
- Do NOT echo the user's question back.
- Do NOT add feedback/rating prompts or sign-off phrases.
- Do NOT ask clarifying questions like "What information do you need?" — provide the complete relevant answer directly.
- Use bullet points only when listing multiple items.
- Do NOT repeat information already shown in the conversation.
- When an INTENDED RESPONSE is provided below, translate it completely and faithfully — do not summarise, shorten, or omit any field.
{f'''
OFFICIAL DATA — always use the facts below to answer questions. This is the authoritative source.

ORGANISATION FACTS:
{_consulate_facts}
''' if _consulate_facts else ''}
{_clean_svc_hint}
ADDITIONAL KNOWLEDGE (from uploaded documents, knowledge base, and web sources):
{_clean_ctx}

IF the answer is not in any of the data above, say so briefly and direct the user to:
{_footer_contact}{_flow_translate_hint}"""

        api_key = os.environ.get('EMERGENT_LLM_KEY')
        chat_instance = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=_base_system_message
        ).with_model("openai", llm_model)

        user_msg_content = [
            ImageContent(image_base64=_b64, media_type=_mime)
            for _b64, _mime in _validated_pages
        ]

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
            # Per-tenant cost ledger (Sprint 14 — Cost dashboard). Uses
            # the actual OpenAI usage from `LlmChat.last_usage` rather
            # than the char-count estimate above, so the tenant view is
            # billing-grade accurate.
            from services import llm_usage as _llm_usage
            asyncio.create_task(_llm_usage.log(tenant_id, chat_instance.last_usage))
        except Exception as e:
            logger.error(f"AI service error: {sanitize_logs(str(e))}")
            try:
                from services.notification_dispatcher import notify
                await notify("llm.provider_error", context={
                    "provider": "openai", "model": llm_model, "error": str(e)[:200],
                })
            except Exception:
                logger.exception("llm.provider_error notify failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI service error: {str(e)}"
            )

        if _FLOW_ENABLED:
            flow_service = detect_service(sanitized_message)
            suffix = await flow_suffix(current_step, flow_service, tenant_id)
            if suffix:
                bot_response += suffix

    # Generate voice response if requested
    audio_base64 = None
    if request.enable_voice:
        try:
            # Detect language from message
            lang_code = request.language or "en"
            audio_base64 = await voice_service.text_to_speech(bot_response, lang_code, company_id=tenant_id)
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
async def chat_stream(
    request: ChatRequest,
    http_request: Request,
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Streaming version of /chat.
    Returns Server-Sent Events so the frontend can render text progressively.
    Non-LLM (deterministic) responses are sent as a single chunk + done event.
    """
    db = await get_database()
    _t = _StageTimer("chat_stream")

    _resolved_user_id = _resolve_user_id(request.user_id, http_request, getattr(request, "visitor_id", None))

    # Preload tenant flow keywords for sync apply/yes/no/discard helpers.
    await preload_flow_keywords(tenant_id)
    await preload_service_patterns(tenant_id)

    _san = sanitize_user_input(request.message or "", context="web_chat")
    _t.mark("sanitize")
    if not _san.is_safe:
        _t.flush(extra="path=blocked_unsafe")
        async def _blocked():
            yield f"data: {json.dumps({'error': 'Message blocked for security reasons'})}\n\n"
        return _sse(_blocked())
    sanitized_message = _san.sanitized_text
    if not sanitized_message:
        _t.flush(extra="path=empty")
        async def _empty():
            yield f"data: {json.dumps({'error': 'Empty message'})}\n\n"
        return _sse(_empty())

    # Validate upload size + format up-front so we fail with a friendly SSE error
    # rather than burning a virus scan + LLM round-trip on a doomed request.
    # NOTE: do NOT overwrite request.image_base64 — the virus scanner below should
    # see the *original* bytes (especially for PDFs, which we render into images for
    # the LLM but must scan as raw PDF).
    _validated_pages: list[tuple[str, str]] = []
    if request.image_base64:
        try:
            _stream_cfg = await get_bot_config(tenant_id)
            _stream_sec = _stream_cfg.security()
            _validated_pages = _validate_and_normalize_upload(
                request.image_base64,
                max_bytes=_stream_sec["upload_max_bytes"],
                max_pdf_pages=_stream_sec["upload_max_pdf_pages"],
            )
        except ValueError as _ve:
            _t.flush(extra="path=upload_rejected")
            _err_msg = str(_ve)
            async def _bad_upload():
                yield f"data: {json.dumps({'error': _err_msg})}\n\n"
            return _sse(_bad_upload())

    # ── Language-switch: detect target language, return signal to frontend ──
    _lang_switch_code = await detect_target_language(sanitized_message, company_id=tenant_id)

    async def _stream_deterministic(text: str, sid: str, step: str, pdf_url: str = None, lang_switch: str = None) -> AsyncGenerator:
        yield f"data: {json.dumps({'chunk': text})}\n\n"
        done_event = {'done': True, 'session_id': sid, 'step': step}
        if pdf_url:
            done_event['pdf_url'] = pdf_url
        if lang_switch:
            done_event['lang_switch'] = lang_switch
        # Tell the widget which input controls to surface for the next
        # turn. Hides upload + camera unless the flow state actually
        # wants them — see services.application_flow.ui_hints_for_state.
        try:
            _fs = await get_flow_state(sid)
            done_event['ui_hints'] = ui_hints_for_state((_fs or {}).get('state'))
        except Exception:
            pass
        yield f"data: {json.dumps(done_event)}\n\n"

    _t.mark("lang_switch")
    if _lang_switch_code:
        session = await session_manager.get_or_create_session(
            channel="web", user_identifier=_resolved_user_id,
            session_id=request.session_id,
            metadata={"language": request.language, "company_id": tenant_id},
        )
        _t.mark("session")
        _t.flush(extra="path=lang_switch")
        return _sse(
            _stream_deterministic("🌐 Switching language...", session["id"], "complete", lang_switch=_lang_switch_code)
        )

    # ── Full LLM path ─────────────────────────────────────────────────
    user_id   = _resolved_user_id
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    # Thread `company_id` into session metadata so the session manager's
    # tenant-scoped lookup (channel + user_identifier + company_id) finds
    # this tenant's session rather than falling through to the env-var
    # default tenant. Missing this scoped a Phase-2 widget call to the
    # CGI default tenant even when X-Company-Id pointed elsewhere.
    session, knowledge_base = await asyncio.gather(
        session_manager.get_or_create_session(
            channel="web", user_identifier=user_id,
            session_id=request.session_id,
            metadata={"language": request.language, "company_id": tenant_id},
        ),
        get_realtime_knowledge(tenant_id),
    )
    session_id = session["id"]
    _t.mark("session_kb")

    context_info, current_flow = await asyncio.gather(
        hybrid_search(sanitized_message, knowledge_base, tenant_id),
        get_flow_state(session_id),
    )
    current_state = current_flow.get("state", "idle")
    _t.mark("hybrid_flow")

    # ── Blocked keyword: stream canned response without calling LLM ───
    if context_info == BLOCKED_SENTINEL:
        _blk_cfg2 = await get_bot_config(tenant_id)
        _blk_footer2 = _build_footer_contact(_blk_cfg2, [])
        _blocked_msg = f"I'm sorry, I don't have information on that topic. For assistance, please contact us directly:\n{_blk_footer2}"
        await session_manager.add_message(session_id, "user", sanitized_message)
        await session_manager.add_message(session_id, "assistant", _blocked_msg)
        import json as _json
        _t.flush(extra="path=blocked_keyword")
        async def _blocked_stream():
            yield f"data: {_json.dumps({'chunk': _blocked_msg})}\n\n"
            yield f"data: {_json.dumps({'done': True, 'session_id': session_id, 'step': 'idle'})}\n\n"
        return _sse(_blocked_stream())

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
            return _sse(_virus_blocked())

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
            session_id, sanitized_message, tenant_id,
            has_image=bool(request.image_base64),
            image_doc_data=image_doc_data,
            user_id=user_id,
            scraped_summary=scraped_summary,
            knowledge_base=knowledge_base,
            preloaded_flow=current_flow,
        )
    else:
        flow_response, needs_llm, current_step = None, True, "idle"
    _t.mark("process_flow")

    # ── Non-LLM flow response ─────────────────────────────────────────
    # For non-English: flow hardcoded strings are English — route through LLM to translate
    if _FLOW_ENABLED and flow_response is not None and not needs_llm and request.language and request.language != "en":
        needs_llm = True

    if _FLOW_ENABLED and flow_response is not None and not needs_llm:
        full_text = flow_response
        asyncio.create_task(session_manager.add_message(session_id, "user", request.message, {}))
        asyncio.create_task(session_manager.add_message(session_id, "assistant", full_text, {}))
        pdf_url = None
        if current_step == "submitted":
            _tid_match = re.search(r"`([A-Z]+-\d{8}-[A-Z0-9]+)`", full_text)
            if _tid_match:
                pdf_url = f"/api/consular/download-pdf/{_tid_match.group(1)}"
        _t.flush(extra=f"path=flow_only step={current_step}")
        return _sse(
            _stream_deterministic(full_text, session_id, current_step, pdf_url=pdf_url)
        )

    # ── Build LLM context ─────────────────────────────────────────────
    llm_context = context_info or ""
    if _FLOW_ENABLED and current_step == "info_shown" and flow_response:
        llm_context = (llm_context + "\n\n---\n\n" + flow_response) if llm_context else flow_response

    detected_svc_key = detect_service(sanitized_message) if _FLOW_ENABLED else None
    detected_svc_obj = await get_service(tenant_id, detected_svc_key) if detected_svc_key else None
    svc_docs_hint = ""
    if detected_svc_obj:
        docs = "\n".join(f"  • {d}" for d in detected_svc_obj.documents)
        svc_docs_hint = f"\nDOCUMENTS REQUIRED FOR {detected_svc_obj.name.upper()}:\n{docs}\n"

    # When a known-good English answer exists (flow or deterministic), pass it as
    # translation context so the LLM translates it rather than searching from scratch.
    _stream_flow_translate_hint = ""
    if request.language and request.language != "en":
        _stream_translate_source = flow_response if flow_response is not None else deterministic
        if _stream_translate_source:
            _stream_flow_translate_hint = (
                f"\nINTENDED RESPONSE (translate this exactly into the user's selected language, "
                f"keeping all proper nouns, addresses, phone numbers, email addresses, URLs, "
                f"and IDs unchanged):\n{_stream_translate_source}\n"
            )

    _s_blocked_kws = await _get_blocked_keywords()
    _s_clean_ctx = filter_blocked_lines(llm_context, _s_blocked_kws)
    _s_clean_hint = filter_blocked_lines(svc_docs_hint, _s_blocked_kws)
    _s_prohibition = blocked_prohibition(_s_blocked_kws)

    # Per-tenant bot config + service names (both cached; negligible extra latency)
    _bot_cfg_stream = await get_bot_config(tenant_id)
    _tenant_svc_rows = await db.tenant_services.find(
        {"company_id": tenant_id, "enabled": True}, {"_id": 0, "name": 1}
    ).sort("display_order", 1).to_list(50)
    _tenant_svc_names = [r["name"] for r in _tenant_svc_rows if r.get("name")]

    _s_facts  = _build_contact_facts(_bot_cfg_stream, _s_blocked_kws)
    _s_footer = _build_footer_contact(_bot_cfg_stream, _s_blocked_kws)
    _s_scope  = _build_scope_rules(
        _bot_cfg_stream.fallback("out_of_scope"),
        _tenant_svc_names,
    )

    _is_walkthrough = bool(re.search(
        r"step\s+by\s+step|walk\s+me\s+through|entire\s+process|from\s+start\s+to\s+(finish|end)|"
        r"full\s+process|complete\s+process|beginning\s+to\s+end|guide\s+me|first\s+explain.*then|"
        r"explain.*then\s+tell|first.*then\s+guide|walk\s+through",
        sanitized_message, re.IGNORECASE
    ))

    # ── Prompt structure: STATIC zone (cacheable) → DYNAMIC zone (per-request).
    # OpenAI's automatic prefix cache hits only when the leading bytes are identical
    # across requests, so anything that varies per query goes at the bottom.
    # NOTE: bot_name/org_name change the cache-key prefix per-tenant, which is
    # expected — each tenant has its own prefix cache.
    _org_label = _bot_cfg_stream.org_name or _bot_cfg_stream.bot_name
    static_prefix = f"""You are {_bot_cfg_stream.bot_name}, the official assistant for {_org_label}.
{_lang_instruction(request.language or "en")}

{_s_scope}

RESPONSE STYLE:
- Be concise. Default to 3–5 short sentences. Use bullet points for lists, numbered steps for processes.
- When the answer comes from a source, quote only the key facts and include a markdown link to the source page if available. Prefer the URL given in any "(Source: …)" tag in the additional knowledge below.
- Expand into a fuller answer only when the user asks for detail, a step-by-step walkthrough, or a multi-part explanation.
- Do NOT echo the user's question back.
- Do NOT add feedback/rating prompts or sign-off phrases.
- Do NOT ask clarifying questions like "What information do you need?" — answer directly.
- Do NOT repeat information already shown in the conversation.
- When an INTENDED RESPONSE is provided in the dynamic context below, translate it completely and faithfully — do not summarise, shorten, or omit any field.
{f'''
OFFICIAL DATA — always use the facts below to answer questions. This is the authoritative source.

ORGANISATION FACTS:
{_s_facts}
''' if _s_facts else ''}
(Per-request context, prohibition rules, service-specific details, and additional knowledge follow below.)"""

    dynamic_suffix_parts: list[str] = [""]
    if _s_prohibition:
        dynamic_suffix_parts.append(_s_prohibition)
    if _is_walkthrough:
        dynamic_suffix_parts.append(
            "OVERRIDE: This is a step-by-step walkthrough or multi-part question. "
            "Provide a COMPLETE, DETAILED response covering ALL parts in order. "
            "Use numbered steps. Do not skip any step. Be thorough."
        )
    if _s_clean_hint:
        dynamic_suffix_parts.append(_s_clean_hint)
    dynamic_suffix_parts.append(
        "ADDITIONAL KNOWLEDGE (from uploaded documents, knowledge base, and web sources):\n"
        f"{_s_clean_ctx}"
    )
    dynamic_suffix_parts.append(
        "IF the answer is not in any of the data above, say so briefly and direct the user to:\n"
        f"{_s_footer}{_stream_flow_translate_hint}"
    )
    system_msg = static_prefix + "\n\n" + "\n\n".join(p for p in dynamic_suffix_parts if p)

    # Walkthroughs need more output room; brevity-tuned answers stay well under 300.
    _max_tokens = 800 if _is_walkthrough else 300

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    chat_instance = (
        LlmChat(
            api_key=api_key, session_id=session_id, system_message=system_msg,
            max_tokens=_max_tokens,
        )
        .with_model("openai", llm_model)
    )

    user_msg_content = [
        ImageContent(image_base64=_b64, media_type=_mime)
        for _b64, _mime in _validated_pages
    ]
    user_message = UserMessage(
        text=sanitized_message,
        file_contents=user_msg_content if user_msg_content else None
    )

    _t.mark("pre_llm")

    # ── Stream generator ──────────────────────────────────────────────
    async def _llm_stream() -> AsyncGenerator:
        full_text = ""
        try:
            if hasattr(chat_instance, "send_message_stream"):
                async for chunk in chat_instance.send_message_stream(user_message):
                    if not full_text:
                        _t.mark_ttft()
                    full_text += chunk
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            else:
                # Fallback for older LlmChat without streaming support
                full_text = await chat_instance.send_message(user_message)
                _t.mark_ttft()
                yield f"data: {json.dumps({'chunk': full_text})}\n\n"
        except Exception as e:
            logger.error(f"[STREAM] LLM error: {sanitize_logs(str(e))}")
            _t.flush(extra="path=llm_error")
            yield f"data: {json.dumps({'error': 'AI service error, please try again.'})}\n\n"
            return

        if _FLOW_ENABLED:
            flow_service = detect_service(sanitized_message)
            suffix = await flow_suffix(current_step, flow_service, tenant_id)
            if suffix:
                full_text += suffix
                yield f"data: {json.dumps({'chunk': suffix})}\n\n"

        _done = {'done': True, 'session_id': session_id, 'step': current_step}
        try:
            _fs = await get_flow_state(session_id)
            _done['ui_hints'] = ui_hints_for_state((_fs or {}).get('state'))
        except Exception:
            pass
        yield f"data: {json.dumps(_done)}\n\n"
        _t.flush(extra=f"path=llm step={current_step} model={llm_model} out_len={len(full_text)}")

        # Fire-and-forget persistence + usage tracking
        asyncio.create_task(record_llm_usage(
            session_id=session_id, input_text=sanitized_message,
            output_text=full_text, model=llm_model
        ))
        from services import llm_usage as _llm_usage
        asyncio.create_task(_llm_usage.log(tenant_id, chat_instance.last_usage))
        asyncio.create_task(session_manager.add_message(session_id, "user", request.message, {}))
        asyncio.create_task(session_manager.add_message(session_id, "assistant", full_text, {}))

    return _sse(_llm_stream())


@router.post("/document-scan")
async def document_scan(
    request: DocumentScanRequest,
    tenant_id: str = Depends(get_tenant_id),
):
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

    _cfg = await get_bot_config(tenant_id)
    chat_instance = LlmChat(
        api_key=api_key,
        session_id=str(uuid.uuid4()),
        system_message=f"""You are a document processing AI for {_cfg.bot_name}.

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
        _doc_sec = _cfg.security()
        pages = _validate_and_normalize_upload(
            request.image_base64,
            max_bytes=_doc_sec["upload_max_bytes"],
            max_pdf_pages=_doc_sec["upload_max_pdf_pages"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    user_message = UserMessage(
        text=f"Extract all information from this {request.document_type}. Translate to English if needed.",
        file_contents=[ImageContent(image_base64=b64, media_type=mime) for b64, mime in pages]
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
            {"id": request.session_id, "company_id": tenant_id},
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
async def generate_pdf(
    session_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """
    TC 4.1 — Generate an editable AcroForm PDF preview of the applicant's form.

    Called by the frontend when the user is in docs_pending state.
    Returns the PDF as a binary file download.
    """
    db = await get_database()

    # Load session and flow (tenant-scoped)
    session = await db.chat_sessions.find_one(
        {"id": session_id, "company_id": tenant_id},
        {"_id": 0},
    )
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    flow = session.get("flow", {})
    service_key  = flow.get("service")
    form_data    = flow.get("data", {})
    tracking_id  = flow.get("tracking_id", "UNKNOWN")
    uploaded_docs = flow.get("uploaded_docs", [])

    svc_obj = await get_service(tenant_id, service_key) if service_key else None
    if not svc_obj:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No active application found for this session.",
        )

    service_name = svc_obj.name
    _cfg = await get_bot_config(tenant_id)

    try:
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None,
            lambda: generate_application_pdf(
                service_name=service_name,
                form_data=form_data,
                tracking_id=tracking_id,
                uploaded_docs=uploaded_docs,
                org_name=_cfg.org_name or _cfg.bot_name,
                branding=dict(_cfg.pdf_branding or {}),
                field_labels={
                    f["key"]: f["display_label"]
                    for f in (getattr(svc_obj, "fields", []) or [])
                    if isinstance(f, dict) and f.get("key") and f.get("display_label")
                },
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
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/download-pdf/{tracking_id}")
async def download_pdf_by_tracking(
    tracking_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Generate and download the submitted application PDF using tracking ID.
    Called automatically after submission (session flow may already be cleared).
    Tenant-scoped — a tracking ID issued by tenant A cannot be redeemed by
    a download request on tenant B.
    """
    db = await get_database()

    app = await db.applications.find_one(
        {"tracking_id": tracking_id.upper(), "company_id": tenant_id},
        {"_id": 0},
    )
    if not app:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")

    service_key   = app.get("service")
    form_data     = app.get("form_data", {})
    uploaded_docs = [
        {"name": d.get("name", "Document"), "status": d.get("status", "uploaded")}
        for d in app.get("documents", [])
    ]

    svc_obj = await get_service(tenant_id, service_key) if service_key else None
    if not svc_obj:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Service information not available for this application.",
        )

    service_name = svc_obj.name
    _cfg = await get_bot_config(tenant_id)

    try:
        loop = asyncio.get_event_loop()
        pdf_bytes = await loop.run_in_executor(
            None,
            lambda: generate_application_pdf(
                service_name=service_name,
                form_data=form_data,
                tracking_id=tracking_id.upper(),
                uploaded_docs=uploaded_docs,
                org_name=_cfg.org_name or _cfg.bot_name,
                branding=dict(_cfg.pdf_branding or {}),
                field_labels={
                    f["key"]: f["display_label"]
                    for f in (getattr(svc_obj, "fields", []) or [])
                    if isinstance(f, dict) and f.get("key") and f.get("display_label")
                },
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
async def form_submit(form: FormData, tenant_id: str = Depends(get_tenant_id)):
    db = await get_database()

    await db.chat_sessions.update_one(
        {"id": form.session_id, "company_id": tenant_id},
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
async def get_session(session_id: str, tenant_id: str = Depends(get_tenant_id)):
    db = await get_database()
    session = await db.chat_sessions.find_one(
        {"id": session_id, "company_id": tenant_id}, {"_id": 0}
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    return session

@router.post("/session/{session_id}/close")
async def close_session(
    session_id: str,
    reason: str = "language_changed",
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Mark a session as closed in the DB and persist its final state.
    Called by the frontend when the user changes language so the old
    conversation is cleanly archived before a fresh session begins.
    """
    db = await get_database()
    result = await db.chat_sessions.update_one(
        {"id": session_id, "company_id": tenant_id},
        {"$set": {
            "is_active": False,
            "closed_at": datetime.now(timezone.utc).isoformat(),
            "close_reason": reason,
            "status": "closed",
        }}
    )
    if result.matched_count == 0:
        # Session not found — not an error, frontend may call with a stale id
        return {"closed": False, "reason": "session_not_found"}
    return {"closed": True, "session_id": session_id}


class TTSRequest(BaseModel):
    text: str
    language: Optional[str] = "en"

@router.post("/tts")
async def text_to_speech(request: TTSRequest, tenant_id: str = Depends(get_tenant_id)):
    """Convert bot response text to speech using OpenAI TTS (supports all languages)."""
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")
    # Truncate to avoid very large TTS calls
    text = request.text.strip()[:3000]
    audio_base64 = await voice_service.text_to_speech(text, request.language or "en", company_id=tenant_id)
    if not audio_base64:
        raise HTTPException(status_code=500, detail="TTS generation failed")
    return {"audio_base64": audio_base64}


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
    language: Optional[str] = "en"
    image_base64: Optional[str] = None
    # See ChatRequest.visitor_id — same field, same purpose.
    visitor_id: Optional[str] = None

class WidgetChatResponse(BaseModel):
    session_id: str
    response: str

@router.post("/chat-widget", response_model=WidgetChatResponse)
async def chat_widget(
    request: WidgetChatRequest,
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Widget-specific chat endpoint with concise, focused responses.
    Designed for embedded chat widgets on external websites.
    With: Input sanitization, PII protection, session isolation
    """
    # Sanitize and validate user input
    sanitization_result = sanitize_user_input(request.message, context="widget")

    if not sanitization_result.is_safe:
        logger.warning(f"[SECURITY] Blocked unsafe widget input: {sanitization_result.detected_patterns}")
        _cfg = await get_bot_config(tenant_id)
        return WidgetChatResponse(
            session_id=request.session_id or str(uuid.uuid4()),
            response=_cfg.fallback("blocked_input") or "I cannot process that request."
        )

    sanitized_message = request.message

    # Use secure session management for widgets — thread tenant into
    # metadata so downstream queries can scope by it. ``visitor_id`` is
    # the stable per-browser token sent by ChatWidget; falling back to
    # the literal "widget_guest" bucketed every anonymous visitor into
    # one session per tenant. Two real users in different browsers
    # collide there.
    _widget_user_identifier = (
        f"visitor:{request.visitor_id.strip()}"
        if getattr(request, "visitor_id", None) and request.visitor_id.strip()
        else "widget_guest"
    )
    session = await session_manager.get_or_create_session(
        channel="widget",
        user_identifier=_widget_user_identifier,
        session_id=request.session_id,
        metadata={"mode": request.mode, "source": "widget", "company_id": tenant_id}
    )
    session_id = session['id']

    # ── Application flow + workflow hooks ────────────────────────────────
    # Parity with /chat: run process_flow first so the widget channel gets
    # the same consent / form-collection / submit state machine — and the
    # same pre_consent / pre_submit / post_submit hook points operators
    # configure on tenant_services. Pure Q&A messages (no apply intent,
    # state already idle) come back from process_flow with
    # ``needs_llm=True`` and ``flow_response=None`` so we fall through to
    # the LLM path below. Gated on APPLICATION_FLOW_ENABLED so deployments
    # that want a pure-LLM widget can keep the legacy behaviour.
    if _FLOW_ENABLED:
        await preload_flow_keywords(tenant_id)
        await preload_service_patterns(tenant_id)
        _w_current_flow = await get_flow_state(session_id)
        _w_flow_response, _w_needs_llm, _w_step = await process_flow(
            session_id, sanitized_message, tenant_id,
            has_image=bool(request.image_base64),
            user_id="widget_guest",
            preloaded_flow=_w_current_flow,
            channel="widget",
        )
        if _w_flow_response is not None and not _w_needs_llm:
            # Flow has a deterministic answer (consent prompt, hook
            # advisory, field question, submit confirmation, etc.) —
            # short-circuit the LLM. Still log to the session so the
            # transcript stays complete.
            await session_manager.add_message(session_id, "user", request.message)
            await session_manager.add_message(session_id, "assistant", _w_flow_response)
            return WidgetChatResponse(
                session_id=session_id,
                response=_w_flow_response,
            )

    # Widget system prompt — sourced entirely from the tenant's bot_config,
    # wrapped with the generic anti-injection guards. The previous version
    # referenced an undefined ``SCOPE_RULES`` constant (NameError on every
    # widget hit post-Phase 2) and embedded verbatim OCI / passportindia.gov.in
    # / "Mon-Fri 9:00 AM - 5:30 PM" few-shot examples — both fixed here.
    # The widget concise-response style now comes from the tenant's
    # ``system_prompt_template`` (operators add their own style rules) or
    # the generic platform default.
    _bot_cfg_widget = await get_bot_config(tenant_id)
    _widget_base = _bot_cfg_widget.system_prompt() + (
        "\n\nWIDGET RESPONSE STYLE:\n"
        "- Wait for the user's question — do not volunteer information.\n"
        "- Keep simple answers to 2-4 sentences. Use bullet points only when listing items.\n"
        "- No lengthy introductions or trailing 'Is there anything else?'."
    )
    _base_system_message = create_safe_system_prompt(
        _widget_base,
        bot_name=_bot_cfg_widget.bot_name,
    )

    api_key = os.environ.get('EMERGENT_LLM_KEY')

    # LLM model: env default → tenant company.llm_model override (parity
    # with /chat and /chat_stream).
    _widget_llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    _widget_db = await get_database()
    _co_widget = await _widget_db.companies.find_one(
        {"id": tenant_id}, {"_id": 0, "llm_model": 1}
    )
    if _co_widget and _co_widget.get("llm_model"):
        _widget_llm_model = _co_widget["llm_model"]

    chat_instance = LlmChat(
        api_key=api_key,
        session_id=session_id,
        system_message=_base_system_message
    ).with_model("openai", _widget_llm_model)
    
    if request.image_base64:
        try:
            _w_cfg = await get_bot_config(tenant_id)
            _w_sec = _w_cfg.security()
            pages = _validate_and_normalize_upload(
                request.image_base64,
                max_bytes=_w_sec["upload_max_bytes"],
                max_pdf_pages=_w_sec["upload_max_pdf_pages"],
            )
            user_message = UserMessage(
                text=sanitized_message or "Please describe what you see in this document/image and help me with it.",
                file_contents=[ImageContent(image_base64=b64, media_type=mime) for b64, mime in pages]
            )
        except Exception:
            user_message = UserMessage(text=sanitized_message or "Document uploaded.")
    else:
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
async def get_application_status(
    tracking_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """Check the status of an application by tracking ID.
    Tenant-scoped — a tracking ID is visible only to its owning tenant."""
    db = await get_database()
    app = await db.applications.find_one(
        {"tracking_id": tracking_id.upper(), "company_id": tenant_id}, {"_id": 0}
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
async def get_session_applications(
    session_id: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """List all applications linked to a session (tenant-scoped)."""
    db = await get_database()
    cursor = db.applications.find(
        {"session_id": session_id, "company_id": tenant_id}, {"_id": 0}
    )
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
async def lookup_applications_by_contact(
    contact: str,
    tenant_id: str = Depends(get_tenant_id),
):
    """
    Find applications by email or phone number. Tenant-scoped — without
    this, an email/phone lookup would surface applications across all
    tenants, leaking cross-tenant PII.

    GET /api/consular/applications/lookup?contact=user@example.com
    GET /api/consular/applications/lookup?contact=+27811234567
    """
    import re as _re
    db = await get_database()
    contact = contact.strip()
    is_email = bool(_re.match(r'.+@.+\..+', contact))
    field = "form_data.email" if is_email else "form_data.phone"
    cursor = db.applications.find(
        {
            "company_id": tenant_id,
            field: {"$regex": _re.escape(contact), "$options": "i"},
        },
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


@router.get("/widget-config")
async def widget_config(tenant_id: str = Depends(get_tenant_id)):
    """Public branding endpoint — the widget calls this on boot to fetch
    everything it needs to render: bot name, avatar, colors, supported
    languages, chat-chrome copy (tagline/footer/greeting/advisories), and
    the tenant's service catalogue.

    No auth required (the widget runs on third-party pages). System prompt,
    contact info, and the raw fallback_responses dict are NOT exposed here;
    only the rendered subset from `cfg.public_branding()` plus a flattened
    services list pulled from `tenant_services`.
    """
    cfg = await get_bot_config(tenant_id)
    payload = cfg.public_branding()

    # Services menu — read enabled rows for this tenant, ordered for display.
    # Each row is reshaped to a stable public schema so renaming a backend
    # field doesn't silently break the widget.
    db = await get_database()
    rows = await db.tenant_services.find(
        {"company_id": tenant_id, "enabled": True},
        {"_id": 0},
    ).sort("display_order", 1).to_list(200)
    payload["services"] = [
        {
            "key":          r.get("service_key"),
            "name":         r.get("name"),
            "emoji":        r.get("emoji") or "",
            "description":  r.get("description") or "",
            "category":     r.get("category") or "TYPE_A",
            "external_url": r.get("external_url"),
            "documents":    list(r.get("documents") or []),
            "keywords":     list(r.get("keywords") or []),
            "post_confirm_message": r.get("post_confirm_message") or "",
            # INFO services ship a typed sections payload + optional CTA.
            # Empty for TYPE_A/TYPE_B; the consumer card hides the block
            # when sections is empty, so this is always safe to include.
            "info_content": dict(r.get("info_content") or {}),
        }
        for r in rows
        if r.get("service_key") and r.get("name")
    ]
    # Expose the frontend-facing slice of platform_config so the widget
    # picks up super-admin tuning (HTTP timeouts, TTS chunk size) without
    # a build. Server-only knobs (cache TTLs, OTP secrets) stay private.
    try:
        from services import platform_config
        payload["platform"] = {
            "chat_stream_timeout_ms":   int(platform_config.get("frontend_chat_stream_timeout_ms", 60000)),
            "tts_timeout_ms":           int(platform_config.get("frontend_tts_timeout_ms", 30000)),
            "inactivity_check_ms":      int(platform_config.get("frontend_inactivity_check_ms", 30000)),
            "tts_chunk_size_chars":     int(platform_config.get("frontend_tts_chunk_size_chars", 250)),
        }
    except Exception:
        payload["platform"] = {
            "chat_stream_timeout_ms":   60000,
            "tts_timeout_ms":           30000,
            "inactivity_check_ms":      30000,
            "tts_chunk_size_chars":     250,
        }
    return payload
