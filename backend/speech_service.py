"""
Speech-to-Text Service using OpenAI Whisper
Supports multi-language transcription for consular services
"""
from emergentintegrations.llm.openai import OpenAISpeechToText
import os
import io
import tempfile
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)


class SpeechService:
    def __init__(self):
        self.api_key = os.getenv('EMERGENT_LLM_KEY')
        self.stt = OpenAISpeechToText(api_key=self.api_key)
        
        # Language code mapping for Whisper (ISO-639-1)
        self.language_map = {
            "en": "en",      # English
            "hi": "hi",      # Hindi
            "ta": "ta",      # Tamil
            "zu": "zu",      # Zulu
            "af": "af",      # Afrikaans
        }
    
    async def transcribe_audio(
        self, 
        audio_bytes: bytes, 
        language: str = "en",
        filename: str = "recording.webm"
    ) -> dict:
        """
        Transcribe audio bytes to text using Whisper
        
        Args:
            audio_bytes: Raw audio data (webm, mp3, wav, etc.)
            language: Language code (en, hi, ta, zu, af)
            filename: Original filename with extension
            
        Returns:
            dict with transcription result
        """
        try:
            # Get ISO language code
            iso_lang = self.language_map.get(language, "en")
            
            # Create a temporary file with the audio data
            suffix = f".{filename.split('.')[-1]}" if '.' in filename else ".webm"
            
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            
            try:
                # Open the temp file and transcribe
                with open(temp_file_path, "rb") as audio_file:
                    response = await self.stt.transcribe(
                        file=audio_file,
                        model="whisper-1",
                        response_format="json",
                        language=iso_lang,
                        temperature=0.0
                    )
                
                transcription = response.text if hasattr(response, 'text') else str(response)
                
                logger.info(f"[SPEECH] Transcribed audio in {language}: {transcription[:100]}...")
                
                return {
                    "success": True,
                    "transcription": transcription,
                    "language": language,
                    "detected_language": iso_lang
                }
                
            finally:
                # Clean up temp file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"[SPEECH] Transcription error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "transcription": None
            }
    
    async def transcribe_with_timestamps(
        self,
        audio_bytes: bytes,
        language: str = "en",
        filename: str = "recording.webm"
    ) -> dict:
        """
        Transcribe audio with detailed timestamps (verbose mode)
        """
        try:
            iso_lang = self.language_map.get(language, "en")
            suffix = f".{filename.split('.')[-1]}" if '.' in filename else ".webm"
            
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            
            try:
                with open(temp_file_path, "rb") as audio_file:
                    response = await self.stt.transcribe(
                        file=audio_file,
                        model="whisper-1",
                        response_format="verbose_json",
                        language=iso_lang,
                        temperature=0.0,
                        timestamp_granularities=["segment"]
                    )
                
                result = {
                    "success": True,
                    "transcription": response.text if hasattr(response, 'text') else str(response),
                    "language": language,
                    "segments": []
                }
                
                # Extract segments if available
                if hasattr(response, 'segments'):
                    for segment in response.segments:
                        result["segments"].append({
                            "start": segment.start,
                            "end": segment.end,
                            "text": segment.text
                        })
                
                return result
                
            finally:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"[SPEECH] Verbose transcription error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "transcription": None
            }


# Singleton instance
speech_service = SpeechService()
