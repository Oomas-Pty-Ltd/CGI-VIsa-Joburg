"""
Local shim for emergentintegrations.llm.chat
Wraps the OpenAI library to provide LlmChat, UserMessage, ImageContent.
"""
import openai
import logging
from typing import List, Optional, Any

logger = logging.getLogger(__name__)

# In-memory chat history keyed by session_id
_sessions: dict = {}

# Models that don't exist on the standard OpenAI API are mapped to a real one
MODEL_MAP = {
    "gpt-5.2": "gpt-4o-mini",
    "gpt-5":   "gpt-4o-mini",
}


class ImageContent:
    def __init__(self, image_base64: str, media_type: str = "image/jpeg"):
        self.image_base64 = image_base64
        self.media_type = media_type


class UserMessage:
    def __init__(self, text: str, file_contents: Optional[List[Any]] = None):
        self.text = text
        self.file_contents = file_contents or []


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
        # Hard cap on completion length. None = unlimited (use only for extraction tasks).
        self.max_tokens = max_tokens
        if session_id not in _sessions:
            _sessions[session_id] = []

    def with_model(self, provider: str, model: str) -> "LlmChat":
        self.model = MODEL_MAP.get(model, model)
        return self

    def with_max_tokens(self, max_tokens: Optional[int]) -> "LlmChat":
        self.max_tokens = max_tokens
        return self

    def _build_messages(self, message: UserMessage) -> tuple:
        """Return (history, openai_messages_list).

        The outgoing request contains the full multimodal content for THIS turn,
        but only the text portion is persisted to history. Replaying image_url
        parts on every follow-up turn poisons the whole conversation if any
        single upload happens to be in a format OpenAI rejects.
        """
        history = _sessions.get(self.session_id, [])
        if message.file_contents:
            content: Any = []
            if message.text:
                content.append({"type": "text", "text": message.text})
            for item in message.file_contents:
                if isinstance(item, ImageContent):
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{item.media_type};base64,{item.image_base64}"
                        }
                    })
        else:
            content = message.text
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
        history, messages = self._build_messages(message)
        client = openai.AsyncOpenAI(api_key=self.api_key)
        try:
            response = await client.chat.completions.create(
                messages=messages,
                **self._completion_kwargs(),
            )
            assistant_text = response.choices[0].message.content
        except Exception as e:
            logger.error(f"[LlmChat] API error: {e}")
            raise
        history.append({"role": "assistant", "content": assistant_text})
        _sessions[self.session_id] = history
        return assistant_text

    async def send_message_stream(self, message: UserMessage):
        """Yield text chunks as they stream from the LLM."""
        history, messages = self._build_messages(message)
        client = openai.AsyncOpenAI(api_key=self.api_key)
        full_response = ""
        try:
            stream = await client.chat.completions.create(
                messages=messages,
                stream=True,
                **self._completion_kwargs(),
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_response += delta
                    yield delta
        except Exception as e:
            logger.error(f"[LlmChat] stream error: {e}")
            raise
        history.append({"role": "assistant", "content": full_response})
        _sessions[self.session_id] = history
