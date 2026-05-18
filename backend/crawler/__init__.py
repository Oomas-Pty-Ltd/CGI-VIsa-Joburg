"""Per-tenant recursive web crawler.

Runs as a standalone process (cron / K8s CronJob), writes into the shared
MongoDB instance using the same `database.py` connection as the API.

Entry point: `python -m crawler.main run --company-id <UUID>`
"""
import os
import sys

# The repo runs with `backend/` on sys.path (no top-level `backend` package),
# so the crawler package needs to add it before any module here does
# `from database import ...` or `from services... import ...`.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
