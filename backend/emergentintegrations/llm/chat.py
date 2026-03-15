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
    def __init__(self, api_key: str, session_id: str, system_message: str = ""):
        import os
        # If an emergent-platform key is passed, fall back to real OpenAI key
        if api_key and api_key.startswith("sk-emergent"):
            api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY", api_key)
        self.api_key = api_key
        self.session_id = session_id
        self.system_message = system_message
        self.model = "gpt-4o-mini"
        if session_id not in _sessions:
            _sessions[session_id] = []

    def with_model(self, provider: str, model: str) -> "LlmChat":
        self.model = MODEL_MAP.get(model, model)
        return self

    async def send_message(self, message: UserMessage) -> str:
        client = openai.AsyncOpenAI(api_key=self.api_key)
        history = _sessions.get(self.session_id, [])

        # Build message content (text + optional images)
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

        user_msg = {"role": "user", "content": content}
        history.append(user_msg)

        messages = []
        if self.system_message:
            messages.append({"role": "system", "content": self.system_message})
        messages.extend(history)

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            assistant_text = response.choices[0].message.content
        except Exception as e:
            logger.error(f"[LlmChat] API error: {e}")
            raise

        history.append({"role": "assistant", "content": assistant_text})
        _sessions[self.session_id] = history
        return assistant_text
