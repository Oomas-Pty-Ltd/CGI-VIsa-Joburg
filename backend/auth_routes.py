from datetime import datetime, timezone, timedelta
from typing import Optional
import os
import uuid
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
import bcrypt
from database import get_database
from auth_utils import create_token, verify_token
from tenant import get_tenant_id
from services.audit_service import audit_service, AuditSeverity

router = APIRouter(prefix="/auth", tags=["auth"])

# Console-login 2FA. After a correct password, an OTP is issued and the real
# JWT is only minted once it's verified (POST /auth/login/verify-otp). Honors
# the platform `dev_auth_mode` flag: dev ON → fixed 123456, no email; dev OFF →
# random OTP emailed, 123456 rejected.
_CONSOLE_DEV_OTP = "123456"
_LOGIN_OTP_TTL_MIN = 10
_LOGIN_OTP_MAX_ATTEMPTS = 5
_LOGIN_OTP_LOCKOUT_MIN = 5


async def _issue_login_otp(db, email: str, identity: dict) -> dict:
    """Create a one-time login OTP bound to a password-verified identity.
    Returns {dev_mode, email_sent}."""
    from services import platform_config as _pc
    try:
        await _pc.ensure_loaded()
    except Exception:
        pass
    dev_mode = bool(_pc.get("dev_auth_mode", True))
    otp_value = _CONSOLE_DEV_OTP if dev_mode else f"{secrets.randbelow(1_000_000):06d}"

    # One active challenge per email at a time.
    await db.login_otp_tokens.delete_many({"email": email, "used": False})
    await db.login_otp_tokens.insert_one({
        "id":          str(uuid.uuid4()),
        "email":       email,
        "otp":         otp_value,
        "identity":    identity,   # user_id, user_type, company_id, password_change_required
        "expires_at":  (datetime.now(timezone.utc) + timedelta(minutes=_LOGIN_OTP_TTL_MIN)).isoformat(),
        "used":        False,
        "attempts":    0,
        "created_at":  datetime.now(timezone.utc).isoformat(),
    })

    email_sent = False
    if not dev_mode:
        from services.email_service import send_otp_email
        email_sent = send_otp_email(
            email, otp_value, bot_name="",
            org_name=os.environ.get("PLATFORM_NAME") or "Admin Console",
        )
    return {"dev_mode": dev_mode, "email_sent": email_sent}

# Rolling per-email failed-login counter (in-process; resets on restart — fine
# for a brute-force burst signal). Maps email -> list of recent attempt times.
_FAILED_LOGINS: dict = {}
_FAILED_WINDOW_SECONDS = 900  # 15 min


async def _maybe_alert_lockout(email: str, ip: str) -> None:
    from services.notification_dispatcher import notify, get_setting
    now = datetime.now(timezone.utc).timestamp()
    times = [t for t in _FAILED_LOGINS.get(email, []) if now - t < _FAILED_WINDOW_SECONDS]
    times.append(now)
    _FAILED_LOGINS[email] = times
    setting = await get_setting("security.login_lockout")
    threshold = int((setting.get("params") or {}).get("attempts_threshold", 5))
    if len(times) >= threshold:
        await notify("security.login_lockout", context={"email": email, "attempts": len(times), "ip": ip or "unknown"})

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UnifiedLoginRequest(BaseModel):
    """Sprint 7 — one login form for both console roles.

    ``company_id`` is optional and only meaningful for local-admin
    sign-ins where the operator wants to scope the lookup explicitly
    (e.g. the same email exists as a super-admin and a local-admin —
    sending ``company_id`` forces the local-admin row to win)."""
    email:      EmailStr
    password:   str
    company_id: Optional[str] = None

