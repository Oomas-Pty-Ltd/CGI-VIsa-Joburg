"""
Seva Setu Bot API Tests
Tests for: Health check, Chat API, Super Admin Auth, Session management
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthCheck:
    """API Health Check Tests"""
    
    def test_api_root_returns_status(self):
        """Test that API root returns running status"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "Seva Setu Bot" in data["message"]
        print(f"✅ API Health: {data}")


class TestConsularChatAPI:
    """Consular Chat Endpoint Tests"""
    
    def test_chat_endpoint_accepts_post(self):
        """Test chat endpoint accepts POST requests"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "Hello",
                "enable_voice": False
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "response" in data
        assert "step" in data
        print(f"✅ Chat response received, session: {data['session_id']}")
    
    def test_chat_returns_session_id(self):
        """Test that chat creates and returns session ID"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "I need passport help",
                "enable_voice": False
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] is not None
        assert len(data["session_id"]) > 0
        # Verify it's a valid UUID format
        uuid.UUID(data["session_id"])
        print(f"✅ Valid session ID: {data['session_id']}")
    
    def test_chat_response_contains_content(self):
        """Test that chat response has meaningful content"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "What documents do I need for visa?",
                "enable_voice": False
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["response"]) > 50  # Should have substantial response
        print(f"✅ Response length: {len(data['response'])} chars")
    
    def test_chat_step_is_valid(self):
        """Test that step field is one of valid values"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "Hello",
                "enable_voice": False
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        valid_steps = ["register", "upload", "verify", "sign"]
        assert data["step"] in valid_steps
        print(f"✅ Step: {data['step']}")
    
    def test_chat_with_language_parameter(self):
        """Test chat accepts language parameter"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "Hello",
                "enable_voice": False,
                "language": "hi"
            },
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        print(f"✅ Language parameter accepted")


class TestSuperAdminAuth:
    """Super Admin Authentication Tests"""
    
    def test_super_admin_login_success(self):
        """Test super admin login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/super-admin/login",
            json={
                "email": "superadmin@sarthak.ai",
                "password": "Admin@2025"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert len(data["token"]) > 0
        print(f"✅ Super Admin login successful, token received")
    
    def test_super_admin_login_invalid_password(self):
        """Test super admin login with wrong password"""
        response = requests.post(
            f"{BASE_URL}/api/auth/super-admin/login",
            json={
                "email": "superadmin@sarthak.ai",
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 401
        print(f"✅ Invalid password correctly rejected")
    
    def test_super_admin_login_invalid_email(self):
        """Test super admin login with wrong email"""
        response = requests.post(
            f"{BASE_URL}/api/auth/super-admin/login",
            json={
                "email": "wrong@email.com",
                "password": "Admin@2025"
            }
        )
        assert response.status_code == 401
        print(f"✅ Invalid email correctly rejected")


class TestSessionManagement:
    """Session Management Tests"""
    
    def test_get_session_not_found(self):
        """Test getting non-existent session returns 404"""
        fake_session_id = str(uuid.uuid4())
        response = requests.get(f"{BASE_URL}/api/consular/session/{fake_session_id}")
        assert response.status_code == 404
        print(f"✅ Non-existent session correctly returns 404")
    
    def test_create_and_retrieve_session(self):
        """Test creating session via chat and retrieving it"""
        # Create session via chat
        chat_response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "Test session creation",
                "enable_voice": False
            },
            timeout=60
        )
        assert chat_response.status_code == 200
        session_id = chat_response.json()["session_id"]
        
        # Retrieve session
        get_response = requests.get(f"{BASE_URL}/api/consular/session/{session_id}")
        assert get_response.status_code == 200
        session_data = get_response.json()
        assert session_data["id"] == session_id
        assert "messages" in session_data
        print(f"✅ Session created and retrieved: {session_id}")


class TestFormSubmission:
    """Form Submission Tests"""
    
    def test_form_submit_endpoint(self):
        """Test form submission endpoint"""
        # First create a session
        chat_response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "Start form",
                "enable_voice": False
            },
            timeout=60
        )
        session_id = chat_response.json()["session_id"]
        
        # Submit form
        form_response = requests.post(
            f"{BASE_URL}/api/consular/form-submit",
            json={
                "session_id": session_id,
                "form_data": {
                    "full_name": "Test User",
                    "email": "test@example.com",
                    "passport_number": "TEST123456"
                }
            }
        )
        assert form_response.status_code == 200
        data = form_response.json()
        assert data["success"] == True
        print(f"✅ Form submitted successfully")


class TestVoiceInput:
    """Voice Input Endpoint Tests"""
    
    def test_voice_input_endpoint_exists(self):
        """Test voice input endpoint is accessible"""
        # This endpoint requires file upload, so we just test it exists
        # by sending an empty request and checking it doesn't 404
        response = requests.post(
            f"{BASE_URL}/api/consular/voice-input",
            data={"session_id": "test"}
        )
        # Should return 422 (validation error) not 404
        assert response.status_code in [200, 422]
        print(f"✅ Voice input endpoint accessible")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
