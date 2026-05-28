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
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from database import get_database
from knowledge_scraper import scrape_cgi_joburg

logger = logging.getLogger(__name__)


async def _bust_response_cache(company_id: Optional[str]) -> None:
    """Drop the tenant's cached chat answers after a KB content change so a
    correction can't be masked by a stale cached answer. No-op when the response
    cache is disabled. Never raises — cache hygiene must not break a KB write."""
    try:
        from services import response_cache
        await response_cache.invalidate_tenant(company_id)
    except Exception:
        logger.debug("[KB] response_cache invalidate skipped for %s", company_id)


class KnowledgeCategory(Enum):
    """Knowledge base categories — platform fallback set.

    Tenants override this list via ``tenant_bot_config.knowledge_categories``.
    The enum stays for back-compat with internal callers that pass
    ``KnowledgeCategory.GENERAL`` as a default; everywhere else (admin
    create/list endpoints) we accept any string in the tenant's resolved
    category list so a freshly-onboarded tenant can name its own buckets.
    """
    PASSPORT = "passport"
    VISA = "visa"
    OCI = "oci"
    CONSULAR = "consular"
    FEES = "fees"
    EMERGENCY = "emergency"
    OFFICE = "office"
    GENERAL = "general"


# Neutral platform default — used when a tenant hasn't configured
# ``knowledge_categories`` on bot_config. Mirrors the legacy enum values
# minus the CGI-tinged ones ("oci", "consular") so a generic tenant
# doesn't see those in the category dropdown.
DEFAULT_KNOWLEDGE_CATEGORIES: List[str] = [
    "general", "fees", "emergency", "office", "announcement", "event", "other",
]


def resolve_knowledge_categories(stored: List[str] | None) -> List[str]:
    """Return the effective category list for a tenant. Empty/missing
    ``stored`` falls back to ``DEFAULT_KNOWLEDGE_CATEGORIES``."""
    out = [str(c).strip().lower() for c in (stored or []) if str(c).strip()]
    return out or list(DEFAULT_KNOWLEDGE_CATEGORIES)


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
    company_id: Optional[str] = None  # Tenant that owns this entry
    # Either a ``KnowledgeCategory`` enum member or a free-form string from
    # the tenant's ``knowledge_categories`` config. ``to_dict`` collapses
    # both to a plain string for storage.
    category: Any = KnowledgeCategory.GENERAL
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
    # event_status: one of "past" | "present" | "future" | "general"
    # Auto-derived by the PDF upload pipeline from dates in the text; can also
    # be set manually for short events or when date parsing didn't fire.
    event_status: Optional[str] = None

    def to_dict(self) -> Dict:
        cat = self.category
        cat_str = cat.value if isinstance(cat, KnowledgeCategory) else str(cat)
        return {
            "id": self.id,
            "company_id": self.company_id,
            "category": cat_str,
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
            "valid_until": self.valid_until,
            "event_status": self.event_status,
        }


# =====================================================================
# DEFAULT KNOWLEDGE BASE
# Empty by design — every tenant seeds its own knowledge via the Knowledge
# Base tab in the super-admin UI. Previously this list contained CGI
# Johannesburg-specific entries that leaked across tenants on first run.
# =====================================================================
DEFAULT_KNOWLEDGE = []


