"""
====================================================================
SEVA SETU BOT - FEEDBACK SERVICE
====================================================================
Stores user feedback with session context in MongoDB.
====================================================================
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
import uuid

logger = logging.getLogger(__name__)


class FeedbackType(str, Enum):
    RATING = "rating"
    COMMENT = "comment"
    ISSUE_REPORT = "issue_report"
    SUGGESTION = "suggestion"
    SATISFACTION = "satisfaction"


class FeedbackSentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class Feedback(BaseModel):
    id: str
    session_id: str
    user_id: Optional[str] = None
    channel: str  # web, whatsapp, facebook, widget
    feedback_type: FeedbackType
    rating: Optional[int] = None  # 1-5 scale
    comment: Optional[str] = None
    sentiment: Optional[FeedbackSentiment] = None
    conversation_topic: Optional[str] = None  # What the conversation was about
    bot_response_quality: Optional[int] = None  # 1-5 scale
    resolved_query: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: str


class FeedbackService:
    def __init__(self):
        self.min_rating = 1
        self.max_rating = 5
    
    def _analyze_sentiment(self, text: str) -> FeedbackSentiment:
        """Simple sentiment analysis based on keywords"""
        if not text:
            return FeedbackSentiment.NEUTRAL
        
        text_lower = text.lower()
        
        positive_words = ['great', 'excellent', 'amazing', 'helpful', 'thank', 'good', 
                         'fantastic', 'awesome', 'love', 'perfect', 'wonderful', 'best']
        negative_words = ['bad', 'terrible', 'awful', 'poor', 'useless', 'waste', 
                         'horrible', 'disappointing', 'frustrated', 'angry', 'worst', 'hate']
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            return FeedbackSentiment.POSITIVE
        elif negative_count > positive_count:
            return FeedbackSentiment.NEGATIVE
        else:
            return FeedbackSentiment.NEUTRAL
    
    async def submit_feedback(
        self,
        db,
        session_id: str,
        feedback_type: FeedbackType,
        channel: str = "web",
        user_id: Optional[str] = None,
        rating: Optional[int] = None,
        comment: Optional[str] = None,
        conversation_topic: Optional[str] = None,
        bot_response_quality: Optional[int] = None,
        resolved_query: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Feedback:
        """Submit user feedback"""
        
        # Validate rating
        if rating is not None:
            rating = max(self.min_rating, min(self.max_rating, rating))
        
        if bot_response_quality is not None:
            bot_response_quality = max(self.min_rating, min(self.max_rating, bot_response_quality))
        
        # Analyze sentiment from comment
        sentiment = self._analyze_sentiment(comment) if comment else None
        
        # If no sentiment from comment, derive from rating
        if sentiment is None and rating is not None:
            if rating >= 4:
                sentiment = FeedbackSentiment.POSITIVE
            elif rating <= 2:
                sentiment = FeedbackSentiment.NEGATIVE
            else:
                sentiment = FeedbackSentiment.NEUTRAL
        
        feedback = Feedback(
            id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            feedback_type=feedback_type,
            rating=rating,
            comment=comment,
            sentiment=sentiment,
            conversation_topic=conversation_topic,
            bot_response_quality=bot_response_quality,
            resolved_query=resolved_query,
            metadata=metadata,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        await db.feedback.insert_one(feedback.model_dump())
        
        logger.info(f"[FEEDBACK] Submitted {feedback_type.value} from session {session_id}, rating={rating}, sentiment={sentiment}")
        
        return feedback
    
    async def get_session_feedback(self, db, session_id: str) -> List[Dict[str, Any]]:
        """Get all feedback for a session"""
        cursor = db.feedback.find(
            {"session_id": session_id},
            {"_id": 0}
        ).sort("created_at", -1)
        
        return await cursor.to_list(length=100)
    
    async def get_user_feedback(self, db, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all feedback from a user"""
        cursor = db.feedback.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def get_feedback_stats(self, db, days: int = 30) -> Dict[str, Any]:
        """Get feedback statistics"""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        pipeline = [
            {"$match": {"created_at": {"$gte": cutoff}}},
            {"$group": {
                "_id": None,
                "total_feedback": {"$sum": 1},
                "avg_rating": {"$avg": "$rating"},
                "avg_bot_quality": {"$avg": "$bot_response_quality"},
                "resolved_count": {"$sum": {"$cond": ["$resolved_query", 1, 0]}},
                "positive_count": {"$sum": {"$cond": [{"$eq": ["$sentiment", "positive"]}, 1, 0]}},
                "negative_count": {"$sum": {"$cond": [{"$eq": ["$sentiment", "negative"]}, 1, 0]}},
                "neutral_count": {"$sum": {"$cond": [{"$eq": ["$sentiment", "neutral"]}, 1, 0]}}
            }}
        ]
        
        result = await db.feedback.aggregate(pipeline).to_list(length=1)
        
        if not result:
            return {
                "total_feedback": 0,
                "avg_rating": 0,
                "avg_bot_quality": 0,
                "resolution_rate": 0,
                "sentiment_breakdown": {"positive": 0, "negative": 0, "neutral": 0}
            }
        
        stats = result[0]
        total = stats.get('total_feedback', 0)
        resolved = stats.get('resolved_count', 0)
        
        return {
            "total_feedback": total,
            "avg_rating": round(stats.get('avg_rating', 0) or 0, 2),
            "avg_bot_quality": round(stats.get('avg_bot_quality', 0) or 0, 2),
            "resolution_rate": round((resolved / total * 100) if total > 0 else 0, 1),
            "sentiment_breakdown": {
                "positive": stats.get('positive_count', 0),
                "negative": stats.get('negative_count', 0),
                "neutral": stats.get('neutral_count', 0)
            }
        }
    
    async def get_channel_stats(self, db, days: int = 30) -> Dict[str, Any]:
        """Get feedback breakdown by channel"""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        pipeline = [
            {"$match": {"created_at": {"$gte": cutoff}}},
            {"$group": {
                "_id": "$channel",
                "count": {"$sum": 1},
                "avg_rating": {"$avg": "$rating"}
            }}
        ]
        
        result = await db.feedback.aggregate(pipeline).to_list(length=10)
        
        return {item['_id']: {
            "count": item['count'],
            "avg_rating": round(item.get('avg_rating', 0) or 0, 2)
        } for item in result if item['_id']}


# Singleton instance
feedback_service = FeedbackService()
