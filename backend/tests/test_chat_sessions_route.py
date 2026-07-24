"""
Tests for GET /api/chat-sessions (SEV-5).

Covers:
- Schema correctness (all required fields present, correct types)
- Empty-array response when no sessions exist (not 404)
- `since` filter correctly excludes older sessions
- Unauthenticated requests are rejected (401)
- `limit` parameter is respected
"""

import pytest
import requests
import os
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
SUPER_ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@sarthak.ai")
SUPER_ADMIN_PASSWORD = os.environ["SUPER_ADMIN_PASSWORD"]


@pytest.fixture(scope="module")
def admin_token():
    resp = requests.post(
        f"{BASE_URL}/api/auth/super-admin/login",
        json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD},
        timeout=10,
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


class TestChatSessionsEndpoint:
    def test_returns_200_and_array(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/chat-sessions", headers=auth_headers, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_empty_array_not_404_when_no_results(self, auth_headers):
        # Use a future `since` so no sessions match
        future = (datetime.now(timezone.utc) + timedelta(days=365 * 10)).isoformat()
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            params={"since": future},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_schema_fields_present(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            params={"limit": 1},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        sessions = resp.json()
        if not sessions:
            pytest.skip("No sessions in DB; schema check skipped")

        s = sessions[0]
        required_fields = [
            "session_id", "created_at", "closed_at", "visitor_type",
            "visitor_name", "visitor_email", "org_name", "org_domain",
            "query_count", "messages", "intent_tags", "sentiment_score",
            "escalation_requested", "product_areas_mentioned",
        ]
        for field in required_fields:
            assert field in s, f"Missing field: {field}"

        assert s["visitor_type"] in ("business", "individual")
        assert isinstance(s["query_count"], int)
        assert isinstance(s["messages"], list)
        assert isinstance(s["intent_tags"], list)
        assert isinstance(s["sentiment_score"], float)
        assert isinstance(s["escalation_requested"], bool)
        assert isinstance(s["product_areas_mentioned"], list)

        if s["messages"]:
            msg = s["messages"][0]
            assert "role" in msg
            assert "text" in msg
            assert msg["role"] in ("visitor", "bot")

    def test_since_filter_excludes_old_sessions(self, auth_headers):
        # Fetch all sessions first
        all_resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            headers=auth_headers,
            timeout=10,
        )
        assert all_resp.status_code == 200
        all_sessions = all_resp.json()
        if len(all_sessions) < 2:
            pytest.skip("Need at least 2 sessions to test `since` filter")

        # Pick the created_at of the oldest session (last in desc list)
        oldest_ts = all_sessions[-1]["created_at"]
        # Request only sessions newer than the oldest
        filtered_resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            params={"since": oldest_ts},
            headers=auth_headers,
            timeout=10,
        )
        assert filtered_resp.status_code == 200
        filtered = filtered_resp.json()
        # Should have fewer than all sessions (oldest excluded)
        assert len(filtered) < len(all_sessions)
        # None of the returned sessions should have created_at <= oldest_ts
        for s in filtered:
            assert s["created_at"] > oldest_ts, (
                f"Session {s['session_id']} has created_at={s['created_at']} "
                f"which is not after since={oldest_ts}"
            )

    def test_limit_parameter_respected(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            params={"limit": 2},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 200
        assert len(resp.json()) <= 2

    def test_unauthenticated_request_rejected(self):
        resp = requests.get(f"{BASE_URL}/api/chat-sessions", timeout=10)
        assert resp.status_code in (401, 403)

    def test_invalid_since_returns_422(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/api/chat-sessions",
            params={"since": "not-a-date"},
            headers=auth_headers,
            timeout=10,
        )
        assert resp.status_code == 422
