"""Tests for per-tenant WABA credentials.

- ``security.crypto``: secret never persisted without a key; roundtrip; graceful
  decrypt failure.
- ``ICSWABAService._resolve_creds``: per-tenant credentials from the channel map
  are used when present, else the env-global account — but the send always goes
  out *as* the number the message was received on.

Offline: the resolver is monkeypatched (no DB). The full Mongo roundtrip +
session-scoping are covered by the live smoke test, not here.
"""
from __future__ import annotations

import asyncio

import pytest

import security.crypto as crypto
import services.ics_waba_service as svc
import services.messaging_channel_resolver as resolver


# ── crypto ───────────────────────────────────────────────────────────────────
def test_encrypt_requires_key(monkeypatch):
    monkeypatch.delenv("CHANNEL_CRED_KEY", raising=False)
    assert crypto.is_configured() is False
    with pytest.raises(RuntimeError):
        crypto.encrypt_secret("topsecret")          # must never persist plaintext
    assert crypto.decrypt_secret("anything") is None  # graceful without a key


def test_crypto_roundtrip(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("CHANNEL_CRED_KEY", Fernet.generate_key().decode())
    token = crypto.encrypt_secret("hunter2")
    assert token != "hunter2"
    assert crypto.decrypt_secret(token) == "hunter2"


def test_decrypt_invalid_or_empty_returns_none(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("CHANNEL_CRED_KEY", Fernet.generate_key().decode())
    assert crypto.decrypt_secret("not-a-valid-token") is None
    assert crypto.decrypt_secret(None) is None
    assert crypto.decrypt_secret("") is None


# ── service credential selection ───────────────────────────────────────────────
def _service():
    s = svc.ICSWABAService()
    s.user, s.pw, s.from_ = "envuser", "envpass", "27ENV"
    return s


def test_env_fallback_when_no_per_tenant_creds(monkeypatch):
    async def _none(channel_type, external_id):
        return None
    monkeypatch.setattr(resolver, "resolve_channel_credentials", _none)
    s = _service()
    user, pw, sender = asyncio.run(s._resolve_creds("27TENANTNUM"))
    assert (user, pw) == ("envuser", "envpass")   # env account
    assert sender == "27TENANTNUM"                # but sends AS the received number


def test_per_tenant_creds_used_when_configured(monkeypatch):
    async def _creds(channel_type, external_id):
        return {"user": "tenantuser", "pass": "tenantpass", "from": external_id}
    monkeypatch.setattr(resolver, "resolve_channel_credentials", _creds)
    s = _service()
    user, pw, sender = asyncio.run(s._resolve_creds("27TENANTNUM"))
    assert (user, pw, sender) == ("tenantuser", "tenantpass", "27TENANTNUM")


def test_empty_from_falls_back_to_env_from(monkeypatch):
    async def _none(channel_type, external_id):
        return None
    monkeypatch.setattr(resolver, "resolve_channel_credentials", _none)
    s = _service()
    user, pw, sender = asyncio.run(s._resolve_creds(""))
    assert (user, pw, sender) == ("envuser", "envpass", "27ENV")
