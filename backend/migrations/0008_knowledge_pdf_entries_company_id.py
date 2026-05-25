"""0008 — Backfill `company_id` on PDF-uploaded knowledge_base entries.

The PDF upload path in `super_admin_routes.upload_pdf_to_knowledge`
historically created entries without a `company_id` because PDF
uploads were treated as a global resource. Sprint 14 makes them
per-tenant so the super-admin Knowledge tab can filter by company.

Backfill rule: any knowledge_base row sourced from `pdf_upload:*`
that does NOT already have a non-null `company_id` gets the env-var
``COMPANY_ID`` (the default tenant) assigned. Rows from other sources
(live scrape, DEFAULT_KNOWLEDGE seed) are left alone — those were
already tenant-scoped by Sprint 4.

Idempotent: re-running is a no-op once company_id is populated.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

VERSION = 8
DESCRIPTION = "Backfill company_id on PDF-uploaded knowledge_base entries"

logger = logging.getLogger("migrations.0008")


async def up(db) -> dict:
    company_id = os.environ.get("COMPANY_ID", "").strip()
    if not company_id:
        raise RuntimeError("COMPANY_ID env required — that's the default tenant the PDF uploads get assigned to.")
    if not await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1}):
        raise RuntimeError(f"company_id {company_id!r} is not in the companies collection.")

    # Only target rows where company_id is missing OR null. Leaves rows
    # that have already been (correctly) tagged alone.
    query = {
        "source": {"$regex": "^pdf_upload:"},
        "$or": [
            {"company_id": {"$exists": False}},
            {"company_id": None},
        ],
    }

    now = datetime.now(timezone.utc).isoformat()
    result = await db.knowledge_base.update_many(
        query,
        {"$set": {"company_id": company_id, "migration_0008_at": now}},
    )

    logger.info(
        "Backfilled company_id on %d PDF knowledge_base rows (tenant=%s)",
        result.modified_count, company_id,
    )
    return {"updated": result.modified_count, "tenant": company_id}
