"""Tests for the distributed (MongoDB) rate limiter (``security.rate_limiter``).

Why this exists: the previous limiter counted in a per-process dict, so on N
workers / Cloud Run instances the *effective* limit was N x the configured
value (each instance only saw its own slice). Enforcement now runs through an
atomic ``$inc`` fixed-window counter in Mongo, which is correct no matter how
many instances share the backend.

Offline: a tiny in-memory fake stands in for the Mongo collection. It mimics
the one operation the limiter uses — ``find_one_and_update`` with ``$inc`` +
``$setOnInsert`` + ``upsert`` returning the AFTER doc. asyncio is single-
threaded here, so the fake's read-modify-write is as atomic as Mongo's is in
production — which is exactly what lets the "shared backend" test prove the
multi-instance fix.
"""
from __future__ import annotations

import asyncio
import importlib

# NB: ``security/__init__.py`` re-exports the ``rate_limiter`` *instance*, which
# shadows the submodule attribute — so ``import security.rate_limiter as rl``
# would bind the instance, not the module. Pull the real module from sys.modules.
rl = importlib.import_module("security.rate_limiter")


class _FakeColl:
    """Minimal stand-in for ``db.rate_limits`` supporting the limiter's single op."""

    def __init__(self):
        self.docs = {}

    async def find_one_and_update(self, filt, update, upsert=False,
                                  return_document=None, projection=None):
        key = filt["key"]
        doc = self.docs.get(key)
        if doc is None:
            if not upsert:
                return None
            doc = {"key": key, "count": 0}
            doc.update(update.get("$setOnInsert", {}))
            self.docs[key] = doc
        doc["count"] += update["$inc"]["count"]
        return dict(doc)


class _FakeDB:
    def __init__(self):
        self.rate_limits = _FakeColl()


def test_allows_up_to_limit_then_blocks():
    db = _FakeDB()

    async def run():
        # limit=3, 60s window. First 3 allowed, 4th over the limit.
        results = [await rl._hit_window(db, "ip_min", "1.1.1.1", 3, 60) for _ in range(4)]
        return results

    assert asyncio.run(run()) == [True, True, True, False]


def test_separate_identifiers_are_independent():
    db = _FakeDB()

    async def run():
        a = await rl._hit_window(db, "ip_min", "1.1.1.1", 1, 60)
        a2 = await rl._hit_window(db, "ip_min", "1.1.1.1", 1, 60)   # A over limit
        b = await rl._hit_window(db, "ip_min", "2.2.2.2", 1, 60)    # B fresh
        return a, a2, b

    assert asyncio.run(run()) == (True, False, True)


def test_window_resets_when_time_advances(monkeypatch):
    db = _FakeDB()
    fake_now = {"t": 1_000_000.0}
    monkeypatch.setattr(rl.time, "time", lambda: fake_now["t"])

    async def run():
        first = await rl._hit_window(db, "ip_min", "1.1.1.1", 1, 60)
        second_same_window = await rl._hit_window(db, "ip_min", "1.1.1.1", 1, 60)
        fake_now["t"] += 61  # next minute → new window key → counter resets
        third_new_window = await rl._hit_window(db, "ip_min", "1.1.1.1", 1, 60)
        return first, second_same_window, third_new_window

    assert asyncio.run(run()) == (True, False, True)


def test_shared_backend_enforces_limit_across_instances():
    # THE multi-instance fix: two "instances" share one Mongo backend, so their
    # hits accumulate into the same window counter and the COMBINED traffic is
    # capped at the configured limit — not limit-per-instance.
    db = _FakeDB()  # one shared backend

    async def run():
        limit = 4
        instance_a = [await rl._hit_window(db, "ip_min", "9.9.9.9", limit, 60) for _ in range(3)]
        instance_b = [await rl._hit_window(db, "ip_min", "9.9.9.9", limit, 60) for _ in range(3)]
        return instance_a + instance_b

    # 6 total hits, limit 4 → first 4 allowed, last 2 blocked (regardless of
    # which instance served them).
    assert asyncio.run(run()) == [True, True, True, True, False, False]


