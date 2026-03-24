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
        "keywords": [
            "address", "location", "office", "timing", "hours", "open",
            "closed", "contact", "phone", "email", "where", "directions"
        ],
        "patterns": [
            r"(where|what).*(office|address|location)",
            r"(office|consulate).*(timing|hours|address)",
            r"(contact|phone|email).*(number|address)",
            r"(when|what time).*open"
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
    }
}


# =====================================================================
# STRUCTURED RESPONSES (Deterministic)
# =====================================================================
STRUCTURED_RESPONSES = {
    "passport_info": {
        "title": "Passport Services",
        "content": """**Indian Passport Services at CGI Johannesburg:**

**Types of Applications:**
• New Passport
• Renewal/Re-issue
• Lost/Damaged Passport
• Tatkal (Urgent)

**Fees:**
• Normal: R1,200 (new), R800 (renewal)
• Tatkal: R2,400 (new), R1,600 (renewal)

**Processing Time:**
• Normal: 4-6 weeks
• Tatkal: 1-2 weeks

**How to Apply:**
1. Book appointment: passportindia.gov.in
2. Fill online application
3. Visit with documents & payment

**Documents Required:**
• Current passport (if renewal)
• Proof of address in SA
• Valid visa/permit
• Passport photos""",
        "source": "CGI Johannesburg Official"
    },
    
    "visa_info": {
        "title": "Indian Visa Information",
        "content": """**Indian Visa Services:**

**Visa Types:**
• Tourist Visa (up to 10 years)
• Business Visa
• Student Visa
• Medical Visa
• E-Visa (online)

**Apply Online:** indianvisaonline.gov.in

**Processing Time:** 3-5 working days

**General Requirements:**
• Valid passport (6+ months validity)
• Completed application form
• Passport photos
• Proof of travel
• Supporting documents (varies by type)""",
        "source": "VFS Global / CGI Johannesburg"
    },
    
    "oci_info": {
        "title": "OCI Card Information",
        "content": """**OCI (Overseas Citizen of India):**

**What is OCI?**
Lifelong visa for foreign nationals of Indian origin.

**Benefits:**
• Multiple entry, lifelong visa
• No registration required
• Work in India (with conditions)

**Fees:**
• Adult: R1,500
• Minor: R750

**Processing:** 6-8 weeks

**Requirements:**
• Current passport
• Proof of Indian origin
• Old Indian passport/birth certificate
• Passport photos""",
        "source": "CGI Johannesburg Official"
    },
    
    "office_info": {
        "title": "CGI Johannesburg Office",
        "content": """**Consulate General of India, Johannesburg:**

**Address:**
2nd Floor, Sandown Mews East
88 Stella Street, Sandton
Johannesburg

**Phone:** +27 11 783 0202
**Emergency:** (+27) 11 581 9800 (24/7)
**Email:** cons.joburg@mea.gov.in

**Office Hours:**
Mon-Fri: 9:00 AM - 5:30 PM

**Consular Services:**
Mon-Fri: 9:00 AM - 12:30 PM

**Website:** https://www.cgijoburg.gov.in""",
        "source": "CGI Johannesburg Official"
    },
    
    "emergency_contact": {
        "title": "Emergency Assistance",
        "content": """**🚨 EMERGENCY CONTACT:**

**24/7 Emergency Helpline:**
📞 (+27) 11 581 9800

**For:**
• Indian citizens in distress
• Lost/stolen passport
• Medical emergencies
• Arrest/detention
• Death of Indian national
• Natural disasters

**Regular Hours:**
📞 +27 11 783 0202
📧 cons.joburg@mea.gov.in

⚠️ **FRAUD ALERT:** The Consulate NEVER calls asking for money.""",
        "source": "CGI Johannesburg Official",
        "escalation": True
    },
    
    "escalation": {
        "title": "Human Assistance",
        "content": """**Connecting you to human assistance...**

Your request has been flagged for human review.

**While you wait:**
📞 Call: +27 11 783 0202
📧 Email: cons.joburg@mea.gov.in
🌐 Visit: https://www.cgijoburg.gov.in

**Office Hours:**
Mon-Fri: 9:00 AM - 5:30 PM

A consular officer will review your query.""",
        "source": "CGI Johannesburg",
        "escalation": True
    },
    
    "greeting": {
        "title": "Welcome",
        "content": """🙏 **Namaste! Welcome to Seva Setu Bot.**

I'm your AI assistant for Indian consular services in South Africa.

**I can help with:**
• Passport services
• Visa information
• OCI/PIO cards
• Document attestation
• Office hours & contact

**How can I assist you today?**""",
        "source": "Seva Setu Bot"
    }
}


class IntentClassifier:
    """
    Rule-based intent classifier for consular queries.
    Reduces LLM calls for common, deterministic queries.
    """
    
    def __init__(self):
        self.patterns = INTENT_PATTERNS
        self.responses = STRUCTURED_RESPONSES
        self.classification_count = 0
        self.llm_fallback_count = 0
    
    def classify(self, text: str) -> IntentResult:
        """
        Classify user intent from text.
        
        Returns IntentResult with category, confidence, and whether LLM is needed.
        """
        if not text or len(text.strip()) < 2:
            return IntentResult(
                category=IntentCategory.UNKNOWN,
                confidence=0.0,
                requires_llm=True
            )
        
        text_lower = text.lower().strip()
        self.classification_count += 1
        
        best_match = None
        best_score = 0.0
        matched_keywords = []
        
        # Check each intent category
        for category, config in self.patterns.items():
            score, keywords = self._calculate_match_score(text_lower, config)
            
            if score > best_score:
                best_score = score
                best_match = category
                matched_keywords = keywords
        
        # Determine if we need LLM
        requires_llm = best_score < 0.5  # Less than 50% confidence
        
        if requires_llm:
            self.llm_fallback_count += 1
        
        # Check for subcategory (e.g., visa type)
        subcategory = None
        if best_match == IntentCategory.VISA:
            subcategory = self._detect_visa_type(text_lower)
        
        # Check if escalation is needed
        escalation_needed = False
        if best_match and self.patterns.get(best_match, {}).get("escalation"):
            escalation_needed = True
        
        result = IntentResult(
            category=best_match or IntentCategory.UNKNOWN,
            subcategory=subcategory.value if subcategory else None,
            confidence=best_score,
            keywords_matched=matched_keywords,
            suggested_response_key=self.patterns.get(best_match, {}).get("response_key"),
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
    
    def get_structured_response(self, response_key: str) -> Optional[Dict]:
        """Get pre-defined structured response"""
        return self.responses.get(response_key)
    
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


def classify_intent(text: str) -> IntentResult:
    """Convenience function to classify intent"""
    return intent_classifier.classify(text)


def get_deterministic_response(intent_result: IntentResult) -> Optional[str]:
    """
    Get deterministic response if available.
    Returns None if LLM should handle it.
    """
    if intent_result.requires_llm:
        return None
    
    if not intent_result.suggested_response_key:
        return None
    
    response_data = intent_classifier.get_structured_response(intent_result.suggested_response_key)
    if not response_data:
        return None
    
    return response_data.get("content")
