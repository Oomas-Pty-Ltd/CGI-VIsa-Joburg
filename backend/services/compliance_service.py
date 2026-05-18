"""
====================================================================
SEVA SETU BOT - GDPR/POPIA/DPDA COMPLIANCE SERVICE
====================================================================
Handles data subject rights:
- Right to access (data export)
- Right to erasure (delete)
- Right to rectification (update)
- Right to portability (export in machine-readable format)
====================================================================
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import uuid
import json
import zipfile
import io
import base64

logger = logging.getLogger(__name__)


class DataExportRequest(BaseModel):
    id: str
    user_id: str
    request_type: str  # export, delete, rectify
    status: str  # pending, processing, completed, failed
    requested_at: str
    completed_at: Optional[str] = None
    download_url: Optional[str] = None
    download_expires_at: Optional[str] = None
    error_message: Optional[str] = None


class ComplianceService:
    def __init__(self):
        self.collections_to_export = [
            'users',
            'chat_sessions',
            'documents',
            'feedback',
            'notifications',
            'audit_logs'
        ]
        
        self.collections_to_delete = [
            'chat_sessions',
            'documents', 
            'feedback',
            'notifications',
            # Note: audit_logs are retained for compliance
        ]
    
    async def create_export_request(
        self,
        db,
        user_id: str
    ) -> DataExportRequest:
        """Create a data export request (GDPR Article 15 & 20)"""
        
        request = DataExportRequest(
            id=str(uuid.uuid4()),
            user_id=user_id,
            request_type="export",
            status="pending",
            requested_at=datetime.now(timezone.utc).isoformat()
        )
        
        await db.data_requests.insert_one(request.model_dump())
        
        logger.info(f"[GDPR] Export request created: {request.id} for user {user_id}")
        
        return request
    
    async def process_export_request(
        self,
        db,
        request_id: str
    ) -> Dict[str, Any]:
        """Process and generate data export"""
        
        # Get request
        request_doc = await db.data_requests.find_one({"id": request_id}, {"_id": 0})
        if not request_doc:
            return {"success": False, "error": "Request not found"}
        
        user_id = request_doc['user_id']
        
        # Update status to processing
        await db.data_requests.update_one(
            {"id": request_id},
            {"$set": {"status": "processing"}}
        )
        
        try:
            export_data = {}
            
            # Collect data from each collection
            for collection_name in self.collections_to_export:
                collection = db[collection_name]
                
                # Find user's data
                cursor = collection.find(
                    {"$or": [
                        {"user_id": user_id},
                        {"id": user_id}  # For users collection
                    ]},
                    {"_id": 0, "password": 0}  # Exclude sensitive fields
                )
                
                docs = await cursor.to_list(length=10000)
                if docs:
                    export_data[collection_name] = docs
            
            # Create ZIP file with JSON data
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add main data file
                zip_file.writestr(
                    'user_data.json',
                    json.dumps(export_data, indent=2, default=str)
                )
                
                # Add metadata
                metadata = {
                    "export_id": request_id,
                    "user_id": user_id,
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "collections_included": list(export_data.keys()),
                    "total_records": sum(len(v) for v in export_data.values()),
                    "compliance_frameworks": ["GDPR", "POPIA", "DPDA"]
                }
                zip_file.writestr(
                    'metadata.json',
                    json.dumps(metadata, indent=2)
                )
                
                # Add README
                readme = """SEVA SETU BOT - DATA EXPORT
========================

This archive contains all personal data associated with your account.

Files:
- user_data.json: Your personal data in JSON format
- metadata.json: Export metadata

This export was generated in compliance with:
- GDPR (General Data Protection Regulation)
- POPIA (Protection of Personal Information Act)
- DPDA (Digital Personal Data Protection Act)

