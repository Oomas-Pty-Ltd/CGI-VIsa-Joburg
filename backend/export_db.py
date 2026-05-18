#!/usr/bin/env python3
"""
MongoDB Database Export Script
Exports all collections to JSON files for backup/migration
"""
import asyncio
import json
import os
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId, json_util
from dotenv import load_dotenv

load_dotenv()

# Custom JSON encoder for MongoDB types
class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)

async def export_database():
    """Export all collections from MongoDB to JSON files"""
    
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')
    
    print(f"Connecting to MongoDB: {mongo_url}")
    print(f"Database: {db_name}")
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Create export directory
    export_dir = f"/app/db_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(export_dir, exist_ok=True)
    print(f"\nExport directory: {export_dir}\n")
    
    # Get all collection names
    collections = await db.list_collection_names()
    
    if not collections:
        print("No collections found in the database.")
        return
    
    print(f"Found {len(collections)} collections: {collections}\n")
    print("=" * 60)
    
    # Export each collection
    total_docs = 0
    export_summary = {}
    
    for collection_name in collections:
        collection = db[collection_name]
        documents = await collection.find({}).to_list(length=None)
        doc_count = len(documents)
        total_docs += doc_count
        
        # Export to JSON file
        file_path = os.path.join(export_dir, f"{collection_name}.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(documents, f, cls=MongoJSONEncoder, indent=2, ensure_ascii=False)
        
        export_summary[collection_name] = doc_count
        print(f"✓ {collection_name}: {doc_count} documents -> {file_path}")
    
    # Create a summary file
    summary = {
        "export_date": datetime.now().isoformat(),
        "database": db_name,
        "mongo_url": mongo_url,
        "total_collections": len(collections),
        "total_documents": total_docs,
        "collections": export_summary
    }
    
    summary_path = os.path.join(export_dir, "_export_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    
    print("=" * 60)
    print(f"\n✅ Export Complete!")
    print(f"   Total Collections: {len(collections)}")
    print(f"   Total Documents: {total_docs}")
    print(f"   Export Directory: {export_dir}")
    print(f"   Summary File: {summary_path}")
    
    # Also create a schema overview
    schema_path = os.path.join(export_dir, "_schema_overview.json")
    schema = {}
    
    for collection_name in collections:
        collection = db[collection_name]
        sample_doc = await collection.find_one({})
        if sample_doc:
            schema[collection_name] = {
                "fields": list(sample_doc.keys()),
                "sample_types": {k: type(v).__name__ for k, v in sample_doc.items()}
            }
    
    with open(schema_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2)
    
    print(f"   Schema Overview: {schema_path}")
    
    client.close()
    return export_dir

if __name__ == "__main__":
    asyncio.run(export_database())
