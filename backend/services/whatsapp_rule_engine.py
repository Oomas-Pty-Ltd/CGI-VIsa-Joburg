"""
====================================================================
SEVA SETU BOT - WHATSAPP RULE ENGINE
====================================================================
Implements intelligent message routing:
- Emergency keyword detection
- Session context management
- Media message handling
- Conversation history for GPT context
====================================================================
"""

import re
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
from pydantic import BaseModel
import hashlib

logger = logging.getLogger(__name__)


class MessagePriority(str, Enum):
    EMERGENCY = "emergency"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class RuleAction(str, Enum):
    EMERGENCY_RESPONSE = "emergency_response"
    ESCALATE = "escalate"
    FORWARD_TO_AI = "forward_to_ai"
    TEMPLATE_RESPONSE = "template_response"
    MEDIA_PROCESSING = "media_processing"
    BLOCKED = "blocked"


# Emergency keywords in multiple languages
EMERGENCY_KEYWORDS = {
    "en": ["emergency", "urgent", "lost passport", "stolen", "help", "accident", 
           "hospital", "police", "arrest", "detained", "missing", "death", "die", "dying"],
    "hi": ["आपातकाल", "तत्काल", "खो गया", "चोरी", "मदद", "दुर्घटना", 
           "अस्पताल", "पुलिस", "गिरफ्तार", "लापता", "मृत्यु"],
    "af": ["nood", "dringend", "verlore", "gesteel", "help", "ongeluk",
           "hospitaal", "polisie", "aangehou", "vermis", "dood"],
    "zu": ["isimo esiphuthumayo", "okuphuthumayo", "ilahlekile", "yebiwe", "usizo",
           "ingozi", "isibhedlela", "amaphoyisa", "baboshiwe", "nyamalele", "ukufa"]
}

# Blocked patterns (spam, abuse)
BLOCKED_PATTERNS = [
    r"(?i)click here.*win",
    r"(?i)free.*prize",
    r"(?i)call now.*\d{10}",
    r"(?i)nigerian.*prince",
    r"(?i)congratulations.*won"
]


class WhatsAppSession(BaseModel):
    phone_hash: str  # Hashed phone number for privacy
    session_id: str
    messages: List[Dict[str, Any]] = []
    last_message_at: str
    context: Dict[str, Any] = {}  # Conversation context
    language: str = "en"
    escalated: bool = False
    created_at: str


class RuleEngineResult(BaseModel):
    action: RuleAction
    priority: MessagePriority
    response: Optional[str] = None
    metadata: Dict[str, Any] = {}
    should_store: bool = True
    forward_to_ai: bool = True


