"""
====================================================================
SEVA SETU BOT - KNOWLEDGE SERVICE
====================================================================
Manages versioned knowledge base:
- Structured FAQ collection
- Version control for updates
- Source transparency
- Admin interface support
====================================================================
"""

import os
import uuid
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from database import get_database
from knowledge_scraper import scrape_cgi_joburg

logger = logging.getLogger(__name__)


class KnowledgeCategory(Enum):
    """Knowledge base categories"""
    PASSPORT = "passport"
    VISA = "visa"
    OCI = "oci"
    CONSULAR = "consular"
    FEES = "fees"
    EMERGENCY = "emergency"
    OFFICE = "office"
    GENERAL = "general"


class KnowledgeStatus(Enum):
    """Knowledge entry status"""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    PENDING_REVIEW = "pending_review"


@dataclass
class KnowledgeEntry:
    """Knowledge base entry"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    category: KnowledgeCategory = KnowledgeCategory.GENERAL
    title: str = ""
    question: str = ""  # FAQ question
    answer: str = ""  # FAQ answer
    keywords: List[str] = field(default_factory=list)
    source: str = ""  # Source URL or reference
    source_verified: bool = False
    version: int = 1
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE
    language: str = "en"
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_by: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "category": self.category.value,
            "title": self.title,
            "question": self.question,
            "answer": self.answer,
            "keywords": self.keywords,
            "source": self.source,
            "source_verified": self.source_verified,
            "version": self.version,
            "status": self.status.value,
            "language": self.language,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until
        }


# =====================================================================
# DEFAULT KNOWLEDGE BASE
# Source: www.cgijoburg.gov.in (compiled April 2026)
# =====================================================================
DEFAULT_KNOWLEDGE = [
    {
        "category": "office",
        "title": "Office Information",
        "question": "What are the CGI Johannesburg office hours and address?",
        "answer": """**Consulate General of India, Johannesburg**

**Address:**
No. 1, Eton Road (Corner Jan Smuts Avenue & Eton Road)
Park Town 2193, PO Box 6805, Johannesburg 2000, South Africa

**Telephone:** +27 11-4828484 / +27 11-4828485 / +27 11-4828486 / +27 11 581 9800
**Fax:** +27 11 482 4648 / +27 11 482 8492
**Email (General):** ccom.jburg@mea.gov.in
**Email (Consular/OCI appointments):** cons.jburg@mea.gov.in
**Website:** www.cgijoburg.gov.in

**Office Hours:** Monday–Friday: 08:30 – 17:00 (Lunch: 13:00–13:30)

**VFS Global — Passport & Consular Submissions:**
2nd Floor, Harrow Court 1, Isle of Houghton Office Park
Boundary Road, Park Town, Johannesburg – 2198
Tel: 012 425 3007 / 011 484 0327 | Email: Info.inza@vfshelpline.com
Submission: 08:00–15:00 | Collection: 11:00–16:00

**Jurisdiction:** Gauteng, North West, Limpopo and Mpumalanga
**Acting Consul General:** Mr. Harish Kumar""",
        "keywords": ["office", "address", "hours", "timing", "contact", "location",
                     "phone", "email", "fax", "parktown", "eton road", "jan smuts",
                     "vfs", "working hours", "open", "close", "consulate"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "passport",
        "title": "Passport Services — How to Apply",
        "question": "How do I apply for or renew my Indian passport in South Africa?",
        "answer": """**Passport Services — CGI Johannesburg**

All passport services are processed through **VFS Global** (not directly at the Consulate).

**Step 1 — Apply Online:**
Complete application at: https://www.cgijoburg.gov.in/page/passport-services-for-the-indian-nationals/

**Step 2 — Submit at VFS Global:**
Indian Visa and Consular Application Centre
2nd Floor, Harrow Court 1, Isle of Houghton Office Park
Boundary Road, Park Town, Johannesburg – 2198
Tel: 012 425 3007 / 011 484 0327
Submission hours: 08:00–15:00 | Collection: 11:00–16:00

**Processing Time:** Up to one month (if all documents are in order)

**Services Available:**
• Re-issue on expiry
• Re-issue for lost/stolen passport (requires FIR/Police Report)
• Re-issue for damaged passport
• New passport for minor child born in South Africa
• Re-issue on change of name/particulars
• Re-issue on exhaustion of pages

**Photos:** 3 passport-sized photos (5cm x 5cm, coloured, white background)
**Payment:** EFT or Credit/Debit Card — original proof required; photocopies NOT accepted
**Applicants may be called for interview** if required by the Consulate.""",
        "keywords": ["passport", "renewal", "renew", "reissue", "apply", "new passport",
                     "lost passport", "stolen passport", "damaged passport", "expired passport",
                     "passport application", "vfs passport", "passportindia"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "fees",
        "title": "Passport Fees Schedule",
        "question": "What are the passport fees in South Africa / CGI Johannesburg?",
        "answer": """**Passport Fees — CGI Johannesburg (as of April 2023)**
