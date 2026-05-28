"""Regression tests for the ephemeral per-turn ``context`` on the LLM shim
(``emergentintegrations.llm.chat``).

Why this exists (cost control): retrieved knowledge / per-request instructions
must be sent to the model on the current turn but must NOT end up in either
the (stable) system message or the persisted history. Keeping them out of both
means the ``[system + history]`` prefix stays byte-identical across turns, so
OpenAI's automatic prompt cache hits it, and history doesn't accumulate large
per-turn knowledge blobs.

History now lives in Mongo (not the old in-process ``_sessions`` dict), so these
tests exercise ``_build_messages(message, history)`` as a PURE function — pass
the history list in, assert on the returned messages + the mutated history.
Offline: no network/DB.
"""
from __future__ import annotations

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent


def _chat():
    return LlmChat(api_key="sk-test", session_id="pytest-ctx", system_message="STATIC")


def test_context_reaches_model_but_is_not_persisted():
    chat = _chat()
    history: list = []
    history, msgs = chat._build_messages(
        UserMessage(text="What is the visa fee?", context="OFFICIAL DATA: fee is X"), history
    )
    assert msgs[0] == {"role": "system", "content": "STATIC"}
    assert "OFFICIAL DATA: fee is X" in msgs[-1]["content"]   # context reaches the model
    assert "What is the visa fee?" in msgs[-1]["content"]
    # Persisted history holds ONLY the bare user text — never the context blob.
    assert history[-1] == {"role": "user", "content": "What is the visa fee?"}


def test_history_prefix_is_byte_stable_across_turns():
    chat = _chat()
    history: list = []
    history, _ = chat._build_messages(UserMessage(text="Q1", context="DATA-A"), history)
    history.append({"role": "assistant", "content": "A1"})   # as send_message would

    history, msgs2 = chat._build_messages(UserMessage(text="Q2", context="DATA-B"), history)
    assert msgs2[0] == {"role": "system", "content": "STATIC"}
    assert msgs2[1] == {"role": "user", "content": "Q1"}
    assert msgs2[2] == {"role": "assistant", "content": "A1"}
    assert "DATA-B" in msgs2[-1]["content"]
    for item in history:
        assert "DATA-A" not in item["content"] and "DATA-B" not in item["content"]


def test_multimodal_context_rides_in_text_part():
    chat = _chat()
    history: list = []
    history, msgs = chat._build_messages(
        UserMessage(text="see image", context="CTX",
                    file_contents=[ImageContent(image_base64="AAAA", media_type="image/png")]),
        history,
    )
    parts = msgs[-1]["content"]
    text_parts = [p for p in parts if p.get("type") == "text"]
    assert text_parts and "CTX" in text_parts[0]["text"] and "see image" in text_parts[0]["text"]
    assert any(p.get("type") == "image_url" for p in parts)
    assert history[-1] == {"role": "user", "content": "see image"}


def test_no_context_is_backward_compatible():
    chat = _chat()
    history: list = []
    history, msgs = chat._build_messages(UserMessage(text="hello"), history)
    assert msgs[-1] == {"role": "user", "content": "hello"}
    assert history[-1] == {"role": "user", "content": "hello"}
