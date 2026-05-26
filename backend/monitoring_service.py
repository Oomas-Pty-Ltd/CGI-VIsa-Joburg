"""
====================================================================
SEVA SETU BOT - MONITORING & ALERTING SERVICE
====================================================================

This module provides:
- Health check endpoints
- System resource monitoring
- Alert notifications (Email/Webhook)
- Performance metrics tracking

Configuration is done via environment variables in .env file.
====================================================================
"""

import asyncio
import os
import psutil
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from collections import deque
import logging
import httpx

logger = logging.getLogger(__name__)

# =====================================================================
# CONFIGURATION - Update these in .env or directly here
# =====================================================================
MONITORING_CONFIG = {
    # Alert thresholds
    "cpu_threshold": 90,           # Alert when CPU > 90%
    "memory_threshold": 90,        # Alert when Memory > 90%
    "disk_threshold": 85,          # Alert when Disk > 85%
    "response_time_threshold": 30, # Alert when response > 30 seconds
    
    # Health check interval (seconds)
    "health_check_interval": 60,
    
    # Alert cooldown (don't spam - wait X seconds between same alerts)
    "alert_cooldown_seconds": 300,  # 5 minutes
    
    # Uptime target
    "uptime_target_percent": 98,
}


@dataclass
class AlertState:
    """Track alert state to prevent spam"""
    last_cpu_alert: float = 0
    last_memory_alert: float = 0
    last_disk_alert: float = 0
    last_downtime_alert: float = 0
    last_response_time_alert: float = 0


@dataclass  
class HealthMetrics:
    """Store health check metrics"""
    timestamp: str
    status: str  # healthy, degraded, critical
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    mongodb_connected: bool
    llm_available: bool
    response_time_avg: float
    active_sessions: int
    uptime_seconds: float
    errors: list = field(default_factory=list)


