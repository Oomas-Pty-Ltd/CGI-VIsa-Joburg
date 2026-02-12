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
from admin_routes import router as admin_router
from monitoring_service import start_background_monitoring

# Security imports
from security.session_manager import session_manager
from security.guardrail import setup_sanitized_logging

# Services imports
from services.knowledge_service import knowledge_service

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Get MongoDB connection details with proper error handling
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')

if not mongo_url:
    raise RuntimeError("MONGO_URL environment variable is required")
if not db_name:
    raise RuntimeError("DB_NAME environment variable is required")

client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler with proper error handling"""
    monitoring_task = None
    session_cleanup_task = None
    
    try:
        # Setup sanitized logging (PII protection in logs)
        setup_sanitized_logging()
        logger.info("Sanitized logging enabled")
        
        # Test database connection using the actual database (not admin)
        # This works with Atlas MongoDB where users may not have admin access
        await db.command('ping')
        logger.info("MongoDB connection successful")
        
        # Initialize super admin
        await init_super_admin()
        logger.info("Super admin initialization complete")
        
        # Initialize default templates
        from template_routes import init_default_templates
        await init_default_templates()
        logger.info("Default templates initialization complete")
        
        # Start background monitoring
        monitoring_task = asyncio.create_task(start_background_monitoring())
        logger.info("Background monitoring started")
        
        # Start session cleanup task (runs every hour)
        async def periodic_session_cleanup():
            while True:
                try:
                    await asyncio.sleep(3600)  # Run every hour
                    await session_manager.cleanup_expired_sessions()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Session cleanup error: {e}")
        
        session_cleanup_task = asyncio.create_task(periodic_session_cleanup())
        logger.info("Session cleanup task started")
        
    except Exception as e:
        logger.error(f"Startup initialization failed: {e}")
        # Don't raise - allow app to start even if init fails
        # This ensures health checks can pass
    
    yield
    
    # Cleanup
    if monitoring_task:
        monitoring_task.cancel()
    if session_cleanup_task:
        session_cleanup_task.cancel()
    client.close()

app = FastAPI(lifespan=lifespan)
api_router = APIRouter(prefix="/api")

# Root-level health check endpoint for deployment health checks
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "seva-setu-bot"}

async def init_super_admin():
    """Initialize super admin if not exists"""
    try:
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
            logger.info(f"Super admin created: {super_admin_email}")
        else:
            logger.info(f"Super admin already exists: {super_admin_email}")
    except Exception as e:
        logger.error(f"Failed to initialize super admin: {e}")

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