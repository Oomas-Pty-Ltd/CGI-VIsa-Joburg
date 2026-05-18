"""Knowledge-base write path for the crawler.

Three entry points:

  upsert_page(...)   — write a successfully-fetched page; content-hash gated
                       so unchanged pages don't bump the version.

  record_failure(...) — bump consecutive_failures on a URL that 404'd /
                       errored this run; flip to status="stale" at threshold.

  sweep_unseen(...)   — after a run finishes, find crawl rows for this tenant
                       that weren't successfully fetched this run and treat
                       them as missed (same failure counter / threshold).

Resurrection: any of these paths can flip a previously-stale row back to
"active" if the URL becomes reachable again.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

from database import get_database

logger = logging.getLogger("crawler.upsert")

# Number of consecutive failed runs (404 or unseen) before a row is marked stale.
STALE_THRESHOLD = 3

# Cap on `answer` length to bound retrieval memory (knowledge_service loads up
# to 500 rows into Python for keyword scoring — see services/knowledge_service.py).
MAX_ANSWER_BYTES = 8192

STATUS_ACTIVE = "active"
STATUS_STALE = "stale"
STATUS_DELETED = "deleted"

SOURCE_TYPE_CRAWL = "crawl"

UpsertResult = Literal["inserted", "unchanged", "updated", "resurrected"]


@dataclass
class PageContent:
    """What the crawler hands to upsert_page after fetch + parse."""
    title: str
    text: str
    language: str
    keywords: list[str]
    category: str


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kb_id(company_id: str, url_hash: str) -> str:
    """Deterministic, stable across runs."""
    return f"kb_{company_id}_{url_hash[:12]}"


def _cap(text: str, max_bytes: int) -> str:
    """Truncate text so its UTF-8 encoding fits in max_bytes."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # Decode with errors='ignore' to drop any partial multi-byte char at the boundary.
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


async def upsert_page(
    company_id: str,
    url: str,
    page: PageContent,
    http_status: int,
) -> UpsertResult:
    """Insert/update a knowledge_base row for one fetched URL.

    Returns:
      "inserted"    — new row created
      "unchanged"   — content_hash matched; only touched fetched_at/last_seen_at
      "updated"     — content changed; version incremented
      "resurrected" — previously stale/deleted, flipped back to active
    """
    db = await get_database()
    url_hash = _sha1(url)
    capped_answer = _cap(page.text, MAX_ANSWER_BYTES)
    content_hash = _sha256(capped_answer)
    now = _now_iso()

    existing = await db.knowledge_base.find_one(
        {"company_id": company_id, "url_hash": url_hash},
        {"_id": 0},
    )

    if existing is None:
        doc = {
            "id":                   _kb_id(company_id, url_hash),
            "company_id":           company_id,
            "source_type":          SOURCE_TYPE_CRAWL,
            "url":                  url,
            "url_hash":             url_hash,
            "title":                page.title,
            "category":             page.category,
            "question":             f"Information from {url}",
            "answer":               capped_answer,
            "content_hash":         content_hash,
            "content_length":       len(capped_answer),
            "language":             page.language,
            "keywords":             page.keywords,
            "version":              1,
            "status":               STATUS_ACTIVE,
            "http_status":          http_status,
            "consecutive_failures": 0,
            "last_seen_at":         now,
            "fetched_at":           now,
            "content_changed_at":   now,
            "created_at":           now,
            "created_by":           "crawler",
            "updated_at":           now,
            "source":               url,   # back-compat with knowledge_service search
        }
        await db.knowledge_base.insert_one(doc)
        return "inserted"

    was_stale = existing.get("status") in (STATUS_STALE,)
    same_content = existing.get("content_hash") == content_hash

    if same_content:
        # Touch-only path. Don't bump version, don't shift content_changed_at.
        set_fields = {
            "fetched_at":           now,
            "last_seen_at":         now,
            "http_status":          http_status,
            "consecutive_failures": 0,
            "updated_at":           now,
        }
        if was_stale:
            set_fields["status"] = STATUS_ACTIVE
        await db.knowledge_base.update_one(
            {"id": existing["id"]},
            {"$set": set_fields},
        )
        return "resurrected" if was_stale else "unchanged"

    # Content changed → real update.
    set_fields = {
        "title":                page.title,
        "category":             page.category,
        "answer":               capped_answer,
        "content_hash":         content_hash,
        "content_length":       len(capped_answer),
        "language":             page.language,
        "keywords":             page.keywords,
        "http_status":          http_status,
        "consecutive_failures": 0,
        "last_seen_at":         now,
        "fetched_at":           now,
        "content_changed_at":   now,
        "updated_at":           now,
        "status":               STATUS_ACTIVE,
        # Keep `source` in sync — knowledge_service search uses it for hybrid hits.
        "source":               url,
    }
    await db.knowledge_base.update_one(
        {"id": existing["id"]},
        {
            "$set": set_fields,
            "$inc": {"version": 1},
        },
    )
    return "resurrected" if was_stale else "updated"


