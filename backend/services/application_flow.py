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
            "VFS Global Visa Application Centre, Johannesburg (not directly at the Consulate). "
            "South African nationals receive Indian visas GRATIS (free of charge). "
            "Apply online at https://indianvisaonline.gov.in/ — no manual forms accepted. "
            "For e-Visa, apply at https://indianvisaonline.gov.in/evisa/tvoa.html (min. 5 working days before travel). "
            "Biometrics mandatory at VFS for regular visa applicants. "
            "VFS Visa Centre: 1st Floor, Rivonia Village Office Block, cnr Rivonia Blvd & Mutual Rd, Rivonia, JHB. "
            "VFS hours: Mon–Fri 08:00–15:00. No visa applications accepted at the Consulate directly."
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
            "OCI (Overseas Citizen of India) provides a multi-purpose, multi-entry life-long visa to India. "
            "Eligibility: persons who were citizens of India on or after 26 Jan 1950, or whose parents/grandparents "
            "were Indian citizens, or who are spouses of Indian citizens/OCI holders (married for ≥2 years), "
            "or minor children of Indian citizens. "
            "Apply online at ociservices.gov.in, then submit documents in person at the Consulate "
            "(appointment via cons.jburg@mea.gov.in). Fees as per MEA notification."
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
            "A Police Clearance Certificate (PCC) is required by Indian nationals for immigration, "
            "change of nationality, employment abroad, or longer stay in another country. "
            "PCC service is outsourced to VFS Global — do NOT apply at the Consulate directly. "
            "Apply online at https://www.cgijoburg.gov.in/page/status-of-indian-passport-pcc/, select CGI Johannesburg, "
            "and submit at VFS Global Johannesburg (2nd Floor, Harrow Court 1, Isle of Houghton, Park Town). "
            "VFS submission hours: 08:00–15:00, Mon–Fri. "
            "VFS Reference: https://www.vfsglobal.com/one-pager/India/SouthAfrica/consular-services/"
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
    "marriage": {
        "name": "Marriage Certificate / Registration",
        "description": (
            "The Consulate General of India, Johannesburg provides services for registration of marriages "
            "of Indian nationals solemnized in South Africa under the Hindu Marriage Act or Special Marriage Act. "
            "Both spouses must appear in person at the consulate. "
            "The consulate also attests South African marriage certificates for use in India. "
            "Processing time: 5–7 business days. Appointment required. "
            "For attestation of documents for use in India, bring originals and certified copies."
        ),
        "documents": [
            "Valid Indian passport of Indian spouse — original + photocopy",
            "South African marriage certificate (registered with Home Affairs) — original + photocopy",
            "Proof of residence in South Africa of both spouses",
            "Recent passport-size photographs of both spouses",
            "Affidavit confirming marital status (if previously married)",
            "Divorce decree / death certificate of previous spouse (if applicable)",
        ],
        "fields": [
            {"key": "full_name",          "question": "Please enter the **full name of the Indian spouse** (as in passport):"},
            {"key": "dob",                "question": "Please enter their **date of birth** (DD/MM/YYYY):"},
            {"key": "passport_number",    "question": "Please enter the **Indian passport number**:"},
            {"key": "spouse_name",        "question": "Please enter the **full name of the other spouse**:"},
            {"key": "marriage_date",      "question": "Please enter the **date of marriage** (DD/MM/YYYY):"},
            {"key": "marriage_place",     "question": "Please enter the **place of marriage** (city, country):"},
            {"key": "phone",              "question": "Please enter your **phone number**:"},
            {"key": "email",              "question": "Please enter your **email address**:"},
        ],
    },
    "birth": {
        "name": "Birth Certificate Registration",
        "description": (
            "Indian nationals residing in South Africa can register the birth of their child born in South Africa "
            "at the Consulate General of India, Johannesburg. "
            "This service is Gratis (free of charge). "
            "Registration is required before applying for an Indian passport for the child. "
            "Required: birth certificate from South African Home Department and local hospital."
        ),
        "documents": [
            "South African birth certificate of the child — original + photocopy",
            "Indian passport of both parents — original + photocopy",
            "Proof of residence in South Africa",
            "Hospital birth record / discharge summary",
            "Recent passport-size photographs of the child",
            "Marriage certificate of parents (if applicable)",
        ],
        "fields": [
            {"key": "child_name",         "question": "Please enter the **child's full name**:"},
            {"key": "dob",                "question": "Please enter the **child's date of birth** (DD/MM/YYYY):"},
            {"key": "birth_place",        "question": "Please enter the **place of birth** (hospital, city):"},
            {"key": "father_name",        "question": "Please enter the **father's full name** (as in passport):"},
            {"key": "mother_name",        "question": "Please enter the **mother's full name** (as in passport):"},
            {"key": "father_passport",    "question": "Please enter the **father's Indian passport number**:"},
            {"key": "phone",              "question": "Please enter your **phone number**:"},
            {"key": "email",              "question": "Please enter your **email address**:"},
        ],
    },
    "attestation": {
        "name": "Document Attestation / Apostille",
        "description": (
            "The Consulate General of India, Johannesburg provides attestation of academic degrees, "
            "general power of attorney (GPA/PoA), and other documents for Indian and foreign nationals. "
            "For Indian documents: must first be apostilled by MEA (Ministry of External Affairs, India) — "
            "see http://www.mea.gov.in/apostille.htm. "
            "For GPA/PoA: bring original documents and self-attested copies. "
            "For foreign nationals: attestation of Indian documents for use in South Africa. "
            "Fee as per consular schedule. Contact the Consulate for appointment."
        ),
        "documents": [
            "Original document(s) to be attested — with photocopies",
            "Valid Indian passport — original + photocopy (for Indian national documents)",
            "Proof of residence in South Africa",
            "Application form (available at the consulate)",
            "Fee payment receipt",
        ],
        "fields": [
            {"key": "full_name",       "question": "Please enter your **full name** (as in your passport):"},
            {"key": "passport_number", "question": "Please enter your **passport number**:"},
            {"key": "doc_type",        "question": "What **type of document** needs attestation? (e.g. degree certificate, affidavit, power of attorney):"},
            {"key": "doc_purpose",     "question": "What is the **purpose** of attestation? (e.g. employment in India, property registration, etc.):"},
            {"key": "phone",           "question": "Please enter your **phone number**:"},
            {"key": "email",           "question": "Please enter your **email address**:"},
        ],
    },
    "renunciation": {
        "name": "Renunciation / Surrender of Indian Citizenship",
        "description": (
            "Indian nationals who have acquired citizenship of another country (including South Africa) "
            "are required by law to renounce their Indian citizenship and surrender their Indian passport. "
            "The renunciation certificate is issued by the Consulate General of India, Johannesburg. "
            "After renunciation, an OCI card can be applied for to maintain ties with India. "
            "Contact the Consulate for appointment: cons.jburg@mea.gov.in or +27 11-4828484 / +27 11 581 9800."
        ),
        "documents": [
            "Indian passport — original (to be surrendered)",
            "New foreign citizenship certificate / foreign passport — original + photocopy",
            "Proof of current address in South Africa",
            "Completed renunciation application form",
            "Recent passport-size photographs",
            "Paid fee receipt (fee payable at consulate)",
        ],
        "fields": [
            {"key": "full_name",          "question": "Please enter your **full name** (as in your Indian passport):"},
            {"key": "dob",                "question": "Please enter your **date of birth** (DD/MM/YYYY):"},
            {"key": "indian_passport",    "question": "Please enter your **Indian passport number** (to be surrendered):"},
            {"key": "new_citizenship",    "question": "What is your **new citizenship / nationality**?"},
            {"key": "new_passport",       "question": "Please enter your **new foreign passport number**:"},
            {"key": "phone",              "question": "Please enter your **phone number**:"},
            {"key": "email",              "question": "Please enter your **email address**:"},
        ],
    },
    "ec_death": {
        "name": "EC / Death Certificate",
        "description": (
            "The Consulate General of India, Johannesburg issues Emergency Certificates (EC) and "
            "assists with death registration for Indian nationals. "
            "An EC is issued when the Indian passport is lost/expired and the person needs to travel back to India urgently. "
            "Death registration is required when an Indian national passes away in South Africa. "
            "Contact: cons.jburg@mea.gov.in | +27 11-4828484 / +27 11 581 9800."
        ),
        "documents": [
            "Indian Passport of the deceased / applicant (copy)",
            "South African Death Certificate (original + notarised copy) — for death registration",
            "Proof of relationship to deceased",
            "Applicant's valid Indian Passport or OCI card",
            "Two passport-size photographs of applicant",
            "Police report (in case of unnatural death)",
        ],
        "fields": [
            {"key": "full_name",       "question": "Please enter your **full name** (applicant):"},
            {"key": "dob",             "question": "Please enter your **date of birth** (DD/MM/YYYY):"},
            {"key": "passport_number", "question": "Please enter your **passport / OCI number**:"},
            {"key": "phone",           "question": "Please enter your **phone number**:"},
            {"key": "email",           "question": "Please enter your **email address**:"},
            {"key": "doc_type",        "question": "What do you require? (Emergency Certificate or Death Certificate registration):"},
            {"key": "doc_purpose",     "question": "Please briefly describe the **purpose / relationship to deceased** (if applicable):"},
        ],
    },
    "misc": {
        "name": "Miscellaneous / Other Consular Services",
        "description": (
            "The Consulate General of India, Johannesburg handles various miscellaneous consular matters "
            "including affidavits, document authentication, general power of attorney (GPA/PoA), "
            "life certificates, and other services not covered under standard categories. "
            "📄 Miscellaneous application form (PDF): "
            "https://www.cgijoburg.gov.in//docs/1771050896misc%20application%20form-new.pdf\n"
            "Contact the Consulate to confirm your specific requirement: "
            "cons.jburg@mea.gov.in | +27 11-4828484 / +27 11 581 9800."
        ),
        "documents": [
            "Valid Indian Passport or OCI card (copy)",
            "Relevant supporting documents (case-specific)",
            "Two passport-size photographs",
            "Completed Miscellaneous Application Form — https://www.cgijoburg.gov.in//docs/1771050896misc%20application%20form-new.pdf",
            "Affidavit / Notarised documents (where required)",
            "Fee payment receipt (if applicable)",
        ],
        "fields": [
            {"key": "full_name",       "question": "Please enter your **full name** (as in your passport):"},
            {"key": "dob",             "question": "Please enter your **date of birth** (DD/MM/YYYY):"},
            {"key": "passport_number", "question": "Please enter your **passport / OCI number**:"},
            {"key": "phone",           "question": "Please enter your **phone number**:"},
            {"key": "email",           "question": "Please enter your **email address**:"},
            {"key": "doc_purpose",     "question": "Please describe the **nature / purpose** of your request:"},
        ],
    },
}

