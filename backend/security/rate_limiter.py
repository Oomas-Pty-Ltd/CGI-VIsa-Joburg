"""
====================================================================
SEVA SETU BOT - RATE LIMITER
====================================================================
Implements rate limiting to prevent abuse and control costs:
- IP-based limits
- Per-user quotas
- Per-phone number caps
- Configurable thresholds
====================================================================
"""

import os
import time
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)

# =====================================================================
# CONFIGURATION
# =====================================================================
RATE_LIMIT_CONFIG = {
    # IP-based limits
    "ip_requests_per_minute": int(os.environ.get('RATE_LIMIT_IP_PER_MIN', '30')),
    "ip_requests_per_hour": int(os.environ.get('RATE_LIMIT_IP_PER_HOUR', '500')),
    
    # User-based limits (authenticated users)
    "user_requests_per_minute": int(os.environ.get('RATE_LIMIT_USER_PER_MIN', '20')),
    "user_requests_per_day": int(os.environ.get('RATE_LIMIT_USER_PER_DAY', '500')),
    
    # Phone-based limits (WhatsApp/SMS)
    "phone_messages_per_minute": int(os.environ.get('RATE_LIMIT_PHONE_PER_MIN', '10')),
    "phone_messages_per_day": int(os.environ.get('RATE_LIMIT_PHONE_PER_DAY', '100')),
    
    # Global limits
    "global_requests_per_minute": int(os.environ.get('RATE_LIMIT_GLOBAL_PER_MIN', '1000')),
    
    # Burst allowance (allows short bursts above limit)
    "burst_multiplier": float(os.environ.get('RATE_LIMIT_BURST_MULTIPLIER', '1.5')),
    
    # Cleanup interval (seconds)
    "cleanup_interval": 300,  # 5 minutes
}


@dataclass
class RateLimitBucket:
    """Tracks rate limit state for an entity"""
    count: int = 0
    window_start: float = field(default_factory=time.time)
    blocked_until: Optional[float] = None
    
    def reset_if_expired(self, window_seconds: int) -> None:
        """Reset counter if window has expired"""
        now = time.time()
        if now - self.window_start >= window_seconds:
            self.count = 0
            self.window_start = now
    
    def increment(self) -> int:
        """Increment counter and return new count"""
        self.count += 1
        return self.count
    
    def is_blocked(self) -> bool:
        """Check if currently blocked"""
        if self.blocked_until is None:
            return False
        return time.time() < self.blocked_until
    
    def block_for(self, seconds: int) -> None:
        """Block for specified duration"""
        self.blocked_until = time.time() + seconds


