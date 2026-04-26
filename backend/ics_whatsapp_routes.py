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

import asyncio
import json
import logging
import os
import re
import smtplib
import uuid
from datetime import datetime, timezone
from email import encoders as _email_encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from urllib.parse import unquote_plus

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, JSONResponse, Response
from pydantic import BaseModel

from database import get_database
from security.input_sanitizer import sanitize_user_input
from security.guardrail import guardrail_service, sanitize_logs
from security.session_manager import session_manager
from services.ics_waba_service import ics_waba
from knowledge_scraper import (
    get_realtime_knowledge, extract_service_content, BLOCKED_SENTINEL,
    _get_blocked_keywords, filter_blocked_lines, blocked_prohibition,
)
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
# LANGUAGE SUPPORT  (mirrors consular_routes.py — keep in sync)
# =====================================================================
_LANG_NAMES: dict[str, str] = {
    "en":  "English",
    # Indian
    "hi":  "Hindi",      "bn":  "Bengali",    "mr":  "Marathi",
    "te":  "Telugu",     "ta":  "Tamil",      "gu":  "Gujarati",
    "ur":  "Urdu",       "kn":  "Kannada",    "or":  "Odia",
    "ml":  "Malayalam",  "pa":  "Punjabi",    "as":  "Assamese",
    "mai": "Maithili",   "sa":  "Sanskrit",   "sat": "Santali",
    "ks":  "Kashmiri",   "ne":  "Nepali",     "sd":  "Sindhi",
    "doi": "Dogri",      "kok": "Konkani",    "mni": "Manipuri",
    "brx": "Bodo",       "mwr": "Marwari",
    # South African
    "zu":  "Zulu",       "xh":  "Xhosa",      "af":  "Afrikaans",
    "nso": "Sepedi",     "tn":  "Setswana",   "st":  "Sesotho",
    "ts":  "Xitsonga",   "ss":  "siSwati",    "ve":  "Tshivenda",
    "nr":  "isiNdebele",
    # International
    "ar":  "Arabic",     "fr":  "French",     "sw":  "Swahili",
    "ha":  "Hausa",      "yo":  "Yoruba",     "ig":  "Igbo",
    "am":  "Amharic",    "om":  "Oromo",
}

_LANG_SCRIPT_HINT: dict[str, str] = {
    "hi":  "You MUST write in Devanagari script (देवनागरी). Do NOT use Urdu/Perso-Arabic script.",
    "mr":  "You MUST write in Devanagari script (देवनागरी). Do NOT use Urdu/Perso-Arabic script.",
    "ne":  "You MUST write in Devanagari script (देवनागरी).",
    "sa":  "You MUST write in Devanagari script (देवनागरी).",
    "doi": "You MUST write in Devanagari script (देवनागरी).",
    "ur":  "You MUST write in Perso-Arabic script (اردو رسم الخط). Do NOT use Devanagari script.",
    "pa":  "You MUST write in Gurmukhi script (ਗੁਰਮੁਖੀ). Do NOT use Shahmukhi/Perso-Arabic script.",
    "ta":  "You MUST write in Tamil script (தமிழ் எழுத்து). Do NOT use any other South Indian script.",
    "te":  "You MUST write in Telugu script (తెలుగు లిపి).",
    "kn":  "You MUST write in Kannada script (ಕನ್ನಡ ಲಿಪಿ).",
    "ml":  "You MUST write in Malayalam script (മലയാളം ലിപി).",
    "gu":  "You MUST write in Gujarati script (ગુજરાતી લિપિ).",
    "bn":  "You MUST write in Bengali script (বাংলা লিপি).",
    "or":  "You MUST write in Odia script (ଓଡ଼ିଆ ଲିପି).",
    "as":  "You MUST write in Bengali-Assamese script (অসমীয়া লিপি).",
}

# Ordered list used to build the numbered WhatsApp menu
# (english_name, lang_code, native_script_display)
_LANGUAGE_LIST = [
    # Indian Languages
    ("English",    "en",  "English"),
    ("Hindi",      "hi",  "हिंदी"),
    ("Bengali",    "bn",  "বাংলা"),
    ("Marathi",    "mr",  "मराठी"),
    ("Telugu",     "te",  "తెలుగు"),
    ("Tamil",      "ta",  "தமிழ்"),
    ("Gujarati",   "gu",  "ગુજરાતી"),
    ("Urdu",       "ur",  "اردو"),
    ("Kannada",    "kn",  "ಕನ್ನಡ"),
    ("Odia",       "or",  "ଓଡ଼ିଆ"),
    ("Malayalam",  "ml",  "മലയാളം"),
    ("Punjabi",    "pa",  "ਪੰਜਾਬੀ"),
    ("Assamese",   "as",  "অসমীয়া"),
    ("Maithili",   "mai", "मैथिली"),
    ("Sanskrit",   "sa",  "संस्कृत"),
    ("Santali",    "sat", "ᱥᱟᱱᱛᱟᱲᱤ"),
    ("Kashmiri",   "ks",  "کٲشُر"),
    ("Nepali",     "ne",  "नेपाली"),
    ("Sindhi",     "sd",  "سنڌي"),
    ("Dogri",      "doi", "डोगरी"),
    ("Konkani",    "kok", "कोंकणी"),
    ("Manipuri",   "mni", "মৈতৈলোন্"),
    ("Bodo",       "brx", "बड़ो"),
    ("Marwari",    "mwr", "मारवाड़ी"),
    # South African Languages
    ("Zulu",       "zu",  "isiZulu"),
    ("Xhosa",      "xh",  "isiXhosa"),
    ("Afrikaans",  "af",  "Afrikaans"),
    ("Sepedi",     "nso", "Sepedi"),
    ("Setswana",   "tn",  "Setswana"),
    ("Sesotho",    "st",  "Sesotho"),
    ("Xitsonga",   "ts",  "Xitsonga"),
    ("siSwati",    "ss",  "siSwati"),
    ("Tshivenda",  "ve",  "Tshivenda"),
    ("isiNdebele", "nr",  "isiNdebele"),
    # International Languages
    ("Arabic",     "ar",  "العربية"),
    ("French",     "fr",  "Français"),
    ("Swahili",    "sw",  "Kiswahili"),
    ("Hausa",      "ha",  "Hausa"),
    ("Yoruba",     "yo",  "Yorùbá"),
    ("Igbo",       "ig",  "Igbo"),
    ("Amharic",    "am",  "አማርኛ"),
    ("Oromo",      "om",  "Oromoo"),
]

