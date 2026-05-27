"""0011 — Platform-wide LLM model registry + per-tenant assignment.

Replaces the hardcoded ``MODEL_MAP`` in
``backend/emergentintegrations/llm/chat.py`` and the hardcoded
``_PRICING`` table in ``backend/services/llm_usage.py`` with a database
collection super-admins can edit at runtime. Each tenant now carries an
explicit allowlist of model keys + a default — no more "every tenant
implicitly gets every model the platform supports".

What this migration does:

  1. Creates the ``platform_models`` collection with a unique index on
     ``key`` so an operator can't ship two rows for the same model.
  2. Seeds the four models that were hardcoded before this migration
     (gpt-4o-mini, gpt-4o, gpt-5, gpt-5.2). Pricing matches the values
     that lived in ``_PRICING``; the ``api_model`` field captures the
     existing ``MODEL_MAP`` resolution (e.g. gpt-5.2 → gpt-4o-mini).
  3. Backfills every ``companies`` row with:
       * ``default_model_key`` — copied from the existing ``llm_model``
         column (or "gpt-4o-mini" if missing).
       * ``allowed_model_keys`` — a single-element list with the same
         key, so a tenant who was using gpt-5.2 keeps using it after
         the migration.

Idempotent: re-running is safe. Existing rows are not overwritten —
the upsert checks ``key`` and the company backfill skips rows that
already have ``default_model_key``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
import uuid

from pymongo.errors import OperationFailure

VERSION = 11
DESCRIPTION = "platform_models registry + tenant model assignment"

logger = logging.getLogger("migrations.0011")

# Mirror of the previous hardcoded MODEL_MAP + _PRICING in code. Each
# entry becomes one row in ``platform_models`` on first run.
SEED_MODELS: List[Dict[str, Any]] = [
    {
        "key":          "gpt-4o-mini",
        "display_name": "GPT-4o mini",
        "provider":     "openai",
        "api_model":    "gpt-4o-mini",
        "description":  "Fast, low-cost general-purpose model. Default for most tenants.",
        "pricing":      {"input_per_1m_usd": 0.15, "output_per_1m_usd": 0.60},
        "capabilities": {"vision": True, "streaming": True, "max_tokens": 16384},
        "enabled":      True,
    },
    {
        "key":          "gpt-4o",
        "display_name": "GPT-4o",
        "provider":     "openai",
        "api_model":    "gpt-4o",
        "description":  "Higher-quality multimodal model. Use when gpt-4o-mini misses nuance.",
        "pricing":      {"input_per_1m_usd": 2.50, "output_per_1m_usd": 10.00},
        "capabilities": {"vision": True, "streaming": True, "max_tokens": 16384},
        "enabled":      True,
    },
    {
        "key":          "gpt-5",
        "display_name": "GPT-5",
        "provider":     "openai",
        # MODEL_MAP previously routed "gpt-5" → "gpt-4o-mini" — keep that
        # alias here so the seeded row matches existing behaviour, then
        # a super-admin can flip the api_model field once gpt-5 is real.
        "api_model":    "gpt-4o-mini",
        "description":  "Reserved key for the next-generation model. Currently aliased to gpt-4o-mini until release.",
        "pricing":      {"input_per_1m_usd": 1.25, "output_per_1m_usd": 10.00},
        "capabilities": {"vision": True, "streaming": True, "max_tokens": 16384},
        "enabled":      True,
    },
    {
        "key":          "gpt-5.2",
        "display_name": "GPT-5.2",
        "provider":     "openai",
        "api_model":    "gpt-4o-mini",  # same alias as MODEL_MAP did
        "description":  "Tenant-facing default. Aliased to gpt-4o-mini at the API boundary.",
        "pricing":      {"input_per_1m_usd": 0.15, "output_per_1m_usd": 0.60},
        "capabilities": {"vision": True, "streaming": True, "max_tokens": 16384},
        "enabled":      True,
    },
]


async def _ensure_indexes(db) -> None:
    """Unique index on (key) — same shape we use for service_key and
    company emails post-Sprint-7."""
    try:
        indexes = await db.platform_models.index_information()
        if "key_unique" not in indexes:
            await db.platform_models.create_index("key", unique=True, name="key_unique")
    except OperationFailure as exc:
        logger.warning("create_index on platform_models.key failed: %s", exc)


async def _seed_models(db) -> int:
    """Upsert the seed list. Re-running won't clobber an operator's
    later edits because we use $setOnInsert for everything except the
    handful of fields they're unlikely to have customised."""
    inserted = 0
    now = datetime.now(timezone.utc).isoformat()
    for spec in SEED_MODELS:
        existing = await db.platform_models.find_one({"key": spec["key"]}, {"_id": 0, "id": 1})
        if existing:
            continue
        doc = dict(spec)
        doc["id"]         = str(uuid.uuid4())
        doc["created_at"] = now
        doc["updated_at"] = now
        doc["created_by"] = "migration_0011"
        await db.platform_models.insert_one(doc)
        inserted += 1
    return inserted


async def _backfill_companies(db) -> int:
    """Give every existing company a default_model_key + allowed_model_keys
    derived from its current ``llm_model`` value. Rows that already have a
    default_model_key (re-run) are skipped."""
    touched = 0
    cursor = db.companies.find({}, {"_id": 0, "id": 1, "llm_model": 1, "default_model_key": 1})
    async for row in cursor:
        if row.get("default_model_key"):
            continue
        key = (row.get("llm_model") or "gpt-4o-mini").strip() or "gpt-4o-mini"
        await db.companies.update_one(
            {"id": row["id"]},
            {"$set": {
                "default_model_key":  key,
                "allowed_model_keys": [key],
            }},
        )
        touched += 1
    return touched


async def up(db) -> dict:
    await _ensure_indexes(db)
    inserted = await _seed_models(db)
    backfilled = await _backfill_companies(db)
    stats = {"models_seeded": inserted, "companies_backfilled": backfilled}
    logger.info("0011 migration done: %s", stats)
    return stats