All fees include ICWF (Indian Community Welfare Fund) of ZAR 30.

**36-Page Passport:**
• Re-issue (expiry / lost / stolen / damaged / name change / exhaustion): **ZAR 2,280**

**60-Page Passport:**
• Re-issue (expiry / lost / stolen / damaged / name change / exhaustion): **ZAR 2,655**

**Minor Child (new passport — 5-year validity):** **ZAR 780**

**Emergency Travel Document:** **ZAR 780**

**OCI & Other Consular Fees:**
• Birth Registration: **Gratis (free)**
• OCI Miscellaneous updates (address/passport details): **Gratis**
• Fresh OCI Card / PCC / Attestation / Non-Impediment Letter: As per MEA/VFS schedule

**Payment Methods:** EFT or Credit/Debit Card at VFS Global or the Consulate.
Original proof of payment required — photocopies/scanned copies NOT accepted.""",
        "keywords": ["fees", "cost", "price", "payment", "charges", "zar", "rand",
                     "passport fees", "how much", "2280", "2655", "780",
                     "visa fees", "oci fees", "consular fees", "icwf"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "passport",
        "title": "Lost or Stolen Passport",
        "question": "What do I do if my Indian passport is lost or stolen in South Africa?",
        "answer": """**Lost / Stolen Passport — Steps to Follow:**

1. **File a Police Report** — Obtain original FIR/Police Report from SA Police (10111)
2. **Apply Online:** https://www.cgijoburg.gov.in/page/passport-services-for-the-indian-nationals/
3. **Submit at VFS Global** with the following documents:
   • Original FIR/Police Report for lost/stolen passport
   • 3 passport-sized photographs (5cm x 5cm, white background)
   • Proof of Indian citizenship (if original passport not available)
   • Proof of residential address in South Africa
   • Original proof of fee payment
4. **Fee:** ZAR 2,280 (36-page) or ZAR 2,655 (60-page), includes ICWF of ZAR 30
5. **Processing:** Up to one month

**For Emergency Travel (need to travel urgently):**
An Emergency Travel Document can be issued for a single journey to India.
Fee: ZAR 780 | Required: Police report, proof of identity, 2 photos, proof of travel.

**VFS Global Address:**
2nd Floor, Harrow Court 1, Isle of Houghton, Park Town, JHB – 2198
Tel: 012 425 3007 / 011 484 0327""",
        "keywords": ["lost passport", "stolen passport", "missing passport", "fir",
                     "police report", "emergency travel", "emergency document"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "passport",
        "title": "Minor Child Passport",
        "question": "How to get an Indian passport for a minor child born in South Africa?",
        "answer": """**Passport for Minor Child Born in South Africa:**

**Fee:** ZAR 780 (includes ICWF of ZAR 30) — 5-year validity passport issued

