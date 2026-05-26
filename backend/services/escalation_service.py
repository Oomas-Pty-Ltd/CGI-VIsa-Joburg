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
# ESCALATION TRIGGERS — moved to tenant_bot_config.escalation_rules
# (resolved via services.bot_config.BotConfig.escalation()). Kept here as
# the fallback so callers that don't have a tenant id still work.
# =====================================================================
_DEFAULT_RULES = {
    "keywords": [
        "speak to human", "talk to person", "real person", "agent",
        "complaint", "complain", "frustrated", "angry", "upset",
        "manager", "supervisor", "not working", "useless", "terrible",
        "sue", "lawyer", "legal", "court", "refund",
    ],
    "patterns": [
        r"(speak|talk).*(human|person|agent|someone)",
        r"(file|make|lodge).*complaint",
        r"(frustrated|angry|upset|disappointed)",
        r"not.*(helpful|working|satisfied|happy)",
        r"(lawyer|legal|court|sue)",
    ],
    "complaint_keywords": ["complaint", "complain", "sue", "lawyer", "legal", "refund"],
    "emergency_keywords": [
        "emergency", "urgent", "help", "arrested", "detained",
        "hospital", "accident", "death", "stranded", "crisis",
    ],
    "consecutive_failure_threshold": 3,
}


class EscalationService:
    """
    Manages escalation of conversations to human agents.

    Trigger keyword / pattern lists are per-tenant via
    ``services.bot_config.BotConfig.escalation()``. Callers that pass a
    ``company_id`` to :py:meth:`should_escalate` get tenant-scoped rules;
    legacy callers fall back to the platform defaults defined above.
    """

    def __init__(self):
        self.escalation_count = 0
        self.resolved_count = 0

    async def _rules_for(self, company_id: Optional[str]) -> Dict:
        """Resolve tenant rules with the platform defaults underneath."""
        if not company_id:
            return _DEFAULT_RULES
        try:
            from services.bot_config import get_bot_config
            cfg = await get_bot_config(company_id)
            return cfg.escalation()
        except Exception as exc:
            logger.debug("[escalation_service._rules_for] %s: %s", company_id, exc)
            return _DEFAULT_RULES

    async def should_escalate(
        self,
        text: str,
        context: Dict = None,
        company_id: Optional[str] = None,
    ) -> tuple[bool, EscalationReason, EscalationPriority]:
        """Check if a message should trigger escalation.

        Returns: (should_escalate, reason, priority).

        Pass ``company_id`` so per-tenant keyword/pattern overrides apply.
        Without it, the platform defaults are used.
        """
        text_lower = text.lower()
        rules = await self._rules_for(company_id)

        # Emergency keywords — highest priority. Both the single list and
        # the per-language map are checked so a tenant can configure either.
        for keyword in rules.get("emergency_keywords", []):
            if keyword.lower() in text_lower:
                return True, EscalationReason.EMERGENCY, EscalationPriority.URGENT
        for _lang, kws in (rules.get("emergency_keywords_by_lang") or {}).items():
            for kw in (kws or []):
                if kw.lower() in text_lower:
                    return True, EscalationReason.EMERGENCY, EscalationPriority.URGENT

        for keyword in rules.get("complaint_keywords", []):
            if keyword.lower() in text_lower:
                return True, EscalationReason.COMPLAINT, EscalationPriority.HIGH

        for keyword in rules.get("keywords", []):
            if keyword.lower() in text_lower:
                return True, EscalationReason.USER_REQUEST, EscalationPriority.MEDIUM

        import re as _re
        for pattern in rules.get("patterns", []):
            try:
                if _re.search(pattern, text_lower):
                    return True, EscalationReason.USER_REQUEST, EscalationPriority.MEDIUM
            except _re.error:
                logger.warning("[escalation] invalid regex %r — skipped", pattern)

        if context:
            failure_count = context.get("consecutive_failures", 0)
            threshold = rules.get("consecutive_failure_threshold", 3)
            if failure_count >= threshold:
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
    
    async def get_escalation_response(
        self,
        priority: EscalationPriority,
        company_id: Optional[str] = None,
    ) -> str:
        """Resolve the response shown to the user when an escalation fires.

        Reads ``escalation_rules.priority_responses[priority]`` on the tenant
        config when ``company_id`` is supplied; falls back to platform
        defaults if the tenant left that priority blank.
        """
        platform_defaults = {
            EscalationPriority.URGENT: (
                "🚨 **Emergency Escalation Created**\n\n"
                "Your request has been marked as **URGENT** and sent to our emergency response team.\n\n"
                "A representative will contact you as soon as possible.\n\n"
                "If this is a life-threatening emergency, please contact your local emergency services immediately."
            ),
            EscalationPriority.HIGH: (
                "⚠️ **High Priority Escalation Created**\n\n"
                "Your concern has been flagged as **high priority** and assigned to a senior team member.\n\n"
                "**Expected Response:** Within 4 business hours\n\n"
                "Reference ID has been generated for tracking."
            ),
            EscalationPriority.MEDIUM: (
                "✅ **Escalation Request Received**\n\n"
                "Your request to speak with a human agent has been recorded.\n\n"
                "**Expected Response:** Within 1 business day\n\n"
                "Thank you for your patience."
            ),
            EscalationPriority.LOW: (
                "✅ **Escalation Request Received**\n\n"
                "Thank you — we'll get back to you when we can."
            ),
        }
        rules = await self._rules_for(company_id)
        responses = rules.get("priority_responses") or {}
        tenant_msg = (responses.get(priority.value) or "").strip()
        if tenant_msg:
            return tenant_msg
        return platform_defaults.get(priority, platform_defaults[EscalationPriority.MEDIUM])


# Global escalation service instance
escalation_service = EscalationService()
