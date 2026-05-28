"""
Local shim for emergentintegrations.llm.chat
Wraps the OpenAI library to provide LlmChat, UserMessage, ImageContent.
"""
import openai
import os
import logging
from typing import List, Optional, Any

logger = logging.getLogger(__name__)

# Per-session history cap. 0 = unlimited (replay everything — default, no
# behaviour change). When >0, _build_messages evicts the oldest turns in a
# chunk (down to half the cap) once a session exceeds it, bounding both the
# replayed input tokens and the stored history doc size. Chunked (not a
# per-turn slide) so the [system + history] prefix stays stable between
# evictions and OpenAI prompt caching keeps hitting during the growth phase.
_MAX_HISTORY_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", "0"))


def _evict_history(history: list) -> None:
    """Trim a session's history in place to the configured cap (chunked)."""
    if _MAX_HISTORY_MESSAGES > 0 and len(history) > _MAX_HISTORY_MESSAGES:
        keep = max(1, _MAX_HISTORY_MESSAGES // 2)
        del history[:-keep]


def _extract_cached_tokens(u) -> int:
    """Cached prompt tokens for a call, for prompt-cache hit-rate tracking.

    OpenAI reports these under ``usage.prompt_tokens_details.cached_tokens``
    (cached input is billed at 50% on gpt-4o-mini). Gemini has no equivalent,
    so this returns 0 there. Best-effort; never raises."""
    try:
        details = getattr(u, "prompt_tokens_details", None)
        return int(getattr(details, "cached_tokens", 0) or 0)
    except Exception:
        return 0


# Conversation history is persisted in MongoDB (collection below), NOT in
# process memory — so it survives restarts and is shared across workers /
# serverless instances (Cloud Run, Lambda). With in-process state, a multi-turn
# conversation whose turns land on different workers would lose its context.
_HISTORY_COLLECTION = "llm_chat_sessions"


async def _load_history(session_id: str) -> list:
    """Load a session's replay history (list of {role, content}) from Mongo.
    Returns [] on a new session or any error (never breaks the chat path)."""
    if not session_id:
        return []
    try:
        from database import get_database
        db = await get_database()
        doc = await db[_HISTORY_COLLECTION].find_one({"_id": session_id}, {"messages": 1})
        return list((doc or {}).get("messages") or [])
    except Exception as e:
        logger.warning("[LlmChat] history load failed for %s: %s", session_id, e)
        return []


async def _save_history(session_id: str, messages: list) -> None:
    """Persist a session's replay history. ``updated_at`` drives the TTL index
    (see database.create_indexes) so abandoned sessions auto-expire — which also
    fixes the unbounded session-count growth of the old in-memory dict."""
    if not session_id:
        return
    try:
        from datetime import datetime, timezone
        from database import get_database
        db = await get_database()
        await db[_HISTORY_COLLECTION].update_one(
            {"_id": session_id},
            {"$set": {"messages": messages, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception as e:
        logger.warning("[LlmChat] history save failed for %s: %s", session_id, e)


async def history_len(session_id: str) -> int:
    """Number of stored turns for a session (0 = no prior turn). Async because
    history now lives in Mongo. Used by the response cache to restrict caching
    to context-free opening questions."""
    return len(await _load_history(session_id))

# Legacy hardcoded model map. Kept only as a last-resort fallback when
# the `platform_models` collection is empty (fresh install before
# migration 0011 runs) or the DB lookup fails. The authoritative source
# is now `services.model_registry`; super-admins edit the rows via the
# Models tab and the runtime picks the change up on the next cache TTL.
MODEL_MAP = {
    "gpt-5.2": "gpt-4o-mini",
    "gpt-5":   "gpt-4o-mini",
}


class ImageContent:
    def __init__(self, image_base64: str, media_type: str = "image/jpeg"):
        self.image_base64 = image_base64
        self.media_type = media_type


class UserMessage:
    def __init__(self, text: str, file_contents: Optional[List[Any]] = None,
                 context: Optional[str] = None):
        self.text = text
        self.file_contents = file_contents or []
        # Ephemeral per-turn context (retrieved KB, per-request instructions).
        # It is sent to the model WITH this turn but NOT persisted to history.
        # Keeping it out of both the (stable) system message and the persisted
        # history means the [system + history] prefix stays byte-identical
        # across turns, so OpenAI's automatic prompt cache hits it — and history
        # doesn't accumulate large per-turn knowledge blobs.
        self.context = context


class LlmChat:
    def __init__(self, api_key: str, session_id: str, system_message: str = "",
                 max_tokens: Optional[int] = 400):
        import os
        # If an emergent-platform key is passed, fall back to real OpenAI key
        if api_key and api_key.startswith("sk-emergent"):
            api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY", api_key)
        self.api_key = api_key
        self.session_id = session_id
        self.system_message = system_message
        self.model = "gpt-4o-mini"
        # Tenant-facing platform model key (the one super-admins edit in
        # the Models tab). The runtime resolves this to the underlying
        # provider model via `services.model_registry`.
        self.platform_key = "gpt-4o-mini"
        # Hard cap on completion length. None = unlimited (use only for extraction tasks).
        self.max_tokens = max_tokens
        # Populated after each send_message / send_message_stream so the
        # caller can log per-request cost. Shape: {"prompt_tokens": int,
        # "completion_tokens": int, "model": str}. None until first call.
        # Streaming responses surface usage via the OpenAI
        # `stream_options={"include_usage": True}` final chunk.
        self.last_usage: Optional[dict] = None

    def with_model(self, provider: str, model: str) -> "LlmChat":
        # Stash the tenant-facing platform key. The real api_model gets
        # resolved at request time inside _resolve_api_model() so a
        # super-admin edit propagates without restarting LlmChat
        # instances. Pre-set self.model to the legacy fallback so an
        # importer reading .model before the first send_message still
        # gets a sensible value.
        self.platform_key = model
        self.model = MODEL_MAP.get(model, model)
        return self

    async def _resolve_api_model(self) -> str:
        """Look up the actual provider API model from the registry.
        Falls back to MODEL_MAP and finally the raw key if both miss."""
        try:
            from services import model_registry
            return await model_registry.resolve_api_model(self.platform_key or self.model)
        except Exception:
            return MODEL_MAP.get(self.platform_key or self.model, self.platform_key or self.model)

    async def _resolve_provider(self) -> str:
        """Look up the provider string for the configured model
        (e.g. "openai", "google"). Defaults to "openai" if the row is
        missing — old hardcoded keys all map to OpenAI."""
        try:
            from services import model_registry
            row = await model_registry.get_model(self.platform_key or self.model)
            return ((row or {}).get("provider") or "openai").lower()
        except Exception:
            return "openai"

    def with_max_tokens(self, max_tokens: Optional[int]) -> "LlmChat":
        self.max_tokens = max_tokens
        return self

    def _build_messages(self, message: UserMessage, history: list) -> tuple:
        """Return (history, openai_messages_list) for the loaded ``history``.

        Pure (no global state): evicts to the cap, builds the outgoing messages,
        and appends the bare user text to ``history`` for the caller to persist.

        The outgoing request contains the full multimodal content for THIS turn,
        but only the text portion is persisted to history. Replaying image_url
        parts on every follow-up turn poisons the whole conversation if any
        single upload happens to be in a format OpenAI rejects.

        ``message.context`` (ephemeral per-turn knowledge/instructions) is sent
        to the model this turn but never persisted — see UserMessage.
        """
        _evict_history(history)  # bound replay + stored size (no-op when cap is 0)
        # Text the model sees this turn = ephemeral context (if any) + user text.
        # Only the bare user text is persisted to history below.
        text_for_model = message.text or ""
        if message.context:
            text_for_model = (
                f"{message.context}\n\n{text_for_model}" if text_for_model
                else message.context
            )
        if message.file_contents:
            content: Any = []
            if text_for_model:
                content.append({"type": "text", "text": text_for_model})
            for item in message.file_contents:
                if isinstance(item, ImageContent):
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{item.media_type};base64,{item.image_base64}"
                        }
                    })
        else:
            content = text_for_model
        messages = []
        if self.system_message:
            messages.append({"role": "system", "content": self.system_message})
        messages.extend(history)
        messages.append({"role": "user", "content": content})
        history.append({"role": "user", "content": message.text or ""})
        return history, messages

    def _completion_kwargs(self) -> dict:
        kwargs: dict = {"model": self.model}
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        return kwargs

    async def send_message(self, message: UserMessage) -> str:
        # Resolve the provider API model from the platform registry on
        # every call so a super-admin's edit propagates without
        # restarting the process or its long-lived LlmChat instances.
        self.model = await self._resolve_api_model()
        provider = await self._resolve_provider()
        if provider == "google":
            return await self._send_via_gemini(message, stream=False)
        history = await _load_history(self.session_id)
        history, messages = self._build_messages(message, history)
        client = openai.AsyncOpenAI(api_key=self.api_key)
        try:
            response = await client.chat.completions.create(
                messages=messages,
                **self._completion_kwargs(),
            )
            assistant_text = response.choices[0].message.content
            # Capture usage for downstream cost logging. The OpenAI SDK
            # returns a CompletionUsage object on non-stream calls.
            try:
                u = getattr(response, "usage", None)
                if u is not None:
                    self.last_usage = {
                        "prompt_tokens":     int(getattr(u, "prompt_tokens", 0) or 0),
                        "completion_tokens": int(getattr(u, "completion_tokens", 0) or 0),
                        "cached_tokens":     _extract_cached_tokens(u),
                        # Record the tenant-facing platform key so the
                        # cost dashboard groups by what the operator
                        # actually picked, not the underlying API alias.
                        "model":             self.platform_key or self.model,
                    }
            except Exception:
                # Never let usage capture failure break the response path.
                pass
        except Exception as e:
            logger.error(f"[LlmChat] API error: {e}")
            raise
        history.append({"role": "assistant", "content": assistant_text})
        await _save_history(self.session_id, history)
        return assistant_text

    async def send_message_stream(self, message: UserMessage):
        """Yield text chunks as they stream from the LLM.

        Streaming responses surface usage via OpenAI's
        ``stream_options={"include_usage": True}`` — a final chunk with
        empty choices and a populated ``usage`` arrives after the last
        text delta. We stash that into ``self.last_usage`` so the
        caller can log cost after the generator is drained."""
        self.model = await self._resolve_api_model()
        provider = await self._resolve_provider()
        if provider == "google":
            async for chunk in self._stream_via_gemini(message):
                yield chunk
            return
        history = await _load_history(self.session_id)
        history, messages = self._build_messages(message, history)
        client = openai.AsyncOpenAI(api_key=self.api_key)
        full_response = ""
        try:
            stream = await client.chat.completions.create(
                messages=messages,
                stream=True,
                stream_options={"include_usage": True},
                **self._completion_kwargs(),
            )
            async for chunk in stream:
                # The usage-only final chunk has empty choices; guard
                # against IndexError before touching choices[0].
                if chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        full_response += delta
                        yield delta
                u = getattr(chunk, "usage", None)
                if u is not None:
                    try:
                        self.last_usage = {
                            "prompt_tokens":     int(getattr(u, "prompt_tokens", 0) or 0),
                            "completion_tokens": int(getattr(u, "completion_tokens", 0) or 0),
                            "cached_tokens":     _extract_cached_tokens(u),
                            # Record the tenant-facing platform key so the cost
                            # dashboard groups by what the operator actually
                            # picked, not the underlying API alias.
                            "model":             self.platform_key or self.model,
                        }
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"[LlmChat] stream error: {e}")
            raise
        history.append({"role": "assistant", "content": full_response})
        await _save_history(self.session_id, history)

    # ── Google Gemini provider ────────────────────────────────────────────
    #
    # The Gemini SDK takes a flat string + role-tagged history that's
    # similar-but-not-identical to OpenAI's shape. We translate at the
    # boundary so the call sites stay provider-agnostic. ImageContent
    # parts become `inline_data` blocks; the system message becomes the
    # `system_instruction` config field.
    #
    # Usage capture: Gemini returns ``usage_metadata`` with
    # ``prompt_token_count`` / ``candidates_token_count`` on the final
    # response object. We map both into ``last_usage`` with the same
    # shape OpenAI emits so the cost dashboard doesn't care which
    # provider answered.

    def _gemini_client(self):
        """Lazy-import google-genai so the OpenAI-only path doesn't pay
        the import cost. Raises with a clear message if the SDK isn't
        installed (i.e. the operator added a google model row without
        installing the dep)."""
        try:
            from google import genai  # noqa
        except ImportError as e:
            raise RuntimeError(
                "Google Gemini SDK not installed. Run `pip install google-genai` "
                "in the backend venv and restart the server."
            ) from e
        import os
        from google import genai
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Gemini API key missing. Set GOOGLE_API_KEY (or GEMINI_API_KEY) in backend/.env."
            )
        return genai.Client(api_key=api_key)

    def _build_gemini_payload(self, message: "UserMessage", history: list):
        """Return (history, contents_for_this_turn) for the loaded ``history``.
        The Gemini SDK wants the system message as a separate config field, so
        we strip it from the per-turn payload."""
        _evict_history(history)  # bound replay + stored size (no-op when cap is 0)
        # Build the user content. Text-only is a plain string; images
        # need to be wrapped as Part objects with inline_data.
        try:
            from google.genai import types
        except ImportError:
            raise RuntimeError("google-genai SDK not installed")
        parts = []
        text_for_model = message.text or ""
        if message.context:
            text_for_model = (
                f"{message.context}\n\n{text_for_model}" if text_for_model
                else message.context
            )
        if text_for_model:
            parts.append(types.Part.from_text(text=text_for_model))
        for item in (message.file_contents or []):
            if isinstance(item, ImageContent):
                import base64
                raw = base64.b64decode(item.image_base64)
                parts.append(types.Part.from_bytes(data=raw, mime_type=item.media_type))
        # Translate history into Gemini's role+parts shape ("user" stays,
        # "assistant" → "model"). Only text history is replayed.
        gem_history = []
        for h in history:
            role = "model" if h.get("role") == "assistant" else "user"
            gem_history.append(types.Content(role=role, parts=[types.Part.from_text(text=h.get("content") or "")]))
        gem_history.append(types.Content(role="user", parts=parts))
        history.append({"role": "user", "content": message.text or ""})
        return history, gem_history

    def _gemini_capture_usage(self, response) -> None:
        """Pull usage_metadata into self.last_usage in the OpenAI shape."""
        try:
            meta = getattr(response, "usage_metadata", None)
            if meta is None:
                return
            prompt = int(getattr(meta, "prompt_token_count", 0) or 0)
            completion = int(getattr(meta, "candidates_token_count", 0) or 0)
            self.last_usage = {
                "prompt_tokens":     prompt,
                "completion_tokens": completion,
                "model":             self.platform_key or self.model,
            }
        except Exception:
            pass

    async def _send_via_gemini(self, message: "UserMessage", stream: bool = False) -> str:
        from google.genai import types  # noqa: F401
        client = self._gemini_client()
        history = await _load_history(self.session_id)
        history, contents = self._build_gemini_payload(message, history)
        try:
            from google.genai import types as gt
            config = gt.GenerateContentConfig(
                system_instruction=self.system_message or None,
                max_output_tokens=self.max_tokens,
            )
            # Gemini async client uses .aio namespace.
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            text = (response.text or "").strip()
            self._gemini_capture_usage(response)
        except Exception as e:
            logger.error(f"[LlmChat/Gemini] API error: {e}")
            raise
        history.append({"role": "assistant", "content": text})
        await _save_history(self.session_id, history)
        return text

    async def _stream_via_gemini(self, message: "UserMessage"):
        """Async generator yielding text chunks from Gemini. The SDK's
        ``generate_content_stream`` returns an async iterator of chunk
        objects; we accumulate text + capture usage from the last
        chunk in the stream."""
        client = self._gemini_client()
        history = await _load_history(self.session_id)
        history, contents = self._build_gemini_payload(message, history)
        full = ""
        last_chunk = None
        try:
            from google.genai import types as gt
            config = gt.GenerateContentConfig(
                system_instruction=self.system_message or None,
                max_output_tokens=self.max_tokens,
            )
            stream = await client.aio.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                last_chunk = chunk
                text = getattr(chunk, "text", None) or ""
                if text:
                    full += text
                    yield text
        except Exception as e:
            logger.error(f"[LlmChat/Gemini] stream error: {e}")
            raise
        if last_chunk is not None:
            self._gemini_capture_usage(last_chunk)
        history.append({"role": "assistant", "content": full})
        await _save_history(self.session_id, history)
