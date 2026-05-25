"""
====================================================================
SEVA SETU BOT - AUDIT TRAIL SERVICE
====================================================================
Comprehensive audit logging for:
- User actions
- Admin operations
- Security events
- Data access
- Compliance tracking (GDPR, POPIA, DPDA)
====================================================================
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
import uuid
import hashlib

logger = logging.getLogger(__name__)


class AuditCategory(str, Enum):
    AUTH = "auth"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    DATA_DELETION = "data_deletion"
    DATA_EXPORT = "data_export"
    ADMIN_ACTION = "admin_action"
    SECURITY_EVENT = "security_event"
    SYSTEM_EVENT = "system_event"
    CONSENT = "consent"
    API_ACCESS = "api_access"


class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditEntry(BaseModel):
    id: str
    timestamp: str
    category: AuditCategory
    severity: AuditSeverity
    action: str
    user_id: Optional[str] = None
    user_type: Optional[str] = None  # super_admin, local_admin, user, guest
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource_type: Optional[str] = None  # document, profile, session, etc.
    resource_id: Optional[str] = None
    company_id: Optional[str] = None
    old_value: Optional[Dict[str, Any]] = None  # For modifications
    new_value: Optional[Dict[str, Any]] = None  # For modifications
    metadata: Optional[Dict[str, Any]] = None
    success: bool = True
    error_message: Optional[str] = None
    compliance_tags: List[str] = []  # GDPR, POPIA, DPDA


class AuditService:
    def __init__(self):
        self.sensitive_fields = {
            'password', 'token', 'api_key', 'secret', 'credit_card',
            'aadhaar', 'pan', 'passport_number', 'ssn', 'id_number'
        }
    
    def _mask_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive fields in audit data"""
        if not data:
            return data
        
        masked = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in self.sensitive_fields):
                if isinstance(value, str) and len(value) > 4:
                    masked[key] = value[:2] + '*' * (len(value) - 4) + value[-2:]
                else:
                    masked[key] = '***MASKED***'
            elif isinstance(value, dict):
                masked[key] = self._mask_sensitive_data(value)
            else:
                masked[key] = value
        
        return masked
    
    # ── Integrity hash versions ────────────────────────────────────────────
    # v1 (legacy): id|timestamp|category|action|user_id  — pre-Sprint-12 rows.
    #              No company_id, so a DB-write attacker could conceptually
    #              move a row between tenants without breaking the hash.
    # v2 (Sprint 12 hardening): same fields + company_id, prefixed "v2:" so
    #              ``verify_integrity`` can route to the right algorithm.
    # New writes use v2. ``verify_integrity`` accepts either based on the
    # stored ``hash_version`` field (absent ⇒ v1, for back-compat).
    INTEGRITY_HASH_VERSION = "v2"

    def _compute_integrity_hash_v1(self, entry: AuditEntry) -> str:
        data = f"{entry.id}|{entry.timestamp}|{entry.category}|{entry.action}|{entry.user_id}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _compute_integrity_hash_v2(self, entry: AuditEntry) -> str:
        data = (
            f"v2|{entry.id}|{entry.timestamp}|{entry.category}|{entry.action}|"
            f"{entry.user_id}|{entry.company_id}"
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _compute_integrity_hash(self, entry: AuditEntry) -> str:
        """Compute the canonical (current) integrity hash for a new entry."""
        return self._compute_integrity_hash_v2(entry)
    
    async def log(
        self,
        db,
        category: AuditCategory,
        action: str,
        user_id: Optional[str] = None,
        user_type: Optional[str] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        company_id: Optional[str] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        compliance_tags: List[str] = None
    ) -> AuditEntry:
        """
        Create an audit log entry.
        
        Args:
            category: Type of audit event
            action: Specific action taken (e.g., "login", "view_document", "update_profile")
            user_id: ID of user performing action
            user_type: Type of user (super_admin, local_admin, user, guest)
            session_id: Current session ID
            ip_address: Client IP address
            user_agent: Client user agent string
            resource_type: Type of resource being accessed/modified
            resource_id: ID of the resource
            old_value: Previous value (for modifications)
            new_value: New value (for modifications)
            metadata: Additional context
            success: Whether action succeeded
            error_message: Error message if failed
            severity: Log severity level
            compliance_tags: Applicable compliance frameworks
        """
        
        # Mask sensitive data
        masked_old = self._mask_sensitive_data(old_value) if old_value else None
        masked_new = self._mask_sensitive_data(new_value) if new_value else None
        masked_metadata = self._mask_sensitive_data(metadata) if metadata else None
        
        entry = AuditEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=category,
            severity=severity,
            action=action,
            user_id=user_id,
            user_type=user_type,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            company_id=company_id,
            old_value=masked_old,
            new_value=masked_new,
            metadata=masked_metadata,
            success=success,
            error_message=error_message,
            compliance_tags=compliance_tags or []
        )
        
        # Add integrity hash + version tag so verify_integrity can route
        # to the right algorithm for legacy v1 rows.
        entry_dict = entry.model_dump()
        entry_dict['integrity_hash'] = self._compute_integrity_hash(entry)
        entry_dict['hash_version']   = self.INTEGRITY_HASH_VERSION
        
        # Store in MongoDB
        await db.audit_logs.insert_one(entry_dict)
        
        # Also log to application logger for centralized logging
        log_msg = f"[AUDIT] {category.value}:{action} user={user_id} resource={resource_type}:{resource_id} success={success}"
        if severity == AuditSeverity.CRITICAL:
            logger.critical(log_msg)
        elif severity == AuditSeverity.ERROR:
            logger.error(log_msg)
        elif severity == AuditSeverity.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
        
        return entry
    
    # Convenience methods for common audit events
    
    async def log_auth(
        self,
        db,
        action: str,  # login, logout, token_refresh, password_change
        user_id: str,
        user_type: str,
        ip_address: str,
        company_id: Optional[str] = None,
        success: bool = True,
        error_message: str = None,
        metadata: Dict[str, Any] = None
    ):
        """Log authentication events"""
        return await self.log(
            db=db,
            category=AuditCategory.AUTH,
            action=action,
            user_id=user_id,
            user_type=user_type,
            ip_address=ip_address,
            company_id=company_id,
            success=success,
            error_message=error_message,
            metadata=metadata,
            severity=AuditSeverity.WARNING if not success else AuditSeverity.INFO,
            compliance_tags=["GDPR", "POPIA", "DPDA"]
        )

    async def log_data_access(
        self,
        db,
        user_id: str,
        user_type: str,
        resource_type: str,
        resource_id: str,
        company_id: Optional[str] = None,
        ip_address: str = None,
        metadata: Dict[str, Any] = None
    ):
        """Log data access events (viewing records)"""
        return await self.log(
            db=db,
            category=AuditCategory.DATA_ACCESS,
            action="view",
            user_id=user_id,
            user_type=user_type,
            resource_type=resource_type,
            resource_id=resource_id,
            company_id=company_id,
            ip_address=ip_address,
            metadata=metadata,
            compliance_tags=["GDPR", "POPIA", "DPDA"]
        )

    async def log_data_modification(
        self,
        db,
        user_id: str,
        user_type: str,
        resource_type: str,
        resource_id: str,
        old_value: Dict[str, Any],
        new_value: Dict[str, Any],
        company_id: Optional[str] = None,
        ip_address: str = None,
        action: str = "update"
    ):
        """Log data modification events"""
        return await self.log(
            db=db,
            category=AuditCategory.DATA_MODIFICATION,
            action=action,
            user_id=user_id,
            user_type=user_type,
            resource_type=resource_type,
            resource_id=resource_id,
            old_value=old_value,
            new_value=new_value,
            company_id=company_id,
            ip_address=ip_address,
            compliance_tags=["GDPR", "POPIA", "DPDA"]
        )

    async def log_data_deletion(
        self,
        db,
        user_id: str,
        user_type: str,
        resource_type: str,
        resource_id: str,
        company_id: Optional[str] = None,
        deleted_data: Dict[str, Any] = None,
        ip_address: str = None,
        reason: str = None
    ):
        """Log data deletion events (important for GDPR)"""
        return await self.log(
            db=db,
            category=AuditCategory.DATA_DELETION,
            action="delete",
            user_id=user_id,
            user_type=user_type,
            resource_type=resource_type,
            resource_id=resource_id,
            company_id=company_id,
            old_value=deleted_data,
            metadata={"reason": reason} if reason else None,
            ip_address=ip_address,
            severity=AuditSeverity.WARNING,
            compliance_tags=["GDPR", "POPIA", "DPDA"]
        )

    async def log_data_export(
        self,
        db,
        user_id: str,
        user_type: str,
        export_type: str,  # full, partial, documents, etc.
        company_id: Optional[str] = None,
        ip_address: str = None,
        metadata: Dict[str, Any] = None
    ):
        """Log data export events (GDPR right to portability)"""
        return await self.log(
            db=db,
            category=AuditCategory.DATA_EXPORT,
            action="export",
            user_id=user_id,
            user_type=user_type,
            company_id=company_id,
            metadata={"export_type": export_type, **(metadata or {})},
            ip_address=ip_address,
            compliance_tags=["GDPR", "POPIA", "DPDA"]
        )

    async def log_security_event(
        self,
        db,
        action: str,  # rate_limit_exceeded, invalid_token, injection_attempt, etc.
        ip_address: str,
        user_id: str = None,
        company_id: Optional[str] = None,
        metadata: Dict[str, Any] = None,
        severity: AuditSeverity = AuditSeverity.WARNING
    ):
        """Log security-related events"""
        return await self.log(
            db=db,
            category=AuditCategory.SECURITY_EVENT,
            action=action,
            user_id=user_id,
            company_id=company_id,
            ip_address=ip_address,
            metadata=metadata,
            severity=severity,
            compliance_tags=["SECURITY"]
        )

    async def log_consent(
        self,
        db,
        user_id: str,
        consent_type: str,  # data_processing, marketing, cookies, etc.
        granted: bool,
        company_id: Optional[str] = None,
        ip_address: str = None,
        metadata: Dict[str, Any] = None
    ):
        """Log consent events (GDPR requirement)"""
        return await self.log(
            db=db,
            category=AuditCategory.CONSENT,
            action="consent_update",
            user_id=user_id,
            company_id=company_id,
            new_value={"consent_type": consent_type, "granted": granted},
            ip_address=ip_address,
            metadata=metadata,
            compliance_tags=["GDPR", "POPIA", "DPDA"]
        )
    
    async def get_user_audit_trail(
        self,
        db,
        user_id: str,
        company_id: str,
        limit: int = 100,
        category: AuditCategory = None
    ) -> List[Dict[str, Any]]:
        """Get audit trail for a specific user, scoped to the calling tenant.

        Tenant scoping is mandatory — without it, a local_admin from tenant A
        could read user records belonging to tenant B. See Sprint 2 audit."""
        query: Dict[str, Any] = {"user_id": user_id, "company_id": company_id}
        if category:
            query["category"] = category.value

        cursor = db.audit_logs.find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit)

        return await cursor.to_list(length=limit)

    async def get_security_events(
        self,
        db,
        company_id: str,
        hours: int = 24,
        severity: AuditSeverity = None
    ) -> List[Dict[str, Any]]:
        """Get recent security events for one tenant only.

        Cross-tenant security visibility is a super-admin concern and goes
        through `super_admin_routes` (which can query without scope); local
        admins must only see events from their own tenant."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        query: Dict[str, Any] = {
            "category": AuditCategory.SECURITY_EVENT.value,
            "company_id": company_id,
            "timestamp": {"$gte": cutoff}
        }
        if severity:
            query["severity"] = severity.value

        cursor = db.audit_logs.find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1)

        return await cursor.to_list(length=1000)

    async def verify_integrity(self, db, audit_id: str, company_id: str) -> bool:
        """Verify audit entry hasn't been tampered with.

        Tenant-scoped so a local admin can only verify entries owned by their
        own tenant — same record-disclosure concern as the other queries.

        Routes to the right algorithm based on the stored ``hash_version``:
          - v2 (current, Sprint-12 hardening): includes company_id in the
            hash so a DB-write attacker can't move a row between tenants
            undetected.
          - missing / "v1" (legacy rows): the pre-hardening format. These
            still verify correctly against their own format but offer no
            defence against the cross-tenant move attack.
        """
        doc = await db.audit_logs.find_one(
            {"id": audit_id, "company_id": company_id}, {"_id": 0}
        )
        if not doc:
            return False

        stored_hash    = doc.pop('integrity_hash', None)
        stored_version = doc.pop('hash_version', None) or "v1"
        entry = AuditEntry(**doc)

        if stored_version == "v2":
            computed_hash = self._compute_integrity_hash_v2(entry)
        else:
            computed_hash = self._compute_integrity_hash_v1(entry)

        return stored_hash == computed_hash


# Singleton instance
audit_service = AuditService()
