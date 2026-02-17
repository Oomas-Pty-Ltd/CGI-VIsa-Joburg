"""
====================================================================
SEVA SETU BOT - ENHANCED VOICE SERVICE
====================================================================
Text-to-Speech with:
- Extended language support (22 Indian + 11 South African languages)
- Dynamic voice selection
- Number/currency spoken format conversion
- Audio chunk management
====================================================================
"""

from emergentintegrations.llm.openai import OpenAITextToSpeech
import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


# Extended language support
# 22 Indian official languages + 11 South African official languages
SUPPORTED_LANGUAGES = {
    # Indian Languages (ISO 639-1 codes where available)
    "en": {"name": "English", "voice": "nova", "region": "both"},
    "hi": {"name": "Hindi", "voice": "shimmer", "region": "india"},
    "bn": {"name": "Bengali", "voice": "shimmer", "region": "india"},
    "te": {"name": "Telugu", "voice": "shimmer", "region": "india"},
    "mr": {"name": "Marathi", "voice": "shimmer", "region": "india"},
    "ta": {"name": "Tamil", "voice": "shimmer", "region": "india"},
    "gu": {"name": "Gujarati", "voice": "shimmer", "region": "india"},
    "kn": {"name": "Kannada", "voice": "shimmer", "region": "india"},
    "ml": {"name": "Malayalam", "voice": "shimmer", "region": "india"},
    "or": {"name": "Odia", "voice": "shimmer", "region": "india"},
    "pa": {"name": "Punjabi", "voice": "shimmer", "region": "india"},
    "as": {"name": "Assamese", "voice": "shimmer", "region": "india"},
    "mai": {"name": "Maithili", "voice": "shimmer", "region": "india"},
    "sa": {"name": "Sanskrit", "voice": "shimmer", "region": "india"},
    "ks": {"name": "Kashmiri", "voice": "shimmer", "region": "india"},
    "ne": {"name": "Nepali", "voice": "shimmer", "region": "india"},
    "sd": {"name": "Sindhi", "voice": "shimmer", "region": "india"},
    "kok": {"name": "Konkani", "voice": "shimmer", "region": "india"},
    "doi": {"name": "Dogri", "voice": "shimmer", "region": "india"},
    "mni": {"name": "Manipuri", "voice": "shimmer", "region": "india"},
    "sat": {"name": "Santali", "voice": "shimmer", "region": "india"},
    "bo": {"name": "Bodo", "voice": "shimmer", "region": "india"},
    "ur": {"name": "Urdu", "voice": "shimmer", "region": "india"},
    
    # South African Languages (11 official)
    "af": {"name": "Afrikaans", "voice": "alloy", "region": "south_africa"},
    "zu": {"name": "Zulu", "voice": "coral", "region": "south_africa"},
    "xh": {"name": "Xhosa", "voice": "coral", "region": "south_africa"},
    "st": {"name": "Sotho", "voice": "coral", "region": "south_africa"},
    "nso": {"name": "Northern Sotho (Sepedi)", "voice": "coral", "region": "south_africa"},
    "tn": {"name": "Tswana", "voice": "coral", "region": "south_africa"},
    "ts": {"name": "Tsonga", "voice": "coral", "region": "south_africa"},
    "ss": {"name": "Swati", "voice": "coral", "region": "south_africa"},
    "ve": {"name": "Venda", "voice": "coral", "region": "south_africa"},
    "nr": {"name": "Ndebele", "voice": "coral", "region": "south_africa"},
}

# Currency formatting for TTS
CURRENCY_WORDS = {
    "INR": {"symbol": "₹", "singular": "rupee", "plural": "rupees", "subunit": "paise"},
    "ZAR": {"symbol": "R", "singular": "rand", "plural": "rand", "subunit": "cents"},
    "USD": {"symbol": "$", "singular": "dollar", "plural": "dollars", "subunit": "cents"},
}


