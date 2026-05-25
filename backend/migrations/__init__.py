"""Versioned schema/data migrations.

Each migration is a numbered file `NNNN_descriptive_name.py` exporting:
  VERSION:     int  — must match the filename prefix
  DESCRIPTION: str
  async def up(db) -> dict   — performs the migration; returns stats

The runner records applied migrations in the `schema_migrations` collection
using a unique index on `version`, which doubles as a multi-replica lock:
whichever replica wins the insert owns the migration; others see a
duplicate-key error and move on.

`run_pending(db)` is called from the FastAPI lifespan startup in server.py
so migrations apply automatically on every deploy before the app accepts
traffic. The same code is reachable via:

    python -m migrations.runner [--dry-run] [--list]

for manual control.
"""
import os
import sys

# The repo runs with `backend/` on sys.path (no top-level `backend` package).
# Make sure `from database import ...` works regardless of invocation path.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
