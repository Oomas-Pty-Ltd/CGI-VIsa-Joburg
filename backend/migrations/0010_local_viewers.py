"""0010 — Read-only viewer accounts (`local_viewers` collection).

A viewer is a tenant-scoped account with read access to the local-admin
console — same data visibility as a local_admin for their tenant, but
backend routes reject any POST/PUT/PATCH/DELETE from a viewer token
(see ``auth_utils.verify_admin``).

This migration:
  1. Creates the ``local_viewers`` collection if it doesn't exist (a
     no-op on Mongo since collections are implicit, but indices need
     to be declared).
  2. Adds a unique index on (email) so a person can only viewer-on
     exactly one tenant — same constraint as local_admins post-0007.
  3. Adds a (company_id) index for tenant-scoped listing.
  4. Pre-flight check: ensure no email collides between local_viewers
     and the existing local_admins / super_admins collections. If a
     conflict exists, abort with a clear message so the operator can
     dedupe manually before re-running.

Idempotent: re-runs are no-ops.
"""
from __future__ import annotations

import logging
from typing import Any, List

from pymongo.errors import OperationFailure

VERSION = 10
DESCRIPTION = "Create local_viewers collection + email-unique index"

logger = logging.getLogger("migrations.0010")


async def _viewer_email_collisions(db) -> List[str]:
    """Emails that exist in `local_viewers` AND in another admin
    collection — would break the login resolver. Return up to 50."""
    pipeline = [
        {"$lookup": {
            "from": "local_admins",
            "localField": "email",
            "foreignField": "email",
            "as": "admins",
        }},
        {"$lookup": {
            "from": "super_admins",
            "localField": "email",
            "foreignField": "email",
            "as": "supers",
        }},
        {"$match": {"$or": [{"admins.0": {"$exists": True}}, {"supers.0": {"$exists": True}}]}},
        {"$project": {"_id": 0, "email": 1}},
        {"$limit": 50},
    ]
    return [row["email"] async for row in db.local_viewers.aggregate(pipeline) if row.get("email")]


async def up(db) -> dict:
    stats: dict[str, Any] = {}

    colliding = await _viewer_email_collisions(db)
    if colliding:
        raise RuntimeError(
            "Cannot create local_viewers indices: emails already exist "
            "in local_admins or super_admins. Remove or rename these viewer "
            f"rows before re-running: {colliding}"
        )

    # Drop any non-unique email index from a previous run (idempotent).
    try:
        indexes = await db.local_viewers.index_information()
        for name, spec in indexes.items():
            key = spec.get("key") or []
            if len(key) == 1 and key[0][0] == "email" and not spec.get("unique"):
                logger.info("Dropping non-unique index %s on local_viewers.email", name)
                await db.local_viewers.drop_index(name)
    except OperationFailure as exc:
        logger.warning("index_information failed on local_viewers: %s", exc)

    await db.local_viewers.create_index("email", unique=True, name="email_unique")
    await db.local_viewers.create_index("company_id", name="company_id_lookup")
    stats["indexes"] = ["email_unique", "company_id_lookup"]

    logger.info("local_viewers migration done: %s", stats)
    return stats
