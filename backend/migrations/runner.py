"""Migration discovery + runner.

Filesystem layout drives ordering: any file matching `NNNN_*.py` in this
package is a migration. The 4-digit prefix is the version number.

Concurrency: the unique index on `schema_migrations.version` (created in
database.py:create_indexes) prevents two replicas from applying the same
migration twice. The runner uses a two-phase insert:

  1. INSERT {version, status: "in_progress"} — race winner, others get
     DuplicateKeyError and skip (or wait, in `run_pending`'s case).
  2. Run `up(db)`. On success, update status to "applied" + stats.
     On exception, update status to "failed" with the error string.

Each migration is responsible for its own idempotency (so a re-run after
a half-finished failure is safe).
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger("migrations.runner")

_MIGRATION_FILE_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.py$")


# ── discovery ───────────────────────────────────────────────────────────────

def discover() -> list[tuple[int, str]]:
    """Return [(version, module_basename), ...] sorted by version."""
    here = Path(__file__).parent
    out: list[tuple[int, str]] = []
    seen_versions: set[int] = set()
    for f in sorted(here.iterdir()):
        m = _MIGRATION_FILE_RE.match(f.name)
        if not m:
            continue
        version = int(m.group(1))
        if version in seen_versions:
            raise RuntimeError(f"Duplicate migration version {version:04d} — {f.name}")
        seen_versions.add(version)
        out.append((version, f.stem))
    return out


async def applied_versions(db) -> dict[int, dict]:
    """Map of {version: record} for migrations that have reached terminal state."""
    cursor = db.schema_migrations.find({}, {"_id": 0})
    return {row["version"]: row async for row in cursor}


# ── apply one ───────────────────────────────────────────────────────────────

async def _apply_one(db, version: int, modname: str) -> dict:
    """Apply a single migration. Returns a record describing the outcome."""
    full_name = f"migrations.{modname}"
    module = importlib.import_module(full_name)

    declared = getattr(module, "VERSION", None)
    if declared != version:
        raise RuntimeError(
            f"{modname}: VERSION constant ({declared}) doesn't match filename ({version})"
        )

    description = getattr(module, "DESCRIPTION", "")
    now = datetime.now(timezone.utc).isoformat()

    # Phase 1: claim the slot. Unique index on `version` makes this atomic.
    try:
        await db.schema_migrations.insert_one({
            "version":     version,
            "name":        modname,
            "description": description,
            "status":      "in_progress",
            "started_at":  now,
        })
    except DuplicateKeyError:
        # Another replica won the race, OR this migration is already done/failed.
        existing = await db.schema_migrations.find_one({"version": version}, {"_id": 0})
        logger.info("Migration %d already %s — skipping", version, (existing or {}).get("status"))
        return existing or {"version": version, "status": "duplicate"}

    # Phase 2: run it.
    logger.info("Applying migration %04d: %s — %s", version, modname, description)
    try:
        stats = await module.up(db) or {}
    except Exception as exc:
        logger.exception("Migration %04d failed: %s", version, exc)
        # Shielded so a cancellation between up()-raise and the failure record
        # doesn't leave the row stuck at "in_progress".
        await asyncio.shield(db.schema_migrations.update_one(
            {"version": version},
            {"$set": {
                "status":     "failed",
                "error":      str(exc)[:500],
                "failed_at":  datetime.now(timezone.utc).isoformat(),
            }},
        ))
        raise

    # Shielded: once up() succeeds, the registry MUST reach "applied" even if
    # the surrounding task is being cancelled (server shutdown, Ctrl-C, etc.).
    # Without this, the data is migrated but the registry row stays
    # "in_progress" forever and the next run thinks a peer is still working.
    await asyncio.shield(db.schema_migrations.update_one(
        {"version": version},
        {"$set": {
            "status":     "applied",
            "stats":      stats,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        }},
    ))
    logger.info("Migration %04d applied: %s", version, stats)
    return {"version": version, "status": "applied", "stats": stats}


# ── public API ──────────────────────────────────────────────────────────────

async def run_pending(db, *, dry_run: bool = False, stop_on_failure: bool = True) -> list[dict]:
    """Apply every migration that's not yet in terminal "applied" state.

    On failure (or partial "in_progress" lingering from a crashed prior run),
    halts unless stop_on_failure=False. Returns one record per migration touched.
    """
    discovered = discover()
    applied = await applied_versions(db)
    results: list[dict] = []

    for version, modname in discovered:
        existing = applied.get(version)
        if existing and existing.get("status") == "applied":
            continue   # done
        if existing and existing.get("status") == "in_progress":
            # Either a peer is running it right now, or a prior run crashed mid-way.
            # Idempotent migrations are safe to retry; we let _apply_one's
            # DuplicateKey behavior gate the retry. Caller can clear the
            # in_progress row manually if it's truly stuck.
            logger.warning(
                "Migration %04d is in_progress (started %s) — peer may still be applying it",
                version, existing.get("started_at"),
            )
            results.append({"version": version, "status": "skipped_in_progress"})
            continue

        if dry_run:
            results.append({"version": version, "name": modname, "status": "would_apply"})
            continue

        try:
            result = await _apply_one(db, version, modname)
            results.append(result)
        except Exception as exc:
            results.append({"version": version, "status": "failed", "error": str(exc)})
            if stop_on_failure:
                break

    return results


async def retry(db, version: int) -> dict:
    """Clear a stuck or failed migration record and re-run it.

    Safe because every migration is required to be idempotent. Use after a
    cancellation left a row stuck at "in_progress", or after fixing whatever
    caused a "failed" record.
    """
    existing = await db.schema_migrations.find_one({"version": version}, {"_id": 0})
    if not existing:
        raise SystemExit(f"No schema_migrations row for version {version:04d}")
    if existing.get("status") == "applied":
        raise SystemExit(
            f"Migration {version:04d} is already 'applied'. "
            f"If you really want to re-run, delete the row manually first."
        )

    await db.schema_migrations.delete_one({"version": version})
    logger.info("Cleared schema_migrations row for version %04d (was %s) — re-running",
                version, existing.get("status"))

    discovered = dict(discover())
    if version not in discovered:
        raise SystemExit(f"No migration file matches version {version:04d}")
    return await _apply_one(db, version, discovered[version])


async def mark_applied(db, version: int) -> dict:
    """Force a stuck migration row to 'applied' status WITHOUT re-running.

    Use only when you've manually verified the data side is correct (e.g.,
    `crawler.diagnose` shows the migration's effects are in place). This is
    the "I know what I'm doing" escape hatch.
    """
    existing = await db.schema_migrations.find_one({"version": version}, {"_id": 0})
    if not existing:
        raise SystemExit(f"No schema_migrations row for version {version:04d}")
    if existing.get("status") == "applied":
        return existing

    await db.schema_migrations.update_one(
        {"version": version},
        {"$set": {
            "status":     "applied",
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "note":       f"manually marked applied (was {existing.get('status')!r})",
        }},
    )
    logger.warning("Migration %04d force-marked applied (was %s)", version, existing.get("status"))
    return await db.schema_migrations.find_one({"version": version}, {"_id": 0})


async def status(db) -> list[dict]:
    """Returns [{version, name, status, applied_at?, ...}, ...] for all known
    migrations — both applied (from DB) and not-yet-applied (from disk)."""
    discovered = discover()
    applied = await applied_versions(db)

    out: list[dict] = []
    for version, modname in discovered:
        rec = applied.get(version)
        if rec:
            out.append({**rec, "name": modname})
        else:
            out.append({"version": version, "name": modname, "status": "pending"})

    # Surface DB rows that have no corresponding file (e.g. someone deleted a migration).
    for version, rec in applied.items():
        if not any(v == version for v, _ in discovered):
            out.append({**rec, "status": rec.get("status", "applied"), "orphan": True})

    return sorted(out, key=lambda r: r["version"])


# ── CLI ─────────────────────────────────────────────────────────────────────

async def _cli_main(args: argparse.Namespace) -> int:
    from database import get_database
    db = await get_database()

    if args.cmd == "list":
        rows = await status(db)
        for r in rows:
            applied_at = r.get("applied_at") or "-"
            print(f"  {r['version']:04d}  {r['status']:18s}  {applied_at}  {r['name']}")
        return 0

    if args.cmd == "run":
        results = await run_pending(db, dry_run=args.dry_run)
        for r in results:
            print(f"  {r.get('version'):04d}  {r['status']}  {r.get('stats') or r.get('error') or ''}")
        if any(r["status"] == "failed" for r in results):
            return 1
        return 0

    if args.cmd == "retry":
        result = await retry(db, args.version)
        print(f"  {result.get('version'):04d}  {result['status']}  {result.get('stats') or ''}")
        return 0 if result.get("status") == "applied" else 1

    if args.cmd == "mark-applied":
        result = await mark_applied(db, args.version)
        print(f"  {result.get('version'):04d}  {result['status']}")
        return 0

    raise SystemExit(f"Unknown command: {args.cmd}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="migrations", description=__doc__)
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="cmd")

    pr = sub.add_parser("run", help="Apply pending migrations (default)")
    pr.add_argument("--dry-run", action="store_true")

    sub.add_parser("list", help="Show status of all migrations")

    prt = sub.add_parser("retry", help="Clear a stuck/failed record and re-run the migration")
    prt.add_argument("--version", type=int, required=True)

    pma = sub.add_parser("mark-applied", help="Force a stuck row to 'applied' without re-running (use carefully)")
    pma.add_argument("--version", type=int, required=True)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    # Default to "run" if no subcommand given.
    if not args.cmd:
        args.cmd = "run"
        args.dry_run = False
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return asyncio.run(_cli_main(args))


if __name__ == "__main__":
    sys.exit(main())
