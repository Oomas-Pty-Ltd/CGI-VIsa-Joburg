"""
====================================================================
SEVA SETU BOT - SESSION MANAGER
====================================================================
Secure session management with unique IDs per channel, TTL support,
and protection against session leakage/cross-user mixing.
====================================================================
"""

import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from database import get_database

logger = logging.getLogger(__name__)

# =====================================================================
# CONFIGURATION
# =====================================================================
SESSION_TTL_HOURS = int(os.environ.get('SESSION_TTL_HOURS', '24'))
MAX_SESSIONS_PER_USER = int(os.environ.get('MAX_SESSIONS_PER_USER', '10'))

# Channel prefixes for session isolation
CHANNEL_PREFIXES = {
    'web': 'web',
    'whatsapp': 'wa',
    'facebook': 'fb',
    'widget': 'wgt',
    'api': 'api'
}


class SessionManager:
    """
    Manages user sessions with:
    - Unique session IDs per channel
    - TTL-based expiration
    - Cross-channel isolation
    - Session leakage prevention
    """
    
    def __init__(self):
        self.ttl_hours = SESSION_TTL_HOURS
        self.max_sessions = MAX_SESSIONS_PER_USER
        
    def generate_session_id(self, channel: str, user_identifier: str) -> str:
        """
        Generate a unique, channel-scoped session ID.
        
        Format: {channel_prefix}_{user_hash}_{uuid}_{timestamp}
        
        This ensures:
        - Sessions are isolated per channel
        - Sessions can be traced to users
        - Sessions are unique even for same user
        """
        import hashlib
        
        channel_prefix = CHANNEL_PREFIXES.get(channel, 'unk')
        user_hash = hashlib.sha256(user_identifier.encode()).hexdigest()[:8]
        unique_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        
        return f"{channel_prefix}_{user_hash}_{unique_id}_{timestamp}"
    
    def parse_session_id(self, session_id: str) -> Dict[str, str]:
        """
        Parse session ID to extract metadata.
        """
        try:
            parts = session_id.split('_')
            if len(parts) >= 4:
                return {
                    'channel': parts[0],
                    'user_hash': parts[1],
                    'unique_id': parts[2],
                    'timestamp': parts[3]
                }
        except Exception:
            pass
        return {'channel': 'unknown', 'raw': session_id}
    
    def is_session_expired(self, created_at: str) -> bool:
        """
        Check if session has expired based on TTL.
        """
        try:
            created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            expiry = created + timedelta(hours=self.ttl_hours)
            return datetime.now(timezone.utc) > expiry
        except Exception as e:
            logger.error(f"Error checking session expiry: {e}")
            return True  # Treat parse errors as expired
    
    async def create_session(
        self,
        channel: str,
        user_identifier: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new session with proper isolation.
        """
        db = await get_database()
        
        session_id = self.generate_session_id(channel, user_identifier)
        now = datetime.now(timezone.utc).isoformat()
        expiry = (datetime.now(timezone.utc) + timedelta(hours=self.ttl_hours)).isoformat()
        
        session = {
            "id": session_id,
            "channel": channel,
            "user_identifier": user_identifier,
            "messages": [],
            "step": "start",
            "created_at": now,
            "expires_at": expiry,
            "last_activity": now,
            "metadata": metadata or {},
            "is_active": True
        }
        
        await db.chat_sessions.insert_one(session)
        
        # Clean up old sessions for this user
        await self._cleanup_old_sessions(channel, user_identifier)
        
        logger.info(f"Created new session: {session_id} for channel: {channel}")
        return session
    
    async def get_session(
        self,
        session_id: str,
        validate_channel: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get session by ID with validation.
        
        Args:
            session_id: Session identifier
            validate_channel: If provided, verify session belongs to this channel
            
        Returns:
            Session data or None if invalid/expired
        """
        db = await get_database()
        
        session = await db.chat_sessions.find_one(
            {"id": session_id},
            {"_id": 0}
        )
        
        if not session:
            logger.warning(f"Session not found: {session_id}")
            return None
        
        # Check channel isolation
        if validate_channel:
            session_meta = self.parse_session_id(session_id)
            expected_prefix = CHANNEL_PREFIXES.get(validate_channel, validate_channel)
            if session_meta.get('channel') != expected_prefix:
                logger.warning(
                    f"Session channel mismatch: {session_id} "
                    f"expected {expected_prefix}, got {session_meta.get('channel')}"
                )
                return None
        
        # Check expiration
        if self.is_session_expired(session.get('created_at', '')):
            logger.info(f"Session expired: {session_id}")
            await self.expire_session(session_id)
            return None
        
        # Update last activity
        await db.chat_sessions.update_one(
            {"id": session_id},
            {"$set": {"last_activity": datetime.now(timezone.utc).isoformat()}}
        )
        
        return session
    
    async def get_or_create_session(
        self,
        channel: str,
        user_identifier: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get existing session or create new one.
        Ensures proper channel isolation.
        """
        if session_id:
            session = await self.get_session(session_id, validate_channel=channel)
            if session:
                return session
        
        # Create new session
        return await self.create_session(channel, user_identifier, metadata)
    
    async def expire_session(self, session_id: str):
        """
        Mark session as expired/inactive.
        """
        db = await get_database()
        
        await db.chat_sessions.update_one(
            {"id": session_id},
            {
                "$set": {
                    "is_active": False,
                    "expired_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        logger.info(f"Session expired: {session_id}")
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Add a message to session history.
        """
        db = await get_database()
        
        message = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(metadata or {})
        }
        
        await db.chat_sessions.update_one(
            {"id": session_id},
            {
                "$push": {"messages": message},
                "$set": {"last_activity": datetime.now(timezone.utc).isoformat()}
            }
        )
    
    async def _cleanup_old_sessions(self, channel: str, user_identifier: str):
        """
        Remove old sessions to prevent accumulation.
        Keeps only the most recent MAX_SESSIONS_PER_USER sessions.
        """
        db = await get_database()
        
        # Find old sessions for this user/channel
        old_sessions = await db.chat_sessions.find(
            {
                "channel": channel,
                "user_identifier": user_identifier,
                "is_active": True
            },
            {"id": 1, "created_at": 1}
        ).sort("created_at", -1).skip(self.max_sessions).to_list(100)
        
        if old_sessions:
            old_ids = [s['id'] for s in old_sessions]
            await db.chat_sessions.update_many(
                {"id": {"$in": old_ids}},
                {"$set": {"is_active": False, "cleanup_reason": "max_sessions_exceeded"}}
            )
            logger.info(f"Cleaned up {len(old_ids)} old sessions for user in channel {channel}")
    
    async def cleanup_expired_sessions(self):
        """
        Background task to clean up all expired sessions.
        Should be run periodically.
        """
        db = await get_database()
        
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=self.ttl_hours)).isoformat()
        
        result = await db.chat_sessions.update_many(
            {
                "is_active": True,
                "created_at": {"$lt": cutoff}
            },
            {
                "$set": {
                    "is_active": False,
                    "cleanup_reason": "ttl_expired",
                    "expired_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"Cleaned up {result.modified_count} expired sessions")


# Global session manager instance
session_manager = SessionManager()
