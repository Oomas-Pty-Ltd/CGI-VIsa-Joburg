"""
====================================================================
SEVA SETU BOT - ENHANCED SPEECH-TO-TEXT SERVICE
====================================================================
Speech-to-Text using OpenAI Whisper with:
- Audio chunking for files >60 seconds
- Confidence scoring
- Extended language support (33 languages)
- Audio normalization support
====================================================================
"""

from emergentintegrations.llm.openai import OpenAISpeechToText
import os
import io
import tempfile
from dotenv import load_dotenv
import logging
from pydub import AudioSegment
import base64

load_dotenv()
logger = logging.getLogger(__name__)


# Extended language support matching voice_service
SUPPORTED_STT_LANGUAGES = {
    # Indian Languages
    "en": "en", "hi": "hi", "bn": "bn", "te": "te", "mr": "mr",
    "ta": "ta", "gu": "gu", "kn": "kn", "ml": "ml", "or": "or",
    "pa": "pa", "as": "as", "ur": "ur", "ne": "ne", "sa": "sa",
    # South African Languages  
    "af": "af", "zu": "zu", "xh": "xh", "st": "st", "tn": "tn",
}

# Confidence threshold for requesting user confirmation
CONFIDENCE_THRESHOLD = 0.7
MAX_CHUNK_DURATION_MS = 60000  # 60 seconds


