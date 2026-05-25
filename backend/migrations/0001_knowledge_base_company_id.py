"""0001 — Backfill knowledge_base rows with company_id + crawler schema fields.

Assigns `company_id` to every existing row that lacks one (reading the
tenant from $COMPANY_ID — same env var the API server validates at startup)
and populates the new crawler-schema fields so the future crawler upsert
path can treat them as first-class.

Source classification:
  - "pdf"    — source starts with "pdf_upload:"
  - "crawl"  — source is an http(s) URL, or legacy [BGCrawl]/background_crawl:
  - "manual" — anything else

Rows whose `source` is a URL also get `url` + `url_hash` (subject to dedup
against the new `(company_id, url_hash)` unique partial index — first row
at a URL wins; duplicates stay searchable but without url_hash).

Idempotent: only touches rows where `company_id` is missing.
"""
from __future__ import annotations

import hashlib
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

VERSION = 1
DESCRIPTION = "Backfill knowledge_base rows with company_id, source_type, url_hash, content_hash"

LEGACY_TITLE_PREFIX = "[BGCrawl] "
LEGACY_SOURCE_PREFIX = "background_crawl:"
PDF_SOURCE_PREFIX = "pdf_upload:"

logger = logging.getLogger("migrations.0001")


def _sha1(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _classify(row: dict) -> tuple[str, Optional[str]]:
    """Return (source_type, url_or_None) for a legacy row."""
    source = (row.get("source") or "").strip()
    title = (row.get("title") or "").strip()

    if source.startswith(PDF_SOURCE_PREFIX):
        return "pdf", None
    if source.startswith("http://") or source.startswith("https://"):
        return "crawl", source
    if source.startswith(LEGACY_SOURCE_PREFIX):
        url = source[len(LEGACY_SOURCE_PREFIX):].strip()
        return "crawl", url or None
    if title.startswith(LEGACY_TITLE_PREFIX):
        url = title[len(LEGACY_TITLE_PREFIX):].strip()
        return "crawl", url or None
    return "manual", None


async def up(db) -> dict:
    company_id = os.environ.get("COMPANY_ID", "").strip()
    if not company_id:
        raise RuntimeError(
            "0001 requires COMPANY_ID env (the default tenant for legacy rows). "
            "Same value the API server uses for validate_company_id()."
        )

    # Confirm company exists. If not, the API server would have failed startup
    # already, but be explicit so a manual `migrations.runner` invocation also
    # gets a clear error.
    if not await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1}):
        raise RuntimeError(f"company_id {company_id!r} not in `companies`; create it first.")

    query = {"company_id": {"$exists": False}}
    total = await db.knowledge_base.count_documents(query)
    logger.info("Found %d unmigrated rows (assigning to company_id=%s)", total, company_id)

    stats: Counter = Counter()
    seen_hashes: set[str] = set()

    cursor = db.knowledge_base.find(query, {"_id": 0}).batch_size(200)

    async for row in cursor:
        stats["scanned"] += 1
        row_id = row.get("id")
        if not row_id:
            stats["skipped_no_id"] += 1
            logger.warning("Row missing `id` field — cannot update; skipped")
            continue

        source_type, url = _classify(row)
        answer = row.get("answer") or ""
        ts = (
            row.get("updated_at")
            or row.get("created_at")
            or datetime.now(timezone.utc).isoformat()
        )

        update: dict = {
            "company_id":           company_id,
            "source_type":          source_type,
            "content_hash":         _sha256(answer),
            "content_length":       len(answer),
            "consecutive_failures": 0,
            "last_seen_at":         ts,
            "fetched_at":           ts,
            "content_changed_at":   ts,
            "status":               row.get("status") or "active",
            "version":              row.get("version") or 1,
        }

        if url:
            url_hash = _sha1(url)
            collided_in_run = url_hash in seen_hashes
            collided_in_db = False
            if not collided_in_run:
                existing = await db.knowledge_base.find_one(
                    {"company_id": company_id, "url_hash": url_hash, "id": {"$ne": row_id}},
                    {"_id": 0, "id": 1},
                )
                collided_in_db = existing is not None

            if collided_in_run or collided_in_db:
                stats[f"{source_type}_dup_url"] += 1
                logger.info("Duplicate URL — leaving url_hash unset on id=%s url=%s", row_id, url)
            else:
                update["url"] = url
                update["url_hash"] = url_hash
                seen_hashes.add(url_hash)

        stats[source_type] += 1

        result = await db.knowledge_base.update_one({"id": row_id}, {"$set": update})
        if result.modified_count == 1:
            stats["updated"] += 1
        else:
            stats["update_miss"] += 1
            logger.error("Update matched=0 for id=%s", row_id)

    return dict(stats)
