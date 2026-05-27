"""Per-tenant bot configuration service.

Single read path: ``await get_bot_config(company_id)`` returns a
:class:`BotConfig` populated from the ``tenant_bot_config`` collection,
falling back to module-level defaults for missing fields. Route code uses
this instead of the hardcoded constants that used to live in
``whatsapp_routes.py``, ``facebook_routes.py``, ``consular_routes.py``.

Caching: in-memory TTL (60s by default). Super-admin edits should call
``invalidate_cache(company_id)`` after writing so the change is visible
on the next request.

Templating: stored strings can include ``{{var}}`` and ``{{nested.path}}``
placeholders, resolved against the same config dict (so the system prompt
can reference ``{{bot_name}}`` and ``{{contact.phone}}``). Unknown
placeholders are left intact (no exception) — easier debugging than
silent empty strings.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from database import get_database

logger = logging.getLogger("services.bot_config")


# ── Defaults applied when a field is missing on the stored row ──────────────

DEFAULT_CONFIG: Dict[str, Any] = {
    "bot_name":       "Assistant",
    "bot_avatar_url": None,
    "org_name":       "",
    "org_short_name": "",
    # Per-tenant feature toggles. The widget reads these via widget-config
    # and uses them to gate the corresponding input controls. Camera and
    # file_upload are *also* gated by per-turn ui_hints from the chat
    # stream — these flags are the global on/off; the hint is the
    # in-the-moment "show now" signal. voice_input is purely tenant-level
    # since the mic affordance doesn't depend on bot state.
    "features": {
        "voice_input":  True,   # mic icon in the chat input bar
        "file_upload":  True,   # upload affordance — only ever appears when the bot expects a file
        "camera":       True,   # camera capture — same: contextual when on
    },
    # Widget chrome — small bits of copy that appear around the chat
    # rather than inside the chat. Surfaced through public_branding() so the
    # widget can render tenant-specific text instead of the legacy hardcoded
    # CGI strings.
    "header_tagline": "",   # e.g. "🇮🇳 Team Bharat SA" — empty hides the line
    "footer_copy":    "",   # e.g. "Official service of {{org_name}} · {{org_short_name}}"
    "advisories":     [],   # list of {id, type, title, content, active}
    "contact": {
        "address":         "",
        "phone":           "",
        "emergency_phone": "",
        "email":           "",
        "website":         "",
        "office_hours":    "",
        "consular_hours":  "",
    },
    # ISD/country code (digits only, no leading "+") used to normalise inbound
    # phone numbers — e.g. "27" for South Africa, "91" for India. Empty string
    # disables country-code mangling and accepts numbers as-supplied.
    "phone_country_code": "",
    # Knowledge-base scrape sources. Empty by default — every tenant supplies
    # its own URLs. See backend/knowledge_scraper.py:_load_scrape_sources.
    "knowledge_sources": {
        "primary_url":    "",       # main site crawled on each refresh
        "sub_pages":      [],       # additional pages on the same domain
        "secondary_urls": [],       # auxiliary sources (e.g. visa provider)
    },
    # Intent keywords — per-tenant phrase lists that drive intent
    # classification (intent_classifier.py) without code changes. Each entry
    # is a list of substrings; the classifier scores by overlap. Leaving a
    # category empty means "use the platform default" (where one exists),
    # so tenants can override only the categories they care about.
    "intent_keywords": {},   # {category: [str, ...]}
    # Flow keywords — phrase sets that drive intent detection inside
    # application_flow (apply / yes / no / discard / continue, etc.).
    # Leaving a key empty falls back to the platform default.
    "flow_keywords": {
        "apply":    [], "yes":     [], "no":   [],
        "discard":  [], "continue":[],
        "menu":     [], "my_applications": [],
    },
    # Escalation rules — when to flag a message for a human handoff.
    # All fields optional; missing keys fall back to the platform defaults
    # baked into EscalationService.
    "escalation_rules": {
        "keywords":             [],     # generic complaint/request triggers
        "patterns":             [],     # regex patterns (Python re syntax)
        "complaint_keywords":   [],     # subset that gets HIGH priority
        "emergency_keywords":   [],     # subset that gets URGENT priority
        "emergency_keywords_by_lang": {},   # {lang_code: [str]} per-language emergency triggers
        "blocked_patterns":     [],     # regex patterns that should be silently dropped (spam)
        "priority_responses": {         # {priority: response_text}
            "urgent": "", "high": "", "medium": "", "low": "",
        },
        "emergency_response_by_lang": {},   # {lang_code: response_text}
        "consecutive_failure_threshold": 0,  # 0 → platform default (3)
    },
    # Security & limits — OTP, session, upload caps. 0 / "" / [] means
    # "use the platform-level default" baked into the consumer code; tenants
    # can override any subset without restating the rest.
    "security_config": {
        "otp_ttl_minutes":              0,    # 0 → use platform default (10)
        "otp_max_attempts":             0,    # 0 → use platform default (3)
        "otp_lockout_minutes":          0,    # 0 → use platform default (5)
        "otp_dev_value":                "",   # empty → platform default ("123456")
        "session_inactivity_minutes":   0,    # 0 → 10
        "client_inactivity_minutes":    0,    # 0 → 10 (frontend idle logout)
        "upload_max_bytes":             0,    # 0 → 5_242_880 (5 MB)
        "upload_max_pdf_pages":         0,    # 0 → 5
        "upload_allowed_mime_types":    [],   # [] → ["application/pdf","image/jpeg","image/png","image/jpg"]
    },
    # OCR pattern extraction — heuristics applied to uploaded-document text
    # to auto-fill form fields. All optional; empty values inherit the
    # platform fallback in services.seva_setu_auth_routes._parse_ocr_text.
    # ``passport_regex`` should match exactly one captured group containing
    # the document number. ``name_blocklist`` lists ALL-CAPS tokens that
    # the name extractor should skip (e.g. "PASSPORT", "REPUBLIC").
    "ocr_patterns": {
        "passport_regex":  "",   # e.g. r"\b[A-Z]{1,2}\d{6,8}\b" (Indian); set to your country's format
        "name_blocklist":  [],   # e.g. ["PASSPORT","REPUBLIC","NATIONALITY"]
        "date_regex":      "",   # e.g. r"\b(\d{2}[/\-]\d{2}[/\-]\d{4})\b" — DD/MM/YYYY or DD-MM-YYYY
    },
    # KB taxonomy — tenants supply their own list of category slugs. Empty
    # falls back to the neutral platform set in ``DEFAULT_KNOWLEDGE_CATEGORIES``;
    # admin_routes validates POST /knowledge against the resolved list, and
    # the dashboards render the resolved list as the category dropdown.
    "knowledge_categories": [],   # e.g. ["passport","visa","fees","emergency","general"]
    "system_prompt_template": "You are {{bot_name}}, a helpful assistant. Be concise and accurate.",
    "supported_languages": [{"code": "en", "name": "English"}],
    "default_language":    "en",
    "branding": {
        "primary_color":   "#1A237E",
        "secondary_color": "#FF6F00",
        "logo_url":        None,
        "favicon_url":     None,
    },
    # PDF branding — colours/strings used by services.pdf_service.
    # Empty/missing keys fall back to neutral defaults inside pdf_service.
    "pdf_branding": {
        "header_color":    "",
        "accent_color":    "",
        "highlight_color": "",
        "stripe_colors":   [],
        "notice_bg":       "",
        "muted_text":      "",
        "border":          "",
        "footer_text":     "",
        "notice_text":     "",
    },
    "fallback_responses": {
        "greeting":      "Hello! How can I help?",
        "out_of_scope":  "I can only help with topics relevant to this service.",
        "error":         "Something went wrong. Please try again.",
        "blocked_input": "I cannot process that request.",
    },
}


# ── BotConfig dataclass ─────────────────────────────────────────────────────

@dataclass
class BotConfig:
    company_id: str
    bot_name: str
    bot_avatar_url: Optional[str]
    org_name: str
    org_short_name: str
    header_tagline: str
    footer_copy: str
    advisories: List[Dict[str, Any]]
    contact: Dict[str, str]
    phone_country_code: str
    system_prompt_template: str
    supported_languages: List[Dict[str, str]]
    default_language: str
    branding: Dict[str, Any]
    pdf_branding: Dict[str, Any]
    fallback_responses: Dict[str, str]
    raw: Dict[str, Any] = field(default_factory=dict)  # for renderer lookups

    # ── rendering ────────────────────────────────────────────────────────

    def render(self, template: str) -> str:
        """Resolve ``{{var}}`` and ``{{nested.path}}`` placeholders against
        this config. Unknown paths are left as-is so they surface clearly
        rather than disappearing into empty strings."""
        if not template:
            return ""
        return _PLACEHOLDER_RE.sub(self._resolve_match, template)

    def system_prompt(self) -> str:
        """Fully-rendered system prompt ready to send to the LLM."""
        return self.render(self.system_prompt_template)

    def fallback(self, key: str) -> str:
        """One named fallback response, rendered. Empty string if missing."""
        raw = self.fallback_responses.get(key, "")
        return self.render(raw)

    def language_codes(self) -> List[str]:
        return [lang["code"] for lang in self.supported_languages if lang.get("code")]

    def flow_keywords(self, category: str, default: Optional[List[str]] = None) -> List[str]:
        """Return the tenant's keyword list for a flow category (apply / yes /
        no / discard / continue / menu / my_applications). When the tenant
        hasn't overridden it, returns ``default`` (which the caller should
        supply with the platform fallback)."""
        fk = self.raw.get("flow_keywords") or {}
        v = fk.get(category) or []
        if v:
            return [str(x).lower() for x in v if x]
        return list(default or [])

    def intent_keywords(self, category: str, default: Optional[List[str]] = None) -> List[str]:
        """Return the tenant's keyword list for an intent category. When
        the tenant hasn't overridden it, returns the platform default
        passed by the caller."""
        ik = self.raw.get("intent_keywords") or {}
        v = ik.get(category) or []
        if v:
            return [str(x).lower() for x in v if x]
        return list(default or [])

    def knowledge_categories(self) -> List[str]:
        """Return the resolved KB-category list (tenant-configured, with the
        neutral platform fallback when empty). Admin dashboards render this
        as the category dropdown and POST /knowledge validates against it."""
        from services.knowledge_service import resolve_knowledge_categories
        return resolve_knowledge_categories(self.raw.get("knowledge_categories") or [])

    def escalation(self) -> Dict[str, Any]:
        """Resolved escalation rules — every key has a sensible default
        when the tenant hasn't overridden it. Returns the union of the
        platform default and the tenant's stored rules."""
        er = self.raw.get("escalation_rules") or {}
        defaults_keywords = [
            "speak to human", "talk to person", "real person", "agent",
            "complaint", "complain", "frustrated", "angry", "upset",
            "manager", "supervisor", "not working", "useless", "terrible",
            "sue", "lawyer", "legal", "court", "refund",
        ]
        defaults_patterns = [
            r"(speak|talk).*(human|person|agent|someone)",
            r"(file|make|lodge).*complaint",
            r"(frustrated|angry|upset|disappointed)",
            r"not.*(helpful|working|satisfied|happy)",
            r"(lawyer|legal|court|sue)",
        ]
        defaults_complaint = ["complaint", "complain", "sue", "lawyer", "legal", "refund"]
        defaults_emergency = ["emergency", "urgent", "help", "arrested", "detained",
                              "hospital", "accident", "death", "stranded", "crisis"]
        return {
            "keywords":           list(er.get("keywords") or defaults_keywords),
            "patterns":           list(er.get("patterns") or defaults_patterns),
            "complaint_keywords": list(er.get("complaint_keywords") or defaults_complaint),
            "emergency_keywords": list(er.get("emergency_keywords") or defaults_emergency),
            "emergency_keywords_by_lang": dict(er.get("emergency_keywords_by_lang") or {}),
            "blocked_patterns":   list(er.get("blocked_patterns") or []),
            "priority_responses": dict(er.get("priority_responses") or {}),
            "emergency_response_by_lang": dict(er.get("emergency_response_by_lang") or {}),
            "consecutive_failure_threshold": int(er.get("consecutive_failure_threshold") or 3),
        }

    def security(self) -> Dict[str, Any]:
        """Resolved security/limits dict — every key has a sensible default
        when the tenant hasn't overridden it. Consumers should read from
        this rather than the raw ``security_config`` dict so they never
        have to handle the 0/empty sentinels themselves."""
        sc = self.raw.get("security_config") or {}
        defaults = {
            "otp_ttl_minutes":            10,
            "otp_max_attempts":           3,
            "otp_lockout_minutes":        5,
            "otp_dev_value":              "123456",
            "session_inactivity_minutes": 10,
            "client_inactivity_minutes":  10,
            "upload_max_bytes":           5 * 1024 * 1024,
            "upload_max_pdf_pages":       5,
            "upload_allowed_mime_types":  ["application/pdf", "image/jpeg", "image/png", "image/jpg"],
        }
        out = {}
        for k, dflt in defaults.items():
            v = sc.get(k)
            # Treat 0 / empty-string / empty-list as "not configured" so
            # super-admins don't need to repeat defaults to override one key.
            if v in (0, "", None, []):
                out[k] = dflt
            else:
                out[k] = v
        return out

    def public_branding(self) -> Dict[str, Any]:
        """Subset safe to expose to unauthenticated widget callers.

        Chat-chrome copy (greeting, advisories, tagline, footer) is rendered
        through ``self.render()`` so placeholders like ``{{org_name}}`` work
        the same way they do in the system prompt.
        """
        # Greeting lives in fallback_responses to avoid duplicating that
        # concept — admins already edit it there. Empty string falls back
        # to the widget's built-in default.
        greeting = self.render(self.fallback_responses.get("greeting") or "")
        rendered_advisories = []
        for adv in (self.advisories or []):
            if not isinstance(adv, dict) or not adv.get("active", True):
                continue
            rendered_advisories.append({
                "id":      adv.get("id") or f"adv_{len(rendered_advisories)}",
                "type":    adv.get("type") or "info",
                "title":   self.render(adv.get("title") or ""),
                "content": self.render(adv.get("content") or ""),
            })
        # Expose only the *client-side* security knobs (file size cap, idle
        # timeout) — never the OTP secrets / TTL.
        sec = self.security()
        client_security = {
            "client_inactivity_minutes": sec["client_inactivity_minutes"],
            "upload_max_bytes":          sec["upload_max_bytes"],
            "upload_max_pdf_pages":      sec["upload_max_pdf_pages"],
            "upload_allowed_mime_types": sec["upload_allowed_mime_types"],
        }
        # Per-tenant feature toggles surfaced to the widget. Missing fields
        # default to True (preserves legacy behaviour for tenants that
        # don't have the `features` block on their stored row yet).
        stored_features = (self.raw.get("features") or {}) if isinstance(self.raw, dict) else {}
        features = {
            "voice_input":  bool(stored_features.get("voice_input",  True)),
            "file_upload":  bool(stored_features.get("file_upload",  True)),
            "camera":       bool(stored_features.get("camera",       True)),
        }
        return {
            "bot_name":       self.bot_name,
            "bot_avatar_url": self.bot_avatar_url,
            "org_name":       self.org_name,
            "org_short_name": self.org_short_name,
            "header_tagline": self.render(self.header_tagline),
            "footer_copy":    self.render(self.footer_copy),
            "greeting":       greeting,
            "advisories":     rendered_advisories,
            "branding":       self.branding,
            "supported_languages": self.supported_languages,
            "default_language":    self.default_language,
            "knowledge_categories": self.knowledge_categories(),
            "security":            client_security,
            "features":            features,
        }

    # ── internals ────────────────────────────────────────────────────────

    def _resolve_match(self, m: re.Match) -> str:
        path = m.group(1).strip()
        cur: Any = self.raw
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return m.group(0)   # leave the {{...}} verbatim
        if cur is None:
            return ""
        return str(cur)


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