For questions, contact: privacy@sevasetu.gov.in
"""
                zip_file.writestr('README.txt', readme)
            
            # Encode ZIP as base64 for storage/download
            zip_buffer.seek(0)
            zip_base64 = base64.b64encode(zip_buffer.read()).decode('utf-8')
            
            # Update request with download info
            expires_at = (datetime.now(timezone.utc).replace(hour=23, minute=59, second=59) + 
                         __import__('datetime').timedelta(days=7)).isoformat()
            
            await db.data_requests.update_one(
                {"id": request_id},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "download_expires_at": expires_at
                    }
                }
            )
            
            # Store export data temporarily
            await db.data_exports.insert_one({
                "request_id": request_id,
                "user_id": user_id,
                "data_base64": zip_base64,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at
            })
            
            logger.info(f"[GDPR] Export completed: {request_id}, {sum(len(v) for v in export_data.values())} records")
            
            return {
                "success": True,
                "request_id": request_id,
                "records_exported": sum(len(v) for v in export_data.values()),
                "collections": list(export_data.keys())
            }
            
        except Exception as e:
            logger.error(f"[GDPR] Export failed: {str(e)}")
            await db.data_requests.update_one(
                {"id": request_id},
                {
                    "$set": {
                        "status": "failed",
                        "error_message": str(e)
                    }
                }
            )
            return {"success": False, "error": str(e)}
    
    async def download_export(
        self,
        db,
        request_id: str,
        user_id: str
    ) -> Optional[bytes]:
        """Download exported data"""
        
        export = await db.data_exports.find_one({
            "request_id": request_id,
            "user_id": user_id
        }, {"_id": 0})
        
        if not export:
            return None
        
        # Check expiry
        if export.get('expires_at'):
            expires = datetime.fromisoformat(export['expires_at'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expires:
                logger.warning(f"[GDPR] Export download expired: {request_id}")
                return None
        
        return base64.b64decode(export['data_base64'])
    
    async def create_deletion_request(
        self,
        db,
        user_id: str
    ) -> DataExportRequest:
        """Create a data deletion request (GDPR Article 17 - Right to Erasure)"""
        
        request = DataExportRequest(
            id=str(uuid.uuid4()),
            user_id=user_id,
            request_type="delete",
            status="pending",
            requested_at=datetime.now(timezone.utc).isoformat()
        )
        
        await db.data_requests.insert_one(request.model_dump())
        
        logger.info(f"[GDPR] Deletion request created: {request.id} for user {user_id}")
        
        return request
    
    async def process_deletion_request(
        self,
        db,
        request_id: str,
        confirm: bool = False
    ) -> Dict[str, Any]:
        """Process data deletion request"""
        
        if not confirm:
            return {"success": False, "error": "Deletion must be confirmed"}
        
        # Get request
        request_doc = await db.data_requests.find_one({"id": request_id}, {"_id": 0})
        if not request_doc:
            return {"success": False, "error": "Request not found"}
        
        user_id = request_doc['user_id']
        
        # Update status to processing
        await db.data_requests.update_one(
            {"id": request_id},
            {"$set": {"status": "processing"}}
        )
        
        try:
            deletion_results = {}
            
            for collection_name in self.collections_to_delete:
                collection = db[collection_name]
                
                # Delete user's data
                result = await collection.delete_many({
                    "$or": [
                        {"user_id": user_id},
                        {"id": user_id}
                    ]
                })
                
                deletion_results[collection_name] = result.deleted_count
            
            # Anonymize user record instead of deleting (for audit purposes)
            await db.users.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "email": f"deleted_{user_id[:8]}@anonymized.local",
                        "name": "Deleted User",
                        "phone": None,
                        "deleted_at": datetime.now(timezone.utc).isoformat(),
                        "is_deleted": True
                    }
                }
            )
            
            # Update request
            await db.data_requests.update_one(
                {"id": request_id},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            # Log deletion for audit (required even for deleted users)
            from services.audit_service import audit_service, AuditCategory
            await audit_service.log_data_deletion(
                db=db,
                user_id=user_id,
                user_type="user",
                resource_type="user_account",
                resource_id=user_id,
                deleted_data={"collections_affected": list(deletion_results.keys())},
                reason="GDPR Article 17 - Right to Erasure"
            )
            
            total_deleted = sum(deletion_results.values())
            logger.info(f"[GDPR] Deletion completed: {request_id}, {total_deleted} records deleted")
            
            return {
                "success": True,
                "request_id": request_id,
                "records_deleted": total_deleted,
                "breakdown": deletion_results
            }
            
        except Exception as e:
            logger.error(f"[GDPR] Deletion failed: {str(e)}")
            await db.data_requests.update_one(
                {"id": request_id},
                {
                    "$set": {
                        "status": "failed",
                        "error_message": str(e)
                    }
                }
            )
            return {"success": False, "error": str(e)}
    
    async def get_user_data_summary(
        self,
        db,
        user_id: str
    ) -> Dict[str, Any]:
        """Get summary of user's data (for transparency)"""
        
        summary = {
            "user_id": user_id,
            "data_collected": {},
            "last_activity": None,
            "consent_status": {},
            "data_requests": []
        }
        
        for collection_name in self.collections_to_export:
            collection = db[collection_name]
            count = await collection.count_documents({
                "$or": [
                    {"user_id": user_id},
                    {"id": user_id}
                ]
            })
            if count > 0:
                summary["data_collected"][collection_name] = count
        
        # Get pending requests
        cursor = db.data_requests.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("requested_at", -1).limit(10)
        
        summary["data_requests"] = await cursor.to_list(length=10)
        
        return summary
    
    async def invalidate_user_tokens(self, db, user_id: str):
        """Invalidate all tokens for a user (for logout everywhere)"""
        await db.invalidated_tokens.insert_one({
            "user_id": user_id,
            "invalidated_at": datetime.now(timezone.utc).isoformat(),
            "reason": "user_request"
        })
        
        logger.info(f"[AUTH] Invalidated all tokens for user {user_id}")


# Singleton instance
compliance_service = ComplianceService()
