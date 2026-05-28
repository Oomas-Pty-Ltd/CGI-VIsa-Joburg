"""Unit tests for the tenant-scoped response cache (``services.response_cache``).

Offline only — exercises normalization, key isolation, and the master enable
flag. get()/put() against Mongo are covered by the live smoke test, not here;
these assert the safety-critical pure logic: keys never cross tenants/langs,
and the cache is a hard no-op when disabled.
"""
from __future__ import annotations

import importlib


def _fresh(monkeypatch, enabled):
    monkeypatch.setenv("RESPONSE_CACHE_ENABLED", "true" if enabled else "false")
    import services.response_cache as rc
    return importlib.reload(rc)


def test_normalize_collapses_case_punctuation_and_space():
    import services.response_cache as rc
    assert rc._normalize("  What  are the OFFICE hours??? ") == "what are the office hours"
    assert rc._normalize("Visa-fee!") == "visa fee"


def test_key_is_deterministic_and_isolated_by_tenant_and_lang():
    import services.response_cache as rc
    k = rc._key("tenantA", "en", "office hours")
    assert k == rc._key("tenantA", "en", "  Office   Hours ")          # normalization
    assert k != rc._key("tenantB", "en", "office hours")               # tenant isolation
    assert k != rc._key("tenantA", "hi", "office hours")               # language isolation
    assert k != rc._key("tenantA", "en", "visa fees")                  # different question


def test_enabled_reads_env(monkeypatch):
    rc = _fresh(monkeypatch, enabled=False)
    assert rc.enabled() is False
    rc = _fresh(monkeypatch, enabled=True)
    assert rc.enabled() is True


async def _get_put_noop_when_disabled():
    import services.response_cache as rc
    # With the cache disabled these must return without any DB access.
    assert await rc.get("t", "en", "q") is None
    await rc.put("t", "en", "q", "answer")  # must not raise


def test_get_put_are_noops_when_disabled(monkeypatch):
    import asyncio
    _fresh(monkeypatch, enabled=False)
    asyncio.run(_get_put_noop_when_disabled())