# number string → (english_name, lang_code)
_LANGUAGES: dict[str, tuple] = {
    str(i + 1): (eng, code) for i, (eng, code, _n) in enumerate(_LANGUAGE_LIST)
}

# name → (english_name, lang_code) for both English and native script input
_LANG_BY_NAME: dict = {}
for _li, (_le, _lc, _ln) in enumerate(_LANGUAGE_LIST):
    _LANG_BY_NAME[_le.lower()] = (_le, _lc)
    _LANG_BY_NAME[_ln]         = (_le, _lc)
    if _ln.lower() != _le.lower():
        _LANG_BY_NAME[_ln.lower()] = (_le, _lc)
del _li, _le, _lc, _ln


def _detect_language_input(text: str):
    """
    Returns (english_name, lang_code) if text is a number 1-42 or a language name
    (English or native script).  Returns None if no match.
    """
    t = text.strip()
    if t in _LANGUAGES:
        eng, code = _LANGUAGES[t]
        return eng, code
    return _LANG_BY_NAME.get(t.lower()) or _LANG_BY_NAME.get(t)


def _wa_lang_instruction(code: str) -> str:
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


def _build_language_menu() -> str:
    lines = [
        "🌐 *Choose your preferred language:*",
        "Reply with the number or type the language name.\n",
        "🇮🇳 *Indian Languages*",
    ]
    for i, (eng, _code, native) in enumerate(_LANGUAGE_LIST):
        num = i + 1
        if num == 25:
            lines.append("\n🇿🇦 *South African Languages*")
        elif num == 35:
            lines.append("\n🌍 *International Languages*")
        display = f"{native} ({eng})" if native != eng else eng
        lines.append(f"{num}. {display}")
    lines.append(
        "\n👉 You can also type your language name (e.g., \"Hindi\", \"Tamil\", \"Zulu\").\n"
        "\n⚙️ *Note:*\n"
        "If no language is selected, the default language will be English.\n"
        "Once selected, the entire conversation will continue in your chosen language."
    )
    return "\n".join(lines)