class RateLimiter:
    """
    In-memory rate limiter with multiple limit types.
    For production, consider using Redis for distributed rate limiting.
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or RATE_LIMIT_CONFIG
        
        # Separate buckets for different limit types
        self.ip_minute_buckets: Dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
        self.ip_hour_buckets: Dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
        self.user_minute_buckets: Dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
        self.user_day_buckets: Dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
        self.phone_minute_buckets: Dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
        self.phone_day_buckets: Dict[str, RateLimitBucket] = defaultdict(RateLimitBucket)
        self.global_minute_bucket = RateLimitBucket()
        
        # Stats
        self.total_requests = 0
        self.blocked_requests = 0
        self.last_cleanup = time.time()
    
    def _cleanup_old_buckets(self):
        """Remove stale buckets to prevent memory growth"""
        now = time.time()
        if now - self.last_cleanup < self.config['cleanup_interval']:
            return
        
        # Cleanup minute buckets older than 2 minutes
        for buckets in [self.ip_minute_buckets, self.user_minute_buckets, self.phone_minute_buckets]:
            stale_keys = [
                k for k, v in buckets.items()
                if now - v.window_start > 120
            ]
            for k in stale_keys:
                del buckets[k]
        
        # Cleanup hour buckets older than 2 hours
        stale_keys = [
            k for k, v in self.ip_hour_buckets.items()
            if now - v.window_start > 7200
        ]
        for k in stale_keys:
            del self.ip_hour_buckets[k]
        
        # Cleanup day buckets older than 2 days
        for buckets in [self.user_day_buckets, self.phone_day_buckets]:
            stale_keys = [
                k for k, v in buckets.items()
                if now - v.window_start > 172800
            ]
            for k in stale_keys:
                del buckets[k]
        
        self.last_cleanup = now
        logger.debug(f"Rate limiter cleanup completed")
    
    def check_ip_limit(self, ip: str) -> Tuple[bool, str]:
        """
        Check IP-based rate limits.
        Returns (allowed, reason)
        """
        self._cleanup_old_buckets()
        
        # Check minute limit
        minute_bucket = self.ip_minute_buckets[ip]
        minute_bucket.reset_if_expired(60)
        
        if minute_bucket.is_blocked():
            return False, "IP temporarily blocked due to excessive requests"
        
        burst_limit = int(self.config['ip_requests_per_minute'] * self.config['burst_multiplier'])
        if minute_bucket.count >= burst_limit:
            minute_bucket.block_for(60)  # Block for 1 minute
            self.blocked_requests += 1
            logger.warning(f"IP {ip} blocked: exceeded minute limit ({minute_bucket.count}/{burst_limit})")
            return False, f"Rate limit exceeded. Please wait 60 seconds."
        
        # Check hour limit
        hour_bucket = self.ip_hour_buckets[ip]
        hour_bucket.reset_if_expired(3600)
        
        if hour_bucket.count >= self.config['ip_requests_per_hour']:
            self.blocked_requests += 1
            logger.warning(f"IP {ip} blocked: exceeded hour limit ({hour_bucket.count}/{self.config['ip_requests_per_hour']})")
            return False, f"Hourly rate limit exceeded. Please try again later."
        
        # Increment counters
        minute_bucket.increment()
        hour_bucket.increment()
        self.total_requests += 1
        
        return True, "OK"
    
    def check_user_limit(self, user_id: str) -> Tuple[bool, str]:
        """
        Check user-based rate limits.
        Returns (allowed, reason)
        """
        # Check minute limit
        minute_bucket = self.user_minute_buckets[user_id]
        minute_bucket.reset_if_expired(60)
        
        if minute_bucket.count >= self.config['user_requests_per_minute']:
            self.blocked_requests += 1
            return False, "You're sending messages too fast. Please slow down."
        
        # Check daily limit
        day_bucket = self.user_day_buckets[user_id]
        day_bucket.reset_if_expired(86400)
        
        if day_bucket.count >= self.config['user_requests_per_day']:
            self.blocked_requests += 1
            return False, "Daily message limit reached. Please try again tomorrow."
        
        minute_bucket.increment()
        day_bucket.increment()
        
        return True, "OK"
    
    def check_phone_limit(self, phone: str) -> Tuple[bool, str]:
        """
        Check phone-based rate limits (for WhatsApp/SMS).
        Returns (allowed, reason)
        """
        # Normalize phone number
        phone = phone.replace("+", "").replace(" ", "").replace("-", "")
        
        # Check minute limit
        minute_bucket = self.phone_minute_buckets[phone]
        minute_bucket.reset_if_expired(60)
        
        if minute_bucket.count >= self.config['phone_messages_per_minute']:
            self.blocked_requests += 1
            return False, "Too many messages. Please wait a moment."
        
        # Check daily limit
        day_bucket = self.phone_day_buckets[phone]
        day_bucket.reset_if_expired(86400)
        
        if day_bucket.count >= self.config['phone_messages_per_day']:
            self.blocked_requests += 1
            return False, "Daily message limit reached for this number."
        
        minute_bucket.increment()
        day_bucket.increment()
        
        return True, "OK"
    
    def check_global_limit(self) -> Tuple[bool, str]:
        """
        Check global rate limit to prevent system overload.
        Returns (allowed, reason)
        """
        self.global_minute_bucket.reset_if_expired(60)
        
        if self.global_minute_bucket.count >= self.config['global_requests_per_minute']:
            self.blocked_requests += 1
            return False, "Service is experiencing high traffic. Please try again shortly."
        
        self.global_minute_bucket.increment()
        return True, "OK"
    
    def check_all_limits(
        self,
        ip: str,
        user_id: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Check all applicable rate limits.
        Returns (allowed, reason)
        """
        # Check global limit first
        allowed, reason = self.check_global_limit()
        if not allowed:
            return allowed, reason
        
        # Check IP limit
        allowed, reason = self.check_ip_limit(ip)
        if not allowed:
            return allowed, reason
        
        # Check user limit if authenticated
        if user_id and user_id != "guest":
            allowed, reason = self.check_user_limit(user_id)
            if not allowed:
                return allowed, reason
        
        # Check phone limit if applicable
        if phone:
            allowed, reason = self.check_phone_limit(phone)
            if not allowed:
                return allowed, reason
        
        return True, "OK"
    
    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        return {
            "total_requests": self.total_requests,
            "blocked_requests": self.blocked_requests,
            "block_rate": round(self.blocked_requests / max(self.total_requests, 1) * 100, 2),
            "active_ip_buckets": len(self.ip_minute_buckets),
            "active_user_buckets": len(self.user_minute_buckets),
            "active_phone_buckets": len(self.phone_minute_buckets),
            "config": {
                "ip_per_minute": self.config['ip_requests_per_minute'],
                "ip_per_hour": self.config['ip_requests_per_hour'],
                "user_per_day": self.config['user_requests_per_day'],
                "phone_per_day": self.config['phone_messages_per_day'],
            }
        }
    
    def get_user_remaining(self, user_id: str) -> Dict:
        """Get remaining quota for a user"""
        minute_bucket = self.user_minute_buckets.get(user_id, RateLimitBucket())
        day_bucket = self.user_day_buckets.get(user_id, RateLimitBucket())
        
        return {
            "minute_remaining": max(0, self.config['user_requests_per_minute'] - minute_bucket.count),
            "day_remaining": max(0, self.config['user_requests_per_day'] - day_bucket.count),
            "minute_limit": self.config['user_requests_per_minute'],
            "day_limit": self.config['user_requests_per_day'],
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


# =====================================================================
# FASTAPI DEPENDENCY
# =====================================================================
async def check_rate_limit(request: Request) -> bool:
    """
    FastAPI dependency to check rate limits.
    Use: @router.post("/chat", dependencies=[Depends(check_rate_limit)])
    """
    # Skip rate limiting if disabled
    if os.environ.get('RATE_LIMIT_DISABLED', '').lower() == 'true':
        return True
    
    ip = request.client.host if request.client else "unknown"
    
    # Try to get user_id from auth header or body
    user_id = None
    try:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            import jwt
            token = auth_header[7:]
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get('user_id')
    except Exception:
        pass
    
    allowed, reason = rate_limiter.check_all_limits(ip, user_id)
    
    if not allowed:
        logger.warning(f"Rate limit hit: IP={ip}, user={user_id}, reason={reason}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=reason,
            headers={"Retry-After": "60"}
        )
    
    return True