class LoginResponse(BaseModel):
    # token/user_* are null on the OTP-challenge response (password verified,
    # awaiting OTP). They're populated by /auth/login/verify-otp.
    token: Optional[str] = None
    user_type: Optional[str] = None
    user_id: Optional[str] = None
    company_id: Optional[str] = None
    # Sprint 10: when True the frontend should land on /change-password
    # instead of the dashboard. Cleared by POST /api/auth/change-password.
    password_change_required: bool = False
    # 2FA challenge fields.
    otp_required: bool = False
    email: Optional[str] = None
    message: Optional[str] = None
    dev_mode: Optional[bool] = None


class LoginOtpVerifyRequest(BaseModel):
    email: EmailStr
    otp: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/login", response_model=LoginResponse)
async def unified_login(request: UnifiedLoginRequest, http_request: Request):
    """Single login endpoint for super-admins and local-admins.

    Resolution order:
      1. If ``company_id`` is given → match local_admins on (email, company_id).
      2. Else try super_admins by email.
      3. Else fall back to local_admins by email (globally unique post-Sprint-7).

    Always returns the same 401 on any failure to avoid leaking which
    table holds the email (basic enumeration defence). Both success and
    failure are written to the audit log so security operations can
    spot brute-force attempts."""
    db = await get_database()
    generic_unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
    )

    client_ip = http_request.client.host if http_request.client else None

    admin = None
    user_type = None
    company_id = None

    if request.company_id:
        # Explicit tenant scope — try local_admin first, then viewer.
        row = await db.local_admins.find_one(
            {"email": request.email, "company_id": request.company_id}, {"_id": 0}
        )
        if row:
            admin = row
            user_type = "local_admin"
            company_id = row["company_id"]
        else:
            row = await db.local_viewers.find_one(
                {"email": request.email, "company_id": request.company_id}, {"_id": 0}
            )
            if row:
                admin = row
                user_type = "viewer"
                company_id = row["company_id"]
    else:
        # Try super-admin first (no company scope)
        row = await db.super_admins.find_one({"email": request.email}, {"_id": 0})
        if row:
            admin = row
            user_type = "super_admin"
        else:
            # Fall back to local-admin then viewer (emails are globally
            # unique post-Sprint-7 / migration 0010, so first hit wins).
            row = await db.local_admins.find_one({"email": request.email}, {"_id": 0})
            if row:
                admin = row
                user_type = "local_admin"
                company_id = row["company_id"]
            else:
                row = await db.local_viewers.find_one({"email": request.email}, {"_id": 0})
                if row:
                    admin = row
                    user_type = "viewer"
                    company_id = row["company_id"]

    if not admin or not bcrypt.checkpw(
        request.password.encode("utf-8"), admin["password"].encode("utf-8")
    ):
        # Sprint 12 — audit failed login. We log the email tried (not the
        # password) so brute force on a known account is visible. The
        # tenant scope is None because we don't trust the input.
        try:
            await audit_service.log_auth(
                db=db, action="login", user_id=request.email, user_type="unknown",
                ip_address=client_ip,
                success=False,
                error_message="Invalid credentials",
                metadata={"email": request.email, "company_id_provided": request.company_id},
            )
        except Exception:
            pass  # never let audit failure block the login response
        # Brute-force signal: track failed attempts per email in a short
        # rolling window and alert when they cross the configured threshold.
        try:
            await _maybe_alert_lockout(request.email, client_ip)
        except Exception:
            pass
        raise generic_unauthorized

    # Password verified — issue a 2FA OTP challenge instead of the token.
    # The JWT is minted only after /auth/login/verify-otp.
    identity = {
        "user_id": admin["id"],
        "user_type": user_type,
        "company_id": company_id,
        "password_change_required": bool(admin.get("password_change_required", False)),
    }
    otp_info = await _issue_login_otp(db, request.email, identity)

    try:
        await audit_service.log_auth(
            db=db, action="login_otp_challenge", user_id=admin["id"], user_type=user_type,
            ip_address=client_ip, company_id=company_id, success=True,
        )
    except Exception:
        pass

    if otp_info["dev_mode"]:
        msg = "Developer mode is on — enter OTP 123456 to finish signing in."
    elif otp_info["email_sent"]:
        msg = f"We sent a verification code to {request.email}. Enter it to finish signing in."
    else:
        msg = "We couldn't send the verification email just now. Please try again in a moment."

    return LoginResponse(
        otp_required=True,
        email=request.email,
        message=msg,
        dev_mode=otp_info["dev_mode"],
        user_type=user_type,  # UX hint only; token still withheld
    )


