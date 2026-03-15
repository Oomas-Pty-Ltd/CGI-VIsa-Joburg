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
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from database import get_database

logger = logging.getLogger(__name__)


# =====================================================================
# SERVICE DEFINITIONS
# =====================================================================
SERVICES: Dict[str, Dict] = {
    "passport": {
        "name": "Passport Services",
        "description": (
            "The Consulate General of India, Johannesburg provides passport services including "
            "fresh issuance, renewal, and emergency travel documents for Indian nationals residing "
            "in South Africa. Applications must be submitted in person by appointment. "
            "Processing time is typically 3–4 weeks for normal passports and 2–3 days for emergency documents. "
            "Visit https://passportindia.gov.in to complete your online application before visiting the consulate."
        ),
        "documents": [
            "Online application receipt from passportindia.gov.in",
            "Current/expired passport — original + photocopy of all pages",
            "Proof of residence in South Africa (utility bill or lease agreement)",
            "Recent passport-size photographs (51×51 mm, white background)",
            "South African ID or valid visa/work permit",
        ],
        "fields": [
            {"key": "full_name",       "question": "Please enter your **full name** (as it appears on your passport):"},
            {"key": "dob",             "question": "Please enter your **date of birth** (DD/MM/YYYY):"},
            {"key": "passport_number", "question": "Please enter your **current passport number**:"},
            {"key": "phone",           "question": "Please enter your **phone number**:"},
            {"key": "email",           "question": "Please enter your **email address**:"},
            {"key": "address",         "question": "Please enter your **residential address** in South Africa:"},
        ],
    },
    "visa": {
        "name": "Indian Visa",
        "description": (
            "Indian visas for South African and other foreign nationals are processed through "
            "VFS Global Visa Application Centre, Johannesburg (not directly at the consulate). "
            "Common visa categories include Tourist, Business, Medical, Student, and e-Visa. "
            "Tourist and Business e-Visas can be applied online at indianvisaonline.gov.in. "
            "For other categories, apply in person at VFS Global. "
            "Processing time: 3–5 business days. VFS hours: Mon–Fri 08:00–15:00 (appointment mandatory). "
            "Visit: https://visa.vfsglobal.com/one-pager/india/south-africa/johannesburg/"
        ),
        "documents": [
            "Valid foreign passport (at least 6 months validity remaining)",
            "Recent passport-size photographs",
            "Proof of residence in South Africa",
            "Bank statements (last 3 months)",
            "Travel itinerary / flight bookings",
            "Proof of purpose (invitation letter / hotel bookings / medical letter)",
        ],
        "fields": [
            {"key": "full_name",       "question": "Please enter your **full name** (as in your passport):"},
            {"key": "dob",             "question": "Please enter your **date of birth** (DD/MM/YYYY):"},
            {"key": "nationality",     "question": "Please enter your **nationality**:"},
            {"key": "passport_number", "question": "Please enter your **passport number**:"},
            {"key": "travel_dates",    "question": "Please enter your **intended travel dates** to India (e.g. 01/06/2026 – 20/06/2026):"},
            {"key": "purpose",         "question": "What is the **purpose** of your visit? (tourism / business / medical / student)"},
            {"key": "phone",           "question": "Please enter your **phone number**:"},
            {"key": "email",           "question": "Please enter your **email address**:"},
        ],
    },
    "oci": {
        "name": "OCI (Overseas Citizen of India)",
        "description": (
            "OCI (Overseas Citizen of India) is a lifelong visa for foreign nationals of Indian origin "
            "and their spouses. It grants multiple-entry, multi-purpose lifelong visa to India, "
            "exemption from registering with the Foreigners Regional Registration Office (FRRO), "
            "and parity with NRIs in most financial and educational matters. "
            "Apply online at ociservices.gov.in and submit documents in person at the consulate. "
            "Processing time: 8–10 weeks. Applicable fee must be paid online."
        ),
        "documents": [
            "Foreign passport — original + copies of all pages",
            "Proof of Indian origin (old Indian passport / parent's Indian passport / Indian birth certificate)",
            "South African ID / permanent residence / work permit",
            "Recent passport-size photographs",
            "Marriage certificate (if applying as spouse of an Indian citizen)",
        ],
        "fields": [
            {"key": "full_name",         "question": "Please enter your **full name** (as in your passport):"},
            {"key": "dob",               "question": "Please enter your **date of birth** (DD/MM/YYYY):"},
            {"key": "passport_number",   "question": "Please enter your **foreign passport number**:"},
            {"key": "indian_connection", "question": "Briefly describe your **Indian origin connection** (e.g. 'My father was an Indian citizen'):"},
            {"key": "phone",             "question": "Please enter your **phone number**:"},
            {"key": "email",             "question": "Please enter your **email address**:"},
        ],
    },
    "pcc": {
        "name": "Police Clearance Certificate (PCC)",
        "description": (
            "A Police Clearance Certificate (PCC) is an official document issued by the Indian consulate "
            "confirming that the applicant has no criminal record in India. "
            "It is commonly required for immigration, employment abroad, or residency applications. "
            "The PCC is issued for Indian passport holders currently residing in South Africa. "
            "Apply in person at the consulate. Processing time: 3–5 business days. "
            "Consulate hours: Mon–Fri 09:00–12:00 (by appointment only)."
        ),
        "documents": [
            "Valid Indian passport — original + photocopy",
            "Proof of current address in South Africa",
            "South African residency document (visa / permit / PR)",
        ],
        "fields": [
            {"key": "full_name",       "question": "Please enter your **full name** (as in your passport):"},
            {"key": "dob",             "question": "Please enter your **date of birth** (DD/MM/YYYY):"},
            {"key": "passport_number", "question": "Please enter your **Indian passport number**:"},
            {"key": "phone",           "question": "Please enter your **phone number**:"},
            {"key": "email",           "question": "Please enter your **email address**:"},
            {"key": "purpose",         "question": "What is the **purpose** for which you need the PCC?"},
        ],
    },
}