class EnhancedSpeechService:
    def __init__(self):
        self.api_key = os.getenv('EMERGENT_LLM_KEY')
        self.stt = OpenAISpeechToText(api_key=self.api_key)
    
    def _get_iso_language(self, language: str) -> str:
        """Get ISO language code for Whisper"""
        return SUPPORTED_STT_LANGUAGES.get(language, "en")
    
    async def _chunk_audio(self, audio_bytes: bytes, filename: str) -> list:
        """
        Split audio into chunks if longer than 60 seconds.
        Returns list of (chunk_bytes, duration_ms) tuples.
        """
        try:
            # Determine format from filename
            ext = filename.split('.')[-1].lower() if '.' in filename else 'webm'
            
            # Load audio with pydub
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=ext)
            duration_ms = len(audio)
            
            logger.info(f"[SPEECH] Audio duration: {duration_ms/1000:.1f}s")
            
            # If short enough, return as single chunk
            if duration_ms <= MAX_CHUNK_DURATION_MS:
                return [(audio_bytes, duration_ms)]
            
            # Split into chunks
            chunks = []
            for i in range(0, duration_ms, MAX_CHUNK_DURATION_MS):
                chunk = audio[i:i + MAX_CHUNK_DURATION_MS]
                
                # Export chunk to bytes
                chunk_buffer = io.BytesIO()
                chunk.export(chunk_buffer, format='mp3')  # Use mp3 for better compatibility
                chunk_bytes = chunk_buffer.getvalue()
                
                chunks.append((chunk_bytes, len(chunk)))
                logger.info(f"[SPEECH] Created chunk {len(chunks)}: {len(chunk)/1000:.1f}s")
            
            return chunks
            
        except Exception as e:
            logger.warning(f"[SPEECH] Could not chunk audio: {e}, processing as single file")
            return [(audio_bytes, 0)]
    
    def _normalize_audio(self, audio_bytes: bytes, filename: str) -> bytes:
        """
        Normalize audio volume and convert to consistent format.
        """
        try:
            ext = filename.split('.')[-1].lower() if '.' in filename else 'webm'
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=ext)
            
            # Normalize volume
            target_dBFS = -20
            change_in_dBFS = target_dBFS - audio.dBFS
            normalized = audio.apply_gain(change_in_dBFS)
            
            # Convert to mp3 for consistent processing
            output_buffer = io.BytesIO()
            normalized.export(output_buffer, format='mp3', bitrate='128k')
            
            logger.info(f"[SPEECH] Audio normalized: {audio.dBFS:.1f}dBFS -> {normalized.dBFS:.1f}dBFS")
            return output_buffer.getvalue()
            
        except Exception as e:
            logger.warning(f"[SPEECH] Could not normalize audio: {e}")
            return audio_bytes
    
    def _estimate_confidence(self, transcription: str, audio_duration_ms: int) -> float:
        """
        Estimate transcription confidence based on heuristics.
        Note: Whisper doesn't provide confidence scores directly.
        """
        if not transcription or audio_duration_ms == 0:
            return 0.5
        
        # Heuristics for confidence estimation
        confidence = 1.0
        
        # Check for very short transcription relative to audio
        words = transcription.split()
        words_per_second = len(words) / (audio_duration_ms / 1000) if audio_duration_ms > 0 else 0
        
        # Normal speech is 2-3 words per second
        if words_per_second < 0.5:  # Suspiciously few words
            confidence -= 0.3
        elif words_per_second > 5:  # Suspiciously many words
            confidence -= 0.2
        
        # Check for repeated patterns (often indicates noise)
        if len(words) > 3:
            unique_words = set(w.lower() for w in words)
            uniqueness_ratio = len(unique_words) / len(words)
            if uniqueness_ratio < 0.3:  # Too repetitive
                confidence -= 0.3
        
        # Check for very short result
        if len(transcription) < 10:
            confidence -= 0.2
        
        return max(0.1, min(1.0, confidence))
    
    async def transcribe_audio(
        self, 
        audio_bytes: bytes, 
        language: str = "en",
        filename: str = "recording.webm",
        normalize: bool = True,
        chunk_long_audio: bool = True
    ) -> dict:
        """
        Transcribe audio bytes to text using Whisper.
        
        Args:
            audio_bytes: Raw audio data
            language: Language code
            filename: Original filename with extension
            normalize: Whether to normalize audio volume
            chunk_long_audio: Whether to split audio >60s into chunks
            
        Returns:
            dict with transcription, confidence, and metadata
        """
        try:
            iso_lang = self._get_iso_language(language)
            
            # Normalize audio if enabled
            if normalize:
                audio_bytes = self._normalize_audio(audio_bytes, filename)
                filename = "normalized.mp3"
            
            # Chunk audio if enabled and necessary
            if chunk_long_audio:
                chunks = await self._chunk_audio(audio_bytes, filename)
            else:
                chunks = [(audio_bytes, 0)]
            
            # Transcribe each chunk
            transcriptions = []
            total_duration_ms = 0
            
            for i, (chunk_bytes, duration_ms) in enumerate(chunks):
                # Create temp file for chunk
                suffix = ".mp3" if normalize else f".{filename.split('.')[-1]}"
                
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                    temp_file.write(chunk_bytes)
                    temp_file_path = temp_file.name
                
                try:
                    with open(temp_file_path, "rb") as audio_file:
                        response = await self.stt.transcribe(
                            file=audio_file,
                            model="whisper-1",
                            response_format="json",
                            language=iso_lang,
                            temperature=0.0
                        )
                    
                    chunk_text = response.text if hasattr(response, 'text') else str(response)
                    transcriptions.append(chunk_text)
                    total_duration_ms += duration_ms
                    
                    logger.info(f"[SPEECH] Chunk {i+1}/{len(chunks)} transcribed: {chunk_text[:50]}...")
                    
                finally:
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
            
            # Combine transcriptions
            full_transcription = " ".join(transcriptions).strip()
            
            # Estimate confidence
            confidence = self._estimate_confidence(full_transcription, total_duration_ms)
            needs_confirmation = confidence < CONFIDENCE_THRESHOLD
            
            logger.info(f"[SPEECH] Transcription complete: {len(full_transcription)} chars, confidence: {confidence:.2f}")
            
            return {
                "success": True,
                "transcription": full_transcription,
                "language": language,
                "detected_language": iso_lang,
                "confidence": round(confidence, 2),
                "needs_confirmation": needs_confirmation,
                "chunks_processed": len(chunks),
                "total_duration_ms": total_duration_ms,
                "confirmation_message": "I'm not entirely sure I heard that correctly. Did you say: " + 
                                       f'"{full_transcription[:100]}..."?' if needs_confirmation else None
            }
                
        except Exception as e:
            logger.error(f"[SPEECH] Transcription error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "transcription": None,
                "confidence": 0.0,
                "needs_confirmation": True
            }
    
    async def transcribe_with_timestamps(
        self,
        audio_bytes: bytes,
        language: str = "en",
        filename: str = "recording.webm"
    ) -> dict:
        """Transcribe audio with detailed timestamps"""
        try:
            iso_lang = self._get_iso_language(language)
            
            # Normalize audio
            audio_bytes = self._normalize_audio(audio_bytes, filename)
            
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
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
speech_service = EnhancedSpeechService()