_LANGUAGE_MENU = _build_language_menu()


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
async def _llm_response(user_message: str, session_id: str, context: str = "", lang_code: str = "en") -> str:
    if not LLM_AVAILABLE or not EMERGENT_LLM_KEY:
        return (
            "Thank you for your message. For detailed assistance please visit "
            "https://www.cgijoburg.gov.in or call +27 11 581 9800."
        )

    _blocked_kws = await _get_blocked_keywords()

    # Build service-specific document hint (same as web bot)
    detected_svc = detect_service(user_message)
    svc_docs_hint = ""
    if detected_svc and detected_svc in SERVICES:
        svc = SERVICES[detected_svc]
        docs = "\n".join(f"  • {d}" for d in svc["documents"])
        svc_docs_hint = f"\nDOCUMENTS REQUIRED FOR {svc['name'].upper()}:\n{docs}\n"

    _clean_ctx      = filter_blocked_lines(context, _blocked_kws)
    _clean_hint     = filter_blocked_lines(svc_docs_hint, _blocked_kws)
    _prohibition    = blocked_prohibition(_blocked_kws)
    _consulate_facts = filter_blocked_lines(
        "- Acting Consul General: Mr. Harish Kumar\n"
        "- Address: No. 1, Eton Road (Corner Jan Smuts Avenue & Eton Road), Park Town 2193, Johannesburg\n"
        "- Phone: +27 11-4828484 / +27 11-4828485 / +27 11-4828486 / +27 11 581 9800\n"
        "- Email: ccom.jburg@mea.gov.in (general) | cons.jburg@mea.gov.in (consular/OCI)\n"
        "- Website: www.cgijoburg.gov.in\n"
        "- Office Hours: Mon–Fri 08:30–17:00 (Lunch: 13:00–13:30)\n"
        "- Jurisdiction: Gauteng, North West, Limpopo and Mpumalanga provinces of South Africa\n"
        "- Social Media: Twitter/X @indiainjoburg | Facebook: IndiaInSouthAfricaJohannesburg | Instagram: @indiainjohannesburg\n"
        "- VFS Global (Passport/PCC): 2nd Floor, Harrow Court 1, Isle of Houghton, Park Town, JHB — Tel: 012 425 3007\n"
        "- VFS Global (Visa): 1st Floor, Rivonia Village Office Block, Rivonia, JHB — Tel: 012 425 3007\n"
        "- VFS Hours: Submission Mon–Fri 08:00–15:00 | Collection 11:00–16:00",
        _blocked_kws,
    )

    system_prompt = f"""You are Seva Setu Bot, the official consular assistant for the Consulate General of India, Johannesburg. You are replying via WhatsApp.
{_prohibition}
CRITICAL — DATA SOURCE RULE:
Answer ONLY using the OFFICIAL DATA provided below.
The data comes from: www.cgijoburg.gov.in, vfsglobal.com, and admin-uploaded documents (FAQs, events, notices).
Do NOT use general training knowledge. Do NOT invent or add information not in the data below.
If the answer is not in the data, say so and direct the user to contact the Consulate directly.

{_wa_lang_instruction(lang_code)}

RESPONSE STYLE:
- Be concise, accurate, and helpful.
- Do NOT echo the user's question back.
- Do NOT add feedback/rating prompts or sign-off phrases.
- Use bullet points only when listing multiple items.
- Do NOT repeat information already shown in the conversation.
- Use *bold* for emphasis (WhatsApp format). Do NOT use markdown ** double-asterisks.
- Never ask for money or claim the consulate calls asking for payments.

KEY CONSULATE FACTS (always use these for contact/location questions):
{_consulate_facts}
{_clean_hint}
OFFICIAL DATA (cgijoburg.gov.in | vfsglobal.com | uploaded documents):
{_clean_ctx}

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
# APPLICATION FLOW — WHATSAPP HELPERS
# =====================================================================
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")

_SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
_SMTP_USER = os.environ.get("SMTP_USER", "")
_SMTP_PASS = os.environ.get("SMTP_PASSWORD", "")

# ── Type A services — Gov portal + reference number collection ────────
_WA_TYPE_A = {
    "passport": {
        "name": "Passport Services",
        "gov_url": "https://passportindia.gov.in",
        "vfs_note": (
            "Submit your completed application at *VFS Global* "
            "(2nd Floor, Harrow Court, Isle of Houghton, Park Town, JHB — Tel: 012 425 3007)\n"
            "🕐 Submission: Mon–Fri 08:00–15:00 | Collection: 11:00–16:00"
        ),
        "documents": [
            "Valid/Expired Indian Passport — original + photocopy of all pages",
            "Completed application from passportindia.gov.in",
            "3 recent passport-size photos (51×51 mm, white background)",
            "Proof of South African address (utility bill/lease)",
            "South African ID / valid visa / work permit",
        ],
    },
    "visa": {
        "name": "Indian Visa",
        "gov_url": "https://indianvisaonline.gov.in",
        "vfs_note": (
            "Submit at *VFS Global Visa Centre* "
            "(1st Floor, Rivonia Village Office Block, cnr Rivonia Blvd & Mutual Rd, JHB)\n"
            "🕐 Mon–Fri 08:00–15:00"
        ),
        "documents": [
            "Valid foreign passport (min. 6 months validity remaining)",
            "Completed Visa Application Form from indianvisaonline.gov.in",
            "2 recent passport-size photographs",
            "Travel itinerary / confirmed tickets",
            "Hotel bookings / invitation letter",
            "Bank statement (last 3 months)",
        ],
    },
    "pcc": {
        "name": "Police Clearance Certificate (PCC)",
        "gov_url": "https://portal5.passportindia.gov.in",
        "vfs_note": (
            "Submit at *VFS Global* "
            "(2nd Floor, Harrow Court 1, Isle of Houghton, Park Town, JHB — Tel: 012 425 3007)\n"
            "🕐 Submission: Mon–Fri 08:00–15:00"
        ),
        "documents": [
            "Valid Indian Passport — original + photocopy",
            "Completed PCC Application Form (portal5.passportindia.gov.in)",
            "Proof of current South African residential address",
            "Copy of SA Permanent Residence / Visa",
            "2 passport-size photographs",
            "Fee payment receipt",
        ],
    },
}

# Type A state fields — collected after gov reference
_WA_TYPE_A_FIELDS = [
    {"key": "full_name", "question": "Please enter your *full name* (as on your passport):"},
    {"key": "email",     "question": "Please enter your *email address* (for PDF copy):"},
]

# Keywords that show "my applications" list
_MY_APPS_WORDS = {
    "my applications", "my application", "my apps", "applications",
    "application list", "application status", "my status", "my forms",
    "show applications", "list applications",
}

# Keywords that show the services menu
_SERVICES_MENU_WORDS = {
    "services", "service list", "what services", "available services",
    "show services", "consular services", "what can you do",
    "help me apply", "i want to apply", "how to apply",
}

# Active form-filling states — language detection must not interfere
_FORM_ACTIVE_STATES = {"consent_pending", "collecting", "docs_uploading", "docs_pending", "paused"}


async def _wa_generate_pdf(tracking_id: str, db) -> Optional[bytes]:
    """Generate PDF bytes for a submitted application."""
    try:
        from services.pdf_service import generate_application_pdf
        app = await db.applications.find_one(
            {"tracking_id": tracking_id.upper()}, {"_id": 0}
        )
        if not app or app.get("service") not in SERVICES:
            return None
        service_name  = SERVICES[app["service"]]["name"]
        uploaded_docs = [
            {"name": d.get("name", "Document"), "status": d.get("status", "uploaded")}
            for d in app.get("documents", [])
        ]
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: generate_application_pdf(
                service_name=service_name,
                form_data=app.get("form_data", {}),
                tracking_id=tracking_id.upper(),
                uploaded_docs=uploaded_docs,
            ),
        )
    except Exception as exc:
        logger.error("[WA PDF] Generation failed %s: %s", tracking_id, exc)
        return None


def _smtp_send(to_email: str, service_name: str, tracking_id: str, pdf_bytes: bytes):
    """Synchronous SMTP helper — run in executor."""
    if not _SMTP_USER or not _SMTP_PASS:
        logger.warning("[WA EMAIL] SMTP not configured — skipping email for %s", tracking_id)
        return
    safe   = service_name.lower().replace(" ", "_")
    fname  = f"application_{safe}_{tracking_id}.pdf"
    msg    = MIMEMultipart()
    msg["From"]    = _SMTP_USER
    msg["To"]      = to_email
    msg["Subject"] = f"Seva Setu — {service_name} Application ({tracking_id})"
    body = (
        f"<html><body style='font-family:Arial,sans-serif'>"
        f"<h2 style='color:#000080'>🇮🇳 Seva Setu — Application Submitted</h2>"
        f"<p>Your <strong>{service_name}</strong> application has been received.</p>"
        f"<table style='border-collapse:collapse'>"
        f"<tr><td style='padding:6px 12px;border:1px solid #ddd'><strong>Tracking ID</strong></td>"
        f"<td style='padding:6px 12px;border:1px solid #ddd'><code>{tracking_id}</code></td></tr>"
        f"<tr><td style='padding:6px 12px;border:1px solid #ddd'><strong>Service</strong></td>"
        f"<td style='padding:6px 12px;border:1px solid #ddd'>{service_name}</td></tr>"
        f"</table>"
        f"<p>Your application PDF is attached. Keep it for your records.</p>"
        f"<p style='color:#666;font-size:12px'>Consulate General of India, Johannesburg<br>"
        f"📞 +27 11-4828484 | ✉️ ccom.jburg@mea.gov.in</p>"
        f"</body></html>"
    )
    msg.attach(MIMEText(body, "html"))
    part = MIMEBase("application", "octet-stream")
    part.set_payload(pdf_bytes)
    _email_encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
    msg.attach(part)
    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as srv:
            srv.starttls()
            srv.login(_SMTP_USER, _SMTP_PASS)
            srv.send_message(msg)
        logger.info("[WA EMAIL] PDF sent to %s for %s", to_email, tracking_id)
    except Exception as exc:
        logger.error("[WA EMAIL] Failed → %s: %s", to_email, exc)


async def _wa_after_submit(phone: str, session_id: str, waba_number: str, db):
    """
    Called right after process_flow() returns step='submitted'.
    Finds the application, generates PDF, sends it via WhatsApp document
    and emails it to the applicant.
    """
    try:
        app = await db.applications.find_one(
            {"user_id": phone, "status": "submitted"},
            {"_id": 0},
            sort=[("submitted_at", -1)],
        )
        if not app:
            app = await db.applications.find_one(
                {"session_id": session_id, "status": "submitted"},
                {"_id": 0},
                sort=[("submitted_at", -1)],
            )
        if not app:
            return

        tracking_id  = app.get("tracking_id", "")
        service_name = app.get("service_name") or SERVICES.get(app.get("service", ""), {}).get("name", "")
        to_email     = app.get("form_data", {}).get("email", "")

        pdf_bytes = await _wa_generate_pdf(tracking_id, db)
        if not pdf_bytes:
            return

        # Send PDF as WhatsApp document if public URL is configured
        if APP_BASE_URL:
            safe  = (service_name or "application").lower().replace(" ", "_")
            fname = f"application_{safe}_{tracking_id}.pdf"
            pdf_url = f"{APP_BASE_URL}/api/ics-whatsapp/pdf/{tracking_id}"
            result = await ics_waba.send_media(
                to=phone,
                media_type="document",
                url=pdf_url,
                caption=f"📄 Your *{service_name}* application PDF\n🔖 Tracking ID: `{tracking_id}`",
                filename=fname,
                from_override=waba_number,
            )
            if "error" not in result:
                await _log_message(
                    phone, "outbound", f"[PDF document: {fname}]",
                    {"step": "pdf_delivery", "tracking_id": tracking_id}, db,
                )

        # Email PDF to applicant
        if to_email and pdf_bytes:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, _smtp_send, to_email, service_name, tracking_id, pdf_bytes,
            )
            await ics_waba.send_text(
                phone,
                f"📧 A copy has also been emailed to *{to_email}*.",
                from_override=waba_number,
            )
    except Exception as exc:
        logger.error("[WA AFTER SUBMIT] phone=%s: %s", phone, exc)


async def _wa_my_applications(phone: str, db) -> str:
    """Return a formatted summary of the user's recent applications."""
    apps = await db.applications.find(
        {"user_id": phone},
        {"_id": 0, "tracking_id": 1, "service_name": 1, "status": 1, "created_at": 1},
        sort=[("created_at", -1)],
    ).limit(5).to_list(5)

    if not apps:
        return (
            "You have no applications on record.\n\n"
            "To start, type the service name — e.g. *Passport*, *OCI*, *Visa*, *Attestation*."
        )

    lines = ["📋 *Your Recent Applications*\n"]
    for i, a in enumerate(apps, 1):
        status = a.get("status", "unknown").replace("_", " ").title()
        svc    = a.get("service_name", "—")
        tid    = a.get("tracking_id", "—")
        dt     = (a.get("created_at") or "")[:10]
        lines.append(f"{i}. *{svc}*\n   🔖 {tid}\n   📅 {dt}  ·  {status}")

    lines.append(
        "\n_Send a Tracking ID to view details or receive your PDF._\n"
        "_Type *apply* + service name to start a new application._"
    )
    return "\n\n".join(lines)


