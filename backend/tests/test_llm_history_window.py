"""Regression tests for the optional per-session history cap in the LLM shim
(``emergentintegrations.llm.chat``, ``MAX_HISTORY_MESSAGES``).

Why this exists (cost + reliability): full-history replay grows input tokens
and the stored history doc without bound. When the cap is set, ``_evict_history``
(invoked from ``_build_messages``) trims a session to the cap, dropping the
OLDEST turns in a chunk (down to half the cap) so the [system + history] prefix
stays stable between evictions (prompt caching keeps hitting) and the stored
history stays bounded. Default 0 = unlimited (no behaviour change).

History now lives in Mongo, so ``_build_messages(message, history)`` is pure —
these tests drive it with a local ``history`` list (no network/DB).
"""
from __future__ import annotations

import emergentintegrations.llm.chat as chat
from emergentintegrations.llm.chat import LlmChat, UserMessage


def _run_turns(history: list, n: int) -> None:
    c = LlmChat(api_key="x", session_id="win", system_message="S")
    for i in range(n):
        c._build_messages(UserMessage(text=f"q{i}"), history)              # appends user turn + evicts
        history.append({"role": "assistant", "content": f"a{i}"})          # as send_message would


def test_unlimited_by_default(monkeypatch):
    monkeypatch.setattr(chat, "_MAX_HISTORY_MESSAGES", 0)
    history: list = []
    _run_turns(history, 20)
    assert len(history) == 40  # 20 user + 20 assistant, nothing evicted


def test_cap_bounds_history(monkeypatch):
    monkeypatch.setattr(chat, "_MAX_HISTORY_MESSAGES", 6)
    history: list = []
    _run_turns(history, 20)
    assert len(history) <= 6 + 2  # cap + at most one in-flight turn's two appends


def test_keeps_recent_drops_oldest(monkeypatch):
    monkeypatch.setattr(chat, "_MAX_HISTORY_MESSAGES", 6)
    history: list = []
    _run_turns(history, 20)
    contents = [m["content"] for m in history]
    assert "q19" in contents and "a19" in contents      # most recent kept
    assert "q0" not in contents and "a0" not in contents  # oldest evicted


def test_eviction_is_chunked_not_per_turn(monkeypatch):
    # A per-turn slide would change the first history message almost every turn
    # (~14 times over 16 turns). Chunked eviction keeps it stable for a run of
    # turns between evictions (cap 12, keep 6 → evicts ~every 4 turns → ~3-4
    # changes), so prompt caching keeps hitting in between.
    monkeypatch.setattr(chat, "_MAX_HISTORY_MESSAGES", 12)
    c = LlmChat(api_key="x", session_id="win-chunk", system_message="S")
    history: list = []
    firsts = []
    for i in range(16):
        _, msgs = c._build_messages(UserMessage(text=f"q{i}"), history)
        firsts.append(msgs[1]["content"] if len(msgs) > 2 else None)  # first history msg
        history.append({"role": "assistant", "content": f"a{i}"})
    seen = [f for f in firsts if f is not None]
    changes = sum(1 for a, b in zip(seen, seen[1:]) if a != b)
    assert changes <= 6  # chunked; a per-turn slide would change ~14 times