class EnhancedVoiceService:
    def __init__(self):
        self.api_key = os.getenv('EMERGENT_LLM_KEY')
        self.tts = OpenAITextToSpeech(api_key=self.api_key)
        self.max_chunk_size = 4000  # Characters per chunk
    
    def get_voice_for_language(self, language: str) -> str:
        """Get appropriate TTS voice for language"""
        lang_config = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES.get("en"))
        return lang_config.get("voice", "nova")
    
    def get_supported_languages(self, region: str = None) -> dict:
        """Get list of supported languages, optionally filtered by region"""
        if region:
            return {k: v for k, v in SUPPORTED_LANGUAGES.items() 
                   if v.get("region") in [region, "both"]}
        return SUPPORTED_LANGUAGES
    
    def convert_numbers_to_spoken(self, text: str, language: str = "en") -> str:
        """Convert numbers and currencies to spoken format"""
        
        # Convert currency amounts (₹1,234.56 → "one thousand two hundred thirty four rupees and fifty six paise")
        def currency_to_words(match):
            symbol = match.group(1)
            amount = match.group(2).replace(',', '')
            
            # Find currency by symbol
            currency = None
            for code, info in CURRENCY_WORDS.items():
                if info["symbol"] == symbol:
                    currency = info
                    break
            
            if not currency:
                return match.group(0)
            
            try:
                if '.' in amount:
                    main, decimal = amount.split('.')
                    main = int(main)
                    decimal = int(decimal)
                    
                    main_word = self._number_to_words(main)
                    unit = currency["singular"] if main == 1 else currency["plural"]
                    
                    if decimal > 0:
                        decimal_word = self._number_to_words(decimal)
                        return f"{main_word} {unit} and {decimal_word} {currency['subunit']}"
                    return f"{main_word} {unit}"
                else:
                    num = int(amount)
                    word = self._number_to_words(num)
                    unit = currency["singular"] if num == 1 else currency["plural"]
                    return f"{word} {unit}"
            except:
                return match.group(0)
        
        # Pattern for currency amounts
        currency_pattern = r'([₹$R])([0-9,]+\.?[0-9]*)'
        text = re.sub(currency_pattern, currency_to_words, text)
        
        # Convert standalone large numbers (avoid dates, phone numbers)
        def number_to_words_match(match):
            num_str = match.group(0).replace(',', '')
            try:
                num = int(num_str)
                if num > 999:  # Only convert large numbers
                    return self._number_to_words(num)
            except:
                pass
            return match.group(0)
        
        # Pattern for standalone numbers (not in dates or phone patterns)
        number_pattern = r'(?<![/-])\b([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})\b(?![/-])'
        text = re.sub(number_pattern, number_to_words_match, text)
        
        return text
    
    def _number_to_words(self, num: int) -> str:
        """Convert number to words (simplified)"""
        if num == 0:
            return "zero"
        
        ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
                "seventeen", "eighteen", "nineteen"]
        tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
        
        def helper(n):
            if n < 20:
                return ones[n]
            elif n < 100:
                return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")
            elif n < 1000:
                return ones[n // 100] + " hundred" + (" " + helper(n % 100) if n % 100 else "")
            elif n < 100000:  # Indian numbering: thousand
                return helper(n // 1000) + " thousand" + (" " + helper(n % 1000) if n % 1000 else "")
            elif n < 10000000:  # Indian numbering: lakh
                return helper(n // 100000) + " lakh" + (" " + helper(n % 100000) if n % 100000 else "")
            else:  # Indian numbering: crore
                return helper(n // 10000000) + " crore" + (" " + helper(n % 10000000) if n % 10000000 else "")
        
        return helper(num)
    
    async def text_to_speech(self, text: str, language: str = "en", convert_numbers: bool = True) -> str:
        """Convert text to speech and return base64 audio"""
        
        # Convert numbers/currency if enabled
        if convert_numbers:
            text = self.convert_numbers_to_spoken(text, language)
        
        # Get voice for language
        voice = self.get_voice_for_language(language)
        
        try:
            audio_base64 = await self.tts.generate_speech_base64(
                text=text,
                model="tts-1-hd",
                voice=voice,
                speed=1.0
            )
            
            logger.info(f"[TTS] Generated speech for {len(text)} chars in {language} using voice {voice}")
            return audio_base64
            
        except Exception as e:
            logger.error(f"[TTS] Error: {e}")
            return None
    
    async def generate_speech_chunks(
        self, 
        text: str, 
        language: str = "en", 
        chunk_size: int = None
    ) -> list:
        """Split long text into chunks and generate speech for each"""
        chunk_size = chunk_size or self.max_chunk_size
        
        # Smart chunking - try to split at sentence boundaries
        chunks = self._smart_chunk(text, chunk_size)
        audio_chunks = []
        
        for i, chunk in enumerate(chunks):
            audio = await self.text_to_speech(chunk, language)
            if audio:
                audio_chunks.append({
                    "index": i,
                    "text_length": len(chunk),
                    "audio_base64": audio
                })
                logger.info(f"[TTS] Generated chunk {i+1}/{len(chunks)}")
        
        return audio_chunks
    
    def _smart_chunk(self, text: str, max_size: int) -> list:
        """Split text at sentence boundaries"""
        if len(text) <= max_size:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= max_size:
                current_chunk += " " + sentence if current_chunk else sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # If single sentence is too long, split by words
                if len(sentence) > max_size:
                    words = sentence.split()
                    current_chunk = ""
                    for word in words:
                        if len(current_chunk) + len(word) + 1 <= max_size:
                            current_chunk += " " + word if current_chunk else word
                        else:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = word
                else:
                    current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def detect_language(self, text: str) -> str:
        """Simple language detection based on script"""
        # Devanagari (Hindi, Marathi, Sanskrit, Nepali)
        if re.search(r'[\u0900-\u097F]', text):
            return "hi"
        # Bengali
        if re.search(r'[\u0980-\u09FF]', text):
            return "bn"
        # Telugu
        if re.search(r'[\u0C00-\u0C7F]', text):
            return "te"
        # Tamil
        if re.search(r'[\u0B80-\u0BFF]', text):
            return "ta"
        # Gujarati
        if re.search(r'[\u0A80-\u0AFF]', text):
            return "gu"
        # Kannada
        if re.search(r'[\u0C80-\u0CFF]', text):
            return "kn"
        # Malayalam
        if re.search(r'[\u0D00-\u0D7F]', text):
            return "ml"
        # Odia
        if re.search(r'[\u0B00-\u0B7F]', text):
            return "or"
        # Punjabi (Gurmukhi)
        if re.search(r'[\u0A00-\u0A7F]', text):
            return "pa"
        # Urdu/Arabic script
        if re.search(r'[\u0600-\u06FF]', text):
            return "ur"
        
        # Default to English
        return "en"


# Create singleton instance (replaces old voice_service)
voice_service = EnhancedVoiceService()
