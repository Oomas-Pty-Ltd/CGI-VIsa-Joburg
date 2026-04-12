from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Get MongoDB connection details with proper error handling
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')

if not mongo_url:
    raise RuntimeError("MONGO_URL environment variable is required")
if not db_name:
    raise RuntimeError("DB_NAME environment variable is required")

# Connection pooling configuration
client = AsyncIOMotorClient(
    mongo_url,
    maxPoolSize=50,  # Maximum connections in the pool
    minPoolSize=10,  # Minimum connections to maintain
    maxIdleTimeMS=30000,  # Close idle connections after 30s
    waitQueueTimeoutMS=10000,  # Timeout waiting for available connection
    serverSelectionTimeoutMS=5000  # Timeout for server selection
)
db = client[db_name]

async def get_database():
    return db


async def create_indexes():
    """Create database indexes for performance optimization"""
    try:
        # User indexes
        await db.users.create_index("id", unique=True)
        await db.users.create_index("email", unique=True, sparse=True)
        await db.users.create_index("phone", sparse=True)
        
        # Session indexes
        await db.chat_sessions.create_index("id", unique=True)
        await db.chat_sessions.create_index("user_id")
        await db.chat_sessions.create_index("session_id")
        await db.chat_sessions.create_index("created_at")
        await db.chat_sessions.create_index("company_id")
        await db.chat_sessions.create_index([("company_id", 1), ("created_at", -1)])
        await db.chat_sessions.create_index([("user_id", 1), ("created_at", -1)])
        
        # Document indexes
        await db.documents.create_index("id", unique=True)
        await db.documents.create_index("user_id")
        await db.documents.create_index("expiry_status")
        await db.documents.create_index("next_check_date")
        
        # Feedback indexes
        await db.feedback.create_index("id", unique=True)
        await db.feedback.create_index("session_id")
        await db.feedback.create_index("user_id")
        await db.feedback.create_index("created_at")
        
        # Notification indexes
        await db.notifications.create_index("id", unique=True)
        await db.notifications.create_index("user_id")
        await db.notifications.create_index([("user_id", 1), ("status", 1)])
        await db.notifications.create_index("scheduled_at")
        
        # Audit log indexes
        await db.audit_logs.create_index("id", unique=True)
        await db.audit_logs.create_index("user_id")
        await db.audit_logs.create_index("company_id")
        await db.audit_logs.create_index("timestamp")
        await db.audit_logs.create_index([("category", 1), ("timestamp", -1)])
        await db.audit_logs.create_index([("user_id", 1), ("timestamp", -1)])
        await db.audit_logs.create_index([("company_id", 1), ("timestamp", -1)])
        
        # Escalation indexes
        await db.escalations.create_index("id", unique=True)
        await db.escalations.create_index("status")
        await db.escalations.create_index("priority")
        await db.escalations.create_index([("status", 1), ("created_at", -1)])
        
        # Knowledge base indexes
        await db.knowledge_base.create_index("id", unique=True)
        await db.knowledge_base.create_index("category")
        await db.knowledge_base.create_index([("title", "text"), ("question", "text"), ("answer", "text")])
        
        # WhatsApp session indexes
        await db.whatsapp_sessions.create_index("phone_hash", unique=True)
        await db.whatsapp_sessions.create_index("session_id")
        await db.whatsapp_sessions.create_index("last_message_at")
        
        # ICS WABA indexes
        await db.ics_whatsapp_sessions.create_index("phone_number", unique=True)
        await db.ics_whatsapp_sessions.create_index("updated_at")
        await db.ics_whatsapp_messages.create_index("phone_number")
        await db.ics_whatsapp_messages.create_index("timestamp")
        await db.ics_whatsapp_messages.create_index("ics_mid", sparse=True)

        # Rate limit indexes (for persistence when Redis is available)
        await db.rate_limits.create_index("key", unique=True)
        await db.rate_limits.create_index("expires_at", expireAfterSeconds=0)  # TTL index
        
        # Token invalidation indexes
        await db.invalidated_tokens.create_index("user_id")
        await db.invalidated_tokens.create_index("invalidated_at")
        
        # Data requests (GDPR)
        await db.data_requests.create_index("id", unique=True)
        await db.data_requests.create_index("user_id")
        await db.data_requests.create_index([("user_id", 1), ("request_type", 1)])

        # Application tracking indexes
        await db.applications.create_index("id", unique=True)
        await db.applications.create_index("tracking_id", unique=True)
        await db.applications.create_index("session_id")
        await db.applications.create_index("user_id")
        await db.applications.create_index("service")
        await db.applications.create_index("status")
        await db.applications.create_index([("user_id", 1), ("created_at", -1)])
        await db.applications.create_index([("status", 1), ("created_at", -1)])

        logger.info("Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"Failed to create indexes: {e}")
        # Don't raise - allow app to continue without indexes