"""0005 — Seed `tenant_bot_config` for the default tenant.

Extracts the values that are currently hardcoded across the codebase
(bot name, org info, contact details, system prompt, supported languages,
branding) into a DB-backed row. Sprint 3B/3C will refactor the route code
to read from this row instead of using the hardcoded constants.

Idempotent: if a `tenant_bot_config` row already exists for the default
tenant, this migration is a no-op (operator may have customised it via
the super-admin endpoints since the framework landed).

Source of the seeded values:
  - whatsapp_routes.py:60-113      (system prompt, fees, address, hours)
  - consular_routes.py:131-200     (supported languages)
  - frontend/src/components/ChatWidget.jsx:43  (bot avatar URL)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

VERSION = 5
DESCRIPTION = "Seed tenant_bot_config for the default tenant from hardcoded values"

logger = logging.getLogger("migrations.0005")


def _seed_doc(company_id: str, now: str) -> dict:
    """The default-tenant seed. Mirrors what the legacy code uses today so
    flipping to DB-driven config preserves identical behavior."""
    return {
        "company_id": company_id,

        # Bot identity
        "bot_name":        "Seva Setu",
        "bot_avatar_url":  "https://customer-assets.emergentagent.com/job_f1ba93b6-bc56-405e-acef-b08fd09a76e6/artifacts/dq7yfeob_image2url.com_2026-02-04_06-21-50.jpg",
        "org_name":        "Consulate General of India, Johannesburg",
        "org_short_name":  "CGI Johannesburg",

        # Contact info — lifted from whatsapp_routes.py:64-71
        "contact": {
            "address":          "2nd Floor, Sandown Mews East, 88 Stella Street, Sandton, Johannesburg",
            "phone":            "+27 11 783 0202",
            "emergency_phone":  "(+27) 11 581 9800",
            "email":            "cons.joburg@mea.gov.in",
            "website":          "https://www.cgijoburg.gov.in",
            "office_hours":     "Mon-Fri 9:00 AM - 5:30 PM",
            "consular_hours":   "Mon-Fri 9:00 AM - 12:30 PM",
        },

        # System prompt template. Uses {{bot_name}} / {{org_name}} placeholders so
        # the same template can be re-used across tenants by swapping just the
        # identity vars. The renderer (bot_config service in 3B) does the
        # substitution before sending to the LLM.
        "system_prompt_template": (
            "You are {{bot_name}}, the official AI assistant for the "
            "{{org_name}} ({{org_short_name}}).\n\n"
            "KNOWLEDGE BASE - {{org_short_name}}:\n\n"
            "**Office Information:**\n"
            "- Address: {{contact.address}}\n"
            "- Phone: {{contact.phone}}\n"
            "- Emergency: {{contact.emergency_phone}} (24/7)\n"
            "- Email: {{contact.email}}\n"
            "- Website: {{contact.website}}\n"
            "- Hours: {{contact.office_hours}}\n"
            "- Consular Services: {{contact.consular_hours}}\n\n"
            "RESPONSE RULES:\n"
            "1. Keep responses SHORT (3-5 sentences max for simple queries)\n"
            "2. For complex queries, give brief answer + suggest web portal\n"
            "3. Always provide relevant contact/link\n"
            "4. Match user's language\n"
            "5. Be helpful and professional\n\n"
            "RESPOND TO USER:"
        ),

        # Supported languages — lifted from consular_routes.py:132-180
        "supported_languages": [
            {"code": "en",  "name": "English"},
            {"code": "hi",  "name": "Hindi"},
            {"code": "bn",  "name": "Bengali"},
            {"code": "mr",  "name": "Marathi"},
            {"code": "te",  "name": "Telugu"},
            {"code": "ta",  "name": "Tamil"},
            {"code": "gu",  "name": "Gujarati"},
            {"code": "ur",  "name": "Urdu"},
            {"code": "kn",  "name": "Kannada"},
            {"code": "or",  "name": "Odia"},
            {"code": "ml",  "name": "Malayalam"},
            {"code": "pa",  "name": "Punjabi"},
            {"code": "as",  "name": "Assamese"},
            {"code": "mai", "name": "Maithili"},
            {"code": "sa",  "name": "Sanskrit"},
            {"code": "sat", "name": "Santali"},
            {"code": "ks",  "name": "Kashmiri"},
            {"code": "ne",  "name": "Nepali"},
            {"code": "sd",  "name": "Sindhi"},
            {"code": "doi", "name": "Dogri"},
            {"code": "kok", "name": "Konkani"},
            {"code": "mni", "name": "Manipuri"},
            {"code": "brx", "name": "Bodo"},
            {"code": "mwr", "name": "Marwari"},
            {"code": "zu",  "name": "Zulu"},
            {"code": "xh",  "name": "Xhosa"},
            {"code": "af",  "name": "Afrikaans"},
            {"code": "nso", "name": "Sepedi"},
            {"code": "tn",  "name": "Setswana"},
            {"code": "st",  "name": "Sesotho"},
        ],
        "default_language": "en",

        # Frontend branding — fetched by the widget on boot (Sprint 3E)
        "branding": {
            "primary_color":  "#1A237E",
            "secondary_color": "#FF6F00",
            "logo_url":        None,
            "favicon_url":     None,
        },

        # Deterministic fallback responses. Sprint 3C wires these into the
        # places that currently hardcode "I cannot process that request..."
        # and similar strings.
        "fallback_responses": {
            "greeting":      "🙏 Namaste! Welcome to {{bot_name}}. I can help you with consular services from {{org_short_name}}. What do you need help with?",
            "out_of_scope":  "I can only help with consular services. Please ask about passport, visa, OCI, or other consular matters.",
            "error":         "I'm having trouble processing that right now. Please try again, or contact the office at {{contact.phone}}.",
            "blocked_input": "I cannot process that request. Please ask a question about consular services.",
        },

        "created_at": now,
        "updated_at": now,
        "created_by": "migration_0005",
    }


async def up(db) -> dict:
    company_id = os.environ.get("COMPANY_ID", "").strip()
    if not company_id:
        raise RuntimeError("COMPANY_ID env required (same value as validate_company_id uses).")
    if not await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1}):
        raise RuntimeError(f"company_id {company_id!r} not in `companies` collection.")

    existing = await db.tenant_bot_config.find_one({"company_id": company_id}, {"_id": 0, "company_id": 1})
    if existing:
        logger.info("tenant_bot_config already exists for %s — leaving customisations alone", company_id)
        return {"company_id": company_id, "action": "noop_already_present"}

    now = datetime.now(timezone.utc).isoformat()
    doc = _seed_doc(company_id, now)
    await db.tenant_bot_config.insert_one(doc)
    logger.info("Seeded tenant_bot_config for %s", company_id)
    return {"company_id": company_id, "action": "seeded"}
