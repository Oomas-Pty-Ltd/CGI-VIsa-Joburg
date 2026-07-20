"""
====================================================================
CHAT SESSIONS API ROUTES — SDR / CSM transcript feed
====================================================================
GET /api/chat-sessions

Returns a paginated, filterable list of visitor chat sessions in
the canonical schema expected by the SDR lead-scoring pipeline
and CSM sentiment feed (SEV-5 / SEV-3).

Auth:  same JWT-based admin auth used across the rest of the API
       (verify_admin — accepts super_admin, local_admin, viewer).
       Local admins and viewers are automatically scoped to their
       own tenant via enforce_tenant_scope.
====================================================================
"""

import re
import logging
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from auth_utils import verify_admin, enforce_tenant_scope
from database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat-sessions", tags=["chat-sessions"])

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str          # "visitor" | "bot"
    text: str
    timestamp: Optional[str] = None


class ChatSessionRecord(BaseModel):
    session_id: str
    created_at: Optional[str] = None
    closed_at: Optional[str] = None
    visitor_type: str              # "business" | "individual"
    visitor_name: Optional[str] = None
    visitor_email: Optional[str] = None
    org_name: Optional[str] = None
    org_domain: Optional[str] = None
    query_count: int
    messages: List[ChatMessage]
    intent_tags: List[str]
    sentiment_score: float
    escalation_requested: bool
    product_areas_mentioned: List[str]


# ---------------------------------------------------------------------------
# Keyword lists for lightweight classification
# ---------------------------------------------------------------------------

_BUSINESS_KEYWORDS = [
    "company", "organisation", "organization", "business", "corporate",
    "firm", "enterprise", "corp", "ltd", "pty", "inc", "llc", "ngo",
    "employer", "employee", "staff", "workforce", "hr",
]

_PRODUCT_AREA_PATTERNS = {
    "passport": ["passport"],
    "visa": ["visa"],
    "oci": ["oci", "overseas citizen"],
    "pcc": ["pcc", "police clearance"],
    "emergency_certificate": ["emergency", "death certificate", "emergency certificate"],
    "surrender_citizenship": ["surrender", "renounce", "renunciation"],
    "attestation": ["attest"],
    "birth_registration": ["birth registration", "birth certificate"],
    "miscellaneous": ["misc", "miscellaneous", "other service"],
}

_ESCALATION_KEYWORDS = ["speak to human", "escalat", "manager", "supervisor", "urgent help"]

_NEGATIVE_SENTIMENT_WORDS = [
    "frustrated", "angry", "terrible", "horrible", "awful", "unhappy",
    "disappointed", "useless", "bad", "wrong", "broken", "fail", "error",
    "can't", "cannot", "won't", "doesn't work", "not working",
]

_POSITIVE_SENTIMENT_WORDS = [
    "thank", "thanks", "great", "excellent", "perfect", "helpful",
    "appreciate", "good", "wonderful", "happy", "satisfied",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_domain(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return None
    domain = email.split("@", 1)[1].lower().strip()
    # Exclude common free providers — only retain company-looking domains
    _free_providers = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"}
    return None if domain in _free_providers else domain


def _classify_visitor_type(messages: list, form_data: dict, email: Optional[str]) -> str:
    combined = " ".join(
        m.get("content", "") for m in messages if m.get("role") == "user"
    ).lower()
    combined += " " + " ".join(str(v) for v in (form_data or {}).values()).lower()
    if any(kw in combined for kw in _BUSINESS_KEYWORDS):
        return "business"
    domain = _extract_domain(email)
    if domain:
        return "business"
    return "individual"


def _extract_intent_tags(messages: list, step: Optional[str]) -> List[str]:
    combined = " ".join(
        m.get("content", "") for m in messages
    ).lower()
    tags = set()
    for tag, patterns in _PRODUCT_AREA_PATTERNS.items():
        if any(p in combined for p in patterns):
            tags.add(tag)
    if step and step not in ("", "register"):
        tags.add(step)
    return sorted(tags)


def _extract_product_areas(messages: list) -> List[str]:
    combined = " ".join(
        m.get("content", "") for m in messages
    ).lower()
    areas = []
    for area, patterns in _PRODUCT_AREA_PATTERNS.items():
        if any(p in combined for p in patterns):
            areas.append(area)
    return sorted(areas)


def _compute_sentiment(messages: list) -> float:
    user_text = " ".join(
        m.get("content", "") for m in messages if m.get("role") == "user"
    ).lower()
    neg = sum(1 for w in _NEGATIVE_SENTIMENT_WORDS if w in user_text)
    pos = sum(1 for w in _POSITIVE_SENTIMENT_WORDS if w in user_text)
    total = neg + pos
    if total == 0:
        return 0.1  # slight positive default
    return round(min(1.0, max(-1.0, (pos - neg) / total)), 2)


def _check_escalation(messages: list) -> bool:
    user_text = " ".join(
        m.get("content", "") for m in messages if m.get("role") == "user"
    ).lower()
    return any(kw in user_text for kw in _ESCALATION_KEYWORDS)


def _map_session(doc: dict) -> ChatSessionRecord:
    msgs_raw = doc.get("messages", [])
    form_data = doc.get("form_data") or {}

    email = form_data.get("email") or doc.get("user_email")
    name = form_data.get("full_name") or form_data.get("name") or doc.get("user_name")

    messages = [
        ChatMessage(
            role="visitor" if m.get("role") == "user" else "bot",
            text=m.get("content", ""),
            timestamp=m.get("timestamp"),
        )
        for m in msgs_raw
    ]

    query_count = sum(1 for m in msgs_raw if m.get("role") == "user")

    return ChatSessionRecord(
        session_id=doc.get("id", ""),
        created_at=doc.get("created_at"),
        closed_at=doc.get("submitted_at") or doc.get("closed_at"),
        visitor_type=_classify_visitor_type(msgs_raw, form_data, email),
        visitor_name=name,
        visitor_email=email,
        org_name=form_data.get("org_name") or form_data.get("company"),
        org_domain=_extract_domain(email),
        query_count=query_count,
        messages=messages,
        intent_tags=_extract_intent_tags(msgs_raw, doc.get("step")),
        sentiment_score=_compute_sentiment(msgs_raw),
        escalation_requested=_check_escalation(msgs_raw),
        product_areas_mentioned=_extract_product_areas(msgs_raw),
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("", response_model=List[ChatSessionRecord])
async def list_chat_sessions(
    request: Request,
    company_id: Optional[str] = None,
    since: Optional[str] = Query(
        None,
        description="ISO-8601 timestamp; return only sessions created after this value",
    ),
    limit: int = Query(100, ge=1, le=500, description="Max records per response"),
    payload: dict = Depends(verify_admin),
):
    """Return visitor chat sessions for SDR lead scoring and CSM sentiment monitoring.

    Supports optional `since` (ISO-8601) and `limit` parameters.
    Always returns a JSON array — empty `[]` when no sessions match.
    Local admins and viewer tokens are automatically scoped to their tenant.
    """
    company_id = enforce_tenant_scope(payload, company_id)
    db = await get_database()

    query: dict = {}
    if company_id:
        query["company_id"] = company_id
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            query["created_at"] = {"$gt": since_dt}
        except ValueError:
            raise HTTPException(status_code=422, detail="`since` must be a valid ISO-8601 timestamp")

    raw = await (
        db.chat_sessions.find(query, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )

    return [_map_session(doc) for doc in raw]
