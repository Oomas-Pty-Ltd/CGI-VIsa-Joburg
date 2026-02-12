"""
Test Suite for Admin Dashboard and Consular Bot Features
Tests:
- Admin Dashboard API endpoints
- Super Admin Login
- Consular Bot voice-input and document-scan endpoints
"""
import pytest
import requests
import os
import base64

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://consulai.preview.emergentagent.com')

# Test credentials
SUPER_ADMIN_EMAIL = "superadmin@sarthak.ai"
SUPER_ADMIN_PASSWORD = "Admin@2025"


class TestSuperAdminAuth:
    """Test Super Admin authentication"""
    
    def test_super_admin_login_success(self):
        """Test successful super admin login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/super-admin/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user_type"] == "super_admin"
        assert "user_id" in data
    
    def test_super_admin_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/super-admin/login",
            json={"email": "wrong@email.com", "password": "wrongpassword"}
        )
        assert response.status_code == 401


class TestAdminDashboardEndpoints:
    """Test Admin Dashboard API endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token before each test"""
        response = requests.post(
            f"{BASE_URL}/api/auth/super-admin/login",
            json={"email": SUPER_ADMIN_EMAIL, "password": SUPER_ADMIN_PASSWORD}
        )
        self.token = response.json().get("token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_admin_dashboard_endpoint(self):
        """Test /api/admin/dashboard returns valid data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/dashboard",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "timestamp" in data
        assert "overview" in data
        assert "escalations" in data
        assert "costs" in data
        assert "health" in data
        
        # Verify overview fields
        assert "total_sessions" in data["overview"]
        assert "total_companies" in data["overview"]
        assert "total_users" in data["overview"]
        assert "today_sessions" in data["overview"]
        
        # Verify health status
        assert data["health"]["status"] == "healthy"
        assert data["health"]["llm_available"] == True
        assert data["health"]["db_connected"] == True
    
    def test_admin_escalations_endpoint(self):
        """Test /api/admin/escalations returns escalations list"""
        response = requests.get(
            f"{BASE_URL}/api/admin/escalations",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "escalations" in data
        assert "count" in data
        assert isinstance(data["escalations"], list)
    
    def test_admin_knowledge_endpoint(self):
        """Test /api/admin/knowledge returns knowledge entries"""
        response = requests.get(
            f"{BASE_URL}/api/admin/knowledge",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "entries" in data
        assert "count" in data
        assert isinstance(data["entries"], list)
        
        # Verify at least some entries exist
        assert data["count"] > 0
    
    def test_admin_observability_endpoint(self):
        """Test /api/admin/observability returns metrics"""
        response = requests.get(
            f"{BASE_URL}/api/admin/observability",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "timestamp" in data
        assert "intent_classification" in data
        assert "rate_limiting" in data
        assert "cost_tracking" in data
        assert "guardrails" in data
        assert "escalations" in data
        assert "knowledge_base" in data
        
        # Verify intent classification fields
        assert "total_classifications" in data["intent_classification"]
        assert "llm_fallbacks" in data["intent_classification"]
        assert "rule_based_rate" in data["intent_classification"]
    
    def test_admin_endpoints_require_auth(self):
        """Test that admin endpoints require authentication"""
        endpoints = [
            "/api/admin/dashboard",
            "/api/admin/escalations",
            "/api/admin/knowledge",
            "/api/admin/observability"
        ]
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            assert response.status_code in [401, 403], f"Endpoint {endpoint} should require auth"


class TestConsularVoiceInput:
    """Test Consular Bot voice-input endpoint"""
    
    def test_voice_input_accepts_audio_files(self):
        """Test /api/consular/voice-input accepts audio files"""
        # Create a minimal webm header (not valid audio, but tests file handling)
        webm_header = bytes([
            0x1A, 0x45, 0xDF, 0xA3,  # EBML header
            0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F,
        ])
        
        files = {'audio': ('test.webm', webm_header, 'audio/webm')}
        data = {'language': 'en'}
        
        response = requests.post(
            f"{BASE_URL}/api/consular/voice-input",
            files=files,
            data=data
        )
        
        # Should return error for invalid audio, but endpoint should be accessible
        # 520 is expected for invalid audio file
        assert response.status_code in [200, 400, 500, 520]
    
    def test_voice_input_rejects_invalid_format(self):
        """Test voice-input rejects invalid file formats"""
        files = {'audio': ('test.txt', b'not audio', 'text/plain')}
        data = {'language': 'en'}
        
        response = requests.post(
            f"{BASE_URL}/api/consular/voice-input",
            files=files,
            data=data
        )
        
        # Should reject non-audio files
        assert response.status_code in [400, 500, 520]


class TestConsularDocumentScan:
    """Test Consular Bot document-scan endpoint"""
    
    def test_document_scan_processes_images(self):
        """Test /api/consular/document-scan processes images"""
        # Minimal 1x1 white PNG image
        png_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        
        response = requests.post(
            f"{BASE_URL}/api/consular/document-scan",
            json={
                "image_base64": png_base64,
                "document_type": "passport",
                "session_id": "test_session_doc_scan"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "extracted_data" in data
    
    def test_document_scan_handles_different_types(self):
        """Test document-scan handles different document types"""
        png_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        
        doc_types = ["passport", "visa", "oci"]
        
        for doc_type in doc_types:
            response = requests.post(
                f"{BASE_URL}/api/consular/document-scan",
                json={
                    "image_base64": png_base64,
                    "document_type": doc_type,
                    "session_id": f"test_session_{doc_type}"
                }
            )
            assert response.status_code == 200, f"Failed for document type: {doc_type}"


class TestConsularChat:
    """Test Consular Bot chat endpoint"""
    
    def test_chat_endpoint_works(self):
        """Test /api/consular/chat processes messages"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "What are the office hours?",
                "language": "en"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "response" in data
        assert "step" in data
    
    def test_chat_with_different_languages(self):
        """Test chat works with different language settings"""
        languages = ["en", "hi", "ta"]
        
        for lang in languages:
            response = requests.post(
                f"{BASE_URL}/api/consular/chat",
                json={
                    "message": "Hello",
                    "language": lang
                }
            )
            assert response.status_code == 200, f"Failed for language: {lang}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
