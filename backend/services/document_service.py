"""
====================================================================
SEVA SETU BOT - DOCUMENT SERVICE
====================================================================
Handles document management with:
- Expiry tracking and 3-month recheck schedule
- AES-256 encryption at rest
- MIME type validation
- Size validation (<10MB)
====================================================================
"""

import os
import base64
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pydantic import BaseModel
from enum import Enum
import logging
import mimetypes

logger = logging.getLogger(__name__)


class DocumentStatus(str, Enum):
    VALID = "valid"
    EXPIRED = "expired"
    EXPIRING_SOON = "expiring_soon"  # Within 30 days
    NO_EXPIRY = "no_expiry"  # Expiry not available
    PENDING_CHECK = "pending_check"


class DocumentType(str, Enum):
    PASSPORT = "passport"
    VISA = "visa"
    OCI = "oci"
    AADHAAR = "aadhaar"
    PAN = "pan"
    DRIVING_LICENSE = "driving_license"
    BIRTH_CERTIFICATE = "birth_certificate"
    OTHER = "other"


# Allowed MIME types for document uploads
ALLOWED_MIME_TYPES = {
    'image/jpeg': ['.jpg', '.jpeg'],
    'image/png': ['.png'],
    'image/webp': ['.webp'],
    'image/heic': ['.heic'],
    'image/heif': ['.heif'],
    'application/pdf': ['.pdf'],
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class DocumentInfo(BaseModel):
    id: str
    user_id: str
    session_id: Optional[str] = None
    document_type: DocumentType
    filename: str
    mime_type: str
    size_bytes: int
    expiry_date: Optional[str] = None  # ISO format or None if not captured
    expiry_status: DocumentStatus = DocumentStatus.PENDING_CHECK
    next_check_date: str  # ISO format - when to recheck expiry
    encrypted: bool = True
    encryption_key_id: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str
    last_checked_at: Optional[str] = None


class DocumentService:
    def __init__(self):
        self._encryption_key = None
        self._fernet = None
        self._init_encryption()
    
    def _init_encryption(self):
        """Initialize AES-256 encryption using Fernet"""
        # Get or generate encryption key
        key_env = os.environ.get('DOCUMENT_ENCRYPTION_KEY')
        
        if key_env:
            # Use provided key (should be base64-encoded 32-byte key)
            self._encryption_key = key_env.encode()
        else:
            # Generate key from JWT_SECRET as fallback (not recommended for production)
            jwt_secret = os.environ.get('JWT_SECRET', 'default-secret-change-me')
            salt = b'seva_setu_doc_salt_v1'
            
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(jwt_secret.encode()))
            self._encryption_key = key
            logger.warning("[SECURITY] Using derived encryption key. Set DOCUMENT_ENCRYPTION_KEY for production.")
        
        self._fernet = Fernet(self._encryption_key)
    
    def validate_file(self, content_type: str, file_size: int, filename: str) -> Dict[str, Any]:
        """
        Validate file upload against security requirements.
        
        Returns:
            dict with 'valid', 'error', and 'details'
        """
        result = {
            'valid': True,
            'error': None,
            'details': {
                'mime_type': content_type,
                'size_bytes': file_size,
                'filename': filename
            }
        }
        
        # Check MIME type
        if content_type not in ALLOWED_MIME_TYPES:
            result['valid'] = False
            result['error'] = f"Invalid file type: {content_type}. Allowed: {', '.join(ALLOWED_MIME_TYPES.keys())}"
            logger.warning(f"[DOCUMENT] Rejected invalid MIME type: {content_type}")
            return result
        
        # Check file extension matches MIME type
        ext = os.path.splitext(filename)[1].lower() if filename else ''
        allowed_exts = ALLOWED_MIME_TYPES.get(content_type, [])
        if ext and ext not in allowed_exts:
            result['valid'] = False
            result['error'] = f"File extension {ext} doesn't match content type {content_type}"
            logger.warning(f"[DOCUMENT] Extension mismatch: {ext} vs {content_type}")
            return result
        
        # Check file size
        if file_size > MAX_FILE_SIZE:
            result['valid'] = False
            result['error'] = f"File too large: {file_size / (1024*1024):.2f}MB. Maximum: 10MB"
            logger.warning(f"[DOCUMENT] File too large: {file_size} bytes")
            return result
        
        if file_size == 0:
            result['valid'] = False
            result['error'] = "Empty file uploaded"
            return result
        
        logger.info(f"[DOCUMENT] File validated: {filename} ({content_type}, {file_size} bytes)")
        return result
    
    def encrypt_document(self, data: bytes) -> tuple[bytes, str]:
        """
        Encrypt document data using AES-256 (Fernet).
        
        Returns:
            tuple of (encrypted_data, key_id)
        """
        encrypted = self._fernet.encrypt(data)
        key_id = hashlib.sha256(self._encryption_key).hexdigest()[:16]
        logger.info(f"[DOCUMENT] Document encrypted with key_id: {key_id}")
        return encrypted, key_id
    
    def decrypt_document(self, encrypted_data: bytes) -> bytes:
        """Decrypt document data"""
        try:
            return self._fernet.decrypt(encrypted_data)
        except Exception as e:
            logger.error(f"[DOCUMENT] Decryption failed: {str(e)}")
            raise ValueError("Failed to decrypt document")
    
    def calculate_expiry_status(self, expiry_date: Optional[str]) -> tuple[DocumentStatus, str]:
        """
        Calculate document expiry status and next check date.
        
        Returns:
            tuple of (status, next_check_date_iso)
        """
        today = datetime.now(timezone.utc).date()
        
        if not expiry_date or expiry_date.lower() in ['nil', 'n/a', 'not available', '']:
            # No expiry captured - schedule recheck in 3 months
            next_check = today + timedelta(days=90)
            return DocumentStatus.NO_EXPIRY, next_check.isoformat()
        
        try:
            # Parse expiry date (support multiple formats)
            expiry = None
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d']:
                try:
                    expiry = datetime.strptime(expiry_date, fmt).date()
                    break
                except ValueError:
                    continue
            
            if not expiry:
                # Could not parse - treat as no expiry
                next_check = today + timedelta(days=90)
                return DocumentStatus.NO_EXPIRY, next_check.isoformat()
            
            # Calculate days until expiry
            days_until_expiry = (expiry - today).days
            
            if days_until_expiry < 0:
                # Already expired
                return DocumentStatus.EXPIRED, today.isoformat()
            elif days_until_expiry <= 30:
                # Expiring within 30 days
                return DocumentStatus.EXPIRING_SOON, expiry.isoformat()
            else:
                # Valid - recheck 30 days before expiry or in 3 months, whichever is sooner
                recheck_before_expiry = expiry - timedelta(days=30)
                recheck_3_months = today + timedelta(days=90)
                next_check = min(recheck_before_expiry, recheck_3_months)
                return DocumentStatus.VALID, next_check.isoformat()
                
        except Exception as e:
            logger.error(f"[DOCUMENT] Error parsing expiry date '{expiry_date}': {e}")
            next_check = today + timedelta(days=90)
            return DocumentStatus.NO_EXPIRY, next_check.isoformat()
    
    async def create_document_record(
        self,
        db,
        user_id: str,
        document_type: DocumentType,
        filename: str,
        mime_type: str,
        size_bytes: int,
        encrypted_data: bytes,
        encryption_key_id: str,
        expiry_date: Optional[str] = None,
        session_id: Optional[str] = None,
        extracted_data: Optional[Dict[str, Any]] = None
    ) -> DocumentInfo:
        """Create a new document record in MongoDB"""
        
        now = datetime.now(timezone.utc).isoformat()
        expiry_status, next_check = self.calculate_expiry_status(expiry_date)
        
        doc = DocumentInfo(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            document_type=document_type,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            expiry_date=expiry_date if expiry_date and expiry_date.lower() not in ['nil', 'n/a', ''] else None,
            expiry_status=expiry_status,
            next_check_date=next_check,
            encrypted=True,
            encryption_key_id=encryption_key_id,
            extracted_data=extracted_data,
            created_at=now,
            updated_at=now,
            last_checked_at=now
        )
        
        # Store document metadata
        await db.documents.insert_one({
            **doc.model_dump(),
            "encrypted_content": base64.b64encode(encrypted_data).decode('utf-8')
        })
        
        logger.info(f"[DOCUMENT] Created document {doc.id} for user {user_id}, status: {expiry_status.value}")
        return doc
    
    async def check_documents_for_expiry(self, db) -> List[Dict[str, Any]]:
        """
        Check all documents that are due for expiry recheck.
        Called by scheduled job every day.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        
        # Find documents due for check
        cursor = db.documents.find({
            "next_check_date": {"$lte": today}
        }, {"_id": 0, "encrypted_content": 0})
        
        updated = []
        async for doc in cursor:
            new_status, new_check_date = self.calculate_expiry_status(doc.get('expiry_date'))
            
            await db.documents.update_one(
                {"id": doc['id']},
                {
                    "$set": {
                        "expiry_status": new_status.value,
                        "next_check_date": new_check_date,
                        "last_checked_at": datetime.now(timezone.utc).isoformat(),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            updated.append({
                "document_id": doc['id'],
                "user_id": doc['user_id'],
                "old_status": doc.get('expiry_status'),
                "new_status": new_status.value,
                "expiry_date": doc.get('expiry_date')
            })
            
            logger.info(f"[DOCUMENT] Updated expiry status for {doc['id']}: {new_status.value}")
        
        return updated
    
    async def get_user_documents(self, db, user_id: str) -> List[Dict[str, Any]]:
        """Get all documents for a user (without encrypted content)"""
        cursor = db.documents.find(
            {"user_id": user_id},
            {"_id": 0, "encrypted_content": 0}
        ).sort("created_at", -1)
        
        return await cursor.to_list(length=100)
    
    async def get_expiring_documents(self, db, days: int = 30) -> List[Dict[str, Any]]:
        """Get documents expiring within specified days"""
        cursor = db.documents.find({
            "expiry_status": {"$in": [DocumentStatus.EXPIRING_SOON.value, DocumentStatus.EXPIRED.value]}
        }, {"_id": 0, "encrypted_content": 0})
        
        return await cursor.to_list(length=100)


# Singleton instance
document_service = DocumentService()
