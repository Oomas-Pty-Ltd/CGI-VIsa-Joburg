"""
GET /api/chat-sessions — SDR transcript feed endpoint (SEV-5).

Returns closed chat sessions in the canonical schema defined by the AI CSM
(SEV-4).  The SDR polls this endpoint hourly and uses `since` to avoid
reprocessing records it has already scored.

Authentication: any valid JWT (super_admin, local_admin, viewer).  Local
admins and viewers are automatically scoped to their own tenant by
`enforce_tenant_scope`.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth_utils import verify_admin, enforce_tenant_scope
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat-sessions", tags=["chat-sessions"])


# ── Response models ──────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str          # "visitor" | "bot"
    text: str
    timestamp: str     # ISO-8601


class ChatSessionRecord(BaseModel):
    session_id: str
    created_at: str
    closed_at: Optional[str]
    visitor_type: Optional[str]    # "business" | "individual" | null
    visitor_name: Optional[str]
    visitor_email: Optional[str]
    org_name: Optional[str]
    org_domain: Optional[str]
    query_count: int
    messages: List[ChatMessage]
    intent_tags: List[str]
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    escalation_requested: bool
    product_areas_mentioned: List[str]


# ── Helpers ──────────────────────────────────────────────────────────────────

_ROLE_MAP = {"user": "visitor", "assistant": "bot"}


def _map_session(doc: dict) -> ChatSessionRecord:
    """Convert a raw MongoDB chat_sessions document to the SDR feed schema."""
    meta = doc.get("metadata") or {}

    # closed_at: set when is_active is False, using last_activity as proxy.
    # If the session is still active we skip it (caller filters is_active=False).
    closed_at = None
    if not doc.get("is_active", True):
        closed_at = doc.get("last_activity") or doc.get("closed_at")

    # Messages: convert internal role names to SDR schema names.
    raw_messages = doc.get("messages") or []
    messages = []
    for m in raw_messages:
        role_raw = m.get("role", "")
        messages.append(ChatMessage(
            role=_ROLE_MAP.get(role_raw, role_raw),
            text=m.get("content") or m.get("text") or "",
            timestamp=m.get("timestamp") or doc.get("created_at") or "",
        ))

    # Visitor metadata: prefer dedicated fields, fall back to meta sub-doc.
    visitor_name = (
        doc.get("visitor_name")
        or meta.get("visitor_name")
        or doc.get("user_name")
        or None
    )
    visitor_email = (
        doc.get("visitor_email")
        or meta.get("visitor_email")
        or doc.get("user_email")
        or None
    )
    org_name = doc.get("org_name") or meta.get("org_name") or None
    org_domain = doc.get("org_domain") or meta.get("org_domain") or None
    visitor_type = doc.get("visitor_type") or meta.get("visitor_type") or None

    return ChatSessionRecord(
        session_id=doc.get("id") or doc.get("session_id") or "",
        created_at=doc.get("created_at") or "",
        closed_at=closed_at,
        visitor_type=visitor_type,
        visitor_name=visitor_name,
        visitor_email=visitor_email,
        org_name=org_name,
        org_domain=org_domain,
        query_count=len([m for m in raw_messages if m.get("role") == "user"]),
        messages=messages,
        intent_tags=doc.get("intent_tags") or [],
        sentiment_score=float(doc.get("sentiment_score") or 0.0),
        escalation_requested=bool(doc.get("escalation_requested") or False),
        product_areas_mentioned=doc.get("product_areas_mentioned") or [],
    )


# ── Route ────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ChatSessionRecord])
async def list_chat_sessions(
    request: Request,
    since: Optional[str] = Query(
        None,
        description="ISO-8601 timestamp — return only sessions closed after this time",
    ),
    limit: int = Query(100, ge=1, le=1000, description="Max records per response"),
    company_id: Optional[str] = Query(None),
    payload: dict = Depends(verify_admin),
):
    """Return closed chat sessions for the SDR transcript feed.

    * ``since`` filters on ``last_activity`` (proxy for ``closed_at``) to
      let the SDR avoid reprocessing.
    * Local admins / viewers are automatically scoped to their own tenant.
    * Returns ``[]`` (not 404) when no sessions match.
    """
    company_id = enforce_tenant_scope(payload, company_id)

    db = await get_database()

    query: dict = {"is_active": False}
    if company_id:
        query["company_id"] = company_id

    if since:
        try:
            # Validate the timestamp is parseable (raises ValueError if not)
            datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="`since` must be a valid ISO-8601 timestamp",
            )
        # Filter on last_activity (the de-facto closed_at proxy)
        query["last_activity"] = {"$gt": since}

    cursor = (
        db.chat_sessions.find(query, {"_id": 0})
        .sort("last_activity", 1)  # oldest-first so SDR can checkpoint incrementally
        .limit(limit)
    )
    docs = await cursor.to_list(limit)

    return [_map_session(d) for d in docs]
