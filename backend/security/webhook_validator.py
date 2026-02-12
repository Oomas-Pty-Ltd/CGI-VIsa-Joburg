"""
====================================================================
SEVA SETU BOT - WEBHOOK SECURITY VALIDATOR
====================================================================
Validates incoming webhooks from Twilio and Facebook to prevent
spoofing attacks. Enforces signature verification for all webhooks.
====================================================================
"""

import os
import hmac
import hashlib
import logging
from typing import Optional, Dict
from fastapi import Request, HTTPException, status
from functools import wraps

logger = logging.getLogger(__name__)

# =====================================================================
# TWILIO SIGNATURE VALIDATOR
# =====================================================================
class TwilioSignatureValidator:
    """
    Validates Twilio webhook signatures to prevent spoofing.
    Uses X-Twilio-Signature header for validation.
    """
    
    def __init__(self):
        self.auth_token = os.environ.get('TWILIO_AUTH_TOKEN', '')
        self.enabled = bool(self.auth_token)
        
    def validate_signature(self, url: str, params: Dict, signature: str) -> bool:
        """
        Validate Twilio request signature.
        
        Args:
            url: Full webhook URL
            params: Request form parameters (sorted)
            signature: X-Twilio-Signature header value
            
        Returns:
            bool: True if signature is valid
        """
        if not self.enabled:
            logger.warning("Twilio auth token not configured - skipping validation")
            return True
            
        if not signature:
            logger.warning("Missing Twilio signature header")
            return False
        
        try:
            # Build the string to sign
            # Twilio signs: URL + sorted params (key + value concatenated)
            s = url
            if params:
                for key in sorted(params.keys()):
                    s += key + str(params[key])
            
            # Create HMAC-SHA1 signature
            computed_sig = hmac.new(
                self.auth_token.encode('utf-8'),
                s.encode('utf-8'),
                hashlib.sha1
            ).digest()
            
            import base64
            computed_sig_b64 = base64.b64encode(computed_sig).decode('utf-8')
            
            # Constant-time comparison to prevent timing attacks
            is_valid = hmac.compare_digest(computed_sig_b64, signature)
            
            if not is_valid:
                logger.warning(f"Twilio signature mismatch for URL: {url}")
                
            return is_valid
            
        except Exception as e:
            logger.error(f"Twilio signature validation error: {e}")
            return False
    
    async def validate_request(self, request: Request) -> bool:
        """
        Validate a FastAPI request from Twilio.
        """
        signature = request.headers.get('X-Twilio-Signature', '')
        
        # Get full URL
        url = str(request.url)
        
        # Get form params
        form_data = await request.form()
        params = {key: form_data[key] for key in form_data}
        
        return self.validate_signature(url, params, signature)


# =====================================================================
# FACEBOOK SIGNATURE VALIDATOR
# =====================================================================
class FacebookSignatureValidator:
    """
    Validates Facebook webhook signatures using X-Hub-Signature-256.
    Prevents unauthorized webhook calls.
    """
    
    def __init__(self):
        self.app_secret = os.environ.get('FB_APP_SECRET', '')
        self.enabled = bool(self.app_secret)
        
    def validate_signature(self, payload: bytes, signature: str) -> bool:
        """
        Validate Facebook webhook signature.
        
        Args:
            payload: Raw request body bytes
            signature: X-Hub-Signature-256 header value
            
        Returns:
            bool: True if signature is valid
        """
        if not self.enabled:
            logger.warning("Facebook app secret not configured - skipping validation")
            return True
            
        if not signature:
            logger.warning("Missing Facebook signature header")
            return False
        
        try:
            # Facebook sends signature as: sha256=<hash>
            if not signature.startswith('sha256='):
                logger.warning("Invalid Facebook signature format")
                return False
                
            expected_sig = signature[7:]  # Remove 'sha256=' prefix
            
            # Compute HMAC-SHA256
            computed_sig = hmac.new(
                self.app_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            # Constant-time comparison
            is_valid = hmac.compare_digest(computed_sig, expected_sig)
            
            if not is_valid:
                logger.warning("Facebook signature mismatch")
                
            return is_valid
            
        except Exception as e:
            logger.error(f"Facebook signature validation error: {e}")
            return False
    
    async def validate_request(self, request: Request) -> bool:
        """
        Validate a FastAPI request from Facebook.
        """
        signature = request.headers.get('X-Hub-Signature-256', '')
        
        # Get raw body
        body = await request.body()
        
        return self.validate_signature(body, signature)


# =====================================================================
# GLOBAL VALIDATORS
# =====================================================================
twilio_validator = TwilioSignatureValidator()
facebook_validator = FacebookSignatureValidator()


# =====================================================================
# MIDDLEWARE / DEPENDENCY HELPERS
# =====================================================================
async def verify_twilio_webhook(request: Request):
    """
    FastAPI dependency to verify Twilio webhook signature.
    Use: @router.post("/webhook", dependencies=[Depends(verify_twilio_webhook)])
    """
    # Skip validation in development/testing mode
    if os.environ.get('WEBHOOK_VALIDATION_DISABLED', '').lower() == 'true':
        logger.debug("Webhook validation disabled for testing")
        return True
        
    if not await twilio_validator.validate_request(request):
        logger.warning(f"Rejected invalid Twilio webhook from {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature"
        )
    return True


async def verify_facebook_webhook(request: Request):
    """
    FastAPI dependency to verify Facebook webhook signature.
    Use: @router.post("/webhook", dependencies=[Depends(verify_facebook_webhook)])
    """
    # Skip validation in development/testing mode
    if os.environ.get('WEBHOOK_VALIDATION_DISABLED', '').lower() == 'true':
        logger.debug("Webhook validation disabled for testing")
        return True
        
    if not await facebook_validator.validate_request(request):
        logger.warning(f"Rejected invalid Facebook webhook from {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature"
        )
    return True


# =====================================================================
# SECURITY LOGGING
# =====================================================================
def log_webhook_attempt(channel: str, source_ip: str, success: bool, details: str = ""):
    """Log webhook validation attempts for security audit"""
    status_str = "ACCEPTED" if success else "REJECTED"
    logger.info(f"[WEBHOOK_SECURITY] {channel} | {status_str} | IP: {source_ip} | {details}")