def _set_limits(monkeypatch, **overrides):
    """Point check_limits_distributed at a fixed limit set. The limiter reads
    limits from platform_config now, so we patch that module's ``get`` (the
    same object the limiter imported as ``_pcfg``)."""
    base = {
        "rate_limit_ip_per_sec": 0,
        "rate_limit_ip_per_min": 30,
        "rate_limit_ip_per_hour": 500,
        "rate_limit_burst_multiplier": 1.5,
        "rate_limit_user_per_sec": 0,
        "rate_limit_user_per_min": 20,
        "rate_limit_user_per_day": 500,
    }
    base.update(overrides)
    monkeypatch.setattr(rl._pcfg, "get", lambda key, default=None: base.get(key, default))


def test_check_limits_distributed_ip_minute_breach(monkeypatch):
    db = _FakeDB()
    _set_limits(monkeypatch, rate_limit_ip_per_min=2, rate_limit_burst_multiplier=1.0)

    async def run():
        return [await rl.check_limits_distributed(db, "5.5.5.5", user_id="guest") for _ in range(3)]

    res = asyncio.run(run())
    assert res[0][0] is True and res[1][0] is True
    assert res[2][0] is False and "Rate limit" in res[2][1]


def test_check_limits_distributed_user_day_breach(monkeypatch):
    db = _FakeDB()
    _set_limits(monkeypatch, rate_limit_user_per_day=2)

    async def run():
        return [await rl.check_limits_distributed(db, "5.5.5.5", user_id="alice") for _ in range(3)]

    res = asyncio.run(run())
    assert res[1][0] is True
    assert res[2][0] is False and "Daily" in res[2][1]


def test_per_second_ip_cap_enforced(monkeypatch):
    db = _FakeDB()
    _set_limits(monkeypatch, rate_limit_ip_per_sec=2)
    # Pin time so all hits land in the same 1-second window.
    monkeypatch.setattr(rl.time, "time", lambda: 1_000_000.0)

    async def run():
        return [await rl.check_limits_distributed(db, "3.3.3.3", user_id="guest") for _ in range(3)]

    res = asyncio.run(run())
    assert res[0][0] is True and res[1][0] is True
    assert res[2][0] is False and "slow down" in res[2][1].lower()


def test_zero_disables_a_dimension(monkeypatch):
    db = _FakeDB()
    # Every IP window disabled (0). Many rapid hits must all pass.
    _set_limits(monkeypatch, rate_limit_ip_per_sec=0, rate_limit_ip_per_min=0, rate_limit_ip_per_hour=0)
    monkeypatch.setattr(rl.time, "time", lambda: 1_000_000.0)

    async def run():
        return [await rl.check_limits_distributed(db, "4.4.4.4", user_id="guest") for _ in range(50)]

    assert all(ok for ok, _ in asyncio.run(run()))


def test_duplicate_key_race_retries_then_increments():
    # Simulate the concurrent-insert race on the unique `key` index: the first
    # find_one_and_update raises DuplicateKeyError once, then the retry finds the
    # (now-existing) doc and increments it.
    db = _FakeDB()
    real = db.rate_limits.find_one_and_update
    state = {"raised": False}

    async def flaky(filt, update, **kw):
        if not state["raised"]:
            state["raised"] = True
            # Pretend a peer inserted the doc between our read and insert.
            db.rate_limits.docs[filt["key"]] = {"key": filt["key"], "count": 1}
            raise rl.DuplicateKeyError("dup")
        return await real(filt, update, **kw)

    db.rate_limits.find_one_and_update = flaky

    async def run():
        # limit high → retry path should end up allowed with count incremented.
        return await rl._hit_window(db, "ip_min", "7.7.7.7", 10, 60)

    assert asyncio.run(run()) is True
    assert db.rate_limits.docs["ip_min:7.7.7.7:" + str(int(rl.time.time() // 60) * 60)]["count"] == 2
