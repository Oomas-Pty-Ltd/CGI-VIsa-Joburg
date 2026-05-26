"""
====================================================================
SEVA SETU BOT - VISA INTENT CLASSIFIER
====================================================================
Rule-based intent classification to reduce LLM calls:
- Keyword-based visa type detection
- Structured intent categories
- Confidence scoring
- Fallback to LLM for ambiguous queries
====================================================================
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class IntentCategory(Enum):
    """Main intent categories"""
    PASSPORT = "passport"
    VISA = "visa"
    OCI = "oci"
    PIO = "pio"
    CONSULAR = "consular"
    APPOINTMENT = "appointment"
    FEES = "fees"
    DOCUMENTS = "documents"
    STATUS = "status"
    EMERGENCY = "emergency"
    OFFICE_INFO = "office_info"
    ESCALATION = "escalation"
    GREETING = "greeting"
    CAPABILITIES = "capabilities"
    LANGUAGE_SWITCH = "language_switch"
    PLATFORM_INFO = "platform_info"
    UNKNOWN = "unknown"


class VisaType(Enum):
    """Visa subcategories"""
    TOURIST = "tourist"
    BUSINESS = "business"
    STUDENT = "student"
    MEDICAL = "medical"
    EMPLOYMENT = "employment"
    CONFERENCE = "conference"
    TRANSIT = "transit"
    E_VISA = "e_visa"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """Result of intent classification"""
    category: IntentCategory
    subcategory: Optional[str] = None
    confidence: float = 0.0
    keywords_matched: List[str] = None
    suggested_response_key: Optional[str] = None
    requires_llm: bool = False
    escalation_needed: bool = False
    
    def __post_init__(self):
        if self.keywords_matched is None:
            self.keywords_matched = []


# =====================================================================
# INTENT PATTERNS
# =====================================================================
INTENT_PATTERNS = {
    IntentCategory.PASSPORT: {
        "keywords": [
            "passport", "पासपोर्ट", "renewal", "renew", "new passport",
            "lost passport", "damaged passport", "tatkal", "tatkaal",
            "passport application", "passport status", "reissue"
        ],
        "patterns": [
            r"(renew|new|lost|damaged|apply).*(passport)",
            r"passport.*(renewal|application|status|fees)",
            r"tatkal.*passport",
            r"how.*(get|apply|renew).*passport"
        ],
        "response_key": "passport_info"
    },
    
    IntentCategory.VISA: {
        "keywords": [
            "visa", "वीज़ा", "tourist visa", "business visa", "student visa",
            "medical visa", "e-visa", "evisa", "visa application",
            "visa fees", "visa requirements", "visa status"
        ],
        "patterns": [
            r"(apply|get|need).*(visa)",
            r"visa.*(application|requirements|fees|status|process)",
            r"(tourist|business|student|medical).*visa",
            r"e-?visa"
        ],
        "response_key": "visa_info",
        "subcategory_patterns": {
            VisaType.TOURIST: [r"tourist", r"tourism", r"holiday", r"vacation", r"visit"],
            VisaType.BUSINESS: [r"business", r"work", r"corporate", r"meeting"],
            VisaType.STUDENT: [r"student", r"study", r"education", r"university", r"college"],
            VisaType.MEDICAL: [r"medical", r"treatment", r"hospital", r"health"],
            VisaType.E_VISA: [r"e-?visa", r"online.*visa", r"electronic.*visa"]
        }
    },
    
    IntentCategory.OCI: {
        "keywords": [
            "oci", "overseas citizen", "oci card", "oci application",
            "oci renewal", "oci status", "oci fees"
        ],
        "patterns": [
            r"oci.*(card|application|renewal|status|fees)",
            r"overseas.*citizen.*india",
            r"(apply|get|renew).*oci"
        ],
        "response_key": "oci_info"
    },
    
    IntentCategory.PIO: {
        "keywords": [
            "pio", "person of indian origin", "pio card", "pio to oci",
            "convert pio"
        ],
        "patterns": [
            r"pio.*(card|conversion|convert)",
            r"person.*indian.*origin",
            r"convert.*pio.*oci"
        ],
        "response_key": "pio_info"
    },
    
    IntentCategory.CONSULAR: {
        "keywords": [
            "attestation", "notary", "birth certificate", "death certificate",
            "marriage certificate", "power of attorney", "poa", "affidavit",
            "document", "registration", "legalization"
        ],
        "patterns": [
            r"(birth|death|marriage).*(certificate|registration)",
            r"(attestation|notary|legalization)",
            r"power.*attorney",
            r"document.*(attestation|verification)"
        ],
        "response_key": "consular_services"
    },
    
    IntentCategory.APPOINTMENT: {
        "keywords": [
            "appointment", "book", "schedule", "slot", "timing",
            "available", "walk-in", "token"
        ],
        "patterns": [
            r"(book|schedule|make).*appointment",
            r"appointment.*(available|slot|timing)",
            r"when.*can.*(come|visit|book)"
        ],
        "response_key": "appointment_info"
    },
    
    IntentCategory.FEES: {
        "keywords": [
            "fees", "cost", "price", "payment", "charges", "how much",
            "rate", "amount"
        ],
        "patterns": [
            r"(how much|what).*(cost|fees|price|charge)",
            r"(fees|cost|price).*(passport|visa|oci)",
            r"payment.*method"
        ],
        "response_key": "fees_info"
    },
    
    IntentCategory.DOCUMENTS: {
        "keywords": [
            "documents", "requirements", "what do i need", "checklist",
            "papers", "proof", "supporting"
        ],
        "patterns": [
            r"(what|which).*documents.*(need|required)",
            r"document.*(list|checklist|requirements)",
            r"(required|supporting).*documents"
        ],
        "response_key": "document_checklist"
    },
    
    IntentCategory.STATUS: {
        "keywords": [
            "status", "track", "tracking", "where is", "check status",
            "application status", "progress"
        ],
        "patterns": [
            r"(check|track|know).*status",
            r"(where|what).*(is|about).*application",
            r"status.*(application|passport|visa|oci)"
        ],
        "response_key": "status_check"
    },
    
    IntentCategory.EMERGENCY: {
        "keywords": [
            "emergency", "urgent", "help", "arrested", "hospital",
            "accident", "death", "stranded", "lost", "stolen", "crisis"
        ],
        "patterns": [
            r"emergency.*(passport|help|contact)",
            r"(arrested|hospital|accident|stranded)",
            r"urgent.*help",
            r"(passport|wallet).*stolen"
        ],
        "response_key": "emergency_contact",
        "escalation": True
    },
    
    IntentCategory.OFFICE_INFO: {
        # Tenant-agnostic office/contact keywords. CGI-specific terms
        # ("cgi", "joburg", "consulate general") used to live here; tenants
        # that want to recognise their own building or city in user messages
        # add them via ``tenant_bot_config.intent_keywords.office_info``.
        "keywords": [
            "address", "location", "office", "timing", "hours", "open",
            "closed", "contact", "phone", "email", "where", "directions",
        ],
        "patterns": [
            r"(where|what).*(office|address|location)",
            r"(office).*(timing|hours|address)",
            r"(contact|phone|email).*(number|address)",
            r"(when|what time).*open",
        ],
        "response_key": "office_info"
    },
    
    IntentCategory.ESCALATION: {
        "keywords": [
            "speak to human", "talk to person", "agent", "complaint",
            "not satisfied", "frustrated", "manager", "supervisor",
            "real person", "human help"
        ],
        "patterns": [
            r"(speak|talk).*(human|person|agent|someone)",
            r"(complaint|complain|frustrated|angry)",
            r"(manager|supervisor)",
            r"not.*(helpful|working|satisfied)"
        ],
        "response_key": "escalation",
        "escalation": True
    },
    
    IntentCategory.GREETING: {
        "keywords": [
            "hello", "hi", "hey", "namaste", "good morning", "good afternoon",
            "good evening", "thanks", "thank you", "bye", "goodbye"
        ],
        "patterns": [
            r"^(hi|hello|hey|namaste)[\s!?.]*$",
            r"^good\s*(morning|afternoon|evening)[\s!?.]*$",
            r"^(thanks|thank you|bye|goodbye)[\s!?.]*$"
        ],
        "response_key": "greeting"
    },

    IntentCategory.LANGUAGE_SWITCH: {
        "keywords": [
            "switch language", "change language", "speak hindi", "respond in hindi",
            "in hindi", "in english", "in tamil", "in telugu", "in bengali",
            "in marathi", "in gujarati", "in urdu", "in kannada", "in malayalam",
            "in punjabi", "in odia", "in assamese", "in nepali", "in arabic",
            "in french", "in swahili", "in zulu", "in xhosa", "in afrikaans",
            "language change", "set language", "mujhe hindi mein", "hindi mein baat",
        ],
        "patterns": [
            r"(switch|change|set)\s+(the\s+)?language\s*(to\s+\w+)?",
            r"(speak|respond|reply|answer|talk)\s+(to\s+me\s+)?(in|using)\s+\w+",
            r"(in|use)\s+(hindi|english|bengali|marathi|telugu|tamil|gujarati|urdu|kannada|malayalam|punjabi|odia|assamese|nepali|arabic|french|swahili|zulu|xhosa|afrikaans|sesotho|setswana)",
            r"(mujhe\s+)?(hindi|bengali|marathi)\s+(mein|me)\s+(baat|jawab|batao)",
            r"^(hindi|english|tamil|telugu|bengali|marathi|gujarati|urdu|kannada|malayalam|french|arabic|swahili|zulu|afrikaans)[\s!?.]*$",
        ],
        "response_key": "language_switch"
    },

    IntentCategory.PLATFORM_INFO: {
        "keywords": [
            "pricing plan", "pricing plans", "price plan", "subscription",
            "customize", "customise", "custom services", "personalize", "personalise",
            "trust", "trustworthy", "reliable", "secure", "safe", "legitimate", "official",
            "sign up", "signup", "register", "create account", "get started", "onboard",
            "how to use", "how does this work", "how do i begin", "getting started",
            "platform", "bot policy", "data privacy", "privacy policy",
            "do you offer", "is this free", "free to use", "no cost",
            "different from others", "unique", "better than", "stand out", "advantage",
            "why choose", "what makes you", "special about", "compared to", "versus",
            "unique features", "key benefits", "value proposition", "why use",
            "competitive", "compared to others", "sets you apart", "differentiator",
        ],
        "patterns": [
            r"(do\s+you|is\s+there)\s+(offer|have)\s+(pricing|plans?|subscription)",
            r"(pricing|price)\s+(plan|plans?|tier|tiers?|structure)",
            r"(can|how)\s+(i|do\s+i)\s+(customize|customise|personalize|personalise)",
            r"why\s+(should|can)\s+i\s+trust",
            r"(is|are)\s+(this|you|your\s+platform)\s+(safe|secure|official|legitimate|reliable|trustworthy)",
            r"(help|guide|walk)\s+me\s+(to\s+)?(sign\s*up|register|get\s+started|onboard)",
            r"(how\s+(do|can)\s+i\s+)?(sign\s*up|register|get\s+started|start\s+using)",
            r"^(get\s+started|sign\s*up|register)[\s!?.]*$",
            r"(is\s+(this|it)\s+free|free\s+to\s+use|no\s+charge\s+for\s+bot)",
            r"(what\s+makes?\s+(your?|this)\s+(platform|bot|service|you)\s+(different|unique|special|better))",
            r"(how\s+(are|is)\s+(you|this|your?\s+\w+)\s+different\s+(from|than|to))",
            r"(why\s+(should|would|do)\s+i\s+(use|choose|pick|prefer|trust)\s+(you|this|your?\s+\w+))",
            r"(what\s+(sets?\s+you|makes?\s+you)\s+apart)",
            r"(different|unique|better|special)\s+(from|than|to|compared)",
            r"(advantage|benefit|benefit|unique\s+feature|key\s+feature)",
            r"(compare|versus|vs\.?)\s+(other|another)",
        ],
        "response_key": "platform_info"
    },

    IntentCategory.CAPABILITIES: {
        "keywords": [
            "features", "services", "what can you do", "what do you do",
            "help me", "how can you help", "capabilities", "what can i ask",
            "what do you offer", "what are you", "tell me about yourself",
            "what services", "menu", "options", "assist", "support"
        ],
        "patterns": [
            r"what\s+(can|do)\s+you\s+(do|offer|help|provide|assist)",
            r"(list|show|tell me).*\b(services|features|options|capabilities)\b",
            r"\b(services|features|capabilities)\b.*(available|offer|provide)",
            r"how\s+can\s+(you|i).*(help|assist|use)",
            r"what\s+(services?|help|assistance)\s+(do\s+you|can\s+you|are)\s+",
            r"^(help|menu|options?)[\s!?.]*$",
            r"(what|which)\s+(can|do)\s+i\s+(ask|do|get|request)",
            r"what\s+are\s+(your\s+)?(services?|features?|options?|capabilities?)",
            r"(show|tell|list)\s+(me\s+)?(your\s+)?(services?|features?|options?|capabilities?)",
            r"^(services?|features?)[\s!?.]*$",
        ],
        "response_key": "capabilities"
    }
}


# Platform-default name → code map used when a tenant hasn't configured
# its own ``supported_languages``. Tenants extend or override this via
# ``bot_config.supported_languages[].name``/``native_name``/``aliases``.
LANGUAGE_NAME_TO_CODE = {
    "english": "en",
    "hindi": "hi", "हिंदी": "hi", "हिन्दी": "hi",
    "bengali": "bn", "bangla": "bn", "বাংলা": "bn",
    "marathi": "mr", "मराठी": "mr",
    "telugu": "te", "తెలుగు": "te",
    "tamil": "ta", "தமிழ்": "ta",
    "gujarati": "gu", "ગુજરાતી": "gu",
    "urdu": "ur", "اردو": "ur",
    "kannada": "kn", "ಕನ್ನಡ": "kn",
    "malayalam": "ml", "മലയാളം": "ml",
    "punjabi": "pa", "ਪੰਜਾਬੀ": "pa",
    "odia": "or", "oriya": "or", "ଓଡ଼ିଆ": "or",
    "assamese": "as", "অসমীয়া": "as",
    "nepali": "ne", "नेपाली": "ne",
    "arabic": "ar", "العربية": "ar",
    "french": "fr", "français": "fr",
    "swahili": "sw", "kiswahili": "sw",
    "zulu": "zu", "isizulu": "zu",
    "xhosa": "xh", "isixhosa": "xh",
    "afrikaans": "af",
    "sesotho": "st", "sotho": "st",
    "setswana": "tn", "tswana": "tn",
}


def _build_tenant_lang_map(supported_languages: list) -> dict:
    """Build a {name_lower: code} map from a tenant's supported_languages
    list. Includes the English label, native script label, and any
    operator-supplied aliases. Empty / malformed rows are skipped."""
    out: dict = {}
    for entry in (supported_languages or []):
        if not isinstance(entry, dict):
            continue
        code = (entry.get("code") or "").strip().lower()
        if not code:
            continue
        for raw in (entry.get("name"), entry.get("native_name"), *(entry.get("aliases") or [])):
            label = (str(raw) if raw else "").strip().lower()
            if label:
                out[label] = code
    return out


async def detect_target_language(text: str, company_id: Optional[str] = None):
    """Extract the target language code from a language-switch message.

    When ``company_id`` is supplied the tenant's configured
    ``supported_languages`` map is consulted first (so e.g. a tenant who
    serves only English + Hindi never accidentally matches "Tamil" in
    free text). Returns None if nothing matches.
    """
    if not text:
        return None
    text_lower = text.lower()

    tenant_map: dict = {}
    if company_id:
        try:
            from services.bot_config import get_bot_config
            cfg = await get_bot_config(company_id)
            tenant_map = _build_tenant_lang_map(cfg.supported_languages or [])
        except Exception:
            tenant_map = {}

    # Tenant map first — tenants can both add aliases and (by leaving rows
    # out) implicitly disable detection of languages they don't serve.
    for name, code in tenant_map.items():
        if name and name in text_lower:
            return code
    # Fall back to the platform map only if the tenant didn't configure any
    # languages (legacy tenants) — avoid surprising cross-tenant matches.
    if not tenant_map:
        for name, code in LANGUAGE_NAME_TO_CODE.items():
            if name in text_lower:
                return code
    return None


# ── Per-tenant intent-keyword cache ─────────────────────────────────────────
# Populated by ``preload_intent_keywords(company_id)`` at request entry.
# Each entry is a copy of ``INTENT_PATTERNS`` with each category's
# ``keywords`` list **replaced** by the tenant's override when present.
# Sync ``classify()`` reads from this cache so we don't pay an async
# bot_config lookup on every classification.
_TENANT_INTENT_PATTERNS: Dict[str, Dict[IntentCategory, dict]] = {}


def _category_for_name(name: str) -> Optional[IntentCategory]:
    """Resolve a stringy intent name (from bot_config keys) to the enum.

    Accepts upper/lower/mixed case. Returns None for unknown names so
    tenant typos surface gracefully (logged, ignored) instead of crashing.
    """
    if not name:
        return None
    norm = str(name).strip().upper()
    try:
        return IntentCategory[norm]
    except KeyError:
        return None


def _build_tenant_intent_patterns(tenant_overrides: Dict[str, list]) -> Dict[IntentCategory, dict]:
    """Merge tenant ``intent_keywords`` into a copy of ``INTENT_PATTERNS``.

    Per-category semantics match ``preload_flow_keywords`` in
    application_flow: when the tenant provides a non-empty keyword list
    for a category, it **replaces** the platform default for that category.
    Categories the tenant didn't mention keep their platform default.
    """
    merged: Dict[IntentCategory, dict] = {}
    for cat, cfg in INTENT_PATTERNS.items():
        merged[cat] = dict(cfg)  # shallow copy is enough — only `keywords` is replaced
    for name, kws in (tenant_overrides or {}).items():
        cat = _category_for_name(name)
        if not cat or cat not in merged:
            logger.debug("[intent_classifier] tenant intent override ignored — unknown category %r", name)
            continue
        clean = [str(k).lower() for k in (kws or []) if k]
        if clean:
            merged[cat] = {**merged[cat], "keywords": clean}
    return merged


async def preload_intent_keywords(company_id: Optional[str]) -> None:
    """Populate the per-tenant intent-pattern cache. Call once per request
    before invoking the sync ``classify_intent`` helper. Safe to call
    repeatedly — relies on bot_config's own 60s cache.
    """
    if not company_id:
        return
    try:
        from services.bot_config import get_bot_config
        cfg = await get_bot_config(company_id)
        overrides = (cfg.raw or {}).get("intent_keywords") or {}
        if overrides:
            _TENANT_INTENT_PATTERNS[company_id] = _build_tenant_intent_patterns(overrides)
    except Exception as exc:
        logger.debug("[preload_intent_keywords] %s: %s", company_id, exc)


def _resolve_patterns(tenant_id: Optional[str]) -> Dict[IntentCategory, dict]:
    """Resolved INTENT_PATTERNS for the request — tenant override → platform."""
    if tenant_id and tenant_id in _TENANT_INTENT_PATTERNS:
        return _TENANT_INTENT_PATTERNS[tenant_id]
    return INTENT_PATTERNS


class IntentClassifier:
    """
    Rule-based intent classifier.
    Reduces LLM calls for common, deterministic queries.

    Tenants override the keyword lists per category via
    ``tenant_bot_config.intent_keywords`` (see ``preload_intent_keywords``
    above). Without an override, the platform defaults in
    ``INTENT_PATTERNS`` fire.
    """

    def __init__(self):
        self.patterns = INTENT_PATTERNS
        self.classification_count = 0
        self.llm_fallback_count = 0

    def classify(self, text: str, tenant_id: Optional[str] = None) -> IntentResult:
        """
        Classify user intent from text.

        Returns IntentResult with category, confidence, and whether LLM is needed.
        ``tenant_id`` reads the cache populated by
        :py:func:`preload_intent_keywords` for per-tenant keyword overrides.
        """
        if not text or len(text.strip()) < 2:
            return IntentResult(
                category=IntentCategory.UNKNOWN,
                confidence=0.0,
                requires_llm=True
            )

        text_lower = text.lower().strip()
        # Strip leading/trailing non-word punctuation so "hi'", "hello.", "hi!!!"
        # match the same patterns as "hi" — keeps interior punctuation intact.
        text_lower = re.sub(r"^[^\w]+|[^\w]+$", "", text_lower)
        self.classification_count += 1

        patterns = _resolve_patterns(tenant_id)

        best_match = None
        best_score = 0.0
        matched_keywords = []

        # Check each intent category
        for category, config in patterns.items():
            score, keywords = self._calculate_match_score(text_lower, config)

            if score > best_score:
                best_score = score
                best_match = category
                matched_keywords = keywords

        # Determine if we need LLM
        requires_llm = best_score < 0.5  # Less than 50% confidence

        # CAPABILITIES has a very broad pattern ("tell me about ... services") that
        # outscores specific-service intents when both fire (e.g. "tell me about
        # passport services"). If a specific service is named in the message,
        # route to that service and let the LLM produce a service-specific reply
        # instead of serving the generic Complete Guide template.
        if best_match == IntentCategory.CAPABILITIES:
            _SERVICE_OVERRIDES = (
                (IntentCategory.PASSPORT, ("passport", "पासपोर्ट", "tatkal")),
                (IntentCategory.VISA, ("visa", "वीज़ा", "evisa", "e-visa")),
                (IntentCategory.OCI, ("oci", "overseas citizen")),
                (IntentCategory.PIO, ("pio", "person of indian origin")),
                (IntentCategory.CONSULAR, (
                    "attestation", "affidavit", "power of attorney", "poa", "gpa",
                    "marriage certificate", "death certificate", "birth certificate",
                    "emergency certificate", "ec ", "etd", "surrender", "renunciation",
                    "noc", "notary", "apostille", "legalization",
                )),
                (IntentCategory.FEES, ("fees", "fee schedule", "cost")),
                (IntentCategory.APPOINTMENT, ("appointment", "book a slot")),
                (IntentCategory.OFFICE_INFO, ("office hours", "address", "location", "directions")),
            )
            for _cat, _kws in _SERVICE_OVERRIDES:
                if any(_kw in text_lower for _kw in _kws):
                    best_match = _cat
                    matched_keywords = [_kw for _kw in _kws if _kw in text_lower]
                    requires_llm = True  # need LLM for service-specific answer
                    break

        # For greetings, capabilities, platform info, and language-switch, any pattern
        # match is unambiguous — serve the deterministic response without calling the LLM.
        for _exact_cat in (IntentCategory.GREETING, IntentCategory.CAPABILITIES,
                           IntentCategory.PLATFORM_INFO, IntentCategory.LANGUAGE_SWITCH):
            if best_match == _exact_cat:
                for pat in patterns[_exact_cat].get("patterns", []):
                    if re.search(pat, text_lower, re.IGNORECASE):
                        requires_llm = False
                        break
                break

        # Safety net: short messages starting with a greeting word still resolve
        # to GREETING even if the pattern missed (e.g. "hii", "hellooo there").
        # The platform default greeting set covers the common surfaces;
        # tenants who need different greetings (e.g. "salaam", "hola") add
        # them via intent_keywords.GREETING.
        if requires_llm and len(text_lower) <= 25:
            _greeting_starts = patterns.get(IntentCategory.GREETING, {}).get("keywords") or []
            # Take the first 6 short tokens as the "startswith" set to keep
            # the safety net cheap.
            _safety_net = [g for g in _greeting_starts if len(g) <= 12][:6] or ["hello", "hey", "hi"]
            for _g in _safety_net:
                if text_lower.startswith(_g.lower()):
                    best_match = IntentCategory.GREETING
                    requires_llm = False
                    matched_keywords = [_g]
                    break

        if requires_llm:
            self.llm_fallback_count += 1

        # Check for subcategory (e.g., visa type)
        subcategory = None
        if best_match == IntentCategory.VISA:
            subcategory = self._detect_visa_type(text_lower)

        # Check if escalation is needed
        escalation_needed = False
        if best_match and patterns.get(best_match, {}).get("escalation"):
            escalation_needed = True

        result = IntentResult(
            category=best_match or IntentCategory.UNKNOWN,
            subcategory=subcategory.value if subcategory else None,
            confidence=best_score,
            keywords_matched=matched_keywords,
            suggested_response_key=patterns.get(best_match, {}).get("response_key"),
            requires_llm=requires_llm,
            escalation_needed=escalation_needed
        )
        
        logger.debug(f"Intent classified: {result.category.value} (confidence: {result.confidence:.2f})")
        
        return result
    
    def _calculate_match_score(self, text: str, config: Dict) -> Tuple[float, List[str]]:
        """Calculate match score for a category"""
        keyword_score = 0.0
        pattern_score = 0.0
        matched = []
        
        # Keyword matching (weight: 0.4)
        keywords = config.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in text:
                keyword_score += 1
                matched.append(keyword)
        
        if keywords:
            keyword_score = (keyword_score / len(keywords)) * 0.4
        
        # Pattern matching (weight: 0.6)
        patterns = config.get("patterns", [])
        pattern_matches = 0
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                pattern_matches += 1
        
        if patterns:
            pattern_score = (pattern_matches / len(patterns)) * 0.6
        
        # Boost score if multiple matches
        total_score = keyword_score + pattern_score
        if len(matched) > 2:
            total_score = min(1.0, total_score * 1.2)
        
        return total_score, matched
    
    def _detect_visa_type(self, text: str) -> Optional[VisaType]:
        """Detect specific visa type from text"""
        visa_config = self.patterns.get(IntentCategory.VISA, {})
        subcategory_patterns = visa_config.get("subcategory_patterns", {})
        
        for visa_type, patterns in subcategory_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return visa_type
        
        return VisaType.UNKNOWN
    
    def get_stats(self) -> Dict:
        """Get classifier statistics"""
        total = self.classification_count or 1
        return {
            "total_classifications": self.classification_count,
            "llm_fallbacks": self.llm_fallback_count,
            "rule_based_rate": round((total - self.llm_fallback_count) / total * 100, 1),
            "categories": list(IntentCategory.__members__.keys())
        }


# Global classifier instance
intent_classifier = IntentClassifier()


def classify_intent(text: str, tenant_id: Optional[str] = None) -> IntentResult:
    """Convenience function to classify intent.

    Pass ``tenant_id`` to apply per-tenant ``intent_keywords`` overrides
    (the cache must have been primed via :py:func:`preload_intent_keywords`
    earlier in the request — usually at the route entry-point).
    """
    return intent_classifier.classify(text, tenant_id=tenant_id)


