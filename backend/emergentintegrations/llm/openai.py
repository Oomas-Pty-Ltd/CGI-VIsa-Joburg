"""
Local shim for emergentintegrations.llm.openai
Wraps OpenAI TTS and STT APIs.
"""
import openai
import base64
import logging
from typing import Any

logger = logging.getLogger(__name__)


class OpenAISpeechToText:
    def __init__(self, api_key: str):
        import os
        if api_key and api_key.startswith("sk-emergent"):
            api_key = os.environ.get("OPENAI_API_KEY") or api_key
        self.api_key = api_key

    async def transcribe(self, file: Any, model: str = "whisper-1", **kwargs) -> Any:
        client = openai.AsyncOpenAI(api_key=self.api_key)
        response = await client.audio.transcriptions.create(
            model=model,
            file=file,
            **kwargs
        )
        return response


class OpenAITextToSpeech:
    def __init__(self, api_key: str):
        import os
        if api_key and api_key.startswith("sk-emergent"):
            api_key = os.environ.get("OPENAI_API_KEY") or api_key
        self.api_key = api_key

    async def generate_speech_base64(
        self,
        text: str,
        model: str = "tts-1",
        voice: str = "nova",
        speed: float = 1.0,
        instructions: str = None
    ) -> str:
        client = openai.AsyncOpenAI(api_key=self.api_key)
        kwargs = dict(model=model, voice=voice, input=text, speed=speed)
        if instructions:
            kwargs["instructions"] = instructions
        response = await client.audio.speech.create(**kwargs)
        audio_bytes = response.content
        return base64.b64encode(audio_bytes).decode("utf-8")
