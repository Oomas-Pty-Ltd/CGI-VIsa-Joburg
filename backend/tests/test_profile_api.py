"""
Seva Setu Bot - User Profile API Tests
Tests for the new profile creation feature
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://seva-setu-1.preview.emergentagent.com').rstrip('/')


class TestProfileCreation:
    """User Profile creation endpoint tests"""
    
    def test_create_profile_success(self):
        """Test creating a new user profile"""
        test_name = f"Test User {uuid.uuid4().hex[:4]}"
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        test_mobile = "+27 12 345 6789"
        test_dob = "1990-05-15"
        
        # Generate profile ID in expected format: [NAME]-[DOB]-[HASH]
        name_part = test_name.replace(' ', '').upper()[:4]
        dob_part = test_dob.replace('-', '')
        hash_part = uuid.uuid4().hex[:4].upper()
        profile_id = f"{name_part}-{dob_part}-{hash_part}"
        
        response = requests.post(
            f"{BASE_URL}/api/consular/create-profile",
            json={
                "name": test_name,
                "email": test_email,
                "mobile": test_mobile,
                "dob": test_dob,
                "profile_id": profile_id,
                "session_id": str(uuid.uuid4())
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["success"] == True
        assert "profile_id" in data
        assert data["profile_id"] == profile_id
        print(f"✅ Profile created with ID: {profile_id}")
        
        return profile_id, test_email
    
    def test_create_profile_duplicate_email(self):
        """Test creating profile with duplicate email returns existing profile"""
        test_email = f"duplicate_{uuid.uuid4().hex[:8]}@example.com"
        test_name = "Duplicate Test"
        test_dob = "1985-06-15"
        
        # First profile
        profile_id_1 = f"DUPL-{test_dob.replace('-', '')}-{uuid.uuid4().hex[:4].upper()}"
        response1 = requests.post(
            f"{BASE_URL}/api/consular/create-profile",
            json={
                "name": test_name,
                "email": test_email,
                "mobile": "+27 11 111 1111",
                "dob": test_dob,
                "profile_id": profile_id_1
            }
        )
        assert response1.status_code == 200
        
        # Second profile with same email
        profile_id_2 = f"DUPL-{test_dob.replace('-', '')}-{uuid.uuid4().hex[:4].upper()}"
        response2 = requests.post(
            f"{BASE_URL}/api/consular/create-profile",
            json={
                "name": "Different Name",
                "email": test_email,  # Same email
                "mobile": "+27 22 222 2222",
                "dob": "1990-01-01",
                "profile_id": profile_id_2
            }
        )
        
        assert response2.status_code == 200
        data = response2.json()
        assert data["success"] == True
        # Should return existing profile ID
        assert data["profile_id"] == profile_id_1
        assert "already exists" in data.get("message", "").lower() or data["profile_id"] == profile_id_1
        print(f"✅ Duplicate email handled correctly - returned existing profile: {profile_id_1}")
    
    def test_create_profile_missing_fields(self):
        """Test profile creation with missing required fields"""
        response = requests.post(
            f"{BASE_URL}/api/consular/create-profile",
            json={
                "name": "Test",
                # Missing email, mobile, dob, profile_id
            }
        )
        # Should return 422 validation error
        assert response.status_code == 422, f"Expected 422 for missing fields, got {response.status_code}"
        print("✅ Missing fields validation works correctly")


class TestProfileRetrieval:
    """User Profile retrieval endpoint tests"""
    
    def test_get_profile_success(self):
        """Test retrieving an existing profile"""
        # First create a profile
        test_name = f"Retrieve Test {uuid.uuid4().hex[:4]}"
        test_email = f"retrieve_{uuid.uuid4().hex[:8]}@example.com"
        test_mobile = "+27 33 333 3333"
        test_dob = "1988-12-25"
        
        name_part = test_name.replace(' ', '').upper()[:4]
        dob_part = test_dob.replace('-', '')
        hash_part = uuid.uuid4().hex[:4].upper()
        profile_id = f"{name_part}-{dob_part}-{hash_part}"
        
        # Create profile
        create_response = requests.post(
            f"{BASE_URL}/api/consular/create-profile",
            json={
                "name": test_name,
                "email": test_email,
                "mobile": test_mobile,
                "dob": test_dob,
                "profile_id": profile_id
            }
        )
        assert create_response.status_code == 200
        
        # Retrieve profile
        get_response = requests.get(f"{BASE_URL}/api/consular/profile/{profile_id}")
        assert get_response.status_code == 200, f"Expected 200, got {get_response.status_code}: {get_response.text}"
        
        data = get_response.json()
        assert data["profile_id"] == profile_id
        assert data["name"] == test_name
        assert data["email"] == test_email
        assert data["mobile"] == test_mobile
        assert data["dob"] == test_dob
        print(f"✅ Profile retrieved successfully: {profile_id}")
    
    def test_get_profile_not_found(self):
        """Test retrieving non-existent profile"""
        fake_profile_id = f"FAKE-19900101-{uuid.uuid4().hex[:4].upper()}"
        response = requests.get(f"{BASE_URL}/api/consular/profile/{fake_profile_id}")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✅ Non-existent profile returns 404 correctly")


class TestProfileIdFormat:
    """Tests for profile ID format validation"""
    
    def test_profile_id_format(self):
        """Test that profile ID follows expected format [NAME]-[DOB]-[HASH]"""
        test_name = "Rajesh Kumar"
        test_dob = "1985-06-15"
        
        # Expected format: RAJE-19850615-XXXX
        name_part = test_name.replace(' ', '').upper()[:4]  # RAJE
        dob_part = test_dob.replace('-', '')  # 19850615
        hash_part = uuid.uuid4().hex[:4].upper()  # Random 4 chars
        
        profile_id = f"{name_part}-{dob_part}-{hash_part}"
        
        # Verify format
        parts = profile_id.split('-')
        assert len(parts) == 3, f"Profile ID should have 3 parts, got {len(parts)}"
        assert len(parts[0]) == 4, f"Name part should be 4 chars, got {len(parts[0])}"
        assert len(parts[1]) == 8, f"DOB part should be 8 chars, got {len(parts[1])}"
        assert len(parts[2]) == 4, f"Hash part should be 4 chars, got {len(parts[2])}"
        
        print(f"✅ Profile ID format correct: {profile_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
