"""
====================================================================
SEVA SETU BOT - NOTIFICATION SERVICE
====================================================================
Handles notifications for:
- Application status changes
- Document expiry alerts
- Escalation updates
- System alerts
====================================================================
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
import uuid

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    STATUS_CHANGE = "status_change"
    DOCUMENT_EXPIRY = "document_expiry"
    ESCALATION_UPDATE = "escalation_update"
    SYSTEM_ALERT = "system_alert"
    WELCOME = "welcome"
    REMINDER = "reminder"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    IN_APP = "in_app"
    PUSH = "push"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    READ = "read"


class NotificationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Notification(BaseModel):
    id: str
    user_id: str
    notification_type: NotificationType
    channel: NotificationChannel
    priority: NotificationPriority
    title: str
    message: str
    metadata: Optional[Dict[str, Any]] = None
    status: NotificationStatus = NotificationStatus.PENDING
    scheduled_at: Optional[str] = None
    sent_at: Optional[str] = None
    delivered_at: Optional[str] = None
    read_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: str
    updated_at: str


class NotificationService:
    def __init__(self):
        self.smtp_configured = bool(os.environ.get('SMTP_HOST'))
        self.twilio_configured = bool(os.environ.get('TWILIO_ACCOUNT_SID'))
        
        # Notification templates
        self.templates = {
            NotificationType.STATUS_CHANGE: {
                "title": "Application Status Update",
                "template": "Your {application_type} application status has changed from {old_status} to {new_status}. {additional_info}"
            },
            NotificationType.DOCUMENT_EXPIRY: {
                "title": "Document Expiry Alert",
                "template": "Your {document_type} is {expiry_status}. {action_required}"
            },
            NotificationType.ESCALATION_UPDATE: {
                "title": "Support Request Update",
                "template": "Your support request #{reference_id} has been updated. Status: {status}. {notes}"
            },
            NotificationType.SYSTEM_ALERT: {
                "title": "Important Notice",
                "template": "{message}"
            },
            NotificationType.WELCOME: {
                "title": "Welcome to Seva Setu",
                "template": "Namaste! Welcome to Seva Setu Bot. We're here to help with your consular needs."
            },
            NotificationType.REMINDER: {
                "title": "Reminder",
                "template": "{message}"
            }
        }
    
    def format_message(self, notification_type: NotificationType, data: Dict[str, Any]) -> tuple[str, str]:
        """Format notification message from template"""
        template = self.templates.get(notification_type, {})
        title = template.get("title", "Notification")
        message_template = template.get("template", "{message}")
        
        try:
            message = message_template.format(**data)
        except KeyError as e:
            logger.warning(f"[NOTIFICATION] Missing template variable: {e}")
            message = str(data.get('message', 'You have a new notification'))
        
        return title, message
    
    async def create_notification(
        self,
        db,
        user_id: str,
        notification_type: NotificationType,
        channel: NotificationChannel,
        data: Dict[str, Any],
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        scheduled_at: Optional[str] = None
    ) -> Notification:
        """Create a new notification"""
        
        title, message = self.format_message(notification_type, data)
        now = datetime.now(timezone.utc).isoformat()
        
        notification = Notification(
            id=str(uuid.uuid4()),
            user_id=user_id,
            notification_type=notification_type,
            channel=channel,
            priority=priority,
            title=title,
            message=message,
            metadata=data,
            scheduled_at=scheduled_at,
            created_at=now,
            updated_at=now
        )
        
        await db.notifications.insert_one(notification.model_dump())
        
        logger.info(f"[NOTIFICATION] Created {notification_type.value} notification {notification.id} for user {user_id}")
        
        # If not scheduled, send immediately
        if not scheduled_at:
            await self.send_notification(db, notification)
        
        return notification
    
    async def send_notification(self, db, notification: Notification) -> bool:
        """Send notification via specified channel"""
        
        try:
            if notification.channel == NotificationChannel.EMAIL:
                success = await self._send_email(notification)
            elif notification.channel == NotificationChannel.WHATSAPP:
                success = await self._send_whatsapp(notification)
            elif notification.channel == NotificationChannel.SMS:
                success = await self._send_sms(notification)
            elif notification.channel == NotificationChannel.IN_APP:
                success = await self._send_in_app(db, notification)
            else:
                success = False
                logger.warning(f"[NOTIFICATION] Unknown channel: {notification.channel}")
            
            # Update notification status
            new_status = NotificationStatus.SENT if success else NotificationStatus.FAILED
            await db.notifications.update_one(
                {"id": notification.id},
                {
                    "$set": {
                        "status": new_status.value,
                        "sent_at": datetime.now(timezone.utc).isoformat() if success else None,
                        "retry_count": notification.retry_count + (0 if success else 1),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            return success
            
        except Exception as e:
            logger.error(f"[NOTIFICATION] Send failed for {notification.id}: {str(e)}")
            await db.notifications.update_one(
                {"id": notification.id},
                {
                    "$set": {
                        "status": NotificationStatus.FAILED.value,
                        "retry_count": notification.retry_count + 1,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            return False
    
    async def _send_email(self, notification: Notification) -> bool:
        """Send email notification"""
        if not self.smtp_configured:
            logger.warning("[NOTIFICATION] SMTP not configured, email not sent")
            return False
        
        # TODO: Implement actual email sending with smtplib or SendGrid
        logger.info(f"[NOTIFICATION] Email would be sent: {notification.title}")
        return True
    
    async def _send_whatsapp(self, notification: Notification) -> bool:
        """Send WhatsApp notification"""
        if not self.twilio_configured:
            logger.warning("[NOTIFICATION] Twilio not configured, WhatsApp not sent")
            return False
        
        # TODO: Implement via Twilio
        logger.info(f"[NOTIFICATION] WhatsApp would be sent: {notification.title}")
        return True
    
    async def _send_sms(self, notification: Notification) -> bool:
        """Send SMS notification"""
        if not self.twilio_configured:
            logger.warning("[NOTIFICATION] Twilio not configured, SMS not sent")
            return False
        
        # TODO: Implement via Twilio
        logger.info(f"[NOTIFICATION] SMS would be sent: {notification.title}")
        return True
    
    async def _send_in_app(self, db, notification: Notification) -> bool:
        """Store in-app notification for retrieval"""
        # In-app notifications are already stored, just mark as sent
        return True
    
    async def notify_status_change(
        self,
        db,
        user_id: str,
        application_type: str,
        old_status: str,
        new_status: str,
        additional_info: str = "",
        channel: NotificationChannel = NotificationChannel.IN_APP
    ) -> Notification:
        """Convenience method for status change notifications"""
        return await self.create_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.STATUS_CHANGE,
            channel=channel,
            priority=NotificationPriority.HIGH,
            data={
                "application_type": application_type,
                "old_status": old_status,
                "new_status": new_status,
                "additional_info": additional_info
            }
        )
    
    async def notify_document_expiry(
        self,
        db,
        user_id: str,
        document_type: str,
        expiry_status: str,
        action_required: str = "",
        channel: NotificationChannel = NotificationChannel.IN_APP
    ) -> Notification:
        """Convenience method for document expiry notifications"""
        priority = NotificationPriority.URGENT if expiry_status == "expired" else NotificationPriority.HIGH
        
        return await self.create_notification(
            db=db,
            user_id=user_id,
            notification_type=NotificationType.DOCUMENT_EXPIRY,
            channel=channel,
            priority=priority,
            data={
                "document_type": document_type,
                "expiry_status": expiry_status,
                "action_required": action_required
            }
        )
    
    async def get_user_notifications(
        self,
        db,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get notifications for a user"""
        query = {"user_id": user_id}
        if unread_only:
            query["status"] = {"$ne": NotificationStatus.READ.value}
        
        cursor = db.notifications.find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def mark_as_read(self, db, notification_id: str, user_id: str) -> bool:
        """Mark notification as read"""
        result = await db.notifications.update_one(
            {"id": notification_id, "user_id": user_id},
            {
                "$set": {
                    "status": NotificationStatus.READ.value,
                    "read_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        return result.modified_count > 0
    
    async def process_pending_notifications(self, db) -> int:
        """Process and send pending scheduled notifications"""
        now = datetime.now(timezone.utc).isoformat()
        
        cursor = db.notifications.find({
            "status": NotificationStatus.PENDING.value,
            "$or": [
                {"scheduled_at": None},
                {"scheduled_at": {"$lte": now}}
            ],
            "retry_count": {"$lt": 3}  # Max 3 retries
        })
        
        sent_count = 0
        async for doc in cursor:
            notification = Notification(**doc)
            if await self.send_notification(db, notification):
                sent_count += 1
        
        if sent_count > 0:
            logger.info(f"[NOTIFICATION] Processed {sent_count} pending notifications")
        
        return sent_count


# Singleton instance
notification_service = NotificationService()
