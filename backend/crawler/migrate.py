"""One-time backfill of `knowledge_base` rows for multi-tenancy + crawler schema.

Assigns `company_id` to every row that lacks one, and populates the new
crawler-schema fields (`source_type`, `content_hash`, `content_length`,
timestamps) so the future crawler upsert path can treat them as first-class.

Rows whose `source` is a URL also get `url` + `url_hash`, which puts them
under the `(company_id, url_hash)` unique partial index — meaning the next
crawl of the same URL will upsert into the same row (content-hash gated).
Duplicate URLs within the legacy data are detected: the first row wins the
`url_hash`; the rest stay searchable but without `url_hash` so the unique
index isn't violated.

Source classification:
  - "pdf"    — source starts with "pdf_upload:"
  - "crawl"  — source is an http(s) URL, or legacy [BGCrawl]/background_crawl:
  - "manual" — anything else

Idempotent: rows that already have `company_id` are skipped.

Usage:
    cd backend
    python -m crawler.migrate --company-id <UUID> --dry-run
    python -m crawler.migrate --company-id <UUID>
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Optional

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from database import get_database  # noqa: E402

logger = logging.getLogger("crawler.migrate")

LEGACY_TITLE_PREFIX = "[BGCrawl] "
LEGACY_SOURCE_PREFIX = "background_crawl:"
PDF_SOURCE_PREFIX = "pdf_upload:"


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


async def _company_exists(db, company_id: str) -> bool:
    return await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1}) is not None


async def migrate(company_id: str, dry_run: bool = False, batch_size: int = 200) -> dict:
    db = await get_database()

    if not await _company_exists(db, company_id):
        raise SystemExit(
            f"company_id {company_id!r} not found in `companies` collection. "
            "Run `python -m crawler.diagnose` to list valid IDs."
        )

    # Rows that have never been migrated.
    query = {"company_id": {"$exists": False}}
    total = await db.knowledge_base.count_documents(query)
    logger.info(
        "Found %d unmigrated rows in knowledge_base (company_id=%s, dry_run=%s)",
        total, company_id, dry_run,
    )

    stats: Counter = Counter()
    seen_hashes: set[str] = set()

    cursor = db.knowledge_base.find(query, {"_id": 0}).batch_size(batch_size)

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

        # URL-typed rows get url + url_hash, subject to dedup.
        if url:
            url_hash = _sha1(url)
            collided_in_run = url_hash in seen_hashes
            collided_in_db = False
            if not collided_in_run:
                # Check for an already-migrated row at the same (company_id, url_hash).
                existing = await db.knowledge_base.find_one(
                    {"company_id": company_id, "url_hash": url_hash, "id": {"$ne": row_id}},
                    {"_id": 0, "id": 1},
                )
                collided_in_db = existing is not None

            if collided_in_run or collided_in_db:
                stats[f"{source_type}_dup_url"] += 1
                logger.info(
                    "Duplicate URL — leaving url_hash unset on id=%s url=%s",
                    row_id, url,
                )
            else:
                update["url"] = url
                update["url_hash"] = url_hash
                seen_hashes.add(url_hash)

        stats[source_type] += 1

        if dry_run:
            stats["would_update"] += 1
            continue

        try:
            result = await db.knowledge_base.update_one({"id": row_id}, {"$set": update})
            if result.modified_count == 1:
                stats["updated"] += 1
            else:
                stats["update_miss"] += 1
                logger.error("Update matched=0 for id=%s", row_id)
        except Exception as exc:
            stats["errors"] += 1
            logger.exception("Failed to update id=%s: %s", row_id, exc)

    logger.info("Migration complete:")
    for key in sorted(stats):
        logger.info("  %-20s %d", key, stats[key])
    return dict(stats)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--company-id",
        default=os.environ.get("COMPANY_ID"),
        help="Tenant ID to assign to all unmigrated rows (defaults to $COMPANY_ID).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing.")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    if not args.company_id:
        logger.error("--company-id is required (or set COMPANY_ID env var)")
        return 2

    stats = asyncio.run(migrate(args.company_id, dry_run=args.dry_run, batch_size=args.batch_size))

    if stats.get("errors"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
