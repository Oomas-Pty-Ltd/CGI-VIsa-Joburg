from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Track if indexes have been created
_indexes_created = False

async def get_database():
    global _indexes_created
    if not _indexes_created:
        await create_indexes()
        _indexes_created = True
    return db

async def create_indexes():
    """Create indexes for better query performance"""
    try:
        # Conversations - frequently queried by session_id
        await db.conversations.create_index("session_id", unique=True)
        
        # Applications - queried by profile_id, status, application_id
        await db.applications.create_index("application_id", unique=True)
        await db.applications.create_index("profile_id")
        await db.applications.create_index("status")
        await db.applications.create_index([("created_at", -1)])
        
        # Chat sessions
        await db.chat_sessions.create_index("id", unique=True)
        await db.chat_sessions.create_index("user_id")
        
        # User profiles
        await db.user_profiles.create_index("profile_id", unique=True)
        await db.user_profiles.create_index("email")
        
        # Admin configs
        await db.admin_configs.create_index("company_id", unique=True)
        
        # Exception logs
        await db.exception_logs.create_index([("timestamp", -1)])
        await db.exception_logs.create_index("resolved")
        
        print("Database indexes created successfully")
    except Exception as e:
        print(f"Index creation warning: {e}")