class MonitoringService:
    """Main monitoring service class"""
    
    def __init__(self):
        self.start_time = datetime.now(timezone.utc)
        self.alert_state = AlertState()
        self.metrics_history: deque = deque(maxlen=1440)  # Store 24 hours of minute-by-minute data
        self.response_times: deque = deque(maxlen=100)    # Last 100 response times
        self.health_check_count = 0
        self.failed_checks = 0
        
        # Load email config from environment
        self.smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', 587))
        self.smtp_user = os.environ.get('SMTP_USER', '')
        self.smtp_password = os.environ.get('SMTP_PASSWORD', '')
        self.alert_emails = os.environ.get('ALERT_EMAILS', '').split(',')
        self.webhook_url = os.environ.get('ALERT_WEBHOOK_URL', '')
        
    def get_system_metrics(self) -> Dict[str, float]:
        """Get current system resource usage.

        Disk path is resolved from ``MONITORING_DISK_PATH`` (defaults to the
        process CWD's filesystem root). Previously hardcoded to ``/app``
        which 500'd on any non-container host.
        """
        disk_path = os.environ.get("MONITORING_DISK_PATH") or os.path.abspath(os.sep)
        try:
            disk_percent = psutil.disk_usage(disk_path).percent
        except FileNotFoundError:
            # Fallback: filesystem root always exists.
            disk_percent = psutil.disk_usage(os.path.abspath(os.sep)).percent
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": disk_percent,
            "memory_used_gb": psutil.virtual_memory().used / (1024**3),
            "memory_total_gb": psutil.virtual_memory().total / (1024**3),
        }
    
    async def check_mongodb_connection(self) -> bool:
        """Check if MongoDB is accessible"""
        try:
            from database import get_database
            db = await get_database()
            await db.command('ping')
            return True
        except Exception as e:
            logger.error(f"MongoDB health check failed: {e}")
            return False
    
    async def check_llm_availability(self) -> bool:
        """Check if LLM service is available (lightweight check)"""
        try:
            api_key = os.environ.get('EMERGENT_LLM_KEY', '')
            return bool(api_key and len(api_key) > 10)
        except Exception:
            return False
    
    async def get_active_sessions_count(self) -> int:
        """Get count of active chat sessions (last 24 hours)"""
        try:
            from database import get_database
            from datetime import timedelta
            db = await get_database()
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            count = await db.chat_sessions.count_documents({
                "created_at": {"$gte": cutoff}
            })
            return count
        except Exception:
            return -1
    
    def record_response_time(self, response_time: float):
        """Record a response time for averaging"""
        self.response_times.append(response_time)
    
    def get_avg_response_time(self) -> float:
        """Get average response time from recent requests"""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
    
    def get_uptime_seconds(self) -> float:
        """Get service uptime in seconds"""
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()
    
    def get_uptime_percent(self) -> float:
        """Calculate uptime percentage"""
        if self.health_check_count == 0:
            return 100.0
        successful = self.health_check_count - self.failed_checks
        return (successful / self.health_check_count) * 100
    
    async def run_health_check(self) -> HealthMetrics:
        """Run a comprehensive health check"""
        self.health_check_count += 1
        errors = []
        
        # Get system metrics
        sys_metrics = self.get_system_metrics()
        
        # Check MongoDB
        mongodb_ok = await self.check_mongodb_connection()
        if not mongodb_ok:
            errors.append("MongoDB connection failed")
        
        # Check LLM
        llm_ok = await self.check_llm_availability()
        if not llm_ok:
            errors.append("LLM service unavailable")
        
        # Get session count
        active_sessions = await self.get_active_sessions_count()
        
        # Determine overall status
        if errors or sys_metrics['cpu_percent'] > 95 or sys_metrics['memory_percent'] > 95:
            status = "critical"
            self.failed_checks += 1
        elif sys_metrics['cpu_percent'] > 80 or sys_metrics['memory_percent'] > 80:
            status = "degraded"
        else:
            status = "healthy"
        
        metrics = HealthMetrics(
            timestamp=datetime.now(timezone.utc).isoformat(),
            status=status,
            cpu_percent=sys_metrics['cpu_percent'],
            memory_percent=sys_metrics['memory_percent'],
            disk_percent=sys_metrics['disk_percent'],
            mongodb_connected=mongodb_ok,
            llm_available=llm_ok,
            response_time_avg=self.get_avg_response_time(),
            active_sessions=active_sessions,
            uptime_seconds=self.get_uptime_seconds(),
            errors=errors
        )
        
        # Store in history
        self.metrics_history.append(metrics)
        
        # Check if alerts needed
        await self.check_and_send_alerts(metrics, sys_metrics)
        
        return metrics
    
    async def check_and_send_alerts(self, metrics: HealthMetrics, sys_metrics: Dict):
        """Check thresholds and send alerts if needed"""
        current_time = datetime.now(timezone.utc).timestamp()
        cooldown = MONITORING_CONFIG['alert_cooldown_seconds']
        alerts_to_send = []
        
        # CPU Alert
        if sys_metrics['cpu_percent'] >= MONITORING_CONFIG['cpu_threshold']:
            if current_time - self.alert_state.last_cpu_alert > cooldown:
                alerts_to_send.append({
                    "type": "CPU_HIGH",
                    "severity": "warning" if sys_metrics['cpu_percent'] < 95 else "critical",
                    "message": f"CPU usage at {sys_metrics['cpu_percent']:.1f}% (threshold: {MONITORING_CONFIG['cpu_threshold']}%)"
                })
                self.alert_state.last_cpu_alert = current_time
        
        # Memory Alert
        if sys_metrics['memory_percent'] >= MONITORING_CONFIG['memory_threshold']:
            if current_time - self.alert_state.last_memory_alert > cooldown:
                alerts_to_send.append({
                    "type": "MEMORY_HIGH",
                    "severity": "warning" if sys_metrics['memory_percent'] < 95 else "critical",
                    "message": f"Memory usage at {sys_metrics['memory_percent']:.1f}% ({sys_metrics['memory_used_gb']:.1f}GB / {sys_metrics['memory_total_gb']:.1f}GB)"
                })
                self.alert_state.last_memory_alert = current_time
        
        # Disk Alert
        if sys_metrics['disk_percent'] >= MONITORING_CONFIG['disk_threshold']:
            if current_time - self.alert_state.last_disk_alert > cooldown:
                alerts_to_send.append({
                    "type": "DISK_HIGH",
                    "severity": "warning",
                    "message": f"Disk usage at {sys_metrics['disk_percent']:.1f}% (threshold: {MONITORING_CONFIG['disk_threshold']}%)"
                })
                self.alert_state.last_disk_alert = current_time
        
        # Service Down Alert
        if metrics.status == "critical":
            if current_time - self.alert_state.last_downtime_alert > cooldown:
                alerts_to_send.append({
                    "type": "SERVICE_CRITICAL",
                    "severity": "critical",
                    "message": f"Service is in CRITICAL state. Errors: {', '.join(metrics.errors)}"
                })
                self.alert_state.last_downtime_alert = current_time
        
        # Response Time Alert
        if metrics.response_time_avg > MONITORING_CONFIG['response_time_threshold']:
            if current_time - self.alert_state.last_response_time_alert > cooldown:
                alerts_to_send.append({
                    "type": "SLOW_RESPONSE",
                    "severity": "warning",
                    "message": f"Average response time is {metrics.response_time_avg:.1f}s (threshold: {MONITORING_CONFIG['response_time_threshold']}s)"
                })
                self.alert_state.last_response_time_alert = current_time
        
        # Send all alerts
        for alert in alerts_to_send:
            await self.send_alert(alert)
    
    async def send_alert(self, alert: Dict):
        """Send alert via configured channels (email and/or webhook)"""
        logger.warning(f"ALERT: [{alert['severity'].upper()}] {alert['type']} - {alert['message']}")
        
        # Send email if configured
        if self.smtp_user and self.alert_emails and self.alert_emails[0]:
            await self.send_email_alert(alert)
        
        # Send webhook if configured
        if self.webhook_url:
            await self.send_webhook_alert(alert)
    
    async def send_email_alert(self, alert: Dict):
        """Send alert via email"""
        try:
            subject = f"[{alert['severity'].upper()}] {os.environ.get('PLATFORM_NAME', 'Bot')} Alert: {alert['type']}"
            
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: {'#dc2626' if alert['severity'] == 'critical' else '#f59e0b'};">
                    ⚠️ {os.environ.get('PLATFORM_NAME', 'Bot')} Alert
                </h2>
                <table style="border-collapse: collapse; width: 100%; max-width: 600px;">
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Alert Type:</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{alert['type']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Severity:</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd; color: {'#dc2626' if alert['severity'] == 'critical' else '#f59e0b'};">
                            {alert['severity'].upper()}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Message:</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{alert['message']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;"><strong>Time:</strong></td>
                        <td style="padding: 10px; border: 1px solid #ddd;">{datetime.now(timezone.utc).isoformat()}</td>
                    </tr>
                </table>
                <p style="color: #666; margin-top: 20px;">
                    This is an automated alert from {os.environ.get('PLATFORM_NAME', 'Bot')} Monitoring System.
                </p>
            </body>
            </html>
            """
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_user
            msg['To'] = ', '.join(self.alert_emails)
            msg.attach(MIMEText(body, 'html'))
            
            # Send in a thread to not block
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_email_sync, msg)
            
            logger.info(f"Alert email sent to {self.alert_emails}")
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
    
    def _send_email_sync(self, msg):
        """Synchronous email sending (run in executor)"""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
    
    async def send_webhook_alert(self, alert: Dict):
        """Send alert via webhook (Slack, Discord, Teams, etc.)"""
        try:
            payload = {
                "text": f"🚨 *{alert['severity'].upper()}* - {alert['type']}\n{alert['message']}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "service": os.environ.get('PLATFORM_NAME', 'Bot'),
                **alert
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(self.webhook_url, json=payload, timeout=10)
                if response.status_code == 200:
                    logger.info("Webhook alert sent successfully")
                else:
                    logger.error(f"Webhook alert failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get a summary of current status for dashboard"""
        uptime_percent = self.get_uptime_percent()
        uptime_status = "🟢" if uptime_percent >= 98 else "🟡" if uptime_percent >= 95 else "🔴"
        
        latest_metrics = self.metrics_history[-1] if self.metrics_history else None
        
        return {
            "service": os.environ.get('PLATFORM_NAME', 'Bot'),
            "status": latest_metrics.status if latest_metrics else "unknown",
            "status_emoji": "🟢" if latest_metrics and latest_metrics.status == "healthy" else "🟡" if latest_metrics and latest_metrics.status == "degraded" else "🔴",
            "uptime": {
                "percent": round(uptime_percent, 2),
                "target": MONITORING_CONFIG['uptime_target_percent'],
                "status": uptime_status,
                "seconds": self.get_uptime_seconds()
            },
            "resources": {
                "cpu_percent": latest_metrics.cpu_percent if latest_metrics else 0,
                "memory_percent": latest_metrics.memory_percent if latest_metrics else 0,
                "disk_percent": latest_metrics.disk_percent if latest_metrics else 0,
            },
            "services": {
                "mongodb": latest_metrics.mongodb_connected if latest_metrics else False,
                "llm": latest_metrics.llm_available if latest_metrics else False,
            },
            "performance": {
                "avg_response_time": round(self.get_avg_response_time(), 2),
                "active_sessions_24h": latest_metrics.active_sessions if latest_metrics else 0,
            },
            "thresholds": MONITORING_CONFIG,
            "last_check": latest_metrics.timestamp if latest_metrics else None,
            "health_checks_total": self.health_check_count,
            "failed_checks": self.failed_checks,
        }


# Global monitoring instance
monitoring_service = MonitoringService()


async def start_background_monitoring():
    """Start the background health check loop"""
    logger.info("Starting background monitoring service...")
    while True:
        try:
            await monitoring_service.run_health_check()
        except Exception as e:
            logger.error(f"Health check error: {e}")
        await asyncio.sleep(MONITORING_CONFIG['health_check_interval'])
