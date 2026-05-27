"""
====================================================================
SEVA SETU BOT - APPLICATION FLOW STATE MACHINE
====================================================================
Flow:
  idle
    → info_shown          (LLM explains service + scraped website data)
    → consent_pending     (shows docs required, asks yes/no)
    → collecting          (step-by-step form fields)
    → docs_uploading      (upload each required document one by one)
    → docs_pending        (all docs processed, confirm submit)
    → submitted           (application saved to DB with tracking ID)

Mid-flow question pause:
  collecting / docs_uploading → paused → (continue / discard)
====================================================================
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from database import get_database
from services.service_registry import Service, get_service, list_services
from services.flow_steps import execute_step

logger = logging.getLogger(__name__)


# =====================================================================
# SERVICE DEFINITIONS — moved to `tenant_services` collection (Sprint 4).
# Per-request loads come from `services.service_registry.get_service()`.
# Seed data for fresh tenants lives in `migrations/0006_seed_tenant_services.py`.
# =====================================================================


CONTACT_INFO = "Please contact us directly using the contact details on our website."


# =====================================================================
# KEYWORD DETECTION
# Platform-default keyword sets. Per-tenant overrides come from
# ``tenant_bot_config.flow_keywords`` (see services.bot_config).
# Use :py:func:`preload_flow_keywords` at the start of a request handler
# to populate the tenant cache so the sync helpers below pick up overrides.
# =====================================================================
_DEFAULT_APPLY_KW    = {"apply", "register", "start", "begin", "application", "apply now"}
_DEFAULT_YES_KW      = {"yes", "yeah", "ok", "okay", "sure", "confirm", "proceed", "ha", "yep", "y"}
_DEFAULT_NO_KW       = {"no", "nope", "cancel", "n"}
_DEFAULT_DISCARD_KW  = {"discard", "cancel", "stop", "quit", "exit", "abort", "back", "go back", "main menu"}
_DEFAULT_CONTINUE_KW = {"continue", "resume", "go on", "yes continue"}

# Per-tenant cache populated by ``preload_flow_keywords``. Keyed by
# ``company_id``; each value is a dict of category → set[str].
_TENANT_KW_CACHE: Dict[str, Dict[str, set]] = {}


async def preload_flow_keywords(company_id: Optional[str]) -> None:
    """Populate the per-tenant flow-keyword cache. Call once per request
    before invoking the sync ``is_apply_intent`` / ``is_yes`` / etc.
    helpers. Safe to call repeatedly — relies on bot_config's own 60s cache.
    """
    if not company_id:
        return
    try:
        from services.bot_config import get_bot_config
        cfg = await get_bot_config(company_id)
        _TENANT_KW_CACHE[company_id] = {
            "apply":    set(cfg.flow_keywords("apply",    _DEFAULT_APPLY_KW)),
            "yes":      set(cfg.flow_keywords("yes",      _DEFAULT_YES_KW)),
            "no":       set(cfg.flow_keywords("no",       _DEFAULT_NO_KW)),
            "discard":  set(cfg.flow_keywords("discard",  _DEFAULT_DISCARD_KW)),
            "continue": set(cfg.flow_keywords("continue", _DEFAULT_CONTINUE_KW)),
        }
    except Exception:
        pass


def _kw(category: str, default: set, tenant_id: Optional[str] = None) -> set:
    """Return the resolved keyword set for ``category`` — tenant override
    when available, otherwise the platform default."""
    if tenant_id and tenant_id in _TENANT_KW_CACHE:
        return _TENANT_KW_CACHE[tenant_id].get(category, default)
    return default


# `\w+` with re.UNICODE (Python 3 default) captures Latin + Devanagari +
# other scripts as words. We use this instead of `str.split()` so trailing
# punctuation doesn't break exact-token matches (e.g. "yes." → ["yes"]).
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _words(msg: str):
    return set(_WORD_RE.findall(msg.lower()))


def _contains(msg: str, kw_set):
    """True if any keyword in ``kw_set`` is present in ``msg``.

    Matching rules:
      * Single-word keywords match only as a whole word. "y" does NOT match
        "apply" (the substring bug that previously turned every message
        containing the letter "y" into a "yes"). "ok" doesn't match "okra".
      * Multi-word keywords (containing a space) use a substring match
        against the lower-cased message so phrases like "go back" still
        match anywhere in a sentence.

    Tokenisation uses ``\\w+`` so trailing punctuation doesn't matter
    ("yes." tokenises to ["yes"]).
    """
    if not kw_set:
        return False
    low = msg.lower()
    word_tokens = _words(msg)
    for kw in kw_set:
        if not kw:
            continue
        if " " in kw:
            # Multi-word phrase — substring is the only sensible match.
            if kw in low:
                return True
        else:
            # Single word — whole-word match only.
            if kw in word_tokens:
                return True
    return False


_TRACKING_RE  = re.compile(r'\b[A-Z]{2,20}-\d{8}-[A-Z0-9]{4,10}\b', re.IGNORECASE)
_LOOKUP_KW    = {"track", "status", "my application", "find my", "check my", "where is my", "application status"}

def is_apply_intent(msg: str, tenant_id: Optional[str] = None) -> bool:
    return _contains(msg, _kw("apply", _DEFAULT_APPLY_KW, tenant_id))

def is_tracking_query(msg: str) -> bool:
    """True if message contains a tracking ID."""
    return bool(_TRACKING_RE.search(msg))


def is_yes(msg: str, tenant_id: Optional[str] = None) -> bool:
    kws = _kw("yes", _DEFAULT_YES_KW, tenant_id)
    m = msg.lower().strip().rstrip(".")
    return m in kws or _contains(msg, kws)


def is_no(msg: str, tenant_id: Optional[str] = None) -> bool:
    kws = _kw("no", _DEFAULT_NO_KW, tenant_id)
    m = msg.lower().strip().rstrip(".")
    return m in kws or _contains(msg, kws)


def is_discard(msg: str, tenant_id: Optional[str] = None) -> bool:
    return _contains(msg, _kw("discard", _DEFAULT_DISCARD_KW, tenant_id))


def is_continue(msg: str, tenant_id: Optional[str] = None) -> bool:
    return _contains(msg, _kw("continue", _DEFAULT_CONTINUE_KW, tenant_id)) or is_yes(msg, tenant_id)


def is_question(msg: str) -> bool:
    if "?" in msg:
        return True
    low = msg.lower()
    q_starts = [
        "what", "how", "when", "where", "why", "can ", "is ", "are ", "do ", "does ",
        "show", "tell", "search", "find", "explain", "describe", "give me", "i need",
        "i want to know", "lookup", "look up", "info", "information", "details",
        "kya", "क्या", "कैसे", "कब", "कहाँ", "कहां",
    ]
    return any(low.startswith(w) for w in q_starts)


def _is_info_query(msg: str) -> bool:
    """Detect info/search queries that don't start with question words but clearly seek info."""
    low = msg.lower()
    info_phrases = [
        "visa fee", "visa fees", "passport fee", "passport fees", "oci fee", "oci fees",
        "pcc fee", "attestation fee", "how much", "fee schedule", "cost of", "price of",
        "office address", "office hours", "contact number", "phone number",
        "tell me about", "show me", "search for", "find info", "get info",
        "about visa", "about passport", "about oci", "about pcc",
    ]
    return any(p in low for p in info_phrases)


# Platform-default service-detection patterns. These match the legacy
# CGI-Joburg service catalogue and fire only when a tenant hasn't
# preloaded its own patterns via :py:func:`preload_service_patterns`.
# New tenants get tenant-specific service detection automatically — the
# patterns below are derived from each tenant's ``tenant_services[].keywords``.
_DEFAULT_SERVICE_PATTERNS: Dict[str, list] = {
    "passport": [
        "passport", "पासपोर्ट", "renew passport", "passport renewal", "new passport",
        "fresh passport", "passport expired", "travel document",
        "passport application", "lost passport", "damaged passport", "passport reissue",
    ],
    "visa": [
        "visa", "वीजा", "tourist visa", "business visa", "student visa",
        "medical visa", "e-visa", "evisa", "entry visa",
        "visa application", "visa fee", "visa processing", "visa on arrival",
    ],
    "oci": [
        "oci", "overseas citizen", "overseas citizenship", "oci card",
        "person of indian origin", "indian origin", "pio card",
        "lifelong visa", "oci registration", "oci renewal", "oci reissue",
    ],
    "pcc": [
        "pcc", "police clearance", "clearance certificate",
        "police certificate", "criminal record", "criminal clearance",
        "good standing certificate", "no criminal record",
        "background check", "character certificate", "clearance letter",
    ],
    "marriage": [
        "marriage certificate", "marriage registration", "marry", "married",
        "wedding certificate", "register marriage", "marriage abroad",
        "spouse visa", "marriage attestation", "marriage document",
    ],
    "birth": [
        "birth certificate", "birth registration", "register birth",
        "born abroad", "child born", "newborn", "baby registration",
        "birth record", "birth abroad",
    ],
    "attestation": [
        "attestation", "apostille", "notarization", "notary",
        "document attestation", "attest document", "certify document",
        "affidavit", "power of attorney", "poa", "document authentication",
        "legalization", "stamp document",
    ],
    "ec_death": [
        "emergency certificate", "ec certificate", "death certificate",
        "death registration", "register death", "deceased", "passed away",
        "emergency travel document",
    ],
    "misc": [
        "miscellaneous", "misc", "other service",
        "affidavit", "power of attorney", "poa", "gpa",
        "other form", "other document", "other request",
    ],
}

