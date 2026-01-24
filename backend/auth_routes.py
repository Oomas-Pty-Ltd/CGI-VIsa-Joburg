from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
import bcrypt
from database import get_database
from auth_utils import create_token

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    token: str
    user_type: str
    user_id: str
    company_id: str = None

@router.post("/super-admin/login", response_model=LoginResponse)
async def super_admin_login(request: LoginRequest):
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
        company_id=admin['company_id']
    )

@router.post("/user/register")
async def user_register(request: LoginRequest):
    db = await get_database()
    
    existing = await db.users.find_one({"email": request.email})
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
        "email": request.email,
        "password": hashed.decode('utf-8'),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    token = create_token(user_id, 'user')
    return LoginResponse(
        token=token,
        user_type='user',
        user_id=user_id
    )

@router.post("/user/login", response_model=LoginResponse)
async def user_login(request: LoginRequest):
    db = await get_database()
    user = await db.users.find_one({"email": request.email}, {"_id": 0})
    
    if not user or not bcrypt.checkpw(request.password.encode('utf-8'), user['password'].encode('utf-8')):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    token = create_token(user['id'], 'user')
    return LoginResponse(
        token=token,
        user_type='user',
        user_id=user['id']
    )