CONTACT_INFO = (
    "📞 **+27 11-4828484 / +27 11-4828485 / +27 11-4828486 / +27 11 581 9800**\n"
    "📧 ccom.jburg@mea.gov.in (general) | cons.jburg@mea.gov.in (consular/OCI)\n"
    "🏢 No. 1, Eton Road (Corner Jan Smuts Avenue & Eton Road), Park Town 2193, Johannesburg\n"
    "🕐 Mon–Fri 08:30–17:00 (Lunch: 13:00–13:30)\n"
    "🌐 https://www.cgijoburg.gov.in"
)


# =====================================================================
# KEYWORD DETECTION
# =====================================================================
_APPLY_KW    = {"apply", "register", "start", "begin", "application", "करना", "चाहिए", "लगाना", "apply now"}
_YES_KW      = {"yes", "yeah", "ok", "okay", "sure", "confirm", "proceed", "हाँ", "हां", "ha", "yep", "y"}
_NO_KW       = {"no", "nope", "cancel", "नहीं", "nahi", "n"}
_DISCARD_KW  = {"discard", "cancel", "stop", "quit", "exit", "छोड़", "बंद", "abort", "back", "go back", "main menu"}
_CONTINUE_KW = {"continue", "resume", "जारी", "चालू", "go on", "yes continue"}


