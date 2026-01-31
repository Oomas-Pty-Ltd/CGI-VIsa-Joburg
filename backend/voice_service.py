from emergentintegrations.llm.openai import OpenAITextToSpeech
import os
from dotenv import load_dotenv
import base64

load_dotenv()

class VoiceService:
    def __init__(self):
        self.api_key = os.getenv('EMERGENT_LLM_KEY')
        self.tts = OpenAITextToSpeech(api_key=self.api_key)
    
    async def text_to_speech(self, text: str, language: str = "en") -> str:
        """Convert text to speech and return base64 audio"""
        
        # Select voice based on language
        voice_map = {
            "en": "nova",      # Energetic for English
            "hi": "shimmer",   # Bright for Hindi
            "af": "alloy",     # Neutral for Afrikaans
            "zu": "coral",     # Warm for Zulu
            "default": "nova"
        }
        
        voice = voice_map.get(language, voice_map["default"])
        
        try:
            # Generate speech with high quality model
            audio_base64 = await self.tts.generate_speech_base64(
                text=text,
                model="tts-1-hd",  # High quality for professional consular service
                voice=voice,
                speed=1.0
            )
            
            return audio_base64
            
        except Exception as e:
            print(f"TTS Error: {e}")
            return None
    
    async def generate_speech_chunks(self, text: str, language: str = "en", chunk_size: int = 4000):
        """Split long text into chunks and generate speech for each"""
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        audio_chunks = []
        
        for chunk in chunks:
            audio = await self.text_to_speech(chunk, language)
            if audio:
                audio_chunks.append(audio)
        
        return audio_chunks

voice_service = VoiceService()
