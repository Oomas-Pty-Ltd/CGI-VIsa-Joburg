"""Per-page crawl record store: raw HTML, extracted content, processing
artifacts, logs, and status — one `crawler_pages` row per (company_id,
run_id, url).

This is the durable, inspectable record behind the admin "per-page results"
view. It is separate from `knowledge_base` (the retrieval store, written by
`upsert.py`): knowledge_base holds the deduped, content-hash-gated answer
used at query time, while crawler_pages holds the full per-run forensic
record — including failures and skips — so an operator can see exactly what
happened to every URL in a run.

Raw HTML and extracted text are capped so a large run can't bloat the
collection; the caps are generous enough to be useful for inspection.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_database

from .processing import process_text

logger = logging.getLogger("crawler.pages")

# Storage caps (bytes/chars). Raw HTML is the biggest; keep a generous slice
# for inspection without storing whole megabyte pages.
_RAW_HTML_CAP = 200_000
_TEXT_CAP = 20_000
# Cap stored chunks so a pathological page can't blow the doc up; chunk_count
# still reflects the true total.
_STORED_CHUNKS = 20

STATUS_PROCESSED = "processed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cap_str(s: Optional[str], n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n]


async def _store(doc: Dict[str, Any]) -> None:
    db = await get_database()
    # Idempotent per (company, run, url_hash): a re-claimed URL in the same run
    # overwrites its prior row rather than duplicating.
    await db.crawler_pages.update_one(
        {"company_id": doc["company_id"], "run_id": doc["run_id"], "url_hash": doc["url_hash"]},
        {"$set": doc, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now_iso()}},
        upsert=True,
    )


async def record_processed(
    *,
    company_id: str,
    run_id: str,
    url: str,
    url_hash: str,
    parent_url: Optional[str],
    depth: int,
    attempts: int,
    http_status: int,
    raw_html: str,
    title: str,
    extracted_text: str,
    language: str,
    category: str,
) -> Dict[str, Any]:
    """Run the processing pipeline and persist the full page record. Returns a
    small summary used by the runner's counters."""
    log: List[str] = [f"fetched HTTP {http_status}, {len(raw_html or '')} bytes of HTML"]
    result = process_text(extracted_text, title=title)
    log.extend(result.log)

    doc = {
        "company_id":       company_id,
        "run_id":           run_id,
        "url":              url,
        "url_hash":         url_hash,
        "parent_url":       parent_url,
        "depth":            depth,
        "attempts":         attempts,
        "status":           STATUS_PROCESSED,
        "http_status":      http_status,
        "error":            None,
        "skip_reason":      None,
        "title":            title,
        "language":         language,
        "category":         category,
        "raw_html":         _cap_str(raw_html, _RAW_HTML_CAP),
        "raw_html_bytes":   len(raw_html or ""),
        "extracted_text":   _cap_str(extracted_text, _TEXT_CAP),
        "extracted_length": len(extracted_text or ""),
        "processing": {
            "status":          "done",
            "chunk_count":     result.chunk_count,
            "chunks":          result.chunks[:_STORED_CHUNKS],
            "summary":         result.summary,
            "keywords":        result.keywords,
            "embedding_dim":   result.embedding_dim,
            "embedding_preview": result.embedding[:8],
            "log":             log,
        },
        "fetched_at":       _now_iso(),
        "processed_at":     _now_iso(),
        "updated_at":       _now_iso(),
    }
    await _store(doc)
    # Return the full artifacts so the runner can sync them onto the KB row.
    return {
        "chunk_count":   result.chunk_count,
        "keywords":      result.keywords,
        "summary":       result.summary,
        "embedding":     result.embedding,
        "embedding_dim": result.embedding_dim,
    }


async def record_unchanged(
    *,
    company_id: str,
    run_id: str,
    url: str,
    url_hash: str,
    parent_url: Optional[str],
    depth: int,
    attempts: int,
    http_status: int,
) -> None:
    """Record that a page was fetched this run but its content was unchanged,
    so reprocessing was skipped. Keeps the per-run page list complete (the
    operator sees the URL was seen) without re-running the pipeline — this is
    the incremental ("changed pages only") path."""
    doc = {
        "company_id":       company_id,
        "run_id":           run_id,
        "url":              url,
        "url_hash":         url_hash,
        "parent_url":       parent_url,
        "depth":            depth,
        "attempts":         attempts,
        "status":           "unchanged",
        "http_status":      http_status,
        "error":            None,
        "skip_reason":      None,
        "title":            "",
        "raw_html":         "",
        "raw_html_bytes":   0,
        "extracted_text":   "",
        "extracted_length": 0,
        "processing": {
            "status": "skipped_unchanged",
            "chunk_count": 0, "chunks": [], "summary": "", "keywords": [],
            "embedding_dim": 0, "embedding_preview": [],
            "log": ["content hash unchanged since last crawl — reprocessing skipped"],
        },
        "fetched_at":   _now_iso(),
        "processed_at": None,
        "updated_at":   _now_iso(),
    }
    await _store(doc)


async def record_failed(
    *,
    company_id: str,
    run_id: str,
    url: str,
    url_hash: str,
    parent_url: Optional[str],
    depth: int,
    attempts: int,
    http_status: Optional[int],
    error: str,
) -> None:
    """Persist a failed page (fetch/parse error) with its log + status."""
    doc = {
        "company_id":       company_id,
        "run_id":           run_id,
        "url":              url,
        "url_hash":         url_hash,
        "parent_url":       parent_url,
        "depth":            depth,
        "attempts":         attempts,
        "status":           STATUS_FAILED,
        "http_status":      http_status,
        "error":            error[:500],
        "skip_reason":      None,
        "title":            "",
        "raw_html":         "",
        "raw_html_bytes":   0,
        "extracted_text":   "",
        "extracted_length": 0,
        "processing": {
            "status": "skipped",
            "chunk_count": 0,
            "chunks": [],
            "summary": "",
            "keywords": [],
            "embedding_dim": 0,
            "embedding_preview": [],
            "log": [f"fetch/parse failed: {error[:200]} — processing not run"],
        },
        "fetched_at":   _now_iso(),
        "processed_at": None,
        "updated_at":   _now_iso(),
    }
    await _store(doc)


async def record_skipped(
    *,
    company_id: str,
    run_id: str,
    url: str,
    url_hash: str,
    parent_url: Optional[str],
    depth: int,
    attempts: int,
    reason: str,
) -> None:
    """Persist a policy-skipped page (robots / non-HTML) with its reason."""
    doc = {
        "company_id":       company_id,
        "run_id":           run_id,
        "url":              url,
        "url_hash":         url_hash,
        "parent_url":       parent_url,
        "depth":            depth,
        "attempts":         attempts,
        "status":           STATUS_SKIPPED,
        "http_status":      None,
        "error":            None,
        "skip_reason":      reason,
        "title":            "",
        "raw_html":         "",
        "raw_html_bytes":   0,
        "extracted_text":   "",
        "extracted_length": 0,
        "processing": {
            "status": "skipped",
            "chunk_count": 0, "chunks": [], "summary": "", "keywords": [],
            "embedding_dim": 0, "embedding_preview": [],
            "log": [f"skipped: {reason} — processing not run"],
        },
        "fetched_at":   _now_iso(),
        "processed_at": None,
        "updated_at":   _now_iso(),
    }
    await _store(doc)
