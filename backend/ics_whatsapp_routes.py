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

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import PlainTextResponse, JSONResponse, Response
from pydantic import BaseModel

import config
from database import get_database
from tenant import get_tenant_id
from services.messaging_channel_resolver import (
    resolve_company_from_channel,
    CHANNEL_ICS_WABA,
)
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
    CONTACT_INFO,
    process_flow,
    flow_suffix,
    get_flow_state,
    detect_service,
    detect_website_service,
    is_apply_intent,
    preload_flow_keywords,
    preload_service_patterns,
)
from services.service_registry import get_service, list_services
from services.bot_config import get_bot_config
# intent_classifier no longer drives chat — escalation + language-switch live
# in escalation_service / detect_target_language; deterministic FAQ replies
# come from the tenant's knowledge_base entries via the LLM context.


async def _wa_type_a_services(company_id: Optional[str]) -> dict:
    """Return the tenant's TYPE_A services keyed by service_key.

    Replaces the old hardcoded ``_WA_TYPE_A`` constant. Each value is a
    plain dict with ``name``, ``documents``, ``gov_url``, ``vfs_note``
    so call sites that did ``_WA_TYPE_A[key]["name"]`` keep working.
    """
    if not company_id:
        return {}
    services = await list_services(company_id)
    # Allowed categories are platform-config driven so super-admins can
    # opt TYPE_B services into the WhatsApp menu without code changes.
    try:
        from services import platform_config
        _allowed = {c.upper() for c in (platform_config.get(
            "whatsapp_visible_service_categories", ["TYPE_A"]) or [])}
    except Exception:
        _allowed = {"TYPE_A"}
    out: dict = {}
    for s in services:
        if (getattr(s, "category", "") or "").upper() not in _allowed:
            continue
        out[s.service_key] = {
            "name":      getattr(s, "name", "") or s.service_key.title(),
            "documents": list(getattr(s, "documents", []) or []),
            "gov_url":   getattr(s, "external_url", "") or "",
            "vfs_note":  getattr(s, "vfs_note", "") or "",
        }
    return out

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
# LANGUAGE SUPPORT
# The dicts below are *platform vocabulary* — display names + script
# hints for any language code we know about. Per-tenant filtering and
# overrides come from bot_config.supported_languages (see
# ``_tenant_language_vocab`` below). A tenant that lists, say, only
# English + Hindi gets a 2-row WhatsApp menu and "switch to Tamil" is
# silently ignored.
# =====================================================================
_DEFAULT_LANG_NAMES: dict[str, str] = {
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

_DEFAULT_LANG_SCRIPT_HINT: dict[str, str] = {
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

# Platform default ordered vocabulary used as a fallback when a tenant
# hasn't configured any ``supported_languages``. Each row is
# ``(english_name, lang_code, native_script_display)``.
_DEFAULT_LANGUAGE_LIST = [
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

async def _tenant_language_list(company_id: Optional[str]) -> list:
    """Resolve the ordered ``(english_name, lang_code, native_label)`` list
    for this tenant. Reads ``bot_config.supported_languages``; falls back to
    the platform default vocabulary when the tenant has nothing configured.
    """
    if company_id:
        try:
            from services.bot_config import get_bot_config
            cfg = await get_bot_config(company_id)
            rows = []
            for entry in (cfg.supported_languages or []):
                if not isinstance(entry, dict):
                    continue
                code = (entry.get("code") or "").strip().lower()
                if not code:
                    continue
                eng_name    = (entry.get("name") or "").strip() or _DEFAULT_LANG_NAMES.get(code, code.title())
                native_name = (entry.get("native_name") or "").strip() or eng_name
                rows.append((eng_name, code, native_name))
            if rows:
                return rows
        except Exception:
            pass
    return list(_DEFAULT_LANGUAGE_LIST)


async def _tenant_script_hint(code: str, company_id: Optional[str]) -> str:
    """Return the script-direction instruction for the given language code.

    Tenant-supplied ``supported_languages[].script_hint`` wins; platform
    defaults underneath cover the well-known Indic / Arabic scripts.
    """
    code = (code or "").lower()
    if company_id:
        try:
            from services.bot_config import get_bot_config
            cfg = await get_bot_config(company_id)
            for entry in (cfg.supported_languages or []):
                if isinstance(entry, dict) and entry.get("code") == code:
                    h = (entry.get("script_hint") or "").strip()
                    if h:
                        return h
        except Exception:
            pass
    return _DEFAULT_LANG_SCRIPT_HINT.get(code, "")


async def _tenant_lang_name(code: str, company_id: Optional[str]) -> str:
    """Return the display label for ``code``. Tenant override → platform default."""
    code = (code or "").lower()
    rows = await _tenant_language_list(company_id)
    for eng, c, _native in rows:
        if c == code:
            return eng
    return _DEFAULT_LANG_NAMES.get(code, "English")


async def _detect_language_input(text: str, company_id: Optional[str] = None):
    """
    Returns ``(english_name, lang_code)`` if ``text`` is a number in the
    tenant's menu range OR a language name (English / native / alias).
    Returns None on no match.
    """
    t = (text or "").strip()
    if not t:
        return None
    rows = await _tenant_language_list(company_id)
    # Number index → tenant menu (1-based).
    if t.isdigit():
        idx = int(t) - 1
        if 0 <= idx < len(rows):
            return rows[idx][0], rows[idx][1]
    # Name lookup — English label, native script, and operator-supplied aliases.
    tl = t.lower()
    for eng, code, native in rows:
        if tl == eng.lower():           return eng, code
        if t == native:                 return eng, code
        if tl == native.lower():        return eng, code
    # Aliases from bot_config (only consulted when we have a tenant).
    if company_id:
        try:
            from services.bot_config import get_bot_config
            cfg = await get_bot_config(company_id)
            for entry in (cfg.supported_languages or []):
                if not isinstance(entry, dict):
                    continue
                code = (entry.get("code") or "").lower()
                if not code:
                    continue
                for alias in (entry.get("aliases") or []):
                    if tl == str(alias).strip().lower():
                        # Resolve English label from the row we built earlier.
                        for eng, c, _n in rows:
                            if c == code:
                                return eng, code
        except Exception:
            pass
    return None


async def _wa_lang_instruction(code: str, company_id: Optional[str] = None) -> str:
    """Return the LANGUAGE system-prompt line for the given language code."""
    code = (code or "en").lower()
    name = await _tenant_lang_name(code, company_id)
    if code == "en":
        return "LANGUAGE: Respond in English."
    script_hint = await _tenant_script_hint(code, company_id)
    script_line = f" {script_hint}" if script_hint else ""
    return (
        f"LANGUAGE: The user has selected {name} as their preferred language. "
        f"You MUST respond entirely in {name}.{script_line} "
        f"Even if the user writes in English, always reply in {name}. "
        f"Proper nouns, addresses, phone numbers, email addresses, URLs, and "
        f"tracking IDs must remain unchanged (do not translate them)."
    )


async def _build_language_menu(company_id: Optional[str] = None) -> str:
    """Build the numbered WhatsApp language menu from the tenant's
    ``supported_languages``. Falls back to the platform default list when
    the tenant hasn't configured any."""
    rows = await _tenant_language_list(company_id)
    lines = [
        "🌐 *Choose your preferred language:*",
        "Reply with the number or type the language name.\n",
    ]
    for i, (eng, _code, native) in enumerate(rows):
        num = i + 1
        display = f"{native} ({eng})" if native and native != eng else eng
        lines.append(f"{num}. {display}")
    lines.append(
        "\n👉 You can also type your language name (e.g., \"Hindi\", \"Tamil\", \"Zulu\").\n"
        "\n⚙️ *Note:*\n"
        "If no language is selected, the default language will be English.\n"
        "Once selected, the entire conversation will continue in your chosen language."
    )
    return "\n".join(lines)

# Fallback greeting used only when a tenant hasn't configured one. Kept
# generic — every tenant should set ``fallback_responses.greeting`` on its
# bot_config (via the super-admin UI) to override.
_WA_GREETING_FALLBACK = (
    "Hello! 👋\n\n"
    "I'm here to help with your queries. "
    "Please type your question, or send *menu* to see what I can do."
)


async def _resolve_greeting(company_id: Optional[str]) -> str:
    """Resolve the WhatsApp greeting for this tenant.

    Reads ``fallback_responses.greeting`` from bot_config, rendering any
    ``{{var}}`` placeholders. Falls back to a neutral built-in if the tenant
    has not configured one. Active advisories are appended below the
    greeting (so admins can publish fraud alerts etc. without code changes).
    """
    if not company_id:
        return _WA_GREETING_FALLBACK
    cfg = await get_bot_config(company_id)
    greeting = cfg.fallback("greeting") or _WA_GREETING_FALLBACK
    parts = [greeting]
    for adv in (cfg.advisories or []):
        if not isinstance(adv, dict) or not adv.get("active", True):
            continue
        title = cfg.render(adv.get("title") or "")
        body  = cfg.render(adv.get("content") or "")
        if title or body:
            parts.append(f"\n*{title}*\n{body}".strip())
    return "\n\n".join(p for p in parts if p)


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
# WhatsApp char limits — platform-config knobs. The constants below are
# platform fallbacks; helpers resolve the live value at call time.
_WA_BODY_LIMIT   = 1024
_WA_MSG_LIMIT    = 4000


def _wa_body_limit() -> int:
    try:
        from services import platform_config
        return int(platform_config.get("whatsapp_body_char_limit", 1024))
    except Exception:
        return 1024


def _wa_msg_limit() -> int:
    try:
        from services import platform_config
        return int(platform_config.get("whatsapp_text_char_limit", 4000))
    except Exception:
        return 4000


def _wa_phrase_mappings() -> list:
    """Per-platform WhatsApp UI-phrase rewrite rules. Each rule is
    ``{"pattern": str, "replacement": str, "flags": "i"|""}`` — applied
    in order via :py:func:`re.sub`."""
    try:
        from services import platform_config
        rules = platform_config.get("whatsapp_ui_phrase_mappings", []) or []
        return rules if isinstance(rules, list) else []
    except Exception:
        return []

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
    # docs_pending: replace web-only "Preview PDF" button reference
    (r'Click \*\*?Preview PDF\*\*? to download an editable preview of your form\.', 'Reply *preview* to see your filled-in form summary.'),
    (r'  • To correct any field, type: `correct field name: new value`', 'To edit a field, tap *Edit Field* below or reply: *correct fieldname: new value*'),
    (r'\*\(e\.g\. `correct name:.*?`\)\*', ''),
]


def _strip_md_link(m: "re.Match") -> str:
    """[label](url) → bare url, or "label: url" when label adds information.

    WhatsApp has no markdown link rendering — a raw ``[text](url)`` reaches
    the user as literal brackets/parentheses. WhatsApp DOES auto-linkify a
    bare ``https://...`` URL, so unwrapping to plain text keeps it tappable.
    """
    label, url = m.group(1).strip(), m.group(2).strip()
    if not label or label.lower() == url.lower() or label.lower().startswith(("http://", "https://")):
        return url
    return f"{label}: {url}"


def _md_to_wa(text: str) -> str:
    """
    Convert a markdown bot response to WhatsApp-compatible text.
    Handles: **bold**, headings, tables, code blocks, lists, blockquotes, links.
    Also strips web-UI instructions and replaces them with WhatsApp equivalents.
    """
    # ── [label](url) → bare/labelled url — safety net in case the LLM emits
    # markdown link syntax despite the system-prompt instruction not to. Must
    # run before bold conversion so a label containing **text** doesn't confuse
    # the bold regex.
    text = re.sub(r'\[([^\]\n]+)\]\((https?://[^\s)]+)\)', _strip_md_link, text)

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
    # First the platform-default bundled rewrites, then any extra rules
    # admins supplied via platform_config.whatsapp_ui_phrase_mappings.
    for pattern, replacement in _WA_REPLACEMENTS:
        text = re.sub(pattern, replacement, text)
    for rule in _wa_phrase_mappings():
        try:
            pat   = rule.get("pattern", "")
            repl  = rule.get("replacement", "")
            flags = re.IGNORECASE if "i" in (rule.get("flags") or "").lower() else 0
            if pat:
                text = re.sub(pat, repl, text, flags=flags)
        except Exception:
            # A bad admin-supplied regex shouldn't break the chat path;
            # skip and continue.
            continue

    # ── Collapse 3+ blank lines → max 2 ──────────────────────────────
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def _split_wa(text: str, max_len: Optional[int] = None) -> list:
    """
    Split text into chunks ≤ max_len characters.
    Splits prefer paragraph (double-newline) boundaries, then single-newline,
    then hard-splits at max_len as a last resort.

    ``max_len`` falls back to the platform-config ``whatsapp_text_char_limit``
    (default 4000) when omitted, so super-admin tuning applies without
    chasing every call site.
    """
    if max_len is None:
        max_len = _wa_msg_limit()
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
    Truncate text to the WhatsApp interactive body limit (default 1024
    chars; tunable via platform_config.whatsapp_body_char_limit).
    Appends '…' if truncated.
    """
    limit = _wa_body_limit()
    if len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(' ', 1)[0] + '…'


# =====================================================================
# LLM WITH KNOWLEDGE CONTEXT
# =====================================================================
async def _llm_response(user_message: str, session_id: str, context: str = "", lang_code: str = "en", company_id: Optional[str] = None) -> str:
    if not LLM_AVAILABLE or not EMERGENT_LLM_KEY:
        return (
            "Thank you for your message. For detailed assistance please contact us directly "
            "using the contact details on our website."
        )

    _blocked_kws = await _get_blocked_keywords()

    # Build service-specific document hint (same as web bot)
    detected_svc_key = detect_service(user_message)
    tenant = company_id or config.COMPANY_ID
    detected_svc_obj = await get_service(tenant, detected_svc_key) if (detected_svc_key and tenant) else None
    svc_docs_hint = ""
    if detected_svc_obj:
        docs = "\n".join(f"  • {d}" for d in detected_svc_obj.documents)
        svc_docs_hint = f"\nDOCUMENTS REQUIRED FOR {detected_svc_obj.name.upper()}:\n{docs}\n"

    _clean_ctx      = filter_blocked_lines(context, _blocked_kws)
    _clean_hint     = filter_blocked_lines(svc_docs_hint, _blocked_kws)
    _prohibition    = blocked_prohibition(_blocked_kws)

    # Pull tenant bot identity from bot_config; do NOT hardcode a brand here.
    _cfg = await get_bot_config(tenant) if tenant else None
    _bot_name = (_cfg.bot_name if _cfg else "") or "Assistant"
    _tenant_prompt = _cfg.system_prompt() if _cfg else ""
    _lang_line = await _wa_lang_instruction(lang_code, company_id=tenant)

    # STABLE system message (per tenant+language) — no per-message data here, so
    # OpenAI prompt caching can hit the [system + history] prefix. The retrieved
    # OFFICIAL DATA + service-doc hint ride as ephemeral context on the user turn.
    system_prompt = f"""You are {_bot_name}, an automated assistant replying via WhatsApp.
{_tenant_prompt}
{_prohibition}
CRITICAL — DATA SOURCE RULE:
Answer ONLY using the OFFICIAL DATA provided with the user's message.
The data comes from admin-uploaded documents (FAQs, events, notices) and official sources.
Do NOT use general training knowledge. Do NOT invent or add information not in that data.
If the answer is not in the data, say so and direct the user to contact us directly.

{_lang_line}

RESPONSE STYLE:
- Be concise. Default to 3-5 short sentences.
- When the answer comes from a source, quote only the key facts, then add the source
  link on its own line as a bare URL (e.g. https://example.com/page) — WhatsApp
  auto-links plain URLs but does NOT render [text](url) markdown, so never wrap a
  link in brackets/parentheses. Prefer the URL given in any "(Source: ...)" tag in
  the official data below.
- Do NOT echo the user's question back.
- Do NOT add feedback/rating prompts or sign-off phrases.
- Use bullet points only when listing multiple items.
- Do NOT repeat information already shown in the conversation.
- Use *bold* for emphasis (WhatsApp format). Do NOT use markdown ** double-asterisks.
- Never ask for money or claim the organisation calls asking for payments.

IF NOT IN OFFICIAL DATA: Say "This information is not available in our current records. Please contact us directly using the contact details provided." """

    # Per-message material — sent this turn, never persisted to history.
    _dynamic_context = f"{_clean_hint}OFFICIAL DATA:\n{_clean_ctx}"

    # Resolve LLM model: env default → tenant company.llm_model override.
    _llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if tenant:
        _co = await (await get_database()).companies.find_one(
            {"id": tenant}, {"_id": 0, "llm_model": 1}
        )
        if _co and _co.get("llm_model"):
            _llm_model = _co["llm_model"]

    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=session_id,
            system_message=system_prompt,
        ).with_model("openai", _llm_model)
        response = await chat.send_message(
            UserMessage(text=user_message, context=_dynamic_context or None)
        )
    except Exception as exc:
        logger.error("LLM error: %s", exc)
        return (
            "I'm having trouble right now. Please try again shortly or contact us directly."
        )

    # Per-tenant cost logging from the real OpenAI usage (`tenant` resolved
    # above). Isolated so it never affects the reply.
    try:
        from services import llm_usage as _llm_usage
        await _llm_usage.log(tenant, chat.last_usage)
    except Exception:
        pass
    return response


# =====================================================================
# AUDIT LOG
# =====================================================================
async def _log_message(
    phone: str, direction: str, text: str, extra: dict, db,
    ics_mid: str = None, company_id: Optional[str] = None,
):
    """Persist one ICS WABA message row.

    `company_id` is set explicitly when the webhook caller passes it (after
    resolving via `resolve_company_from_channel`). When not provided —
    e.g. utility paths that don't have tenant context — falls back to the
    env-var default so every row still gets tagged.
    """
    doc = {
        "id":           str(uuid.uuid4()),
        "company_id":   company_id or config.COMPANY_ID,
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
async def _get_flow_safe(phone: str, company_id: Optional[str] = None) -> dict:
    """Get the current flow state for a phone number, safely handling errors.
    ``company_id`` scopes the session to the resolved tenant (else default)."""
    try:
        session = await session_manager.get_or_create_session(
            channel="whatsapp",
            user_identifier=phone,
            metadata={"company_id": company_id} if company_id else None,
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
def _normalize_phone(raw: str, waba_number: str = "", country_code: str = "") -> str:
    """
    Normalise an incoming customer number to digits-only E.164 (no leading +).

    Tenant-configurable: ``country_code`` is the tenant's ISD code (e.g.
    ``"27"`` for South Africa, ``"91"`` for India). When unset, it's derived
    from ``waba_number``'s leading 1–3 digits.

    Safe transforms:
      1. Strip leading '+' and punctuation/spaces.
      2. Local with leading 0     : ``0XXXXXXXXX`` → ``<cc>XXXXXXXXX``.
      3. Bare local (no '0', no cc): when total length ≤ 10 and ``cc`` set.
      4. Duplicate country code   : ``<cc><cc>XXXXXXXXXX`` → ``<cc>XXXXXXXXXX``.

    Known carrier quirk: some inbound gateways strip the first digit of an
    international number and re-prepend a *different* country code (we've
    seen ``91`` substituted for ``27``). If ``country_code`` is set and the
    incoming number starts with a *different* prefix that would yield a
    valid local number when swapped, swap it. Logged at INFO level.
    """
    phone = re.sub(r"[\s\-\(\)\.]+", "", (raw or "").strip().lstrip("+"))
    if not phone:
        return phone

    cc = re.sub(r"\D", "", (country_code or "").lstrip("+"))
    waba = re.sub(r"[\s\-\(\)\.]+", "", (waba_number or "").strip().lstrip("+"))
    # Derive country code from WABA number when not explicitly configured.
    if not cc and waba:
        # Most ISD codes are 1–3 digits; the safest cheap guess is the first 2.
        cc = waba[:2]

    # Carrier mangle: if a non-cc prefix yields a same-length number that
    # starts with our tenant cc, prefer the swapped form. (Defensive — only
    # applies when waba's cc matches the tenant's cc and the result is valid.)
    if cc and waba.startswith(cc) and not phone.startswith(cc):
        m = re.match(r"^(\d{2})(\d{10})$", phone)
        if m and cc != m.group(1):
            candidate = cc[:1] + m.group(2) if len(cc) == 2 else cc + m.group(2)
            if candidate.startswith(cc):
                logger.info("[PHONE NORM] CC-mangle corrected: %s → %s", phone, candidate)
                phone = candidate
                return phone

    # Duplicate country-code prefix.
    if cc and phone.startswith(cc * 2) and len(phone) > len(cc) + 9:
        phone = phone[len(cc):]

    # Local with leading 0 (10 digits total).
    if cc and re.match(r"^0\d{8,10}$", phone):
        phone = cc + phone[1:]
    # Bare local without leading 0 (8–10 digits, no cc yet).
    elif cc and len(phone) <= 10 and not phone.startswith(cc):
        phone = cc + phone
    return phone


# =====================================================================
# APPLICATION FLOW — WHATSAPP HELPERS
# =====================================================================
APP_BASE_URL = os.environ.get("APP_BASE_URL", "").rstrip("/")

_SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
_SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
_SMTP_USER = os.environ.get("SMTP_USER", "")
_SMTP_PASS = os.environ.get("SMTP_PASSWORD", "")

# Type A services come from ``tenant_services`` (category == "TYPE_A") via
# ``_wa_type_a_services(company_id)``. No hardcoded catalogue lives here —
# every tenant supplies its own service rows through the super-admin UI.

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

# Ordered service key list that matches _wa_services_menu() display order:
# Type A first (passport, visa, pcc), then Type B (oci, marriage, …)
# Used by the numbered-reply fallback so "4" = OCI, not pcc.
# Per-tenant cache of menu ordering: ``{company_id: [service_key, ...]}``.
# Order matches what ``_wa_services_menu()`` shows the user — Type A first.
_WA_MENU_SVCKEYS: dict[str, list] = {}


async def _wa_generate_pdf(
    tracking_id: str,
    db,
    company_id: Optional[str] = None,
) -> Optional[bytes]:
    """Generate PDF bytes for a submitted application.

    ``company_id`` scopes the lookup so tracking IDs from one tenant cannot
    be downloaded by another. Legacy callers (``None``) get the old global
    behaviour but log a warning — every new caller should thread the tenant.
    """
    try:
        from services.pdf_service import generate_application_pdf
        query: Dict[str, Any] = {"tracking_id": tracking_id.upper()}
        if company_id:
            query["company_id"] = company_id
        else:
            logger.warning(
                "[_wa_generate_pdf] called without company_id (tracking_id=%s) — "
                "falling back to global lookup; caller should pass tenant",
                tracking_id,
            )
        app = await db.applications.find_one(query, {"_id": 0})
        if not app:
            return None
        # service_name is denormalised onto the application at creation time
        # (see services.application_flow._create_application) so we don't need
        # to load the Service definition here.
        service_name = app.get("service_name") or app.get("service", "Application").title()
        uploaded_docs = [
            {"name": d.get("name", "Document"), "status": d.get("status", "uploaded")}
            for d in app.get("documents", [])
        ]
        _co_id = app.get("company_id") or ""
        _cfg = await get_bot_config(_co_id) if _co_id else None
        _org_name = (_cfg.org_name or _cfg.bot_name) if _cfg else ""
        _branding = dict(_cfg.pdf_branding or {}) if _cfg else {}
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: generate_application_pdf(
                service_name=service_name,
                form_data=app.get("form_data", {}),
                tracking_id=tracking_id.upper(),
                uploaded_docs=uploaded_docs,
                org_name=_org_name,
                branding=_branding,
            ),
        )
    except Exception as exc:
        logger.error("[WA PDF] Generation failed %s: %s", tracking_id, exc)
        return None


def _smtp_send(to_email: str, service_name: str, tracking_id: str, pdf_bytes: bytes, brand: str = ""):
    """Synchronous SMTP helper — run in executor. ``brand`` is the tenant's
    bot/org name; pass an empty string for an unbranded outbound message."""
    if not _SMTP_USER or not _SMTP_PASS:
        logger.warning("[WA EMAIL] SMTP not configured — skipping email for %s", tracking_id)
        return
    safe   = service_name.lower().replace(" ", "_")
    fname  = f"application_{safe}_{tracking_id}.pdf"
    msg    = MIMEMultipart()
    msg["From"]    = _SMTP_USER
    msg["To"]      = to_email
    label = (brand or "Application").strip()
    msg["Subject"] = f"{label} — {service_name} ({tracking_id})"
    body = (
        f"<html><body style='font-family:Arial,sans-serif'>"
        f"<h2 style='color:#000080'>{label} — Application Submitted</h2>"
        f"<p>Your <strong>{service_name}</strong> application has been received.</p>"
        f"<table style='border-collapse:collapse'>"
        f"<tr><td style='padding:6px 12px;border:1px solid #ddd'><strong>Tracking ID</strong></td>"
        f"<td style='padding:6px 12px;border:1px solid #ddd'><code>{tracking_id}</code></td></tr>"
        f"<tr><td style='padding:6px 12px;border:1px solid #ddd'><strong>Service</strong></td>"
        f"<td style='padding:6px 12px;border:1px solid #ddd'>{service_name}</td></tr>"
        f"</table>"
        f"<p>Your application PDF is attached. Keep it for your records.</p>"
        f"<p style='color:#666;font-size:12px'>{label}</p>"
        f"</body></html>"
    )
    msg.attach(MIMEText(body, "html"))
    part = MIMEBase("application", "octet-stream")
    part.set_payload(pdf_bytes)
    _email_encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
    msg.attach(part)
    try:
        import ssl as _ssl
        if _SMTP_PORT == 465:
            _ctx = _ssl.create_default_context()
            _srv_cm = smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, context=_ctx)
        else:
            _srv_cm = smtplib.SMTP(_SMTP_HOST, _SMTP_PORT)
        with _srv_cm as srv:
            srv.ehlo()
            if _SMTP_PORT != 465:
                srv.starttls()
            srv.login(_SMTP_USER, _SMTP_PASS)
            srv.send_message(msg)
        logger.info("[WA EMAIL] PDF sent to %s for %s", to_email, tracking_id)
    except Exception as exc:
        logger.error("[WA EMAIL] Failed → %s: %s", to_email, exc)


async def _wa_after_submit(
    phone: str,
    session_id: str,
    waba_number: str,
    db,
    company_id: Optional[str] = None,
):
    """
    Called right after process_flow() returns step='submitted'.
    Finds the application, generates PDF, sends it via WhatsApp document
    and emails it to the applicant. ``company_id`` scopes the lookup so a
    user on one tenant cannot pull another tenant's most-recent submission.
    """
    try:
        base_q: Dict[str, Any] = {"user_id": phone, "status": "submitted"}
        if company_id:
            base_q["company_id"] = company_id
        app = await db.applications.find_one(
            base_q,
            {"_id": 0},
            sort=[("submitted_at", -1)],
        )
        if not app:
            fallback_q: Dict[str, Any] = {"session_id": session_id, "status": "submitted"}
            if company_id:
                fallback_q["company_id"] = company_id
            app = await db.applications.find_one(
                fallback_q,
                {"_id": 0},
                sort=[("submitted_at", -1)],
            )
        if not app:
            return

        tracking_id  = app.get("tracking_id", "")
        service_name = app.get("service_name") or app.get("service", "").title()
        to_email     = app.get("form_data", {}).get("email", "")

        pdf_bytes = await _wa_generate_pdf(tracking_id, db, company_id=company_id or app.get("company_id"))
        if not pdf_bytes:
            return

        # Send PDF as WhatsApp document if public URL is configured
        if APP_BASE_URL:
            safe  = (service_name or "application").lower().replace(" ", "_")
            fname = f"application_{safe}_{tracking_id}.pdf"
            # Include tenant in the URL so /pdf/{tracking_id} can validate.
            _co = company_id or app.get("company_id") or ""
            pdf_url = f"{APP_BASE_URL}/api/ics-whatsapp/pdf/{tracking_id}"
            if _co:
                pdf_url += f"?company_id={_co}"
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
            _co_id = app.get("company_id") or ""
            _brand = ""
            if _co_id:
                _bc = await get_bot_config(_co_id)
                _brand = _bc.bot_name or _bc.org_name or ""
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, _smtp_send, to_email, service_name, tracking_id, pdf_bytes, _brand,
            )
            await ics_waba.send_text(
                phone,
                f"📧 A copy has also been emailed to *{to_email}*.",
                from_override=waba_number,
            )
    except Exception as exc:
        logger.error("[WA AFTER SUBMIT] phone=%s: %s", phone, exc)


async def _wa_my_applications(phone: str, db, company_id: Optional[str] = None) -> str:
    """Return a formatted summary of the user's recent applications, scoped
    to the calling tenant so the same phone number across two tenants can't
    leak applications between them."""
    query: Dict[str, Any] = {"user_id": phone}
    if company_id:
        query["company_id"] = company_id
    apps = await db.applications.find(
        query,
        {"_id": 0, "tracking_id": 1, "service_name": 1, "status": 1, "created_at": 1},
        sort=[("created_at", -1)],
    ).limit(5).to_list(5)

    if not apps:
        return (
            "You have no applications on record.\n\n"
            "Type the name of the service you need to get started."
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
# TYPE B — WHATSAPP REVIEW / EDIT HELPERS
# =====================================================================

async def _wa_field_review(company_id: str, service_key: str, data: dict) -> str:
    """Return a numbered field-by-field summary of the collected form data."""
    svc = await get_service(company_id, service_key)
    if not svc:
        return "📋 *Application Review unavailable — service definition missing.*"
    lines = [f"📋 *Your {svc.name} Application — Review*\n"]
    for i, f in enumerate(svc.fields):
        val = data.get(f["key"], "—")
        label = f["key"].replace("_", " ").title()
        lines.append(f"{i + 1}. *{label}:* {val}")
    lines.append("\n_Tap *Edit Field* to correct any entry before submitting._")
    return "\n".join(lines)


async def _wa_edit_get(db, session_id: str) -> str:
    s = await db.chat_sessions.find_one({"id": session_id}, {"metadata.wa_edit": 1})
    return (s or {}).get("metadata", {}).get("wa_edit", "")


async def _wa_edit_set(db, session_id: str, value: str):
    await db.chat_sessions.update_one(
        {"id": session_id}, {"$set": {"metadata.wa_edit": value}}
    )


async def _wa_edit_clear(db, session_id: str):
    await db.chat_sessions.update_one(
        {"id": session_id}, {"$unset": {"metadata.wa_edit": ""}}
    )


async def _wa_save_on_timeout(db, session_id: str):
    """
    Persist any in-progress application data to the DB before session reset,
    so partial work is not silently lost on a 10-minute timeout.

    Type B — existing application record is updated with status='timeout'.
    Type A — partial data is inserted as a new record with status='timeout'.
    """
    now = datetime.now(timezone.utc).isoformat()

    # ── Type B: update existing in-progress application record ──────────
    try:
        from services.application_flow import _get_flow as _af_get_flow
        flow    = await _af_get_flow(session_id)
        app_id  = flow.get("application_id")
        state   = flow.get("state", "idle")
        if app_id and state not in ("idle", "submitted"):
            await db.applications.update_one(
                {"id": app_id},
                {"$set": {
                    "status":       "timeout",
                    "form_data":    flow.get("data", {}),
                    "documents":    flow.get("uploaded_docs", []),
                    "last_state":   state,
                    "abandoned_at": now,
                    "updated_at":   now,
                }},
            )
            logger.info(
                "[WA TIMEOUT] Saved Type-B app %s state=%s as timeout", app_id, state
            )
    except Exception as exc:
        logger.error("[WA TIMEOUT] Failed to save Type-B app: %s", exc)

    # ── Type A: insert partial collected data if any ─────────────────────
    try:
        sess = await db.chat_sessions.find_one(
            {"id": session_id}, {"metadata.wa_type_a": 1}
        )
        ta = (sess or {}).get("metadata", {}).get("wa_type_a", {})
        if ta and ta.get("state") and ta.get("service"):
            svc_key  = ta["service"]
            # Best-effort name lookup; falls back to the key if the tenant
            # row was edited/removed between the start and timeout.
            sess_co_id = (sess or {}).get("metadata", {}).get("company_id") \
                         or (sess or {}).get("company_id") or ""
            svc_meta = (await _wa_type_a_services(sess_co_id)).get(svc_key, {}) if sess_co_id else {}
            form_data = {
                "full_name":            ta.get("full_name", ""),
                "email":                ta.get("email", ""),
                "gov_reference_number": ta.get("gov_reference", ""),
            }
            if any(form_data.values()):
                new_id     = str(uuid.uuid4())
                new_tid    = (
                    f"{svc_key.upper()}-"
                    f"{datetime.now(timezone.utc).strftime('%Y%m%d')}-"
                    f"{new_id[:6].upper()}-TIMEOUT"
                )
                await db.applications.insert_one({
                    "id":           new_id,
                    "tracking_id":  new_tid,
                    "session_id":   session_id,
                    "service":      svc_key,
                    "service_name": svc_meta.get("name", svc_key.title()),
                    "category":     "TYPE_A",
                    "status":       "timeout",
                    "form_data":    form_data,
                    "last_state":   ta.get("state", ""),
                    "abandoned_at": now,
                    "created_at":   now,
                    "updated_at":   now,
                })
                logger.info(
                    "[WA TIMEOUT] Saved Type-A partial app %s as timeout", new_tid
                )
    except Exception as exc:
        logger.error("[WA TIMEOUT] Failed to save Type-A partial app: %s", exc)


async def _wa_reset_session(db, session_id: str):
    """
    Destroy all active conversation state after a 10-minute idle timeout.
    Saves any in-progress application data first, then clears:
    application flow, Type-A state, edit state, lang-pending flag,
    and the greeted flag (so the next interaction is treated as brand-new).
    Language preference is intentionally preserved.
    """
    await _wa_save_on_timeout(db, session_id)
    from services.application_flow import _clear_flow as _af_clear_flow
    await _af_clear_flow(session_id)
    await db.chat_sessions.update_one(
        {"id": session_id},
        {
            "$set":   {"metadata.greeted": False, "metadata.lang_pending": False},
            "$unset": {"metadata.wa_type_a": "", "metadata.wa_edit": ""},
        },
    )


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
    svc_key      = ta.get("service") or ""
    # Look up the tenant's service row to source name + required docs.
    sess = await db.chat_sessions.find_one({"id": session_id}, {"company_id": 1, "metadata.company_id": 1})
    co_id = (sess or {}).get("company_id") or (sess or {}).get("metadata", {}).get("company_id") or ""
    svc          = (await _wa_type_a_services(co_id)).get(svc_key, {}) if co_id else {}
    service_name = svc.get("name") or (svc_key.title() if svc_key else "Application")
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
    _cfg_pdf = await get_bot_config(co_id) if co_id else None
    _pdf_org = (_cfg_pdf.org_name or _cfg_pdf.bot_name) if _cfg_pdf else ""
    _pdf_branding = dict(_cfg_pdf.pdf_branding or {}) if _cfg_pdf else {}
    loop = asyncio.get_event_loop()
    try:
        pdf_bytes = await loop.run_in_executor(
            None,
            lambda: generate_application_pdf(
                service_name=service_name,
                form_data=form_data,
                tracking_id=tracking_id,
                uploaded_docs=doc_list,
                org_name=_pdf_org,
                branding=_pdf_branding,
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
                _brand2 = ""
                if co_id:
                    _bc2 = await get_bot_config(co_id)
                    _brand2 = _bc2.bot_name or _bc2.org_name or ""
                loop2 = asyncio.get_event_loop()
                await loop2.run_in_executor(
                    None, _smtp_send, form_data["email"], service_name, tracking_id, pdf_bytes, _brand2,
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


async def _wa_services_menu(company_id: str) -> str:
    """Build the WhatsApp services menu from this tenant's service rows."""
    cfg = await get_bot_config(company_id) if company_id else None
    title = (cfg.bot_name if cfg else "") or "Services"
    type_a = await _wa_type_a_services(company_id)
    type_b_services = [
        s for s in await list_services(company_id)
        if s.service_key not in type_a
    ]

    lines: list[str] = [f"🏛️ *{title}*\n", "─────────────────────────────"]
    num = 1
    if type_a:
        lines += [
            "🌐 *Apply via Government Portal*",
            "_(Bot records your reference number & generates PDF)_\n",
        ]
        for _key, svc in type_a.items():
            gov = svc.get("gov_url") or ""
            line = f"{num}. *{svc['name']}*"
            if gov:
                line += f"\n   🔗 {gov}"
            lines.append(line)
            num += 1
        lines.append("")
    if type_b_services:
        lines += [
            "─────────────────────────────",
            "📝 *Fill the Form in this Chat*",
            "_(Complete and submit without leaving WhatsApp)_\n",
        ]
        for svc in type_b_services:
            lines.append(f"{num}. *{svc.name}*")
            num += 1
        lines.append("")

    lines.append(
        "─────────────────────────────\n"
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
    company_id: Optional[str] = None,
):
    """Core bot handler — delegates to the shared process_flow() state machine.

    `company_id` is the tenant that owns this inbound channel, resolved at
    the webhook entry point. When None (legacy callers), `_log_message`'s
    own fallback to config.COMPANY_ID kicks in — but new code should pass it.
    """

    # Preload tenant flow keywords so the sync apply/yes/no helpers
    # downstream pick up per-tenant overrides from bot_config.
    await preload_flow_keywords(company_id)
    await preload_service_patterns(company_id)

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
    _current_flow = await _get_flow_safe(phone, company_id)

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
        metadata={"waba_number": waba_number, "company_id": company_id},
    )
    session_id         = session["id"]
    _meta              = session.get("metadata", {})
    _lang_pending_flag = _meta.get("lang_pending", False)
    _lang_code         = _meta.get("language", "en")
    _lang_name         = _meta.get("language_name", "English")

    # ── SESSION TIMEOUT: destroy state after 10 min idle ─────────────
    # Applies only to sessions that were previously active (greeted=True).
    # Any message after timeout gets a fresh session — greeting + language menu.
    _was_greeted  = _meta.get("greeted", False)
    _last_activity = session.get("last_activity", "")
    if _was_greeted and _last_activity:
        try:
            _idle_seconds = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(_last_activity.replace("Z", "+00:00"))
            ).total_seconds()
            if _idle_seconds > 600:
                await _wa_reset_session(db, session_id)
                await _log_message(
                    phone, "system", "[session reset — idle timeout]",
                    {"step": "timeout_reset", "idle_seconds": int(_idle_seconds)}, db,
                )
                _greeting = await _resolve_greeting(company_id)
                _menu = await _build_language_menu(company_id)
                await ics_waba.send_text(phone, _greeting, from_override=waba_number)
                await ics_waba.send_text(phone, _menu, from_override=waba_number)
                await _set_lang_pending(db, session_id)
                return
        except Exception:
            pass

    # ── Active form state check — used to protect language and menu detection ──
    _form_active = _current_flow.get("state") in _FORM_ACTIVE_STATES

    # ── GLOBAL COMMANDS — works from any non-form state ─────────────────
    if not _form_active and not selected_id:
        _t_lower = clean_text.strip().lower()
        if _t_lower in _MY_APPS_WORDS:
            apps_msg = await _wa_my_applications(phone, db, company_id=company_id)
            await _wa_send(phone, apps_msg, db, "my_apps", waba_number)
            await session_manager.add_message(session_id, "user", user_text)
            await session_manager.add_message(session_id, "assistant", apps_msg)
            return
        if _t_lower in _SERVICES_MENU_WORDS:
            menu_msg = await _wa_services_menu(company_id or config.COMPANY_ID)
            await _wa_send(phone, menu_msg, db, "services_menu", waba_number)
            await session_manager.add_message(session_id, "user", user_text)
            await session_manager.add_message(session_id, "assistant", menu_msg)
            return

    # ── LANGUAGE SELECTION — skip during active form filling ────────────────
    # During lang_pending: numbers 1-42 AND typed names are treated as language picks.
    # At any other time: only a bare typed language name switches the language.
    if _lang_pending_flag and not _form_active:
        lang_result = await _detect_language_input(clean_text, company_id=company_id)
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
        # Strip trailing punctuation so "change language?" / "language ?" work the same as without
        _t = clean_text.strip().lower().rstrip("?!. ")

        # "language" / "change language" keywords → show language menu to re-select
        _LANG_MENU_TRIGGERS = {
            "language", "change language", "languages", "select language",
            "choose language", "switch language", "भाषा", "langue", "lugha",
        }
        if _t in _LANG_MENU_TRIGGERS:
            _menu = await _build_language_menu(company_id)
            await ics_waba.send_text(phone, _menu, from_override=waba_number)
            await _log_message(phone, "outbound", _menu, {"step": "lang_menu"}, db)
            await _set_lang_pending(db, session_id)
            await session_manager.add_message(session_id, "user", user_text)
            return

        # Bare typed language name → confirm switch then show menu for re-selection.
        # Tenant-scoped detection rejects names that aren't in the tenant's
        # supported_languages, so a user can't accidentally switch into a
        # language the tenant doesn't serve.
        _name_match = await _detect_language_input(_t, company_id=company_id)
        if not _name_match:
            _name_match = await _detect_language_input(clean_text.strip(), company_id=company_id)
        if _name_match:
            eng_name, code = _name_match
            await _set_session_language(db, session_id, eng_name, code)
            _lang_name, _lang_code = eng_name, code
            confirm_msg = f"✅ Language switched to *{eng_name}*. I'll continue all responses in {eng_name}. 🙏"
            await _wa_send(phone, confirm_msg, db, "lang_set", waba_number)
            await session_manager.add_message(session_id, "user", user_text)
            await session_manager.add_message(session_id, "assistant", confirm_msg)
            # Show menu again so user can change their mind
            _menu = await _build_language_menu(company_id)
            await ics_waba.send_text(phone, _menu, from_override=waba_number)
            await _log_message(phone, "outbound", _menu, {"step": "lang_menu"}, db)
            await _set_lang_pending(db, session_id)
            return

    # ── Numbered reply fallback (when interactive messages unsupported) ─
    # Context-aware: interpretation depends on current flow state.
    # Build the ordered key list that matches _wa_services_menu() per tenant:
    #   Type A first, then Type B — same order the user sees.
    _menu_tenant = company_id or config.COMPANY_ID or ""
    if _menu_tenant not in _WA_MENU_SVCKEYS:
        _tenant_type_a = await _wa_type_a_services(_menu_tenant)
        _all_services  = await list_services(_menu_tenant) if _menu_tenant else []
        _WA_MENU_SVCKEYS[_menu_tenant] = list(_tenant_type_a.keys()) + [
            s.service_key for s in _all_services if s.service_key not in _tenant_type_a
        ]
    _menu_svckeys = _WA_MENU_SVCKEYS.get(_menu_tenant, [])

    # Pre-load wa_edit state for docs_pending so the numbered fallback below can
    # distinguish "field-selecting" mode (numbers = field indices) from normal mode
    # (numbers = Submit / Edit / Cancel).
    _wa_edit_early = ""
    if _current_flow.get("state") == "docs_pending":
        _wa_edit_early = await _wa_edit_get(db, session_id)

    if not selected_id and clean_text.strip().isdigit():
        user_choice = int(clean_text.strip())

        # info_shown → secondary menu: 1=Apply Now, 2=Ask Question, 3=Main Menu
        if _current_flow.get("state") == "info_shown" and _current_flow.get("service"):
            if user_choice == 1:
                selected_id = f"apply_{_current_flow.get('service')}"
            elif user_choice == 2:
                selected_id = "ask_question"
            elif user_choice == 3:
                selected_id = "main_menu"
        # consent_pending → 1=Yes, 2=No
        elif _current_flow.get("state") == "consent_pending":
            if user_choice == 1:
                selected_id = "consent_yes"
            elif user_choice == 2:
                selected_id = "consent_no"
        # docs_pending → 1=Submit, 2=Edit Field, 3=Cancel
        # UNLESS we're in field-selecting mode, where numbers are field indices
        # and must fall through to the docs_pending handler unchanged.
        elif _current_flow.get("state") == "docs_pending" and _wa_edit_early != "selecting":
            if user_choice == 1:
                selected_id = "btn_submit"
            elif user_choice == 2:
                selected_id = "wa_edit"
            elif user_choice == 3:
                selected_id = "btn_cancel"
        # paused → 1=Continue, 2=Cancel
        elif _current_flow.get("state") == "paused":
            if user_choice == 1:
                selected_id = "consent_yes"   # maps to "continue"
            elif user_choice == 2:
                selected_id = "btn_cancel"
        # Default: main service menu (idle / new user types "4" for OCI, etc.)
        else:
            n = user_choice - 1
            if 0 <= n < len(_menu_svckeys):
                selected_id = _menu_svckeys[n]

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
            _tenant_type_a = await _wa_type_a_services(_menu_tenant)
            if _svc_key in _tenant_type_a:
                # Type A service — will be intercepted by state machine below
                clean_text = f"apply {_svc_key}"
            else:
                clean_text = f"apply {_svc_key}"
                # Pre-set the service in the flow so process_flow() picks it up even from idle state
                _pre_session = await session_manager.get_or_create_session(
                    channel="whatsapp", user_identifier=phone,
                    metadata={"waba_number": waba_number, "company_id": company_id},
                )
                from services.application_flow import _get_flow, _save_flow
                _pre_flow = await _get_flow(_pre_session["id"])
                if await get_service(company_id or config.COMPANY_ID, _svc_key):
                    _pre_flow["state"]   = "info_shown"
                    _pre_flow["service"] = _svc_key
                    await _save_flow(_pre_session["id"], _pre_flow)
        elif await get_service(company_id or config.COMPANY_ID, selected_id):
            clean_text = f"apply {selected_id}"

    # ── SHOW MAIN MENU ────────────────────────────────────────────────
    # Shown for: first message (new session) or greeting words.
    # 10-min idle is handled early above — by the time we reach here the
    # session has already been reset and control returned to the caller.
    current_flow = await get_flow_state(session_id)

    _MENU_WORDS = {"menu", "hi", "hello", "start", "help", "/start", "hey", "namaste", "hola"}
    _is_new_session   = not _meta.get("greeted", False)
    _is_greeting_word = clean_text.lower().strip() in _MENU_WORDS

    is_menu_trigger = _is_new_session or _is_greeting_word

    if is_menu_trigger and not selected_id:
        _greeting = await _resolve_greeting(company_id)
        _menu = await _build_language_menu(company_id)
        await ics_waba.send_text(phone, _greeting, from_override=waba_number)
        await _log_message(phone, "outbound", _greeting, {"step": "greeting"}, db)
        await ics_waba.send_text(phone, _menu, from_override=waba_number)
        await _log_message(phone, "outbound", _menu, {"step": "lang_menu"}, db)
        await _set_lang_pending(db, session_id)
        return

    # ── SERVICE SELECTED FROM LIST — show info card + apply buttons ───
    _selected_svc = await get_service(company_id or config.COMPANY_ID, selected_id) if selected_id else None
    if _selected_svc:
        docs_text = "\n".join(f"  • {d}" for d in _selected_svc.documents)
        info_text = _md_to_wa(
            f"*{_selected_svc.name}*\n\n"
            f"{_selected_svc.description}\n\n"
            f"*Required documents:*\n{docs_text}"
        )
        # Save info_shown + service so "Apply Now" works correctly
        from services.application_flow import _get_flow, _save_flow
        _flow = await _get_flow(session_id)
        _flow["state"]   = "info_shown"
        _flow["service"] = selected_id
        await _save_flow(session_id, _flow)

        await _wa_send(phone, info_text, db, "info_shown", waba_number)
        await session_manager.add_message(session_id, "user", user_text)
        await session_manager.add_message(session_id, "assistant", info_text)
        # Always follow with Apply Now / Ask a Question / Main Menu buttons
        await ics_waba.send_buttons(
            to=phone,
            body=f"Would you like to apply for *{_selected_svc.name}*?",
            buttons=[
                {"id": f"apply_{selected_id}", "title": "Apply Now"},
                {"id": "ask_question",          "title": "Ask a Question"},
                {"id": "main_menu",             "title": "Main Menu"},
            ],
            header="Next Steps",
            from_override=waba_number,
        )
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
            _ta_svc  = _ta.get("service") or ""
            _tenant_type_a = await _wa_type_a_services(_menu_tenant)
            _ta_name = _tenant_type_a.get(_ta_svc, {}).get("name") or (_ta_svc.title() if _ta_svc else "Application")

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
                        f"Your PDF summary has been sent. We will be in touch with you."
                    )
                    await _wa_send(phone, confirm, db, "type_a_submitted", waba_number)
                    await session_manager.add_message(session_id, "user", user_text)
                    await session_manager.add_message(session_id, "assistant", confirm)
                    return

        # ── Detect new Type A apply intent ───────────────────────────────
        if not _ta_state:
            _det_svc = detect_service(clean_text)
            _ta_trigger = None
            _tenant_type_a = await _wa_type_a_services(_menu_tenant)
            if _det_svc in _tenant_type_a and is_apply_intent(clean_text):
                _ta_trigger = _det_svc
            elif is_apply_intent(clean_text) and current_flow.get("service") in _tenant_type_a:
                _ta_trigger = current_flow.get("service")
            if _ta_trigger:
                svc_info = _tenant_type_a[_ta_trigger]
                docs_text = "\n".join(f"  • {d}" for d in svc_info.get("documents", []))
                gov_url   = svc_info.get("gov_url") or ""
                vfs_note  = svc_info.get("vfs_note") or ""
                apply_line  = f"🌐 {gov_url}\n\n" if gov_url else ""
                step1_text  = f"at {gov_url}" if gov_url else "at the official portal"
                info_msg = _md_to_wa(
                    f"*{svc_info['name']}*\n\n"
                    f"Apply via the official portal:\n"
                    f"{apply_line}"
                    f"*Required Documents:*\n{docs_text}\n\n"
                    f"{vfs_note + chr(10) + chr(10) if vfs_note else ''}"
                    f"*Steps:*\n"
                    f"1️⃣ Complete your application {step1_text}\n"
                    f"2️⃣ Submit any required documents at the official submission centre\n"
                    f"3️⃣ Return here and send your *government reference number*\n"
                    f"   (Bot will record it and generate your application PDF)"
                )
                await _wa_send(phone, info_msg, db, "type_a_info", waba_number)
                await _type_a_save(db, session_id, service=_ta_trigger, state="awaiting_ref")
                await session_manager.add_message(session_id, "user", user_text)
                await session_manager.add_message(session_id, "assistant", info_msg)
                return

    # ── TYPE B — WA EDIT / PREVIEW FLOW ─────────────────────────────────
    # Intercept edit-field and preview commands while in docs_pending state
    # so users can review and correct their form data before submitting.
    if current_flow.get("state") == "docs_pending":
        _eb_svc   = current_flow.get("service")
        _eb_data  = current_flow.get("data", {})
        _eb_svc_obj = await get_service(company_id or config.COMPANY_ID, _eb_svc) if _eb_svc else None
        _eb_fields = _eb_svc_obj.fields if _eb_svc_obj else []
        _wa_edit  = await _wa_edit_get(db, session_id)

        # "Edit Field" button tapped → show numbered field list
        if selected_id == "wa_edit":
            await _wa_edit_set(db, session_id, "selecting")
            _eb_name = _eb_svc_obj.name if _eb_svc_obj else "Application"
            lines = [f"✏️ *Edit a Field — {_eb_name}*\n"]
            for i, f in enumerate(_eb_fields):
                val   = _eb_data.get(f["key"], "—")
                label = f["key"].replace("_", " ").title()
                lines.append(f"{i + 1}. *{label}:* {val}")
            lines.append("\nReply with the *field number* to edit.")
            _edit_list = "\n".join(lines)
            await _wa_send(phone, _edit_list, db, "wa_edit_list", waba_number)
            await session_manager.add_message(session_id, "user", user_text)
            return

        # "Preview" button tapped or user typed "preview"
        if selected_id == "wa_preview" or clean_text.strip().lower() == "preview":
            _review_text = await _wa_field_review(company_id or config.COMPANY_ID, _eb_svc, _eb_data)
            _tid = current_flow.get("tracking_id", "")
            await _wa_send(phone, _review_text, db, "wa_preview", waba_number)
            await ics_waba.send_buttons(
                to=phone,
                body=f"🔖 Tracking ID: `{_tid}`\nReady to submit?",
                buttons=[
                    {"id": "btn_submit", "title": "Submit Application"},
                    {"id": "wa_edit",    "title": "Edit Field"},
                    {"id": "btn_cancel", "title": "Cancel"},
                ],
                header="Review & Submit",
                footer="Tap 'Edit Field' to correct any entry.",
                from_override=waba_number,
            )
            await session_manager.add_message(session_id, "user", user_text)
            return

        # Format hints shown below the current value when editing a field
        _EDIT_HINTS: dict = {
            "dob":            "Format: DD/MM/YYYY  (e.g. 26/07/1990)",
            "marriage_date":  "Format: DD/MM/YYYY",
            "travel_dates":   "Format: DD/MM/YYYY – DD/MM/YYYY  (e.g. 01/06/2026 – 20/06/2026)",
            "email":          "Format: name@example.com",
            "phone":          "Format: +27 72 641 3058",
            "passport_number":"e.g. A1234567  (Indian passport) or your foreign passport number",
            "indian_passport":"e.g. A1234567",
            "new_passport":   "e.g. your foreign passport number",
            "father_passport":"e.g. A1234567",
        }

        # User is in "selecting" mode — waiting for a field number
        if _wa_edit == "selecting" and clean_text.strip().isdigit():
            idx = int(clean_text.strip()) - 1
            if 0 <= idx < len(_eb_fields):
                fkey   = _eb_fields[idx]["key"]
                flabel = fkey.replace("_", " ").title()
                cur    = _eb_data.get(fkey, "—")
                hint   = _EDIT_HINTS.get(fkey, "")
                hint_line = f"\n_{hint}_" if hint else ""
                await _wa_edit_set(db, session_id, f"field_{fkey}")
                await _wa_send(
                    phone,
                    f"✏️ *Edit {flabel}*\n\nCurrent value: *{cur}*{hint_line}\n\nPlease send the new value:",
                    db, "wa_edit_field", waba_number,
                )
            else:
                await _wa_send(
                    phone,
                    f"Please reply with a number between 1 and {len(_eb_fields)}.",
                    db, "wa_edit", waba_number,
                )
            await session_manager.add_message(session_id, "user", user_text)
            return

        # User has sent the new value for a field
        if _wa_edit.startswith("field_"):
            fkey = _wa_edit[len("field_"):]
            await _wa_edit_clear(db, session_id)
            # Rewrite as a process_flow correction command
            clean_text = f"correct {fkey.replace('_', ' ')}: {clean_text.strip()}"
            # Fall through to process_flow with the correction command

    # ── LOAD KNOWLEDGE BASE FOR CONTEXT (mirrors web bot exactly) ───────
    context_info    = ""
    scraped_summary = ""
    knowledge_base  = {}
    try:
        knowledge_base = await get_realtime_knowledge(company_id)

        # hybrid_search always runs — same as web bot (context_info goes to LLM).
        # tenant_id is REQUIRED (the call previously omitted it and threw every
        # time, leaving WhatsApp answers ungrounded).
        context_info = await hybrid_search(clean_text, knowledge_base, company_id or config.COMPANY_ID)

        # Blocked keyword: reply with canned message and skip LLM entirely
        if context_info == BLOCKED_SENTINEL:
            _blocked_reply = "I'm sorry, I don't have information on that topic. For assistance please contact us directly using the contact details provided."
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
            cgi_text = knowledge_base.get("cgi_joburg", {}).get("page_content", "") or knowledge_base.get("main", {}).get("page_content", "")
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
        tenant_id=company_id or config.COMPANY_ID,
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
        # Use a language-scoped LLM session so history from a previous language
        # (e.g. Tamil) does not bleed into a newly selected language (e.g. Hindi).
        from services import response_cache as _rc
        from emergentintegrations.llm.chat import history_len as _hlen
        _wa_sess = f"{session_id}_{_lang_code}"
        _tenant = company_id or config.COMPANY_ID
        # Response cache (opt-in): serve a repeat FAQ with no LLM call. Restricted
        # to context-free opening questions — first turn in this language, idle
        # flow, no flow-supplied text, no media — so a cached answer can't depend
        # on prior conversation context. Key is (tenant, language, query).
        _cache_eligible = (
            _rc.enabled()
            and not has_doc
            and flow_response is None
            and step in (None, "idle")
            and current_flow.get("state", "idle") == "idle"
            and (await _hlen(_wa_sess)) == 0
        )
        from services import budget_guard as _bg
        raw_llm = await _rc.get(_tenant, _lang_code, clean_text) if _cache_eligible else None
        if raw_llm is None and await _bg.is_over_budget(_tenant):
            # Over the monthly cap → soft-decline with no LLM call. The cache
            # serve above still answers repeat FAQs (graceful degradation).
            raw_llm = _bg.exceeded_message()
        elif raw_llm is None:
            raw_llm = await _llm_response(
                clean_text, _wa_sess, llm_context,
                lang_code=_lang_code, company_id=_tenant,
            )
            if _cache_eligible and raw_llm:
                await _rc.put(_tenant, _lang_code, clean_text, raw_llm)
        # Append flow guidance suffix (same as web bot)
        suffix = await flow_suffix(
            step, detect_service(clean_text),
            tenant_id=company_id or config.COMPANY_ID, channel="whatsapp",
        )
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
        # Reload flow to get the latest data (process_flow may have just updated it)
        _dp_flow = await get_flow_state(session_id)
        _dp_svc  = _dp_flow.get("service")
        _dp_data = _dp_flow.get("data", {})
        _dp_tid  = _dp_flow.get("tracking_id", "")
        # Prepend numbered form-field review so user can see what they entered
        if _dp_svc and _dp_data:
            await _wa_send(
                phone,
                await _wa_field_review(company_id or config.COMPANY_ID, _dp_svc, _dp_data),
                db, "docs_pending_review", wa,
            )
        await _wa_send(phone, bot_text, db, step, wa)
        await ics_waba.send_buttons(
            to=phone,
            body=f"🔖 Tracking ID: `{_dp_tid}`\nReady to submit?",
            buttons=[
                {"id": "btn_submit", "title": "Submit Application"},
                {"id": "wa_edit",    "title": "Edit Field"},
                {"id": "btn_cancel", "title": "Cancel"},
            ],
            header="Review & Submit",
            footer="Tap 'Edit Field' to correct any entry.",
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
        await _wa_after_submit(phone, session_id, wa, db, company_id=company_id)

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
        # Prioritise service detected in the current message (handles auto-discard case
        # where current_flow still holds the old service); fall back to flow context.
        _svc = detect_service(clean_text) or current_flow.get("service")
        _svc_obj = await get_service(company_id or config.COMPANY_ID, _svc) if _svc else None
        if _svc_obj:
            await ics_waba.send_buttons(
                to=phone,
                body=f"Would you like to apply for *{_svc_obj.name}*?",
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
        _pdf = await _wa_generate_pdf(_req_tid, db, company_id=company_id)
        if _pdf and APP_BASE_URL:
            _pdf_url = f"{APP_BASE_URL}/api/ics-whatsapp/pdf/{_req_tid}"
            if company_id:
                _pdf_url += f"?company_id={company_id}"
            await ics_waba.send_media(
                to=phone,
                media_type="document",
                url=_pdf_url,
                caption=f"📄 Application PDF — {_req_tid}",
                filename=f"application_{_req_tid}.pdf",
                from_override=wa,
            )
        elif not APP_BASE_URL:
            # Pull a tenant-appropriate "contact support" hint instead of the
            # legacy CGI-specific "contact the Consulate". Falls back to a
            # neutral phrase when no email is configured.
            try:
                from services.bot_config import get_bot_config as _gbc
                _cfg = await _gbc(company_id or config.COMPANY_ID)
                _email = (_cfg.contact or {}).get("email") or ""
                _support = f"Please email {_email} for assistance." if _email else "Please contact support for assistance."
            except Exception:
                _support = "Please contact support for assistance."
            await ics_waba.send_text(
                phone,
                "⚠️ PDF delivery is not configured on this server. " + _support,
                from_override=wa,
            )


# =====================================================================
# ENDPOINTS
# =====================================================================

@router.get("/pdf/{tracking_id}")
async def serve_application_pdf(
    tracking_id: str,
    company_id: Optional[str] = Query(default=None),
):
    """
    Serve the generated application PDF by tracking ID.

    Used by ICS WABA to deliver the document to WhatsApp users. The bot
    constructs the URL with ``?company_id=<UUID>`` so tracking IDs from
    one tenant cannot be downloaded by another tenant; requests without
    the query param fall back to a global lookup (legacy behaviour) so
    in-flight links from before this change still work.
    Set APP_BASE_URL env var so the WhatsApp bot can construct this URL.
    """
    db        = await get_database()
    pdf_bytes = await _wa_generate_pdf(tracking_id, db, company_id=company_id)
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
        # Resolve tenant from the WABA number the user messaged TO. Resolver
        # is hardcoded today; this is the single-point swap for Sprint 5+.
        company_id = await resolve_company_from_channel(CHANNEL_ICS_WABA, waba_number)
        background_tasks.add_task(
            _handle_message, phone, waba_number, reply_type, raw_reply, db, company_id
        )
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
        company_id = await resolve_company_from_channel(CHANNEL_ICS_WABA, waba_number)
        background_tasks.add_task(
            _handle_message, phone, waba_number, reply_type, raw_reply, db, company_id
        )
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
        company_id = await resolve_company_from_channel(CHANNEL_ICS_WABA, req.waba_number or "")
        background_tasks.add_task(
            _handle_message, phone, req.waba_number or "", req.reply_type.upper(), req.message, db, company_id,
        )
        logger.info("simulate: phone=%s msg=%s", sanitize_logs(phone), sanitize_logs(req.message[:80]))
        return {"success": True, "phone": phone, "message": req.message}
    except Exception as exc:
        logger.error("simulate error: %s", exc)
        return {"success": False, "error": str(exc)}


@router.get("/conversations")
async def get_conversations(limit: int = 50, tenant_id: str = Depends(get_tenant_id)):
    """Get recent ICS WhatsApp conversations for admin view (tenant-scoped)."""
    db = await get_database()
    pipeline = [
        {"$match": {"company_id": tenant_id}},
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
async def get_messages(
    phone_number: str,
    limit: int = 50,
    tenant_id: str = Depends(get_tenant_id),
):
    """Get message history for a single conversation (tenant-scoped)."""
    db = await get_database()
    msgs = await db.ics_whatsapp_messages.find(
        {"company_id": tenant_id, "phone_number": phone_number}, {"_id": 0}
    ).sort("timestamp", 1).limit(limit).to_list(limit)
    return {"messages": msgs}
