"""0003 — Convert single-field uniques to compound (company_id, X) on seva_setu_*.

Before: `seva_setu_users.email` is globally unique; same for
`seva_setu_applications.reference_id`. Two tenants can't have a user
with the same email, even though those are conceptually separate
identities.

After: uniqueness is scoped per-tenant. `seva_setu_users.email` is unique
within a `company_id`; same for `reference_id`. Cross-tenant collisions
become permissible (and expected, for common emails like personal ones).

The `seva_setu_users.id` and `seva_setu_applications.id` UUIDs stay
globally unique — they're internal handles.

`edit_token` (on applications) stays a global sparse unique because it's
a long random string used in public review links; collisions are
astronomically unlikely and keeping it global avoids needing to know
the tenant to validate a token.

Pre-check: if cross-tenant collisions already exist on the soon-to-be-
compound key, the migration fails loudly with a list of offending values
so an operator can resolve them manually before re-running.
"""
from __future__ import annotations

import logging
from typing import Any

from pymongo.errors import OperationFailure

VERSION = 3
DESCRIPTION = "Convert seva_setu_users.email and seva_setu_applications.reference_id to compound uniques"

logger = logging.getLogger("migrations.0003")


async def _detect_collisions(db, collection: str, key: str) -> list[dict]:
    """Find values that would violate (company_id, key) uniqueness today."""
    pipeline = [
        {"$match": {"company_id": {"$exists": True}, key: {"$exists": True}}},
        {"$group": {
            "_id": {"company_id": "$company_id", "value": f"${key}"},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 20},
    ]
    return [row async for row in db[collection].aggregate(pipeline)]


async def _drop_if_exists(db, collection: str, index_name: str) -> bool:
    try:
        await db[collection].drop_index(index_name)
        logger.info("dropped %s.%s", collection, index_name)
        return True
    except OperationFailure as exc:
        # 27 = IndexNotFound, also surface as "index not found with name"
        msg = str(exc).lower()
        if "index not found" in msg or getattr(exc, "code", None) == 27:
            logger.info("%s.%s already absent — skipping", collection, index_name)
            return False
        raise


async def _ensure_compound_unique(db, collection: str, fields: list[tuple[str, int]], name: str) -> None:
    # `create_index` is idempotent when the spec matches the existing one;
    # if a non-unique compound was created earlier (Sprint 1A's
    # `(company_id, email)` non-unique helper index), drop it first.
    existing = await db[collection].index_information()
    if name in existing and not existing[name].get("unique"):
        await db[collection].drop_index(name)
        logger.info("dropped non-unique %s.%s to recreate as unique", collection, name)
    await db[collection].create_index(fields, unique=True, name=name)
    logger.info("ensured unique %s.%s on %s", collection, name, fields)


async def up(db) -> dict:
    stats: dict[str, Any] = {}

    # ── seva_setu_users.email ────────────────────────────────────────────────
    collisions = await _detect_collisions(db, "seva_setu_users", "email")
    if collisions:
        sample = [{"company_id": c["_id"]["company_id"], "email": c["_id"]["value"], "count": c["count"]}
                  for c in collisions[:5]]
        raise RuntimeError(
            f"Cannot create unique (company_id, email) on seva_setu_users — "
            f"{len(collisions)} collision(s) already exist. Sample: {sample}. "
            "Deduplicate manually then re-run."
        )
    dropped_users_email = await _drop_if_exists(db, "seva_setu_users", "email_1")
    await _ensure_compound_unique(
        db, "seva_setu_users",
        [("company_id", 1), ("email", 1)],
        name="company_id_1_email_1",
    )
    stats["seva_setu_users"] = {
        "dropped_old_unique": dropped_users_email,
        "compound_unique_created": True,
    }

    # ── seva_setu_applications.reference_id ──────────────────────────────────
    collisions = await _detect_collisions(db, "seva_setu_applications", "reference_id")
    if collisions:
        sample = [{"company_id": c["_id"]["company_id"], "reference_id": c["_id"]["value"], "count": c["count"]}
                  for c in collisions[:5]]
        raise RuntimeError(
            f"Cannot create unique (company_id, reference_id) on seva_setu_applications — "
            f"{len(collisions)} collision(s) already exist. Sample: {sample}."
        )
    dropped_apps_ref = await _drop_if_exists(db, "seva_setu_applications", "reference_id_1")
    await _ensure_compound_unique(
        db, "seva_setu_applications",
        [("company_id", 1), ("reference_id", 1)],
        name="company_id_1_reference_id_1",
    )
    stats["seva_setu_applications"] = {
        "dropped_old_unique": dropped_apps_ref,
        "compound_unique_created": True,
    }

    return stats