# =====================================================================
# TYPE A STATE MACHINE HELPERS
# =====================================================================
async def _type_a_get(db, session_id: str) -> dict:
    s = await db.chat_sessions.find_one({"id": session_id}, {"metadata.wa_type_a": 1})
    return (s or {}).get("metadata", {}).get("wa_type_a", {})


async def _type_a_save(db, session_id: str, **fields):
    current = await _type_a_get(db, session_id)
    current.update(fields)
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {"metadata.wa_type_a": current}},
    )


async def _type_a_clear(db, session_id: str):
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$unset": {"metadata.wa_type_a": ""}},
    )


async def _type_a_submit(phone: str, session_id: str, waba_number: str, db) -> str:
    """
    Finalise a Type A application: create DB record, generate PDF, deliver it.
    Returns the tracking ID.
    """
    ta = await _type_a_get(db, session_id)
    svc_key      = ta.get("service", "passport")
    svc          = _WA_TYPE_A.get(svc_key, {})
    service_name = svc.get("name", svc_key.title())
    gov_ref      = ta.get("gov_reference", "")
    form_data    = {
        "full_name":             ta.get("full_name", ""),
        "email":                 ta.get("email", ""),
        "phone":                 phone,
        "gov_reference_number":  gov_ref,
    }
    now        = datetime.now(timezone.utc)
    app_id     = str(uuid.uuid4())
    tracking_id = f"{svc_key.upper()}-{now.strftime('%Y%m%d')}-{app_id[:6].upper()}"
    doc_list   = [{"name": d, "status": "required"} for d in svc.get("documents", [])]

    await db.applications.insert_one({
        "id":                 app_id,
        "tracking_id":        tracking_id,
        "session_id":         session_id,
        "user_id":            phone,
        "service":            svc_key,
        "service_name":       service_name,
        "category":           "TYPE_A",
        "status":             "submitted",
        "form_data":          form_data,
        "documents":          doc_list,
        "gov_reference":      gov_ref,
        "created_at":         now.isoformat(),
        "updated_at":         now.isoformat(),
        "submitted_at":       now.isoformat(),
    })

    # Generate and deliver PDF
    from services.pdf_service import generate_application_pdf
    loop = asyncio.get_event_loop()
    try:
        pdf_bytes = await loop.run_in_executor(
            None,
            lambda: generate_application_pdf(
                service_name=service_name,
                form_data=form_data,
                tracking_id=tracking_id,
                uploaded_docs=doc_list,
            ),
        )
        if pdf_bytes:
            if APP_BASE_URL:
                pdf_url  = f"{APP_BASE_URL}/api/ics-whatsapp/pdf/{tracking_id}"
                safe     = service_name.lower().replace(" ", "_")
                await ics_waba.send_media(
                    to=phone, media_type="document", url=pdf_url,
                    caption=f"📄 *{service_name}* Application Summary\n🔖 Tracking ID: `{tracking_id}`",
                    filename=f"application_{safe}_{tracking_id}.pdf",
                    from_override=waba_number,
                )
            if form_data.get("email"):
                loop2 = asyncio.get_event_loop()
                await loop2.run_in_executor(
                    None, _smtp_send, form_data["email"], service_name, tracking_id, pdf_bytes,
                )
                await ics_waba.send_text(
                    phone,
                    f"📧 PDF also emailed to *{form_data['email']}*.",
                    from_override=waba_number,
                )
    except Exception as exc:
        logger.error("[TYPE_A SUBMIT] PDF error for %s: %s", tracking_id, exc)

    await _type_a_clear(db, session_id)
    return tracking_id


