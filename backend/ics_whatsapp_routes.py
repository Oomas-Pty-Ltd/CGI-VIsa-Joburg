"""
====================================================================
SEVA SETU BOT - ICS WABA INTEGRATION
====================================================================
WhatsApp bot powered by ICS Production WhatsApp Solution API v3.1.

Webhook endpoints called by ICS:
  GET /api/ics-whatsapp/webhook   - Incoming user messages
  GET /api/ics-whatsapp/delivery  - Delivery status callbacks

Bot flow uses the SAME engine as the web ConsularBot:
  - session_manager  (shared chat_sessions collection)
  - process_flow()   (application_flow.py state machine)
  - hybrid_search()  + get_realtime_knowledge()
  - LLM with full knowledge context

Interactive WhatsApp features:
  - Welcome: interactive LIST  (service menu)
  - Service info: interactive BUTTONS (Apply / Ask a Question / Main Menu)
  - Consent: interactive BUTTONS  (Yes, I have docs / Not yet)
  - Submit confirm: interactive BUTTONS (Submit / Cancel)
  - All flow/LLM responses: plain TEXT (WhatsApp-formatted)
====================================================================
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import unquote_plus

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from database import get_database
from security.input_sanitizer import sanitize_user_input
from security.guardrail import guardrail_service, sanitize_logs
from security.session_manager import session_manager
from services.ics_waba_service import ics_waba
from knowledge_scraper import get_realtime_knowledge, extract_service_content
from services.hybrid_retrieval import hybrid_search
from services.application_flow import (
    SERVICES,
    CONTACT_INFO,
    process_flow,
    flow_suffix,
    get_flow_state,
    detect_service,
    detect_website_service,
    is_apply_intent,
)

# LLM for open-ended Q&A
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

router = APIRouter(prefix="/ics-whatsapp", tags=["ics-whatsapp"])
logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# =====================================================================
# MODELS
# =====================================================================
class SendRequest(BaseModel):
    to: str
    message: str
    type: str = "text"


class SimulateRequest(BaseModel):
    phone: str
    message: str
    waba_number: str = ""
    reply_type: str = "TEXT"


# =====================================================================


# =====================================================================
# MARKDOWN → WHATSAPP TEXT CONVERTER
# =====================================================================
# WhatsApp character limits (interactive messages)
_WA_BODY_LIMIT   = 1024   # interactive button/list body
_WA_MSG_LIMIT    = 4000   # plain text message

# Web-UI phrases that make no sense on WhatsApp → WhatsApp equivalents
_WA_REPLACEMENTS = [
    (r'Use the \*\*?Upload\*\*? button or \*\*?Camera\*\*? button below\.?', 'Send a photo or PDF of the document as an attachment.'),
    (r'Upload\s+button\s+or\s+Camera\s+button', 'attachment'),
    (r'Type\s+\*\*?skip\*\*?',      'Reply *skip*'),
    (r'type\s+\*\*?skip\*\*?',      'reply *skip*'),
    (r'Type\s+\*\*?discard\*\*?',   'Reply *discard*'),
    (r'type\s+\*\*?discard\*\*?',   'reply *discard*'),
    (r'Type\s+\*\*?submit\*\*?',    'Reply *submit*'),
    (r'type\s+\*\*?submit\*\*?',    'reply *submit*'),
    (r'Type\s+\*\*?continue\*\*?',  'Reply *continue*'),
    (r'type\s+\*\*?continue\*\*?',  'reply *continue*'),
    (r'Type\s+\*\*?apply\*\*?',     'Reply *apply*'),
    (r'type\s+\*\*?apply\*\*?',     'reply *apply*'),
    (r'Type\s+\*\*?cancel\*\*?',    'Reply *cancel*'),
    (r'type\s+\*\*?cancel\*\*?',    'reply *cancel*'),
    (r'Type\s+\*\*menu\*\*',        'Reply *menu*'),
]


def _md_to_wa(text: str) -> str:
    """
    Convert a markdown bot response to WhatsApp-compatible text.
    Handles: **bold**, headings, tables, code blocks, lists, blockquotes.
    Also strips web-UI instructions and replaces them with WhatsApp equivalents.
    """
    # ── Fenced code blocks → WhatsApp monospace ──────────────────────
    text = re.sub(r'```[a-zA-Z]*\n?(.*?)```', r'```\1```', text, flags=re.DOTALL)

    # ── Markdown headings → *bold* with blank line after ─────────────
    text = re.sub(r'^#{1,6}\s*(.+)$', r'*\1*', text, flags=re.MULTILINE)

    # ── **bold** → *bold*  (but avoid double-converting *already bold*) ─
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text, flags=re.DOTALL)

    # ── __italic__ / _italic_ → _italic_ ─────────────────────────────
    text = re.sub(r'__(.+?)__', r'_\1_', text)

    # ── Blockquotes > → italic text ───────────────────────────────────
    text = re.sub(r'^>\s*(.+)$', r'_\1_', text, flags=re.MULTILINE)

    # ── Tables → formatted rows ───────────────────────────────────────
    def _table_row(m):
        row = m.group(0)
        # Skip separator lines  |---|---|
        if re.match(r'^\s*\|[\s\-:|]+\|\s*$', row):
            return ''
        cols = [c.strip() for c in row.strip().strip('|').split('|')]
        return '  │  '.join(cols)
    text = re.sub(r'^\|.+\|$', _table_row, text, flags=re.MULTILINE)

    # ── Inline code `x` → keep backticks ─────────────────────────────
    # Already fine for WhatsApp monospace; nothing to change.

    # ── Horizontal rules → blank separator line ───────────────────────
    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)

    # ── Apply WhatsApp-specific phrase replacements ───────────────────
    for pattern, replacement in _WA_REPLACEMENTS:
        text = re.sub(pattern, replacement, text)

    # ── Collapse 3+ blank lines → max 2 ──────────────────────────────
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def _split_wa(text: str, max_len: int = _WA_MSG_LIMIT) -> list:
    """
    Split text into chunks ≤ max_len characters.
    Splits prefer paragraph (double-newline) boundaries, then single-newline,
    then hard-splits at max_len as a last resort.
    """
    if len(text) <= max_len:
        return [text]

    chunks = []
    while len(text) > max_len:
        # Try splitting at last double-newline within limit
        cut = text.rfind('\n\n', 0, max_len)
        if cut == -1:
            cut = text.rfind('\n', 0, max_len)
        if cut == -1:
            cut = max_len
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


async def _wa_send(phone: str, text: str, db, step: str = "", waba_number: str = "") -> Optional[str]:
    """
    Send one or more WhatsApp text messages (splitting if needed).
    Returns the ics_mid of the last message sent.
    Logs errors if sending fails.
    """
    chunks = _split_wa(text)
    last_mid = None
    for i, chunk in enumerate(chunks):
        if not chunk:
            continue
        result = await ics_waba.send_text(phone, chunk, from_override=waba_number)
        
        # Check for errors
        if isinstance(result, dict):
            if result.get("error"):
                logger.error(f"[WHATSAPP_ERROR] Failed to send to {phone} (chunk {i+1}/{len(chunks)}): {result.get('error')}")
                await _log_message(
                    phone, "outbound_error", chunk,
                    {
                        "step": step,
                        "chunk_index": i,
                        "chunk_total": len(chunks),
                        "error": result.get("error"),
                        "error_type": result.get("error_type"),
                    },
                    db
                )
                continue
            
            _mid = result.get("mid")
            if _mid:
                last_mid = str(_mid)
                logger.info(f"[WHATSAPP_SUCCESS] Message to {phone} (chunk {i+1}/{len(chunks)}): mid={_mid}")
            else:
                logger.warning(f"[WHATSAPP_WARNING] No MID in response for {phone}: {result}")
        else:
            logger.error(f"[WHATSAPP_ERROR] Unexpected response type for {phone}: {type(result)}")
        
        await _log_message(
            phone, "outbound", chunk,
            {"step": step, "chunk_index": i, "chunk_total": len(chunks)},
            db, ics_mid=last_mid,
        )
    
    if not last_mid:
        logger.warning(f"[WHATSAPP_WARNING] No messages sent successfully to {phone}")
    
    return last_mid


def _truncate_body(text: str) -> str:
    """
    Truncate text to WhatsApp interactive body limit (1024 chars).
    Appends '…' if truncated.
    """
    if len(text) <= _WA_BODY_LIMIT:
        return text
    return text[:_WA_BODY_LIMIT - 1].rsplit(' ', 1)[0] + '…'


# =====================================================================
# LLM WITH KNOWLEDGE CONTEXT
# =====================================================================
async def _llm_response(user_message: str, session_id: str, context: str = "") -> str:
    if not LLM_AVAILABLE or not EMERGENT_LLM_KEY:
        return (
            "Thank you for your message. For detailed assistance please visit "
            "https://www.cgijoburg.gov.in or call +27 11 581 9800."
        )

    # Build service-specific document hint (same as web bot)
    detected_svc = detect_service(user_message)
    svc_docs_hint = ""
    if detected_svc and detected_svc in SERVICES:
        svc = SERVICES[detected_svc]
        docs = "\n".join(f"  • {d}" for d in svc["documents"])
        svc_docs_hint = f"\nDOCUMENTS REQUIRED FOR {svc['name'].upper()}:\n{docs}\n"

    system_prompt = f"""You are Seva Setu Bot, the official consular assistant for the Consulate General of India, Johannesburg. You are replying via WhatsApp.

