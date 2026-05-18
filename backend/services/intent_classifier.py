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
        "keywords": [
            "address", "location", "office", "timing", "hours", "open",
            "closed", "contact", "phone", "email", "where", "directions",
            "cgi", "consulate", "johannesburg", "joburg", "jburg",
            "consul general", "consulate general"
        ],
        "patterns": [
            r"(where|what).*(office|address|location)",
            r"(office|consulate).*(timing|hours|address)",
            r"(contact|phone|email).*(number|address)",
            r"(when|what time).*open",
            r"cgi\s*(joburg|johannesburg|jburg)?",
            r"(consulate|consul).*(general|india|johannesburg|joburg)?"
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


# =====================================================================
# STRUCTURED RESPONSES (Deterministic)
# =====================================================================
STRUCTURED_RESPONSES = {

    "passport_info": {
        "title": "🛂 Passport Services",
        "content": """**🛂 Indian Passport Services**
*Consulate General of India, Johannesburg*

---

**📋 Types of Applications**

| Type | Description |
|---|---|
| New Passport | First-time applicants |
| Renewal / Re-issue | Expired or expiring passport |
| Lost / Damaged | FIR (police report) required |
| Tatkal | Urgent processing |

---

**💰 Fee Schedule**

| Application Type | Fee (ZAR) |
|---|---|
| 36-page passport | ZAR 2,280 |
| 60-page passport | ZAR 2,655 |
| Minor / Emergency passport | ZAR 780 |
| Tatkal surcharge | Additional fees apply |

> All fees include ICWF charge of ZAR 30.

---

**⏱ Processing Time**

- Normal: Up to one month
- Tatkal: 1–2 weeks

---

**🔗 How to Apply**

1. Apply online at cgijoburg.gov.in passport services
2. Complete the online application form
3. Pay the fee and save your receipt
4. Book appointment via VFS Global Johannesburg
5. Visit VFS with all original documents
6. Collect your passport when ready

> ⚠️ Applications are **not** accepted directly at the Consulate — all go through **VFS Global**.

---

**📁 Documents Required**

- ✅ Completed online application form
- ✅ Original current / expired passport
- ✅ 3 passport-size photos (5×5 cm, white background)
- ✅ Proof of residential address in South Africa
- ✅ Original proof of payment (no photocopies)
- ✅ Valid South African visa / permit
- ✅ FIR / Police Report *(lost or stolen only)*

---

**🏢 VFS Global — Passport / PCC**

📍 2nd Floor, Harrow Court 1, Isle of Houghton, Park Town, JHB 2198
📞 012 425 3007 / 011 484 0327
🕐 Submission: Mon–Fri 08:00–15:00 | Collection: 11:00–16:00

---

📞 **Consulate:** +27 11-4828484 | 📧 ccom.jburg@mea.gov.in""",
        "source": "CGI Johannesburg Official — cgijoburg.gov.in"
    },

    "visa_info": {
        "title": "✈️ Indian Visa Information",
        "content": """**✈️ Indian Visa Services**
*Consulate General of India, Johannesburg*

---

**🗂 Visa Types Available**

| Visa Type | Notes |
|---|---|
| Tourist | Up to 10 years, multiple entry |
| Business | For trade / corporate visits |
| Student | For study programmes in India |
| Medical | For treatment in India |
| Employment | For working in India |
| Conference / Research | Short-duration visits |
| Transit | Passing through India |
| e-Visa | Online — available at 30+ airports |

---

**💰 Visa Fees**

> 🎉 **South African nationals receive Indian visa GRATIS (free of charge).**
> For other nationalities, fees are as per MEA notification.

---

**⏱ Processing Time**

- Regular visa: 3–5 working days
- e-Visa: Apply minimum **5 working days** before departure

---

**🔗 How to Apply**

*Regular Visa:*
1. Apply online at indianvisaonline.gov.in
2. Fill the form and upload photos
3. Pay the visa fee online
4. Book appointment at VFS Global (Visa)
5. Submit biometrics and documents at VFS
6. Collect visa when ready

*e-Visa:*
1. Apply at indianvisaonline.gov.in/evisa
2. Upload documents and photo
3. Pay online — receive e-Visa by email

---

**📁 Documents Required**

- ✅ Valid passport — min **6 months** validity from departure
- ✅ At least **2 blank pages** in passport
- ✅ Completed application form
- ✅ Recent passport-size photographs
- ✅ Proof of travel (tickets / itinerary)
- ✅ Supporting documents *(varies by visa type)*

---

**🏢 VFS Global — Visa Submission**

> ⚠️ **No visa applications at the Consulate** — all through VFS only.

📍 1st Floor, Rivonia Village Office Block, Rivonia, JHB
📞 012 425 3007
🕐 Submission: Mon–Fri 08:00–15:00 | Collection: 11:00–16:00

---

📞 **Consulate:** +27 11-4828484 | 📧 ccom.jburg@mea.gov.in""",
        "source": "VFS Global / CGI Johannesburg Official"
    },

    "oci_info": {
        "title": "🇮🇳 OCI Card Information",
        "content": """**🇮🇳 OCI Card — Overseas Citizen of India**
*Consulate General of India, Johannesburg*

---

**ℹ️ What is OCI?**

An OCI Card is a **multi-purpose, multi-entry, lifelong visa** to India. It grants:

- ✅ Unlimited entry to India for any purpose
- ✅ No need to report to police on arrival
- ✅ Parity with NRIs for economic, financial & educational purposes
- ✅ No expiry — valid for life

---

**✅ Eligibility**

You may apply if:
- You were an **Indian citizen on or after 26 January 1950**, OR
- Your **parent, grandparent or great-grandparent** was Indian, OR
- You are the **spouse of an Indian citizen / OCI holder** (married ≥ 2 years)
- You are a **minor child** of an Indian citizen

*Not eligible:* Pakistan / Bangladesh nationals; foreign military personnel.

---

**💰 Fees**

> Fees are **as per MEA notification** — contact Consulate for current rates.
> 📧 cons.jburg@mea.gov.in

---

**🔗 How to Apply**

1. Apply online at ociservices.gov.in
2. Upload all required documents
3. Email cons.jburg@mea.gov.in to book appointment
4. Visit the Consulate with all original documents
5. Collect your OCI card when ready

---

**📁 Documents Required**

- ✅ Current foreign passport (original + all page copies)
- ✅ Renunciation / Surrender Certificate
- ✅ Proof of Indian origin (old Indian passport / birth / school cert)
- ✅ Proof of SA residential address
- ✅ SA ID / Permanent Residence / Work Permit
- ✅ 2 recent passport-size photos (51×51 mm)
- ✅ Marriage certificate *(if applying as spouse)*

---

**🏢 Consulate Office**

📍 No. 1, Eton Road, Park Town 2193, Johannesburg
📞 +27 11-4828484 | 📧 cons.jburg@mea.gov.in
🕐 Mon–Fri 08:30–17:00 (Lunch: 13:00–13:30)""",
        "source": "CGI Johannesburg Official — cgijoburg.gov.in"
    },

    "office_info": {
        "title": "🏢 CGI Johannesburg Office",
        "content": """**🏢 Consulate General of India, Johannesburg**

---

**📌 Contact Details**

| Field | Details |
|---|---|
| Acting Consul General | Mr. Harish Kumar |
| Address | No. 1, Eton Road, Park Town 2193, Johannesburg |
| Phone | +27 11-4828484 / +27 11-4828485 / +27 11-4828486 |
| Emergency | +27 11 581 9800 |
| General Email | ccom.jburg@mea.gov.in |
| Consular / OCI Email | cons.jburg@mea.gov.in |
| Website | www.cgijoburg.gov.in |

---

**🕐 Office Hours**

| Day | Hours |
|---|---|
| Monday – Friday | 08:30 – 17:00 |
| Lunch Break | 13:00 – 13:30 |
| Saturday – Sunday | Closed |
| Public Holidays | Closed |

---

**🗺 Jurisdiction**

Gauteng · North West · Limpopo · Mpumalanga

---

**🏢 VFS Global — Passport / PCC**

📍 2nd Floor, Harrow Court 1, Isle of Houghton, Park Town, JHB 2198
📞 012 425 3007 / 011 484 0327
🕐 Submission: Mon–Fri 08:00–15:00 | Collection: 11:00–16:00

---

**🏢 VFS Global — Visa**

📍 1st Floor, Rivonia Village Office Block, Rivonia, JHB
📞 012 425 3007
🕐 Submission: Mon–Fri 08:00–15:00 | Collection: 11:00–16:00

---

> ⚠️ **FRAUD ALERT:** The Consulate NEVER requests money over phone or SMS.""",
        "source": "CGI Johannesburg Official — cgijoburg.gov.in"
    },

    "emergency_contact": {
        "title": "🚨 Emergency Assistance",
        "content": """**🚨 Emergency Consular Assistance**

---

**📞 24/7 Emergency Helpline**

> **+27 11 581 9800**
> *Available around the clock for Indian citizens in distress*

---

**🆘 When to Call**

- 🔴 Lost or stolen passport
- 🔴 Arrest or detention
- 🔴 Medical emergency
- 🔴 Death of an Indian national
- 🔴 Natural disaster / civil unrest
- 🔴 Stranded without funds or documents

---

**🕐 Regular Office Hours**

📞 +27 11-4828484 / +27 11-4828485 / +27 11-4828486
📧 ccom.jburg@mea.gov.in
🕐 Mon–Fri 08:30–17:00 (Lunch: 13:00–13:30)

---

**🏢 Consulate Address**

📍 No. 1, Eton Road, Park Town 2193, Johannesburg

---

> ⚠️ **FRAUD ALERT:** The Consulate **NEVER** calls asking for money. Hang up and report to ccom.jburg@mea.gov.in immediately.""",
        "source": "CGI Johannesburg Official",
        "escalation": True
    },

    "escalation": {
        "title": "👤 Human Assistance",
        "content": """**👤 Connecting You to Human Assistance**

Your request has been noted and flagged for human review.

---

**📞 Contact the Consulate Directly**

| Channel | Details |
|---|---|
| Phone | +27 11-4828484 / +27 11-4828485 / +27 11-4828486 |
| Emergency | +27 11 581 9800 *(24/7)* |
| General Email | ccom.jburg@mea.gov.in |
| Consular / OCI | cons.jburg@mea.gov.in |
| Website | www.cgijoburg.gov.in |

---

**🕐 Office Hours**

Mon–Fri **08:30–17:00** | Lunch: 13:00–13:30
Saturday, Sunday & Public Holidays — Closed

---

**🏢 Walk-In Address**

📍 No. 1, Eton Road, Park Town 2193, Johannesburg

---

> A consular officer will review your query and respond as soon as possible.""",
        "source": "CGI Johannesburg",
        "escalation": True
    },

    "greeting": {
        "title": "Welcome",
        "content": """🙏 **Namaste! Welcome to Seva Setu Bot**
*Your official AI assistant for Indian consular services in South Africa*

---

**🏛️ I Can Help You With**

| Service | |
|---|---|
| 🛂 Passport | New, renewal, lost/damaged, Tatkal |
| ✈️ Indian Visa | Tourist, business, student, e-Visa |
| 🇮🇳 OCI / PIO Card | Lifelong visa for persons of Indian origin |
| 📋 Police Clearance (PCC) | For immigration or employment abroad |
| 📄 EC / Death Certificate | Emergency certificate and attestation |
| 📜 Surrender / Renunciation | Surrender Indian passport |
| 💍 Marriage Certificate | Registration and attestation |
| 🗂️ Miscellaneous | Affidavits, power of attorney, apostille |
| 🏢 Office Info | Hours, address, contact numbers |

---

Just type your question or say **"help"** to see everything I can do!""",
        "source": "Seva Setu Bot"
    },

    "capabilities": {
        "title": "Services & Features",
        "content": """🤖 **Seva Setu Bot — Complete Guide**
*Official AI assistant for the Consulate General of India, Johannesburg*

---

**🏛️ Consular Services**

| # | Service | What It Covers |
|---|---|---|
| 1 | 🛂 Passport | New, renewal, lost/damaged, Tatkal — via VFS Global |
| 2 | ✈️ Indian Visa | Tourist, business, student, medical, e-Visa — via VFS Global |
| 3 | 📋 PCC | Police Clearance Certificate for immigration / employment |
| 4 | 🇮🇳 OCI Card | Lifelong multi-entry visa — processed at the Consulate |
| 5 | 📄 EC / Death Cert | Emergency Certificate and Death Certificate attestation |
| 6 | 📜 Renunciation | Surrender Indian passport after acquiring foreign nationality |
| 7 | 💍 Marriage Cert | Register or attest South African marriage for India |
| 8 | 🗂️ Miscellaneous | Affidavits, power of attorney, apostille, name correction |

---

**💬 What You Can Ask Me**

- 📁 Required documents for any service
- 💰 Fees and processing times
- 📅 How to book an appointment
- 🔍 Track your application status
- 🏢 Office address, timings, and contact info
- 🚨 Emergency consular assistance

---

**✨ Extra Features**

| Feature | Details |
|---|---|
| 🌐 20+ Languages | Hindi, Tamil, Zulu, Xhosa, Afrikaans, Arabic, French & more |
| 🎤 Voice Input | Speak your question in your language |
| 📷 Document Upload | Auto-scan and extract fields from your documents |
| 📄 PDF Receipt | Get a tracking ID and PDF summary after each application |
| 📱 WhatsApp | Same bot available on WhatsApp |
| 🔒 Secure | All uploads are virus-scanned; sessions are private |

---

📞 **Need human help?** +27 11-4828484 | 📧 ccom.jburg@mea.gov.in
🕐 Mon–Fri 08:30–17:00""",
        "source": "Seva Setu Bot"
    },

    "platform_info": {
        "title": "About Seva Setu Bot",
        "content": """🌟 **What Makes Seva Setu Bot Different?**
*The only official AI assistant for the Consulate General of India, Johannesburg*

---

**🏆 Seva Setu Bot vs Other Chatbots**

| Feature | ✅ Seva Setu Bot | ❌ Generic Chatbots |
|---|---|---|
| Official source | CGI Johannesburg verified | Third-party / unverified |
| Live consulate data | Scraped from cgijoburg.gov.in | Static or outdated |
| Guided application flow | Step-by-step + PDF output | Information only |
| Document upload & scan | Auto-extracts fields | Not supported |
| 20+ languages | Hindi, Tamil, Zulu, Xhosa & more | English only |
| Voice input | Speak in your language | Rarely available |
| WhatsApp support | Same bot on WhatsApp | Web only |
| Emergency helpline | 24/7 emergency contact | Not available |
| Cost | 100% Free | Often paid |

---

**💰 Pricing — Is This Free?**

> ✅ **Seva Setu Bot is completely free.** No subscription, no sign-up fee, no hidden charges.

The government consulate services have official fees:

| Service | Fee (ZAR) |
|---|---|
| Passport 36-page | ZAR 2,280 |
| Passport 60-page | ZAR 2,655 |
| Minor / Emergency Passport | ZAR 780 |
| Indian Visa | Gratis for South African nationals |
| Birth Registration | Gratis (free) |
| OCI Card | As per MEA notification |
| Attestation / Other | As per consular schedule |

---

**🔧 Can I Customise the Services?**

These are official government processes — requirements cannot be changed. However, you can personalise your experience:

- 🌐 Choose from **20+ languages**
- 🎤 Use **voice input** in your language
- 📷 **Upload documents** for auto-scanning
- 📋 Follow a **guided step-by-step** application flow
- 🔍 Ask **specific questions** about your situation

---

**🔒 Why Trust This Platform?**

- ✅ **Official** — The only AI assistant endorsed by CGI Johannesburg
- ✅ **Government-backed** — Data from CGI Joburg, VFS Global & MEA notifications
- ✅ **Secure** — Every document is virus-scanned before processing
- ✅ **Private** — Conversations never sold or shared
- ✅ **Transparent** — Always directs to official government portals
- ⚠️ **Fraud Alert** — The Consulate NEVER calls asking for money.

---

**🚀 How to Get Started**

1. **Select language** — click the 🌐 flag button at the top
2. **Ask your question** — type naturally, e.g. *"I need to renew my passport"*
3. **Follow the guided flow** — the bot collects your details step by step
4. **Upload documents** — use the 📷 camera or 📎 upload button when prompted
5. **Receive your PDF** — get a tracking ID and summary upon submission

---

📞 **Consulate:** +27 11-4828484 / +27 11 581 9800 *(24/7 emergency)*
📧 ccom.jburg@mea.gov.in | 🕐 Mon–Fri 08:30–17:00""",
        "source": "Seva Setu Bot — CGI Johannesburg Official"
    },

    "language_switch": {
        "title": "Language Switch",
        "content": "🌐 Switching language for you...",
        "source": "Seva Setu Bot"
    }
}


# Maps common language names (lower-case) → language code used by the frontend
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


def detect_target_language(text: str):
    """Extract the target language code from a language-switch message. Returns None if not found."""
    text_lower = text.lower()
    for name, code in LANGUAGE_NAME_TO_CODE.items():
        if name in text_lower:
            return code
    return None


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
        # Strip leading/trailing non-word punctuation so "hi'", "hello.", "hi!!!"
        # match the same patterns as "hi" — keeps interior punctuation intact.
        text_lower = re.sub(r"^[^\w]+|[^\w]+$", "", text_lower)
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
                for pat in self.patterns[_exact_cat].get("patterns", []):
                    if re.search(pat, text_lower, re.IGNORECASE):
                        requires_llm = False
                        break
                break

        # Safety net: short messages starting with a greeting word still resolve
        # to GREETING even if the pattern missed (e.g. "hii", "hellooo there").
        if requires_llm and len(text_lower) <= 25:
            for _g in ("namaste", "hello", "hey", "hi"):
                if text_lower.startswith(_g):
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
