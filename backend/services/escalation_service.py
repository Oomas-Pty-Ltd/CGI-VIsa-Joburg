"""
====================================================================
SEVA SETU BOT - ESCALATION SERVICE
====================================================================
Handles human handoff for complex cases:
- Escalation triggers
- Ticket creation
- Admin notifications
- Complaint logging
====================================================================
"""

import os
import uuid
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from database import get_database

logger = logging.getLogger(__name__)


class EscalationStatus(Enum):
    """Escalation ticket status"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class EscalationPriority(Enum):
    """Escalation priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class EscalationReason(Enum):
    """Reasons for escalation"""
    USER_REQUEST = "user_request"
    EMERGENCY = "emergency"
    COMPLAINT = "complaint"
    COMPLEX_QUERY = "complex_query"
    REPEATED_FAILURE = "repeated_failure"
    SENSITIVE_TOPIC = "sensitive_topic"
    LEGAL_MATTER = "legal_matter"
    VIP_USER = "vip_user"


@dataclass
class EscalationRequest:
    """Escalation request data"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    user_identifier: str = ""
    channel: str = "web"
    reason: EscalationReason = EscalationReason.USER_REQUEST
    priority: EscalationPriority = EscalationPriority.MEDIUM
    description: str = ""
    conversation_summary: str = ""
    status: EscalationStatus = EscalationStatus.OPEN
    assigned_to: Optional[str] = None
    company_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolution_notes: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "user_identifier": self.user_identifier,
            "channel": self.channel,
            "reason": self.reason.value,
            "priority": self.priority.value,
            "description": self.description,
            "conversation_summary": self.conversation_summary,
            "status": self.status.value,
            "assigned_to": self.assigned_to,
            "company_id": self.company_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "resolution_notes": self.resolution_notes
        }


# =====================================================================
# ESCALATION TRIGGERS
# =====================================================================
ESCALATION_TRIGGERS = {
    "keywords": [
        "speak to human", "talk to person", "real person", "agent",
        "complaint", "complain", "frustrated", "angry", "upset",
        "manager", "supervisor", "not working", "useless", "terrible",
        "sue", "lawyer", "legal", "court", "refund"
    ],
    "patterns": [
        r"(speak|talk).*(human|person|agent|someone)",
        r"(file|make|lodge).*complaint",
        r"(frustrated|angry|upset|disappointed)",
        r"not.*(helpful|working|satisfied|happy)",
        r"(lawyer|legal|court|sue)"
    ],
    "emergency_keywords": [
        "emergency", "urgent", "help", "arrested", "detained",
        "hospital", "accident", "death", "stranded", "crisis"
    ]
}


class EscalationService:
    """
    Manages escalation of conversations to human agents.
    """
    
    def __init__(self):
        self.triggers = ESCALATION_TRIGGERS
        self.escalation_count = 0
        self.resolved_count = 0
    
    def should_escalate(self, text: str, context: Dict = None) -> tuple[bool, EscalationReason, EscalationPriority]:
        """
        Check if message should trigger escalation.
        
        Returns: (should_escalate, reason, priority)
        """
        text_lower = text.lower()
        
        # Check emergency keywords (highest priority)
        for keyword in self.triggers["emergency_keywords"]:
            if keyword in text_lower:
                return True, EscalationReason.EMERGENCY, EscalationPriority.URGENT
        
        # Check complaint keywords
        complaint_keywords = ["complaint", "complain", "sue", "lawyer", "legal", "refund"]
        for keyword in complaint_keywords:
            if keyword in text_lower:
                return True, EscalationReason.COMPLAINT, EscalationPriority.HIGH
        
        # Check user request keywords
        for keyword in self.triggers["keywords"]:
            if keyword in text_lower:
                return True, EscalationReason.USER_REQUEST, EscalationPriority.MEDIUM
        
        # Check patterns
        import re
        for pattern in self.triggers["patterns"]:
            if re.search(pattern, text_lower):
                return True, EscalationReason.USER_REQUEST, EscalationPriority.MEDIUM
        
        # Check context for repeated failures
        if context:
            failure_count = context.get("consecutive_failures", 0)
            if failure_count >= 3:
                return True, EscalationReason.REPEATED_FAILURE, EscalationPriority.MEDIUM
        
        return False, None, None
    
    async def create_escalation(
        self,
        session_id: str,
        user_identifier: str,
        channel: str,
        reason: EscalationReason,
        priority: EscalationPriority,
        description: str,
        company_id: Optional[str] = None,
        conversation_history: List[Dict] = None
    ) -> EscalationRequest:
        """Create a new escalation ticket.

        ``company_id`` should always be supplied by the caller — the chat
        session it was raised from has a tenant. It's optional only to
        avoid breaking legacy callers during the rollout; once everything
        is migrated this becomes required."""
        db = await get_database()

        # Generate conversation summary
        summary = self._generate_summary(conversation_history or [])

        escalation = EscalationRequest(
            session_id=session_id,
            user_identifier=user_identifier,
            channel=channel,
            reason=reason,
            priority=priority,
            description=description,
            conversation_summary=summary,
            company_id=company_id
        )

        # Store in database
        await db.escalations.insert_one(escalation.to_dict())

        self.escalation_count += 1

        logger.info(
            f"[ESCALATION] Created ticket {escalation.id[:8]} | "
            f"Reason: {reason.value} | Priority: {priority.value} | "
            f"Channel: {channel} | Tenant: {company_id}"
        )

        # Send notification
        await self._send_notification(escalation)

        return escalation
    
    def _generate_summary(self, conversation_history: List[Dict]) -> str:
        """Generate summary from conversation history"""
        if not conversation_history:
            return "No conversation history available."
        
        # Get last 5 messages
        recent = conversation_history[-5:]
        
        summary_parts = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]  # Truncate long messages
            summary_parts.append(f"[{role}]: {content}")
        
        return "\n".join(summary_parts)
    
    async def _send_notification(self, escalation: EscalationRequest):
        """Send notification to admin about new escalation"""
        try:
            # Log notification (in production, send email/webhook)
            logger.info(
                f"[ESCALATION NOTIFICATION] "
                f"New {escalation.priority.value} priority escalation: {escalation.id}"
            )
            
            # TODO: Send email notification
            # TODO: Send webhook to admin dashboard
            # TODO: Send SMS for urgent escalations
            
        except Exception as e:
            logger.error(f"Failed to send escalation notification: {e}")
    
    async def get_escalation(self, escalation_id: str, company_id: Optional[str] = None) -> Optional[Dict]:
        """Get escalation by ID. If ``company_id`` is given, scope the
        lookup to that tenant — a None scope means cross-tenant (super-admin)."""
        db = await get_database()
        query: Dict[str, Any] = {"id": escalation_id}
        if company_id is not None:
            query["company_id"] = company_id
        return await db.escalations.find_one(query, {"_id": 0})

    async def update_escalation(
        self,
        escalation_id: str,
        status: EscalationStatus = None,
        assigned_to: str = None,
        resolution_notes: str = None,
        company_id: Optional[str] = None,
    ) -> bool:
        """Update escalation status. ``company_id`` scopes the update so a
        local admin can't modify another tenant's ticket by ID guess."""
        db = await get_database()

        update_data = {
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        if status:
            update_data["status"] = status.value
            if status == EscalationStatus.RESOLVED:
                update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
                self.resolved_count += 1

        if assigned_to:
            update_data["assigned_to"] = assigned_to

        if resolution_notes:
            update_data["resolution_notes"] = resolution_notes

        query: Dict[str, Any] = {"id": escalation_id}
        if company_id is not None:
            query["company_id"] = company_id
        result = await db.escalations.update_one(query, {"$set": update_data})

        return result.modified_count > 0

    async def get_open_escalations(self, limit: int = 50, company_id: Optional[str] = None) -> List[Dict]:
        """Get all open escalations. ``company_id=None`` returns across
        all tenants (super-admin view)."""
        db = await get_database()

        query: Dict[str, Any] = {"status": {"$in": ["open", "in_progress"]}}
        if company_id is not None:
            query["company_id"] = company_id

        escalations = await db.escalations.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)

        return escalations

    async def get_escalations_by_status(
        self,
        status: EscalationStatus,
        limit: int = 50,
        company_id: Optional[str] = None,
    ) -> List[Dict]:
        """Get escalations by status. ``company_id=None`` returns across
        all tenants (super-admin view)."""
        db = await get_database()

        query: Dict[str, Any] = {"status": status.value}
        if company_id is not None:
            query["company_id"] = company_id

        escalations = await db.escalations.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)

        return escalations

    async def get_escalation_stats(self, company_id: Optional[str] = None) -> Dict:
        """Get escalation statistics, optionally tenant-scoped."""
        db = await get_database()

        base_match: Dict[str, Any] = {}
        if company_id is not None:
            base_match["company_id"] = company_id

        status_pipeline = []
        if base_match:
            status_pipeline.append({"$match": dict(base_match)})
        status_pipeline.append({"$group": {"_id": "$status", "count": {"$sum": 1}}})

        status_counts = await db.escalations.aggregate(status_pipeline).to_list(10)

        status_map = {s["_id"]: s["count"] for s in status_counts}

        # Priority breakdown — same tenant scope, restricted to open/in_progress
        priority_match: Dict[str, Any] = {"status": {"$in": ["open", "in_progress"]}}
        if company_id is not None:
            priority_match["company_id"] = company_id
        priority_pipeline = [
            {"$match": priority_match},
            {"$group": {
                "_id": "$priority",
                "count": {"$sum": 1}
            }}
        ]

        priority_counts = await db.escalations.aggregate(priority_pipeline).to_list(10)
        priority_map = {p["_id"]: p["count"] for p in priority_counts}
        
        return {
            "total": sum(status_map.values()),
            "by_status": {
                "open": status_map.get("open", 0),
                "in_progress": status_map.get("in_progress", 0),
                "resolved": status_map.get("resolved", 0),
                "closed": status_map.get("closed", 0)
            },
            "by_priority": {
                "urgent": priority_map.get("urgent", 0),
                "high": priority_map.get("high", 0),
                "medium": priority_map.get("medium", 0),
                "low": priority_map.get("low", 0)
            },
            "session_stats": {
                "escalation_count": self.escalation_count,
                "resolved_count": self.resolved_count
            }
        }
    
    def get_escalation_response(self, priority: EscalationPriority) -> str:
        """Get appropriate response for escalation"""
        if priority == EscalationPriority.URGENT:
            return """🚨 **Emergency Escalation Created**

Your request has been marked as **URGENT** and sent to our emergency response team.

**Immediate Actions:**
📞 **Emergency Helpline:** (+27) 11 581 9800 (24/7)

A consular officer will contact you as soon as possible.

If this is a life-threatening emergency, please also contact local emergency services (10111)."""

        elif priority == EscalationPriority.HIGH:
            return """⚠️ **High Priority Escalation Created**

Your concern has been flagged as **high priority** and assigned to a senior officer.

**Expected Response:** Within 4 business hours

**In the meantime:**
📞 Phone: +27 11 783 0202
📧 Email: cons.joburg@mea.gov.in

Reference ID has been generated for tracking."""

        else:
            return """✅ **Escalation Request Received**

Your request to speak with a human agent has been recorded.

**Expected Response:** Within 1 business day

**Contact Options:**
📞 Phone: +27 11 783 0202
📧 Email: cons.joburg@mea.gov.in

**Office Hours:**
Mon-Fri: 9:00 AM - 5:30 PM

Thank you for your patience."""


# Global escalation service instance
escalation_service = EscalationService()