async def record_failure(
    company_id: str,
    url: str,
    http_status: Optional[int],
) -> Optional[str]:
    """Bump `consecutive_failures` on the existing row for this URL.

    Flips status to "stale" once the count hits STALE_THRESHOLD. Returns the
    new status string, or None if no row exists for this URL (nothing to mark).
    Deleted rows are not touched.
    """
    db = await get_database()
    url_hash = _sha1(url)
    now = _now_iso()

    existing = await db.knowledge_base.find_one(
        {"company_id": company_id, "url_hash": url_hash},
        {"_id": 0, "id": 1, "consecutive_failures": 1, "status": 1},
    )
    if not existing:
        return None
    if existing.get("status") == STATUS_DELETED:
        return STATUS_DELETED

    new_count = (existing.get("consecutive_failures") or 0) + 1
    set_fields = {
        "consecutive_failures": new_count,
        "http_status":          http_status,
        "fetched_at":           now,
        "updated_at":           now,
    }
    if new_count >= STALE_THRESHOLD:
        set_fields["status"] = STATUS_STALE

    await db.knowledge_base.update_one(
        {"id": existing["id"]},
        {"$set": set_fields},
    )
    return set_fields.get("status", existing.get("status", STATUS_ACTIVE))


async def sweep_unseen(
    company_id: str,
    seen_url_hashes: set[str],
) -> dict:
    """Post-run reconciliation: rows for this tenant whose URL wasn't seen
    successfully this run get a missed-run penalty (same counter as record_failure).

    Only touches `source_type="crawl"` rows in `status="active"`. Stale and
    deleted rows are left alone.

    Returns counts: {missed, marked_stale}.
    """
    db = await get_database()
    now = _now_iso()
    missed = 0
    marked_stale = 0

    query = {
        "company_id":  company_id,
        "source_type": SOURCE_TYPE_CRAWL,
        "status":      STATUS_ACTIVE,
    }
    cursor = db.knowledge_base.find(
        query,
        {"_id": 0, "id": 1, "url_hash": 1, "consecutive_failures": 1},
    )

    async for row in cursor:
        url_hash = row.get("url_hash")
        # Rows without url_hash were not trackable by this crawler (e.g. legacy
        # dedup duplicates from migration) — leave them alone.
        if not url_hash:
            continue
        if url_hash in seen_url_hashes:
            continue
        missed += 1
        new_count = (row.get("consecutive_failures") or 0) + 1
        set_fields = {
            "consecutive_failures": new_count,
            "updated_at":           now,
        }
        if new_count >= STALE_THRESHOLD:
            set_fields["status"] = STATUS_STALE
            marked_stale += 1
        await db.knowledge_base.update_one(
            {"id": row["id"]},
            {"$set": set_fields},
        )

    logger.info(
        "sweep_unseen company=%s missed=%d marked_stale=%d",
        company_id, missed, marked_stale,
    )
    return {"missed": missed, "marked_stale": marked_stale}