class KnowledgeService:
    """
    Manages versioned knowledge base for deterministic responses.
    """
    
    def __init__(self):
        self.cache: Dict[str, KnowledgeEntry] = {}
        self.initialized = False
    
    async def initialize(self):
        """Initialise the default tenant's knowledge base.

        DEFAULT_KNOWLEDGE is empty by design — every tenant supplies its own
        entries via the super-admin Knowledge Base tab. On first start, if
        the default tenant's KB is empty AND it has scrape sources
        configured on bot_config, a live scrape is performed and stored as
        a single ``live`` entry. New tenants never get any auto-seeded
        content — they upload their own data via the super-admin endpoints.
        """
        if self.initialized:
            return

        # The default-tenant seed only runs if COMPANY_ID is set — otherwise
        # initialise is a no-op (e.g. CI without a tenant configured yet).
        from config import COMPANY_ID as _default_tenant
        if not _default_tenant:
            logger.info("[KB INIT] COMPANY_ID not set — skipping default-tenant seed")
            self.initialized = True
            return

        db = await get_database()
        count = await db.knowledge_base.count_documents({"company_id": _default_tenant})

        # ── Step 1: Live scrape on first run (empty KB for default tenant) ──
        if count == 0:
            logger.info("[KB INIT] Default tenant KB empty — attempting live scrape from configured sources")
            try:
                scraped = await scrape_cgi_joburg(_default_tenant)
                page_content = scraped.get("page_content", "")
                pages_crawled = scraped.get("pages_crawled", 0)
                src_url = scraped.get("source", "")

                if page_content and pages_crawled > 0:
                    live_entry = KnowledgeEntry(
                        company_id=_default_tenant,
                        category=KnowledgeCategory.GENERAL,
                        title="Live Scraped Content",
                        question="What is the latest information from the primary website?",
                        answer=page_content[:8000],  # cap to avoid oversized docs
                        keywords=["live", "latest", "official"],
                        source=src_url or "primary",
                        source_verified=True,
                        created_by="system_scraper"
                    )
                    await db.knowledge_base.update_one(
                        {"title": live_entry.title, "company_id": _default_tenant},
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
                company_id=_default_tenant,
                category=KnowledgeCategory(entry_data["category"]),
                title=entry_data["title"],
                question=entry_data["question"],
                answer=entry_data["answer"],
                keywords=entry_data["keywords"],
                source=entry_data["source"],
                source_verified=entry_data["source_verified"]
            )
            await db.knowledge_base.update_one(
                {"title": entry_data["title"], "company_id": _default_tenant},
                {"$set": entry.to_dict()},
                upsert=True
            )

        logger.info(f"[KB INIT] Upserted {len(DEFAULT_KNOWLEDGE)} verified entries for tenant {_default_tenant}")
        self.initialized = True
    
    async def search(
        self,
        query: str,
        company_id: str,
        category: KnowledgeCategory = None,
        limit: int = 5
    ) -> List[Dict]:
        """Search knowledge base for relevant entries within a tenant.

        ``company_id`` is required — searching cross-tenant would mix one
        tenant's FAQs into another tenant's bot responses."""
        await self.initialize()

        db = await get_database()
        query_lower = query.lower()

        # Build search filter (tenant-scoped, active entries only)
        filter_query: Dict[str, Any] = {"status": "active", "company_id": company_id}
        if category:
            filter_query["category"] = category.value if isinstance(category, KnowledgeCategory) else str(category)

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
    
    async def get_entry(self, entry_id: str, company_id: Optional[str] = None) -> Optional[Dict]:
        """Get knowledge entry by ID. Pass ``company_id`` to scope the
        lookup to one tenant (defensive when used from a tenant-scoped UI);
        omit for super-admin cross-tenant access."""
        db = await get_database()
        query: Dict[str, Any] = {"id": entry_id}
        if company_id is not None:
            query["company_id"] = company_id
        return await db.knowledge_base.find_one(query, {"_id": 0})

    async def create_entry(
        self,
        company_id: str,
        category: KnowledgeCategory,
        title: str,
        question: str,
        answer: str,
        keywords: List[str],
        source: str = "",
        created_by: str = "admin",
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
        event_status: Optional[str] = None,
    ) -> KnowledgeEntry:
        """Create new knowledge entry. ``company_id`` is required — every
        entry belongs to exactly one tenant. Bot searches are tenant-scoped
        so untagged entries would simply never surface.

        ``valid_from`` / ``valid_until`` / ``event_status`` are optional
        overrides for short events or for entries where automatic date
        parsing isn't appropriate (manual KB entry creation never runs
        the parser)."""
        db = await get_database()

        entry = KnowledgeEntry(
            company_id=company_id,
            category=category,
            title=title,
            question=question,
            answer=answer,
            keywords=keywords,
            source=source,
            created_by=created_by,
            status=KnowledgeStatus.PENDING_REVIEW,
            valid_from=valid_from,
            valid_until=valid_until,
            event_status=event_status,
        )

        await db.knowledge_base.insert_one(entry.to_dict())
        await _bust_response_cache(company_id)

        logger.info(f"Created knowledge entry: {entry.id} - {title} (tenant={company_id})")

        return entry

    async def update_entry(
        self,
        entry_id: str,
        updates: Dict,
        updated_by: str = "admin",
        company_id: Optional[str] = None,
    ) -> bool:
        """Update knowledge entry with version increment. Old version is
        preserved in history. Pass ``company_id`` to require the entry
        belong to that tenant — without it, a super-admin can mutate any
        entry by ID."""
        db = await get_database()

        # Get current entry — scoped to caller's tenant if specified
        query: Dict[str, Any] = {"id": entry_id}
        if company_id is not None:
            query["company_id"] = company_id
        current = await db.knowledge_base.find_one(query)
        if not current:
            return False

        # Store history
        history_entry = {
            "knowledge_id": entry_id,
            "company_id": current.get("company_id"),
            "version": current["version"],
            "data": current,
            "archived_at": datetime.now(timezone.utc).isoformat()
        }
        await db.knowledge_history.insert_one(history_entry)

        # Update entry
        updates["version"] = current["version"] + 1
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        updates["updated_by"] = updated_by
        # Never let the update payload reassign tenancy
        updates.pop("company_id", None)

        result = await db.knowledge_base.update_one(
            query,
            {"$set": updates}
        )
        await _bust_response_cache(current.get("company_id"))

        logger.info(f"Updated knowledge entry: {entry_id} to version {updates['version']}")

        return result.modified_count > 0

    async def get_entry_history(self, entry_id: str, company_id: Optional[str] = None) -> List[Dict]:
        """Get version history for an entry, optionally scoped by tenant."""
        db = await get_database()

        query: Dict[str, Any] = {"knowledge_id": entry_id}
        if company_id is not None:
            query["company_id"] = company_id

        history = await db.knowledge_history.find(
            query, {"_id": 0}
        ).sort("version", -1).to_list(50)

        return history

    async def get_all_entries(
        self,
        category: KnowledgeCategory = None,
        status: KnowledgeStatus = None,
        limit: int = 100,
        company_id: Optional[str] = None,
    ) -> List[Dict]:
        """Get all knowledge entries with optional filters. ``company_id=None``
        returns across all tenants (super-admin); pass it for a
        tenant-scoped admin view."""
        db = await get_database()

        filter_query: Dict[str, Any] = {}
        if category:
            filter_query["category"] = category.value if isinstance(category, KnowledgeCategory) else str(category)
        if status:
            filter_query["status"] = status.value
        if company_id is not None:
            filter_query["company_id"] = company_id

        entries = await db.knowledge_base.find(
            filter_query,
            {"_id": 0}
        ).sort("updated_at", -1).limit(limit).to_list(limit)

        return entries

    async def get_stats(self, company_id: Optional[str] = None) -> Dict:
        """Get knowledge base statistics, optionally tenant-scoped."""
        db = await get_database()

        base_match: Dict[str, Any] = {}
        if company_id is not None:
            base_match["company_id"] = company_id

        # Count by category
        category_pipeline = []
        if base_match:
            category_pipeline.append({"$match": dict(base_match)})
        category_pipeline.append({"$group": {"_id": "$category", "count": {"$sum": 1}}})
        category_counts = await db.knowledge_base.aggregate(category_pipeline).to_list(20)

        # Count by status
        status_pipeline = []
        if base_match:
            status_pipeline.append({"$match": dict(base_match)})
        status_pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})
        status_counts = await db.knowledge_base.aggregate(status_pipeline).to_list(10)

        total_filter = dict(base_match)
        total = await db.knowledge_base.count_documents(total_filter)
        verified_filter = {**total_filter, "source_verified": True}
        verified = await db.knowledge_base.count_documents(verified_filter)

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