class WhatsAppRuleEngine:
    def __init__(self):
        self.emergency_contact = "+27 6830 38144"
        self.emergency_email = "cons.joburg@mea.gov.in"
        
        # Compile blocked patterns for efficiency
        self.blocked_patterns = [re.compile(p) for p in BLOCKED_PATTERNS]
    
    def _hash_phone(self, phone: str) -> str:
        """Hash phone number for privacy"""
        return hashlib.sha256(phone.encode()).hexdigest()[:16]
    
    def _detect_language(self, text: str) -> str:
        """Simple language detection based on character sets"""
        # Hindi (Devanagari)
        if re.search(r'[\u0900-\u097F]', text):
            return "hi"
        # Zulu/Afrikaans detection is harder - default to English
        return "en"
    
    def _check_emergency(self, text: str) -> Tuple[bool, str]:
        """Check if message contains emergency keywords"""
        text_lower = text.lower()
        
        for lang, keywords in EMERGENCY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    return True, keyword
        
        return False, ""
    
    def _check_blocked(self, text: str) -> bool:
        """Check if message matches blocked patterns"""
        for pattern in self.blocked_patterns:
            if pattern.search(text):
                logger.warning(f"[WHATSAPP] Blocked spam message matching pattern")
                return True
        return False
    
    def _generate_emergency_response(self, language: str = "en") -> str:
        """Generate emergency response in appropriate language"""
        responses = {
            "en": f"""🚨 **EMERGENCY ASSISTANCE**

Your message has been flagged as urgent. Please contact us immediately:

📞 **24/7 Emergency Hotline:** {self.emergency_contact}
📧 **Email:** {self.emergency_email}

**For immediate assistance:**
• Lost/Stolen Passport: Call the hotline immediately
• Medical Emergency: Contact local emergency services (10111) and then call us
• Arrest/Detention: Call the hotline - we will assist with consular access
• Death of Indian National: Call the hotline for repatriation assistance

🏢 **Walk-in Hours:** Mon-Fri, 9:00 AM - 5:30 PM
📍 **Address:** 12 Autumn Street, Rivonia, Sandton

A consular officer will respond to your case within 2 hours.""",

            "hi": f"""🚨 **आपातकालीन सहायता**

आपका संदेश तत्काल के रूप में चिह्नित किया गया है। कृपया तुरंत संपर्क करें:

📞 **24/7 आपातकालीन हॉटलाइन:** {self.emergency_contact}
📧 **ईमेल:** {self.emergency_email}

एक कांसुलर अधिकारी 2 घंटे के भीतर आपके मामले का जवाब देगा।""",

            "af": f"""🚨 **NOODHULP**

U boodskap is as dringend gemerk. Kontak ons asseblief onmiddellik:

📞 **24/7 Noodlyn:** {self.emergency_contact}
📧 **E-pos:** {self.emergency_email}

'n Konsulêre beampte sal binne 2 uur op u saak reageer."""
        }
        
        return responses.get(language, responses["en"])
    
    async def process_message(
        self,
        db,
        phone: str,
        message: str,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None
    ) -> RuleEngineResult:
        """
        Process incoming WhatsApp message through rule engine.
        
        Returns action to take and optional immediate response.
        """
        
        phone_hash = self._hash_phone(phone)
        detected_lang = self._detect_language(message)
        
        # Rule 1: Check for blocked content
        if self._check_blocked(message):
            return RuleEngineResult(
                action=RuleAction.BLOCKED,
                priority=MessagePriority.LOW,
                response="This message has been blocked.",
                should_store=False,
                forward_to_ai=False
            )
        
        # Rule 2: Check for emergency keywords
        is_emergency, trigger_keyword = self._check_emergency(message)
        if is_emergency:
            logger.info(f"[WHATSAPP] Emergency detected: {trigger_keyword}")
            
            # Store emergency flag in session
            await self._update_session_context(db, phone_hash, {
                "emergency_triggered": True,
                "emergency_keyword": trigger_keyword,
                "emergency_time": datetime.now(timezone.utc).isoformat()
            })
            
            return RuleEngineResult(
                action=RuleAction.EMERGENCY_RESPONSE,
                priority=MessagePriority.EMERGENCY,
                response=self._generate_emergency_response(detected_lang),
                metadata={
                    "trigger_keyword": trigger_keyword,
                    "language": detected_lang
                },
                should_store=True,
                forward_to_ai=False  # Don't forward - emergency response is immediate
            )
        
        # Rule 3: Check for media message
        if media_url:
            return RuleEngineResult(
                action=RuleAction.MEDIA_PROCESSING,
                priority=MessagePriority.NORMAL,
                metadata={
                    "media_url": media_url,
                    "media_type": media_type,
                    "language": detected_lang
                },
                should_store=True,
                forward_to_ai=True
            )
        
        # Rule 4: Default - forward to AI
        return RuleEngineResult(
            action=RuleAction.FORWARD_TO_AI,
            priority=MessagePriority.NORMAL,
            metadata={"language": detected_lang},
            should_store=True,
            forward_to_ai=True
        )
    
    async def get_or_create_session(
        self,
        db,
        phone: str
    ) -> WhatsAppSession:
        """Get or create WhatsApp session"""
        phone_hash = self._hash_phone(phone)
        now = datetime.now(timezone.utc).isoformat()
        
        session = await db.whatsapp_sessions.find_one(
            {"phone_hash": phone_hash},
            {"_id": 0}
        )
        
        if session:
            # Update last message time
            await db.whatsapp_sessions.update_one(
                {"phone_hash": phone_hash},
                {"$set": {"last_message_at": now}}
            )
            return WhatsAppSession(**session)
        
        # Create new session
        new_session = WhatsAppSession(
            phone_hash=phone_hash,
            session_id=f"wa_{phone_hash}_{now.replace(':', '').replace('-', '')}",
            messages=[],
            last_message_at=now,
            created_at=now
        )
        
        await db.whatsapp_sessions.insert_one(new_session.model_dump())
        
        return new_session
    
    async def add_message_to_session(
        self,
        db,
        phone: str,
        role: str,  # "user" or "assistant"
        content: str,
        metadata: Dict[str, Any] = None
    ):
        """Add message to session history"""
        phone_hash = self._hash_phone(phone)
        now = datetime.now(timezone.utc).isoformat()
        
        message = {
            "role": role,
            "content": content,
            "timestamp": now,
            "metadata": metadata or {}
        }
        
        # Keep only last 20 messages (10 exchanges)
        await db.whatsapp_sessions.update_one(
            {"phone_hash": phone_hash},
            {
                "$push": {
                    "messages": {
                        "$each": [message],
                        "$slice": -20  # Keep last 20
                    }
                },
                "$set": {"last_message_at": now}
            }
        )
    
    async def get_conversation_context(
        self,
        db,
        phone: str,
        last_n: int = 5
    ) -> List[Dict[str, Any]]:
        """Get last N messages for GPT context"""
        phone_hash = self._hash_phone(phone)
        
        session = await db.whatsapp_sessions.find_one(
            {"phone_hash": phone_hash},
            {"_id": 0, "messages": 1}
        )
        
        if not session or not session.get('messages'):
            return []
        
        return session['messages'][-last_n:]
    
    async def _update_session_context(
        self,
        db,
        phone_hash: str,
        context_updates: Dict[str, Any]
    ):
        """Update session context"""
        await db.whatsapp_sessions.update_one(
            {"phone_hash": phone_hash},
            {"$set": {f"context.{k}": v for k, v in context_updates.items()}}
        )
    
    def format_context_for_gpt(
        self,
        messages: List[Dict[str, Any]]
    ) -> str:
        """Format conversation history for GPT prompt"""
        if not messages:
            return "No previous conversation."
        
        formatted = "Previous conversation:\n"
        for msg in messages:
            role = "User" if msg['role'] == 'user' else "Assistant"
            formatted += f"{role}: {msg['content']}\n"
        
        return formatted


# Singleton instance
whatsapp_rule_engine = WhatsAppRuleEngine()
