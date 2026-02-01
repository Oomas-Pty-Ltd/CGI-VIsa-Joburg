"""
Seva Setu Bot API Tests
Tests for consular services, authentication, and chat functionality
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://seva-bridge-1.preview.emergentagent.com').rstrip('/')

class TestHealthCheck:
    """Health check endpoint tests"""
    
    def test_api_health(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "Seva Setu Bot" in data["message"]


class TestSuperAdminAuth:
    """Super Admin authentication tests"""
    
    def test_super_admin_login_success(self):
        """Test super admin login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/super-admin/login",
            json={"email": "superadmin@sarthak.ai", "password": "Admin@2025"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user_type"] == "super_admin"
        assert "user_id" in data
        assert len(data["token"]) > 0
    
    def test_super_admin_login_invalid_credentials(self):
        """Test super admin login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/super-admin/login",
            json={"email": "wrong@example.com", "password": "wrongpass"}
        )
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data


class TestConsularChat:
    """Consular chat endpoint tests"""
    
    def test_chat_basic_message(self):
        """Test basic chat message"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={"message": "Hello", "enable_voice": False}
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "response" in data
        assert "step" in data
        assert len(data["response"]) > 0
    
    def test_chat_passport_query(self):
        """Test passport-related query"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={"message": "I need help with passport renewal", "enable_voice": False}
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        # Response should contain passport-related info
        assert len(data["response"]) > 50
    
    def test_chat_session_persistence(self):
        """Test chat session persistence"""
        # First message
        response1 = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={"message": "Hello", "enable_voice": False}
        )
        assert response1.status_code == 200
        session_id = response1.json()["session_id"]
        
        # Second message with same session
        response2 = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={"message": "Tell me about visa services", "session_id": session_id, "enable_voice": False}
        )
        assert response2.status_code == 200
        assert response2.json()["session_id"] == session_id
    
    def test_chat_hindi_language(self):
        """Test Hindi language support"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={"message": "नमस्ते, मुझे पासपोर्ट की जानकारी चाहिए", "enable_voice": False, "language": "hi"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert len(data["response"]) > 0


class TestConsularSession:
    """Consular session endpoint tests"""
    
    def test_get_session_not_found(self):
        """Test getting non-existent session"""
        fake_session_id = str(uuid.uuid4())
        response = requests.get(f"{BASE_URL}/api/consular/session/{fake_session_id}")
        assert response.status_code == 404
    
    def test_get_session_after_chat(self):
        """Test getting session after chat"""
        # Create session via chat
        chat_response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={"message": "Test message", "enable_voice": False}
        )
        assert chat_response.status_code == 200
        session_id = chat_response.json()["session_id"]
        
        # Get session
        session_response = requests.get(f"{BASE_URL}/api/consular/session/{session_id}")
        assert session_response.status_code == 200
        data = session_response.json()
        assert data["id"] == session_id
        assert "messages" in data


class TestFormSubmission:
    """Form submission endpoint tests"""
    
    def test_form_submit(self):
        """Test form submission"""
        # First create a session
        chat_response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={"message": "Start application", "enable_voice": False}
        )
        session_id = chat_response.json()["session_id"]
        
        # Submit form
        response = requests.post(
            f"{BASE_URL}/api/consular/form-submit",
            json={
                "session_id": session_id,
                "form_data": {
                    "name": "Test User",
                    "email": "test@example.com",
                    "service_type": "passport_renewal"
                }
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True


class TestUserAuth:
    """User authentication tests"""
    
    def test_user_register_and_login(self):
        """Test user registration and login flow"""
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "TestPass123!"
        
        # Register
        register_response = requests.post(
            f"{BASE_URL}/api/auth/user/register",
            json={"email": test_email, "password": test_password}
        )
        assert register_response.status_code == 200
        data = register_response.json()
        assert "token" in data
        assert data["user_type"] == "user"
        
        # Login with same credentials
        login_response = requests.post(
            f"{BASE_URL}/api/auth/user/login",
            json={"email": test_email, "password": test_password}
        )
        assert login_response.status_code == 200
        login_data = login_response.json()
        assert "token" in login_data
    
    def test_user_login_invalid(self):
        """Test user login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/user/login",
            json={"email": "nonexistent@example.com", "password": "wrongpass"}
        )
        assert response.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
