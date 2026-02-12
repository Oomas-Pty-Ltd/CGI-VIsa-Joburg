"""
====================================================================
SEVA SETU BOT - COST MONITOR
====================================================================
Tracks AI token usage and costs to prevent budget overruns:
- Per-session token tracking
- Daily/monthly cost aggregation
- Budget alerts
- Cost dashboard data
====================================================================
"""

import os
import logging
from typing import Dict, Optional, List
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
from database import get_database

logger = logging.getLogger(__name__)

# =====================================================================
# CONFIGURATION
# =====================================================================
COST_CONFIG = {
    # Token pricing (per 1000 tokens) - GPT-5.2 pricing
    "input_cost_per_1k": float(os.environ.get('LLM_INPUT_COST_PER_1K', '0.01')),
    "output_cost_per_1k": float(os.environ.get('LLM_OUTPUT_COST_PER_1K', '0.03')),
    
    # Budget limits (in USD)
    "daily_budget": float(os.environ.get('DAILY_TOKEN_BUDGET', '50.0')),
    "monthly_budget": float(os.environ.get('MONTHLY_TOKEN_BUDGET', '1000.0')),
    "per_session_limit": float(os.environ.get('SESSION_TOKEN_BUDGET', '1.0')),
    
    # Alert thresholds (percentage of budget)
    "alert_threshold_warning": 0.70,  # 70%
    "alert_threshold_critical": 0.90,  # 90%
    
    # Model info
    "default_model": "gpt-5.2",
    "provider": "openai"
}


@dataclass
class TokenUsage:
    """Represents token usage for a single request"""
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "gpt-5.2"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
    
    @property
    def cost(self) -> float:
        """Calculate cost in USD"""
        input_cost = (self.input_tokens / 1000) * COST_CONFIG['input_cost_per_1k']
        output_cost = (self.output_tokens / 1000) * COST_CONFIG['output_cost_per_1k']
        return round(input_cost + output_cost, 6)


