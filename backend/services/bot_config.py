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
    "contact": {
        "address":         "",
        "phone":           "",
        "emergency_phone": "",
        "email":           "",
        "website":         "",
        "office_hours":    "",
        "consular_hours":  "",
    },
    "system_prompt_template": "You are {{bot_name}}, a helpful assistant. Be concise and accurate.",
    "supported_languages": [{"code": "en", "name": "English"}],
    "default_language":    "en",
    "branding": {
        "primary_color":   "#1A237E",
        "secondary_color": "#FF6F00",
        "logo_url":        None,
        "favicon_url":     None,
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
    contact: Dict[str, str]
    system_prompt_template: str
    supported_languages: List[Dict[str, str]]
    default_language: str
    branding: Dict[str, Any]
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

    def public_branding(self) -> Dict[str, Any]:
        """Subset safe to expose to unauthenticated widget callers."""
        return {
            "bot_name":       self.bot_name,
            "bot_avatar_url": self.bot_avatar_url,
            "org_name":       self.org_name,
            "org_short_name": self.org_short_name,
            "branding":       self.branding,
            "supported_languages": self.supported_languages,
            "default_language":    self.default_language,
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

_CACHE_TTL_SECONDS = 60
_cache: Dict[str, tuple[float, BotConfig]] = {}   # company_id -> (expiry_monotonic, cfg)


def invalidate_cache(company_id: Optional[str] = None) -> None:
    """Drop a single tenant from the cache, or the whole cache if None."""
    if company_id is None:
        _cache.clear()
    else:
        _cache.pop(company_id, None)


# ── public API ──────────────────────────────────────────────────────────────

def _merge_with_defaults(stored: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-merge per top-level key, deep-merge for the few nested dicts
    where it matters (contact, branding, fallback_responses). Keeps stored
    values precedent; defaults fill in missing fields only."""
    out = {**DEFAULT_CONFIG, **(stored or {})}
    for key in ("contact", "branding", "fallback_responses"):
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
        contact=merged["contact"],
        system_prompt_template=merged["system_prompt_template"],
        supported_languages=merged["supported_languages"],
        default_language=merged["default_language"],
        branding=merged["branding"],
        fallback_responses=merged["fallback_responses"],
        raw=merged,
    )

    _cache[company_id] = (now + _CACHE_TTL_SECONDS, cfg)
    return cfg