def _words(msg: str):
    return set(msg.lower().split())


def _contains(msg: str, kw_set):
    return bool(_words(msg) & kw_set) or any(k in msg.lower() for k in kw_set)


_TRACKING_RE  = re.compile(r'\b[A-Z]{2,20}-\d{8}-[A-Z0-9]{4,10}\b', re.IGNORECASE)
_LOOKUP_KW    = {"track", "status", "my application", "find my", "check my", "where is my", "application status"}

def is_apply_intent(msg: str) -> bool:
    return _contains(msg, _APPLY_KW)

def is_tracking_query(msg: str) -> bool:
    """True if message contains a tracking ID."""
    return bool(_TRACKING_RE.search(msg))


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


_SERVICE_PATTERNS: Dict[str, list] = {
    "passport": [
        "passport", "पासपोर्ट", "renew passport", "passport renewal", "new passport",
        "fresh passport", "passport expired", "travel document", "tatkal",
        "passportindia", "passport application", "emergency passport",
        "lost passport", "damaged passport", "passport reissue",
    ],
    "visa": [
        "visa", "वीजा", "tourist visa", "business visa", "student visa",
        "medical visa", "e-visa", "evisa", "entry visa", "visit india",
        "travel to india", "go to india", "trip to india", "travel india",
        "indianvisaonline", "vfs", "vfs global", "vfs appointment",
        "visa application", "visa fee", "visa processing", "visa stamping",
        "visa on arrival", "conference visa", "employment visa",
    ],
    "oci": [
        "oci", "overseas citizen", "overseas citizenship", "oci card",
        "person of indian origin", "indian origin", "pio card",
        "lifelong visa", "oci registration", "oci renewal", "oci reissue",
        "oci child", "oci minor", "oci spouse", "ociservices",
        "indian origin card", "proof of indian origin",
    ],
    "pcc": [
        "pcc", "police clearance", "clearance certificate",
        "police certificate", "criminal record", "criminal clearance",
        "good standing certificate", "no criminal record",
        "background check", "character certificate", "clearance letter",
        "immigration clearance", "police verification",
    ],
    "marriage": [
        "marriage certificate", "marriage registration", "marry", "married",
        "wedding certificate", "matrimonial", "nikah certificate",
        "register marriage", "marriage abroad", "marriage in south africa",
        "spouse visa", "marriage attestation", "marriage document",
    ],
    "birth": [
        "birth certificate", "birth registration", "register birth",
        "born abroad", "child born", "newborn", "baby registration",
        "birth record", "birth abroad", "child registration",
    ],
    "attestation": [
        "attestation", "apostille", "notarization", "notary",
        "document attestation", "attest document", "certify document",
        "degree attestation", "certificate attestation", "affidavit",
        "power of attorney", "poa", "document authentication",
        "legalization", "stamp document",
    ],
    "renunciation": [
        "renunciation", "renounce", "surrender passport", "give up citizenship",
        "renounce indian citizenship", "surrender indian passport",
        "change citizenship", "foreign citizenship", "new citizenship",
        "took south african citizenship", "naturalisation", "surrender",
        "surrender citizenship", "surrender indian citizenship",
    ],
    "ec_death": [
        "emergency certificate", "ec certificate", "death certificate",
        "death registration", "register death", "deceased", "passed away",
        "death abroad", "indian died", "indian national died",
        "emergency travel document", "lost passport emergency",
        "ec for travel", "emergency cert",
    ],
    "misc": [
        "miscellaneous", "misc", "other service", "other consular",
        "affidavit", "power of attorney", "poa", "gpa", "general power of attorney",
        "life certificate", "jeevan pramaan", "attestation",
        "apostille", "notarization", "document authentication", "legalization",
        "stamp document", "certify document", "degree attestation",
        "certificate attestation", "attest document", "other form",
        "other document", "other request",
    ],
}

