"""0006 — Seed `tenant_services` for the default tenant.

Sprint 4 moves per-tenant service definitions (passport, visa, OCI, PCC, ...)
out of a hardcoded dict in `services/application_flow.py` and into the
`tenant_services` collection. This migration seeds the rows for the
default tenant so the 4C refactor is a behaviour-preserving swap.

Each service becomes one row:
  - service_key      — passport, visa, oci, pcc, ...
  - name             — display name (e.g. "Passport Services")
  - description      — info text shown before consent
  - documents        — list of required document descriptions
  - fields           — list of {key, question} pairs for collection
  - category         — TYPE_A (in-house) | TYPE_B (redirect-only)
  - external_url     — for TYPE_B redirects (e.g. VFS Global)
  - enabled          — true (operator can hide via super-admin later)
  - display_order    — preserves dict order so menus are stable

The seed data is inlined here (formerly imported from application_flow.py).
Migrations are historical artifacts — keeping the data here means the
runtime module can shed the dict without breaking re-runs on fresh DBs.

Idempotent: rows that already exist for (company_id, service_key) are
left alone (operator may have customised since the framework landed).
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

VERSION = 6
DESCRIPTION = "Seed tenant_services from the bundled default catalogue for the default tenant"

logger = logging.getLogger("migrations.0006")

# Services that hand the user off to VFS Global rather than collect data
# in-house. Encoded here so the engine can branch on category cleanly.
TYPE_B_SERVICE_KEYS = {"visa", "pcc"}

# External-redirect URLs for TYPE_B services (lifted from the descriptions).
EXTERNAL_URLS = {
    "visa":     "https://indianvisaonline.gov.in/",
    "pcc":      "https://www.cgijoburg.gov.in/page/status-of-indian-passport-pcc/",
    "passport": "https://passportindia.gov.in",
    "oci":      "https://ociservices.gov.in",
}


# ── Default service catalogue ───────────────────────────────────────────────
# Mirrors the CGI Johannesburg service set the chatbot was originally built
# around. The keys/order are load-bearing — they drive menu order and the
# `_SERVICE_PATTERNS` detector in `services/application_flow.py`.
_SERVICES_SEED: Dict[str, Dict[str, Any]] = {
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


def _build_doc(company_id: str, service_key: str, src: Dict[str, Any],
               order: int, now: str) -> Dict[str, Any]:
    category = "TYPE_B" if service_key in TYPE_B_SERVICE_KEYS else "TYPE_A"
    return {
        "id":            str(uuid.uuid4()),
        "company_id":    company_id,
        "service_key":   service_key,
        "name":          src.get("name", service_key.title()),
        "description":   src.get("description", ""),
        "documents":     list(src.get("documents", [])),
        "fields":        list(src.get("fields", [])),
        "category":      category,
        "external_url":  EXTERNAL_URLS.get(service_key),
        "enabled":       True,
        "display_order": order,
        "created_at":    now,
        "updated_at":    now,
        "created_by":    "migration_0006",
    }


async def up(db) -> dict:
    company_id = os.environ.get("COMPANY_ID", "").strip()
    if not company_id:
        raise RuntimeError("COMPANY_ID env required (same value as validate_company_id uses).")
    if not await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1}):
        raise RuntimeError(f"company_id {company_id!r} not in `companies` collection.")

    now = datetime.now(timezone.utc).isoformat()

    stats: Dict[str, int] = {"seeded": 0, "already_present": 0}
    for order, (service_key, src) in enumerate(_SERVICES_SEED.items()):
        existing = await db.tenant_services.find_one(
            {"company_id": company_id, "service_key": service_key},
            {"_id": 0, "service_key": 1},
        )
        if existing:
            stats["already_present"] += 1
            continue

        doc = _build_doc(company_id, service_key, src, order, now)
        await db.tenant_services.insert_one(doc)
        stats["seeded"] += 1

    logger.info("tenant_services seed: %s (company_id=%s)", stats, company_id)
    return stats
