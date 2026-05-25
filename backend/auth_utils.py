import asyncio
import logging
import time
import jwt
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("auth_utils")
security = HTTPBearer()

JWT_SECRET = os.environ.get('JWT_SECRET')
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is required")

JWT_ALGORITHM = 'HS256'


def create_token(user_id: str, user_type: str, company_id: str = None) -> str:
    """Issue a JWT. The ``iat`` claim is needed so the invalidated-tokens
    blacklist can reject tokens issued before a user's data was deleted /
    their session was forcibly revoked."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id":    user_id,
        "user_type":  user_type,
        "company_id": company_id,
        "iat":        now,
        "exp":        now + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ── Invalidated-tokens blacklist (Sprint-14 hardening) ──────────────────────
# The `invalidated_tokens` collection records "every token for user_id X
# issued before time T is no longer valid." Used by GDPR deletion and
# (future) "log out everywhere" flows. The pre-Sprint-14 code wrote rows
# here but never read them — so the blacklist was a no-op. We now consult
# it on every protected request with a 60s TTL cache to keep the hot path
# fast (one Mongo round-trip per (user_id, company_id) per minute).
_INVALIDATION_TTL_SECONDS = 60
# (user_id, company_id) -> (cache_expiry_monotonic, invalidated_at_iso or None)
_invalidation_cache: Dict[Tuple[Optional[str], Optional[str]], Tuple[float, Optional[str]]] = {}


def invalidate_token_cache(user_id: Optional[str] = None, company_id: Optional[str] = None) -> None:
    """Drop one entry from the per-process invalidation cache, or all if both
    args are None. Compliance / token-rotation code should call this after
    writing to ``invalidated_tokens`` so the next request sees the change
    without waiting for the TTL."""
    if user_id is None and company_id is None:
        _invalidation_cache.clear()
        return
    _invalidation_cache.pop((user_id, company_id), None)


async def _lookup_invalidation(db, user_id: str, company_id: Optional[str]) -> Optional[str]:
    """Return the most recent invalidation timestamp for (user_id, company_id),
    or None if the user has no blacklist row. Cached per-process for
    ``_INVALIDATION_TTL_SECONDS``."""
    key = (user_id, company_id)
    now = time.monotonic()
    cached = _invalidation_cache.get(key)
    if cached and cached[0] > now:
        return cached[1]

    query = {"user_id": user_id}
    # Tenant scope on the lookup so a blacklist for a different tenant
    # (rare but possible if the same user_id ever existed under another
    # company) doesn't cross-invalidate. None matches inserts that
    # predate the Sprint 4 company_id backfill.
    if company_id:
        query["company_id"] = company_id

    row = await db.invalidated_tokens.find_one(
        query, {"_id": 0, "invalidated_at": 1}, sort=[("invalidated_at", -1)]
    )
    invalidated_at = row.get("invalidated_at") if row else None
    _invalidation_cache[key] = (now + _INVALIDATION_TTL_SECONDS, invalidated_at)
    return invalidated_at


async def _check_token_not_invalidated(payload: dict) -> None:
    """Raise 401 if this token was issued before the user was blacklisted.

    Skips the check for tokens missing ``iat`` (issued by pre-Sprint-14
    code) — they fall back to the legacy behaviour of "signature+expiry
    is enough." Once existing tokens expire (≤7 days) every token will
    carry ``iat`` and the blacklist becomes authoritative."""
    user_id = payload.get("user_id")
    iat     = payload.get("iat")
    if not user_id or not iat:
        return  # nothing to compare against
    # Import here to avoid a circular import at module load
    from database import get_database
    db = await get_database()
    invalidated_at = await _lookup_invalidation(db, user_id, payload.get("company_id"))
    if not invalidated_at:
        return
    # Compare token's iat (epoch seconds) to invalidated_at (ISO 8601)
    try:
        inv_dt = datetime.fromisoformat(invalidated_at.replace("Z", "+00:00"))
        token_iat = datetime.fromtimestamp(int(iat), tz=timezone.utc)
    except (ValueError, TypeError):
        return  # malformed dates — fail open
    if token_iat < inv_dt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    # Sprint-14: consult the invalidated_tokens blacklist. Cached per-process
    # so this is at most one Mongo lookup per (user_id, company_id) per
    # minute on the hot path.
    await _check_token_not_invalidated(payload)
    return payload

def verify_super_admin(payload: dict = Depends(verify_token)):
    if payload.get('user_type') != 'super_admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )
    return payload

def verify_local_admin(payload: dict = Depends(verify_token)):
    if payload.get('user_type') != 'local_admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local admin access required"
        )
    return payload


# ── Sprint 8: shared admin dependency + tenant-scope enforcement ────────────

def verify_admin(payload: dict = Depends(verify_token)):
    """Accept either a super_admin or a local_admin token.

    Endpoints that both roles can hit (services, bot-config, scrapers,
    knowledge, escalations, audit logs, conversations) use this instead
    of ``verify_super_admin``. The handler is then responsible for
    calling ``enforce_tenant_scope()`` to constrain the data a local
    admin can see to their own tenant."""
    if payload.get('user_type') not in ('super_admin', 'local_admin'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return payload


def enforce_tenant_scope(payload: dict, company_id):
    """Resolve the effective tenant scope for an admin handler.

    - ``super_admin``: returns ``company_id`` as-is. ``None`` means
      "all tenants" (cross-tenant overview).
    - ``local_admin``: ignores any ``company_id`` that differs from the
      JWT's tenant. Returns the JWT's tenant. Cross-tenant access
      attempts raise 403 — a tenant admin cannot probe other tenants
      by guessing IDs.

    Pattern in handlers::

        async def list_services(
            company_id: str,
            payload: dict = Depends(verify_admin),
        ):
            company_id = enforce_tenant_scope(payload, company_id)
            ...
    """
    user_type = payload.get('user_type')
    jwt_tenant = payload.get('company_id')

    if user_type == 'super_admin':
        return company_id  # may be None for cross-tenant views

    if user_type == 'local_admin':
        if not jwt_tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Local admin token missing company_id",
            )
        if company_id is not None and company_id != jwt_tenant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access another tenant's data",
            )
        return jwt_tenant

    # Should never reach here because verify_admin filters non-admins.
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin role required",
    )