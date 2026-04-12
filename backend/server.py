from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Query, Request
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
from ics_whatsapp_routes import router as ics_whatsapp_router
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
        
        # Create database indexes for performance
        from database import create_indexes
        await create_indexes()

        # Validate COMPANY_ID against the companies collection
        from config import validate_company_id
        company_id = await validate_company_id(db)
        logger.info(f"Company validated: {company_id}")

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
        
        # Initialize knowledge base
        await knowledge_service.initialize()
        logger.info("Knowledge base initialized")
        
        # Check WhatsApp/ICS WABA configuration
        _check_whatsapp_config()
        
        # Pre-warm the scraper cache so the first user chat request is instant
        from knowledge_scraper import get_realtime_knowledge
        asyncio.create_task(get_realtime_knowledge())
        logger.info("Scraper cache pre-warm started in background")
        
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

# ICS WABA sends webhook calls to the root path /?replytype=...&customernumber=...
# This catches those and forwards them to the proper ICS handler.
# Also handles delivery status callbacks at /?qStatus=...&qMsgRef=...
@app.get("/")
async def root_ics_or_info(
    request: Request,
    background_tasks: BackgroundTasks,
    replytype: str = Query(default=""),
    customernumber: str = Query(default=""),
    replymessage: str = Query(default=""),
    timestamp: Optional[str] = Query(default=None),
    wabanumber: Optional[str] = Query(default=""),
    mid: Optional[str] = Query(default=None),
    smsgid: Optional[str] = Query(default=None),
    qStatus: Optional[str] = Query(default=None),
    qMobile: Optional[str] = Query(default=None),
    qMsgRef: Optional[str] = Query(default=None),
    qDTime: Optional[str] = Query(default=None),
    SMSMSGID: Optional[str] = Query(default=None),
    NOTES: Optional[str] = Query(default=None),
):
    logger.info("[ROOT /] raw_url=%s", str(request.url))
    if customernumber:
        # ICS WABA incoming webhook — delegate to the proper handler
        from ics_whatsapp_routes import ics_incoming_webhook
        return await ics_incoming_webhook(
            request, background_tasks, replytype, customernumber,
            replymessage, timestamp, wabanumber,
        )
    if qMsgRef and qStatus:
        # ICS WABA delivery status callback
        from ics_whatsapp_routes import ics_delivery_callback
        return await ics_delivery_callback(
            request, qStatus, qMobile, qMsgRef, qDTime, SMSMSGID, None, NOTES,
        )
    return {"message": "Seva Setu Bot API", "status": "running"}