def _wa_services_menu() -> str:
    """Build the WhatsApp services menu showing all Type A and Type B services."""
    lines = [
        "🏛️ *Consular Services — Seva Setu Bot*\n",
        "─────────────────────────────",
        "🌐 *Type A — Apply via Government Portal*",
        "_(Bot records your reference number & generates PDF)_\n",
    ]
    num = 1
    for key, svc in _WA_TYPE_A.items():
        lines.append(f"{num}. *{svc['name']}*\n   🔗 {svc['gov_url']}")
        num += 1

    lines.append(
        "\n─────────────────────────────\n"
        "📝 *Type B — Fill Form Directly Here*\n"
        "_(Complete the form in this chat)_\n"
    )
    for key, svc in SERVICES.items():
        if key not in _WA_TYPE_A:
            lines.append(f"{num}. *{svc['name']}*")
            num += 1

    lines.append(
        "\n─────────────────────────────\n"
        "💬 Type the *service name* or *number* to begin.\n"
        "📋 Type *my applications* to view your submissions."
    )
    return "\n".join(lines)


# =====================================================================
# SESSION LANGUAGE HELPERS
# =====================================================================
async def _set_session_language(db, session_id: str, lang_name: str, lang_code: str):
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {
            "metadata.language":      lang_code,
            "metadata.language_name": lang_name,
            "metadata.lang_pending":  False,
        }},
    )