# Website-info-only categories — tenant-supplied via the
# ``tenant_bot_config.website_only_services`` config slot when needed.
# Empty platform default; legacy CGI categories like "Income Certificate"
# / "NRI Services" / "pension" are no longer hardcoded here.
_WEBSITE_ONLY_KEYWORDS: Dict[str, str] = {}


# Per-tenant service-pattern cache. Each entry mirrors the structure of
# ``_DEFAULT_SERVICE_PATTERNS`` but is derived from the tenant's actual
# ``tenant_services[].keywords`` lists. Populated by
# :py:func:`preload_service_patterns` at the request entry point.
_TENANT_SERVICE_PATTERNS: Dict[str, Dict[str, list]] = {}


async def preload_service_patterns(company_id: Optional[str]) -> None:
    """Populate the per-tenant service-detection cache.

    Reads ``tenant_services`` for the tenant and builds a
    ``{service_key: keyword_list}`` map. Call once per request before any
    sync :py:func:`detect_service` invocations downstream. Safe to call
    repeatedly (relies on the service_registry's own 60s cache).
    """
    if not company_id:
        return
    try:
        from services.service_registry import list_services
        services = await list_services(company_id)
        out: Dict[str, list] = {}
        for s in services:
            if not s.enabled:
                continue
            kws = [str(k).lower() for k in (s.raw.get("keywords") or []) if k]
            # Always include the service name + key itself as keywords —
            # avoids tenants having to repeat the obvious ones.
            kws.append(s.service_key.lower())
            if s.name:
                kws.append(s.name.lower())
            out[s.service_key] = sorted(set(kws), key=len, reverse=True)  # longest-first → "tourist visa" beats "visa"
        if out:
            _TENANT_SERVICE_PATTERNS[company_id] = out
    except Exception as exc:
        logger.debug("[preload_service_patterns] %s: %s", company_id, exc)


def detect_service(msg: str, tenant_id: Optional[str] = None) -> Optional[str]:
    """Return a service_key if the message matches, else None.

    When ``tenant_id`` is supplied AND the tenant's patterns have been
    preloaded, the tenant's own ``tenant_services[].keywords`` drive
    detection. Falls back to ``_DEFAULT_SERVICE_PATTERNS`` (legacy CGI
    vocabulary) only when the tenant cache is empty.
    """
    low = msg.lower()
    patterns = (
        _TENANT_SERVICE_PATTERNS.get(tenant_id)
        if tenant_id and tenant_id in _TENANT_SERVICE_PATTERNS
        else _DEFAULT_SERVICE_PATTERNS
    )
    for service, kws in patterns.items():
        if any(p in low for p in kws):
            return service
    return None


def detect_website_service(msg: str) -> Optional[str]:
    """Return a human-readable service name for keywords not in SERVICES dict."""
    low = msg.lower()
    for kw, label in _WEBSITE_ONLY_KEYWORDS.items():
        if kw in low:
            return label
    return None


# =====================================================================
# FLOW STATE HELPERS
# =====================================================================
_EMPTY_FLOW = {
    "state":               "idle",
    # idle | info_shown | consent_pending | collecting
    # | docs_uploading | docs_pending | paused | submitted
    "service":             None,
    "field_index":         0,
    "data":                {},
    "doc_index":           0,        # which required doc we're waiting for
    "uploaded_docs":       [],       # [{name, file_id, filename, scanned_data, status, uploaded_at}]
    "application_id":      None,
    "tracking_id":         None,
    "paused_question":     None,
    "paused_field_index":  None,
    "paused_in_state":     None,     # state to resume into after pause
    # IDP: extracted fields from scanned documents (TC 3.3 / 3.4)
    "doc_context":         {},       # {full_name, date_of_birth, document_number, ...}
    "prefill_pending":     None,     # {field_key, value} — waiting for user confirm/correct
}


async def _get_flow(session_id: str) -> Dict:
    db = await get_database()
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    return (session or {}).get("flow", dict(_EMPTY_FLOW))


async def get_flow_state(session_id: str) -> Dict:
    """Public accessor for current flow — used by consular_routes."""
    return await _get_flow(session_id)


def ui_hints_for_state(state: Optional[str]) -> Dict[str, bool]:
    """Map a flow state to the per-turn hints the widget uses to decide
    which input controls to surface for the user's NEXT turn. Returns
    `{ expects_upload, expects_image, expects_text }`.

    The widget always allows text input — the hint is about whether to
    also expose the camera + file-upload affordances. Hiding them when
    the bot isn't asking for files keeps the input bar uncluttered (the
    operator's complaint that started this).

    States:
      * docs_pending / docs_uploading — bot is asking for documents,
        so both upload and image-capture should show.
      * everything else — text-only.
    """
    if state in ("docs_pending", "docs_uploading"):
        return {
            "expects_upload": True,
            "expects_image":  True,
            "expects_text":   True,
        }
    return {
        "expects_upload": False,
        "expects_image":  False,
        "expects_text":   True,
    }


async def _save_flow(session_id: str, flow: Dict):
    db = await get_database()
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {"flow": flow}}
    )


async def _clear_flow(session_id: str):
    await _save_flow(session_id, dict(_EMPTY_FLOW))


async def _create_application(session_id: str, user_id: str, svc: Service) -> Tuple[str, str]:
    """Create a new application record in the applications collection.
    Returns (application_id, tracking_id)."""
    db = await get_database()
    app_id = str(uuid.uuid4())
    tracking_id = f"{svc.service_key.upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{app_id[:6].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    await db.applications.insert_one({
        "id":                 app_id,
        "tracking_id":        tracking_id,
        "session_id":         session_id,
        "user_id":            user_id,
        "company_id":         svc.company_id,
        "service":            svc.service_key,
        "service_name":       svc.name,
        "status":             "in_progress",
        "form_data":          {},
        "documents":          [],
        "required_documents": list(svc.documents),
        "created_at":         now,
        "updated_at":         now,
    })
    logger.info(f"[APP] Created application {tracking_id} for {svc.service_key}")
    return app_id, tracking_id


async def _update_application(app_id: str, update: Dict):
    db = await get_database()
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.applications.update_one({"id": app_id}, {"$set": update})


async def _fast_forward_non_input(
    fields: List[Dict[str, Any]],
    fi: int,
    flow: Dict,
    app_id: Optional[str],
) -> int:
    """Sprint 4E — auto-evaluate any consecutive `conditional` / `api_call`
    fields starting at ``fi`` so the user never sees their `question`.

    Each non-input step may update form data (api_call response →
    ``store_response_as``) or short-circuit the form (``skip_to_docs``);
    on short-circuit we return ``len(fields)`` so the caller transitions
    straight to docs_uploading. Plain input fields stop the fast-forward
    and the caller asks the user the question."""
    while fi < len(fields):
        step = await execute_step(fields[fi], flow.get("data", {}))
        if step is None:
            return fi
        if step.form_updates:
            flow.setdefault("data", {}).update(step.form_updates)
            if app_id:
                await _update_application(app_id, {"form_data": flow["data"]})
        if step.advance == "skip_to_docs":
            return len(fields)
        fi += 1
    return fi


# =====================================================================
# RESPONSE BUILDERS — all take a `Service` loaded once per request
# from `service_registry.get_service(tenant_id, service_key)`.
# =====================================================================
def _docs_list(svc: Service) -> str:
    docs = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(svc.documents))
    return f"**Documents required for {svc.name}:**\n{docs}"


def _consent_prompt(svc: Service, scraped_summary: str = "") -> str:
    parts = []
    if scraped_summary:
        parts.append(scraped_summary)
    parts.append(_docs_list(svc))
    parts.append(
        f"\nWould you like to start your **{svc.name}** application now?\n"
        f"Reply **yes** to proceed or **no** to cancel."
    )
    return "\n\n".join(parts)


