import jwt
import os
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGORITHM = 'HS256'

def create_token(user_id: str, user_type: str, company_id: str = None) -> str:
    payload = {
        "user_id": user_id,
        "user_type": user_type,
        "company_id": company_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
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