# Services that can be detected from website keywords even if not in SERVICES
_WEBSITE_ONLY_KEYWORDS: Dict[str, str] = {
    "income certificate":   "Income Certificate",
    "domicile":             "Domicile Certificate",
    "nri":                  "NRI Services",
    "pension":              "Pension Services",
}


def detect_service(msg: str) -> Optional[str]:
    """Return a SERVICES key if message matches, else None."""
    low = msg.lower()
    for service, patterns in _SERVICE_PATTERNS.items():
        if any(p in low for p in patterns):
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
        f"Use the **Upload** button or **Camera** button below.\n"
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
        f"**For this service, please contact the consulate directly:**\n\n"
        f"{CONTACT_INFO}\n\n"
        f"You may also visit **https://www.cgijoburg.gov.in** for the latest updates."
    )
    return "\n\n".join(parts)


_PASSPORT_SUBTYPES = {
    "lost": {
        "label": "Lost/Stolen Passport — Re-issue",
        "description": (
            "To re-issue a lost or stolen Indian passport, you must apply online at "
            "https://passportindia.gov.in (select 'Re-issue') and submit in person at "
            "the VFS Global Passport Centre, Johannesburg with an appointment.\n\n"
            "**Important:** A police report (FIR) for the lost/stolen passport is mandatory. "
            "Fees: ZAR 2,280 (36-page) | ZAR 2,655 (60-page) — includes ICWF ZAR 30. "
            "Processing time: 3–4 weeks."
        ),
        "extra_docs": [
            "Original FIR / Police Report for lost or stolen passport (mandatory)",
            "Proof of Indian citizenship (if original passport not available)",
            "Sworn affidavit explaining circumstances of loss",
        ],
    },
    "stolen": {
        "label": "Lost/Stolen Passport — Re-issue",
        "description": (
            "To re-issue a stolen Indian passport, apply online at "
            "https://passportindia.gov.in (select 'Re-issue') and submit at VFS Global, Johannesburg.\n\n"
            "**Important:** A police report (FIR) is mandatory. "
            "Fees: ZAR 2,280 (36-page) | ZAR 2,655 (60-page). Processing: 3–4 weeks."
        ),
        "extra_docs": [
            "Original FIR / Police Report for stolen passport (mandatory)",
            "Proof of Indian citizenship (Aadhaar / PAN / birth certificate)",
            "Sworn affidavit explaining circumstances of theft",
        ],
    },
    "damaged": {
        "label": "Damaged Passport — Re-issue",
        "description": (
            "To re-issue a damaged Indian passport, apply online at "
            "https://passportindia.gov.in (select 'Re-issue') and submit at VFS Global, Johannesburg.\n\n"
            "A passport is considered damaged if it has ink/water stains, scribbling, torn pages, "
            "missing data page, or spine damage. "
            "Fees: ZAR 2,280 (36-page) | ZAR 2,655 (60-page). Processing: 3–4 weeks."
        ),
        "extra_docs": [
            "Original damaged passport (must be submitted)",
        ],
    },
    "emergency": {
        "label": "Emergency Travel Document",
        "description": (
            "An Emergency Travel Document (ETD) is issued for a single journey to India when a valid "
            "Indian passport is not available due to loss, theft, or damage.\n\n"
            "Required: police report (if lost/stolen), proof of identity, 2 photographs, proof of travel. "
            "Fees: ZAR 780 (includes ICWF). Processing: 2–3 working days."
        ),
        "extra_docs": [
            "Police report (FIR) if passport was lost or stolen",
            "Proof of identity (Aadhaar / PAN / any government ID)",
            "Proof of travel (flight ticket or booking confirmation)",
            "2 recent passport-size photographs",
        ],
    },
    "tatkal": {
        "label": "Tatkal (Urgent) Passport",
        "description": (
            "Tatkal is an urgent passport scheme for Indian nationals who require a passport quickly. "
            "Apply online at https://passportindia.gov.in (select 'Tatkal') and submit at VFS Global, Johannesburg.\n\n"
            "Tatkal fee is higher than normal; processing is typically 2–5 working days after verification."
        ),
        "extra_docs": [],
    },
}