def _field_question(svc: Service, index: int) -> str:
    total = len(svc.fields)
    q = svc.fields[index]["question"]
    return f"**Step {index+1} of {total}** — {q}"


def _doc_upload_prompt(svc: Service, doc_index: int) -> str:
    total = len(svc.documents)
    doc = svc.documents[doc_index]
    return (
        f"📎 **Document {doc_index+1} of {total}** — Please upload:\n\n"
        f"**{doc}**\n\n"
        f"Use the **Upload** button or **Camera** button below.\n"
        f"Type **skip** to skip this document, or **discard** to cancel the entire application."
    )


def _summary(svc: Service, data: Dict) -> str:
    lines = [f"  • **{f['key'].replace('_', ' ').title()}:** {data.get(f['key'], '—')}" for f in svc.fields]
    return (
        f"✅ **Application Summary — {svc.name}**\n\n"
        + "\n".join(lines)
        + f"\n\n📎 Now let's collect your **{len(svc.documents)} required documents**."
    )


def _website_only_info_page(service_label: str, scraped_summary: str = "") -> str:
    """Info page for services detected from keywords but not in the SERVICES registry.
    Shows scraped website content + contact info. No registration flow."""
    parts = [f"## {service_label}"]

    if scraped_summary and len(scraped_summary.strip()) > 40:
        parts.append(
            f"**Information from official websites:**\n{scraped_summary.strip()}"
        )
    else:
        parts.append(
            "Live website information is currently unavailable for this service. "
            "Please contact the consulate directly for detailed requirements."
        )

    parts.append(
        f"**For this service, please contact us directly:**\n\n"
        f"{CONTACT_INFO}"
    )
    return "\n\n".join(parts)


def _detect_subtype(svc: Service, query: str) -> Optional[Dict[str, Any]]:
    """Match a user query against this service's configured subtypes.

    Subtypes live on ``tenant_services[].subtypes`` (see Service dataclass).
    Each entry has a ``keywords`` list; the first subtype whose keywords
    overlap the user's lower-cased query is returned. Returns None when
    the service has no subtypes or no match.

    Replaces the previous hardcoded ``_PASSPORT_SUBTYPES`` dict that
    embedded ZAR fees, VFS Global Johannesburg, passportindia.gov.in,
    FIR requirements, and tatkal scheme references — all CGI-specific.
    Tenants now configure subtypes per service via the super-admin UI.
    """
    if not query:
        return None
    subtypes = svc.subtypes or []
    if not subtypes:
        return None
    low = query.lower()
    for st in subtypes:
        if not isinstance(st, dict):
            continue
        kws = [str(k).lower() for k in (st.get("keywords") or []) if k]
        if any(kw in low for kw in kws):
            return st
    return None


def _info_service_page(svc: Service, channel: str = "web") -> str:
    """Render an INFO-category service as plain markdown.

    No "type apply to begin" footer, no documents-required block, no
    consent prompt. Just the description + the configured `info_content`
    sections + an optional single CTA line. The widget renders these as
    structured blocks (see ChatWidget / ConsularBot); WhatsApp and other
    text-only channels fall back to this markdown form.
    """
    parts: list = [f"## {svc.name}"]
    if svc.description:
        parts.append(svc.description)

    sections = (svc.info_content or {}).get("sections") or []
    for sec in sections:
        kind = (sec or {}).get("kind") or "text"
        title = (sec or {}).get("title") or ""
        if kind == "bullets":
            items = sec.get("items") or []
            bullets = "\n".join(f"- {item}" for item in items)
            parts.append(f"**{title}**\n{bullets}" if title else bullets)
        elif kind == "callout":
            tone = (sec.get("tone") or "info").lower()
            icon = {"info": "ℹ️", "warning": "⚠️", "success": "✅"}.get(tone, "ℹ️")
            body = sec.get("body") or ""
            parts.append(f"{icon} **{title}**\n{body}" if title else f"{icon} {body}")
        elif kind == "links":
            items = sec.get("items") or []
            lines = [f"- [{(it.get('label') or it.get('url') or '').strip()}]({(it.get('url') or '').strip()})" for it in items]
            parts.append(f"**{title}**\n" + "\n".join(lines) if title else "\n".join(lines))
        elif kind == "contact":
            items = sec.get("items") or []
            lines = []
            for it in items:
                label = (it.get("label") or "").strip()
                value = (it.get("value") or "").strip()
                href = (it.get("href") or "").strip()
                rendered = f"[{value}]({href})" if href else value
                lines.append(f"- **{label}:** {rendered}" if label else f"- {rendered}")
            parts.append(f"**{title}**\n" + "\n".join(lines) if title else "\n".join(lines))
        else:  # text or unknown — render body as-is
            body = sec.get("body") or ""
            parts.append(f"**{title}**\n{body}" if title else body)

    primary = (svc.info_content or {}).get("primary_action") or None
    if primary and primary.get("url") and channel != "whatsapp":
        label = (primary.get("label") or "Open").strip()
        url = primary.get("url").strip()
        parts.append(f"---\n[{label}]({url})")

    return "\n\n".join(p for p in parts if p)


def _service_info_page(svc: Service, scraped_summary: str = "", user_query: str = "", channel: str = "web") -> str:
    """Full info card shown when a user asks about a service.
    Combines static description + live scraped data + docs required + apply offer.

    For any service that has ``subtypes`` configured on its tenant_services
    row, the user's query is matched against subtype keywords; on a hit
    the subtype's description + extra docs are prepended to the service
    info card. Previously this logic was hardcoded for ``service_key ==
    "passport"`` only — now any tenant service can opt in by populating
    ``subtypes``.

    INFO-category services bypass the documents + apply-offer footer
    entirely; the helper above renders them.
    """

    if svc.is_info_only():
        return _info_service_page(svc, channel=channel)

    # Subtype customisation — tenant-configurable per service.
    subtype_info = _detect_subtype(svc, user_query)

    if subtype_info:
        title = subtype_info.get("label") or svc.name
        description = subtype_info.get("description") or svc.description
        base_docs = list(svc.documents)
        # Prepend subtype-specific docs (e.g. police report) before generic list
        extra = list(subtype_info.get("extra_docs") or [])
        all_docs = extra + [d for d in base_docs if d not in extra]
        docs = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(all_docs))
        parts = [f"## {title}\n\n{description}"]
    else:
        docs = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(svc.documents))
        parts = [f"## {svc.name}\n\n{svc.description}"]

    if scraped_summary and len(scraped_summary.strip()) > 40:
        parts.append(f"**Latest information from official websites:**\n{scraped_summary.strip()}")

    parts.append(f"**Documents required:**\n{docs}")
    if channel != "whatsapp":
        parts.append(
            f"---\n**Are you interested in starting the application process for {svc.name}?**\n"
            f"Type **apply** to begin, or ask any questions you may have."
        )
    return "\n\n".join(parts)


def _docs_complete_prompt(svc: Service, uploaded: List[Dict], tracking_id: str) -> str:
    lines = []
    for d in uploaded:
        icon = "✅" if d.get("status") == "uploaded" else "⚠️ skipped"
        lines.append(f"  {icon} {d['name']}")
    skipped = len(svc.documents) - sum(1 for d in uploaded if d.get("status") == "uploaded")
    skip_note = f"\n  _(⚠️ {skipped} document(s) were skipped — you may be asked to provide them later)_" if skipped else ""
    return (
        f"📋 **All documents processed for {svc.name}**\n\n"
        + "\n".join(lines)
        + skip_note
        + f"\n\n🔖 **Tracking ID:** `{tracking_id}`\n\n"
        + "📄 **Review your application before submitting:**\n"
        + "  • Click **Preview PDF** to download an editable preview of your form.\n"
        + "  • To correct any field, type: `correct field name: new value`\n"
        + "    *(e.g. `correct name: John Smith` or `correct dob: 15/08/1990`)*\n\n"
        + "Type **submit** to finalise and submit your application, or **discard** to cancel."
    )


# ── Field correction helpers (TC 4.2) ─────────────────────────────────────────

