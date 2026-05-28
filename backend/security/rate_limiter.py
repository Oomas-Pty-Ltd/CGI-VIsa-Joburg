"""
====================================================================
SEVA SETU BOT - RATE LIMITER
====================================================================
Implements rate limiting to prevent abuse and control costs:
- IP-based limits
- Per-user quotas
- Per-phone number caps
- Configurable thresholds

Enforcement is DISTRIBUTED via MongoDB (atomic ``$inc`` fixed-window
counters in the ``rate_limits`` collection). This is correct across
multiple workers / Cloud Run instances — a per-process in-memory
counter would let the effective limit scale with the instance count
(each instance counts only its own slice). The in-memory ``RateLimiter``
below is retained ONLY for the dashboard stats (``get_stats``); it no
longer gates requests. Swap-in for Redis later is a drop-in: same
key + counter semantics, faster backend.
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
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from database import get_database
from services import platform_config as _pcfg

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

    NOTE: request gating now runs through the Mongo-backed distributed
    path (``check_limits_distributed`` / ``check_rate_limit``). This class
    is kept for the per-process dashboard counters exposed by ``get_stats``
    (``total_requests`` / ``blocked_requests``, bumped from the Mongo path).
    The ``check_*_limit`` methods are no longer on the request path.
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


# Global rate limiter instance (stats only; see class docstring)
rate_limiter = RateLimiter()


# =====================================================================
# DISTRIBUTED (MongoDB) ENFORCEMENT
# =====================================================================
# Fixed-window counters in the ``rate_limits`` collection. One atomic
# ``find_one_and_update`` ($inc, upsert) per dimension — correct across
# workers/instances, no shared memory needed. The TTL index on
# ``expires_at`` auto-evicts old windows (no cleanup job). Limits config
# (RATE_LIMIT_CONFIG) is read in-process; only the COUNTERS hit Mongo.

async def _hit_window(db, key_prefix: str, identifier: str, limit: int, window_seconds: int) -> bool:
    """Count this request in the current fixed window and report whether it is
    still within ``limit``. Atomic ``$inc`` upsert → safe under concurrency and
    across instances. Returns True if ALLOWED, False if the window is over limit.

    Retries once on the upsert race: two instances creating the same brand-new
    window key can collide on the unique ``key`` index; the retry finds the now-
    existing doc and simply increments it.
    """
    now = time.time()
    window_start = int(now // window_seconds) * window_seconds
    full_key = f"{key_prefix}:{identifier}:{window_start}"
    # Keep the doc a bit past the window end so a late request in the window
    # still sees the count before the TTL sweep removes it.
    expires_at = datetime.fromtimestamp(window_start + window_seconds + 60, tz=timezone.utc)
    for _ in range(2):
        try:
            doc = await db.rate_limits.find_one_and_update(
                {"key": full_key},
                {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": expires_at}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
                projection={"count": 1},
            )
            return int((doc or {}).get("count", 1)) <= limit
        except DuplicateKeyError:
            continue
    return True  # persistent upsert race → fail-open for this hit


def _limit(key: str, default: int) -> int:
    """Read a rate-limit knob from platform_config (DB → env → default).
    Coerces to int; a non-positive / unparseable value means "no limit on
    this dimension" (the caller skips the window)."""
    try:
        return int(_pcfg.get(key, default) or 0)
    except (TypeError, ValueError):
        return default


async def check_limits_distributed(db, ip: str, user_id: Optional[str] = None) -> Tuple[bool, str]:
    """Enforce per-IP (second/minute/hour) and, for authenticated users,
    per-user (second/minute/day) limits via Mongo. Short-circuits on the first
    breach. Limits come from ``platform_config`` (super-admin editable, env
    fallback); **0 on any dimension disables that window**.

    No single global counter: that would be one hot document every request
    writes to (a Mongo write-contention point) — global capacity is better
    bounded by Cloud Run ``max-instances`` + concurrency. Phone limits live in
    the webhook paths, not here (web ``/chat`` has no phone)."""
    try:
        burst = float(_pcfg.get("rate_limit_burst_multiplier", 1.5) or 1.0)
    except (TypeError, ValueError):
        burst = 1.5
    ip_per_sec = _limit("rate_limit_ip_per_sec", 0)
    ip_minute_limit = int(_limit("rate_limit_ip_per_min", 30) * burst)
    ip_per_hour = _limit("rate_limit_ip_per_hour", 500)
    user_per_sec = _limit("rate_limit_user_per_sec", 0)
    user_per_min = _limit("rate_limit_user_per_min", 20)
    user_per_day = _limit("rate_limit_user_per_day", 500)

    if ip_per_sec > 0 and not await _hit_window(db, "ip_sec", ip, ip_per_sec, 1):
        return False, "Too many requests. Please slow down."
    if ip_minute_limit > 0 and not await _hit_window(db, "ip_min", ip, ip_minute_limit, 60):
        return False, "Rate limit exceeded. Please wait a minute and try again."
    if ip_per_hour > 0 and not await _hit_window(db, "ip_hour", ip, ip_per_hour, 3600):
        return False, "Hourly rate limit exceeded. Please try again later."

    if user_id and user_id != "guest":
        if user_per_sec > 0 and not await _hit_window(db, "user_sec", user_id, user_per_sec, 1):
            return False, "You're sending messages too fast. Please slow down."
        if user_per_min > 0 and not await _hit_window(db, "user_min", user_id, user_per_min, 60):
            return False, "You're sending messages too fast. Please slow down."
        if user_per_day > 0 and not await _hit_window(db, "user_day", user_id, user_per_day, 86400):
            return False, "Daily message limit reached. Please try again tomorrow."

    return True, "OK"


def _extract_user_id(request: Request) -> Optional[str]:
    """Best-effort user id from an unverified Bearer token (used only to key the
    rate limit — signature is verified elsewhere on the real auth path)."""
    try:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            import jwt
            payload = jwt.decode(auth_header[7:], options={"verify_signature": False})
            return payload.get('user_id')
    except Exception:
        pass
    return None


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
    user_id = _extract_user_id(request)
    rate_limiter.total_requests += 1  # per-process counter for get_stats()

    try:
        db = await get_database()
        allowed, reason = await check_limits_distributed(db, ip, user_id)
    except Exception as e:
        # Fail OPEN: never block real users on a limiter/DB hiccup. The app
        # itself can't serve a chat without Mongo, so this isn't a bypass risk.
        logger.warning("rate limiter backend error (failing open): %s", e)
        return True

    if not allowed:
        rate_limiter.blocked_requests += 1
        logger.warning(f"Rate limit hit: IP={ip}, user={user_id}, reason={reason}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=reason,
            headers={"Retry-After": "60"}
        )

    return True