**Documents Required:**
• Completed online application (https://www.cgijoburg.gov.in/page/passport-services-for-the-indian-nationals/)
• 3 passport-sized photographs (5cm x 5cm, white background)
• Birth registration at the Consulate (obtain this first — it is free)
• Birth certificate issued by South African Home Department and local hospital
• Both parents must sign the form at the declaration column
• For infants: thumb impression in the box on Page 1 and Page 2 after Serial No. 26

**Submit at VFS Global:**
2nd Floor, Harrow Court 1, Isle of Houghton, Park Town, JHB – 2198
Tel: 012 425 3007 / 011 484 0327 | Submission: 08:00–15:00

**Note:** Birth must first be registered at the Consulate (free service) before applying for passport.""",
        "keywords": ["minor passport", "child passport", "baby passport", "infant passport",
                     "born in south africa", "new passport minor", "child born"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "visa",
        "title": "Indian Visa for South African Nationals",
        "question": "How do South African nationals apply for an Indian visa?",
        "answer": """**Indian Visa — For South African Nationals**

**South African nationals receive Indian visas GRATIS (free of charge).**

**Apply Online:** https://indianvisaonline.gov.in/visa/index.html

**Submit at VFS Global (Visa Centre):**
1st Floor, Rivonia Village Office Block
cnr Rivonia Boulevard and Mutual Road, Rivonia, Johannesburg
Tel: 012 425 3007 / 011 484 0327

**Biometrics:** Mandatory for all regular visa applicants (since 17 July 2017)

**Requirements:**
• Passport valid for minimum 6 months from date of departure from India
• At least 2 blank pages in passport
• Completed online application form
• Biometrics captured at VFS

**Visa Types Available:** Tourist, Business, Employment, Student, Medical, Research,
Journalist, Conference, Transit, Entry (X), Medical Attendant, Missionary/Religious Worker

**Special Note:** South African nationals holding diplomatic/official passports are
exempt from visa for up to 90 days (bilateral agreement).

**No visa applications accepted directly at the Consulate — all through VFS only.**""",
        "keywords": ["visa", "indian visa", "south african visa", "visit india", "travel india",
                     "tourist visa", "business visa", "student visa", "medical visa",
                     "gratis", "free visa", "visa application", "vfs visa"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "visa",
        "title": "E-Visa Information",
        "question": "What is e-Visa and how do I apply for it to visit India?",
        "answer": """**E-Visa for India — South African Nationals (GRATIS)**

South African nationals are eligible for e-Visa at no charge.

**Apply Online:** https://indianvisaonline.gov.in/evisa/tvoa.html
Apply minimum **5 working days** before departure.

**E-Visa Categories:**
• **e-Tourist Visa:** 30 days / 1 year / 5 years — Double/Multiple entry; tourism & visiting friends/relatives
• **e-Business Visa:** 1 year, Multiple entry — business visits
• **e-Medical Visa:** 60 days, Triple entry — medical treatment in India
• **e-Medical Attendant Visa:** 60 days, Triple entry — max 2 attendants per e-Medical Visa
• **e-Conference Visa:** 30 days — attending conferences/seminars

**Key Rules:**
• e-Visa is linked to specific ports of entry (30+ international airports, 5 seaports)
• Arrive/depart through designated airports/seaports only
• Activities can be combined across categories (except e-Conference, which only allows e-Tourist activities)

**No need to visit VFS for e-Visa — apply and receive entirely online.**""",
        "keywords": ["evisa", "e-visa", "e visa", "online visa", "tourist visa online",
                     "e tourist", "e business visa", "e medical visa", "e conference"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "oci",
        "title": "OCI Card Application",
        "question": "How to apply for an OCI (Overseas Citizen of India) card?",
        "answer": """**OCI (Overseas Citizen of India) Card**

OCI provides a multi-purpose, multi-entry, life-long visa for India.

**Eligibility:**
• Person who was an Indian citizen at any time since 26 January 1950
• Person whose parent/grandparent/great-grandparent was an Indian citizen
• Spouse of foreign origin of an Indian citizen or OCI holder (marriage registered ≥ 2 years)
• Minor child where both/one parent is Indian citizen
• NOT eligible: Pakistan/Bangladesh nationals; foreign military personnel (serving or retired)

**Apply Online:** https://ociservices.gov.in/

**Submit to the Consulate** (appointment required — email: cons.jburg@mea.gov.in):
• Computer-generated application form with registration number
• 2 photos (51mm x 51mm) — one pasted on form, one attached separately
• Proof of present citizenship (current foreign passport)
• Proof of renunciation of Indian citizenship / surrender certificate
• Proof of Indian origin (old Indian passport, birth certificate, school certificate, land records)
• Proof of residential address in SA (utility bill, lease, property papers)
• For spouse of Indian citizen: marriage certificate + copy of spouse's Indian passport

**Fees:** As per MEA notification (contact Consulate for current fees)

**Important Restrictions:**
• OCI does NOT permit missionary work, mountaineering, or research without GoI permission
• Fees are not refunded if OCI is not granted
• Husband/wife must each claim OCI on strength of their own parents — not each other's""",
        "keywords": ["oci", "overseas citizen", "indian origin", "oci card", "oci application",
                     "oci eligibility", "oci documents", "pio to oci", "ociservices"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "consular",
        "title": "Police Clearance Certificate (PCC)",
        "question": "How do I apply for a Police Clearance Certificate (PCC)?",
        "answer": """**Police Clearance Certificate (PCC)**

PCC is required by Indian nationals for immigration, change of nationality,
employment abroad, or longer stay in another country.

**PCC service is outsourced to VFS Global.**

**Apply Online:** https://www.cgijoburg.gov.in/page/status-of-indian-passport-pcc/
• Select CGI Johannesburg
• Submit application at VFS Global Johannesburg

**VFS Global Address:**
2nd Floor, Harrow Court 1, Isle of Houghton, Park Town, JHB – 2198
Tel: 012 425 3007 / 011 484 0327

**Applicants in:** Gauteng, North West, Limpopo, and Mpumalanga must apply through CGI Johannesburg.

**Check Status:** https://www.cgijoburg.gov.in/page/status-of-indian-passport-pcc/

**VFS Reference:** https://www.vfsglobal.com/one-pager/India/SouthAfrica/consular-services/""",
        "keywords": ["pcc", "police clearance", "police clearance certificate",
                     "clearance certificate", "immigration clearance"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "consular",
        "title": "Birth Registration",
        "question": "How do I register the birth of my child (born in South Africa) at the Consulate?",
        "answer": """**Birth Registration — Children Born in South Africa to Indian Nationals**

**Service is Gratis (free of charge).**

**Required Documents:**
• Birth certificate issued by South African Home Department
• Birth certificate from local hospital
• Indian passport(s) of parent(s)

**Process:**
• Visit the Consulate directly (not VFS) to register the birth
• The registered birth certificate is then used for minor passport applications

**Contact:** cons.jburg@mea.gov.in or call +27 11-4828484 / +27 11 581 9800
**Office Hours:** Mon–Fri 08:30–17:00 (Lunch 13:00–13:30)""",
        "keywords": ["birth registration", "register birth", "child born", "newborn",
                     "birth certificate", "register child"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "consular",
        "title": "Document Attestation",
        "question": "How do I get Indian documents attested at the Consulate?",
        "answer": """**Document Attestation — CGI Johannesburg**

**For Indian Nationals (Academic Degrees & General Documents):**
• Indian documents must first be **apostilled by MEA (Ministry of External Affairs, India)**
• MEA Apostille: http://www.mea.gov.in/apostille.htm
• Submit apostilled/attested documents with application to the Consulate

**General Power of Attorney (GPA/PoA):**
• For Indian nationals wishing to attest GPA/PoA for use in India
• Bring original documents and self-attested copies
• Fee as per consular schedule

**For Foreign Nationals:**
• Attestation of Indian documents for use in South Africa
• Applicable for legal, business, or personal documents

**One and the Same Certificate:**
• Issued when a name spelling difference exists across your documents
• Bring self-attested copies of all documents showing name variations

**Contact:** ccom.jburg@mea.gov.in | +27 11-4828484 / +27 11 581 9800""",
        "keywords": ["attestation", "attest", "apostille", "document attestation",
                     "power of attorney", "gpa", "poa", "notarize", "one and the same"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "emergency",
        "title": "Emergency Travel Document & Assistance",
        "question": "How to get emergency consular assistance or an emergency travel document?",
        "answer": """**Emergency Consular Assistance — CGI Johannesburg**

**Consulate Contact (office hours Mon–Fri 08:30–17:00):**
📞 +27 11-4828484 / +27 11-4828485 / +27 11-4828486 / +27 11 581 9800
📧 ccom.jburg@mea.gov.in

**For emergencies involving Indian nationals:**
• Indians in distress (arrest, detention, accident, death)
• Lost/stolen passports requiring urgent travel
• Medical emergencies

**Emergency Travel Document (ETD):**
• Issued when valid Indian passport not available due to loss/theft/damage
• Valid for **single journey to India only**
• **Fee:** ZAR 780 (includes ICWF)
• Required: Police report, proof of identity, 2 photographs, proof of travel booking

**Pravasi Bharatiya Sahayata Kendra (for Indians abroad in distress):**
Toll Free (India only): 1800 11 3090
WhatsApp: +91-7428 3211 44
Email: helpline@mea.gov.in

**Local Emergency (SA Police):** 10111
**Ambulance / Fire:** 10177

⚠️ The Consulate NEVER calls asking for money. Report scam calls to local police.""",
        "keywords": ["emergency", "urgent", "help", "crisis", "distress",
                     "emergency travel document", "etd", "indian in trouble",
                     "arrested", "accident", "death", "pravasi"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "consular",
        "title": "Other Consular Services",
        "question": "What other services does CGI Johannesburg offer?",
        "answer": """**Other Services at CGI Johannesburg:**

**Non-Impediment Letter:**
• Issued to Indian nationals wishing to marry a foreign national
• Certifies the applicant is not married and is free to marry
• Required: Indian passport, proof of address, application form

**NOC for Child Passport in India:**
• Required when one parent applies for a child's passport in India
• Other parent (in South Africa) obtains NOC from the Consulate
• Required: Passport copies of both parents, child's birth certificate, application form

**Translation of Indian Driving Licence:**
• Certified translation for use in South Africa

**Registration of NRIs/PIOs/OCIs:**
• Indian nationals in South Africa encouraged to register with the Consulate
• Helps in emergencies and for consular assistance

**Tracing the Roots Programme:**
• For persons of Indian origin to trace their ancestral roots in India
• MEA facilitates visits to villages/districts of origin
• Contact Consulate for application process

**Open House (Grievance Redressal):**
• Consulate periodically holds open house sessions
• Dates announced on website and social media

**Contact for appointments/enquiries:**
📞 +27 11-4828484 / +27 11 581 9800
📧 cons.jburg@mea.gov.in (consular services & OCI)
📧 ccom.jburg@mea.gov.in (general)""",
        "keywords": ["non impediment", "noc", "driving licence", "driving license translation",
                     "register nri", "tracing roots", "open house", "grievance",
                     "marriage abroad", "child noc", "consular services"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "general",
        "title": "Trade & Commerce — India–South Africa Bilateral Relations",
        "question": "What are the trade and commercial relations between India and South Africa?",
        "answer": """**Trade & Commerce — India–South Africa Bilateral Relations**

India and South Africa established diplomatic relations in **1993**. Both countries are members of **BRICS** and the **G20**.

**South Africa at a Glance:**
• Population: Over 64 million | Area: 1.22 million sq km
• GDP: Services 62.75% | Industry 24.46% | Growth rate (2024): ~1.0%
• Key resources: World's largest producer of platinum, vanadium, chromium, and manganese
• Financial capital of Africa: Johannesburg

**India–South Africa Trade Facts:**
• Indian firms have invested approximately **USD 10 billion** in South Africa
• More than **150 Indian companies** operating in South Africa
• Major Indian MNCs: TATA, Mahindra, Vedanta, Jindal, Cipla, Sun Pharma (Ranbaxy), TCS, WIPRO, Zensar, TechMahindra
• Indian companies employ approximately **18,000 South Africans**
• Key bilateral sectors: IT, Mining, Infrastructure, Automobiles, Pharmaceuticals, Agriculture, Heavy Machinery

**Double Taxation Avoidance Agreement (DTAA):**
Entered into force on **28 November 1997** (Notification No. GSR 198(E), dated 21-04-1998)

**Services for Indian Companies:**
Trade advisory, market intelligence, business meeting facilitation, partner identification, export/import guidance, exhibition support.

**Services for South African Companies:**
Market entry advisory for India, introductions to Indian counterparts, investment/regulatory information, Buyer-Seller Meets (BSM) support.

**Contact:** ccom.jburg@mea.gov.in | +27 11-4828484 / +27 11 581 9800""",
        "keywords": ["trade", "commerce", "bilateral", "india south africa trade", "brics", "g20",
                     "investment", "indian companies", "tata", "mahindra", "dtaa", "double taxation",
                     "business south africa", "indian business", "wipro", "tcs"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "general",
        "title": "Important Links & Online Portals",
        "question": "What are the important links and online portals for CGI Johannesburg services?",
        "answer": """**Important Links & Online Portals — CGI Johannesburg**

| Service | Link |
|---|---|
| Consulate Website | www.cgijoburg.gov.in |
| Passport Application | https://www.cgijoburg.gov.in/page/passport-services-for-the-indian-nationals/ |
| Regular Visa Application | https://indianvisaonline.gov.in/visa/index.html |
| E-Visa Application | https://indianvisaonline.gov.in/evisa/tvoa.html |
| OCI Services | https://ociservices.gov.in/ |
| PCC Application | https://www.cgijoburg.gov.in/page/status-of-indian-passport-pcc/ |
| VFS Global South Africa | https://services.vfsglobal.com/zaf/en/ind/ |
| Passport Status Check | https://www.cgijoburg.gov.in/page/status-of-indian-passport-pcc/ |
| MEA Apostille | http://www.mea.gov.in/apostille.htm |
| Ministry of External Affairs | www.mea.gov.in |
| High Commission of India, Pretoria | www.hcipretoria.gov.in |

**Key Contacts:**
• **General Email:** ccom.jburg@mea.gov.in
• **Consular / OCI Email:** cons.jburg@mea.gov.in
• **VFS Johannesburg:** 2nd Floor, Harrow Court 1, Isle of Houghton, Park Town — Tel: 012 425 3007

**Pravasi Bharatiya Sahayata Kendra (Indians abroad in distress):**
Toll Free (India): 1800 11 3090 | WhatsApp: +91-7428 3211 44 | helpline@mea.gov.in

**Office of Protector General of Emigrants:**
pge@mea.gov.in | diroe1@mea.gov.in

**Social Media:**
Twitter/X: @indiainjoburg | Facebook: IndiaInSouthAfricaJohannesburg
Instagram: @indiainjohannesburg | YouTube: @Indiainjoburg""",
        "keywords": ["links", "portal", "website", "online", "url", "apply online",
                     "passportindia", "indianvisaonline", "ociservices", "vfs global",
                     "status check", "social media", "twitter", "facebook", "instagram"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "general",
        "title": "Latest News & Events — CGI Johannesburg (April 2026)",
        "question": "What are the latest news and events from CGI Johannesburg?",
        "answer": """**Latest News & Events — CGI Johannesburg (as of April 2026)**

**Recent Activities:**
• **11 Mar 2026:** ACG Mr. Harish Kumar inaugurates the 11th Agritec South Africa with MEC: Agriculture Ms. Vuyiswa Ramokgopa.
• **27 Jan 2026:** India–South Africa A.I. Dialogue — 100+ participants, in preparation for India A.I. Impact Summit.
• **29 Jan 2026:** Consulate hosts the 77th Republic Day evening reception.
• **26 Jan 2026:** India's 77th Republic Day — Flag Unfurling at Chancery.
• **30 Jan 2026:** Hindi Poetry and Costume contest on Vishwa Hindi Diwas.
• **25 Dec 2025:** ACG Mr. Harish Kumar at St. Thomas Indian Orthodox Church, Midrand.
• **24 Dec 2025:** Consulate team visits children of Leratong Joy for One Foundation.
• **23 Oct 2025:** Commercial Representative addresses Delegates at JCCI Annual Conference 2025.
• **08 Oct 2025:** CG Shri Mahesh Kumar welcomes Shri Harivansh Narayan Singh (Chairman, Rajya Sabha).
• **05 Oct 2025:** Speaker of Delhi Legislative Assembly plants sapling under Ek Ped Maa Ke Naam.

**Recent Press Releases:**
• India–South Africa A.I. Dialogue (Jan 2026)
• Launch of Study in India Portal (SII) & e-Student Visa for Foreign Students (Sep 2025)
• Viksit Bharat Run (Sep 2025)
• All-party Indian Parliamentary delegation led by Hon. Ms. Supriya Sule (May 2025)
• Digitization of Disembarkation Card for Foreign Nationals Visiting India

**Upcoming / Recent Notices:**
• Tender — Renovation of rooms at the Consulate (Apr 01, 2026)
• Tender — Security Services (Nov 11, 2025)
• Tender — Boundary Wall Reconstruction (Nov 01, 2025)
• 88th Edition of Know India Programme (KIP)
• 61st IHGF Delhi Fair (Spring 2026), India Expo Centre, Greater Noida
• SEPC Buyer-Seller Meet in Johannesburg (09–10 Mar 2026)

**Acting Consul General:** Mr. Harish Kumar
For latest updates: www.cgijoburg.gov.in | @indiainjoburg""",
        "keywords": ["news", "events", "latest", "recent", "republic day", "agritec",
                     "consul general", "harish kumar", "know india", "kip", "tender",
                     "press release", "ai dialogue", "vishwa hindi diwas"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    },
    {
        "category": "general",
        "title": "Frequently Asked Questions (FAQ)",
        "question": "Frequently asked questions about CGI Johannesburg services",
        "answer": """**Frequently Asked Questions — CGI Johannesburg**

**Q: How do I apply for a new/renewal/lost/damaged passport?**
A: Complete online application at https://www.cgijoburg.gov.in/page/passport-services-for-the-indian-nationals/ and submit at VFS Global with prior appointment.

**Q: What is the timeframe for passport reissue?**
A: Approximately 3–4 weeks, provided all documents are in place and approved by Indian authorities.

**Q: What is a damaged passport?**
A: Ink/water spill, scribbling, torn paper, missing data page, spine damage, or thread out.

**Q: How do I apply for PCC?**
A: Apply online at https://www.cgijoburg.gov.in/page/status-of-indian-passport-pcc/ — submit at VFS Global Johannesburg.

**Q: How do I get Indian documents attested?**
A: Indian documents must first be apostilled by MEA India — see http://www.mea.gov.in/apostille.htm

**Q: Is my foreign spouse entitled to an OCI card?**
A: Yes, if the marriage has been registered and continuously subsisted for not less than two years.

**Q: Are foreign military personnel eligible for OCI?**
A: No. Foreign military personnel, whether serving or retired, are NOT entitled to an OCI card.

**Q: What should I do if I find a mistake in my passport?**
A: Visit the Consulate immediately and return the passport for rectification. Additional fees may apply.

**Q: What is a minor vs major name change?**
A: Minor = spelling discrepancy without total phonetic change (e.g., Rakesh vs Rakash). Major = complete or phonetically different name change.

**Q: How do I apply for an emergency visa?**
A: Apply online at www.indianvisaonline.gov.in and submit in person at VFS Global Johannesburg. Tel: 012 425 3007.

**Q: Can I apply for OCI on my spouse's eligibility?**
A: No. Husband and wife must each claim OCI on the strength of their own parents/grandparents.

**Q: How do I check passport/PCC status?**
A: Passport: https://www.cgijoburg.gov.in/page/status-of-indian-passport-pcc/ | PCC: https://www.cgijoburg.gov.in/page/status-of-indian-passport-pcc/""",
        "keywords": ["faq", "frequently asked", "questions", "how to", "what is",
                     "damaged passport", "name change", "emergency visa", "spouse oci",
                     "military oci", "passport mistake", "passport status", "pcc status"],
        "source": "https://www.cgijoburg.gov.in",
        "source_verified": True
    }
]


class KnowledgeService:
    """
    Manages versioned knowledge base for deterministic responses.
    """
    
    def __init__(self):
        self.cache: Dict[str, KnowledgeEntry] = {}
        self.initialized = False
    
    async def initialize(self):
        """Initialize knowledge base.

        Flow:
        1. If DB is empty → attempt live scrape of https://www.cgijoburg.gov.in/
           and populate from scraped content (stored as a single 'live' entry).
        2. Always upsert DEFAULT_KNOWLEDGE entries (PDF-verified data) so
           corrections are applied on every restart regardless of live scrape.
        """
        if self.initialized:
            return

        db = await get_database()
        count = await db.knowledge_base.count_documents({})

        # ── Step 1: Live scrape on first run (empty DB) ──────────────────────
        if count == 0:
            logger.info("[KB INIT] Database empty — attempting live scrape of cgijoburg.gov.in")
            try:
                scraped = await scrape_cgi_joburg()
                page_content = scraped.get("page_content", "")
                pages_crawled = scraped.get("pages_crawled", 0)

                if page_content and pages_crawled > 0:
                    live_entry = KnowledgeEntry(
                        category=KnowledgeCategory.GENERAL,
                        title="Live Scraped Content — CGI Johannesburg",
                        question="What is the latest information from the CGI Johannesburg website?",
                        answer=page_content[:8000],  # cap to avoid oversized docs
                        keywords=["cgi", "consulate", "johannesburg", "live", "latest"],
                        source="https://www.cgijoburg.gov.in/",
                        source_verified=True,
                        created_by="system_scraper"
                    )
                    await db.knowledge_base.update_one(
                        {"title": live_entry.title},
                        {"$set": live_entry.to_dict()},
                        upsert=True
                    )
                    logger.info(f"[KB INIT] Live scrape succeeded — {pages_crawled} pages, stored in DB")
                else:
                    logger.info("[KB INIT] Live scrape returned no content — using DEFAULT_KNOWLEDGE only")
            except Exception as e:
                logger.warning(f"[KB INIT] Live scrape failed ({e}) — falling back to DEFAULT_KNOWLEDGE")

        # ── Step 2: Always upsert PDF-verified DEFAULT_KNOWLEDGE ────────────
        for entry_data in DEFAULT_KNOWLEDGE:
            entry = KnowledgeEntry(
                category=KnowledgeCategory(entry_data["category"]),
                title=entry_data["title"],
                question=entry_data["question"],
                answer=entry_data["answer"],
                keywords=entry_data["keywords"],
                source=entry_data["source"],
                source_verified=entry_data["source_verified"]
            )
            await db.knowledge_base.update_one(
                {"title": entry_data["title"]},
                {"$set": entry.to_dict()},
                upsert=True
            )

        logger.info(f"[KB INIT] Upserted {len(DEFAULT_KNOWLEDGE)} verified knowledge entries")
        self.initialized = True
    
    async def search(
        self,
        query: str,
        category: KnowledgeCategory = None,
        limit: int = 5
    ) -> List[Dict]:
        """
        Search knowledge base for relevant entries.
        """
        await self.initialize()
        
        db = await get_database()
        query_lower = query.lower()
        
        # Build search filter
        filter_query = {"status": "active"}
        if category:
            filter_query["category"] = category.value
        
        # Get all active entries (500 gives full coverage for large PDF knowledge bases)
        entries = await db.knowledge_base.find(
            filter_query,
            {"_id": 0}
        ).to_list(500)
        
        # Score entries by relevance
        scored = []
        for entry in entries:
            score = self._calculate_relevance(query_lower, entry)
            if score > 0:
                scored.append((score, entry))

        # Sort by score, then by recency (valid_from → created_at → updated_at)
        # so newer press releases / events beat older ones for the same topic.
        def _recency_key(entry: Dict) -> str:
            return (
                entry.get("valid_from")
                or entry.get("created_at")
                or entry.get("updated_at")
                or ""
            )

        scored.sort(key=lambda x: (x[0], _recency_key(x[1])), reverse=True)

        return [entry for score, entry in scored[:limit]]
    
    @staticmethod
    def _norm(text: str) -> str:
        """Normalize text: lowercase and replace hyphens/underscores with spaces."""
        import re as _re
        return _re.sub(r'[-_]+', ' ', text.lower())

    def _calculate_relevance(self, query: str, entry: Dict) -> float:
        """Calculate relevance score for an entry.

        Normalizes hyphenated terms (e.g. 'id-ul-fitr' == 'id ul fitr') so
        holiday name variants match regardless of hyphenation style.
        """
        import re as _re
        score = 0.0
        norm_query = self._norm(query)
        query_words = [w for w in norm_query.split() if len(w) >= 2]

        # Check keywords (highest weight) — try both raw and normalized forms
        keywords = entry.get("keywords", [])
        for keyword in keywords:
            kw_norm = self._norm(keyword)
            # Full keyword match in normalized query
            if kw_norm in norm_query:
                score += 2.0
            # Partial: any keyword word appears in normalized query
            elif any(w in norm_query for w in kw_norm.split() if len(w) >= 3):
                score += 0.5

        # Check title (normalized)
        title_norm = self._norm(entry.get("title", ""))
        if any(w in title_norm for w in query_words if len(w) >= 3):
            score += 1.5

        # Check question (normalized)
        question_norm = self._norm(entry.get("question", ""))
        if any(w in question_norm for w in query_words if len(w) > 3):
            score += 1.0

        # Bonus: check answer snippet for query words (helps surface PDF sections)
        answer_snippet = self._norm((entry.get("answer") or "")[:300])
        matched_in_answer = sum(1 for w in query_words if len(w) >= 4 and w in answer_snippet)
        if matched_in_answer >= 2:
            score += 0.5

        # Recency boost — keeps newly uploaded press releases / events ahead of
        # older entries on the same topic, so "yoga day" surfaces 2026 before 2025.
        # Only applied when the entry carries a recognised date signal, so plain
        # FAQ entries (no dates) keep their existing relative ranking.
        score += self._recency_boost(entry)

        return score

    @staticmethod
    def _recency_boost(entry: Dict) -> float:
        """Return a small additive score reflecting how recent / upcoming an entry is.

        Priority:
          • event_status == "future"  → +1.5  (upcoming events outrank past)
          • event_status == "present" → +1.0
          • valid_from within last 180 days → +0.5
          • created_at within last 90 days  → +0.3
        Returns 0.0 when no date metadata is present (legacy FAQ entries).
        """
        from datetime import datetime as _dt, timezone as _tz
        boost = 0.0

        status = (entry.get("event_status") or "").lower()
        if status == "future":
            boost += 1.5
        elif status == "present":
            boost += 1.0

        now = _dt.now(_tz.utc)

        def _age_days(iso: Optional[str]) -> Optional[float]:
            if not iso:
                return None
            try:
                ts = _dt.fromisoformat(iso.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=_tz.utc)
                return (now - ts).total_seconds() / 86400.0
            except Exception:
                return None

        vf_age = _age_days(entry.get("valid_from"))
        if vf_age is not None and -365 <= vf_age <= 180:
            boost += 0.5

        ca_age = _age_days(entry.get("created_at"))
        if ca_age is not None and 0 <= ca_age <= 90:
            boost += 0.3

        return boost
    
    async def get_entry(self, entry_id: str) -> Optional[Dict]:
        """Get knowledge entry by ID"""
        db = await get_database()
        return await db.knowledge_base.find_one({"id": entry_id}, {"_id": 0})
    
    async def create_entry(
        self,
        category: KnowledgeCategory,
        title: str,
        question: str,
        answer: str,
        keywords: List[str],
        source: str = "",
        created_by: str = "admin"
    ) -> KnowledgeEntry:
        """Create new knowledge entry"""
        db = await get_database()
        
        entry = KnowledgeEntry(
            category=category,
            title=title,
            question=question,
            answer=answer,
            keywords=keywords,
            source=source,
            created_by=created_by,
            status=KnowledgeStatus.PENDING_REVIEW
        )
        
        await db.knowledge_base.insert_one(entry.to_dict())
        
        logger.info(f"Created knowledge entry: {entry.id} - {title}")
        
        return entry
    
    async def update_entry(
        self,
        entry_id: str,
        updates: Dict,
        updated_by: str = "admin"
    ) -> bool:
        """
        Update knowledge entry with version increment.
        Old version is preserved in history.
        """
        db = await get_database()
        
        # Get current entry
        current = await db.knowledge_base.find_one({"id": entry_id})
        if not current:
            return False
        
        # Store history
        history_entry = {
            "knowledge_id": entry_id,
            "version": current["version"],
            "data": current,
            "archived_at": datetime.now(timezone.utc).isoformat()
        }
        await db.knowledge_history.insert_one(history_entry)
        
        # Update entry
        updates["version"] = current["version"] + 1
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        updates["updated_by"] = updated_by
        
        result = await db.knowledge_base.update_one(
            {"id": entry_id},
            {"$set": updates}
        )
        
        logger.info(f"Updated knowledge entry: {entry_id} to version {updates['version']}")
        
        return result.modified_count > 0
    
    async def get_entry_history(self, entry_id: str) -> List[Dict]:
        """Get version history for an entry"""
        db = await get_database()
        
        history = await db.knowledge_history.find(
            {"knowledge_id": entry_id},
            {"_id": 0}
        ).sort("version", -1).to_list(50)
        
        return history
    
    async def get_all_entries(
        self,
        category: KnowledgeCategory = None,
        status: KnowledgeStatus = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get all knowledge entries with optional filters"""
        db = await get_database()
        
        filter_query = {}
        if category:
            filter_query["category"] = category.value
        if status:
            filter_query["status"] = status.value
        
        entries = await db.knowledge_base.find(
            filter_query,
            {"_id": 0}
        ).sort("updated_at", -1).limit(limit).to_list(limit)
        
        return entries
    
    async def get_stats(self) -> Dict:
        """Get knowledge base statistics"""
        db = await get_database()
        
        # Count by category
        category_pipeline = [
            {"$group": {
                "_id": "$category",
                "count": {"$sum": 1}
            }}
        ]
        category_counts = await db.knowledge_base.aggregate(category_pipeline).to_list(20)
        
        # Count by status
        status_pipeline = [
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1}
            }}
        ]
        status_counts = await db.knowledge_base.aggregate(status_pipeline).to_list(10)
        
        total = await db.knowledge_base.count_documents({})
        verified = await db.knowledge_base.count_documents({"source_verified": True})
        
        return {
            "total_entries": total,
            "verified_entries": verified,
            "verification_rate": round(verified / max(total, 1) * 100, 1),
            "by_category": {c["_id"]: c["count"] for c in category_counts},
            "by_status": {s["_id"]: s["count"] for s in status_counts},
            "categories": [c.value for c in KnowledgeCategory]
        }


# Global knowledge service instance
knowledge_service = KnowledgeService()