_CORRECT_RE = re.compile(
    r"^\s*(?:correct|update|change|edit|fix|modify)\s+(.+?)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)

# Common aliases users may type instead of the exact field key
_FIELD_ALIASES: Dict[str, str] = {
    "name":              "full_name",
    "full name":         "full_name",
    "dob":               "dob",
    "date of birth":     "dob",
    "birthday":          "dob",
    "birth date":        "dob",
    "passport":          "passport_number",
    "passport number":   "passport_number",
    "passport no":       "passport_number",
    "passport num":      "passport_number",
    "phone":             "phone",
    "mobile":            "phone",
    "contact":           "phone",
    "email":             "email",
    "mail":              "email",
    "address":           "address",
    "nationality":       "nationality",
    "purpose":           "purpose",
    "travel dates":      "travel_dates",
    "travel":            "travel_dates",
    "doc type":          "doc_type",
    "document type":     "doc_type",
    "child name":        "child_name",
    "child":             "child_name",
    "father":            "father_name",
    "mother":            "mother_name",
    "spouse":            "spouse_name",
    "spouse name":       "spouse_name",
    "marriage date":     "marriage_date",
    "marriage place":    "marriage_place",
    "place of marriage": "marriage_place",
    "birth place":       "birth_place",
    "place of birth":    "birth_place",
    "indian passport":   "indian_passport",
    "new passport":      "new_passport",
    "new citizenship":   "new_citizenship",
    "father passport":   "father_passport",
    "indian connection": "indian_connection",
    "connection":        "indian_connection",
}


def _match_field_key(svc: Service, user_label: str) -> Optional[str]:
    """
    Map a free-text label (e.g. 'name', 'date of birth') to the exact
    form field key defined on the tenant's Service.fields.
    Returns None if no match found.
    """
    fields = svc.fields
    field_keys = {f["key"] for f in fields}
    low = user_label.lower().strip()

    # 1. Direct key match (user typed the exact key)
    normalised = low.replace(" ", "_")
    if normalised in field_keys:
        return normalised

    # 2. Tenant-supplied aliases on the field itself (preferred)
    for f in fields:
        for alias in (f.get("aliases") or []):
            if low == str(alias).lower().strip():
                return f["key"]

    # 3. Built-in alias map (kept as a fallback for legacy services
    #    that haven't been edited since the schema added per-field aliases).
    alias = _FIELD_ALIASES.get(low)
    if alias and alias in field_keys:
        return alias

    # 4. Substring match against key words or question text
    for f in fields:
        key_words = f["key"].replace("_", " ")
        q_words   = (f.get("question") or "").lower()
        if low in key_words or (q_words and low in q_words):
            return f["key"]

    return None


# =====================================================================
# MAIN ENTRY POINT
# =====================================================================
def _pause_prompt(svc_name: str, question: str = "") -> str:
    """Prompt shown when user asks a question while a form is in progress."""
    q_note = f'\n\nYou asked: *"{question[:80]}"*' if question else ""
    return (
        f"⏸ Your **{svc_name}** application is currently in progress.{q_note}\n\n"
        f"What would you like to do?\n\n"
        f"- Reply **continue** — resume your application from where you left off\n"
        f"- Reply **cancel** — cancel the application and I'll look up your query for you"
    )


async def _search_and_format(question: str, knowledge_base: Optional[Dict]) -> str:
    """
    Search knowledge base using the keyword-driven selective scanner.
    Tries service-specific extraction first, then falls back to deep scan.
    """
    if not question or knowledge_base is None:
        return ""
    try:
        from knowledge_scraper import extract_service_content, _SERVICE_KEYWORDS
        from services.hybrid_retrieval import hybrid_search
        # Try service-specific extraction first (focused, fast)
        for svc_key, kws in _SERVICE_KEYWORDS.items():
            if any(k in question.lower() for k in kws):
                result = extract_service_content(svc_key, knowledge_base)
                if result:
                    return result
        # Full hybrid pipeline: MongoDB → scraped cache → deep crawl → fallback
        return await hybrid_search(question, knowledge_base)
    except Exception:
        return ""


# =====================================================================
# AUTO-FILL HELPERS  (TC 3.4)
# =====================================================================

# Maps doc_context keys (from OCR) to one or more form field keys.
# The OCR endpoint returns English-translated fields in this shape.
_DOC_CTX_TO_FORM: Dict[str, List[str]] = {
    "full_name":       ["full_name", "child_name", "father_name", "mother_name", "spouse_name"],
    "date_of_birth":   ["dob"],
    "document_number": ["passport_number", "indian_passport", "new_passport", "father_passport"],
    "nationality":     ["nationality"],
    "address":         ["address"],
    "place_of_birth":  ["birth_place"],
}

# Values that mean "nothing useful was extracted"
_EMPTY_VALUES = {"", "n/a", "null", "none", "unknown", "not available", "not found"}


def _get_prefill(svc: Service, field_index: int, doc_context: Dict) -> Optional[str]:
    """
    Return a pre-filled value from doc_context for fields[field_index], or None.
    Converts OCR date format (YYYY-MM-DD) → form format (DD/MM/YYYY) automatically.
    """
    if not doc_context:
        return None
    fields = svc.fields
    if field_index >= len(fields):
        return None
    field_key = fields[field_index]["key"]

    for ctx_key, form_keys in _DOC_CTX_TO_FORM.items():
        if field_key not in form_keys:
            continue
        raw = doc_context.get(ctx_key)
        if not raw or str(raw).lower().strip() in _EMPTY_VALUES:
            continue
        value = str(raw).strip()
        # Auto-convert ISO date → DD/MM/YYYY
        if field_key == "dob" and re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            y, m, d = value.split("-")
            value = f"{d}/{m}/{y}"
        return value

    return None


def _prefill_prompt(svc: Service, field_index: int, prefilled_value: str) -> str:
    """Question shown when a field has a pre-filled value from a scanned document."""
    fields = svc.fields
    total  = len(fields)
    label  = fields[field_index]["key"].replace("_", " ").title()
    return (
        f"**Step {field_index + 1} of {total}** — "
        f"📋 From your uploaded document we found:\n\n"
        f"**{label}:** {prefilled_value}\n\n"
        f"Reply **yes** to confirm, or type the correct value."
    )


async def process_flow(
    session_id: str,
    message: str,
    tenant_id: str,
    has_image: bool = False,
    image_doc_data: Optional[Dict] = None,
    user_id: str = "guest",
    scraped_summary: str = "",
    knowledge_base: Optional[Dict] = None,
    preloaded_flow: Optional[Dict] = None,  # avoids duplicate DB read when caller has it
    channel: str = "web",  # "web" or "whatsapp" — controls apply prompt visibility
) -> Tuple[Optional[str], bool, str]:
    """
    Process a message through the application flow state machine.

    Returns:
        (response, needs_llm, new_step)
        - response  : direct response string, or None if LLM should handle it
        - needs_llm : True if LLM should generate/augment the response
        - new_step  : step label for ChatResponse
    """
    # ------------------------------------------------------------------
    # TRACKING ID LOOKUP — intercept before any state logic
    # Pattern: SERVICENAME-YYYYMMDD-XXXXXXX (e.g. VISA-20260324-571A82)
    # ------------------------------------------------------------------
    def _fmt_dt(iso: str) -> str:
        """Format ISO datetime string as 'YYYY-MM-DD HH:MM'."""
        if not iso:
            return "—"
        try:
            return iso[:16].replace("T", " ")
        except Exception:
            return iso[:10]

    _tid_match = re.search(r'\b([A-Z]{2,20}-\d{8}-[A-Z0-9]{4,10})\b', message.upper())
    if _tid_match:
        tid = _tid_match.group(1)
        db = await get_database()
        app = await db.applications.find_one({"tracking_id": tid}, {"_id": 0})
        if app:
            svc_name  = app.get("service_name", app.get("service", "").title())
            status    = app.get("status", "unknown").replace("_", " ").title()
            created   = _fmt_dt(app.get("created_at", ""))
            updated   = _fmt_dt(app.get("updated_at", ""))
            form_data = app.get("form_data", {})
            name      = form_data.get("full_name", "—")
            response  = (
                f"🔖 **Application Status**\n\n"
                f"| Field | Details |\n"
                f"|---|---|\n"
                f"| **Tracking ID** | `{tid}` |\n"
                f"| **Service** | {svc_name} |\n"
                f"| **Applicant** | {name} |\n"
                f"| **Status** | {status} |\n"
                f"| **Submitted** | {created} |\n"
                f"| **Last Updated** | {updated} |\n\n"
            )
            if status.lower() == "submitted":
                response += "✅ Your application has been received. You will be contacted at the details provided.\n\n"
            elif status.lower() in ("discarded", "cancelled"):
                response += "❌ This application was cancelled.\n\n"
            else:
                response += f"⏳ Your application is currently being processed.\n\n"
            response += f"For follow-up:\n{CONTACT_INFO}"
            return (response, False, "tracking")
        else:
            return (
                f"❌ No application found with tracking ID **`{tid}`**.\n\n"
                f"Please check the ID and try again, or contact us:\n{CONTACT_INFO}",
                False, "tracking"
            )


    flow    = preloaded_flow if preloaded_flow is not None else await _get_flow(session_id)
    state   = flow.get("state", "idle")
    service = flow.get("service")
    fi      = flow.get("field_index", 0)
    di      = flow.get("doc_index", 0)
    app_id  = flow.get("application_id")

    # Resolve the tenant's Service definition once. If the user is mid-flow
    # but the operator deleted/renamed the service in the meantime, svc_obj
    # is None and downstream branches treat that as "service gone" rather
    # than crashing.
    svc_obj: Optional[Service] = await get_service(tenant_id, service) if service else None

    # ------------------------------------------------------------------
    # STATE: paused  (user asked a question mid-registration)
    # ------------------------------------------------------------------
    if state == "paused":
        svc_name = svc_obj.name if svc_obj else "your application"

        if is_discard(message):
            saved_question = flow.get("paused_question", "")
            if app_id:
                await _update_application(app_id, {"status": "discarded"})
            await _clear_flow(session_id)

            # Search knowledge base / websites for the original question
            search_result = await _search_and_format(saved_question, knowledge_base)

            cancel_msg = f"Your **{svc_name}** application has been **cancelled**. All data has been cleared.\n\n"
            if search_result and saved_question:
                cancel_msg += (
                    f"Here's what I found about **\"{saved_question[:80]}\"**:\n\n"
                    f"{search_result}\n\n"
                    f"---\nLet me know if you need anything else."
                )
            else:
                cancel_msg += "How can I help you?"
            return (cancel_msg, False, "idle")

        if is_continue(message):
            saved_fi        = flow.get("paused_field_index", fi)
            paused_in_state = flow.get("paused_in_state", "collecting")
            flow["state"]             = paused_in_state
            flow["field_index"]       = saved_fi
            flow["paused_question"]   = None
            flow["paused_field_index"]= None
            flow["paused_in_state"]   = None
            await _save_flow(session_id, flow)
            if paused_in_state == "docs_uploading":
                return (
                    "✅ Resuming document upload.\n\n" + _doc_upload_prompt(svc_obj, flow.get("doc_index", 0)),
                    False, "docs_uploading"
                )
            if paused_in_state == "docs_pending":
                tracking_id = flow.get("tracking_id", "")
                return (
                    f"✅ Resuming your application.\n\n"
                    f"🔖 Tracking ID: `{tracking_id}`\n\n"
                    f"Type **submit** to finalise, or **discard** to cancel.",
                    False, "docs_pending"
                )
            return (
                "✅ Resuming your application.\n\n" + _field_question(svc_obj, saved_fi),
                False, "collecting"
            )

        # Any other message while paused — show the continue/cancel prompt again
        return (_pause_prompt(svc_name), False, "paused")

    # ------------------------------------------------------------------
    # STATE: docs_pending  (all docs processed, waiting for submit)
    # ------------------------------------------------------------------
    if state == "docs_pending":
        tracking_id = flow.get("tracking_id", "")
        svc_name    = svc_obj.name if svc_obj else (service or "your application")

        # ── TC 4.2 — Field correction: "correct field: value" ────────
        _corr = _CORRECT_RE.match(message)
        if _corr:
            user_label = _corr.group(1).strip()
            new_value  = _corr.group(2).strip()
            field_key  = _match_field_key(svc_obj, user_label) if svc_obj else None
            if field_key:
                _fc = _field_cfg(svc_obj, field_key) if svc_obj else {}
                validation_error = _validate_field(field_key, new_value, _fc)
                if validation_error:
                    return (
                        f"⚠️ {validation_error}\n\nPlease try again.",
                        False, "docs_pending",
                    )
                flow["data"][field_key] = new_value
                if app_id:
                    await _update_application(app_id, {"form_data": flow["data"]})
                await _save_flow(session_id, flow)
                display_label = field_key.replace("_", " ").title()
                return (
                    f"✅ **{display_label}** updated to: **{new_value}**\n\n"
                    f"Any other corrections? Or type **submit** to finalise.\n"
                    f"🔖 Tracking ID: `{tracking_id}`",
                    False, "docs_pending",
                )
            else:
                example_fields = svc_obj.fields if svc_obj else []
                return (
                    f"I couldn't find a field named **\"{user_label}\"** in your {svc_name} application.\n\n"
                    f"Try using the exact field name, e.g.:\n"
                    + "\n".join(
                        f"  • `correct {f['key'].replace('_', ' ')}: <value>`"
                        for f in example_fields
                    ),
                    False, "docs_pending",
                )

        # ── TC 4.3 — Final submission ─────────────────────────────────
        if "submit" in message.lower():
            # ── pre_submit hooks ──────────────────────────────────────
            # Run with the full form data in scope so rules can branch on
            # field values (fee_amount > 10000 → require_review, etc.).
            # Actions handled here:
            #   * block          — refuse the submission with a message
            #   * require_review — mark application "pending_review"
            #                      instead of "submitted"
            #   * set_field      — override a form field before persist
            from services.service_hooks import evaluate_hooks, first_action
            _form_data = dict(flow.get("data", {}) or {})
            _hook_ctx_submit = {
                "service": svc_obj.service_key if svc_obj else service,
                "service_name": svc_name,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "channel": channel,
                "tracking_id": tracking_id,
                **_form_data,
            }
            _pre_actions = evaluate_hooks(
                (svc_obj.hooks or {}).get("pre_submit") if svc_obj else [],
                _hook_ctx_submit,
            )

            _blocked = first_action(_pre_actions, "block")
            if _blocked:
                return (
                    _blocked.get("message")
                    or "Your application can't be submitted as configured. Please correct the highlighted issue and try again.",
                    False, "docs_pending",
                )

            # Apply set_field actions to the form data BEFORE we persist.
            # Each set_field action looks like {"action":"set_field","field":"X","value":Y}.
            for _act in _pre_actions:
                if _act.get("action") == "set_field" and _act.get("field"):
                    _form_data[_act["field"]] = _act.get("value")
            flow["data"] = _form_data  # keep flow in sync if we save later

            # require_review flips the persisted status from "submitted"
            # to "pending_review" + records the rule's reason for later
            # admin/UI surfacing. The user still gets a positive
            # confirmation; the operator sees the review queue.
            _review_action = first_action(_pre_actions, "require_review")
            _persist_status = "pending_review" if _review_action else "submitted"
            _persist_extra = {}
            if _review_action:
                _persist_extra["review_reason"] = _review_action.get("reason", "rule_triggered")
                if _review_action.get("reviewer"):
                    _persist_extra["assigned_reviewer"] = _review_action["reviewer"]

            if app_id:
                await _update_application(app_id, {
                    "status":       _persist_status,
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "form_data":    _form_data,
                    "documents":    flow.get("uploaded_docs", []),
                    **_persist_extra,
                })

            # ── post_submit hooks ─────────────────────────────────────
            # Run after the application is persisted. Mostly side-effect
            # actions:
            #   * send_email — fire an async notification (compliance
            #     team, partner, etc.)
            #   * show_message — append text to the success reply
            _post_actions = evaluate_hooks(
                (svc_obj.hooks or {}).get("post_submit") if svc_obj else [],
                {**_hook_ctx_submit, "status": _persist_status},
            )
            for _act in _post_actions:
                if _act.get("action") == "send_email":
                    try:
                        # Fire-and-forget — failures are logged but never
                        # block the user's confirmation. The notification
                        # service has its own retry/queueing.
                        from services.notification_service import (
                            notification_service,
                            NotificationType,
                            NotificationChannel,
                            NotificationPriority,
                        )
                        _to = _act.get("to") or _act.get("recipient")
                        _subj = _act.get("subject") or f"New {svc_name} application"
                        _body = _act.get("body") or _act.get("message") or (
                            f"New application submitted.\n\n"
                            f"Tracking ID: {tracking_id}\nService: {svc_name}\nStatus: {_persist_status}"
                        )
                        db = await get_database()
                        await notification_service.create_notification(
                            db=db,
                            user_id=_to or "external_recipient",
                            notification_type=NotificationType.SYSTEM_ALERT,
                            channel=NotificationChannel.EMAIL,
                            priority=NotificationPriority.MEDIUM,
                            data={"message": _body, "subject": _subj, "tracking_id": tracking_id},
                        )
                    except Exception as exc:
                        logger.warning("[post_submit send_email] %s", exc)

            await _clear_flow(session_id)

            # Tailor the confirmation copy to the actual persisted status.
            _extra_messages = "\n\n".join(
                a.get("message", "")
                for a in _post_actions
                if a.get("action") == "show_message" and a.get("message")
            )
            if _persist_status == "pending_review":
                _confirmation = (
                    f"📥 Your **{svc_name}** application has been **received** and is now in review.\n\n"
                    f"🔖 **Tracking ID:** `{tracking_id}`\n\n"
                    f"A team member will be in touch shortly. "
                    f"You can check the status anytime using this tracking ID."
                )
            else:
                _confirmation = (
                    f"🎉 Your **{svc_name}** application has been **submitted successfully**!\n\n"
                    f"🔖 **Tracking ID:** `{tracking_id}`\n\n"
                    f"You can check your application status anytime using this tracking ID.\n\n"
                    f"You will be contacted at the email/phone you provided."
                )
            if _extra_messages:
                _confirmation += "\n\n" + _extra_messages
            _confirmation += f"\n\nFor follow-up:\n{CONTACT_INFO}"
            return (_confirmation, False, "submitted")
        if is_discard(message):
            if app_id:
                await _update_application(app_id, {"status": "discarded"})
            await _clear_flow(session_id)
            return ("Application **discarded**. All data cleared. How can I help you?", False, "idle")
        if is_question(message) or _is_info_query(message):
            if channel == "whatsapp":
                asked_svc = detect_service(message, tenant_id=tenant_id)
                asked_svc_obj = await get_service(tenant_id, asked_svc) if asked_svc else None
                if app_id:
                    await _update_application(app_id, {"status": "discarded"})
                if asked_svc_obj:
                    new_flow = dict(_EMPTY_FLOW)
                    new_flow["state"]   = "info_shown"
                    new_flow["service"] = asked_svc
                    await _save_flow(session_id, new_flow)
                    return (_service_info_page(asked_svc_obj, scraped_summary, user_query=message, channel="whatsapp"), True, "info_shown")
                await _clear_flow(session_id)
                return (None, True, "idle")
            flow["state"]             = "paused"
            flow["paused_question"]   = message
            flow["paused_field_index"]= fi
            flow["paused_in_state"]   = "docs_pending"
            await _save_flow(session_id, flow)
            return (_pause_prompt(svc_name, message), False, "paused")
        return (
            f"Please type **submit** to complete your application, or **discard** to cancel.\n"
            f"To correct a field: `correct field name: new value`\n"
            f"🔖 Tracking ID: `{tracking_id}`",
            False, "docs_pending"
        )

    # ------------------------------------------------------------------
    # STATE: docs_uploading  (step-by-step document collection)
    # ------------------------------------------------------------------
    if state == "docs_uploading":
        docs     = svc_obj.documents if svc_obj else []
        uploaded = flow.get("uploaded_docs", [])

        if is_discard(message):
            if app_id:
                await _update_application(app_id, {"status": "discarded"})
            await _clear_flow(session_id)
            return ("Application **discarded**. All data cleared. How can I help you?", False, "idle")

        if (is_question(message) or _is_info_query(message)) and not has_image:
            if channel == "whatsapp":
                asked_svc = detect_service(message, tenant_id=tenant_id)
                asked_svc_obj = await get_service(tenant_id, asked_svc) if asked_svc else None
                if app_id:
                    await _update_application(app_id, {"status": "discarded"})
                if asked_svc_obj:
                    new_flow = dict(_EMPTY_FLOW)
                    new_flow["state"]   = "info_shown"
                    new_flow["service"] = asked_svc
                    await _save_flow(session_id, new_flow)
                    return (_service_info_page(asked_svc_obj, scraped_summary, user_query=message, channel="whatsapp"), True, "info_shown")
                await _clear_flow(session_id)
                return (None, True, "idle")
            flow["state"]             = "paused"
            flow["paused_question"]   = message
            flow["paused_field_index"]= fi
            flow["paused_in_state"]   = "docs_uploading"
            await _save_flow(session_id, flow)
            svc_name = svc_obj.name if svc_obj else "your application"
            return (_pause_prompt(svc_name, message), False, "paused")

        # Accept uploaded image or skip
        if has_image or "skip" in message.lower():
            doc_record: Dict = {
                "name":        docs[di],
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            if has_image and image_doc_data:
                doc_record["scanned_data"] = image_doc_data
                doc_record["file_id"]      = image_doc_data.get("file_id", str(uuid.uuid4()))
                doc_record["filename"]     = image_doc_data.get("filename", f"doc_{di+1}")
                doc_record["status"]       = "uploaded"
                logger.info(f"[APP] Document {di+1}/{len(docs)} uploaded for {app_id}")
            else:
                doc_record["status"]  = "skipped"
                doc_record["file_id"] = None
                logger.info(f"[APP] Document {di+1}/{len(docs)} skipped for {app_id}")

            uploaded.append(doc_record)
            flow["uploaded_docs"] = uploaded
            di += 1
            flow["doc_index"] = di

            # Persist docs to application record
            if app_id:
                await _update_application(app_id, {
                    "documents": uploaded,
                    "status":    "documents_in_progress",
                })

            if di >= len(docs):
                # All documents processed → move to docs_pending
                flow["state"] = "docs_pending"
                await _save_flow(session_id, flow)
                tracking_id = flow.get("tracking_id", "")
                return (
                    _docs_complete_prompt(svc_obj, uploaded, tracking_id),
                    False, "docs_pending"
                )

            await _save_flow(session_id, flow)
            # Acknowledge upload and ask for next
            ack = "✅ Document uploaded." if has_image else "⚠️ Document skipped."
            return (
                f"{ack}\n\n" + _doc_upload_prompt(svc_obj, di),
                False, "docs_uploading"
            )

        # No image, not skip — re-prompt
        return (_doc_upload_prompt(svc_obj, di), False, "docs_uploading")

    # ------------------------------------------------------------------
    # STATE: collecting  (step-by-step data collection)
    # ------------------------------------------------------------------
    if state == "collecting":
        # If the operator deleted the service mid-flow, abandon gracefully.
        if not svc_obj:
            await _clear_flow(session_id)
            return ("This service is no longer available. How can I help you?", False, "idle")
        fields      = svc_obj.fields
        doc_context = flow.get("doc_context", {})

        # ── Resolve a pending pre-fill confirm (TC 3.4) ───────────────
        prefill_pending = flow.get("prefill_pending")
        if prefill_pending and prefill_pending.get("field_key") == fields[fi]["key"]:
            prefilled_value = prefill_pending["value"]

            if is_discard(message):
                if app_id:
                    await _update_application(app_id, {"status": "discarded"})
                await _clear_flow(session_id)
                return ("Application **discarded**. All data cleared. How can I help you?", False, "idle")

            if is_yes(message):
                # Accept the OCR-extracted value
                accepted_value = prefilled_value
            else:
                # User typed their own value — validate it (using the
                # tenant's per-field validation config if supplied).
                validation_error = _validate_field(
                    fields[fi]["key"], message.strip(),
                    field_cfg=fields[fi] if isinstance(fields[fi], dict) else None,
                )
                if validation_error:
                    return (
                        f"⚠️ {validation_error}\n\n"
                        + _prefill_prompt(svc_obj, fi, prefilled_value),
                        False, "collecting",
                    )
                accepted_value = message.strip()

            flow["prefill_pending"]            = None
            flow["data"][fields[fi]["key"]]    = accepted_value
            fi += 1
            if app_id:
                await _update_application(app_id, {"form_data": flow["data"]})
            # Skip past any conditional/api_call steps inserted between inputs.
            fi = await _fast_forward_non_input(fields, fi, flow, app_id)
            flow["field_index"] = fi

            if fi >= len(fields):
                flow["state"]         = "docs_uploading"
                flow["doc_index"]     = 0
                flow["uploaded_docs"] = []
                await _save_flow(session_id, flow)
                return (
                    _summary(svc_obj, flow["data"]) + "\n\n" + _doc_upload_prompt(svc_obj, 0),
                    False, "docs_uploading",
                )

            # Check doc_context for the NEXT field before asking
            next_prefill = _get_prefill(svc_obj, fi, doc_context)
            if next_prefill:
                flow["prefill_pending"] = {"field_key": fields[fi]["key"], "value": next_prefill}
                await _save_flow(session_id, flow)
                return (_prefill_prompt(svc_obj, fi, next_prefill), False, "collecting")

            await _save_flow(session_id, flow)
            return (_field_question(svc_obj, fi), False, "collecting")

        # ── Normal collecting flow ────────────────────────────────────
        if (is_question(message) or _is_info_query(message)) and not _looks_like_answer(message, fields[fi]["key"]):
            if channel == "whatsapp":
                asked_svc = detect_service(message, tenant_id=tenant_id)
                asked_svc_obj = await get_service(tenant_id, asked_svc) if asked_svc else None
                if app_id:
                    await _update_application(app_id, {"status": "discarded"})
                if asked_svc_obj:
                    new_flow = dict(_EMPTY_FLOW)
                    new_flow["state"]   = "info_shown"
                    new_flow["service"] = asked_svc
                    await _save_flow(session_id, new_flow)
                    return (_service_info_page(asked_svc_obj, scraped_summary, user_query=message, channel="whatsapp"), True, "info_shown")
                await _clear_flow(session_id)
                return (None, True, "idle")
            flow["state"]             = "paused"
            flow["paused_question"]   = message
            flow["paused_field_index"]= fi
            flow["paused_in_state"]   = "collecting"
            await _save_flow(session_id, flow)
            return (_pause_prompt(svc_obj.name, message), False, "paused")

        if is_discard(message):
            if app_id:
                await _update_application(app_id, {"status": "discarded"})
            await _clear_flow(session_id)
            return ("Application **discarded**. All data cleared. How can I help you?", False, "idle")

        # Validate the answer before accepting (tenant per-field config aware).
        validation_error = _validate_field(
            fields[fi]["key"], message.strip(),
            field_cfg=fields[fi] if isinstance(fields[fi], dict) else None,
        )
        if validation_error:
            await _save_flow(session_id, flow)
            return (
                f"⚠️ {validation_error}\n\n" + _field_question(svc_obj, fi),
                False, "collecting"
            )

        # Accept the answer
        flow["data"][fields[fi]["key"]] = message.strip()
        fi += 1

        # Persist form data
        if app_id:
            await _update_application(app_id, {"form_data": flow["data"]})

        # Skip past any conditional/api_call steps inserted between inputs.
        fi = await _fast_forward_non_input(fields, fi, flow, app_id)
        flow["field_index"] = fi

        if fi >= len(fields):
            # All fields collected → move to docs_uploading
            flow["state"]         = "docs_uploading"
            flow["doc_index"]     = 0
            flow["uploaded_docs"] = []
            await _save_flow(session_id, flow)
            return (
                _summary(svc_obj, flow["data"]) + "\n\n" + _doc_upload_prompt(svc_obj, 0),
                False, "docs_uploading"
            )

        # Check doc_context for the NEXT field before asking (TC 3.4)
        next_prefill = _get_prefill(svc_obj, fi, doc_context)
        if next_prefill:
            flow["prefill_pending"] = {"field_key": fields[fi]["key"], "value": next_prefill}
            await _save_flow(session_id, flow)
            return (_prefill_prompt(svc_obj, fi, next_prefill), False, "collecting")

        await _save_flow(session_id, flow)
        return (_field_question(svc_obj, fi), False, "collecting")

    # ------------------------------------------------------------------
    # STATE: consent_pending  (asked user yes/no to start registration)
    # ------------------------------------------------------------------
    if state == "consent_pending":
        if is_yes(message):
            if not svc_obj:
                await _clear_flow(session_id)
                return ("This service is no longer available. How can I help you?", False, "idle")
            app_id, tracking_id = await _create_application(session_id, user_id, svc_obj)
            flow["state"]          = "collecting"
            flow["data"]           = {}
            flow["application_id"] = app_id
            flow["tracking_id"]    = tracking_id

            # Fast-forward through any leading conditional / api_call steps
            # so the first user-facing question is the first INPUT field.
            start_fi = await _fast_forward_non_input(svc_obj.fields, 0, flow, app_id)
            flow["field_index"] = start_fi

            greeting = (
                f"Great! Let's begin your **{svc_obj.name}** application.\n"
                f"🔖 Your tracking ID: `{tracking_id}`\n\n"
            )

            # All fields were non-input (or a conditional skipped straight
            # to docs) → transition directly to docs_uploading.
            if start_fi >= len(svc_obj.fields):
                flow["state"]         = "docs_uploading"
                flow["doc_index"]     = 0
                flow["uploaded_docs"] = []
                await _save_flow(session_id, flow)
                return (
                    greeting + _summary(svc_obj, flow["data"]) + "\n\n"
                    + _doc_upload_prompt(svc_obj, 0),
                    False, "docs_uploading",
                )

            # Check doc_context for the FIRST input field (TC 3.4 auto-fill)
            doc_context = flow.get("doc_context", {})
            first_prefill = _get_prefill(svc_obj, start_fi, doc_context)
            if first_prefill:
                fields = svc_obj.fields
                flow["prefill_pending"] = {"field_key": fields[start_fi]["key"], "value": first_prefill}
                await _save_flow(session_id, flow)
                return (
                    greeting + _prefill_prompt(svc_obj, start_fi, first_prefill),
                    False, "collecting",
                )

            await _save_flow(session_id, flow)
            return (
                greeting + _field_question(svc_obj, start_fi),
                False, "collecting"
            )
        if is_no(message):
            await _clear_flow(session_id)
            return ("No problem. Feel free to ask if you need anything else.", False, "idle")
        # User asked something else — answer via LLM, then remind
        return (None, True, "consent_pending")

    # ------------------------------------------------------------------
    # STATE: info_shown / idle  — detect apply intent
    # ------------------------------------------------------------------
    if is_apply_intent(message) or state == "consent_pending":
        detected_svc = detect_service(message, tenant_id=tenant_id)
        # Fall back to session service when:
        #   - already in consent_pending (mid-flow), OR
        #   - info_shown (user just asked about this service, "apply" means that service)
        # Do NOT fall back from idle — that caused stale cross-session carry-over
        # (e.g. old PCC session → user types "apply oci" → PCC wrongly suggested)
        if state in ("consent_pending", "info_shown"):
            svc_key = detected_svc or service
        else:
            svc_key = detected_svc

        # Resolve to a Service object (may be the same as svc_obj when the
        # fallback used the session-stored key, but a fresh lookup is cheap
        # thanks to the registry's TTL cache and keeps the branches simple).
        target_svc = await get_service(tenant_id, svc_key) if svc_key else None

        # INFO services have no application flow — re-render the info page
        # so the user isn't dropped into a half-broken consent prompt for
        # something that was never meant to be an "application".
        if target_svc and target_svc.is_info_only():
            flow["state"]   = "info_shown"
            flow["service"] = target_svc.service_key
            await _save_flow(session_id, flow)
            return (_service_info_page(target_svc, scraped_summary, user_query=message, channel=channel), False, "info_shown")

        if target_svc:
            # ── pre_consent hooks ──────────────────────────────────────
            # Run before the consent prompt is shown. Use cases:
            #   * show_message — prepend an advisory ("processing for
            #     this country takes 3 weeks")
            #   * block        — short-circuit before the user even
            #     commits ("this service is suspended this week")
            # See services.service_hooks for the rule schema.
            from services.service_hooks import evaluate_hooks, first_action
            _hooks = (target_svc.hooks or {}).get("pre_consent") or []
            _hook_ctx = {
                "service": target_svc.service_key,
                "service_name": target_svc.name,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "channel": channel,
                "message": message,
            }
            _actions = evaluate_hooks(_hooks, _hook_ctx)
            _blocked = first_action(_actions, "block")
            if _blocked:
                # Don't change state — user stays in idle so they can
                # try a different service or ask a question.
                return (
                    _blocked.get("message")
                    or f"Sorry — {target_svc.name} is currently unavailable. Please try again later.",
                    False, state or "idle",
                )

            flow["state"]   = "consent_pending"
            flow["service"] = target_svc.service_key
            await _save_flow(session_id, flow)
            _prompt = _consent_prompt(target_svc, scraped_summary)
            # Prepend each show_message action's text above the consent
            # prompt so the user reads the advisory before saying yes.
            _msgs = [a.get("message") for a in _actions if a.get("action") == "show_message" and a.get("message")]
            if _msgs:
                _prompt = "\n\n".join(_msgs) + "\n\n---\n\n" + _prompt
            return (_prompt, False, "consent_pending")

        # Apply intent detected but no recognisable (or no enabled) service — ask the user
        if is_apply_intent(message):
            available = await list_services(tenant_id)
            svc_list = "\n".join(f"• {s.name}" for s in available)
            return (
                f"I'd be happy to help you apply! Which service are you looking for?\n\n{svc_list}\n\n"
                f"Just mention the service name and I'll guide you.",
                False, "idle"
            )

    # ------------------------------------------------------------------
    # Service info request — show structured info (scraped + static)
    # Triggers from idle OR info_shown (user switches service or asks again)
    # ------------------------------------------------------------------
    detected_key = detect_service(message, tenant_id=tenant_id)
    if detected_key and state in ("idle", "info_shown"):
        detected_svc = await get_service(tenant_id, detected_key)
        if detected_svc:
            flow["state"]   = "info_shown"
            flow["service"] = detected_key
            await _save_flow(session_id, flow)
            # needs_llm=True so the route handler runs the LLM with live knowledge
            # (hybrid_search context_info) as primary source. The service info page
            # is passed back as structured context that the route handler appends.
            return (_service_info_page(detected_svc, scraped_summary, user_query=message, channel=channel), True, "info_shown")

    # ------------------------------------------------------------------
    # Website-only service — scan websites, show info, no registration flow
    # (e.g. life certificate, death registration, domicile, NRI services)
    # ------------------------------------------------------------------
    website_svc_label = detect_website_service(message)
    if website_svc_label and state in ("idle", "info_shown"):
        flow["state"]   = "info_shown"
        flow["service"] = None
        await _save_flow(session_id, flow)
        return (_website_only_info_page(website_svc_label, scraped_summary), True, "info_shown")

    # Default: let LLM handle
    # WhatsApp: if in info_shown with no service detected, clear service context so
    # option buttons are not shown for non-service queries
    if channel == "whatsapp" and state == "info_shown":
        flow["state"]   = "idle"
        flow["service"] = None
        await _save_flow(session_id, flow)
        return (None, True, "idle")
    return (None, True, state)


def _looks_like_answer(msg: str, field_key: str) -> bool:
    """Heuristic: does the message look like data for the given field?"""
    import re
    msg = msg.strip()
    if field_key == "dob":
        return bool(re.search(r"\d{1,2}/\d{1,2}/\d{4}", msg))
    if field_key == "email":
        return "@" in msg
    if field_key == "phone":
        return bool(re.search(r"\+?\d[\d\s\-]{6,}", msg))
    return len(msg) < 120 and "?" not in msg


def _field_cfg(svc, key: str) -> Dict[str, Any]:
    """Return the per-field config dict from a Service, by ``key``.
    Returns an empty dict if not found — callers should treat it as
    "no tenant overrides, use defaults"."""
    if not svc:
        return {}
    fields = getattr(svc, "fields", None) or []
    for f in fields:
        if isinstance(f, dict) and f.get("key") == key:
            return f
    return {}


def _validation_type_for_key(key: str) -> str:
    """Best-effort guess of validation type for a bare field key (no tenant
    config). Tenants should set ``validation_type`` explicitly on the
    field; this is only the fallback for legacy services that haven't been
    edited since the schema was added."""
    name_keys     = {"full_name", "child_name", "father_name", "mother_name", "spouse_name"}
    date_keys     = {"dob", "marriage_date"}
    passport_keys = {"passport_number", "indian_passport", "new_passport", "father_passport"}
    if key in name_keys:     return "name"
    if key in date_keys:     return "date"
    if key in passport_keys: return "passport"
    if key == "email":       return "email"
    if key == "phone":       return "phone"
    if key == "travel_dates":return "travel_dates"
    return "free_text"


def _validate_field(key: str, value: str, field_cfg: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Validate a form field value.

    ``field_cfg`` is the per-field dict from ``tenant_services[].fields[]``;
    keys checked on it (all optional):

      * ``validation_regex``  — custom regex; failure shows ``error_message``.
      * ``validation_type``   — one of ``name|date|email|phone|passport|free_text``.
        Overrides the key-based heuristic below.
      * ``validation_min``    — min length / min age in days for dob.
      * ``validation_max``    — max length / max year-back for dob.
      * ``error_message``     — friendly message shown on failure.
      * ``required``          — when False, an empty value is accepted.

    Returns an error message string if invalid, or None if valid.
    """
    import re
    from datetime import date

    v = value.strip()
    field_cfg = field_cfg or {}

    if not v:
        if field_cfg.get("required") is False:
            return None
        return "This field cannot be empty. Please provide a valid answer."

    # 1) Tenant-supplied custom regex wins outright if present.
    custom_rx = field_cfg.get("validation_regex")
    if custom_rx:
        try:
            if not re.search(custom_rx, v):
                return field_cfg.get("error_message") or "Value does not match the expected format."
            return None
        except re.error:
            logger.warning("[_validate_field] invalid tenant regex for %s: %r", key, custom_rx)

    # 2) Resolve which validation_type to use: tenant override → key-based default.
    vt = (field_cfg.get("validation_type") or "").lower() or _validation_type_for_key(key)

    # --- Name fields ---
    if vt == "name":
        if len(v) < 2:
            return "Name is too short. Please enter your full name."
        if re.search(r"\d", v):
            return "Name should not contain numbers. Please enter a valid name."
        if len(v) > 120:
            return "Name is too long. Please enter a valid name."
        return None

    # --- Date fields (DD/MM/YYYY) ---
    if vt == "date":
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
        if not m:
            return field_cfg.get("error_message") or "Please enter the date in **DD/MM/YYYY** format (e.g. 15/08/1990)."
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            entered = date(year, month, day)
        except ValueError:
            return "That is not a valid date. Please re-enter in **DD/MM/YYYY** format."
        today = date.today()
        if key == "dob":
            if entered >= today:
                return "Date of birth cannot be today or a future date."
            if (today - entered).days < 365:
                return "Date of birth seems incorrect. Please re-enter."
            if year < 1900:
                return "Date of birth year is too far in the past. Please re-enter."
        if key == "marriage_date":
            if entered > today:
                return "Marriage date cannot be in the future."
        return None

    # --- Passport / document numbers ---
    if vt == "passport":
        cleaned = re.sub(r"[\s\-]", "", v).upper()
        min_len = field_cfg.get("validation_min") or 5
        if len(cleaned) < min_len:
            return field_cfg.get("error_message") or f"Passport number is too short (minimum {min_len} characters)."
        if not re.match(r"^[A-Z0-9]+$", cleaned):
            return "Passport number should contain only letters and digits."
        return None

    # --- Email ---
    if vt == "email":
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            return field_cfg.get("error_message") or "Please enter a valid email address (e.g. name@example.com)."
        return None

    # --- Phone ---
    if vt == "phone":
        digits = re.sub(r"[\s\+\-\(\)]", "", v)
        if not digits.isdigit():
            return field_cfg.get("error_message") or "Phone number should contain only digits (and optional +, spaces, or dashes)."
        min_len = field_cfg.get("validation_min") or 7
        max_len = field_cfg.get("validation_max") or 15
        if len(digits) < min_len:
            return f"Phone number is too short (minimum {min_len} digits)."
        if len(digits) > max_len:
            return f"Phone number is too long (maximum {max_len} digits)."
        return None

    # --- Travel dates (DD/MM/YYYY – DD/MM/YYYY) ---
    if vt == "travel_dates" or key == "travel_dates":
        # Normalise separators: en-dash, em-dash, hyphen → "-"
        normalised = re.sub(r"[–—]", "-", v)
        # Extract all date-like tokens (must be DD/MM/YYYY — 4-digit year required)
        date_pattern = r"(\d{1,2})/(\d{1,2})/(\d{4})"
        matches = re.findall(date_pattern, normalised)
        if len(matches) < 2:
            # Check if user used a 2-digit year (e.g. 10/05/25) to give a clear hint
            if re.search(r"\d{1,2}/\d{1,2}/\d{2}\b", normalised):
                return "Please use a **4-digit year** for your travel dates (e.g. 01/06/2026 – 20/06/2026)."
            return "Please enter your intended travel dates in **DD/MM/YYYY – DD/MM/YYYY** format (e.g. 01/06/2026 – 20/06/2026)."
        parsed = []
        for day_s, mon_s, yr_s in matches[:2]:
            try:
                parsed.append(date(int(yr_s), int(mon_s), int(day_s)))
            except ValueError:
                return "One or more travel dates are not valid. Please re-enter (e.g. 01/06/2026 – 20/06/2026)."
        if parsed[1] <= parsed[0]:
            return "The return date must be **after** the departure date. Please re-enter your travel dates."
        return None

    # --- Generic non-empty check for all remaining fields ---
    if len(v) < 2:
        return "This field cannot be empty. Please provide a valid answer."
    if len(v) > 500:
        return "Response is too long. Please be more concise."
    return None


# =====================================================================
# POST-LLM HOOK  (append context-aware suffix after LLM response)
# =====================================================================
async def flow_suffix(state: str, service: Optional[str], tenant_id: str, channel: str = "web") -> str:
    """Append after LLM response to guide user back into the flow.

    channel: "web" shows apply prompts; "whatsapp" hides them.
    """
    svc_obj = await get_service(tenant_id, service) if service else None
    svc_name = svc_obj.name if svc_obj else "your application"
    # Note: "paused" state no longer uses LLM — it returns direct prompts,
    # so no suffix is needed for it here.
    if state == "consent_pending" and service:
        if channel == "whatsapp":
            return ""
        return (
            f"\n\n---\n"
            f"Would you still like to **apply** for {svc_name}? "
            f"Reply **yes** to start registration or **no** to cancel."
        )
    if state in ("idle", "info_shown"):
        if channel == "whatsapp":
            return ""
        if svc_obj:
            return (
                f"\n\n---\n"
                f"Is this sufficient information, or do you need more details?\n"
                f"**Are you interested in starting the application process for {svc_obj.name}?** "
                f"Type **apply** to begin."
            )
        return (
            "\n\n---\n"
            "Is this sufficient information, or do you need more details?"
        )
    return ""
