from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
import bcrypt
from database import get_database
from auth_utils import create_token, verify_token
from tenant import get_tenant_id
from services.audit_service import audit_service, AuditSeverity

router = APIRouter(prefix="/auth", tags=["auth"])

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
    token: str
    user_type: str
    user_id: str
    company_id: Optional[str] = None
    # Sprint 10: when True the frontend should land on /change-password
    # instead of the dashboard. Cleared by POST /api/auth/change-password.
    password_change_required: bool = False


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
        # Explicit local-admin scope
        row = await db.local_admins.find_one(
            {"email": request.email, "company_id": request.company_id}, {"_id": 0}
        )
        if row:
            admin = row
            user_type = "local_admin"
            company_id = row["company_id"]
    else:
        # Try super-admin first (no company scope)
        row = await db.super_admins.find_one({"email": request.email}, {"_id": 0})
        if row:
            admin = row
            user_type = "super_admin"
        else:
            # Fall back to local-admin (post-migration emails are globally unique)
            row = await db.local_admins.find_one({"email": request.email}, {"_id": 0})
            if row:
                admin = row
                user_type = "local_admin"
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
        raise generic_unauthorized

    token = create_token(admin["id"], user_type, company_id) if company_id else create_token(admin["id"], user_type)

    # Sprint 12 — audit successful login.
    try:
        await audit_service.log_auth(
            db=db, action="login", user_id=admin["id"], user_type=user_type,
            ip_address=client_ip, company_id=company_id,
            success=True,
        )
    except Exception:
        pass

    return LoginResponse(
        token=token,
        user_type=user_type,
        user_id=admin["id"],
        company_id=company_id,
        password_change_required=bool(admin.get("password_change_required", False)),
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
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can change their password via this endpoint",
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