CRITICAL — DATA SOURCE RULE:
Answer ONLY using the OFFICIAL DATA provided below.
The data comes from: www.cgijoburg.gov.in, vfsglobal.com, and admin-uploaded documents (FAQs, events, notices).
Do NOT use general training knowledge. Do NOT invent or add information not in the data below.
If the answer is not in the data, say so and direct the user to contact the Consulate directly.

LANGUAGE: Always respond in English only, regardless of what language the user writes in.

RESPONSE STYLE:
- Be concise, accurate, and helpful.
- Do NOT echo the user's question back.
- Do NOT add feedback/rating prompts or sign-off phrases.
- Use bullet points only when listing multiple items.
- Do NOT repeat information already shown in the conversation.
- Use *bold* for emphasis (WhatsApp format). Do NOT use markdown ** double-asterisks.
- Never ask for money or claim the consulate calls asking for payments.

KEY CONSULATE FACTS (always use these for contact/location questions):
- Acting Consul General: Mr. Harish Kumar
- Address: No. 1, Eton Road (Corner Jan Smuts Avenue & Eton Road), Park Town 2193, Johannesburg
- Phone: +27 11-4828484 / +27 11-4828485 / +27 11-4828486 / +27 11 581 9800
- Email: ccom.jburg@mea.gov.in (general) | cons.jburg@mea.gov.in (consular/OCI)
- Website: www.cgijoburg.gov.in
- Office Hours: Mon–Fri 08:30–17:00 (Lunch: 13:00–13:30)
- Jurisdiction: Gauteng, North West, Limpopo and Mpumalanga provinces of South Africa
- Social Media: Twitter/X @indiainjoburg | Facebook: IndiaInSouthAfricaJohannesburg | Instagram: @indiainjohannesburg
- VFS Global (Passport/PCC): 2nd Floor, Harrow Court 1, Isle of Houghton, Park Town, JHB — Tel: 012 425 3007
- VFS Global (Visa): 1st Floor, Rivonia Village Office Block, Rivonia, JHB — Tel: 012 425 3007
- VFS Hours: Submission Mon–Fri 08:00–15:00 | Collection 11:00–16:00
{svc_docs_hint}
OFFICIAL DATA (cgijoburg.gov.in | vfsglobal.com | uploaded documents):
{context}

