"""
Seva Setu Bot - Enhanced Features API Tests
Tests for: 50+ languages, extended profile, family linking, document validity tracking
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://seva-setu-1.preview.emergentagent.com').rstrip('/')


class TestExtendedProfile:
    """Extended profile fields tests (father_name, mother_name, passport_number, etc.)"""
    
    def test_create_profile_with_extended_fields(self):
        """Test creating profile with all extended fields"""
        test_id = uuid.uuid4().hex[:4].upper()
        profile_id = f"TEST-19900101-{test_id}"
        
        response = requests.post(
            f"{BASE_URL}/api/consular/create-profile",
            json={
                "name": f"Test Extended {test_id}",
                "email": f"test_extended_{test_id}@example.com",
                "mobile": "+27 12 345 6789",
                "dob": "1990-01-01",
                "profile_id": profile_id,
                "gender": "Male",
                "nationality": "Indian",
                "father_name": "Father Name Test",
                "mother_name": "Mother Name Test",
                "spouse_name": "Spouse Name Test",
                "place_of_birth": "Mumbai, India",
                "current_address": "123 Test Street, Johannesburg",
                "permanent_address": "456 Home Street, Mumbai",
                "passport_number": "K9876543",
                "aadhar_number": "1234-5678-9012",
                "pan_number": "ABCDE1234F",
                "emergency_contact": "+91 98765 43210",
                "occupation": "Software Engineer"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["success"] == True
        assert data["profile_id"] == profile_id
        print(f"✅ Extended profile created: {profile_id}")
        
        # Verify all fields are stored
        get_response = requests.get(f"{BASE_URL}/api/consular/profile/{profile_id}")
        assert get_response.status_code == 200
        profile = get_response.json()
        
        assert profile["father_name"] == "Father Name Test"
        assert profile["mother_name"] == "Mother Name Test"
        assert profile["spouse_name"] == "Spouse Name Test"
        assert profile["place_of_birth"] == "Mumbai, India"
        assert profile["passport_number"] == "K9876543"
        assert profile["aadhar_number"] == "1234-5678-9012"
        assert profile["pan_number"] == "ABCDE1234F"
        assert profile["occupation"] == "Software Engineer"
        print("✅ All extended fields verified")
        
        return profile_id
    
    def test_update_profile_extended_fields(self):
        """Test updating profile with extended fields"""
        # First create a profile
        test_id = uuid.uuid4().hex[:4].upper()
        profile_id = f"UPDT-19850615-{test_id}"
        
        requests.post(
            f"{BASE_URL}/api/consular/create-profile",
            json={
                "name": f"Update Test {test_id}",
                "email": f"update_test_{test_id}@example.com",
                "mobile": "+27 11 111 1111",
                "dob": "1985-06-15",
                "profile_id": profile_id
            }
        )
        
        # Update with extended fields
        update_response = requests.put(
            f"{BASE_URL}/api/consular/profile/{profile_id}",
            json={
                "name": f"Update Test {test_id}",
                "email": f"update_test_{test_id}@example.com",
                "mobile": "+27 11 111 1111",
                "dob": "1985-06-15",
                "profile_id": profile_id,
                "father_name": "Updated Father",
                "mother_name": "Updated Mother",
                "occupation": "Doctor"
            }
        )
        
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["success"] == True
        print(f"✅ Profile updated: {profile_id}")
        
        # Verify update
        get_response = requests.get(f"{BASE_URL}/api/consular/profile/{profile_id}")
        profile = get_response.json()
        assert profile["father_name"] == "Updated Father"
        assert profile["mother_name"] == "Updated Mother"
        assert profile["occupation"] == "Doctor"
        print("✅ Extended fields update verified")


class TestFamilyMemberLinking:
    """Family member addition and linking tests"""
    
    def test_add_family_member(self):
        """Test adding family member to profile"""
        # Create parent profile
        test_id = uuid.uuid4().hex[:4].upper()
        parent_profile_id = f"PRNT-19800101-{test_id}"
        
        requests.post(
            f"{BASE_URL}/api/consular/create-profile",
            json={
                "name": f"Parent Test {test_id}",
                "email": f"parent_{test_id}@example.com",
                "mobile": "+27 22 222 2222",
                "dob": "1980-01-01",
                "profile_id": parent_profile_id
            }
        )
        
        # Add spouse
        spouse_response = requests.post(
            f"{BASE_URL}/api/consular/profile/{parent_profile_id}/family",
            json={
                "parent_profile_id": parent_profile_id,
                "name": "Spouse Test",
                "relationship": "spouse",
                "dob": "1982-05-15",
                "gender": "Female",
                "passport_number": "L1234567"
            }
        )
        
        assert spouse_response.status_code == 200, f"Expected 200, got {spouse_response.status_code}: {spouse_response.text}"
        data = spouse_response.json()
        assert data["success"] == True
        assert "family_member_id" in data
        assert data["family_member_id"].startswith("FAM-")
        print(f"✅ Spouse added: {data['family_member_id']}")
        
        # Add child
        child_response = requests.post(
            f"{BASE_URL}/api/consular/profile/{parent_profile_id}/family",
            json={
                "parent_profile_id": parent_profile_id,
                "name": "Child Test",
                "relationship": "child",
                "dob": "2010-08-20",
                "gender": "Male"
            }
        )
        
        assert child_response.status_code == 200
        child_data = child_response.json()
        assert child_data["success"] == True
        print(f"✅ Child added: {child_data['family_member_id']}")
        
        return parent_profile_id
    
    def test_get_family_members(self):
        """Test retrieving family members"""
        # Create profile with family
        test_id = uuid.uuid4().hex[:4].upper()
        profile_id = f"FMLY-19750101-{test_id}"
        
        requests.post(
            f"{BASE_URL}/api/consular/create-profile",
            json={
                "name": f"Family Test {test_id}",
                "email": f"family_{test_id}@example.com",
                "mobile": "+27 33 333 3333",
                "dob": "1975-01-01",
                "profile_id": profile_id
            }
        )
        
        # Add family members
        requests.post(
            f"{BASE_URL}/api/consular/profile/{profile_id}/family",
            json={
                "parent_profile_id": profile_id,
                "name": "Family Member 1",
                "relationship": "spouse",
                "dob": "1978-03-10"
            }
        )
        
        requests.post(
            f"{BASE_URL}/api/consular/profile/{profile_id}/family",
            json={
                "parent_profile_id": profile_id,
                "name": "Family Member 2",
                "relationship": "child",
                "dob": "2005-07-25"
            }
        )
        
        # Get family members
        get_response = requests.get(f"{BASE_URL}/api/consular/profile/{profile_id}/family")
        assert get_response.status_code == 200
        data = get_response.json()
        
        assert data["success"] == True
        assert len(data["family_members"]) == 2
        
        relationships = [fm["relationship"] for fm in data["family_members"]]
        assert "spouse" in relationships
        assert "child" in relationships
        print(f"✅ Family members retrieved: {len(data['family_members'])} members")
    
    def test_family_member_not_found(self):
        """Test getting family for non-existent profile"""
        fake_id = f"FAKE-19990101-{uuid.uuid4().hex[:4].upper()}"
        response = requests.get(f"{BASE_URL}/api/consular/profile/{fake_id}/family")
        assert response.status_code == 404
        print("✅ Non-existent profile returns 404 for family")


class TestDocumentValidityTracking:
    """Document upload and validity tracking tests"""
    
    def test_add_document_original_passport(self):
        """Test adding original passport with expiry-based validity"""
        # Use existing test profile
        profile_id = "AMIT-19850315-TEST"
        
        # Add new passport document
        doc_response = requests.post(
            f"{BASE_URL}/api/consular/profile/{profile_id}/document",
            json={
                "profile_id": profile_id,
                "document_type": "passport",
                "document_name": "Test Passport Original",
                "is_original": True,
                "issue_date": "2023-01-15",
                "expiry_date": "2033-01-14",
                "document_number": "T1234567",
                "issuing_authority": "Passport Office Mumbai"
            }
        )
        
        assert doc_response.status_code == 200, f"Expected 200, got {doc_response.status_code}: {doc_response.text}"
        data = doc_response.json()
        
        assert data["success"] == True
        assert "document_id" in data
        assert "validity" in data
        
        validity = data["validity"]
        assert validity["is_valid"] == True
        assert validity["validity_type"] == "expiry"
        assert validity["status"] == "active"
        assert validity["days_remaining"] > 0
        print(f"✅ Original passport added: {data['document_id']}, valid for {validity['days_remaining']} days")
    
    def test_add_document_copy_90_day_rule(self):
        """Test adding document copy with 90-day validity rule"""
        profile_id = "AMIT-19850315-TEST"
        
        # Add copy issued 80 days ago (should be expiring soon)
        issue_date = (datetime.now() - timedelta(days=80)).strftime("%Y-%m-%d")
        
        doc_response = requests.post(
            f"{BASE_URL}/api/consular/profile/{profile_id}/document",
            json={
                "profile_id": profile_id,
                "document_type": "passport",
                "document_name": "Test Passport Copy",
                "is_original": False,
                "issue_date": issue_date,
                "document_number": "COPY-123"
            }
        )
        
        assert doc_response.status_code == 200
        data = doc_response.json()
        
        validity = data["validity"]
        assert validity["validity_type"] == "expiry"
        assert validity["status"] == "expiring_soon"  # 10 days remaining
        assert validity["days_remaining"] <= 15
        print(f"✅ Copy document (80 days old): status={validity['status']}, {validity['days_remaining']} days remaining")
    
    def test_add_document_expired_copy(self):
        """Test adding expired copy (>90 days old)"""
        profile_id = "AMIT-19850315-TEST"
        
        # Add copy issued 100 days ago (should be expired)
        issue_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        
        doc_response = requests.post(
            f"{BASE_URL}/api/consular/profile/{profile_id}/document",
            json={
                "profile_id": profile_id,
                "document_type": "driving_license",
                "document_name": "Test DL Copy Expired",
                "is_original": False,
                "issue_date": issue_date
            }
        )
        
        assert doc_response.status_code == 200
        data = doc_response.json()
        
        validity = data["validity"]
        assert validity["is_valid"] == False
        assert validity["status"] == "expired"
        print(f"✅ Expired copy (100 days old): is_valid={validity['is_valid']}, status={validity['status']}")
    
    def test_add_document_birth_certificate_permanent(self):
        """Test birth certificate has permanent validity"""
        profile_id = "AMIT-19850315-TEST"
        
        doc_response = requests.post(
            f"{BASE_URL}/api/consular/profile/{profile_id}/document",
            json={
                "profile_id": profile_id,
                "document_type": "birth_certificate",
                "document_name": "Test Birth Certificate Original",
                "is_original": True,
                "issue_date": "1990-01-01"
            }
        )
        
        assert doc_response.status_code == 200
        data = doc_response.json()
        
        validity = data["validity"]
        assert validity["validity_type"] == "permanent"
        assert validity["status"] == "permanent"
        assert validity["is_valid"] == True
        print(f"✅ Birth certificate (original): validity_type={validity['validity_type']}, status={validity['status']}")
    
    def test_add_document_death_certificate_permanent(self):
        """Test death certificate has permanent validity"""
        profile_id = "AMIT-19850315-TEST"
        
        doc_response = requests.post(
            f"{BASE_URL}/api/consular/profile/{profile_id}/document",
            json={
                "profile_id": profile_id,
                "document_type": "death_certificate",
                "document_name": "Test Death Certificate",
                "is_original": True,
                "issue_date": "2020-05-15"
            }
        )
        
        assert doc_response.status_code == 200
        data = doc_response.json()
        
        validity = data["validity"]
        assert validity["validity_type"] == "permanent"
        assert validity["is_valid"] == True
        print(f"✅ Death certificate: validity_type={validity['validity_type']}")
    
    def test_add_document_marriage_certificate_affidavit(self):
        """Test marriage certificate needs affidavit flag"""
        profile_id = "AMIT-19850315-TEST"
        
        doc_response = requests.post(
            f"{BASE_URL}/api/consular/profile/{profile_id}/document",
            json={
                "profile_id": profile_id,
                "document_type": "marriage_certificate",
                "document_name": "Test Marriage Certificate",
                "is_original": True,
                "issue_date": "2015-06-20",
                "issuing_authority": "Registrar of Marriages"
            }
        )
        
        assert doc_response.status_code == 200
        data = doc_response.json()
        
        validity = data["validity"]
        assert validity["validity_type"] == "affidavit"
        assert validity["needs_affidavit"] == True
        assert validity["is_valid"] == True
        print(f"✅ Marriage certificate: needs_affidavit={validity['needs_affidavit']}")
    
    def test_get_documents_with_summary(self):
        """Test getting documents with validity summary"""
        profile_id = "AMIT-19850315-TEST"
        
        response = requests.get(f"{BASE_URL}/api/consular/profile/{profile_id}/documents")
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        assert "documents" in data
        assert "summary" in data
        
        summary = data["summary"]
        assert "total" in summary
        assert "valid" in summary
        assert "expired" in summary
        assert "expiring_soon" in summary
        assert "needs_affidavit" in summary
        
        print(f"✅ Documents summary: total={summary['total']}, valid={summary['valid']}, expired={summary['expired']}, expiring_soon={summary['expiring_soon']}, needs_affidavit={summary['needs_affidavit']}")


class TestExistingTestProfile:
    """Tests using the existing test profile AMIT-19850315-TEST"""
    
    def test_existing_profile_has_extended_fields(self):
        """Verify existing test profile has extended fields"""
        response = requests.get(f"{BASE_URL}/api/consular/profile/AMIT-19850315-TEST")
        assert response.status_code == 200
        profile = response.json()
        
        assert profile["name"] == "Amit Sharma"
        assert profile["father_name"] == "Rajesh Sharma"
        assert profile["mother_name"] == "Sunita Sharma"
        assert profile["passport_number"] == "K1234567"
        assert profile["place_of_birth"] == "Mumbai"
        print("✅ Existing profile has all extended fields")
    
    def test_existing_profile_has_family_member(self):
        """Verify existing test profile has family member"""
        response = requests.get(f"{BASE_URL}/api/consular/profile/AMIT-19850315-TEST/family")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["family_members"]) >= 1
        spouse = next((fm for fm in data["family_members"] if fm["relationship"] == "spouse"), None)
        assert spouse is not None
        assert spouse["name"] == "Priya Sharma"
        print(f"✅ Existing profile has family member: {spouse['name']} ({spouse['relationship']})")
    
    def test_existing_profile_documents_validity(self):
        """Verify existing profile documents have correct validity"""
        response = requests.get(f"{BASE_URL}/api/consular/profile/AMIT-19850315-TEST/documents")
        assert response.status_code == 200
        data = response.json()
        
        # Check marriage certificate has needs_affidavit
        marriage_cert = next((d for d in data["documents"] if d["document_type"] == "marriage_certificate"), None)
        if marriage_cert:
            assert marriage_cert["validity"]["needs_affidavit"] == True
            print(f"✅ Marriage certificate needs_affidavit: {marriage_cert['validity']['needs_affidavit']}")
        
        # Check passport has expiry-based validity
        passport = next((d for d in data["documents"] if d["document_type"] == "passport"), None)
        if passport:
            assert passport["validity"]["validity_type"] == "expiry"
            assert passport["validity"]["days_remaining"] > 0
            print(f"✅ Passport validity: {passport['validity']['days_remaining']} days remaining")
        
        # Check summary
        summary = data["summary"]
        print(f"✅ Documents summary: {summary}")


class TestFeedbackEndpoint:
    """Feedback endpoint tests"""
    
    def test_submit_positive_feedback(self):
        """Test submitting positive feedback"""
        response = requests.post(
            f"{BASE_URL}/api/consular/feedback",
            json={
                "session_id": str(uuid.uuid4()),
                "message_index": 1,
                "feedback": "positive"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        print("✅ Positive feedback submitted")
    
    def test_submit_negative_feedback(self):
        """Test submitting negative feedback"""
        response = requests.post(
            f"{BASE_URL}/api/consular/feedback",
            json={
                "session_id": str(uuid.uuid4()),
                "message_index": 2,
                "feedback": "negative"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        print("✅ Negative feedback submitted")


class TestChatMultiLanguage:
    """Multi-language chat tests"""
    
    def test_chat_english(self):
        """Test chat in English"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "Hello, I need help with passport renewal",
                "language": "en",
                "enable_voice": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert len(data["response"]) > 0
        print("✅ English chat working")
    
    def test_chat_hindi(self):
        """Test chat in Hindi"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "नमस्ते, मुझे पासपोर्ट नवीनीकरण में मदद चाहिए",
                "language": "hi",
                "enable_voice": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert len(data["response"]) > 0
        print("✅ Hindi chat working")
    
    def test_chat_tamil(self):
        """Test chat in Tamil"""
        response = requests.post(
            f"{BASE_URL}/api/consular/chat",
            json={
                "message": "வணக்கம், எனக்கு பாஸ்போர்ட் புதுப்பிப்பு உதவி தேவை",
                "language": "ta",
                "enable_voice": False
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert len(data["response"]) > 0
        print("✅ Tamil chat working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
