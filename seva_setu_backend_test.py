#!/usr/bin/env python3
"""
Comprehensive Backend API Testing for Seva Setu Bot
Consulate General of India Johannesburg - Multi-language Bot Testing
"""

import requests
import sys
import json
import base64
from datetime import datetime
from typing import Dict, Any, Optional

class SevaSetuBotTester:
    def __init__(self, base_url="https://secure-consul.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.super_admin_token = None
        self.local_admin_token = None
        self.session_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def log_result(self, test_name: str, success: bool, details: str = ""):
        """Log test results"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {test_name} - PASSED")
        else:
            self.failed_tests.append({"test": test_name, "details": details})
            print(f"❌ {test_name} - FAILED: {details}")

    def make_request(self, method: str, endpoint: str, data: Dict = None, 
                    token: str = None, files: Dict = None) -> tuple[bool, Dict]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        if files:
            headers.pop('Content-Type', None)  # Let requests handle multipart

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                if files:
                    response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
                else:
                    response = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, headers=headers, json=data, timeout=30)
            else:
                return False, {"error": f"Unsupported method: {method}"}

            if response.status_code < 400:
                return True, response.json() if response.content else {}
            else:
                return False, {
                    "status_code": response.status_code,
                    "error": response.text
                }
        except Exception as e:
            return False, {"error": str(e)}

    def test_api_health(self):
        """Test basic API health"""
        success, response = self.make_request('GET', '')
        self.log_result(
            "API Health Check", 
            success and response.get('message') == 'Sarthak-AI Sovereign API',
            f"Response: {response}"
        )
        return success

    def test_seva_setu_chat_english(self):
        """Test Seva Setu Bot chat in English"""
        data = {
            "message": "Hello, I need help with passport application",
            "user_id": "test_user"
        }
        
        success, response = self.make_request('POST', 'consular/chat', data)
        
        if success and 'session_id' in response and 'response' in response:
            self.session_id = response['session_id']
            # Check if response contains bot name
            bot_response = response['response'].lower()
            has_seva_setu = 'seva setu' in bot_response or 'seva setu bot' in bot_response
            self.log_result("Seva Setu Chat (English)", True, f"Response: {response['response'][:100]}...")
            return True
        else:
            self.log_result("Seva Setu Chat (English)", False, str(response))
            return False

    def test_seva_setu_chat_hindi(self):
        """Test Seva Setu Bot chat in Hindi"""
        data = {
            "message": "नमस्ते, मुझे पासपोर्ट के बारे में जानकारी चाहिए",
            "user_id": "test_user"
        }
        
        success, response = self.make_request('POST', 'consular/chat', data)
        
        if success and 'response' in response:
            # Check if response is in Hindi (contains Devanagari script)
            bot_response = response['response']
            has_hindi = any('\u0900' <= char <= '\u097F' for char in bot_response)
            self.log_result("Seva Setu Chat (Hindi)", has_hindi, f"Response: {bot_response[:100]}...")
            return has_hindi
        else:
            self.log_result("Seva Setu Chat (Hindi)", False, str(response))
            return False

    def test_seva_setu_chat_afrikaans(self):
        """Test Seva Setu Bot chat in Afrikaans"""
        data = {
            "message": "Hallo, ek het hulp nodig met my paspoort aansoek",
            "user_id": "test_user"
        }
        
        success, response = self.make_request('POST', 'consular/chat', data)
        
        if success and 'response' in response:
            bot_response = response['response'].lower()
            # Check for Afrikaans words in response
            afrikaans_words = ['help', 'paspoort', 'aansoek', 'hulp', 'jou', 'jy']
            has_afrikaans = any(word in bot_response for word in afrikaans_words)
            self.log_result("Seva Setu Chat (Afrikaans)", True, f"Response: {response['response'][:100]}...")
            return True
        else:
            self.log_result("Seva Setu Chat (Afrikaans)", False, str(response))
            return False

    def test_seva_setu_chat_zulu(self):
        """Test Seva Setu Bot chat in Zulu"""
        data = {
            "message": "Sawubona, ngidinga usizo ngephasipoti yami",
            "user_id": "test_user"
        }
        
        success, response = self.make_request('POST', 'consular/chat', data)
        
        if success and 'response' in response:
            self.log_result("Seva Setu Chat (Zulu)", True, f"Response: {response['response'][:100]}...")
            return True
        else:
            self.log_result("Seva Setu Chat (Zulu)", False, str(response))
            return False

    def test_official_contact_info(self):
        """Test if bot provides official contact information"""
        data = {
            "message": "What is the emergency contact number?",
            "user_id": "test_user"
        }
        
        success, response = self.make_request('POST', 'consular/chat', data)
        
        if success and 'response' in response:
            bot_response = response['response']
            has_contact = '+27 6830 38144' in bot_response
            self.log_result("Official Contact Info", has_contact, f"Response: {bot_response[:100]}...")
            return has_contact
        else:
            self.log_result("Official Contact Info", False, str(response))
            return False

    def test_vfs_timings(self):
        """Test if bot provides VFS Johannesburg timings"""
        data = {
            "message": "What are the VFS Johannesburg office timings?",
            "user_id": "test_user"
        }
        
        success, response = self.make_request('POST', 'consular/chat', data)
        
        if success and 'response' in response:
            bot_response = response['response']
            has_timings = ('08:00' in bot_response and '15:00' in bot_response) or ('8:00' in bot_response and '3:00' in bot_response)
            self.log_result("VFS Timings", has_timings, f"Response: {bot_response[:100]}...")
            return has_timings
        else:
            self.log_result("VFS Timings", False, str(response))
            return False

    def test_passport_info(self):
        """Test passport information from official sources"""
        data = {
            "message": "How do I apply for a new passport?",
            "user_id": "test_user"
        }
        
        success, response = self.make_request('POST', 'consular/chat', data)
        
        if success and 'response' in response:
            bot_response = response['response'].lower()
            has_passport_info = 'passport' in bot_response and ('vfs' in bot_response or 'application' in bot_response)
            self.log_result("Passport Information", has_passport_info, f"Response: {response['response'][:100]}...")
            return has_passport_info
        else:
            self.log_result("Passport Information", False, str(response))
            return False

    def test_visa_info(self):
        """Test visa information from official sources"""
        data = {
            "message": "What types of visas are available?",
            "user_id": "test_user"
        }
        
        success, response = self.make_request('POST', 'consular/chat', data)
        
        if success and 'response' in response:
            bot_response = response['response'].lower()
            has_visa_info = 'visa' in bot_response and ('tourist' in bot_response or 'business' in bot_response or 'e-visa' in bot_response)
            self.log_result("Visa Information", has_visa_info, f"Response: {response['response'][:100]}...")
            return has_visa_info
        else:
            self.log_result("Visa Information", False, str(response))
            return False

    def test_oci_info(self):
        """Test OCI information from official sources"""
        data = {
            "message": "Tell me about OCI registration",
            "user_id": "test_user"
        }
        
        success, response = self.make_request('POST', 'consular/chat', data)
        
        if success and 'response' in response:
            bot_response = response['response'].lower()
            has_oci_info = 'oci' in bot_response or 'overseas citizen' in bot_response
            self.log_result("OCI Information", has_oci_info, f"Response: {response['response'][:100]}...")
            return has_oci_info
        else:
            self.log_result("OCI Information", False, str(response))
            return False

    def test_document_scan(self):
        """Test document scanning functionality"""
        # Create a simple base64 encoded test image
        test_image = base64.b64encode(b"fake_image_data").decode()
        
        data = {
            "image_base64": test_image,
            "document_type": "passport",
            "session_id": self.session_id or "test_session"
        }
        
        success, response = self.make_request('POST', 'consular/document-scan', data)
        
        self.log_result(
            "Document Scan",
            success and response.get('success') == True,
            str(response)
        )
        return success

    def test_form_submit(self):
        """Test form submission functionality"""
        data = {
            "session_id": self.session_id or "test_session",
            "form_data": {
                "full_name": "Test User",
                "email": "test@example.com",
                "phone": "+27123456789"
            }
        }
        
        success, response = self.make_request('POST', 'consular/form-submit', data)
        
        self.log_result(
            "Form Submit",
            success and response.get('success') == True,
            str(response)
        )
        return success

    def test_session_retrieval(self):
        """Test session retrieval"""
        if not self.session_id:
            self.log_result("Session Retrieval", False, "No session ID available")
            return False
            
        success, response = self.make_request('GET', f'consular/session/{self.session_id}')
        
        self.log_result(
            "Session Retrieval",
            success and 'id' in response,
            str(response)
        )
        return success

    def test_voice_input(self):
        """Test voice input endpoint"""
        # Create a simple test file
        test_content = b"Test audio content"
        files = {'audio_file': ('test_audio.wav', test_content, 'audio/wav')}
        data = {'session_id': self.session_id or 'test_session'}
        
        success, response = self.make_request(
            'POST', 'consular/voice-input', 
            data=data, files=files
        )
        
        self.log_result(
            "Voice Input",
            success and response.get('success') == True,
            str(response)
        )
        return success

    def test_super_admin_login(self):
        """Test Super Admin authentication"""
        data = {
            "email": "superadmin@sarthak.ai",
            "password": "Admin@2025"
        }
        success, response = self.make_request('POST', 'auth/super-admin/login', data)
        
        if success and 'token' in response:
            self.super_admin_token = response['token']
            self.log_result("Super Admin Login", True)
            return True
        else:
            self.log_result("Super Admin Login", False, str(response))
            return False

    def test_local_admin_dashboard(self):
        """Test Local Admin dashboard access"""
        if not self.super_admin_token:
            self.log_result("Local Admin Dashboard", False, "No admin token")
            return False

        success, response = self.make_request(
            'GET', 'local-admin/dashboard', token=self.super_admin_token
        )
        
        if success:
            self.log_result("Local Admin Dashboard", True)
            return True
        else:
            self.log_result("Local Admin Dashboard", False, str(response))
            return False

    def run_seva_setu_tests(self):
        """Run comprehensive Seva Setu Bot test suite"""
        print("🚀 Starting Seva Setu Bot Testing...")
        print("🙏 Testing Consulate General of India Johannesburg Bot")
        print("=" * 60)
        
        # Core API Tests
        if not self.test_api_health():
            print("❌ API is not responding. Stopping tests.")
            return self.generate_report()
        
        # Seva Setu Bot Core Tests
        print("\n🤖 Testing Seva Setu Bot Chat Functionality...")
        self.test_seva_setu_chat_english()
        
        # Multi-language Tests
        print("\n🌍 Testing Multi-language Support...")
        self.test_seva_setu_chat_hindi()
        self.test_seva_setu_chat_afrikaans()
        self.test_seva_setu_chat_zulu()
        
        # Official Information Tests
        print("\n📋 Testing Official Information...")
        self.test_official_contact_info()
        self.test_vfs_timings()
        self.test_passport_info()
        self.test_visa_info()
        self.test_oci_info()
        
        # Feature Tests
        print("\n🔧 Testing Bot Features...")
        self.test_document_scan()
        self.test_form_submit()
        self.test_session_retrieval()
        self.test_voice_input()
        
        # Admin Tests
        print("\n👨‍💼 Testing Admin Functionality...")
        if self.test_super_admin_login():
            self.test_local_admin_dashboard()
        
        return self.generate_report()

    def generate_report(self):
        """Generate test report"""
        print("\n" + "=" * 60)
        print("📊 SEVA SETU BOT TEST RESULTS")
        print("=" * 60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {len(self.failed_tests)}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "0%")
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for failure in self.failed_tests:
                print(f"  • {failure['test']}: {failure['details']}")
        
        print("\n🎯 KEY FINDINGS:")
        if self.session_id:
            print("  ✅ Seva Setu Bot chat working")
        if self.super_admin_token:
            print("  ✅ Admin authentication working")
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "failed_tests": len(self.failed_tests),
            "success_rate": (self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0,
            "failures": self.failed_tests,
            "session_id": self.session_id,
            "admin_token": bool(self.super_admin_token)
        }

def main():
    """Main test execution"""
    tester = SevaSetuBotTester()
    results = tester.run_seva_setu_tests()
    
    # Return appropriate exit code
    return 0 if results["success_rate"] >= 70 else 1

if __name__ == "__main__":
    sys.exit(main())