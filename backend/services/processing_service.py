"""External processing-service invocation for application submission.

The external service is the **system of record**: an application is not
truly submitted until this call is accepted. Confirmation (status=confirmed,
PDF, email) is gated on acceptance — see ``confirm_application``. A failed
call leaves the application in ``submission_pending`` and is retried (inline
here, and via the admin "Retry" action).

Design notes:
  - **Idempotency.** Every call carries an idempotency key (the application
    reference_id) in the body and the ``Idempotency-Key`` header so retries
    never create duplicate downstream records. The mock honours it.
  - **Inline retry.** Transient failures (transport errors, timeouts, and
    retryable HTTP statuses: 429/500/502/503/504) are retried up to
    ``_MAX_ATTEMPTS`` with linear backoff. Terminal failures (other 4xx —
    a bad payload won't fix itself) are not retried.
  - The call never raises; it always returns a self-contained invocation
    record the caller persists against the application.
  - Target URL is config-driven (``PROCESSING_SERVICE_URL``).
"""

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("processing_service")

_DEFAULT_URL = "http://localhost:8000/api/seva-setu/_mock/gov-submit"

# Per-attempt ceiling so a hung downstream can't wedge the confirm request.
_TIMEOUT_SECONDS = 10.0

# Bounded inline retry. Total worst-case added latency on a confirm is
# roughly _BACKOFF_BASE * (1 + 2) ≈ 1.5s plus the per-attempt timeouts.
_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 0.5  # seconds; attempt N waits N * base before retrying

# HTTP statuses worth retrying — transient/server-side. Everything else in
# the 4xx range is a client error (bad payload, auth) that retrying won't fix.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _service_url() -> str:
    return os.environ.get("PROCESSING_SERVICE_URL", _DEFAULT_URL)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def invoke_processing_service(
    app: Dict[str, Any],
    *,
    simulate_failure: bool = False,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Submit ``app`` to the external processing service (system of record).

    Returns a self-contained invocation record (always — never raises):

        {
          "id", "endpoint", "method", "request", "idempotency_key",
          "ok", "status_code", "response", "error",
          "attempts", "retryable", "duration_ms", "invoked_at"
        }

    ``retryable`` is True when the final failure was a transient one that we
    exhausted retries on (vs a terminal client error) — surfaced so the admin
    UI can hint whether a manual retry is worth it.
    """
    url = _service_url()
    idem = idempotency_key or app.get("reference_id") or str(uuid.uuid4())
    request_body = {
        "reference_id":    app.get("reference_id"),
        "service_type":    app.get("service_type"),
        "service_name":    app.get("service_name"),
        "applicant_name":  (app.get("form_data") or {}).get("full_name"),
        "applicant_email": (app.get("form_data") or {}).get("email"),
        "document_count":  len(app.get("documents") or []),
        "company_id":      app.get("company_id"),
        "idempotency_key": idem,
        # Honoured only by the mock endpoint; a real service ignores it.
        "simulate_failure": bool(simulate_failure),
    }
    headers = {"Idempotency-Key": idem}

    record: Dict[str, Any] = {
        "id":              str(uuid.uuid4()),
        "endpoint":        url,
        "method":          "POST",
        "request":         request_body,
        "idempotency_key": idem,
        "ok":              False,
        "status_code":     None,
        "response":        None,
        "error":           None,
        "attempts":        0,
        "retryable":       False,
        "duration_ms":     None,
        "invoked_at":      _now_iso(),
    }

    start = time.monotonic()
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        record["attempts"] = attempt
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, json=request_body, headers=headers)
            record["status_code"] = resp.status_code
            try:
                record["response"] = resp.json()
            except ValueError:
                record["response"] = {"raw": resp.text[:2000]}

            if resp.is_success:
                record["ok"] = True
                record["error"] = None
                record["retryable"] = False
                break

            # HTTP error — decide whether to retry.
            if resp.status_code in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS:
                record["retryable"] = True
                record["error"] = f"HTTP {resp.status_code} (retrying)"
                await asyncio.sleep(_BACKOFF_BASE * attempt)
                continue
            # Terminal, or retries exhausted.
            record["retryable"] = resp.status_code in _RETRYABLE_STATUS
            record["error"] = f"HTTP {resp.status_code}"
            logger.warning(
                "processing service %s returned %s for %s (attempt %d/%d)",
                url, resp.status_code, app.get("reference_id"), attempt, _MAX_ATTEMPTS,
            )
            break
        except httpx.HTTPError as exc:
            # Transport/timeout errors are transient — retry while we can.
            record["error"] = str(exc) or exc.__class__.__name__
            record["retryable"] = True
            if attempt < _MAX_ATTEMPTS:
                logger.warning(
                    "processing service %s transport error for %s (attempt %d/%d): %s",
                    url, app.get("reference_id"), attempt, _MAX_ATTEMPTS, exc,
                )
                await asyncio.sleep(_BACKOFF_BASE * attempt)
                continue
            logger.warning(
                "processing service %s call failed for %s after %d attempts: %s",
                url, app.get("reference_id"), attempt, exc,
            )
            break

    record["duration_ms"] = round((time.monotonic() - start) * 1000, 1)
    return record
