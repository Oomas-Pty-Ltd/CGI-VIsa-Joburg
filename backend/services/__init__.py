"""
Services module for Seva Setu Bot
"""

from .intent_classifier import (
    IntentClassifier,
    intent_classifier,
    classify_intent,
    get_deterministic_response,
    IntentCategory,
    VisaType,
    IntentResult,
    STRUCTURED_RESPONSES
)

from .escalation_service import (
    EscalationService,
    escalation_service,
    EscalationRequest,
    EscalationStatus,
    EscalationPriority
)

from .knowledge_service import (
    KnowledgeService,
    knowledge_service,
    KnowledgeEntry,
    KnowledgeCategory
)

__all__ = [
    # Intent classifier
    'IntentClassifier',
    'intent_classifier',
    'classify_intent',
    'get_deterministic_response',
    'IntentCategory',
    'VisaType',
    'IntentResult',
    'STRUCTURED_RESPONSES',
    
    # Escalation
    'EscalationService',
    'escalation_service',
    'EscalationRequest',
    'EscalationStatus',
    'EscalationPriority',
    
    # Knowledge
    'KnowledgeService',
    'knowledge_service',
    'KnowledgeEntry',
    'KnowledgeCategory'
]
