from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
from contextlib import asynccontextmanager

from auth_routes import router as auth_router
from super_admin_routes import router as super_admin_router
from local_admin_routes import router as local_admin_router
from consular_routes import router as consular_router
from whatsapp_routes import router as whatsapp_router
from facebook_routes import router as facebook_router
from template_routes import router as template_router
from monitoring_routes import router as monitoring_router
from monitoring_service import start_background_monitoring

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_super_admin()
    # Initialize default templates
    from template_routes import init_default_templates
    await init_default_templates()
    # Start background monitoring
    monitoring_task = asyncio.create_task(start_background_monitoring())
    yield
    monitoring_task.cancel()
    client.close()

app = FastAPI(lifespan=lifespan)
api_router = APIRouter(prefix="/api")

async def init_super_admin():
    """Initialize super admin if not exists"""
    super_admin_email = os.environ.get('SUPER_ADMIN_EMAIL', 'superadmin@sarthak.ai')
    super_admin_password = os.environ.get('SUPER_ADMIN_PASSWORD', 'Admin@2025')
    
    existing = await db.super_admins.find_one({"email": super_admin_email})
    if not existing:
        hashed = bcrypt.hashpw(super_admin_password.encode('utf-8'), bcrypt.gensalt())
        await db.super_admins.insert_one({
            "id": str(uuid.uuid4()),
            "email": super_admin_email,
            "password": hashed.decode('utf-8'),
            "created_at": datetime.now(timezone.utc).isoformat()
        })

@api_router.get("/")
async def root():
    return {"message": "Seva Setu Bot API", "status": "running"}

api_router.include_router(auth_router)
api_router.include_router(super_admin_router)
api_router.include_router(local_admin_router)
api_router.include_router(consular_router)
api_router.include_router(whatsapp_router)
api_router.include_router(facebook_router)
api_router.include_router(template_router)
api_router.include_router(monitoring_router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)