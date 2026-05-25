"""0004 — Backfill `company_id` on messaging collections.

These collections weren't in migration 0002's target list because they were
not on the multi-tenancy roadmap at the time. Sprint 2D wires the webhook
routes to tag new writes with `company_id` via the channel resolver; this
migration handles the legacy rows.

Collections covered:
  - whatsapp_users         (Twilio inbound users)
  - whatsapp_messages      (Twilio message history)
  - facebook_users         (Facebook Messenger users)
  - facebook_messages      (Facebook message history)
  - ics_whatsapp_messages  (ICS-WABA inbound/outbound)

Identical bulk-update-many pattern as 0002. Idempotent — only touches rows
with no existing `company_id`.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

VERSION = 4
DESCRIPTION = "Backfill company_id on whatsapp/facebook/ics messaging collections"

logger = logging.getLogger("migrations.0004")

TARGET_COLLECTIONS = (
    "whatsapp_users",
    "whatsapp_messages",
    "facebook_users",
    "facebook_messages",
    "ics_whatsapp_messages",
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
