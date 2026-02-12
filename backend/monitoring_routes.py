"""
====================================================================
MONITORING API ROUTES
====================================================================
Provides REST endpoints for health checks and status monitoring.
Includes security metrics and guardrail statistics.
====================================================================
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime, timezone
import time

from monitoring_service import monitoring_service, MONITORING_CONFIG
from security.guardrail import guardrail_service
from security.session_manager import session_manager
from security.rate_limiter import rate_limiter
from security.cost_monitor import cost_monitor

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Quick health check endpoint for load balancers and uptime monitors.
    Returns 200 if healthy, 503 if critical.
    """
    start_time = time.time()
    metrics = await monitoring_service.run_health_check()
    response_time = time.time() - start_time
    
    # Record response time
    monitoring_service.record_response_time(response_time)
    
    result = {
        "status": metrics.status,
        "timestamp": metrics.timestamp,
        "response_time_ms": round(response_time * 1000, 2),
        "services": {
            "mongodb": metrics.mongodb_connected,
            "llm": metrics.llm_available
        }
    }
    
    if metrics.status == "critical":
        raise HTTPException(status_code=503, detail=result)
    
    return result


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """
    Detailed status dashboard endpoint.
    Returns comprehensive system status and metrics.
    """
    return monitoring_service.get_status_summary()


@router.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """
    Get detailed performance metrics for monitoring dashboards.
    """
    summary = monitoring_service.get_status_summary()
    
    # Calculate uptime in human readable format
    uptime_seconds = summary['uptime']['seconds']
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    
    return {
        "service_name": "Seva Setu Bot",
        "version": "1.0.0",
        "environment": "production",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        
        "uptime": {
            "formatted": f"{days}d {hours}h {minutes}m",
            "seconds": uptime_seconds,
            "percent": summary['uptime']['percent'],
            "target_percent": summary['uptime']['target'],
            "meeting_sla": summary['uptime']['percent'] >= summary['uptime']['target']
        },
        
        "health": {
            "overall_status": summary['status'],
            "total_checks": summary['health_checks_total'],
            "failed_checks": summary['failed_checks'],
            "success_rate": round((summary['health_checks_total'] - summary['failed_checks']) / max(summary['health_checks_total'], 1) * 100, 2)
        },
        
        "resources": {
            "cpu": {
                "current": summary['resources']['cpu_percent'],
                "threshold": MONITORING_CONFIG['cpu_threshold'],
                "status": "ok" if summary['resources']['cpu_percent'] < MONITORING_CONFIG['cpu_threshold'] else "warning"
            },
            "memory": {
                "current": summary['resources']['memory_percent'],
                "threshold": MONITORING_CONFIG['memory_threshold'],
                "status": "ok" if summary['resources']['memory_percent'] < MONITORING_CONFIG['memory_threshold'] else "warning"
            },
            "disk": {
                "current": summary['resources']['disk_percent'],
                "threshold": MONITORING_CONFIG['disk_threshold'],
                "status": "ok" if summary['resources']['disk_percent'] < MONITORING_CONFIG['disk_threshold'] else "warning"
            }
        },
        
        "dependencies": {
            "mongodb": {
                "status": "connected" if summary['services']['mongodb'] else "disconnected",
                "healthy": summary['services']['mongodb']
            },
            "llm_service": {
                "status": "available" if summary['services']['llm'] else "unavailable",
                "healthy": summary['services']['llm']
            }
        },
        
        "performance": {
            "avg_response_time_seconds": summary['performance']['avg_response_time'],
            "response_time_threshold": MONITORING_CONFIG['response_time_threshold'],
            "active_sessions_24h": summary['performance']['active_sessions_24h']
        },
        
        "alerts": {
            "thresholds": {
                "cpu_percent": MONITORING_CONFIG['cpu_threshold'],
                "memory_percent": MONITORING_CONFIG['memory_threshold'],
                "disk_percent": MONITORING_CONFIG['disk_threshold'],
                "response_time_seconds": MONITORING_CONFIG['response_time_threshold']
            },
            "cooldown_seconds": MONITORING_CONFIG['alert_cooldown_seconds']
        }
    }


@router.get("/history")
async def get_metrics_history(limit: int = 60) -> Dict[str, Any]:
    """
    Get historical metrics for charting.
    Default returns last 60 data points (1 hour at 1-minute intervals).
    """
    history = list(monitoring_service.metrics_history)[-limit:]
    
    return {
        "count": len(history),
        "interval_seconds": MONITORING_CONFIG['health_check_interval'],
        "data_points": [
            {
                "timestamp": m.timestamp,
                "status": m.status,
                "cpu": m.cpu_percent,
                "memory": m.memory_percent,
                "disk": m.disk_percent,
                "response_time": m.response_time_avg,
                "sessions": m.active_sessions
            }
            for m in history
        ]
    }


@router.post("/test-alert")
async def test_alert() -> Dict[str, str]:
    """
    Send a test alert to verify alert configuration.
    """
    test_alert = {
        "type": "TEST_ALERT",
        "severity": "info",
        "message": "This is a test alert from Seva Setu Bot monitoring system."
    }
    
    await monitoring_service.send_alert(test_alert)
    
    return {
        "status": "sent",
        "message": "Test alert has been dispatched. Check your configured alert channels."
    }


@router.get("/security")
async def get_security_metrics() -> Dict[str, Any]:
    """
    Get security metrics including guardrail statistics.
    """
    guardrail_stats = guardrail_service.get_stats()
    rate_limit_stats = rate_limiter.get_stats()
    cost_stats = cost_monitor.get_daily_stats()
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "guardrails": {
            "pii_detections": guardrail_stats['pii_detections'],
            "unsafe_output_detections": guardrail_stats['unsafe_output_detections'],
            "status": "active"
        },
        "session_security": {
            "ttl_hours": session_manager.ttl_hours,
            "max_sessions_per_user": session_manager.max_sessions,
            "channel_isolation": True
        },
        "webhook_security": {
            "twilio_validation": "enabled",
            "facebook_validation": "enabled"
        },
        "input_sanitization": {
            "prompt_injection_protection": True,
            "pii_masking": True
        },
        "output_validation": {
            "unsafe_content_filtering": True,
            "auto_disclaimers": True
        },
        "rate_limiting": rate_limit_stats,
        "cost_monitoring": cost_stats
    }


@router.get("/rate-limits")
async def get_rate_limit_stats() -> Dict[str, Any]:
    """
    Get detailed rate limiting statistics.
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stats": rate_limiter.get_stats()
    }


@router.get("/costs")
async def get_cost_stats() -> Dict[str, Any]:
    """
    Get AI cost monitoring statistics.
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "daily_stats": cost_monitor.get_daily_stats(),
        "config": {
            "daily_budget": cost_monitor.config['daily_budget'],
            "monthly_budget": cost_monitor.config['monthly_budget'],
            "session_limit": cost_monitor.config['per_session_limit'],
            "model": cost_monitor.config['default_model'],
            "provider": cost_monitor.config['provider']
        }
    }


@router.get("/costs/session/{session_id}")
async def get_session_cost_stats(session_id: str) -> Dict[str, Any]:
    """
    Get cost statistics for a specific session.
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_stats": cost_monitor.get_session_stats(session_id)
    }