IF NOT IN OFFICIAL DATA: Say "This information is not available in our current records. Please contact the Consulate directly:"
  📞 +27 11-4828484 / +27 11 581 9800  |  📧 ccom.jburg@mea.gov.in
  🏢 No. 1, Eton Road, Park Town 2193, Johannesburg
  🕐 Mon–Fri 08:30–17:00 (Lunch: 13:00–13:30)"""

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_prompt,
        ).with_model("openai", "gpt-4o")
        return await chat.send_message(UserMessage(text=user_message))
    except Exception as exc:
        logger.error("LLM error: %s", exc)
        return (
            "I'm having trouble right now. Please try again shortly or call "
            "+27 11 581 9800."
        )


# =====================================================================
# AUDIT LOG
# =====================================================================
async def _log_message(phone: str, direction: str, text: str, extra: dict, db, ics_mid: str = None):
    doc = {
        "id":           str(uuid.uuid4()),
        "phone_number": phone,
        "direction":    direction,
        "message":      text,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    if ics_mid:
        doc["ics_mid"] = ics_mid
    await db.ics_whatsapp_messages.insert_one(doc)


# =====================================================================
# HELPER: Get flow state early (for context-aware numbered reply handling)
# =====================================================================
async def _get_flow_safe(phone: str) -> dict:
    """Get the current flow state for a phone number, safely handling errors."""
    try:
        session = await session_manager.get_or_create_session(
            channel="whatsapp",
            user_identifier=phone,
        )
        from services.application_flow import _get_flow
        flow = await _get_flow(session["id"])
        return flow
    except Exception as e:
        logger.debug(f"Could not fetch flow state for {phone}: {e}")
        return {"state": "idle", "service": None}


# =====================================================================
# PHONE NORMALISATION
# =====================================================================
def _normalize_phone(raw: str, waba_number: str = "") -> str:
    """
    Normalise an incoming customernumber to digits-only E.164 (no leading +).

    Safe transforms:
      1. Leading '+'          : +27726413058    → 27726413058
      2. Punctuation/spaces   : +27 72-641 3058 → 27726413058
      3. SA local with 0      : 0726413058      → 27726413058  (ONLY SA uses 0xx 10-digit)
      4. SA local without 0   : 726413058       → 27726413058  (9-digit SA mobile)
      5. Duplicate India CC   : 9191XXXXXXXXXX  → 91XXXXXXXXXX (known ICS India bug)

    ICS SA-mangling fix (requires waba_number context):
      ICS bug: strips leading '2' from SA E.164, prepends '91'
        27726413058 → 917726413058
      Reversal: strip '91', prepend '2'; accept only if result starts with '27'.
      Only applied when waba_number is a South African number (starts with '27').
    """
    # Strip whitespace and leading +
    phone = raw.strip().lstrip("+")
    # Remove formatting characters
    phone = re.sub(r"[\s\-\(\)\.]+", "", phone)

    # ICS SA-mangling fix: 91XXXXXXXXXX → 27XXXXXXXXX
    # ICS strips the leading '2' from SA numbers (27...) and prepends '91',
    # producing a 12-digit number like 917726413058 instead of 27726413058.
    # Only correct this when the WABA itself is South African (starts with '27'),
    # to avoid mis-converting genuine Indian customer numbers.
    waba = re.sub(r"[\s\-\(\)\.]+", "", waba_number.strip().lstrip("+"))
    if (
        waba.startswith("27")
        and re.match(r"^91\d{10}$", phone)
    ):
        candidate = "2" + phone[2:]   # strip "91", prepend "2"
        if candidate.startswith("27"):
            logger.info(
                "[PHONE NORM] ICS SA-mangle corrected: %s → %s",
                phone, candidate,
            )
            phone = candidate
            return phone

    # SA local with leading 0: 0XXXXXXXXX (10 digits) → 27XXXXXXXXX
    if re.match(r"^0[6-8]\d{8}$", phone):
        phone = "27" + phone[1:]
    # SA local without 0: 9-digit number starting with SA mobile prefix (6x/7x/8x)
    elif re.match(r"^[6-8]\d{8}$", phone):
        phone = "27" + phone
    # Fix duplicate India country code: 9191<10 digits> → 91<10 digits>
    elif re.match(r"^9191\d{10}$", phone):
        phone = phone[2:]
    return phone


# =====================================================================
# BOT LOGIC — process one incoming message and send reply
# Uses the same process_flow() engine as the web ConsularBot.
# =====================================================================
async def _handle_message(
    phone: str,
    waba_number: str,
    reply_type: str,
    raw_reply: str,
    db,
):
    """Core bot handler — delegates to the shared process_flow() state machine."""

    # ── Parse interactive input ───────────────────────────────────────
    selected_id    = None
    selected_title = None
    media_id       = None

    if reply_type == "INTERACTIVE":
        try:
            data = json.loads(raw_reply)
            if data.get("type") == "list_reply":
                selected_id    = data["list_reply"]["id"]
                selected_title = data["list_reply"]["title"]
            elif data.get("type") == "button_reply":
                selected_id    = data["button_reply"]["id"]
                selected_title = data["button_reply"]["title"]
        except (json.JSONDecodeError, KeyError):
            pass
        user_text = selected_title or raw_reply
    elif reply_type in ("IMAGE", "VIDEO", "DOCUMENT"):
        try:
            media_info = json.loads(raw_reply)
            media_id   = media_info.get("id")
        except (json.JSONDecodeError, KeyError):
            media_id = None
        user_text = "document"
    else:
        user_text = raw_reply

    # ── Sanitize ──────────────────────────────────────────────────────
    san = sanitize_user_input(user_text, context="whatsapp")
    if not san.is_safe:
        await ics_waba.send_text(phone, "I cannot process that request. Please ask about consular services.")
        return

    await _log_message(phone, "inbound", user_text, {"reply_type": reply_type, "media_id": media_id}, db)

    # ── Get current flow state for context-aware numbered reply handling ────
    _current_flow = await _get_flow_safe(phone)

    # When collecting form data (names, dates, passport numbers, etc.), skip PII
    # redaction — the guardrail aggressively mangles valid form values (e.g. dates
    # like 01/01/1990 → 01/01/[PHONE_REDACTED]).  In all other states apply the
    # normal guardrail pass so LLM responses are not poisoned by PII.
    _form_states = {"collecting", "docs_uploading", "docs_pending", "consent_pending"}
    if _current_flow.get("state") in _form_states:
        clean_text = user_text
    else:
        clean_text = guardrail_service.validate_input(user_text).sanitized_text
    
    # ── Numbered reply fallback (when interactive messages unsupported) ─
    # Context-aware: interpretation depends on current flow state
    _service_keys = list(SERVICES.keys())
    if not selected_id and clean_text.strip().isdigit():
        user_choice = int(clean_text.strip())
        
        # If in info_shown state with a service: map to secondary menu (Apply/Question/Menu)
        if _current_flow.get("state") == "info_shown" and _current_flow.get("service"):
            if user_choice == 1:  # "Apply Now"
                selected_id = f"apply_{_current_flow.get('service')}"
            elif user_choice == 2:  # "Ask a Question"
                selected_id = "ask_question"
            elif user_choice == 3:  # "Main Menu"
                selected_id = "main_menu"
        # If in consent_pending state: map to yes/no
        elif _current_flow.get("state") == "consent_pending":
            if user_choice == 1:  # Yes
                selected_id = "consent_yes"
            elif user_choice == 2:  # No
                selected_id = "consent_no"
        # Default: map to service menu (idle or first-time users)
        else:
            n = user_choice - 1
            if 0 <= n < len(_service_keys):
                selected_id = _service_keys[n]

    # ── Map button/list IDs to text understood by process_flow() ─────
    # This bridges WhatsApp interactive buttons to the shared state machine.
    if selected_id:
        if selected_id == "main_menu":
            clean_text = "menu"
        elif selected_id == "consent_yes":
            clean_text = "yes"
        elif selected_id == "consent_no":
            clean_text = "no"
        elif selected_id == "btn_submit":
            clean_text = "submit"
        elif selected_id == "btn_cancel":
            clean_text = "discard"
        elif selected_id == "ask_question":
            await ics_waba.send_text(
                phone,
                "Sure! Please type your question and I'll do my best to answer it. 🙏",
                from_override=waba_number,
            )
            await _log_message(phone, "outbound", "Sure! Please type your question and I'll do my best to answer it. 🙏", {"step": "qa"}, db)
            return
        elif selected_id.startswith("apply_"):
            # Extract the service key directly — more reliable than text matching
            _svc_key = selected_id[len("apply_"):]
            clean_text = f"apply {_svc_key}"
            # Pre-set the service in the flow so process_flow() picks it up even from idle state
            _pre_session = await session_manager.get_or_create_session(
                channel="whatsapp", user_identifier=phone, metadata={"waba_number": waba_number}
            )
            from services.application_flow import _get_flow, _save_flow
            _pre_flow = await _get_flow(_pre_session["id"])
            if _svc_key in SERVICES:
                _pre_flow["state"]   = "info_shown"
                _pre_flow["service"] = _svc_key
                await _save_flow(_pre_session["id"], _pre_flow)
        elif selected_id in SERVICES:
            clean_text = f"apply {selected_id}"

    # ── Get or create session (shared with web bot via session_manager) ─
    session = await session_manager.get_or_create_session(
        channel="whatsapp",
        user_identifier=phone,
        metadata={"waba_number": waba_number},
    )
    session_id = session["id"]

    # ── SHOW MAIN MENU ────────────────────────────────────────────────
    # Only shown for explicit greeting/menu words — NOT for any question or query.
    # Everything else (questions, apply intents, service names) goes to the bot engine.
    current_flow = await get_flow_state(session_id)

    _MENU_WORDS = {"menu", "hi", "hello", "start", "help", "/start", "hey", "namaste", "hola"}
    is_menu_trigger = clean_text.lower().strip() in _MENU_WORDS

    if is_menu_trigger and not selected_id:
        # Send greeting + advisory as plain text first
        greeting_text = (
            "🙏 नमस्ते भाइयो और बहनो!\n\n"
            "मैं हूं \"सेवा सेतु स्वचालित सहायक (बॉट)\", आपकी सेवा में सदैव तत्पर।\n\n"
            "🗣️ भारतीय काउंसलर सर्विसेज के साथ हाजिर हूं। बताएं, मैं आपकी किस प्रकार सहायता कर सकता हूं? "
            "आज मैं आपकी मदद करने में सक्षम हूं।\n\n"
            "Namaste, brothers and sisters!\n\n"
            "I am \"Seva Setu Automated Assistant (Bot)\", always ready to serve you.\n\n"
            "🗣️ Here to assist with your Indian consular service queries. "
            "Please let me know how I can help you today. I am fully equipped to assist you.\n\n"
            "⚠️ *Important Advisory from the Consulate General of India, Johannesburg*"
        )
        await ics_waba.send_text(phone, greeting_text, from_override=waba_number)
        return

    # ── SERVICE SELECTED FROM LIST — show info card + apply buttons ───
    if selected_id in SERVICES:
        svc = SERVICES[selected_id]
        docs_text = "\n".join(f"  • {d}" for d in svc["documents"])
        info_text = _md_to_wa(
            f"*{svc['name']}*\n\n"
            f"{svc['description']}\n\n"
            f"*Required documents:*\n{docs_text}"
        )
        # Save info_shown + service to the shared flow so "Apply Now" works correctly
        from services.application_flow import _get_flow, _save_flow
        _flow = await _get_flow(session_id)
        _flow["state"]   = "info_shown"
        _flow["service"] = selected_id
        await _save_flow(session_id, _flow)

        await ics_waba.send_text(phone, info_text, from_override=waba_number)
        return

    # ── "Apply" intent handling — context-aware routing ─
    # If user has a service in progress (info_shown or any state with service set),
    # transform apply intent to be service-specific. This handles text responses
    # to the "Apply Now" buttons when they're displayed as numbered options.
    if (
        is_apply_intent(clean_text)
        and not detect_service(clean_text)
    ):
        # Case 1: User has a service context in their flow — apply for it
        if current_flow.get("service"):
            service_key = current_flow.get("service")
            clean_text = f"apply {service_key}"
            # Don't modify state — let process_flow handle the transition.
        # Case 2: No service context — let LLM handle
        elif current_flow.get("state") == "idle":
            pass  # fall through to bot engine

    # ── LOAD KNOWLEDGE BASE FOR CONTEXT (mirrors web bot exactly) ───────
    context_info    = ""
    scraped_summary = ""
    knowledge_base  = {}
    try:
        knowledge_base = await get_realtime_knowledge()

        # hybrid_search always runs — same as web bot (context_info goes to LLM)
        context_info = await hybrid_search(clean_text, knowledge_base)

        # scraped_summary is service-specific — goes to process_flow
        active_service = detect_service(clean_text) or current_flow.get("service")
        if active_service:
            scraped_summary = extract_service_content(active_service, knowledge_base, user_query=clean_text)
        elif detect_website_service(clean_text):
            # Website-only service — keyword search from scraped pages
            words = [w for w in clean_text.lower().split() if len(w) > 3]
            cgi_text = knowledge_base.get("cgi_joburg", {}).get("page_content", "")
            vfs_text = knowledge_base.get("vfs_global", {}).get("page_content", "")
            relevant = [
                line.strip() for line in (cgi_text + "\n" + vfs_text).split("\n")
                if line.strip() and any(w in line.lower() for w in words)
            ]
            scraped_summary = "\n".join(relevant[:15])
    except Exception as exc:
        logger.warning("Knowledge base fetch failed: %s", exc)

    # ── TC 3.1 — Virus scan for media attachments ────────────────────
    has_doc = reply_type in ("IMAGE", "DOCUMENT") and bool(media_id)
    if has_doc:
        # Attempt to download media bytes for scanning.
        # ICS WABA delivers media via media_id; download if possible.
        _media_bytes: bytes | None = None
        try:
            import httpx as _httpx
            _dl_url = f"https://media.sendmsg.in/download/{media_id}"
            _dl_headers = {}
            _ics_user = os.environ.get("ICS_WABA_USER", "")
            _ics_pass = os.environ.get("ICS_WABA_PASS", "")
            if _ics_user and _ics_pass:
                import base64 as _b64
                _cred = _b64.b64encode(f"{_ics_user}:{_ics_pass}".encode()).decode()
                _dl_headers["Authorization"] = f"Basic {_cred}"
            async with _httpx.AsyncClient(timeout=8.0) as _client:
                _resp = await _client.get(_dl_url, headers=_dl_headers)
                if _resp.status_code == 200:
                    _media_bytes = _resp.content
        except Exception as _exc:
            logger.warning("[VIRUS_SCAN] Could not download media %s for scan: %s", media_id, _exc)

        if _media_bytes:
            from virus_scanner import scan_bytes as _virus_scan
            _scan = await _virus_scan(_media_bytes, f"wa_{reply_type.lower()}_{media_id}")
            if not _scan["clean"]:
                threat = _scan.get("threat", "unknown threat")
                logger.warning(
                    "[SECURITY] Virus scan blocked WhatsApp media from %s: %s", phone, threat
                )
                await ics_waba.send_text(
                    phone,
                    f"🚫 *Security Alert:* The file you sent was flagged as a threat "
                    f"({threat}) and cannot be processed. Please send a different document.",
                    from_override=waba_number,
                )
                await _log_message(
                    phone, "outbound",
                    "Security alert: virus detected in uploaded media.",
                    {"step": "virus_blocked", "threat": threat},
                    db,
                )
                return

    image_doc_data = {"filename": "whatsapp_doc", "file_id": media_id, "status": "uploaded"} if has_doc else None

    flow_response, needs_llm, step = await process_flow(
        session_id=session_id,
        message=clean_text,
        has_image=has_doc,
        image_doc_data=image_doc_data,
        user_id=phone,
        scraped_summary=scraped_summary,   # service-specific → process_flow
        knowledge_base=knowledge_base,
        preloaded_flow=current_flow,
        channel="whatsapp",
    )

    # ── Build final response text ─────────────────────────────────────
    if flow_response is not None and not needs_llm:
        bot_text = _md_to_wa(flow_response)
    else:
        # LLM path — knowledge scraper (context_info) is PRIMARY source.
        # For service info requests (step="info_shown"), also include the
        # structured service page as additional context so the LLM has both
        # live knowledge AND the structured docs/fees info.
        llm_context = context_info or ""
        if step == "info_shown" and flow_response:
            if llm_context:
                llm_context = llm_context + "\n\n---\n\n" + flow_response
            else:
                llm_context = flow_response
        raw_llm = await _llm_response(clean_text, session_id, llm_context)
        # Append flow guidance suffix (same as web bot)
        suffix = flow_suffix(step, detect_service(clean_text), channel="whatsapp")
        if suffix:
            raw_llm += suffix
        bot_text = _md_to_wa(raw_llm)

    # ── Save to session history ───────────────────────────────────────
    await session_manager.add_message(session_id, "user", user_text)
    await session_manager.add_message(session_id, "assistant", bot_text)

    # ── Send — per-step WhatsApp formatting ───────────────────────────
    #
    # Rules:
    #   • Long content is always sent as plain text FIRST (via _wa_send),
    #     then a short interactive button message follows.
    #   • Interactive body is capped at 1024 chars (_truncate_body).
    #   • Web-UI phrases are already stripped by _md_to_wa().
    #
    wa = waba_number   # shorthand for from_override

    if step == "consent_pending":
        await _wa_send(phone, bot_text, db, step, wa)
        await ics_waba.send_buttons(
            to=phone,
            body="Do you have *all* the required documents ready?",
            buttons=[
                {"id": "consent_yes", "title": "Yes, I have them"},
                {"id": "consent_no",  "title": "No, not yet"},
            ],
            header="Documents Checklist",
            footer="You can send photos/PDFs in the next steps.",
            from_override=wa,
        )

    elif step == "docs_pending":
        await _wa_send(phone, bot_text, db, step, wa)
        await ics_waba.send_buttons(
            to=phone,
            body="All information collected. Ready to submit?",
            buttons=[
                {"id": "btn_submit", "title": "Submit Application"},
                {"id": "btn_cancel", "title": "Cancel"},
            ],
            header="Review & Submit",
            footer="A tracking ID will be sent on submission.",
            from_override=wa,
        )

    elif step == "paused":
        await _wa_send(phone, bot_text, db, step, wa)
        await ics_waba.send_buttons(
            to=phone,
            body="What would you like to do?",
            buttons=[
                {"id": "consent_yes", "title": "Continue Application"},
                {"id": "btn_cancel",  "title": "Cancel Application"},
            ],
            from_override=wa,
        )

    elif step in ("submitted", "tracking"):
        await _wa_send(phone, bot_text, db, step, wa)

    elif step in ("idle", "escalated", "error", "complete"):
        await _wa_send(phone, bot_text, db, step, wa)

    elif step == "info_shown":
        # Service info was shown — always follow with Apply Now / Ask a Question buttons.
        # This eliminates the need to type "Apply" and avoids the race condition where
        # the flow state hasn't been saved yet when the user quickly types "Apply".
        await _wa_send(phone, bot_text, db, step, wa)

    elif step == "docs_uploading":
        await _wa_send(phone, bot_text, db, step, wa)

    elif step == "collecting":
        await _wa_send(phone, bot_text, db, step, wa)

    else:
        await _wa_send(phone, bot_text, db, step, wa)


# =====================================================================
# ENDPOINTS
# =====================================================================

@router.get("/webhook")
async def ics_incoming_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    replytype: str            = Query(default="TEXT"),
    customernumber: str       = Query(default=""),
    replymessage: str         = Query(default=""),
    timestamp: Optional[str]  = Query(default=None),
    wabanumber: Optional[str] = Query(default=""),
):
    """
    Incoming user message webhook — called by ICS WABA.
    ICS sends: replytype, customernumber, replymessage, timestamp, wabanumber
    """
    waba_number = (wabanumber or "").strip()
    phone       = _normalize_phone(customernumber, waba_number)
    raw_reply   = unquote_plus(replymessage)
    reply_type  = replytype.upper()

    # ── Log full raw payload ──────────────────────────────────────────
    logger.info(
        "[ICS INCOMING PAYLOAD] raw_url=%s | replytype=%s | customernumber=%s | "
        "replymessage=%s | timestamp=%s | wabanumber=%s",
        str(request.url),
        replytype,
        sanitize_logs(customernumber),
        sanitize_logs(replymessage[:200]),
        timestamp,
        wabanumber,
    )

    if not phone:
        logger.warning("ICS webhook: empty customernumber — ignoring")
        return PlainTextResponse("OK", status_code=200)

    logger.info(
        "[ICS INCOMING] phone=%s type=%s waba=%s msg=%s",
        sanitize_logs(phone), reply_type, wabanumber, sanitize_logs(raw_reply[:200]),
    )

    try:
        db = await get_database()
        background_tasks.add_task(_handle_message, phone, waba_number, reply_type, raw_reply, db)
    except Exception as exc:
        logger.error("ICS webhook handler error: %s", exc)

    return PlainTextResponse("OK", status_code=200)


@router.post("/webhook")
async def ics_incoming_webhook_post(request: Request, background_tasks: BackgroundTasks):
    """POST variant of the incoming webhook."""
    params      = dict(request.query_params)
    waba_number = params.get("wabanumber", "").strip()
    phone       = _normalize_phone(params.get("customernumber", ""), waba_number)
    raw_reply   = unquote_plus(params.get("replymessage", ""))
    reply_type  = params.get("replytype", "TEXT").upper()

    if not phone:
        try:
            body = await request.json()
            waba_number = body.get("wabanumber", waba_number)
            phone       = _normalize_phone(body.get("customernumber", ""), waba_number)
            raw_reply   = body.get("replymessage", "")
            reply_type  = body.get("replytype", "TEXT").upper()
        except Exception:
            pass

    if not phone:
        return PlainTextResponse("OK", status_code=200)

    try:
        db = await get_database()
        background_tasks.add_task(_handle_message, phone, waba_number, reply_type, raw_reply, db)
    except Exception as exc:
        logger.error("ICS webhook POST handler error: %s", exc)

    return PlainTextResponse("OK", status_code=200)


@router.get("/delivery")
async def ics_delivery_callback(
    request: Request,
    qStatus:  Optional[str] = Query(default=None),
    qMobile:  Optional[str] = Query(default=None),
    qMsgRef:  Optional[str] = Query(default=None),
    qDTime:   Optional[str] = Query(default=None),
    SMSMSGID: Optional[str] = Query(default=None),
    SENDERID: Optional[str] = Query(default=None),
    NOTES:    Optional[str] = Query(default=None),
):
    """
    Delivery status callback — called by ICS WABA.
    Configure ICS delivery URL as:
      <your-ngrok>/api/ics-whatsapp/delivery?qStatus=%STATUS&qMobile=%MOBILENO
        &qMsgRef=%MESSAGEID&qDTime=%DATETIME&SMSMSGID=%SMSMSGID&NOTES=%NOTES
    """
    # ── Log full raw DLR payload ──────────────────────────────────────
    logger.info(
        "[ICS DLR PAYLOAD] raw_url=%s | qStatus=%s | qMobile=%s | qMsgRef=%s | "
        "qDTime=%s | SMSMSGID=%s | SENDERID=%s | NOTES=%s",
        str(request.url),
        qStatus, sanitize_logs(qMobile or ""), qMsgRef,
        qDTime, SMSMSGID, SENDERID, NOTES,
    )

    if qMsgRef and qStatus:
        try:
            db = await get_database()
            result = await db.ics_whatsapp_messages.update_one(
                {"ics_mid": qMsgRef},
                {"$set": {
                    "delivery_status":    qStatus,
                    "delivery_phone":     qMobile,
                    "delivery_timestamp": qDTime,
                    "client_ref":         SMSMSGID,
                    "notes":              NOTES,
                    "updated_at":         datetime.now(timezone.utc).isoformat(),
                }},
                upsert=False,
            )
            logger.info(
                "[ICS DLR] msg_ref=%s status=%s phone=%s matched=%d modified=%d",
                qMsgRef, qStatus, sanitize_logs(qMobile or ""),
                result.matched_count, result.modified_count,
            )
        except Exception as exc:
            logger.error("ICS delivery callback error: %s", exc)
    else:
        logger.warning("[ICS DLR] Missing qMsgRef or qStatus — payload ignored")

    return PlainTextResponse("OK", status_code=200)


@router.post("/delivery")
async def ics_delivery_callback_post(request: Request):
    """POST variant of delivery callback."""
    params    = dict(request.query_params)
    q_status  = params.get("qStatus")
    q_msg_ref = params.get("qMsgRef")
    q_mobile  = params.get("qMobile")
    q_d_time  = params.get("qDTime")
    smsmsgid  = params.get("SMSMSGID")
    notes     = params.get("NOTES")

    if q_msg_ref and q_status:
        try:
            db = await get_database()
            await db.ics_whatsapp_messages.update_one(
                {"ics_mid": q_msg_ref},
                {"$set": {
                    "delivery_status":    q_status,
                    "delivery_phone":     q_mobile,
                    "delivery_timestamp": q_d_time,
                    "client_ref":         smsmsgid,
                    "notes":              notes,
                    "updated_at":         datetime.now(timezone.utc).isoformat(),
                }},
                upsert=False,
            )
        except Exception as exc:
            logger.error("ICS delivery POST callback error: %s", exc)

    return PlainTextResponse("OK", status_code=200)


@router.get("/status")
async def ics_status():
    """Health check for ICS WABA integration."""
    return {
        "status":           "active",
        "ics_configured":   ics_waba.enabled,
        "ics_from":         ics_waba.from_ if ics_waba.enabled else "(not set)",
        "llm_available":    LLM_AVAILABLE and bool(EMERGENT_LLM_KEY),
        "webhook_incoming": "/api/ics-whatsapp/webhook",
        "webhook_delivery": "/api/ics-whatsapp/delivery",
    }


@router.post("/send")
async def send_ics_message(req: SendRequest):
    """Manual send endpoint — sends a raw outbound message (bypasses bot logic)."""
    result = await ics_waba.send_text(req.to, req.message)
    return {"success": "error" not in result, "result": result}


@router.post("/simulate")
async def simulate_incoming_message(req: SimulateRequest, background_tasks: BackgroundTasks):
    """
    Simulate an incoming WhatsApp message from req.phone.
    Runs the full bot logic (_handle_message) in the background exactly as if
    the message arrived via the real ICS webhook.
    """
    phone = _normalize_phone(req.phone, req.waba_number or "")
    if not phone:
        return {"success": False, "error": "phone is required"}

    try:
        db = await get_database()
        background_tasks.add_task(
            _handle_message, phone, req.waba_number or "", req.reply_type.upper(), req.message, db,
        )
        logger.info("simulate: phone=%s msg=%s", sanitize_logs(phone), sanitize_logs(req.message[:80]))
        return {"success": True, "phone": phone, "message": req.message}
    except Exception as exc:
        logger.error("simulate error: %s", exc)
        return {"success": False, "error": str(exc)}


@router.get("/conversations")
async def get_conversations(limit: int = 50):
    """Get recent ICS WhatsApp conversations for admin view."""
    db = await get_database()
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id":            "$phone_number",
            "last_message":   {"$first": "$message"},
            "last_timestamp": {"$first": "$timestamp"},
            "message_count":  {"$sum": 1},
        }},
        {"$sort": {"last_timestamp": -1}},
        {"$limit": limit},
    ]
    convs = await db.ics_whatsapp_messages.aggregate(pipeline).to_list(limit)
    return {
        "conversations": [
            {
                "phone_number":   c["_id"],
                "last_message":   (c["last_message"] or "")[:100],
                "last_timestamp": c["last_timestamp"],
                "message_count":  c["message_count"],
            }
            for c in convs
        ]
    }


@router.get("/messages/{phone_number}")
async def get_messages(phone_number: str, limit: int = 50):
    """Get message history for a single conversation."""
    db = await get_database()
    msgs = await db.ics_whatsapp_messages.find(
        {"phone_number": phone_number}, {"_id": 0}
    ).sort("timestamp", 1).limit(limit).to_list(limit)
    return {"messages": msgs}