CONTACT_INFO = (
    "📞 **+27 6830 38144**\n"
    "📧 cons.joburg@mea.gov.in\n"
    "🏢 1st Floor, Cedar Square, Corner Willow Ave & Cedar Road, Fourways, Johannesburg 2055\n"
    "🕐 Mon–Fri 09:00–17:00 | Consular services: 09:00–12:00 (by appointment)\n"
    "🌐 https://www.cgijoburg.gov.in"
)


# =====================================================================
# KEYWORD DETECTION
# =====================================================================
_APPLY_KW    = {"apply", "register", "start", "begin", "application", "करना", "चाहिए", "लगाना", "apply now"}
_YES_KW      = {"yes", "yeah", "ok", "okay", "sure", "confirm", "proceed", "हाँ", "हां", "ha", "yep", "y"}
_NO_KW       = {"no", "nope", "cancel", "नहीं", "nahi", "n"}
_DISCARD_KW  = {"discard", "cancel", "stop", "quit", "exit", "छोड़", "बंद", "abort"}
_CONTINUE_KW = {"continue", "resume", "जारी", "चालू", "go on", "yes continue"}


def _words(msg: str):
    return set(msg.lower().split())


def _contains(msg: str, kw_set):
    return bool(_words(msg) & kw_set) or any(k in msg.lower() for k in kw_set)


def is_apply_intent(msg: str) -> bool:
    return _contains(msg, _APPLY_KW)


def is_yes(msg: str) -> bool:
    m = msg.lower().strip().rstrip(".")
    return m in _YES_KW or _contains(msg, _YES_KW)


def is_no(msg: str) -> bool:
    m = msg.lower().strip().rstrip(".")
    return m in _NO_KW or _contains(msg, _NO_KW)


def is_discard(msg: str) -> bool:
    return _contains(msg, _DISCARD_KW)


def is_continue(msg: str) -> bool:
    return _contains(msg, _CONTINUE_KW) or is_yes(msg)


def is_question(msg: str) -> bool:
    if "?" in msg:
        return True
    low = msg.lower()
    q_starts = ["what", "how", "when", "where", "why", "can ", "is ", "are ", "do ", "does ",
                "kya", "क्या", "कैसे", "कब", "कहाँ", "कहां"]
    return any(low.startswith(w) for w in q_starts)


def detect_service(msg: str) -> Optional[str]:
    low = msg.lower()
    if any(w in low for w in ["passport", "पासपोर्ट"]):
        return "passport"
    if any(w in low for w in ["oci", "overseas citizen"]):
        return "oci"
    if any(w in low for w in ["pcc", "police clearance"]):
        return "pcc"
    if any(w in low for w in ["visa", "वीजा"]):
        return "visa"
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
}


async def _get_flow(session_id: str) -> Dict:
    db = await get_database()
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    return (session or {}).get("flow", dict(_EMPTY_FLOW))


