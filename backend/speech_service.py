"""
====================================================================
SEVA SETU BOT - SPEECH-TO-TEXT SERVICE
====================================================================
Transcribes audio using OpenAI Whisper.
pydub/pyaudioop removed — incompatible with Python 3.13.
Audio is passed directly to Whisper, which accepts webm/mp4/ogg/wav.
====================================================================
"""

from emergentintegrations.llm.openai import OpenAISpeechToText
import os
import tempfile
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SUPPORTED_STT_LANGUAGES = {
    "en": "en", "hi": "hi", "bn": "bn", "te": "te", "mr": "mr",
    "ta": "ta", "gu": "gu", "kn": "kn", "ml": "ml", "or": "or",
    "pa": "pa", "as": "as", "ur": "ur", "ne": "ne", "sa": "sa",
    "af": "af", "zu": "zu", "xh": "xh", "st": "st", "tn": "tn",
}

CONFIDENCE_THRESHOLD = 0.7


class EnhancedSpeechService:
    def __init__(self):
        self.api_key = os.getenv("EMERGENT_LLM_KEY")
        self.stt = OpenAISpeechToText(api_key=self.api_key)

    def _get_iso_language(self, language: str) -> str:
        return SUPPORTED_STT_LANGUAGES.get(language, "en")

    def _estimate_confidence(self, transcription: str) -> float:
        if not transcription:
            return 0.5
        confidence = 1.0
        words = transcription.split()
        if len(transcription) < 10:
            confidence -= 0.2
        if len(words) > 3:
            unique_ratio = len(set(w.lower() for w in words)) / len(words)
            if unique_ratio < 0.3:
                confidence -= 0.3
        return max(0.1, min(1.0, confidence))

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        language: str = "en",
        filename: str = "recording.webm",
        normalize: bool = True,
        chunk_long_audio: bool = True,
    ) -> dict:
        """Send audio bytes directly to Whisper for transcription."""
        try:
            iso_lang = self._get_iso_language(language)

            # Determine file suffix from filename so Whisper picks the right decoder
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
            # Whisper accepts: mp3, mp4, m4a, wav, webm, ogg, flac
            if ext not in {"mp3", "mp4", "m4a", "wav", "webm", "ogg", "flac"}:
                ext = "webm"

            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                with open(tmp_path, "rb") as audio_file:
                    response = await self.stt.transcribe(
                        file=audio_file,
                        model="whisper-1",
                        response_format="json",
                        language=iso_lang,
                        temperature=0.0,
                    )
                text = (response.text if hasattr(response, "text") else str(response)).strip()
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            confidence = self._estimate_confidence(text)
            needs_confirmation = confidence < CONFIDENCE_THRESHOLD
            logger.info(f"[SPEECH] Transcribed {len(text)} chars, confidence {confidence:.2f}")

            return {
                "success": True,
                "transcription": text,
                "language": language,
                "detected_language": iso_lang,
                "confidence": round(confidence, 2),
                "needs_confirmation": needs_confirmation,
                "chunks_processed": 1,
                "total_duration_ms": 0,
                "confirmation_message": (
                    f'I\'m not entirely sure I heard that correctly. Did you say: "{text[:100]}..."?'
                    if needs_confirmation else None
                ),
            }

        except Exception as e:
            logger.error(f"[SPEECH] Transcription error: {e}")
            return {
                "success": False,
                "error": str(e),
                "transcription": None,
                "confidence": 0.0,
                "needs_confirmation": True,
            }

    async def transcribe_with_timestamps(
        self,
        audio_bytes: bytes,
        language: str = "en",
        filename: str = "recording.webm",
    ) -> dict:
        try:
            iso_lang = self._get_iso_language(language)
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"
            if ext not in {"mp3", "mp4", "m4a", "wav", "webm", "ogg", "flac"}:
                ext = "webm"

            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                with open(tmp_path, "rb") as audio_file:
                    response = await self.stt.transcribe(
                        file=audio_file,
                        model="whisper-1",
                        response_format="verbose_json",
                        language=iso_lang,
                        temperature=0.0,
                        timestamp_granularities=["segment"],
                    )
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            result = {
                "success": True,
                "transcription": (response.text if hasattr(response, "text") else str(response)),
                "language": language,
                "segments": [],
            }
            if hasattr(response, "segments"):
                for seg in response.segments:
                    result["segments"].append({"start": seg.start, "end": seg.end, "text": seg.text})
            return result

        except Exception as e:
            logger.error(f"[SPEECH] Verbose transcription error: {e}")
            return {"success": False, "error": str(e), "transcription": None}


speech_service = EnhancedSpeechService()
