from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

# Get MongoDB connection details with proper error handling
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')

if not mongo_url:
    raise RuntimeError("MONGO_URL environment variable is required")
if not db_name:
    raise RuntimeError("DB_NAME environment variable is required")

client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

async def get_database():
    return db