# ── TTL cache ───────────────────────────────────────────────────────────────
# TTL is now a platform-config knob. The previous 60s constant lives in
# services.platform_config.DEFAULTS["cache_bot_config_ttl_seconds"]; super
# admins tune it via the Platform Settings tab. Cached at lookup time so
# changes apply on the next ``get_bot_config()`` call without a restart.
_cache: Dict[str, tuple[float, BotConfig]] = {}   # company_id -> (expiry_monotonic, cfg)


def _cache_ttl() -> int:
    """Resolved TTL in seconds. Falls back to 60 if platform_config has not
    loaded yet (cold start). Cheap — synchronous in-process lookup."""
    try:
        from services import platform_config
        return int(platform_config.get("cache_bot_config_ttl_seconds", 60))
    except Exception:
        return 60


def invalidate_cache(company_id: Optional[str] = None) -> None:
    """Drop a single tenant from the cache, or the whole cache if None."""
    if company_id is None:
        _cache.clear()
    else:
        _cache.pop(company_id, None)


# ── public API ──────────────────────────────────────────────────────────────

def _merge_with_defaults(stored: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-merge per top-level key, deep-merge for the few nested dicts
    where it matters (contact, branding, pdf_branding, knowledge_sources,
    fallback_responses). Keeps stored values precedent; defaults fill in
    missing fields only."""
    out = {**DEFAULT_CONFIG, **(stored or {})}
    for key in ("contact", "branding", "pdf_branding", "knowledge_sources", "intent_keywords", "flow_keywords", "escalation_rules", "security_config", "ocr_patterns", "fallback_responses"):
        out[key] = {**DEFAULT_CONFIG[key], **(stored.get(key) or {})}
    return out


async def get_bot_config(company_id: str) -> BotConfig:
    """Return the tenant's bot config (cached). Tenants without a stored
    row get the module defaults — never raises for "no config"."""
    now = time.monotonic()
    cached = _cache.get(company_id)
    if cached and cached[0] > now:
        return cached[1]

    db = await get_database()
    stored = await db.tenant_bot_config.find_one(
        {"company_id": company_id}, {"_id": 0}
    ) or {}

    merged = _merge_with_defaults(stored)
    merged["company_id"] = company_id

    cfg = BotConfig(
        company_id=company_id,
        bot_name=merged["bot_name"],
        bot_avatar_url=merged["bot_avatar_url"],
        org_name=merged["org_name"],
        org_short_name=merged["org_short_name"],
        header_tagline=merged.get("header_tagline") or "",
        footer_copy=merged.get("footer_copy") or "",
        advisories=list(merged.get("advisories") or []),
        contact=merged["contact"],
        phone_country_code=str(merged.get("phone_country_code") or "").lstrip("+").strip(),
        system_prompt_template=merged["system_prompt_template"],
        supported_languages=merged["supported_languages"],
        default_language=merged["default_language"],
        branding=merged["branding"],
        pdf_branding=merged["pdf_branding"],
        fallback_responses=merged["fallback_responses"],
        raw=merged,
    )

    _cache[company_id] = (now + _cache_ttl(), cfg)
    return cfg