_PASSPORT_SUBTYPE_KEYWORDS = {
    "lost":      ["lost passport", "lost my passport", "passport lost", "misplaced passport"],
    "stolen":    ["stolen passport", "passport stolen", "passport was stolen", "passport theft"],
    "damaged":   ["damaged passport", "passport damaged", "torn passport", "wet passport", "stained passport"],
    "emergency": ["emergency travel", "emergency document", "emergency passport", "etd", "stranded without passport"],
    "tatkal":    ["tatkal", "tatkaal", "urgent passport", "urgent travel"],
}


def _detect_passport_subtype(query: str) -> Optional[str]:
    low = query.lower()
    for subtype, phrases in _PASSPORT_SUBTYPE_KEYWORDS.items():
        if any(p in low for p in phrases):
            return subtype
    # Single word fallbacks
    if "lost" in low.split() or "lose" in low.split():
        return "lost"
    if "stolen" in low.split() or "theft" in low.split():
        return "stolen"
    if "damaged" in low.split() or "damage" in low.split():
        return "damaged"
    if "emergency" in low.split():
        return "emergency"
    if "tatkal" in low.split():
        return "tatkal"
    return None


def _service_info_page(service_key: str, scraped_summary: str = "", user_query: str = "", channel: str = "web") -> str:
    """Full info card shown when a user asks about a service.
    Combines static description + live scraped data + docs required + apply offer.
    For passport, detects sub-type (lost/stolen/damaged/emergency/tatkal) from user_query."""
    svc = SERVICES[service_key]

    # Passport sub-type customisation
    subtype_info = None
    if service_key == "passport" and user_query:
        subtype_key = _detect_passport_subtype(user_query)
        subtype_info = _PASSPORT_SUBTYPES.get(subtype_key)

    if subtype_info:
        title = subtype_info["label"]
        description = subtype_info["description"]
        base_docs = list(svc["documents"])
        # Prepend sub-type specific docs (FIR etc.) before generic list
        extra = subtype_info.get("extra_docs", [])
        all_docs = extra + [d for d in base_docs if d not in extra]
        docs = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(all_docs))
        parts = [f"## {title}\n\n{description}"]
    else:
        docs = "\n".join(f"  {i+1}. {d}" for i, d in enumerate(svc["documents"]))
        parts = [f"## {svc['name']}\n\n{svc['description']}"]

    if scraped_summary and len(scraped_summary.strip()) > 40:
        parts.append(f"**Latest information from official websites:**\n{scraped_summary.strip()}")

    parts.append(f"**Documents required:**\n{docs}")
    if channel != "whatsapp":
        parts.append(
            f"---\n**Are you interested in starting the application process for {svc['name']}?**\n"
            f"Type **apply** to begin, or ask any questions you may have."
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


def _match_field_key(service_key: str, user_label: str) -> Optional[str]:
    """
    Map a free-text label (e.g. 'name', 'date of birth') to the exact
    form field key defined in SERVICES[service_key]['fields'].
    Returns None if no match found.
    """
    fields = SERVICES[service_key]["fields"]
    field_keys = {f["key"] for f in fields}
    low = user_label.lower().strip()

    # 1. Direct key match (user typed the exact key)
    normalised = low.replace(" ", "_")
    if normalised in field_keys:
        return normalised

    # 2. Alias lookup
    alias = _FIELD_ALIASES.get(low)
    if alias and alias in field_keys:
        return alias

    # 3. Substring match against key words or question text
    for f in fields:
        key_words = f["key"].replace("_", " ")
        q_words   = f["question"].lower()
        if low in key_words or low in q_words:
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


def _get_prefill(service_key: str, field_index: int, doc_context: Dict) -> Optional[str]:
    """
    Return a pre-filled value from doc_context for fields[field_index], or None.
    Converts OCR date format (YYYY-MM-DD) → form format (DD/MM/YYYY) automatically.
    """
    if not doc_context:
        return None
    fields = SERVICES[service_key]["fields"]
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


def _prefill_prompt(service_key: str, field_index: int, prefilled_value: str) -> str:
    """Question shown when a field has a pre-filled value from a scanned document."""
    fields = SERVICES[service_key]["fields"]
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

    # ------------------------------------------------------------------
    # STATE: paused  (user asked a question mid-registration)
    # ------------------------------------------------------------------
    if state == "paused":
        svc_name = SERVICES[service]["name"] if service and service in SERVICES else "your application"

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
                    "✅ Resuming document upload.\n\n" + _doc_upload_prompt(service, flow.get("doc_index", 0)),
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
                "✅ Resuming your application.\n\n" + _field_question(service, saved_fi),
                False, "collecting"
            )

        # Any other message while paused — show the continue/cancel prompt again
        return (_pause_prompt(svc_name), False, "paused")

    # ------------------------------------------------------------------
    # STATE: docs_pending  (all docs processed, waiting for submit)
    # ------------------------------------------------------------------
    if state == "docs_pending":
        tracking_id = flow.get("tracking_id", "")
        svc_name    = SERVICES[service]["name"]

        # ── TC 4.2 — Field correction: "correct field: value" ────────
        _corr = _CORRECT_RE.match(message)
        if _corr:
            user_label = _corr.group(1).strip()
            new_value  = _corr.group(2).strip()
            field_key  = _match_field_key(service, user_label)
            if field_key:
                validation_error = _validate_field(field_key, new_value)
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
                return (
                    f"I couldn't find a field named **\"{user_label}\"** in your {svc_name} application.\n\n"
                    f"Try using the exact field name, e.g.:\n"
                    + "\n".join(
                        f"  • `correct {f['key'].replace('_', ' ')}: <value>`"
                        for f in SERVICES[service]["fields"]
                    ),
                    False, "docs_pending",
                )

        # ── TC 4.3 — Final submission ─────────────────────────────────
        if "submit" in message.lower():
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
        if is_question(message) or _is_info_query(message):
            if channel == "whatsapp":
                asked_svc = detect_service(message)
                if app_id:
                    await _update_application(app_id, {"status": "discarded"})
                if asked_svc and asked_svc in SERVICES:
                    new_flow = dict(_EMPTY_FLOW)
                    new_flow["state"]   = "info_shown"
                    new_flow["service"] = asked_svc
                    await _save_flow(session_id, new_flow)
                    return (_service_info_page(asked_svc, scraped_summary, user_query=message, channel="whatsapp"), True, "info_shown")
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
        docs     = SERVICES[service]["documents"]
        uploaded = flow.get("uploaded_docs", [])

        if is_discard(message):
            if app_id:
                await _update_application(app_id, {"status": "discarded"})
            await _clear_flow(session_id)
            return ("Application **discarded**. All data cleared. How can I help you?", False, "idle")

        if (is_question(message) or _is_info_query(message)) and not has_image:
            if channel == "whatsapp":
                asked_svc = detect_service(message)
                if app_id:
                    await _update_application(app_id, {"status": "discarded"})
                if asked_svc and asked_svc in SERVICES:
                    new_flow = dict(_EMPTY_FLOW)
                    new_flow["state"]   = "info_shown"
                    new_flow["service"] = asked_svc
                    await _save_flow(session_id, new_flow)
                    return (_service_info_page(asked_svc, scraped_summary, user_query=message, channel="whatsapp"), True, "info_shown")
                await _clear_flow(session_id)
                return (None, True, "idle")
            flow["state"]             = "paused"
            flow["paused_question"]   = message
            flow["paused_field_index"]= fi
            flow["paused_in_state"]   = "docs_uploading"
            await _save_flow(session_id, flow)
            svc_name = SERVICES[service]["name"]
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
                    _docs_complete_prompt(service, uploaded, tracking_id),
                    False, "docs_pending"
                )

            await _save_flow(session_id, flow)
            # Acknowledge upload and ask for next
            ack = "✅ Document uploaded." if has_image else "⚠️ Document skipped."
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
        fields      = SERVICES[service]["fields"]
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
                # User typed their own value — validate it
                validation_error = _validate_field(fields[fi]["key"], message.strip())
                if validation_error:
                    return (
                        f"⚠️ {validation_error}\n\n"
                        + _prefill_prompt(service, fi, prefilled_value),
                        False, "collecting",
                    )
                accepted_value = message.strip()

            flow["prefill_pending"]            = None
            flow["data"][fields[fi]["key"]]    = accepted_value
            fi += 1
            flow["field_index"] = fi
            if app_id:
                await _update_application(app_id, {"form_data": flow["data"]})

            if fi >= len(fields):
                flow["state"]         = "docs_uploading"
                flow["doc_index"]     = 0
                flow["uploaded_docs"] = []
                await _save_flow(session_id, flow)
                return (
                    _summary(service, flow["data"]) + "\n\n" + _doc_upload_prompt(service, 0),
                    False, "docs_uploading",
                )

            # Check doc_context for the NEXT field before asking
            next_prefill = _get_prefill(service, fi, doc_context)
            if next_prefill:
                flow["prefill_pending"] = {"field_key": fields[fi]["key"], "value": next_prefill}
                await _save_flow(session_id, flow)
                return (_prefill_prompt(service, fi, next_prefill), False, "collecting")

            await _save_flow(session_id, flow)
            return (_field_question(service, fi), False, "collecting")

        # ── Normal collecting flow ────────────────────────────────────
        if (is_question(message) or _is_info_query(message)) and not _looks_like_answer(message, fields[fi]["key"]):
            if channel == "whatsapp":
                asked_svc = detect_service(message)
                if app_id:
                    await _update_application(app_id, {"status": "discarded"})
                if asked_svc and asked_svc in SERVICES:
                    new_flow = dict(_EMPTY_FLOW)
                    new_flow["state"]   = "info_shown"
                    new_flow["service"] = asked_svc
                    await _save_flow(session_id, new_flow)
                    return (_service_info_page(asked_svc, scraped_summary, user_query=message, channel="whatsapp"), True, "info_shown")
                await _clear_flow(session_id)
                return (None, True, "idle")
            flow["state"]             = "paused"
            flow["paused_question"]   = message
            flow["paused_field_index"]= fi
            flow["paused_in_state"]   = "collecting"
            await _save_flow(session_id, flow)
            svc_name = SERVICES[service]["name"]
            return (_pause_prompt(svc_name, message), False, "paused")

        if is_discard(message):
            if app_id:
                await _update_application(app_id, {"status": "discarded"})
            await _clear_flow(session_id)
            return ("Application **discarded**. All data cleared. How can I help you?", False, "idle")

        # Validate the answer before accepting
        validation_error = _validate_field(fields[fi]["key"], message.strip())
        if validation_error:
            await _save_flow(session_id, flow)
            return (
                f"⚠️ {validation_error}\n\n" + _field_question(service, fi),
                False, "collecting"
            )

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

        # Check doc_context for the NEXT field before asking (TC 3.4)
        next_prefill = _get_prefill(service, fi, doc_context)
        if next_prefill:
            flow["prefill_pending"] = {"field_key": fields[fi]["key"], "value": next_prefill}
            await _save_flow(session_id, flow)
            return (_prefill_prompt(service, fi, next_prefill), False, "collecting")

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

            # Check doc_context for the FIRST field (TC 3.4 auto-fill)
            doc_context = flow.get("doc_context", {})
            first_prefill = _get_prefill(service, 0, doc_context)
            if first_prefill:
                fields = SERVICES[service]["fields"]
                flow["prefill_pending"] = {"field_key": fields[0]["key"], "value": first_prefill}
                await _save_flow(session_id, flow)
                return (
                    f"Great! Let's begin your **{SERVICES[service]['name']}** application.\n"
                    f"🔖 Your tracking ID: `{tracking_id}`\n\n"
                    + _prefill_prompt(service, 0, first_prefill),
                    False, "collecting",
                )

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
        detected_svc = detect_service(message)
        # Fall back to session service when:
        #   - already in consent_pending (mid-flow), OR
        #   - info_shown (user just asked about this service, "apply" means that service)
        # Do NOT fall back from idle — that caused stale cross-session carry-over
        # (e.g. old PCC session → user types "apply oci" → PCC wrongly suggested)
        if state in ("consent_pending", "info_shown"):
            svc = detected_svc or service
        else:
            svc = detected_svc

        if svc:
            flow["state"]   = "consent_pending"
            flow["service"] = svc
            await _save_flow(session_id, flow)
            return (_consent_prompt(svc, scraped_summary), False, "consent_pending")

        # Apply intent detected but no recognisable service — ask the user
        if is_apply_intent(message) and not svc:
            svc_list = "\n".join(f"• {v['name']}" for v in SERVICES.values())
            return (
                f"I'd be happy to help you apply! Which service are you looking for?\n\n{svc_list}\n\n"
                f"Just mention the service name (e.g. *passport*, *visa*, *OCI card*, *PCC*) and I'll guide you.",
                False, "idle"
            )

    # ------------------------------------------------------------------
    # Service info request — show structured info (scraped + static)
    # Triggers from idle OR info_shown (user switches service or asks again)
    # ------------------------------------------------------------------
    svc = detect_service(message)
    if svc and state in ("idle", "info_shown"):
        flow["state"]   = "info_shown"
        flow["service"] = svc
        await _save_flow(session_id, flow)
        # needs_llm=True so the route handler runs the LLM with live knowledge
        # (hybrid_search context_info) as primary source. The service info page
        # is passed back as structured context that the route handler appends.
        return (_service_info_page(svc, scraped_summary, user_query=message, channel=channel), True, "info_shown")

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


