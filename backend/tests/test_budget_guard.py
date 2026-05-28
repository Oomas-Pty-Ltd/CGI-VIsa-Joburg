"""Tests for per-tenant LLM budget enforcement (``services.budget_guard``).

Why this exists: ``companies.llm_monthly_budget_usd`` used to be a dashboard
number only. The guard turns it into a real pre-flight gate. The safety-critical
properties to lock down: it's a hard no-op when disabled, an unconfigured budget
means UNLIMITED (enabling the feature must not silently block tenants), the
decision is TTL-cached (so the chat path doesn't aggregate the ledger every
request), and it fails OPEN on error (a DB hiccup must never block real users).

Offline: a tiny fake stands in for ``db.companies`` and the ledger lookup is
monkeypatched, so no Mongo / network is touched. asyncio via ``asyncio.run``
(the repo has no pytest-asyncio plugin).
"""
from __future__ import annotations

import asyncio

import services.budget_guard as bg


class _FakeCompanies:
    def __init__(self, budget):
        self._budget = budget  # None → company row absent

    async def find_one(self, *_a, **_k):
        if self._budget is None:
            return None
        return {"llm_monthly_budget_usd": self._budget}


class _FakeDB:
    def __init__(self, budget):
        self.companies = _FakeCompanies(budget)


def _wire(monkeypatch, *, enabled, budget, spent):
    """Point the guard at a fake company budget + fake MTD spend."""
    monkeypatch.setenv("BUDGET_ENFORCEMENT_ENABLED", "true" if enabled else "false")
    monkeypatch.setattr(bg, "_decision_cache", {})  # fresh cache per test
    # enabled()/knobs now read platform_config; clear its cache so the env-var
    # fallback path is exercised deterministically (no DB in offline tests).
    import services.platform_config as pc
    monkeypatch.setattr(pc, "_cache_value", None)

    async def _fake_get_db():
        return _FakeDB(budget)

    monkeypatch.setattr(bg, "get_database", _fake_get_db)

    import services.llm_usage as llm_usage

    async def _fake_mtd(company_id):
        return spent

    monkeypatch.setattr(llm_usage, "month_to_date_cost", _fake_mtd)


def test_enabled_reads_platform_config(monkeypatch):
    # A super-admin toggling the flag in the UI = a platform_config value.
    import services.platform_config as pc
    monkeypatch.setattr(pc, "get", lambda key, default=None: True if key == "budget_enforcement_enabled" else default)
    assert bg.enabled() is True
    monkeypatch.setattr(pc, "get", lambda key, default=None: False if key == "budget_enforcement_enabled" else default)
    assert bg.enabled() is False


def test_noop_when_disabled(monkeypatch):
    _wire(monkeypatch, enabled=False, budget=10.0, spent=999.0)  # wildly over
    assert asyncio.run(bg.is_over_budget("t1")) is False


def test_unlimited_when_no_budget_configured(monkeypatch):
    # Budget 0 and a missing company row both mean "no cap" → never gated,
    # even when enforcement is on and spend is high.
    _wire(monkeypatch, enabled=True, budget=0.0, spent=999.0)
    assert asyncio.run(bg.is_over_budget("t1")) is False
    _wire(monkeypatch, enabled=True, budget=None, spent=999.0)
    assert asyncio.run(bg.is_over_budget("t1")) is False


def test_under_budget_allows(monkeypatch):
    _wire(monkeypatch, enabled=True, budget=10.0, spent=4.99)
    assert asyncio.run(bg.is_over_budget("t1")) is False


def test_at_or_over_budget_gates(monkeypatch):
    _wire(monkeypatch, enabled=True, budget=10.0, spent=10.0)   # exactly at cap
    assert asyncio.run(bg.is_over_budget("t1")) is True
    _wire(monkeypatch, enabled=True, budget=10.0, spent=12.5)   # over cap
    assert asyncio.run(bg.is_over_budget("t1")) is True


def test_hard_multiplier_grace_band(monkeypatch):
    # multiplier 1.5 → block only at 15.0, so 12.0 (over cap, under grace) allows.
    monkeypatch.setenv("BUDGET_HARD_MULTIPLIER", "1.5")
    _wire(monkeypatch, enabled=True, budget=10.0, spent=12.0)
    assert asyncio.run(bg.is_over_budget("t1")) is False
    _wire(monkeypatch, enabled=True, budget=10.0, spent=15.0)
    monkeypatch.setenv("BUDGET_HARD_MULTIPLIER", "1.5")
    assert asyncio.run(bg.is_over_budget("t1")) is True


def test_decision_is_cached_then_invalidated(monkeypatch):
    _wire(monkeypatch, enabled=True, budget=10.0, spent=20.0)
    assert asyncio.run(bg.is_over_budget("t1")) is True   # computes + caches True

    # Spend "drops" below cap, but the cached True should stick within the TTL.
    import services.llm_usage as llm_usage

    async def _now_cheap(_cid):
        return 1.0

    monkeypatch.setattr(llm_usage, "month_to_date_cost", _now_cheap)
    assert asyncio.run(bg.is_over_budget("t1")) is True   # served from cache

    bg.invalidate_cache("t1")
    assert asyncio.run(bg.is_over_budget("t1")) is False  # recomputed after invalidation


def test_fails_open_on_db_error(monkeypatch):
    monkeypatch.setenv("BUDGET_ENFORCEMENT_ENABLED", "true")
    monkeypatch.setattr(bg, "_decision_cache", {})

    async def _boom():
        raise RuntimeError("mongo down")

    monkeypatch.setattr(bg, "get_database", _boom)
    assert asyncio.run(bg.is_over_budget("t1")) is False  # never block on error


def test_exceeded_message_default_and_override(monkeypatch):
    monkeypatch.delenv("BUDGET_EXCEEDED_MESSAGE", raising=False)
    assert "usage limit" in bg.exceeded_message().lower()
    monkeypatch.setenv("BUDGET_EXCEEDED_MESSAGE", "Custom cap notice")
    assert bg.exceeded_message() == "Custom cap notice"
