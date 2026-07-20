"""
Tests for GET /api/chat-sessions (SEV-5).

Covers:
- Schema validation: all required fields present with correct types
- `since` filter: only sessions closed after the given timestamp are returned
- `limit` parameter: capped number of results
- Empty result: returns [] not 404 when no sessions match
- Auth guard: 401 without token

These are integration tests that run against a live backend.  Set
REACT_APP_BACKEND_URL to target a staging instance (default: localhost:8001).
"""

import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
SUPER_ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@sarthak.ai")
SUPER_ADMIN_PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD", "Admin@2025")


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_headers():
    resp = requests.post(
        f"{BASE_URL}/api/auth/super-admin/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        timeout=10,
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestChatSessionsEndpoint:

    def test_returns_array(self, auth_headers):
        """GET /api/chat-sessions must return a JSON array."""
        resp = requests.get(f"{BASE_URL}/api/chat-sessions", headers=auth_headers, timeout=10)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_empty_array_not_404(self, auth_headers):
        """When no closed sessions exist the response is [] not 404."""
        # Use a `since` far in the future to guarantee zero results.
        future = (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            headers=auth_headers,
            params={"since": future},
            timeout=10,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_schema_fields(self, auth_headers):
        """Each record must carry all required SDR schema fields."""
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            headers=auth_headers,
            params={"limit": 1},
            timeout=10,
        )
        assert resp.status_code == 200
        records = resp.json()
        if not records:
            pytest.skip("No closed sessions in DB — schema check skipped")

        record = records[0]
        required_fields = [
            "session_id",
            "created_at",
            "closed_at",
            "visitor_type",
            "visitor_name",
            "visitor_email",
            "org_name",
            "org_domain",
            "query_count",
            "messages",
            "intent_tags",
            "sentiment_score",
            "escalation_requested",
            "product_areas_mentioned",
        ]
        for field in required_fields:
            assert field in record, f"Missing field: {field}"

        assert isinstance(record["query_count"], int)
        assert isinstance(record["messages"], list)
        assert isinstance(record["intent_tags"], list)
        assert isinstance(record["product_areas_mentioned"], list)
        assert isinstance(record["escalation_requested"], bool)
        assert isinstance(record["sentiment_score"], (int, float))
        assert -1.0 <= record["sentiment_score"] <= 1.0

    def test_messages_schema(self, auth_headers):
        """Messages must have role, text, and timestamp fields."""
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            headers=auth_headers,
            params={"limit": 5},
            timeout=10,
        )
        assert resp.status_code == 200
        for record in resp.json():
            for msg in record.get("messages", []):
                assert "role" in msg
                assert "text" in msg
                assert "timestamp" in msg
                assert msg["role"] in ("visitor", "bot")

    def test_since_filter(self, auth_headers):
        """Records returned must all have closed_at after the `since` timestamp."""
        anchor = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            headers=auth_headers,
            params={"since": anchor, "limit": 50},
            timeout=10,
        )
        assert resp.status_code == 200
        for record in resp.json():
            closed_at = record.get("closed_at")
            if closed_at:
                record_ts = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                anchor_ts = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
                assert record_ts > anchor_ts, (
                    f"session {record['session_id']} has closed_at {closed_at} "
                    f"which is not after since={anchor}"
                )

    def test_limit_parameter(self, auth_headers):
        """Response must not exceed the requested limit."""
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            headers=auth_headers,
            params={"limit": 2},
            timeout=10,
        )
        assert resp.status_code == 200
        assert len(resp.json()) <= 2

    def test_invalid_since_returns_422(self, auth_headers):
        """A non-ISO-8601 `since` value must return 422."""
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            headers=auth_headers,
            params={"since": "not-a-date"},
            timeout=10,
        )
        assert resp.status_code == 422

    def test_unauthenticated_returns_401(self):
        """Requests without a bearer token must be rejected with 401."""
        resp = requests.get(f"{BASE_URL}/api/chat-sessions", timeout=10)
        assert resp.status_code == 401