def _validate_field(key: str, value: str) -> Optional[str]:
    """
    Validate a form field value.
    Returns an error message string if invalid, or None if valid.
    """
    import re
    from datetime import date

    v = value.strip()

    # --- Name fields ---
    _name_keys = {"full_name", "child_name", "father_name", "mother_name", "spouse_name"}
    if key in _name_keys:
        if len(v) < 2:
            return "Name is too short. Please enter your full name."
        if re.search(r"\d", v):
            return "Name should not contain numbers. Please enter a valid name."
        if len(v) > 120:
            return "Name is too long. Please enter a valid name."
        return None

    # --- Date fields (DD/MM/YYYY) ---
    _date_keys = {"dob", "marriage_date"}
    if key in _date_keys:
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
        if not m:
            return "Please enter the date in **DD/MM/YYYY** format (e.g. 15/08/1990)."
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
    _passport_keys = {"passport_number", "indian_passport", "new_passport", "father_passport"}
    if key in _passport_keys:
        # Indian passport: 1 letter + 7 digits (e.g. A1234567)
        # Foreign passports vary — require at least 5 alphanumeric chars
        cleaned = re.sub(r"[\s\-]", "", v).upper()
        if len(cleaned) < 5:
            return "Passport number is too short. Please enter a valid passport number."
        if not re.match(r"^[A-Z0-9]+$", cleaned):
            return "Passport number should contain only letters and digits."
        return None

    # --- Email ---
    if key == "email":
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            return "Please enter a valid email address (e.g. name@example.com)."
        return None

    # --- Phone ---
    if key == "phone":
        digits = re.sub(r"[\s\+\-\(\)]", "", v)
        if not digits.isdigit():
            return "Phone number should contain only digits (and optional +, spaces, or dashes)."
        if len(digits) < 7:
            return "Phone number is too short. Please enter a valid phone number."
        if len(digits) > 15:
            return "Phone number is too long. Please enter a valid phone number."
        return None

    # --- Travel dates (DD/MM/YYYY – DD/MM/YYYY) ---
    if key == "travel_dates":
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
def flow_suffix(state: str, service: Optional[str], channel: str = "web") -> str:
    """Append after LLM response to guide user back into the flow.

    channel: "web" shows apply prompts; "whatsapp" hides them.
    """
    svc_name = SERVICES[service]["name"] if service and service in SERVICES else "your application"
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
        if service and service in SERVICES:
            svc_name = SERVICES[service]["name"]
            return (
                f"\n\n---\n"
                f"Is this sufficient information, or do you need more details?\n"
                f"**Are you interested in starting the application process for {svc_name}?** "
                f"Type **apply** to begin."
            )
        return (
            "\n\n---\n"
            "Is this sufficient information, or do you need more details?"
        )
    return ""
