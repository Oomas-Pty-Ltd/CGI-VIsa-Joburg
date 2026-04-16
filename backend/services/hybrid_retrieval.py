"""
====================================================================
SEVA SETU BOT — HYBRID RETRIEVAL SYSTEM
====================================================================
Implements a 4-layer "search → cache → crawl → store" pipeline:

  Layer 1  MongoDB knowledge_base  (persistent, indexed, instant)
           ↓ no strong match
  Layer 2  In-memory scraped cache  (30-min TTL, keyword-filtered)
           ↓ keyword sparse in cache
  Layer 3  Per-keyword deep-scan cache  (30-min in-memory TTL)
           Fresh hit → return immediately
           Stale/missing → fire background crawl, skip to Layer 4
           ↓ background crawl completes
           Stores result in Layer 3 AND writes back to Layer 1
  Layer 4  Structured fallback  (always available, zero latency)

This mirrors how modern AI search works:
  stored knowledge → live cache → on-demand crawl → hardcoded fallback
====================================================================
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from database import get_database

logger = logging.getLogger(__name__)

# Minimum relevance score for a MongoDB hit to be considered "strong"
_KB_CONFIDENCE_THRESHOLD = 2.0

# Minimum scraped-cache line hits before we skip the deep crawl
_CACHE_HIT_THRESHOLD = 3

# Stop words excluded from keyword extraction
_STOP_WORDS = {
    "what", "when", "where", "how", "can", "the", "a", "an", "is", "are",
    "my", "me", "you", "to", "for", "of", "in", "on", "at", "do", "does",
    "will", "would", "could", "should", "with", "from", "this", "that",
    "and", "or", "but", "not", "have", "has", "had", "been", "being", "i",
    "need", "want", "get", "tell", "know", "please", "about",
}

# Holiday / event name aliases: maps variant spellings to all equivalent forms.
# When any key is found in a query, all its aliases are also searched.
_TERM_ALIASES: Dict[str, List[str]] = {
    "eid":      ["id", "idul", "eidul"],
    "id":       ["eid", "idul", "eidul"],
    "fitr":     ["fitar", "fitri"],
    "adha":     ["azha"],
    "muharram": ["moharram"],
    "diwali":   ["deepavali"],
    "holi":     ["holika"],
}


def _normalize(text: str) -> str:
    """Lower-case and replace hyphens/underscores with spaces for fuzzy matching."""
    return re.sub(r'[-_]+', ' ', text.lower())


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _extract_keywords(query: str) -> List[str]:
    """Extract keywords; also captures hyphenated compound words as whole tokens."""
    norm = _normalize(query)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', norm)
    base = [w for w in words if w not in _STOP_WORDS]
    # Also keep full hyphenated tokens from original query (e.g. "id-ul-fitr")
    compound = re.findall(r'\b[a-zA-Z]+-(?:[a-zA-Z]+-)*[a-zA-Z]+\b', query.lower())
    return list(dict.fromkeys(base + compound))  # deduplicate, preserve order


def _expand_keywords(keywords: List[str]) -> List[str]:
    """Add alias variants for known holiday/event name fragments."""
    expanded = list(keywords)
    for kw in keywords:
        for alias in _TERM_ALIASES.get(kw, []):
            if alias not in expanded:
                expanded.append(alias)
    return expanded


def _count_hits(keywords: List[str], content: str) -> int:
    if not content or not keywords:
        return 0
    expanded = _expand_keywords(keywords)
    return sum(
        1 for line in content.split("\n")
        if line.strip() and any(k in _normalize(line) for k in expanded)
    )


def _extract_matching_lines(keywords: List[str], content: str, max_lines: int = 30) -> List[str]:
    """Return lines ranked by number of keyword matches (highest first).

    Lines matching more keywords (e.g. both 'lost' and 'passport') float to
    the top so compound queries return specific content before generic lines.
    Also matches normalized/alias variants for holiday and event names.
    """
    if not content or not keywords:
        return []
    expanded = _expand_keywords(keywords)
    scored = []
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        norm_line = _normalize(stripped)
        count = sum(1 for k in expanded if k in norm_line)
        if count > 0:
            scored.append((count, stripped))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [line for _, line in scored][:max_lines]


def _format_kb_entries(entries: List[Dict]) -> str:
    """Format MongoDB knowledge_base entries into a clean context string."""
    if not entries:
        return ""
    parts = []
    for e in entries:
        title  = e.get("title", "")
        answer = e.get("answer", "").strip()
        source = e.get("source", "")
        if answer:
            block = f"**{title}**\n{answer}"
            if source:
                block += f"\n(Source: {source})"
            parts.append(block)
    return "\n\n---\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND: crawl + store back to MongoDB
# ─────────────────────────────────────────────────────────────────────────────

async def _crawl_and_store(
    cache_key: str,
    keywords: List[str],
    query: str,
    in_progress_set: set,
):
    """
    Background task:
      1. Run deep crawl for keywords.
      2. Store result in per-keyword memory cache.
      3. Write back to MongoDB knowledge_base so Layer 1 catches it next time.
    """
    from knowledge_scraper import (
        _run_deep_crawl,
        _deep_scan_cache,
        _SERVICE_KEYWORDS,
        _DEEP_SCAN_TTL,
    )
    try:
        await _run_deep_crawl(cache_key, keywords, query)
        content = (_deep_scan_cache.get(cache_key) or {}).get("content", "")
        if not content:
            return

        # Detect the service category from keywords
        category = "general"
        for svc_key, kws in _SERVICE_KEYWORDS.items():
            if any(k in query.lower() for k in kws) or any(k in keywords for k in kws):
                category = svc_key
                break

        # Write back to MongoDB knowledge_base
        db = await get_database()
        title = f"[Auto] {query[:80]}"
        await db.knowledge_base.update_one(
            {"title": title},
            {
                "$set": {
                    "title":          title,
                    "category":       category,
                    "question":       query,
                    "answer":         content,
                    "keywords":       keywords[:10],
                    "source":         "live_crawl",
                    "source_verified": False,
                    "status":         "active",
                    "auto_generated": True,
                    "updated_at":     datetime.now(timezone.utc).isoformat(),
                },
                "$setOnInsert": {
                    "id":         f"auto_{cache_key}",
                    "version":    1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": "hybrid_retrieval",
                },
            },
            upsert=True,
        )
        logger.info(f"[HYBRID] Stored crawl result for '{cache_key}' → MongoDB")
    except Exception as e:
        logger.warning(f"[HYBRID] crawl_and_store failed for '{cache_key}': {e}")
    finally:
        in_progress_set.discard(cache_key)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RETRIEVAL PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

_crawl_in_progress: set = set()


async def hybrid_search(query: str, knowledge_base: Dict) -> str:
    """
    4-layer hybrid retrieval — always returns immediately, never blocks.

    Layer 1  MongoDB knowledge_base  →  instant DB lookup
    Layer 2  In-memory scraped cache  →  keyword line scan
    Layer 3  Deep-scan cache / background crawl  →  fire-and-forget
    Layer 4  Structured fallback  →  always available
    """
    keywords = _extract_keywords(query)
    cache_key = "_".join(sorted(set(keywords[:6]))) if keywords else "general"

    # ── Layer 1: MongoDB knowledge_base ──────────────────────────────
    try:
        from services.knowledge_service import knowledge_service
        await knowledge_service.initialize()
        # Fetch top 20 so full PDFs (e.g. holiday calendars with many sections)
        # and multi-topic queries (fee + service combos) all surface
        kb_results = await knowledge_service.search(query, limit=20)
        if kb_results:
            top_score = knowledge_service._calculate_relevance(query.lower(), kb_results[0])
            if top_score >= _KB_CONFIDENCE_THRESHOLD:
                logger.debug(f"[HYBRID L1] '{cache_key}' — MongoDB hit (score {top_score:.1f})")
                # Include ALL entries that scored above threshold
                strong = [
                    e for e in kb_results
                    if knowledge_service._calculate_relevance(query.lower(), e) >= _KB_CONFIDENCE_THRESHOLD
                ]
                return _format_kb_entries(strong)
    except Exception as e:
        logger.warning(f"[HYBRID L1] MongoDB search failed: {e}")

    # ── Layer 2: PDF documents first → knowledge scraper fallback ───────
    # Include the original query phrase so compound terms score higher
    phrase_kws = keywords + ([query.lower().strip()] if len(keywords) > 1 else [])

    uploaded_content = knowledge_base.get("uploaded_docs", {}).get("page_content", "")
    cgi_content      = knowledge_base.get("cgi_joburg", {}).get("page_content", "")
    vfs_content      = knowledge_base.get("vfs_global", {}).get("page_content", "")

    pdf_hits = _count_hits(keywords, uploaded_content)

    # 2a: Uploaded PDF documents have sufficient hits — return PDF content directly
    if pdf_hits >= _CACHE_HIT_THRESHOLD:
        logger.debug(f"[HYBRID L2a] '{cache_key}' — PDF match ({pdf_hits} lines)")
        uploaded_lines = _extract_matching_lines(phrase_kws, uploaded_content, max_lines=50)
        if uploaded_lines:
            return "[Uploaded Documents]\n" + "\n".join(uploaded_lines)

    # 2b: PDF insufficient — check knowledge scraper (CGI Joburg + VFS)
    scraper_hits = _count_hits(keywords, cgi_content + "\n" + vfs_content)
    if scraper_hits >= _CACHE_HIT_THRESHOLD:
        logger.debug(
            f"[HYBRID L2b] '{cache_key}' — PDF insufficient ({pdf_hits} hits), "
            f"knowledge scraper hit ({scraper_hits} lines)"
        )
        parts = []
        # Prepend any partial PDF matches so they're still visible
        if pdf_hits > 0:
            uploaded_lines = _extract_matching_lines(phrase_kws, uploaded_content, max_lines=20)
            if uploaded_lines:
                parts.append("[Uploaded Documents]\n" + "\n".join(uploaded_lines))
        cgi_lines = _extract_matching_lines(phrase_kws, cgi_content)
        vfs_lines = _extract_matching_lines(phrase_kws, vfs_content)
        if cgi_lines:
            parts.append("[CGI Johannesburg — live]\n" + "\n".join(cgi_lines))
        if vfs_lines:
            parts.append("[VFS Global — live]\n" + "\n".join(vfs_lines))
        return "\n\n".join(parts) if parts else ""

    # ── Layer 3: per-keyword deep-scan cache ─────────────────────────
    try:
        from knowledge_scraper import _deep_scan_cache, _DEEP_SCAN_TTL
        cached = _deep_scan_cache.get(cache_key)
        if cached:
            age = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(cached["scanned_at"])
            ).total_seconds()
            if age < _DEEP_SCAN_TTL and cached.get("content"):
                logger.debug(f"[HYBRID L3] '{cache_key}' — deep-scan cache hit (age {int(age)}s)")
                return cached["content"]
    except Exception:
        pass

    # Layer 3 miss → fire background crawl (result available for next request)
    if keywords and cache_key not in _crawl_in_progress:
        _crawl_in_progress.add(cache_key)
        logger.info(f"[HYBRID L3] '{cache_key}' — firing background crawl")
        asyncio.create_task(
            _crawl_and_store(cache_key, keywords, query, _crawl_in_progress)
        )
    else:
        logger.debug(f"[HYBRID L3] '{cache_key}' — crawl already in progress")

    # ── Layer 4: structured fallback (instant) ────────────────────────
    logger.info(f"[HYBRID L4] '{cache_key}' — serving structured fallback")
    from knowledge_scraper import _fallback_for_keywords, _search_knowledge_sync
    fallback = _fallback_for_keywords(keywords, query)
    return fallback if fallback else _search_knowledge_sync(query, knowledge_base)