class CostMonitor:
    """
    Monitors AI token usage and costs across sessions.
    Provides budget tracking and alerting.
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or COST_CONFIG
        
        # In-memory tracking for current day
        self.today_usage: Dict[str, List[TokenUsage]] = defaultdict(list)  # session_id -> usages
        self.today_total_cost: float = 0.0
        self.today_total_tokens: int = 0
        self.current_date: str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        # Alert state
        self.warning_sent: bool = False
        self.critical_sent: bool = False
        
        # Stats
        self.total_requests: int = 0
        self.budget_exceeded_count: int = 0
    
    def _reset_if_new_day(self):
        """Reset daily counters if it's a new day"""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if today != self.current_date:
            logger.info(f"New day detected, resetting daily counters. Previous: {self.today_total_cost:.4f} USD")
            self.today_usage.clear()
            self.today_total_cost = 0.0
            self.today_total_tokens = 0
            self.current_date = today
            self.warning_sent = False
            self.critical_sent = False
    
    def record_usage(
        self,
        session_id: str,
        input_tokens: int,
        output_tokens: int,
        model: str = None,
        user_id: Optional[str] = None,
        channel: Optional[str] = None
    ) -> Dict:
        """
        Record token usage for a request.
        Returns usage info and any budget warnings.
        """
        self._reset_if_new_day()
        self.total_requests += 1
        
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model or self.config['default_model']
        )
        
        # Track by session
        self.today_usage[session_id].append(usage)
        self.today_total_cost += usage.cost
        self.today_total_tokens += usage.total_tokens
        
        # Check budget status
        budget_status = self._check_budget_status(session_id)
        
        # Log usage
        logger.info(
            f"[COST] Session={session_id[:20]}... "
            f"Tokens={usage.total_tokens} (in:{input_tokens}, out:{output_tokens}) "
            f"Cost=${usage.cost:.4f} "
            f"DailyTotal=${self.today_total_cost:.2f}"
        )
        
        return {
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": usage.total_tokens,
                "cost_usd": usage.cost
            },
            "session_total": {
                "requests": len(self.today_usage[session_id]),
                "tokens": sum(u.total_tokens for u in self.today_usage[session_id]),
                "cost_usd": sum(u.cost for u in self.today_usage[session_id])
            },
            "daily_total": {
                "requests": self.total_requests,
                "tokens": self.today_total_tokens,
                "cost_usd": self.today_total_cost
            },
            "budget_status": budget_status
        }
    
    def _check_budget_status(self, session_id: str) -> Dict:
        """Check budget status and return warnings"""
        status = {
            "daily_budget_used_pct": round(self.today_total_cost / self.config['daily_budget'] * 100, 1),
            "session_budget_used_pct": 0,
            "warning": None,
            "can_proceed": True
        }
        
        # Check session budget
        session_cost = sum(u.cost for u in self.today_usage[session_id])
        status["session_budget_used_pct"] = round(session_cost / self.config['per_session_limit'] * 100, 1)
        
        # Check daily budget thresholds
        daily_pct = self.today_total_cost / self.config['daily_budget']
        
        if daily_pct >= 1.0:
            status["warning"] = "BUDGET_EXCEEDED"
            status["can_proceed"] = False
            self.budget_exceeded_count += 1
            logger.error(f"[COST] Daily budget exceeded! ${self.today_total_cost:.2f} / ${self.config['daily_budget']}")
            
        elif daily_pct >= self.config['alert_threshold_critical']:
            if not self.critical_sent:
                status["warning"] = "CRITICAL_BUDGET"
                self.critical_sent = True
                logger.warning(f"[COST] CRITICAL: Daily budget at {daily_pct*100:.1f}%")
                
        elif daily_pct >= self.config['alert_threshold_warning']:
            if not self.warning_sent:
                status["warning"] = "WARNING_BUDGET"
                self.warning_sent = True
                logger.warning(f"[COST] WARNING: Daily budget at {daily_pct*100:.1f}%")
        
        # Check session budget
        if session_cost >= self.config['per_session_limit']:
            status["warning"] = status["warning"] or "SESSION_LIMIT"
            logger.warning(f"[COST] Session {session_id[:20]} exceeded limit: ${session_cost:.4f}")
        
        return status
    
    def check_can_proceed(self, session_id: str) -> tuple[bool, str]:
        """
        Check if a new request can proceed based on budget.
        Returns (can_proceed, reason)
        """
        self._reset_if_new_day()
        
        # Check daily budget
        if self.today_total_cost >= self.config['daily_budget']:
            return False, "Daily AI budget has been reached. Please try again tomorrow."
        
        # Check session budget
        session_cost = sum(u.cost for u in self.today_usage.get(session_id, []))
        if session_cost >= self.config['per_session_limit']:
            return False, "Session token limit reached. Please start a new conversation."
        
        return True, "OK"
    
    def estimate_cost(self, input_text: str, expected_output_tokens: int = 500) -> Dict:
        """
        Estimate cost for a request before making it.
        Rough estimation: ~4 chars per token for English
        """
        estimated_input_tokens = len(input_text) // 4
        
        input_cost = (estimated_input_tokens / 1000) * self.config['input_cost_per_1k']
        output_cost = (expected_output_tokens / 1000) * self.config['output_cost_per_1k']
        
        return {
            "estimated_input_tokens": estimated_input_tokens,
            "estimated_output_tokens": expected_output_tokens,
            "estimated_cost_usd": round(input_cost + output_cost, 6),
            "daily_remaining_usd": round(self.config['daily_budget'] - self.today_total_cost, 2)
        }
    
    def get_daily_stats(self) -> Dict:
        """Get daily cost statistics"""
        self._reset_if_new_day()
        
        return {
            "date": self.current_date,
            "total_requests": sum(len(usages) for usages in self.today_usage.values()),
            "total_sessions": len(self.today_usage),
            "total_tokens": self.today_total_tokens,
            "total_cost_usd": round(self.today_total_cost, 4),
            "budget": {
                "daily_limit": self.config['daily_budget'],
                "remaining": round(self.config['daily_budget'] - self.today_total_cost, 2),
                "used_percentage": round(self.today_total_cost / self.config['daily_budget'] * 100, 1)
            },
            "alerts": {
                "warning_sent": self.warning_sent,
                "critical_sent": self.critical_sent,
                "budget_exceeded_count": self.budget_exceeded_count
            }
        }
    
    def get_session_stats(self, session_id: str) -> Dict:
        """Get stats for a specific session"""
        usages = self.today_usage.get(session_id, [])
        
        total_tokens = sum(u.total_tokens for u in usages)
        total_cost = sum(u.cost for u in usages)
        
        return {
            "session_id": session_id,
            "request_count": len(usages),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "limit": {
                "session_budget": self.config['per_session_limit'],
                "remaining": round(self.config['per_session_limit'] - total_cost, 4),
                "used_percentage": round(total_cost / self.config['per_session_limit'] * 100, 1) if self.config['per_session_limit'] > 0 else 0
            }
        }
    
    async def save_daily_summary_to_db(self):
        """Save daily summary to database for historical tracking"""
        try:
            db = await get_database()
            
            summary = {
                "date": self.current_date,
                "total_requests": sum(len(usages) for usages in self.today_usage.values()),
                "total_sessions": len(self.today_usage),
                "total_tokens": self.today_total_tokens,
                "total_cost_usd": round(self.today_total_cost, 4),
                "budget_exceeded": self.today_total_cost >= self.config['daily_budget'],
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.cost_summaries.update_one(
                {"date": self.current_date},
                {"$set": summary},
                upsert=True
            )
            
            logger.info(f"[COST] Daily summary saved: {summary}")
            
        except Exception as e:
            logger.error(f"[COST] Failed to save daily summary: {e}")


# Global cost monitor instance
cost_monitor = CostMonitor()


# =====================================================================
# UTILITY FUNCTIONS
# =====================================================================
def estimate_tokens(text: str) -> int:
    """Rough token estimation (~4 chars per token for English)"""
    return len(text) // 4


async def record_llm_usage(
    session_id: str,
    input_text: str,
    output_text: str,
    model: str = "gpt-5.2"
) -> Dict:
    """
    Convenience function to record LLM usage.
    Call this after every LLM request.
    """
    input_tokens = estimate_tokens(input_text)
    output_tokens = estimate_tokens(output_text)
    
    return cost_monitor.record_usage(
        session_id=session_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model
    )
