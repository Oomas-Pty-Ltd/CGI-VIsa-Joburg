"""0009 — INFO service category + info_content payload.

Adds a third service category alongside the existing TYPE_A (in-house
form-collection) and TYPE_B (redirect to portal): INFO — a reference
card with no application flow. Use cases include status summaries,
contextual help, support details, and announcements.

INFO services carry an ``info_content`` payload (a list of typed
sections — text / bullets / callout / links / contact) plus an
optional single ``primary_action`` CTA for hybrid "info + one action"
surfaces (e.g. "Status summary → Open status portal").

This migration:
  1. Ensures every existing tenant_services row has an ``info_content``
     field (empty default) so the read path never sees an undefined
     value.
  2. Leaves existing categories untouched — TYPE_A / TYPE_B rows
     ignore info_content.

Idempotent: re-runs are no-ops.
"""
from __future__ import annotations

import logging

VERSION = 9
DESCRIPTION = "Add INFO category + info_content default to tenant_services"

logger = logging.getLogger("migrations.0009")

DEFAULT_INFO_CONTENT = {
    "sections": [],
    "primary_action": None,
}


async def up(db) -> dict:
    """Backfill info_content on every existing row that lacks it."""
    result = await db.tenant_services.update_many(
        {"info_content": {"$exists": False}},
        {"$set": {"info_content": DEFAULT_INFO_CONTENT}},
    )
    stats = {
        "matched":   result.matched_count,
        "modified":  result.modified_count,
    }
    logger.info("info_content backfill: %s", stats)
    return stats
