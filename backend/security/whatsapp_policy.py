"""
====================================================================
SEVA SETU BOT - WHATSAPP 24-HOUR POLICY MANAGER
====================================================================
Manages WhatsApp Business API 24-hour messaging window:
- Tracks last user interaction timestamp
- Auto-switches to templates when window expires
- Manages template message sending
====================================================================
"""

import os
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
from database import get_database

logger = logging.getLogger(__name__)

# =====================================================================
# CONFIGURATION
# =====================================================================
WHATSAPP_POLICY_CONFIG = {
    # WhatsApp Business API 24-hour window
    "conversation_window_hours": 24,
    
    # Grace period before window expires (send reminder)
    "reminder_before_expiry_hours": 2,
    
    # Default template to use when window expires
    "default_template_sid": os.environ.get('WHATSAPP_DEFAULT_TEMPLATE', 'HX123...'),
    
    # Template categories
    "template_categories": {
        "session_expiry": "Your session is about to expire. Reply to continue our conversation.",
        "welcome_back": "Welcome back! How can I help you with consular services today?",
        "appointment_reminder": "Reminder: You have an upcoming appointment.",
        "document_ready": "Your documents are ready for collection."
    }
}


class WhatsAppPolicyManager:
    """
    Manages WhatsApp Business API 24-hour messaging window compliance.
    
    WhatsApp Policy:
    - Businesses can send any message within 24h of user's last message
    - After 24h, only approved template messages can be sent
    - User must initiate conversation to re-open the window
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or WHATSAPP_POLICY_CONFIG
        self.window_hours = self.config['conversation_window_hours']
    
    async def get_user_interaction(self, phone_number: str) -> Optional[Dict]:
        """Get user's last interaction data"""
        db = await get_database()
        
        user = await db.whatsapp_users.find_one(
            {"phone_number": phone_number},
            {"_id": 0, "phone_number": 1, "last_interaction": 1, "profile_name": 1}
        )
        
        return user
    
    async def update_interaction(self, phone_number: str, profile_name: str = None):
        """Update user's last interaction timestamp"""
        db = await get_database()
        
        update_data = {
            "last_interaction": datetime.now(timezone.utc).isoformat(),
            "interaction_count": {"$inc": 1}
        }
        
        if profile_name:
            update_data["profile_name"] = profile_name
        
        await db.whatsapp_users.update_one(
            {"phone_number": phone_number},
            {
                "$set": {
                    "last_interaction": datetime.now(timezone.utc).isoformat(),
                    "profile_name": profile_name
                },
                "$inc": {"interaction_count": 1}
            },
            upsert=True
        )
    
    def is_window_open(self, last_interaction: str) -> Tuple[bool, int]:
        """
        Check if the 24-hour messaging window is still open.
        
        Returns:
            Tuple of (is_open, minutes_remaining)
        """
        if not last_interaction:
            return False, 0
        
        try:
            last_time = datetime.fromisoformat(last_interaction.replace('Z', '+00:00'))
            window_end = last_time + timedelta(hours=self.window_hours)
            now = datetime.now(timezone.utc)
            
            if now < window_end:
                remaining = (window_end - now).total_seconds() / 60
                return True, int(remaining)
            else:
                return False, 0
                
        except Exception as e:
            logger.error(f"Error parsing interaction timestamp: {e}")
            return False, 0
    
    def should_send_reminder(self, last_interaction: str) -> bool:
        """
        Check if we should send a reminder before window expires.
        """
        if not last_interaction:
            return False
        
        try:
            last_time = datetime.fromisoformat(last_interaction.replace('Z', '+00:00'))
            reminder_time = last_time + timedelta(
                hours=self.window_hours - self.config['reminder_before_expiry_hours']
            )
            
            return datetime.now(timezone.utc) >= reminder_time
            
        except Exception:
            return False
    
    async def check_and_get_message_type(
        self, 
        phone_number: str
    ) -> Dict:
        """
        Check window status and determine message type.
        
        Returns:
            {
                "can_send_freeform": bool,
                "window_open": bool,
                "minutes_remaining": int,
                "use_template": bool,
                "suggested_template": str | None,
                "reminder_needed": bool
            }
        """
        user = await self.get_user_interaction(phone_number)
        
        if not user or not user.get('last_interaction'):
            # New user or no interaction record
            return {
                "can_send_freeform": False,
                "window_open": False,
                "minutes_remaining": 0,
                "use_template": True,
                "suggested_template": "welcome_back",
                "reminder_needed": False
            }
        
        last_interaction = user['last_interaction']
        window_open, minutes_remaining = self.is_window_open(last_interaction)
        
        result = {
            "can_send_freeform": window_open,
            "window_open": window_open,
            "minutes_remaining": minutes_remaining,
            "use_template": not window_open,
            "suggested_template": None if window_open else "welcome_back",
            "reminder_needed": self.should_send_reminder(last_interaction) if window_open else False
        }
        
        # Log window status
        if window_open:
            logger.debug(f"WhatsApp window OPEN for {phone_number}: {minutes_remaining} min remaining")
        else:
            logger.info(f"WhatsApp window CLOSED for {phone_number}: Template required")
        
        return result
    
    def get_template_message(self, template_key: str, variables: Dict = None) -> str:
        """
        Get template message content.
        For Twilio, this would typically be a template SID.
        """
        template = self.config['template_categories'].get(template_key)
        
        if not template:
            template = self.config['template_categories']['welcome_back']
        
        # Substitute variables if provided
        if variables:
            try:
                template = template.format(**variables)
            except KeyError:
                pass
        
        return template
    
    async def get_window_status_for_numbers(
        self, 
        phone_numbers: list
    ) -> Dict[str, Dict]:
        """
        Batch check window status for multiple phone numbers.
        Useful for bulk messaging campaigns.
        """
        db = await get_database()
        
        users = await db.whatsapp_users.find(
            {"phone_number": {"$in": phone_numbers}},
            {"_id": 0, "phone_number": 1, "last_interaction": 1}
        ).to_list(len(phone_numbers))
        
        # Create lookup dict
        user_map = {u['phone_number']: u.get('last_interaction') for u in users}
        
        results = {}
        for phone in phone_numbers:
            last_interaction = user_map.get(phone)
            if last_interaction:
                window_open, minutes_remaining = self.is_window_open(last_interaction)
            else:
                window_open, minutes_remaining = False, 0
            
            results[phone] = {
                "window_open": window_open,
                "minutes_remaining": minutes_remaining,
                "use_template": not window_open
            }
        
        return results
    
    async def get_expiring_conversations(self, within_hours: int = 2) -> list:
        """
        Get conversations that will expire within specified hours.
        Useful for sending proactive reminders.
        """
        db = await get_database()
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.window_hours - within_hours)
        cutoff_str = cutoff.isoformat()
        
        expiring = await db.whatsapp_users.find(
            {
                "last_interaction": {
                    "$gte": cutoff_str,
                    "$lt": datetime.now(timezone.utc).isoformat()
                }
            },
            {"_id": 0, "phone_number": 1, "last_interaction": 1, "profile_name": 1}
        ).to_list(100)
        
        return expiring


# Global instance
whatsapp_policy = WhatsAppPolicyManager()