async def get_flow_state(session_id: str) -> Dict:
    """Public accessor for current flow — used by consular_routes."""
    return await _get_flow(session_id)


async def _save_flow(session_id: str, flow: Dict):
    db = await get_database()
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {"flow": flow}}
    )


async def _clear_flow(session_id: str):
    await _save_flow(session_id, dict(_EMPTY_FLOW))


async def _create_application(session_id: str, user_id: str, service: str) -> Tuple[str, str]:
    """Create a new application record in the applications collection.
    Returns (application_id, tracking_id)."""
    db = await get_database()
    app_id = str(uuid.uuid4())
    svc = SERVICES[service]
    tracking_id = f"{service.upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{app_id[:6].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    await db.applications.insert_one({
        "id":                 app_id,
        "tracking_id":        tracking_id,
        "session_id":         session_id,
        "user_id":            user_id,
        "service":            service,
        "service_name":       svc["name"],
        "status":             "in_progress",
        "form_data":          {},
        "documents":          [],
        "required_documents": svc["documents"],
        "created_at":         now,
        "updated_at":         now,
    })
    logger.info(f"[APP] Created application {tracking_id} for {service}")
    return app_id, tracking_id


async def _update_application(app_id: str, update: Dict):
    db = await get_database()
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.applications.update_one({"id": app_id}, {"$set": update})


# =====================================================================
# RESPONSE BUILDERS
# =====================================================================
def _docs_list(service_key: str) -> str:
    svc = SERVICES[service_key]
    docs = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(svc["documents"]))
    return f"**Documents required for {svc['name']}:**\n{docs}"


def _consent_prompt(service_key: str, scraped_summary: str = "") -> str:
    svc = SERVICES[service_key]
    parts = []
    if scraped_summary:
        parts.append(scraped_summary)
    parts.append(_docs_list(service_key))
    parts.append(
        f"\nWould you like to start your **{svc['name']}** application now?\n"
        f"Reply **yes** to proceed or **no** to cancel."
    )
    return "\n\n".join(parts)


def _field_question(service_key: str, index: int) -> str:
    fields = SERVICES[service_key]["fields"]
    total = len(fields)
    q = fields[index]["question"]
    return f"**Step {index+1} of {total}** — {q}"


def _doc_upload_prompt(service_key: str, doc_index: int) -> str:
    docs = SERVICES[service_key]["documents"]
    total = len(docs)
    doc = docs[doc_index]
    return (
        f"📎 **Document {doc_index+1} of {total}** — Please upload:\n\n"
        f"**{doc}**\n\n"
        f"Use the 📎 attachment button to upload the file or image.\n"
        f"Type **skip** to skip this document, or **discard** to cancel the entire application."
    )


def _summary(service_key: str, data: Dict) -> str:
    svc = SERVICES[service_key]
    fields = svc["fields"]
    lines = [f"  • **{f['key'].replace('_', ' ').title()}:** {data.get(f['key'], '—')}" for f in fields]
    return (
        f"✅ **Application Summary — {svc['name']}**\n\n"
        + "\n".join(lines)
        + f"\n\n📎 Now let's collect your **{len(svc['documents'])} required documents**."
    )


def _service_info_page(service_key: str, scraped_summary: str = "") -> str:
    """Full info card shown when a user asks about a service.
    Combines static description + live scraped data + docs required + apply offer."""
    svc = SERVICES[service_key]
    docs = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(svc["documents"]))

    parts = [f"## {svc['name']}\n\n{svc['description']}"]

    if scraped_summary and len(scraped_summary.strip()) > 40:
        parts.append(f"**Latest information from official websites:**\n{scraped_summary.strip()}")

    parts.append(f"**Documents required:**\n{docs}")
    parts.append(
        f"---\nWould you like to **apply** for {svc['name']}?\n"
        f"Type **apply** to start your application."
    )
    return "\n\n".join(parts)


def _docs_complete_prompt(service_key: str, uploaded: List[Dict], tracking_id: str) -> str:
    svc = SERVICES[service_key]
    lines = []
    for d in uploaded:
        icon = "✅" if d.get("status") == "uploaded" else "⚠️ skipped"
        lines.append(f"  {icon} {d['name']}")
    skipped = len(svc["documents"]) - sum(1 for d in uploaded if d.get("status") == "uploaded")
    skip_note = f"\n  _(⚠️ {skipped} document(s) were skipped — you may be asked to provide them later)_" if skipped else ""
    return (
        f"📋 **All documents processed for {svc['name']}**\n\n"
        + "\n".join(lines)
        + skip_note
        + f"\n\n🔖 **Tracking ID:** `{tracking_id}`\n\n"
        + "Type **submit** to finalise and submit your application, or **discard** to cancel."
    )


