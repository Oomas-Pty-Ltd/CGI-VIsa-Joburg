#!/usr/bin/env python3
"""
Comprehensive Backend API Testing for Seva Setu Bot
Consulate General of India Johannesburg - Multi-language Bot Testing
"""

import requests
import sys
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

class SevaSetuBotTester:
    def __init__(self, base_url="https://secure-consul.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.super_admin_token = None
        self.local_admin_token = None
        self.user_token = None
        self.company_id = None
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
            success and response.get('message') == 'Seva Setu Bot API',
            f"Response: {response}"
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

    def test_create_company(self):
        """Test company creation by Super Admin"""
        if not self.super_admin_token:
            self.log_result("Create Company", False, "No super admin token")
            return False

        timestamp = datetime.now().strftime("%H%M%S")
        data = {
            "name": f"Test Company {timestamp}",
            "email": f"testcompany{timestamp}@example.com",
            "admin_password": "TestAdmin123!",
            "llm_model": "gpt-5.2",
            "features": {"voice": True, "camera": True}
        }
        
        success, response = self.make_request(
            'POST', 'super-admin/companies', data, self.super_admin_token
        )
        
        if success and 'id' in response:
            self.company_id = response['id']
            self.test_company_email = data['email']
            self.test_company_password = data['admin_password']
            self.log_result("Create Company", True)
            return True
        else:
            self.log_result("Create Company", False, str(response))
            return False

    def test_local_admin_login(self):
        """Test Local Admin authentication"""
        if not hasattr(self, 'test_company_email'):
            self.log_result("Local Admin Login", False, "No test company created")
            return False

        data = {
            "email": self.test_company_email,
            "password": self.test_company_password
        }
        success, response = self.make_request('POST', 'auth/local-admin/login', data)
        
        if success and 'token' in response:
            self.local_admin_token = response['token']
            self.log_result("Local Admin Login", True)
            return True
        else:
            self.log_result("Local Admin Login", False, str(response))
            return False

    def test_user_registration(self):
        """Test user registration"""
        timestamp = datetime.now().strftime("%H%M%S")
        data = {
            "email": f"testuser{timestamp}@example.com",
            "password": "TestUser123!"
        }
        
        success, response = self.make_request('POST', 'auth/user/register', data)
        
        if success and 'token' in response:
            self.user_token = response['token']
            self.log_result("User Registration", True)
            return True
        else:
            self.log_result("User Registration", False, str(response))
            return False

    def test_consular_chat(self):
        """Test consular bot chat functionality"""
        if not self.user_token:
            self.log_result("Consular Chat", False, "No user token")
            return False

        data = {
            "message": "Hello, I need help with passport application",
            "company_id": self.company_id,
            "user_id": "test_user"
        }
        
        success, response = self.make_request(
            'POST', 'consular/chat', data, self.user_token
        )
        
        if success and 'session_id' in response and 'response' in response:
            self.session_id = response['session_id']
            self.log_result("Consular Chat", True)
            return True
        else:
            self.log_result("Consular Chat", False, str(response))
            return False

    def test_local_admin_dashboard(self):
        """Test Local Admin dashboard access"""
        if not self.local_admin_token:
            self.log_result("Local Admin Dashboard", False, "No local admin token")
            return False

        success, response = self.make_request(
            'GET', 'local-admin/dashboard', token=self.local_admin_token
        )
        
        if success and 'company' in response:
            self.log_result("Local Admin Dashboard", True)
            return True
        else:
            self.log_result("Local Admin Dashboard", False, str(response))
            return False

    def test_feature_toggles(self):
        """Test feature toggle functionality"""
        if not self.local_admin_token:
            self.log_result("Feature Toggles", False, "No local admin token")
            return False

        data = {"voice": False, "camera": True}
        success, response = self.make_request(
            'PUT', 'local-admin/feature-toggles', data, self.local_admin_token
        )
        
        self.log_result(
            "Feature Toggles", 
            success and response.get('success') == True,
            str(response)
        )
        return success

    def test_whatsapp_webhook(self):
        """Test WhatsApp webhook endpoint"""
        data = {
            "phone_number": "+1234567890",
            "message": "Hello",
            "message_id": "test_msg_123",
            "timestamp": int(datetime.now().timestamp())
        }
        
        success, response = self.make_request('POST', 'whatsapp/webhook', data)
        
        self.log_result(
            "WhatsApp Webhook",
            success and response.get('success') == True,
            str(response)
        )
        return success

    def test_whatsapp_status(self):
        """Test WhatsApp status endpoint"""
        success, response = self.make_request('GET', 'whatsapp/status')
        
        self.log_result(
            "WhatsApp Status",
            success and response.get('status') == 'webhook_ready',
            str(response)
        )
        return success

    def test_super_admin_analytics(self):
        """Test Super Admin analytics"""
        if not self.super_admin_token:
            self.log_result("Super Admin Analytics", False, "No super admin token")
            return False

        success, response = self.make_request(
            'GET', 'super-admin/analytics/overview', token=self.super_admin_token
        )
        
        expected_keys = ['total_companies', 'total_sessions', 'total_documents']
        has_keys = all(key in response for key in expected_keys)
        
        self.log_result(
            "Super Admin Analytics",
            success and has_keys,
            f"Response keys: {list(response.keys()) if success else response}"
        )
        return success and has_keys

    def test_document_upload_simulation(self):
        """Test document upload (simulation without actual file)"""
        if not self.local_admin_token:
            self.log_result("Document Upload", False, "No local admin token")
            return False

        # Create a simple text file for testing
        test_content = b"Test document content for upload"
        files = {'file': ('test_document.txt', test_content, 'text/plain')}
        data = {'category': 'test'}
        
        success, response = self.make_request(
            'POST', 'local-admin/documents/upload', 
            data=data, token=self.local_admin_token, files=files
        )
        
        self.log_result(
            "Document Upload",
            success and response.get('success') == True,
            str(response)
        )
        return success

    def run_all_tests(self):
        """Run comprehensive test suite"""
        print("🚀 Starting Sarthak-AI Sovereign API Testing...")
        print("=" * 60)
        
        # Core API Tests
        if not self.test_api_health():
            print("❌ API is not responding. Stopping tests.")
            return self.generate_report()
        
        # Authentication Flow Tests
        if not self.test_super_admin_login():
            print("❌ Super Admin login failed. Stopping tests.")
            return self.generate_report()
        
        # Multi-tenant Tests
        if self.test_create_company():
            self.test_local_admin_login()
        
        # User Flow Tests
        self.test_user_registration()
        
        # Core Feature Tests
        self.test_consular_chat()
        self.test_local_admin_dashboard()
        self.test_feature_toggles()
        
        # Integration Tests
        self.test_whatsapp_webhook()
        self.test_whatsapp_status()
        self.test_super_admin_analytics()
        self.test_document_upload_simulation()
        
        return self.generate_report()

    def generate_report(self):
        """Generate test report"""
        print("\n" + "=" * 60)
        print("📊 TEST RESULTS SUMMARY")
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
        if self.super_admin_token:
            print("  ✅ Super Admin authentication working")
        if self.company_id:
            print("  ✅ Multi-tenant company creation working")
        if self.local_admin_token:
            print("  ✅ Local Admin authentication working")
        if self.user_token:
            print("  ✅ User registration working")
        if self.session_id:
            print("  ✅ Consular bot chat working")
        
        return {
            "total_tests": self.tests_run,
            "passed_tests": self.tests_passed,
            "failed_tests": len(self.failed_tests),
            "success_rate": (self.tests_passed/self.tests_run*100) if self.tests_run > 0 else 0,
            "failures": self.failed_tests,
            "tokens": {
                "super_admin": bool(self.super_admin_token),
                "local_admin": bool(self.local_admin_token),
                "user": bool(self.user_token)
            },
            "company_id": self.company_id,
            "session_id": self.session_id
        }

def main():
    """Main test execution"""
    tester = SarthakAPITester()
    results = tester.run_all_tests()
    
    # Return appropriate exit code
    return 0 if results["success_rate"] >= 80 else 1

if __name__ == "__main__":
    sys.exit(main())