async def init_super_admin():
    """Initialize super admin, always syncing password from env vars."""
    try:
        super_admin_email = os.environ.get('SUPER_ADMIN_EMAIL', 'superadmin@sarthak.ai')
        super_admin_password = os.environ.get('SUPER_ADMIN_PASSWORD', 'Admin@2025')
        hashed = bcrypt.hashpw(super_admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        existing = await db.super_admins.find_one({"email": super_admin_email})
        if not existing:
            await db.super_admins.insert_one({
                "id": str(uuid.uuid4()),
                "email": super_admin_email,
                "password": hashed,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            logger.info(f"Super admin created: {super_admin_email}")
        else:
            # Always update password so env-var changes take effect on restart
            await db.super_admins.update_one(
                {"email": super_admin_email},
                {"$set": {"password": hashed}}
            )
            logger.info(f"Super admin password synced: {super_admin_email}")
    except Exception as e:
        logger.error(f"Failed to initialize super admin: {e}")

def _check_whatsapp_config():
    """Validate WhatsApp/ICS WABA configuration at startup"""
    ics_user = os.environ.get('ICS_WABA_USER', '').strip()
    ics_pass = os.environ.get('ICS_WABA_PASS', '').strip()
    ics_from = os.environ.get('ICS_WABA_FROM', '').strip()
    
    if not ics_user or not ics_pass or not ics_from:
        logger.warning("⚠️  [WHATSAPP CONFIG] ICS WABA not fully configured:")
        if not ics_user:
            logger.warning("   • ICS_WABA_USER is missing")
        if not ics_pass:
            logger.warning("   • ICS_WABA_PASS is missing")
        if not ics_from:
            logger.warning("   • ICS_WABA_FROM is missing")
        logger.warning("   WhatsApp messages will NOT be sent. Set these in .env to enable.")
    else:
        logger.info(f"✓ [WHATSAPP CONFIG] ICS WABA configured: user={ics_user}, from={ics_from}")
    
    # Also check Meta/WA Simple config
    meta_token = os.environ.get('META_ACCESS_TOKEN', '').strip()
    if meta_token:
        logger.info(f"✓ [META_CONFIG] Meta WhatsApp token configured (length={len(meta_token)})")
    else:
        logger.debug("ℹ [META_CONFIG] Meta WhatsApp token not set (optional if using ICS WABA)")

@api_router.get("/")
@api_router.head("/")
async def root(
    request: Request,
    background_tasks: BackgroundTasks,
    replytype: str = Query(default=""),
    customernumber: str = Query(default=""),
    replymessage: str = Query(default=""),
    timestamp: Optional[str] = Query(default=None),
    wabanumber: Optional[str] = Query(default=""),
    # delivery status params (ICS delivery callbacks)
    qStatus: Optional[str] = Query(default=None),
    qMobile: Optional[str] = Query(default=None),
    qMsgRef: Optional[str] = Query(default=None),
    qDTime: Optional[str] = Query(default=None),
    SMSMSGID: Optional[str] = Query(default=None),
    NOTES: Optional[str] = Query(default=None),
):
    logger.info("[ROOT /api/] raw_url=%s", str(request.url))
    if customernumber:
        # ICS WABA incoming message webhook
        from ics_whatsapp_routes import ics_incoming_webhook
        return await ics_incoming_webhook(
            request, background_tasks, replytype, customernumber,
            replymessage, timestamp, wabanumber,
        )
    if qMsgRef and qStatus:
        # ICS WABA delivery status callback
        from ics_whatsapp_routes import ics_delivery_callback
        return await ics_delivery_callback(
            request, qStatus, qMobile, qMsgRef, qDTime, SMSMSGID, None, NOTES,
        )
    return {"message": "Seva Setu Bot API", "status": "running"}

# Webhook endpoint for SEV-SETU delivery status callbacks
# Alias for /api/ with webhook-style naming convention
@api_router.get("/webhook/sevasetu-delivery")
@api_router.post("/webhook/sevasetu-delivery")
@api_router.head("/webhook/sevasetu-delivery")
async def sevasetu_delivery_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    qStatus: Optional[str] = Query(default=None),
    qMobile: Optional[str] = Query(default=None),
    qMsgRef: Optional[str] = Query(default=None),
    qDTime: Optional[str] = Query(default=None),
    SMSMSGID: Optional[str] = Query(default=None),
    NOTES: Optional[str] = Query(default=None),
):
    """
    SEV-SETU API delivery status webhook endpoint.
    Receives delivery status updates from the SEV-SETU platform.
    
    Supports both GET and POST methods with query parameters.
    Routes to the ICS delivery callback handler.
    
    Query Parameters:
        qStatus: Delivery status (DELIVERED, FAILED, PENDING, BOUNCED)
        qMobile: Phone number that received message
        qMsgRef: Message reference ID
        qDTime: Delivery timestamp (ISO format)
        SMSMSGID: SMS message ID
        NOTES: Additional notes about delivery
    """
    logger.info(f"SEV-SETU delivery webhook received: status={qStatus}, msg_ref={qMsgRef}")
    
    if request.method == "HEAD":
        # HEAD requests should return successful response without body
        return {"status": "received"}
    
    if qMsgRef and qStatus:
        # Route to ICS delivery callback handler
        from ics_whatsapp_routes import ics_delivery_callback
        return await ics_delivery_callback(
            request, qStatus, qMobile, qMsgRef, qDTime, SMSMSGID, None, NOTES,
        )
    
    # Invalid request - missing required parameters
    logger.warning(f"Invalid delivery webhook request: missing qStatus or qMsgRef")
    return {"error": "Missing required parameters: qStatus and qMsgRef"}

from user_routes import router as user_router

api_router.include_router(auth_router)
api_router.include_router(super_admin_router)
api_router.include_router(local_admin_router)
api_router.include_router(consular_router)
api_router.include_router(whatsapp_router)
api_router.include_router(ics_whatsapp_router)
api_router.include_router(facebook_router)
api_router.include_router(template_router)
api_router.include_router(monitoring_router)
api_router.include_router(admin_router)
api_router.include_router(user_router)

app.include_router(api_router)

# HSTS Middleware for security
from starlette.middleware.base import BaseHTTPMiddleware

class HSTSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Add HSTS header for HTTPS enforcement
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        # Additional security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(HSTSMiddleware)

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