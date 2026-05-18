"""
====================================================================
SEVA SETU BOT - GUARDRAIL SERVICE
====================================================================
Validates input and output for PII protection, legal compliance,
and content safety. Ensures no sensitive data leaks through logs.
====================================================================
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# =====================================================================
# PII PATTERNS - Enhanced detection
# =====================================================================
PII_PATTERNS = {
    # South African ID Number (13 digits: YYMMDD SSSS C A Z)
    'SA_ID': (
        r'\b([0-9]{2})(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])([0-9]{4})([0-9])([0-9])([0-9])\b',
        '[SA_ID_REDACTED]'
    ),
    
    # Indian Aadhaar Number (12 digits with optional spaces)
    'AADHAAR': (
        r'\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b',
        '[AADHAAR_REDACTED]'
    ),
    
    # Indian PAN Number (ABCDE1234F format)
    'PAN': (
        r'\b[A-Z]{3}[ABCFGHLJPT][A-Z][0-9]{4}[A-Z]\b',
        '[PAN_REDACTED]'
    ),
    
    # Passport Number (alphanumeric, 6-9 chars)
    'PASSPORT': (
        r'\b[A-Z][0-9]{7}\b|\b[A-Z]{2}[0-9]{7}\b',
        '[PASSPORT_REDACTED]'
    ),
    
    # Phone Numbers (international format)
    'PHONE': (
        r'\+?[0-9]{1,4}[-.\s]?\(?[0-9]{1,4}\)?[-.\s]?[0-9]{1,4}[-.\s]?[0-9]{1,9}',
        '[PHONE_REDACTED]'
    ),
    
    # Email Addresses
    'EMAIL': (
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        '[EMAIL_REDACTED]'
    ),
    
    # Credit Card Numbers (with optional spaces/dashes)
    'CREDIT_CARD': (
        r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b',
        '[CARD_REDACTED]'
    ),
    
    # Bank Account Numbers (8-18 digits)
    'BANK_ACCOUNT': (
        r'\b[0-9]{8,18}\b',
        '[ACCOUNT_REDACTED]'
    ),
    
    # Date of Birth patterns
    'DOB': (
        r'\b(0[1-9]|[12][0-9]|3[01])[-/](0[1-9]|1[0-2])[-/](19|20)[0-9]{2}\b',
        '[DOB_REDACTED]'
    ),
    
    # IP Addresses
    'IP_ADDRESS': (
        r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
        '[IP_REDACTED]'
    ),
}

# =====================================================================
# UNSAFE OUTPUT PATTERNS
# =====================================================================
# Phrases that should not appear in bot responses (legal risk)

UNSAFE_OUTPUT_PATTERNS = [
    # Guarantees and promises
    (r'\b(guarantee[ds]?|100%|definitely|certainly)\s+(approval|success|visa)', 'guarantee'),
    (r'\byou\s+will\s+(definitely|certainly|surely)\s+(get|receive|obtain)', 'promise'),
    (r'\bno\s+(chance|way)\s+(of\s+)?(rejection|denial|failure)', 'false_promise'),
    
    # Legal advice
    (r'\blegal\s+advice', 'legal_advice'),
    (r'\bas\s+your\s+lawyer', 'legal_advice'),
    (r'\blegally\s+binding', 'legal_advice'),
    
    # Medical advice
    (r'\bmedical\s+advice', 'medical_advice'),
    (r'\bdiagnos(is|e)', 'medical_advice'),
    (r'\bprescri(be|ption)', 'medical_advice'),
    
    # Financial guarantees
    (r'\binvestment\s+advice', 'financial_advice'),
    (r'\bguaranteed\s+returns?', 'financial_advice'),
    
    # Discriminatory content
    (r'\b(hate|discriminat)', 'discrimination'),
]

COMPILED_UNSAFE_PATTERNS = [
    (re.compile(pattern, re.IGNORECASE), category)
    for pattern, category in UNSAFE_OUTPUT_PATTERNS
]

# =====================================================================
# SAFE DISCLAIMERS
# =====================================================================
DISCLAIMERS = {
    'visa': "Note: Visa approval is at the sole discretion of the consular officer. This information is for guidance only.",
    'legal': "Note: This is general information, not legal advice. Please consult a qualified legal professional.",
    'medical': "Note: For medical queries, please consult a healthcare professional.",
    'financial': "Note: This is not financial advice. Please consult a qualified financial advisor.",
    'general': "Note: This information is for guidance purposes. Please verify with official sources."
}


@dataclass
class GuardrailResult:
    """Result of guardrail check"""
    is_safe: bool
    sanitized_text: str
    pii_detected: List[str]
    unsafe_patterns: List[str]
    added_disclaimers: List[str]


class GuardrailService:
    """
    Comprehensive guardrail service for input/output validation.
    """
    
    def __init__(self):
        self.pii_detection_count = 0
        self.unsafe_output_count = 0
        
    def mask_pii(self, text: str, log_detections: bool = True) -> Tuple[str, List[str]]:
        """
        Mask PII in text using regex patterns.
        
        Returns:
            Tuple of (masked_text, list_of_detected_pii_types)
        """
        if not text:
            return text, []
        
        masked = text
        detected = []
        
        for pii_type, (pattern, replacement) in PII_PATTERNS.items():
            regex = re.compile(pattern, re.IGNORECASE)
            matches = regex.findall(masked)
            
            if matches:
                detected.append(pii_type)
                masked = regex.sub(replacement, masked)
                
                if log_detections:
                    self.pii_detection_count += 1
                    logger.info(f"[GUARDRAIL] Masked {pii_type} PII ({len(matches)} instances)")
        
        return masked, detected
    
    def check_output_safety(self, text: str) -> Tuple[bool, List[str], str]:
        """
        Check bot output for unsafe patterns and add disclaimers.
        
        Returns:
            Tuple of (is_safe, detected_patterns, modified_text)
        """
        if not text:
            return True, [], text
        
        detected = []
        modified = text
        disclaimers_to_add = set()
        
        for pattern, category in COMPILED_UNSAFE_PATTERNS:
            if pattern.search(text):
                detected.append(category)
                self.unsafe_output_count += 1
                logger.warning(f"[GUARDRAIL] Unsafe output pattern detected: {category}")
                
                # Map category to disclaimer
                if category in ('guarantee', 'promise', 'false_promise'):
                    disclaimers_to_add.add('visa')
                elif category == 'legal_advice':
                    disclaimers_to_add.add('legal')
                elif category == 'medical_advice':
                    disclaimers_to_add.add('medical')
                elif category == 'financial_advice':
                    disclaimers_to_add.add('financial')
        
        # Add disclaimers if needed
        if disclaimers_to_add:
            disclaimer_text = "\n\n---\n" + "\n".join(
                DISCLAIMERS[d] for d in disclaimers_to_add
            )
            modified = text + disclaimer_text
        
        is_safe = len(detected) == 0
        return is_safe, detected, modified
    
    def validate_input(self, text: str) -> GuardrailResult:
        """
        Validate and sanitize user input.
        """
        masked_text, pii_types = self.mask_pii(text)
        
        return GuardrailResult(
            is_safe=True,  # Input is sanitized, so it's safe to process
            sanitized_text=masked_text,
            pii_detected=pii_types,
            unsafe_patterns=[],
            added_disclaimers=[]
        )
    
    def validate_output(self, text: str) -> GuardrailResult:
        """
        Validate and sanitize bot output before sending to user.
        """
        # First mask any PII that might have leaked
        masked_text, pii_types = self.mask_pii(text)
        
        # Then check for unsafe patterns
        is_safe, unsafe_patterns, final_text = self.check_output_safety(masked_text)
        
        added_disclaimers = []
        if unsafe_patterns:
            if any(p in ('guarantee', 'promise', 'false_promise') for p in unsafe_patterns):
                added_disclaimers.append('visa')
            if 'legal_advice' in unsafe_patterns:
                added_disclaimers.append('legal')
            if 'medical_advice' in unsafe_patterns:
                added_disclaimers.append('medical')
            if 'financial_advice' in unsafe_patterns:
                added_disclaimers.append('financial')
        
        return GuardrailResult(
            is_safe=is_safe,
            sanitized_text=final_text,
            pii_detected=pii_types,
            unsafe_patterns=unsafe_patterns,
            added_disclaimers=added_disclaimers
        )
    
    def get_stats(self) -> Dict:
        """Get guardrail statistics"""
        return {
            "pii_detections": self.pii_detection_count,
            "unsafe_output_detections": self.unsafe_output_count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# =====================================================================
# LOG SANITIZATION
# =====================================================================
class SanitizedLogFormatter(logging.Formatter):
    """
    Custom log formatter that sanitizes PII from log messages.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guardrail = GuardrailService()
    
    # Loggers whose output is structured numeric metrics — skip PII redaction
    # so request durations/token counts are not mangled into [PHONE_REDACTED].
    _SKIP_REDACTION_PREFIXES = ("timing",)

    def format(self, record):
        # Skip redaction for structured-metric loggers
        if record.name and record.name.startswith(self._SKIP_REDACTION_PREFIXES):
            return super().format(record)

        # Sanitize the message
        if record.msg:
            sanitized_msg, _ = self.guardrail.mask_pii(str(record.msg), log_detections=False)
            record.msg = sanitized_msg

        # Sanitize args if present
        if record.args:
            sanitized_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    sanitized, _ = self.guardrail.mask_pii(arg, log_detections=False)
                    sanitized_args.append(sanitized)
                else:
                    sanitized_args.append(arg)
            record.args = tuple(sanitized_args)

        return super().format(record)


def setup_sanitized_logging():
    """
    Configure logging with PII sanitization.
    """
    formatter = SanitizedLogFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Update root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)


# =====================================================================
# UTILITY FUNCTIONS
# =====================================================================

# Global guardrail instance
guardrail_service = GuardrailService()


def mask_pii_enhanced(text: str) -> str:
    """
    Convenience function to mask PII in text.
    """
    masked, _ = guardrail_service.mask_pii(text)
    return masked


def sanitize_logs(text: str) -> str:
    """
    Sanitize text for safe logging.
    """
    masked, _ = guardrail_service.mask_pii(text, log_detections=False)
    return masked


def validate_and_sanitize_response(response: str) -> str:
    """
    Full validation and sanitization of bot response.
    """
    result = guardrail_service.validate_output(response)
    return result.sanitized_text
