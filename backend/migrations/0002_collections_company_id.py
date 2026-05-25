"""0002 — Backfill `company_id` across remaining single-tenant collections.

Adds the default tenant (from $COMPANY_ID) to every row in:
  users, documents, feedback, notifications, escalations,
  applications, seva_setu_applications, seva_setu_users,
  whatsapp_sessions, ics_whatsapp_sessions

Bulk update per collection — each `update_many` only touches rows missing
`company_id`, so re-runs are no-ops.

Note: this migration does NOT modify existing unique indexes (e.g., the
unique on `users.email`). Promoting those to compound uniques like
`(company_id, email)` requires a cross-tenant collision audit first and
ships as its own future migration.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

VERSION = 2
DESCRIPTION = "Backfill company_id across users/documents/feedback/notifications/escalations/applications/sessions"

logger = logging.getLogger("migrations.0002")

TARGET_COLLECTIONS = (
    "users",
    "documents",
    "feedback",
    "notifications",
    "escalations",
    "applications",
    "seva_setu_applications",
    "seva_setu_users",
    "whatsapp_sessions",
    "ics_whatsapp_sessions",
)


async def up(db) -> dict:
    company_id = os.environ.get("COMPANY_ID", "").strip()
    if not company_id:
        raise RuntimeError("COMPANY_ID env required (same value as validate_company_id uses).")
    if not await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1}):
        raise RuntimeError(f"company_id {company_id!r} not in `companies` collection.")

    now = datetime.now(timezone.utc).isoformat()
    stats: dict = {}

    for collection in TARGET_COLLECTIONS:
        coll = db[collection]
        missing_filter = {"company_id": {"$exists": False}}

        before = await coll.count_documents(missing_filter)
        if before == 0:
            stats[collection] = {"before": 0, "updated": 0}
            logger.info("%-30s no rows to update", collection)
            continue

        result = await coll.update_many(
            missing_filter,
            {"$set": {"company_id": company_id, "company_id_backfilled_at": now}},
        )
        stats[collection] = {"before": before, "updated": result.modified_count}
        logger.info("%-30s before=%d updated=%d", collection, before, result.modified_count)

    return stats
