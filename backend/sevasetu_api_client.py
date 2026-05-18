"""
SEV-SETU API Helper - Integration module for Python backend
Handles delivery status callbacks without curl
"""
import requests
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

SEVASETU_API_URL = "https://sevasetu.seva.org.za/api/"
TIMEOUT = 10


class SevaSetuAPIClient:
    """Client for interacting with SEV-SETU API"""
    
    def __init__(self, base_url: str = SEVASETU_API_URL, timeout: int = TIMEOUT):
        self.base_url = base_url
        self.timeout = timeout
    
    def send_delivery_status(
        self,
        status: str,
        msg_ref: str,
        mobile: Optional[str] = None,
        d_time: Optional[str] = None,
        sms_msg_id: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send delivery status to SEV-SETU API
        
        Args:
            status: Delivery status (e.g., 'DELIVERED', 'FAILED', 'PENDING')
            msg_ref: Message reference ID
            mobile: Phone number that received/failed delivery
            d_time: Delivery timestamp (ISO format)
            sms_msg_id: SMS message ID
            notes: Optional notes about delivery
        
        Returns:
            Dictionary with response status and data
        """
        
        params = {
            "qStatus": status,
            "qMsgRef": msg_ref,
        }
        
        # Add optional parameters
        if mobile:
            params["qMobile"] = mobile
        if d_time:
            params["qDTime"] = d_time
        else:
            params["qDTime"] = datetime.utcnow().isoformat()
        if sms_msg_id:
            params["SMSMSGID"] = sms_msg_id
        if notes:
            params["NOTES"] = notes
        
        try:
            logger.info(f"Sending delivery status to SEV-SETU: {msg_ref}")
            
            response = requests.get(
                self.base_url,
                params=params,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            
            result = {
                "success": True,
                "status_code": response.status_code,
                "message": "Delivery status sent successfully",
                "response": response.json()
            }
            
            logger.info(f"SEV-SETU response: {result['response']}")
            return result
            
        except requests.exceptions.Timeout:
            error_msg = f"SEV-SETU API timeout after {self.timeout}s"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "msg_ref": msg_ref
            }
        except requests.exceptions.RequestException as e:
            error_msg = f"SEV-SETU API request failed: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "msg_ref": msg_ref
            }
    
    def check_api_health(self) -> bool:
        """Check if SEV-SETU API is reachable"""
        try:
            response = requests.get(self.base_url, timeout=5)
            return response.status_code == 200
        except:
            return False


def send_delivery_status_callback(
    status: str,
    msg_ref: str,
    mobile: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    """
    Convenience function to send delivery status
    
    Usage:
        send_delivery_status_callback(
            status="DELIVERED",
            msg_ref="MSG12345",
            mobile="27612345678",
            notes="Message delivered successfully"
        )
    """
    client = SevaSetuAPIClient()
    result = client.send_delivery_status(
        status=status,
        msg_ref=msg_ref,
        mobile=mobile,
        notes=notes
    )
    return result.get("success", False)


# Example usage in your routes
if __name__ == "__main__":
    import asyncio
    
    async def example():
        client = SevaSetuAPIClient()
        
        # Check API health
        if client.check_api_health():
            print("✓ SEV-SETU API is healthy")
        else:
            print("✗ SEV-SETU API is down")
            return
        
        # Send delivery status
        result = client.send_delivery_status(
            status="DELIVERED",
            msg_ref="MSG_TEST_001",
            mobile="27612345678",
            sms_msg_id="SMS_001",
            notes="Test delivery notification"
        )
        
        print(f"\nResult: {result}")
    
    asyncio.run(example())
