"""Regression tests for the keyword-based intent helpers in
``services.application_flow`` — ``is_yes`` / ``is_no`` / ``is_apply_intent``
/ ``is_discard`` / ``is_continue``.

These guard against the substring-match bug we hit on 2026-05-27 where a
single-letter keyword like ``"y"`` matched any message containing the
letter "y" (so "apply for visa" classified as "yes" during consent
state and silently advanced the application flow). Whole-word matching
is required for single-token keywords; multi-word phrases still match
as substrings so things like "go back" work mid-sentence.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Run via pytest from backend/, but be path-safe either way.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.application_flow import (  # noqa: E402
    is_yes, is_no, is_apply_intent, is_discard, is_continue,
)


# ── is_yes: must NOT match short-keyword substrings ────────────────────


def test_is_yes_does_not_match_y_in_random_words():
    """The single-letter "y" yes-keyword must not match inside other words."""
    assert is_yes("apply for visa") is False
    assert is_yes("I want to apply for a tourist visa") is False
    assert is_yes("yesterday I went") is False
    assert is_yes("my name is Sally") is False


def test_is_yes_does_not_match_ok_in_random_words():
    """ "ok" is in the yes set; it must not match inside "okra", "tokens", etc."""
    assert is_yes("the okra is fresh") is False
    assert is_yes("count the tokens") is False


def test_is_yes_matches_exact_yes():
    for s in ["yes", "yes.", "yes!", "Yes", "  yes  ", "y", "Y", "ok", "okay",
              "sure", "confirm", "proceed", "yeah", "yep", "yes please"]:
        assert is_yes(s) is True, f"expected is_yes({s!r}) to be True"


# ── is_no: same shape ─────────────────────────────────────────────────


def test_is_no_does_not_match_n_in_random_words():
    assert is_no("apply for visa") is False
    assert is_no("I don't want it") is False  # has 'n' but no whole-word 'n'
    assert is_no("noticed nothing") is False  # 'n' as letter, not whole word
    # 'no' literally embedded in "notice" used to substring-match the keyword "no"
    assert is_no("I noticed something") is False


def test_is_no_matches_exact_no():
    for s in ["no", "no.", "No", "  no  ", "n", "nope", "cancel"]:
        assert is_no(s) is True, f"expected is_no({s!r}) to be True"


# ── is_apply_intent ───────────────────────────────────────────────────


def test_is_apply_matches_real_apply_intent():
    for s in ["apply", "I want to apply", "register me", "let's begin",
              "start application", "apply now"]:
        assert is_apply_intent(s) is True, f"expected is_apply({s!r}) to be True"


def test_is_apply_no_false_positives_on_unrelated():
    assert is_apply_intent("how much is the fee") is False
    assert is_apply_intent("where is your office") is False


# ── is_discard: includes multi-word phrases ───────────────────────────


def test_is_discard_matches_multiword_phrases():
    # "go back" must match anywhere — that's the whole reason we keep
    # substring matching for multi-word keywords.
    assert is_discard("go back") is True
    assert is_discard("I want to go back to the main menu") is True
    assert is_discard("main menu please") is True
    assert is_discard("discard") is True
    assert is_discard("cancel") is True


def test_is_discard_no_false_positives():
    # "back" is in the keyword set but only as a whole word, not a substring.
    assert is_discard("backpack") is False
    assert is_discard("background check") is False


# ── is_continue chains is_yes — make sure the substring bug doesn't sneak in ─


def test_is_continue_does_not_match_y_in_random_words():
    assert is_continue("apply for visa") is False
    assert is_continue("I want to apply for a tourist visa") is False


def test_is_continue_matches_real_continue_intent():
    for s in ["continue", "resume", "go on", "yes continue", "yes"]:
        assert is_continue(s) is True, f"expected is_continue({s!r}) to be True"
