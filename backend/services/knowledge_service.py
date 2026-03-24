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
# =====================================================================
DEFAULT_KNOWLEDGE = [
    {
        "category": "passport",
        "title": "Passport Renewal Process",
        "question": "How do I renew my Indian passport in South Africa?",
        "answer": """**Passport Renewal Process:**

1. **Book Appointment:** Visit passportindia.gov.in
2. **Complete Application:** Fill the online form
3. **Gather Documents:**
   • Current passport
   • Proof of address in SA
   • Valid visa/residence permit
   • Passport-size photos
4. **Visit Consulate:** CGI Johannesburg
5. **Pay Fees:** R800 (normal) / R1,600 (tatkal)
6. **Processing:** 4-6 weeks (normal) / 1-2 weeks (tatkal)

**Important:** Book appointment before visiting.""",
        "keywords": ["passport", "renewal", "renew", "reissue"],
        "source": "https://www.cgijoburg.gov.in/page/passport-services/",
        "source_verified": True
    },
    {
        "category": "passport",
        "title": "Tatkal Passport",
        "question": "What is Tatkal passport and how to apply?",
        "answer": """**Tatkal (Urgent) Passport:**

**What is it?** Expedited passport processing for urgent needs.

**Processing Time:** 1-2 weeks

**Additional Fee:** Double the normal fee
• New passport: R2,400
• Renewal: R1,600

**Requirements:**
• Proof of urgency (travel tickets, medical emergency, etc.)
• All regular documents
• Higher processing fee

**How to Apply:**
1. Select 'Tatkal' when booking appointment
2. Provide urgency justification
3. Pay tatkal fees""",
        "keywords": ["tatkal", "urgent", "emergency passport", "fast"],
        "source": "https://www.cgijoburg.gov.in/page/passport-services/",
        "source_verified": True
    },
    {
        "category": "visa",
        "title": "Tourist Visa",
        "question": "How to apply for Indian tourist visa?",
        "answer": """**Indian Tourist Visa:**

**Validity:** Up to 10 years (multiple entry)

**Apply Online:** indianvisaonline.gov.in

**Requirements:**
• Valid passport (6+ months validity)
• Passport-size photos
• Completed application form
• Proof of accommodation
• Return flight tickets
• Bank statements (3 months)

**Processing:** 3-5 working days

**Fees:** Varies by nationality and duration

**E-Visa:** Available for most countries - apply online for faster processing.""",
        "keywords": ["tourist visa", "visit visa", "travel visa", "holiday"],
        "source": "https://indianvisaonline.gov.in",
        "source_verified": True
    },
    {
        "category": "oci",
        "title": "OCI Card Application",
        "question": "How to apply for OCI card?",
        "answer": """**OCI (Overseas Citizen of India) Card:**

**What is OCI?** Lifelong visa for foreign nationals of Indian origin.

**Eligibility:**
• Former Indian citizen (or their descendants)
• Spouse of Indian citizen/OCI holder

**Benefits:**
• Lifelong multiple-entry visa
• No police registration required
• Parity with NRIs in financial/property matters

**Documents Required:**
• Current foreign passport
• Proof of Indian origin
• Old Indian passport / Birth certificate
• Passport photos

**Fees:** R1,500 (adult) / R750 (minor)
**Processing:** 6-8 weeks""",
        "keywords": ["oci", "overseas citizen", "indian origin"],
        "source": "https://www.cgijoburg.gov.in/page/oci-services/",
        "source_verified": True
    },
    {
        "category": "fees",
        "title": "Consular Fees",
        "question": "What are the fees for passport, visa, and OCI?",
        "answer": """**CGI Johannesburg Fee Schedule:**

**PASSPORT:**
• New (Normal): R1,200
• New (Tatkal): R2,400
• Renewal (Normal): R800
• Renewal (Tatkal): R1,600

**OCI:**
• Adult: R1,500
• Minor (under 18): R750

**CONSULAR SERVICES:**
• Attestation: R200 per document
• Power of Attorney: R500
• Birth/Death certificate: R300

**Payment Methods:**
• Cash (Rand)
• Bank transfer

*Fees subject to change. Verify current rates before visiting.*""",
        "keywords": ["fees", "cost", "price", "payment", "charges"],
        "source": "https://www.cgijoburg.gov.in/page/fee-schedule/",
        "source_verified": True
    },
    {
        "category": "office",
        "title": "Office Information",
        "question": "What are the CGI Johannesburg office hours and address?",
        "answer": """**Consulate General of India, Johannesburg**

**Address:**
1st Floor, Cedar Square, Corner Willow Ave & Cedar Road
Fourways, Johannesburg 2055

**Contact:**
📞 Phone: +27 6830 38144
📧 Email: cons.joburg@mea.gov.in
🌐 Website: https://www.cgijoburg.gov.in

**Office Hours:**
Monday–Friday: 09:00–17:00

**Consular Services:**
Monday–Friday: 09:00–12:00 (by appointment only)

**Closed:** Indian and South African public holidays

**24/7 Emergency:** +27 6830 38144""",
        "keywords": ["office", "address", "hours", "timing", "contact", "location"],
        "source": "https://www.cgijoburg.gov.in/",
        "source_verified": True
    },
    {
        "category": "emergency",
        "title": "Emergency Assistance",
        "question": "How to get emergency consular assistance?",
        "answer": """**Emergency Consular Assistance**

**24/7 Emergency Helpline:**
📞 +27 6830 38144

**For emergencies involving:**
• Indian citizens in distress
• Lost/stolen passports
• Medical emergencies
• Arrest or detention
• Death of Indian national
• Natural disasters
• Evacuation assistance

**Regular Hours:**
📞 +27 11 783 0202
📧 cons.joburg@mea.gov.in

**Important:**
⚠️ The Consulate NEVER calls asking for money
⚠️ Report scam calls to local police

**Local Emergency:** 10111 (SA Police)""",
        "keywords": ["emergency", "urgent", "help", "crisis", "24/7"],
        "source": "https://www.cgijoburg.gov.in/page/emergency-services/",
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
        """Initialize knowledge base with default entries"""
        if self.initialized:
            return
        
        db = await get_database()
        
        # Check if knowledge base exists
        count = await db.knowledge_base.count_documents({})
        
        # Always upsert default entries by title so corrections are applied on restart
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

        logger.info(f"Upserted {len(DEFAULT_KNOWLEDGE)} default knowledge entries")
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
        
        # Get all active entries
        entries = await db.knowledge_base.find(
            filter_query,
            {"_id": 0}
        ).to_list(100)
        
        # Score entries by relevance
        scored = []
        for entry in entries:
            score = self._calculate_relevance(query_lower, entry)
            if score > 0:
                scored.append((score, entry))
        
        # Sort by score and return top results
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return [entry for score, entry in scored[:limit]]
    
    def _calculate_relevance(self, query: str, entry: Dict) -> float:
        """Calculate relevance score for an entry"""
        score = 0.0
        
        # Check keywords (highest weight)
        keywords = entry.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in query:
                score += 2.0
        
        # Check title
        title = entry.get("title", "").lower()
        if any(word in title for word in query.split()):
            score += 1.5
        
        # Check question
        question = entry.get("question", "").lower()
        if any(word in question for word in query.split() if len(word) > 3):
            score += 1.0
        
        return score
    
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
