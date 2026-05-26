"""Unit tests for `services.service_hooks` — the small rule interpreter
that drives the pre_consent / pre_submit / post_submit hook points in
`application_flow.process_flow`.

These are pure-Python tests with no DB or HTTP — fast to run from
`backend/` via ``pytest tests/test_service_hooks.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Tests run via ``pytest`` from the `backend/` directory; add backend to
# sys.path so `from services.service_hooks import …` works regardless of
# where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.service_hooks import evaluate_hooks, first_action  # noqa: E402


# ── happy path ─────────────────────────────────────────────────────────


def test_empty_hooks_returns_empty():
    assert evaluate_hooks(None, {}) == []
    assert evaluate_hooks([], {"x": 1}) == []


def test_always_fire_rule_no_if():
    rules = [{"then": {"action": "show_message", "message": "Hi"}}]
    assert evaluate_hooks(rules, {}) == [{"action": "show_message", "message": "Hi"}]


def test_always_fire_with_explicit_true():
    rules = [{"if": True, "then": {"action": "block", "message": "no"}}]
    out = evaluate_hooks(rules, {})
    assert out == [{"action": "block", "message": "no"}]


def test_explicit_false_never_fires():
    rules = [{"if": False, "then": {"action": "block"}}]
    assert evaluate_hooks(rules, {}) == []


# ── field predicates ───────────────────────────────────────────────────


def test_eq_match():
    rules = [{"if": {"field": "country", "eq": "IN"}, "then": {"action": "show_message"}}]
    assert evaluate_hooks(rules, {"country": "IN"}) == [{"action": "show_message"}]
    assert evaluate_hooks(rules, {"country": "US"}) == []


def test_neq():
    rules = [{"if": {"field": "country", "neq": "IN"}, "then": {"action": "show_message"}}]
    assert evaluate_hooks(rules, {"country": "US"}) == [{"action": "show_message"}]
    assert evaluate_hooks(rules, {"country": "IN"}) == []


def test_in_and_not_in():
    rules_in = [{"if": {"field": "country", "in": ["IN", "BD"]}, "then": {"action": "a"}}]
    assert evaluate_hooks(rules_in, {"country": "IN"}) == [{"action": "a"}]
    assert evaluate_hooks(rules_in, {"country": "US"}) == []

    rules_nin = [{"if": {"field": "country", "not_in": ["IN"]}, "then": {"action": "b"}}]
    assert evaluate_hooks(rules_nin, {"country": "US"}) == [{"action": "b"}]
    assert evaluate_hooks(rules_nin, {"country": "IN"}) == []


def test_numeric_comparisons():
    base = [{"if": {"field": "amount", "gt": 10000}, "then": {"action": "review"}}]
    assert evaluate_hooks(base, {"amount": 15000}) == [{"action": "review"}]
    assert evaluate_hooks(base, {"amount": 10000}) == []  # strictly greater
    assert evaluate_hooks(base, {"amount": "15000"}) == [{"action": "review"}]  # coerce str
    # malformed value → fails closed
    assert evaluate_hooks(base, {"amount": "huge"}) == []

    for op, val, expected_match, no_match in [
        ("lt", 100, 50, 200),
        ("gte", 100, 100, 99),
        ("lte", 100, 100, 101),
    ]:
        rules = [{"if": {"field": "x", op: val}, "then": {"action": "a"}}]
        assert evaluate_hooks(rules, {"x": expected_match}), f"{op} should match"
        assert not evaluate_hooks(rules, {"x": no_match}), f"{op} should not match"


def test_regex_matches():
    rules = [
        {"if": {"field": "email", "matches": r"@example\.com$"},
         "then": {"action": "show_message", "message": "Internal staff"}}
    ]
    out = evaluate_hooks(rules, {"email": "alice@example.com"})
    assert out == [{"action": "show_message", "message": "Internal staff"}]
    assert evaluate_hooks(rules, {"email": "alice@gmail.com"}) == []
    # Missing field → empty string → no match
    assert evaluate_hooks(rules, {}) == []


def test_exists_predicate():
    rules_present = [{"if": {"field": "passport", "exists": True}, "then": {"action": "a"}}]
    assert evaluate_hooks(rules_present, {"passport": "AB123"}) == [{"action": "a"}]
    assert evaluate_hooks(rules_present, {"passport": ""}) == []
    assert evaluate_hooks(rules_present, {}) == []

    rules_absent = [{"if": {"field": "passport", "exists": False}, "then": {"action": "b"}}]
    assert evaluate_hooks(rules_absent, {}) == [{"action": "b"}]
    assert evaluate_hooks(rules_absent, {"passport": "AB123"}) == []


def test_dotted_field_lookup():
    rules = [
        {"if": {"field": "user.email", "matches": r"@example\.com$"},
         "then": {"action": "a"}}
    ]
    assert evaluate_hooks(rules, {"user": {"email": "x@example.com"}}) == [{"action": "a"}]
    assert evaluate_hooks(rules, {"user": {"email": "x@other.com"}}) == []
    assert evaluate_hooks(rules, {"user": {}}) == []
    assert evaluate_hooks(rules, {}) == []


# ── boolean combinators ────────────────────────────────────────────────


def test_and_combinator():
    rules = [{
        "if": {"and": [
            {"field": "country", "eq": "IN"},
            {"field": "amount", "gt": 1000},
        ]},
        "then": {"action": "review"},
    }]
    assert evaluate_hooks(rules, {"country": "IN", "amount": 5000}) == [{"action": "review"}]
    assert evaluate_hooks(rules, {"country": "IN", "amount": 500}) == []
    assert evaluate_hooks(rules, {"country": "US", "amount": 5000}) == []


def test_or_combinator():
    rules = [{
        "if": {"or": [
            {"field": "country", "eq": "IN"},
            {"field": "country", "eq": "BD"},
        ]},
        "then": {"action": "a"},
    }]
    assert evaluate_hooks(rules, {"country": "IN"}) == [{"action": "a"}]
    assert evaluate_hooks(rules, {"country": "BD"}) == [{"action": "a"}]
    assert evaluate_hooks(rules, {"country": "US"}) == []


def test_not_combinator():
    rules = [{"if": {"not": {"field": "country", "eq": "IN"}}, "then": {"action": "a"}}]
    assert evaluate_hooks(rules, {"country": "US"}) == [{"action": "a"}]
    assert evaluate_hooks(rules, {"country": "IN"}) == []


def test_nested_combinators():
    rules = [{
        "if": {
            "and": [
                {"field": "country", "in": ["IN", "BD"]},
                {"or": [
                    {"field": "amount", "gt": 10000},
                    {"field": "vip", "eq": True},
                ]},
            ],
        },
        "then": {"action": "review"},
    }]
    assert evaluate_hooks(rules, {"country": "IN", "amount": 20000, "vip": False}) == [{"action": "review"}]
    assert evaluate_hooks(rules, {"country": "IN", "amount": 100,   "vip": True})  == [{"action": "review"}]
    assert evaluate_hooks(rules, {"country": "IN", "amount": 100,   "vip": False}) == []
    assert evaluate_hooks(rules, {"country": "US", "amount": 99999, "vip": True})  == []


# ── multiple rules / ordering ──────────────────────────────────────────


def test_all_matching_rules_contribute():
    rules = [
        {"if": {"field": "country", "eq": "IN"}, "then": {"action": "show_message", "message": "A"}},
        {"if": {"field": "amount", "gt": 1000}, "then": {"action": "show_message", "message": "B"}},
        {"if": {"field": "amount", "gt": 99999}, "then": {"action": "block"}},
    ]
    out = evaluate_hooks(rules, {"country": "IN", "amount": 5000})
    assert out == [
        {"action": "show_message", "message": "A"},
        {"action": "show_message", "message": "B"},
    ]


def test_first_action_picks_first_by_name():
    actions = [
        {"action": "show_message", "message": "hi"},
        {"action": "block", "message": "stop"},
        {"action": "send_email", "to": "x@y"},
    ]
    assert first_action(actions, "block") == {"action": "block", "message": "stop"}
    assert first_action(actions, "missing") is None


# ── malformed / hostile input fails closed ────────────────────────────


def test_malformed_rule_is_skipped():
    rules = [
        "not a dict",  # garbage
        {"if": {"field": "x", "eq": 1}, "then": "not a dict"},  # garbage action
        {"if": {"field": "x", "eq": 1}, "then": {"action": "a"}},  # the valid one
    ]
    out = evaluate_hooks(rules, {"x": 1})
    assert out == [{"action": "a"}]


def test_bad_regex_does_not_raise():
    rules = [{"if": {"field": "x", "matches": "[unterminated"}, "then": {"action": "a"}}]
    assert evaluate_hooks(rules, {"x": "anything"}) == []


def test_unknown_predicate_is_false():
    rules = [{"if": {"field": "x", "starts_with": "foo"}, "then": {"action": "a"}}]
    assert evaluate_hooks(rules, {"x": "foobar"}) == []


def test_missing_field_with_field_predicate():
    rules = [{"if": {"eq": 1}, "then": {"action": "a"}}]  # no "field"
    assert evaluate_hooks(rules, {"x": 1}) == []
