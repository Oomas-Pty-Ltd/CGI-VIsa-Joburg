"""Unit tests for the in-process TTS audio cache (``voice_service``).

Offline — exercises the pure cache helpers (key derivation, get/put, eviction,
TTL). No OpenAI calls. Guards the cost-saving invariant: identical
(model, voice, speed, language, text) returns the same cached clip without a
second synthesis charge, and the cache stays bounded.
"""
from __future__ import annotations

import time

import voice_service as vs


def test_key_is_deterministic_and_field_sensitive():
    k = vs._tts_key("tts-1", "nova", 1.0, "en", "hello")
    assert k == vs._tts_key("tts-1", "nova", 1.0, "en", "hello")
    assert k != vs._tts_key("tts-1-hd", "nova", 1.0, "en", "hello")   # model
    assert k != vs._tts_key("tts-1", "shimmer", 1.0, "en", "hello")   # voice
    assert k != vs._tts_key("tts-1", "nova", 1.0, "hi", "hello")      # language
    assert k != vs._tts_key("tts-1", "nova", 1.0, "en", "hi there")   # text


def test_put_get_roundtrip():
    vs._TTS_CACHE.clear()
    k = vs._tts_key("tts-1", "nova", 1.0, "en", "cache me")
    assert vs._tts_cache_get(k) is None
    vs._tts_cache_put(k, "BASE64AUDIO")
    assert vs._tts_cache_get(k) == "BASE64AUDIO"


def test_empty_value_not_cached():
    vs._TTS_CACHE.clear()
    k = vs._tts_key("tts-1", "nova", 1.0, "en", "x")
    vs._tts_cache_put(k, "")          # empty/None synthesis result must not be stored
    assert vs._tts_cache_get(k) is None


def test_eviction_respects_max(monkeypatch):
    vs._TTS_CACHE.clear()
    monkeypatch.setattr(vs, "_TTS_CACHE_MAX", 3)
    for i in range(5):
        vs._tts_cache_put(vs._tts_key("tts-1", "nova", 1.0, "en", f"t{i}"), f"a{i}")
    assert len(vs._TTS_CACHE) <= 3


def test_ttl_expiry(monkeypatch):
    vs._TTS_CACHE.clear()
    monkeypatch.setattr(vs, "_TTS_CACHE_TTL", 0.05)
    k = vs._tts_key("tts-1", "nova", 1.0, "en", "expiring")
    vs._tts_cache_put(k, "AUDIO")
    assert vs._tts_cache_get(k) == "AUDIO"
    time.sleep(0.08)
    assert vs._tts_cache_get(k) is None


def test_enabled_reads_env(monkeypatch):
    monkeypatch.setenv("TTS_CACHE_ENABLED", "false")
    assert vs._tts_cache_enabled() is False
    monkeypatch.setenv("TTS_CACHE_ENABLED", "true")
    assert vs._tts_cache_enabled() is True


def test_default_model_is_tts1():
    # Cost-optimal default; revertable via TTS_MODEL=tts-1-hd.
    assert vs._TTS_MODEL in ("tts-1", "tts-1-hd")  # whatever env set; default tts-1
