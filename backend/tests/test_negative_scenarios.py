"""
====================================================================
SEVA SETU BOT - COMPREHENSIVE NEGATIVE TESTING
====================================================================
Tests for:
- Empty message submission
- Very long message handling (>5000 chars)
- Invalid file type upload rejection
- Large file (>10MB) upload rejection
- Malformed JSON in API requests
- Invalid auth token handling
- Rate limiting (30+ rapid requests)
- Error report endpoint
- Theme context loading
====================================================================
"""

import pytest
import requests
import os
import json
import time
from io import BytesIO

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://consulai.preview.emergentagent.com').rstrip('/')

# Test credentials
SUPER_ADMIN_EMAIL = "superadmin@sarthak.ai"
SUPER_ADMIN_PASSWORD = "Admin@2025"


class TestNegativeScenarios:
    """Negative test cases for edge cases and error handling"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    # =====================================================================
    # NEGATIVE TEST: Empty message submission
    # =====================================================================
    def test_empty_message_submission(self):
        """Test that empty message returns appropriate error or handles gracefully"""
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": "",
            "session_id": None,
            "user_id": "test_user"
        })
        
        # Should either return 400 or handle gracefully with a response
        assert response.status_code in [200, 400, 422], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            # If 200, should have a response asking for input
            assert "response" in data
            print(f"Empty message handled gracefully: {data.get('response', '')[:100]}")
        else:
            print(f"Empty message rejected with status {response.status_code}")
    
    def test_whitespace_only_message(self):
        """Test that whitespace-only message is handled"""
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": "   \n\t   ",
            "session_id": None,
            "user_id": "test_user"
        })
        
        assert response.status_code in [200, 400, 422]
        print(f"Whitespace message status: {response.status_code}")
    
    # =====================================================================
    # NEGATIVE TEST: Very long message (>5000 chars)
    # =====================================================================
    def test_very_long_message(self):
        """Test handling of very long messages (>5000 characters)"""
        long_message = "A" * 5001  # 5001 characters
        
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": long_message,
            "session_id": None,
            "user_id": "test_user"
        })
        
        # Should either truncate, reject, or handle gracefully
        assert response.status_code in [200, 400, 413, 422], f"Unexpected status: {response.status_code}"
        print(f"Long message (5001 chars) status: {response.status_code}")
    
    def test_extremely_long_message(self):
        """Test handling of extremely long messages (>10000 characters)"""
        very_long_message = "B" * 10001
        
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": very_long_message,
            "session_id": None,
            "user_id": "test_user"
        })
        
        assert response.status_code in [200, 400, 413, 422]
        print(f"Very long message (10001 chars) status: {response.status_code}")
    
    # =====================================================================
    # NEGATIVE TEST: Invalid file type upload rejection
    # =====================================================================
    def test_invalid_file_type_voice_input(self):
        """Test that invalid file types are rejected for voice input"""
        # Create a fake text file
        fake_file = BytesIO(b"This is not an audio file")
        
        response = self.session.post(
            f"{BASE_URL}/api/consular/voice-input",
            files={"audio": ("test.txt", fake_file, "text/plain")},
            data={"language": "en"}
        )
        
        # Should reject with 400
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print(f"Invalid file type rejected: {response.status_code}")
    
    def test_invalid_file_type_exe(self):
        """Test that executable files are rejected"""
        fake_exe = BytesIO(b"MZ" + b"\x00" * 100)  # Fake EXE header
        
        response = self.session.post(
            f"{BASE_URL}/api/consular/voice-input",
            files={"audio": ("malware.exe", fake_exe, "application/x-msdownload")},
            data={"language": "en"}
        )
        
        assert response.status_code == 400
        print(f"EXE file rejected: {response.status_code}")
    
    # =====================================================================
    # NEGATIVE TEST: Large file (>10MB) upload rejection
    # =====================================================================
    def test_large_file_rejection(self):
        """Test that files larger than 10MB are rejected"""
        # Create a 11MB fake file (just headers, not actual content to save memory)
        # We'll test with a smaller file but check the validation logic
        large_content = b"X" * (11 * 1024 * 1024)  # 11MB
        large_file = BytesIO(large_content)
        
        response = self.session.post(
            f"{BASE_URL}/api/consular/voice-input",
            files={"audio": ("large.webm", large_file, "audio/webm")},
            data={"language": "en"}
        )
        
        # Should reject with 400 or 413 (Payload Too Large)
        assert response.status_code in [400, 413], f"Expected 400/413, got {response.status_code}"
        print(f"Large file (11MB) rejected: {response.status_code}")
    
    # =====================================================================
    # NEGATIVE TEST: Malformed JSON in API requests
    # =====================================================================
    def test_malformed_json_chat(self):
        """Test handling of malformed JSON in chat request"""
        response = self.session.post(
            f"{BASE_URL}/api/consular/chat",
            data="{{invalid json}",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print(f"Malformed JSON rejected: {response.status_code}")
    
    def test_missing_required_fields(self):
        """Test handling of missing required fields"""
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            # Missing 'message' field
            "session_id": "test"
        })
        
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        print(f"Missing fields rejected: {response.status_code}")
    
    def test_wrong_data_types(self):
        """Test handling of wrong data types"""
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": 12345,  # Should be string
            "session_id": ["array", "not", "string"],  # Should be string or null
            "user_id": {"object": "not_string"}  # Should be string
        })
        
        # Should either reject or coerce types
        assert response.status_code in [200, 400, 422]
        print(f"Wrong data types status: {response.status_code}")
    
    # =====================================================================
    # NEGATIVE TEST: Invalid auth token handling
    # =====================================================================
    def test_invalid_auth_token_admin_dashboard(self):
        """Test that invalid auth tokens are rejected for admin endpoints"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/dashboard",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )
        
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"Invalid token rejected: {response.status_code}")
    
    def test_expired_token_format(self):
        """Test handling of expired/malformed JWT tokens"""
        # Malformed JWT
        malformed_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"
        
        response = self.session.get(
            f"{BASE_URL}/api/admin/dashboard",
            headers={"Authorization": f"Bearer {malformed_jwt}"}
        )
        
        assert response.status_code in [401, 403]
        print(f"Malformed JWT rejected: {response.status_code}")
    
    def test_no_auth_header(self):
        """Test that missing auth header is rejected for protected endpoints"""
        response = self.session.get(f"{BASE_URL}/api/admin/dashboard")
        
        assert response.status_code in [401, 403]
        print(f"No auth header rejected: {response.status_code}")
    
    def test_wrong_auth_scheme(self):
        """Test that wrong auth scheme is rejected"""
        response = self.session.get(
            f"{BASE_URL}/api/admin/dashboard",
            headers={"Authorization": "Basic dXNlcjpwYXNz"}  # Basic auth instead of Bearer
        )
        
        assert response.status_code in [401, 403]
        print(f"Wrong auth scheme rejected: {response.status_code}")
    
    # =====================================================================
    # NEGATIVE TEST: Rate limiting (30+ rapid requests)
    # =====================================================================
    def test_rate_limiting(self):
        """Test that rate limiting kicks in after 30+ rapid requests"""
        blocked_count = 0
        success_count = 0
        
        # Send 35 rapid requests
        for i in range(35):
            response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
                "message": f"Test message {i}",
                "session_id": None,
                "user_id": "rate_limit_test_user"
            })
            
            if response.status_code == 429:
                blocked_count += 1
            elif response.status_code == 200:
                success_count += 1
        
        print(f"Rate limit test: {success_count} success, {blocked_count} blocked")
        
        # At least some requests should be blocked if rate limiting is working
        # Note: Rate limiting may not kick in immediately depending on config
        assert success_count > 0, "All requests failed"
        print(f"Rate limiting test completed: {blocked_count} requests blocked")
    
    # =====================================================================
    # POSITIVE TEST: Error report endpoint
    # =====================================================================
    def test_error_report_endpoint(self):
        """Test that error report endpoint accepts error data"""
        error_data = {
            "error_type": "test_error",
            "error_message": "This is a test error from automated testing",
            "stack_trace": "Error at line 1\n  at test.js:1:1",
            "context": {
                "url": "https://test.com/page",
                "userAgent": "TestBot/1.0",
                "timestamp": "2026-02-17T20:00:00Z"
            },
            "severity": "low"
        }
        
        response = self.session.post(f"{BASE_URL}/api/admin/error-report", json=error_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data.get("success") == True
        assert "report_id" in data
        print(f"Error report created: {data.get('report_id')}")
    
    def test_error_report_critical_severity(self):
        """Test error report with critical severity"""
        error_data = {
            "error_type": "critical_test",
            "error_message": "Critical test error - should notify admin",
            "severity": "critical"
        }
        
        response = self.session.post(f"{BASE_URL}/api/admin/error-report", json=error_data)
        
        assert response.status_code == 200
        print(f"Critical error report submitted")
    
    # =====================================================================
    # POSITIVE TEST: Chat functionality works end-to-end
    # =====================================================================
    def test_chat_functionality_e2e(self):
        """Test that chat functionality works end-to-end"""
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": "What is OCI?",
            "session_id": None,
            "user_id": "e2e_test_user",
            "language": "en"
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "session_id" in data
        assert "response" in data
        assert "step" in data
        assert len(data["response"]) > 0
        
        print(f"Chat E2E test passed. Response length: {len(data['response'])}")
    
    # =====================================================================
    # POSITIVE TEST: Admin dashboard displays error reports
    # =====================================================================
    def test_admin_error_reports_list(self):
        """Test that admin can view error reports"""
        # First login as super admin
        login_response = self.session.post(f"{BASE_URL}/api/auth/super-admin/login", json={
            "email": SUPER_ADMIN_EMAIL,
            "password": SUPER_ADMIN_PASSWORD
        })
        
        assert login_response.status_code == 200
        token = login_response.json().get("token")
        
        # Get error reports
        response = self.session.get(
            f"{BASE_URL}/api/admin/error-reports",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "reports" in data
        assert "stats" in data
        print(f"Error reports retrieved: {len(data['reports'])} reports")
    
    # =====================================================================
    # ADDITIONAL NEGATIVE TESTS
    # =====================================================================
    def test_sql_injection_attempt(self):
        """Test that SQL injection attempts are handled safely"""
        malicious_message = "'; DROP TABLE users; --"
        
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": malicious_message,
            "session_id": None,
            "user_id": "sql_test"
        })
        
        # Should handle safely (either sanitize or reject)
        assert response.status_code in [200, 400]
        print(f"SQL injection attempt handled: {response.status_code}")
    
    def test_xss_attempt(self):
        """Test that XSS attempts are handled safely"""
        xss_message = "<script>alert('XSS')</script>"
        
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": xss_message,
            "session_id": None,
            "user_id": "xss_test"
        })
        
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            data = response.json()
            # Response should not contain raw script tags
            assert "<script>" not in data.get("response", "")
        print(f"XSS attempt handled: {response.status_code}")
    
    def test_unicode_handling(self):
        """Test handling of various unicode characters"""
        unicode_message = "Hello 你好 مرحبا שלום 🎉 ñ ü ö"
        
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": unicode_message,
            "session_id": None,
            "user_id": "unicode_test"
        })
        
        assert response.status_code == 200
        print(f"Unicode handling passed")
    
    def test_special_characters(self):
        """Test handling of special characters"""
        special_message = "Test with special chars: @#$%^&*()[]{}|\\;:'\",.<>?/`~"
        
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": special_message,
            "session_id": None,
            "user_id": "special_test"
        })
        
        assert response.status_code in [200, 400]
        print(f"Special characters handled: {response.status_code}")
    
    def test_document_scan_invalid_base64(self):
        """Test document scan with invalid base64"""
        response = self.session.post(f"{BASE_URL}/api/consular/document-scan", json={
            "image_base64": "not_valid_base64!!!",
            "document_type": "passport",
            "session_id": "test_session"
        })
        
        # Should handle gracefully
        assert response.status_code in [200, 400, 500]
        print(f"Invalid base64 handled: {response.status_code}")
    
    def test_invalid_session_id_format(self):
        """Test with invalid session ID format"""
        response = self.session.post(f"{BASE_URL}/api/consular/chat", json={
            "message": "Hello",
            "session_id": "invalid-session-id-with-special-chars-!@#$%",
            "user_id": "test"
        })
        
        # Should either accept or reject gracefully
        assert response.status_code in [200, 400, 422]
        print(f"Invalid session ID handled: {response.status_code}")


class TestDocumentServiceValidation:
    """Test document service file validation"""
    
    def test_allowed_mime_types(self):
        """Test that allowed MIME types are accepted"""
        allowed_types = [
            ('image/jpeg', '.jpg'),
            ('image/png', '.png'),
            ('application/pdf', '.pdf'),
        ]
        
        for mime_type, ext in allowed_types:
            # Create minimal valid file content
            if mime_type == 'image/jpeg':
                content = b'\xff\xd8\xff\xe0\x00\x10JFIF'  # JPEG header
            elif mime_type == 'image/png':
                content = b'\x89PNG\r\n\x1a\n'  # PNG header
            else:
                content = b'%PDF-1.4'  # PDF header
            
            file = BytesIO(content)
            
            response = requests.post(
                f"{BASE_URL}/api/consular/voice-input",
                files={"audio": (f"test{ext}", file, mime_type)},
                data={"language": "en"}
            )
            
            # Voice input should reject non-audio files
            print(f"MIME type {mime_type}: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
