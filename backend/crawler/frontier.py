"""MongoDB-backed BFS frontier for the crawler.

One `crawler_frontier` row per (company_id, run_id, url). Workers claim
the next pending row atomically, fetch + parse, then call the appropriate
`mark_*` helper. Discovered links go through `enqueue_links()` which
deduplicates against the same run.

The frontier survives process restarts: a crashed worker's claimed rows
sit as `in_progress` until the 30-day TTL on `finished_at` expires. A new
run gets a fresh `run_id` and starts clean.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from pymongo import ReturnDocument

from database import get_database

logger = logging.getLogger("crawler.frontier")

STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


@dataclass
class FrontierRow:
    """Minimal view of a claimed frontier row passed to workers."""
    id: str
    company_id: str
    run_id: str
    url: str
    url_hash: str
    depth: int
    parent_url: Optional[str]
    attempts: int


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def seed(
    run_id: str,
    company_id: str,
    seed_urls: Iterable[str],
) -> int:
    """Insert seed URLs at depth 0. Returns count inserted (dedup-safe)."""
    db = await get_database()
    inserted = 0
    for url in seed_urls:
        if not url:
            continue
        url_hash = _sha1(url)
        doc = {
            "id":            str(uuid.uuid4()),
            "company_id":    company_id,
            "run_id":        run_id,
            "url":           url,
            "url_hash":      url_hash,
            "parent_url":    None,
            "depth":         0,
            "status":        STATUS_PENDING,
            "attempts":      0,
            "discovered_at": _now_iso(),
            "started_at":    None,
            "finished_at":   None,
            "http_status":   None,
            "last_error":    None,
            "skip_reason":   None,
        }
        try:
            await db.crawler_frontier.insert_one(doc)
            inserted += 1
        except Exception as exc:
            # Duplicate (company_id, run_id, url_hash) — fine.
            logger.debug("Seed dedup for %s: %s", url, exc)
    logger.info("Seeded %d / %d URLs for run %s", inserted, len(list(seed_urls)) if hasattr(seed_urls, '__len__') else inserted, run_id)
    return inserted


async def claim_next(run_id: str, company_id: str) -> Optional[FrontierRow]:
    """Atomically claim the next pending URL (BFS order) for a worker.

    Returns None when no pending rows remain.
    """
    db = await get_database()
    doc = await db.crawler_frontier.find_one_and_update(
        {
            "company_id": company_id,
            "run_id":     run_id,
            "status":     STATUS_PENDING,
        },
        {
            "$set":  {"status": STATUS_IN_PROGRESS, "started_at": _now_iso()},
            "$inc":  {"attempts": 1},
        },
        sort=[("depth", 1), ("discovered_at", 1)],   # BFS
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    if not doc:
        return None
    return FrontierRow(
        id=doc["id"],
        company_id=doc["company_id"],
        run_id=doc["run_id"],
        url=doc["url"],
        url_hash=doc["url_hash"],
        depth=doc["depth"],
        parent_url=doc.get("parent_url"),
        attempts=doc["attempts"],
    )


async def mark_success(frontier_id: str, http_status: int) -> None:
    db = await get_database()
    await db.crawler_frontier.update_one(
        {"id": frontier_id},
        {"$set": {
            "status":      STATUS_SUCCESS,
            "http_status": http_status,
            "finished_at": _now_iso(),
        }},
    )


async def mark_failed(frontier_id: str, http_status: Optional[int], error: str) -> None:
    db = await get_database()
    await db.crawler_frontier.update_one(
        {"id": frontier_id},
        {"$set": {
            "status":      STATUS_FAILED,
            "http_status": http_status,
            "last_error":  error[:500],
            "finished_at": _now_iso(),
        }},
    )


async def mark_skipped(frontier_id: str, reason: str) -> None:
    db = await get_database()
    await db.crawler_frontier.update_one(
        {"id": frontier_id},
        {"$set": {
            "status":      STATUS_SKIPPED,
            "skip_reason": reason,
            "finished_at": _now_iso(),
        }},
    )


async def enqueue_links(
    run_id: str,
    company_id: str,
    parent_url: str,
    parent_depth: int,
    links: Iterable[str],
    max_depth: int,
    max_pages: int,
) -> int:
    """Enqueue discovered links. Dedup by (company_id, run_id, url_hash).

    Caller is responsible for domain/pattern filtering before calling this.
    Stops inserting once total pending+in_progress+success would exceed max_pages.
    Returns count inserted.
    """
    if parent_depth + 1 > max_depth:
        return 0

    db = await get_database()
    inserted = 0
    next_depth = parent_depth + 1
    now = _now_iso()

    for url in links:
        if not url:
            continue

        # Cheap quota check before each insert (allows other workers to add too).
        active = await db.crawler_frontier.count_documents({
            "company_id": company_id,
            "run_id":     run_id,
            "status":     {"$in": [STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_SUCCESS]},
        })
        if active >= max_pages:
            logger.info("max_pages=%d reached for run %s — stopping enqueue", max_pages, run_id)
            return inserted

        doc = {
            "id":            str(uuid.uuid4()),
            "company_id":    company_id,
            "run_id":        run_id,
            "url":           url,
            "url_hash":      _sha1(url),
            "parent_url":    parent_url,
            "depth":         next_depth,
            "status":        STATUS_PENDING,
            "attempts":      0,
            "discovered_at": now,
            "started_at":    None,
            "finished_at":   None,
            "http_status":   None,
            "last_error":    None,
            "skip_reason":   None,
        }
        try:
            await db.crawler_frontier.insert_one(doc)
            inserted += 1
        except Exception:
            # Duplicate url_hash for this run — already enqueued. Silent.
            pass

    return inserted


async def run_stats(run_id: str) -> dict:
    """Counts by status for a run. Returns dict with all status keys present."""
    db = await get_database()
    pipeline = [
        {"$match": {"run_id": run_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    out = {s: 0 for s in (STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_SUCCESS, STATUS_FAILED, STATUS_SKIPPED)}
    async for row in db.crawler_frontier.aggregate(pipeline):
        out[row["_id"]] = row["count"]
    out["total"] = sum(out.values())
    return out


async def successful_url_hashes(run_id: str, company_id: str) -> set[str]:
    """Set of url_hashes successfully fetched in this run. Used by the post-run sweep."""
    db = await get_database()
    cursor = db.crawler_frontier.find(
        {"company_id": company_id, "run_id": run_id, "status": STATUS_SUCCESS},
        {"_id": 0, "url_hash": 1},
    )
    return {row["url_hash"] async for row in cursor}
