"""0007 — Globally unique email across local_admins (and super_admins).

Sprint 7 unifies the super-admin and local-admin login pages. With one
login form, an email address must identify exactly one console user —
otherwise the resolver can't decide which row to authenticate.

Per the design decision: emails are globally unique at the
``local_admins`` level (not per-tenant). A single real person who
administrates two tenants needs two distinct email aliases.

Pre-check: detect collisions first and fail loudly with the offending
emails so the operator can fix them manually (rename one, delete one,
etc.) before re-running. The migration never silently dedupes — that
would discard real data.

Idempotent: re-running with the index already present is a no-op.
"""
from __future__ import annotations

import logging
from typing import Any, List

from pymongo.errors import OperationFailure

VERSION = 7
DESCRIPTION = "Globally unique email on local_admins and super_admins"

logger = logging.getLogger("migrations.0007")


async def _detect_duplicates(db, collection: str) -> List[dict]:
    """Return rows with duplicate (case-insensitive) emails."""
    pipeline = [
        {"$match": {"email": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": {"$toLower": "$email"},
            "count": {"$sum": 1},
            "ids": {"$push": "$id"},
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 50},
    ]
    return [row async for row in db[collection].aggregate(pipeline)]


async def _ensure_unique_email(db, collection: str) -> dict:
    """Detect duplicates, then create a unique index on email if clean."""
    dupes = await _detect_duplicates(db, collection)
    if dupes:
        msg_lines = [f"  - {d['_id']!r} appears in ids {d['ids']}" for d in dupes]
        raise RuntimeError(
            f"Cannot enforce unique email on {collection}: duplicates exist.\n"
            "Resolve manually (rename, merge, or delete) before re-running:\n"
            + "\n".join(msg_lines)
        )

    # Drop any non-unique index on email first (idempotent)
    try:
        indexes = await db[collection].index_information()
        for name, spec in indexes.items():
            key = spec.get("key") or []
            if len(key) == 1 and key[0][0] == "email" and not spec.get("unique"):
                logger.info("Dropping non-unique index %s on %s.email", name, collection)
                await db[collection].drop_index(name)
    except OperationFailure as exc:
        logger.warning("Couldn't inspect/drop existing indexes on %s: %s", collection, exc)

    # Create the unique index. Idempotent — pymongo no-ops if it already exists.
    await db[collection].create_index("email", unique=True, name="email_unique")
    return {"collection": collection, "unique_index": "email_unique"}


async def up(db) -> dict:
    stats: dict[str, Any] = {}
    for coll in ("local_admins", "super_admins"):
        stats[coll] = await _ensure_unique_email(db, coll)
    logger.info("Unique-email migration done: %s", stats)
    return stats