async def _set_lang_pending(db, session_id: str):
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {"metadata.lang_pending": True, "metadata.greeted": True}},
    )


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
    
    # ── Get or create session EARLY — needed for language state checks ──
    session = await session_manager.get_or_create_session(
        channel="whatsapp",
        user_identifier=phone,
        metadata={"waba_number": waba_number},
    )
    session_id         = session["id"]
    _meta              = session.get("metadata", {})
    _lang_pending_flag = _meta.get("lang_pending", False)
    _lang_code         = _meta.get("language", "en")
    _lang_name         = _meta.get("language_name", "English")

    # ── Active form state check — used to protect language and menu detection ──
    _form_active = _current_flow.get("state") in _FORM_ACTIVE_STATES

    # ── GLOBAL COMMANDS — works from any non-form state ─────────────────
    if not _form_active and not selected_id:
        _t_lower = clean_text.strip().lower()
        if _t_lower in _MY_APPS_WORDS:
            apps_msg = await _wa_my_applications(phone, db)
            await _wa_send(phone, apps_msg, db, "my_apps", waba_number)
            await session_manager.add_message(session_id, "user", user_text)
            await session_manager.add_message(session_id, "assistant", apps_msg)
            return
        if _t_lower in _SERVICES_MENU_WORDS:
            menu_msg = _wa_services_menu()
            await _wa_send(phone, menu_msg, db, "services_menu", waba_number)
            await session_manager.add_message(session_id, "user", user_text)
            await session_manager.add_message(session_id, "assistant", menu_msg)
            return

    # ── LANGUAGE SELECTION — skip during active form filling ────────────────
    # During lang_pending: numbers 1-42 AND typed names are treated as language picks.
    # At any other time: only a bare typed language name switches the language.
    if _lang_pending_flag and not _form_active:
        lang_result = _detect_language_input(clean_text)
        if lang_result:
            eng_name, code = lang_result
            await _set_session_language(db, session_id, eng_name, code)
            _lang_name, _lang_code = eng_name, code
            confirm_msg = f"✅ Language set to *{eng_name}*. I'll continue all responses in {eng_name}. 🙏"
            await _wa_send(phone, confirm_msg, db, "lang_set", waba_number)
            await session_manager.add_message(session_id, "user", user_text)
            await session_manager.add_message(session_id, "assistant", confirm_msg)
            return
        else:
            # No valid selection — clear lang_pending but KEEP the previously chosen language
            _existing_code = _meta.get("language", "en")
            _existing_name = _meta.get("language_name", "English")
            await _set_session_language(db, session_id, _existing_name, _existing_code)
            _lang_code = _existing_code
            _lang_name = _existing_name
    elif not _form_active and not clean_text.strip().isdigit():
        _t = clean_text.strip().lower()

        # "language" / "change language" keywords → show language menu to re-select
        _LANG_MENU_TRIGGERS = {
            "language", "change language", "languages", "select language",
            "choose language", "switch language", "भाषा", "langue", "lugha",
        }
        if _t in _LANG_MENU_TRIGGERS:
            await ics_waba.send_text(phone, _LANGUAGE_MENU, from_override=waba_number)
            await _log_message(phone, "outbound", _LANGUAGE_MENU, {"step": "lang_menu"}, db)
            await _set_lang_pending(db, session_id)
            await session_manager.add_message(session_id, "user", user_text)
            return

        # Bare typed language name → confirm switch then show menu for re-selection
        _name_match = (
            _LANG_BY_NAME.get(_t)
            or _LANG_BY_NAME.get(clean_text.strip())
        )
        if _name_match:
            eng_name, code = _name_match
            await _set_session_language(db, session_id, eng_name, code)
            _lang_name, _lang_code = eng_name, code
            confirm_msg = f"✅ Language switched to *{eng_name}*. I'll continue all responses in {eng_name}. 🙏"
            await _wa_send(phone, confirm_msg, db, "lang_set", waba_number)
            await session_manager.add_message(session_id, "user", user_text)
            await session_manager.add_message(session_id, "assistant", confirm_msg)
            # Show menu again so user can change their mind
            await ics_waba.send_text(phone, _LANGUAGE_MENU, from_override=waba_number)
            await _log_message(phone, "outbound", _LANGUAGE_MENU, {"step": "lang_menu"}, db)
            await _set_lang_pending(db, session_id)
            return

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
        elif selected_id == "type_a_submit":
            clean_text = "submit"   # handled by Type A state machine below
        elif selected_id.startswith("apply_"):
            # Extract the service key directly — more reliable than text matching
            _svc_key = selected_id[len("apply_"):]
            if _svc_key in _WA_TYPE_A:
                # Type A service — will be intercepted by state machine below
                clean_text = f"apply {_svc_key}"
            else:
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

    # ── SHOW MAIN MENU ────────────────────────────────────────────────
    # Shown for: first message, greeting words, OR 10-min idle.
    # Everything else (questions, apply intents, service names) goes to the bot engine.
    current_flow = await get_flow_state(session_id)

    _MENU_WORDS = {"menu", "hi", "hello", "start", "help", "/start", "hey", "namaste", "hola"}
    _is_new_session   = not _meta.get("greeted", False)
    _is_greeting_word = clean_text.lower().strip() in _MENU_WORDS

    _is_long_idle = False
    _last_act = session.get("last_activity", "")
    if _last_act and not _is_new_session:
        try:
            _la_dt = datetime.fromisoformat(_last_act.replace("Z", "+00:00"))
            _is_long_idle = (datetime.now(timezone.utc) - _la_dt).total_seconds() > 600
        except Exception:
            pass

    is_menu_trigger = _is_new_session or _is_greeting_word or _is_long_idle

    if is_menu_trigger and not selected_id:
        # Send greeting + advisory as plain text first
        greeting_text = (
            "🙏 नमस्ते भाईयो और बहनो!\n\n"
            "मैं हूं \"सेवा सेतु स्वचालित सहायक (बॉट)\", आपकी सेवा में सदैव तत्पर।\n\n"
            "🗣 भारतीय काउंसलर सर्विसेज के साथ हाज़िर हूं। बताएं, मैं आपकी किस प्रकार सहायता कर सकता हूं? "
            "आज मैं आपकी मदद करने में सक्षम हूं।\n\n"
            "Namaste, brothers and sisters!\n\n"
            "I am \"Seva Setu Automated Assistant (Bot)\", always ready to serve you.\n\n"
            "🗣 Here to assist with your Indian consular service queries. "
            "Please let me know how I can help you today. I am fully equipped to assist you.\n\n"
            "⚠️ *Important Advisory from the Consulate General of India, Johannesburg*\n"
            "The Consulate does not make phone calls demanding money for fines, penalties, or any other reason. "
            "It is not within our mandate to conduct criminal investigations.\n\n"
            "Do not engage with such callers under any circumstance.\n\n"
            "• Do not share any personal or financial information.\n"
            "• If you receive a suspicious call, note the caller's number and any details.\n"
            "• Report it immediately to your local police station.\n\n"
            "Be vigilant. Stay safe.\n\n"
            "🗣 *Fraud Alert: Extortion Calls Using Spoofed Numbers*\n"
            "It has come to our attention that certain individuals are fraudulently spoofing the Consulate General's "
            "phone numbers to contact persons of Indian origin. These calls attempt to intimidate recipients with "
            "false legal threats and demand payments, claiming affiliation with the Consulate General or Government of India agencies.\n\n"
            "Please be advised:\n\n"
            "• No representative of the Consulate General will call to request payments for any governmental purpose.\n"
            "• If you receive such a call, note the caller's details and report the incident to your local police immediately."
        )
        await ics_waba.send_text(phone, greeting_text, from_override=waba_number)
        await _log_message(phone, "outbound", greeting_text, {"step": "greeting"}, db)
        # Always follow greeting with language menu (new session, greeting word, or 10-min idle).
        await ics_waba.send_text(phone, _LANGUAGE_MENU, from_override=waba_number)
        await _log_message(phone, "outbound", _LANGUAGE_MENU, {"step": "lang_menu"}, db)
        await _set_lang_pending(db, session_id)
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

    # ── TYPE A: detect apply intent and start gov-portal flow ───────────
    if not _form_active:
        _ta = _meta.get("wa_type_a", {})
        _ta_state = _ta.get("state", "")

        # ── Step handler: active Type A application ──────────────────────
        if _ta_state:
            from services.application_flow import is_discard as _is_discard
            _ta_svc  = _ta.get("service", "passport")
            _ta_name = _WA_TYPE_A.get(_ta_svc, {}).get("name", _ta_svc.title())

            if _ta_state == "awaiting_ref":
                ref = clean_text.strip()
                if len(ref) >= 4:
                    await _type_a_save(db, session_id, gov_reference=ref, state="collecting_name")
                    await _wa_send(
                        phone,
                        f"✅ Reference *{ref}* saved.\n\n" + _WA_TYPE_A_FIELDS[0]["question"],
                        db, "type_a", waba_number,
                    )
                else:
                    await _wa_send(
                        phone,
                        f"Please send your government reference number for *{_ta_name}*.\n"
                        "Type *discard* to cancel.",
                        db, "type_a", waba_number,
                    )
                await session_manager.add_message(session_id, "user", user_text)
                return

            elif _ta_state == "collecting_name":
                if _is_discard(clean_text):
                    await _type_a_clear(db, session_id)
                    await _wa_send(phone, "Application cancelled. How else can I help?", db, "type_a", waba_number)
                else:
                    await _type_a_save(db, session_id, full_name=clean_text.strip(), state="collecting_email")
                    await _wa_send(phone, _WA_TYPE_A_FIELDS[1]["question"], db, "type_a", waba_number)
                await session_manager.add_message(session_id, "user", user_text)
                return

            elif _ta_state == "collecting_email":
                if _is_discard(clean_text):
                    await _type_a_clear(db, session_id)
                    await _wa_send(phone, "Application cancelled. How else can I help?", db, "type_a", waba_number)
                    await session_manager.add_message(session_id, "user", user_text)
                    return
                await _type_a_save(db, session_id, email=clean_text.strip(), state="submitting")
                ta_now = await _type_a_get(db, session_id)
                summary = (
                    f"📋 *Review Your {_ta_name} Application*\n\n"
                    f"👤 Name: {ta_now.get('full_name', '—')}\n"
                    f"📧 Email: {ta_now.get('email', '—')}\n"
                    f"📞 Phone: {phone}\n"
                    f"🔖 Gov Reference: {ta_now.get('gov_reference', '—')}\n\n"
                    f"Reply *submit* to confirm or *discard* to cancel."
                )
                await _wa_send(phone, summary, db, "type_a", waba_number)
                await ics_waba.send_buttons(
                    to=phone,
                    body="Ready to submit?",
                    buttons=[
                        {"id": "type_a_submit", "title": "Submit"},
                        {"id": "btn_cancel",    "title": "Cancel"},
                    ],
                    header=_ta_name,
                    from_override=waba_number,
                )
                await session_manager.add_message(session_id, "user", user_text)
                return

            elif _ta_state == "submitting":
                if _is_discard(clean_text) or selected_id == "btn_cancel":
                    await _type_a_clear(db, session_id)
                    await _wa_send(phone, "Application cancelled.", db, "type_a", waba_number)
                    await session_manager.add_message(session_id, "user", user_text)
                    return
                if "submit" in clean_text.lower() or selected_id == "type_a_submit":
                    tracking_id = await _type_a_submit(phone, session_id, waba_number, db)
                    confirm = (
                        f"🎉 *Application Submitted!*\n\n"
                        f"🔖 Tracking ID: `{tracking_id}`\n\n"
                        f"Your PDF summary has been sent. The Consulate will contact you.\n\n"
                        f"📞 +27 11-4828484 | 📧 cons.jburg@mea.gov.in"
                    )
                    await _wa_send(phone, confirm, db, "type_a_submitted", waba_number)
                    await session_manager.add_message(session_id, "user", user_text)
                    await session_manager.add_message(session_id, "assistant", confirm)
                    return

        # ── Detect new Type A apply intent ───────────────────────────────
        if not _ta_state:
            _det_svc = detect_service(clean_text)
            _ta_trigger = None
            if _det_svc in _WA_TYPE_A and is_apply_intent(clean_text):
                _ta_trigger = _det_svc
            elif is_apply_intent(clean_text) and current_flow.get("service") in _WA_TYPE_A:
                _ta_trigger = current_flow.get("service")
            if _ta_trigger:
                svc_info = _WA_TYPE_A[_ta_trigger]
                docs_text = "\n".join(f"  • {d}" for d in svc_info["documents"])
                info_msg = _md_to_wa(
                    f"*{svc_info['name']}*\n\n"
                    f"Apply via the official government portal:\n"
                    f"🌐 {svc_info['gov_url']}\n\n"
                    f"*Required Documents:*\n{docs_text}\n\n"
                    f"{svc_info.get('vfs_note', '')}\n\n"
                    f"*Steps:*\n"
                    f"1️⃣ Complete your application at {svc_info['gov_url']}\n"
                    f"2️⃣ Submit documents at VFS Global / Consulate\n"
                    f"3️⃣ Return here and send your *government reference number*\n"
                    f"   (Bot will record it and generate your application PDF)"
                )
                await _wa_send(phone, info_msg, db, "type_a_info", waba_number)
                await _type_a_save(db, session_id, service=_ta_trigger, state="awaiting_ref")
                await session_manager.add_message(session_id, "user", user_text)
                await session_manager.add_message(session_id, "assistant", info_msg)
                return

    # ── LOAD KNOWLEDGE BASE FOR CONTEXT (mirrors web bot exactly) ───────
    context_info    = ""
    scraped_summary = ""
    knowledge_base  = {}
    try:
        knowledge_base = await get_realtime_knowledge()

        # hybrid_search always runs — same as web bot (context_info goes to LLM)
        context_info = await hybrid_search(clean_text, knowledge_base)

        # Blocked keyword: reply with canned message and skip LLM entirely
        if context_info == BLOCKED_SENTINEL:
            _blocked_reply = "I'm sorry, I don't have information on that topic. For assistance please contact us directly:\n📞 +27 11-4828484 / +27 11 581 9800\n📧 ccom.jburg@mea.gov.in\n🏢 No. 1, Eton Road, Park Town, Johannesburg\n🕐 Mon–Fri 08:30–17:00"
            await session_manager.add_message(session_id, "user", user_text)
            await session_manager.add_message(session_id, "assistant", _blocked_reply)
            await _wa_send(phone, _blocked_reply, db, "idle", waba_number)
            return JSONResponse({"status": "ok"})

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
        raw_llm = await _llm_response(clean_text, session_id, llm_context, lang_code=_lang_code)
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

    elif step == "submitted":
        await _wa_send(phone, bot_text, db, step, wa)
        # Generate PDF and send via WhatsApp document + email
        await _wa_after_submit(phone, session_id, wa, db)

    elif step == "tracking":
        await _wa_send(phone, bot_text, db, step, wa)
        # Offer to resend PDF for this tracking ID if we can find it
        _tid_match = re.search(r'([A-Z]+-\d{8}-[A-Z0-9]+)', clean_text.upper())
        if _tid_match:
            _tid = _tid_match.group(1)
            await ics_waba.send_buttons(
                to=phone,
                body=f"Would you like to receive the PDF for *{_tid}*?",
                buttons=[{"id": f"pdf_{_tid}", "title": "Send PDF"}],
                from_override=wa,
            )

    elif step in ("idle", "escalated", "error", "complete"):
        await _wa_send(phone, bot_text, db, step, wa)

    elif step == "info_shown":
        await _wa_send(phone, bot_text, db, step, wa)
        # Show Apply / Ask a Question / My Applications buttons after service info
        _svc = current_flow.get("service") or detect_service(clean_text)
        if _svc and _svc in SERVICES:
            await ics_waba.send_buttons(
                to=phone,
                body=f"Would you like to apply for *{SERVICES[_svc]['name']}*?",
                buttons=[
                    {"id": f"apply_{_svc}", "title": "Apply Now"},
                    {"id": "ask_question",  "title": "Ask a Question"},
                    {"id": "main_menu",     "title": "Main Menu"},
                ],
                header="Next Steps",
                from_override=wa,
            )

    elif step == "docs_uploading":
        await _wa_send(phone, bot_text, db, step, wa)

    elif step == "collecting":
        await _wa_send(phone, bot_text, db, step, wa)

    else:
        await _wa_send(phone, bot_text, db, step, wa)

    # ── Handle "Send PDF" button reply for tracking queries ─────────────
    if selected_id and selected_id.startswith("pdf_"):
        _req_tid = selected_id[4:]
        _pdf = await _wa_generate_pdf(_req_tid, db)
        if _pdf and APP_BASE_URL:
            _pdf_url = f"{APP_BASE_URL}/api/ics-whatsapp/pdf/{_req_tid}"
            await ics_waba.send_media(
                to=phone,
                media_type="document",
                url=_pdf_url,
                caption=f"📄 Application PDF — {_req_tid}",
                filename=f"application_{_req_tid}.pdf",
                from_override=wa,
            )
        elif not APP_BASE_URL:
            await ics_waba.send_text(
                phone,
                "⚠️ PDF delivery is not configured on this server. "
                "Please contact the Consulate to request your application copy.",
                from_override=wa,
            )


# =====================================================================
# ENDPOINTS
# =====================================================================

@router.get("/pdf/{tracking_id}")
async def serve_application_pdf(tracking_id: str):
    """
    Serve the generated application PDF by tracking ID.
    Used by ICS WABA to deliver the document to WhatsApp users.
    Set APP_BASE_URL env var so the WhatsApp bot can construct this URL.
    """
    db        = await get_database()
    pdf_bytes = await _wa_generate_pdf(tracking_id, db)
    if not pdf_bytes:
        return Response(content="Application not found.", status_code=404, media_type="text/plain")
    safe     = tracking_id.upper().replace("/", "_")
    filename = f"application_{safe}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