@router.post("/login/verify-otp", response_model=LoginResponse)
async def verify_login_otp(req: LoginOtpVerifyRequest, http_request: Request):
    """Second step of console login: verify the OTP and mint the JWT."""
    db = await get_database()
    client_ip = http_request.client.host if http_request.client else None
    otp_input = req.otp.strip()

    token_doc = await db.login_otp_tokens.find_one(
        {"email": req.email, "used": False}, sort=[("created_at", -1)]
    )
    if not token_doc:
        raise HTTPException(status_code=400, detail="No active verification code. Please sign in again.")

    # Expiry
    expires_at = token_doc["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        await db.login_otp_tokens.delete_one({"id": token_doc["id"]})
        raise HTTPException(status_code=400, detail="Verification code expired. Please sign in again.")

    # Lockout on too many wrong attempts.
    locked_until = token_doc.get("locked_until")
    if locked_until:
        lu = datetime.fromisoformat(locked_until) if isinstance(locked_until, str) else locked_until
        if lu.tzinfo is None:
            lu = lu.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < lu:
            raise HTTPException(status_code=429, detail="Too many attempts. Please try again shortly.")

    if token_doc["otp"] != otp_input:
        attempts = token_doc.get("attempts", 0) + 1
        update = {"attempts": attempts}
        if attempts >= _LOGIN_OTP_MAX_ATTEMPTS:
            update["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=_LOGIN_OTP_LOCKOUT_MIN)).isoformat()
        await db.login_otp_tokens.update_one({"id": token_doc["id"]}, {"$set": update})
        remaining = max(_LOGIN_OTP_MAX_ATTEMPTS - attempts, 0)
        if remaining == 0:
            raise HTTPException(status_code=429, detail=f"Too many attempts. Locked for {_LOGIN_OTP_LOCKOUT_MIN} minutes.")
        raise HTTPException(status_code=400, detail=f"Invalid code. {remaining} attempt(s) remaining.")

    await db.login_otp_tokens.update_one({"id": token_doc["id"]}, {"$set": {"used": True}})

    identity = token_doc.get("identity") or {}
    uid = identity.get("user_id")
    user_type = identity.get("user_type")
    company_id = identity.get("company_id")
    token = create_token(uid, user_type, company_id)

    try:
        await audit_service.log_auth(
            db=db, action="login", user_id=uid, user_type=user_type,
            ip_address=client_ip, company_id=company_id, success=True,
        )
    except Exception:
        pass

    return LoginResponse(
        token=token,
        user_type=user_type,
        user_id=uid,
        company_id=company_id,
        password_change_required=bool(identity.get("password_change_required", False)),
    )


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    http_request: Request,
    payload: dict = Depends(verify_token),
):
    """Set a new password for the currently-authenticated console user.

    Used by:
      - The forced password-change flow after a super-admin provisions an
        account (the create-company flow sets ``password_change_required``)
      - Voluntary password changes from any admin's profile menu

    Verifies the current password as a defence-in-depth check — a stolen
    token alone can't rotate the password without also knowing the old one.
    Always clears ``password_change_required`` on success."""
    user_type = payload.get("user_type")
    user_id   = payload.get("user_id")

    if user_type == "super_admin":
        collection = "super_admins"
    elif user_type == "local_admin":
        collection = "local_admins"
    elif user_type == "viewer":
        # Viewers go through the same forced-first-login rotation as
        # admins — the resolver was missing this branch when the role
        # was introduced, so their initial bootstrap rotation 403'd.
        collection = "local_viewers"
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only console users can change their password via this endpoint",
        )

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from the current password",
        )

    db = await get_database()
    row = await db[collection].find_one({"id": user_id}, {"_id": 0})
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found",
        )

    if not bcrypt.checkpw(
        body.current_password.encode("utf-8"),
        row["password"].encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    new_hash = bcrypt.hashpw(body.new_password.encode("utf-8"), bcrypt.gensalt())
    await db[collection].update_one(
        {"id": user_id},
        {"$set": {
            "password": new_hash.decode("utf-8"),
            "password_change_required": False,
            "password_changed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    # Sprint 12 — audit the password rotation. We never store the new
    # password — the audit row just records that it happened.
    try:
        await audit_service.log_auth(
            db=db, action="password_change", user_id=user_id, user_type=user_type,
            ip_address=http_request.client.host if http_request.client else None,
            company_id=payload.get("company_id"),
            success=True,
        )
    except Exception:
        pass

    return {"success": True, "message": "Password updated"}


async def super_admin_login(request: LoginRequest):
    """Deprecated — use ``POST /api/auth/login`` instead. Kept so existing
    scripts (smoke tests, integration scripts) keep working; remove once
    everything's migrated."""
    db = await get_database()
    admin = await db.super_admins.find_one({"email": request.email}, {"_id": 0})

    if not admin or not bcrypt.checkpw(request.password.encode('utf-8'), admin['password'].encode('utf-8')):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    token = create_token(admin['id'], 'super_admin')
    return LoginResponse(
        token=token,
        user_type='super_admin',
        user_id=admin['id']
    )

@router.post("/local-admin/login", response_model=LoginResponse)
async def local_admin_login(request: LoginRequest):
    """Deprecated — use ``POST /api/auth/login`` instead."""
    db = await get_database()
    admin = await db.local_admins.find_one({"email": request.email}, {"_id": 0})

    if not admin or not bcrypt.checkpw(request.password.encode('utf-8'), admin['password'].encode('utf-8')):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    token = create_token(admin['id'], 'local_admin', admin['company_id'])
    return LoginResponse(
        token=token,
        user_type='local_admin',
        user_id=admin['id'],
        company_id=admin['company_id'],
        password_change_required=bool(admin.get("password_change_required", False)),
    )

@router.post("/user/register")
async def user_register(
    request: LoginRequest,
    company_id: str = Depends(get_tenant_id),
):
    """Register a widget user. The tenant is taken from X-Company-Id
    (sent by the embedded widget) — the new user belongs to that tenant."""
    db = await get_database()

    existing = await db.users.find_one({"company_id": company_id, "email": request.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists"
        )

    import uuid
    from datetime import datetime, timezone

    hashed = bcrypt.hashpw(request.password.encode('utf-8'), bcrypt.gensalt())
    user_id = str(uuid.uuid4())

    await db.users.insert_one({
        "id": user_id,
        "company_id": company_id,
        "email": request.email,
        "password": hashed.decode('utf-8'),
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    token = create_token(user_id, 'user', company_id)
    return LoginResponse(
        token=token,
        user_type='user',
        user_id=user_id,
        company_id=company_id,
    )

@router.post("/user/login", response_model=LoginResponse)
async def user_login(
    request: LoginRequest,
    company_id: str = Depends(get_tenant_id),
):
    """Log in a widget user. The user must belong to the tenant indicated
    by X-Company-Id — a user registered against tenant A cannot log in
    against tenant B even if the email matches."""
    db = await get_database()
    user = await db.users.find_one(
        {"company_id": company_id, "email": request.email},
        {"_id": 0},
    )

    if not user or not bcrypt.checkpw(request.password.encode('utf-8'), user['password'].encode('utf-8')):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    token = create_token(user['id'], 'user', company_id)
    return LoginResponse(
        token=token,
        user_type='user',
        user_id=user['id'],
        company_id=company_id,
    )