# =====================================================================
# MAIN ENTRY POINT
# =====================================================================
async def process_flow(
    session_id: str,
    message: str,
    has_image: bool = False,
    image_doc_data: Optional[Dict] = None,
    user_id: str = "guest",
    scraped_summary: str = "",
) -> Tuple[Optional[str], bool, str]:
    """
    Process a message through the application flow state machine.

    Returns:
        (response, needs_llm, new_step)
        - response  : direct response string, or None if LLM should handle it
        - needs_llm : True if LLM should generate/augment the response
        - new_step  : step label for ChatResponse
    """
    flow    = await _get_flow(session_id)
    state   = flow.get("state", "idle")
    service = flow.get("service")
    fi      = flow.get("field_index", 0)
    di      = flow.get("doc_index", 0)
    app_id  = flow.get("application_id")

    # ------------------------------------------------------------------
    # STATE: paused  (user asked a question mid-registration)
    # ------------------------------------------------------------------
    if state == "paused":
        if is_discard(message):
            if app_id:
                await _update_application(app_id, {"status": "discarded"})
            await _clear_flow(session_id)
            return (
                "Your application has been **discarded**. All data has been cleared.\n\nHow can I help you?",
                False, "idle"
            )
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
                    "Resuming document upload.\n\n" + _doc_upload_prompt(service, flow.get("doc_index", 0)),
                    False, "docs_uploading"
                )
            return (
                "Resuming your application.\n\n" + _field_question(service, saved_fi),
                False, "collecting"
            )
        # Still asking — let LLM answer, then remind
        return (None, True, "paused")

    # ------------------------------------------------------------------
    # STATE: docs_pending  (all docs processed, waiting for submit)
    # ------------------------------------------------------------------
    if state == "docs_pending":
        if "submit" in message.lower():
            svc_name    = SERVICES[service]["name"]
            tracking_id = flow.get("tracking_id", "")
            if app_id:
                await _update_application(app_id, {
                    "status":       "submitted",
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                    "form_data":    flow.get("data", {}),
                    "documents":    flow.get("uploaded_docs", []),
                })
            await _clear_flow(session_id)
            return (
                f"🎉 Your **{svc_name}** application has been **submitted successfully**!\n\n"
                f"🔖 **Tracking ID:** `{tracking_id}`\n\n"
                f"You can check your application status anytime using this tracking ID.\n\n"
                f"You will be contacted at the email/phone you provided.\n\n"
                f"For follow-up:\n{CONTACT_INFO}",
                False, "submitted"
            )
        if is_discard(message):
            if app_id:
                await _update_application(app_id, {"status": "discarded"})
            await _clear_flow(session_id)
            return ("Application **discarded**. All data cleared. How can I help you?", False, "idle")
        if is_question(message):
            flow["state"]             = "paused"
            flow["paused_question"]   = message
            flow["paused_field_index"]= fi
            flow["paused_in_state"]   = "docs_pending"
            await _save_flow(session_id, flow)
            return (None, True, "paused")
        tracking_id = flow.get("tracking_id", "")
        return (
            f"Please type **submit** to complete your application, or **discard** to cancel.\n"
            f"🔖 Tracking ID: `{tracking_id}`",
            False, "docs_pending"
        )

    # ------------------------------------------------------------------
    # STATE: docs_uploading  (step-by-step document collection)
    # ------------------------------------------------------------------
    if state == "docs_uploading":
        docs     = SERVICES[service]["documents"]
        uploaded = flow.get("uploaded_docs", [])

        if is_discard(message):
            if app_id:
                await _update_application(app_id, {"status": "discarded"})
            await _clear_flow(session_id)
            return ("Application **discarded**. All data cleared. How can I help you?", False, "idle")

        if is_question(message) and not has_image:
            flow["state"]             = "paused"
            flow["paused_question"]   = message
            flow["paused_field_index"]= fi
            flow["paused_in_state"]   = "docs_uploading"
            await _save_flow(session_id, flow)
            return (None, True, "paused")

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
                    _docs_complete_prompt(service, uploaded, tracking_id),
                    False, "docs_pending"
                )

            await _save_flow(session_id, flow)
            # Acknowledge upload and ask for next
            ack = "✅ Document uploaded and scanned." if has_image else "⚠️ Document skipped."
            return (
                f"{ack}\n\n" + _doc_upload_prompt(service, di),
                False, "docs_uploading"
            )

        # No image, not skip — re-prompt
        return (_doc_upload_prompt(service, di), False, "docs_uploading")

    # ------------------------------------------------------------------
    # STATE: collecting  (step-by-step data collection)
    # ------------------------------------------------------------------
    if state == "collecting":
        fields = SERVICES[service]["fields"]

        if is_question(message) and not _looks_like_answer(message, fields[fi]["key"]):
            flow["state"]             = "paused"
            flow["paused_question"]   = message
            flow["paused_field_index"]= fi
            flow["paused_in_state"]   = "collecting"
            await _save_flow(session_id, flow)
            return (None, True, "paused")

        if is_discard(message):
            if app_id:
                await _update_application(app_id, {"status": "discarded"})
            await _clear_flow(session_id)
            return ("Application **discarded**. All data cleared. How can I help you?", False, "idle")

        # Accept the answer
        flow["data"][fields[fi]["key"]] = message.strip()
        fi += 1
        flow["field_index"] = fi

        # Persist form data
        if app_id:
            await _update_application(app_id, {"form_data": flow["data"]})

        if fi >= len(fields):
            # All fields collected → move to docs_uploading
            flow["state"]         = "docs_uploading"
            flow["doc_index"]     = 0
            flow["uploaded_docs"] = []
            await _save_flow(session_id, flow)
            return (
                _summary(service, flow["data"]) + "\n\n" + _doc_upload_prompt(service, 0),
                False, "docs_uploading"
            )

        await _save_flow(session_id, flow)
        return (_field_question(service, fi), False, "collecting")

    # ------------------------------------------------------------------
    # STATE: consent_pending  (asked user yes/no to start registration)
    # ------------------------------------------------------------------
    if state == "consent_pending":
        if is_yes(message):
            app_id, tracking_id = await _create_application(session_id, user_id, service)
            flow["state"]          = "collecting"
            flow["field_index"]    = 0
            flow["data"]           = {}
            flow["application_id"] = app_id
            flow["tracking_id"]    = tracking_id
            await _save_flow(session_id, flow)
            return (
                f"Great! Let's begin your **{SERVICES[service]['name']}** application.\n"
                f"🔖 Your tracking ID: `{tracking_id}`\n\n"
                + _field_question(service, 0),
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
        svc = detect_service(message) or service
        if svc:
            flow["state"]   = "consent_pending"
            flow["service"] = svc
            await _save_flow(session_id, flow)
            return (_consent_prompt(svc, scraped_summary), False, "consent_pending")

    # ------------------------------------------------------------------
    # Service info request — show structured info (scraped + static)
    # then offer to apply
    # ------------------------------------------------------------------
    svc = detect_service(message)
    if svc and state == "idle":
        flow["state"]   = "info_shown"
        flow["service"] = svc
        await _save_flow(session_id, flow)
        return (_service_info_page(svc, scraped_summary), False, "info_shown")

    # Default: let LLM handle
    return (None, True, state)


def _looks_like_answer(msg: str, field_key: str) -> bool:
    """Heuristic: does the message look like data for the given field?"""
    import re
    msg = msg.strip()
    if field_key == "dob":
        return bool(re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", msg))
    if field_key == "email":
        return "@" in msg
    if field_key == "phone":
        return bool(re.search(r"\+?\d[\d\s\-]{6,}", msg))
    return len(msg) < 120 and "?" not in msg


# =====================================================================
# POST-LLM HOOK  (append context-aware suffix after LLM response)
# =====================================================================
def flow_suffix(state: str, service: Optional[str]) -> str:
    """Append after LLM response to guide user back into the flow."""
    svc_name = SERVICES[service]["name"] if service and service in SERVICES else "your application"
    if state == "paused":
        return (
            f"\n\n---\n"
            f"⏸ Your **{svc_name}** application is paused.\n"
            f"Reply **continue** to resume, or **discard** to cancel and clear all data."
        )
    if state == "consent_pending" and service:
        return (
            f"\n\n---\n"
            f"Would you still like to **apply** for {svc_name}? "
            f"Reply **yes** to start registration or **no** to cancel."
        )
    return ""
