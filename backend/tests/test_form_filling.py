"""
Test suite for Interactive Form-Filling System
Tests: consent flow, step-by-step confirmation, STOP/CONTINUE, NO (edit), review, submit
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestFormFillingConsent:
    """Test consent flow for form filling"""
    
    def test_initial_consent_prompt(self):
        """Test that form filling starts with consent prompt"""
        session_id = f"test-consent-{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "start"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify consent pending state
        assert data["status"] == "consent_pending"
        assert data["current_step"] == 0
        assert data["waiting_for"] == "consent"
        assert "CONSENT REQUIRED" in data["response"]
        assert "Reply YES to proceed" in data["response"]
        
    def test_consent_yes_starts_form(self):
        """Test YES command gives consent and starts form"""
        session_id = f"test-consent-yes-{uuid.uuid4().hex[:8]}"
        
        # Start form
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "start"
        })
        
        # Give consent
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "yes"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify form started
        assert data["status"] == "in_progress"
        assert data["current_step"] == 1
        assert data["progress_percent"] > 0
        assert "Thank you for your consent" in data["response"]
        assert "Step 1" in data["response"]
        
    def test_profile_not_found_error(self):
        """Test error when profile doesn't exist"""
        session_id = f"test-no-profile-{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "NON-EXISTENT-PROFILE",
            "service_type": "passport_renewal",
            "message": "start"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Profile not found" in data["response"]
        
    def test_invalid_service_type_error(self):
        """Test error for invalid service type"""
        session_id = f"test-invalid-service-{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "invalid_service",
            "message": "start"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert "Unknown service type" in data["response"]


class TestFormFillingStepByStep:
    """Test step-by-step field confirmation"""
    
    @pytest.fixture
    def form_session(self):
        """Create a form session with consent given"""
        session_id = f"test-steps-{uuid.uuid4().hex[:8]}"
        
        # Start and give consent
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "start"
        })
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "yes"
        })
        
        return session_id
    
    def test_yes_confirms_and_advances(self, form_session):
        """Test YES command confirms current field and moves to next"""
        # Confirm step 1
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": form_session,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "yes"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be on step 2
        assert data["current_step"] == 2
        assert "Confirmed" in data["response"]
        assert "Step 2" in data["response"]
        
    def test_no_enters_edit_mode(self, form_session):
        """Test NO command enters edit mode"""
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": form_session,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "no"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should be in edit mode
        assert data["waiting_for"] == "input"
        assert "Edit Mode" in data["response"]
        assert "Please type the correct value" in data["response"]
        
    def test_manual_value_input(self, form_session):
        """Test providing manual value for a field"""
        # Enter edit mode
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": form_session,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "no"
        })
        
        # Provide new value
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": form_session,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "Amit Kumar Sharma"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # Should show updated value for confirmation
        assert "Field Updated" in data["response"]
        assert "Amit Kumar Sharma" in data["response"]
        assert data["waiting_for"] == "confirmation"
        
    def test_progress_tracking(self, form_session):
        """Test progress bar updates correctly"""
        # Confirm multiple steps
        for i in range(3):
            response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
                "session_id": form_session,
                "profile_id": "AMIT-19850315-TEST",
                "service_type": "passport_renewal",
                "message": "yes"
            })
        
        data = response.json()
        
        # Progress should increase
        assert data["current_step"] >= 3
        assert data["progress_percent"] > 0
        assert data["total_steps"] == 12  # passport_renewal has 12 steps


class TestFormFillingStopContinue:
    """Test STOP and CONTINUE commands"""
    
    @pytest.fixture
    def active_form_session(self):
        """Create an active form session at step 2"""
        session_id = f"test-stop-{uuid.uuid4().hex[:8]}"
        
        # Start, consent, and confirm step 1
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "start"
        })
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "yes"
        })
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "yes"
        })
        
        return session_id
    
    def test_stop_pauses_application(self, active_form_session):
        """Test STOP command pauses the application"""
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": active_form_session,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "stop"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "paused"
        assert "Application Paused" in data["response"]
        assert "Progress Summary" in data["response"]
        assert data["waiting_for"] == "resume"
        
    def test_pause_command_works(self, active_form_session):
        """Test PAUSE command also pauses"""
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": active_form_session,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "pause"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"
        
    def test_wait_command_works(self, active_form_session):
        """Test WAIT command also pauses"""
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": active_form_session,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "wait"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"


class TestFormFillingReviewSubmit:
    """Test review mode and submission"""
    
    def test_review_mode_after_all_fields(self):
        """Test that review mode shows all fields"""
        session_id = f"test-review-{uuid.uuid4().hex[:8]}"
        
        # Start and consent
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "pcc_application",  # PCC has only 10 steps
            "message": "start"
        })
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "pcc_application",
            "message": "yes"
        })
        
        # Confirm all 10 steps
        for i in range(10):
            response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
                "session_id": session_id,
                "profile_id": "AMIT-19850315-TEST",
                "service_type": "pcc_application",
                "message": "yes"
            })
        
        data = response.json()
        
        # Should be in review mode
        assert data["status"] == "review"
        assert data["progress_percent"] == 100
        assert "Review" in data["response"] or "SUBMIT" in data["response"]
        
    def test_submit_generates_application_id(self):
        """Test SUBMIT generates application ID"""
        session_id = f"test-submit-{uuid.uuid4().hex[:8]}"
        
        # Start and consent
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "pcc_application",
            "message": "start"
        })
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "pcc_application",
            "message": "yes"
        })
        
        # Confirm all steps to reach review
        for i in range(10):
            requests.post(f"{BASE_URL}/api/consular/form-filling", json={
                "session_id": session_id,
                "profile_id": "AMIT-19850315-TEST",
                "service_type": "pcc_application",
                "message": "yes"
            })
        
        # Submit
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "pcc_application",
            "message": "submit"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "completed"
        assert "Application Submitted Successfully" in data["response"]
        assert "Application ID" in data["response"]
        assert "APP-" in data["response"]


class TestFormFillingServiceTypes:
    """Test different service types"""
    
    def test_passport_renewal_template(self):
        """Test passport_renewal has correct fields"""
        session_id = f"test-passport-{uuid.uuid4().hex[:8]}"
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "start"
        })
        
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "yes"
        })
        
        data = response.json()
        assert data["total_steps"] == 12
        assert "Passport Renewal Application" in data["response"]
        
    def test_tourist_visa_template(self):
        """Test tourist_visa has correct fields"""
        session_id = f"test-visa-{uuid.uuid4().hex[:8]}"
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "tourist_visa",
            "message": "start"
        })
        
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "tourist_visa",
            "message": "yes"
        })
        
        data = response.json()
        assert data["total_steps"] == 15
        assert "Tourist Visa Application" in data["response"]
        
    def test_oci_application_template(self):
        """Test oci_application has correct fields"""
        session_id = f"test-oci-{uuid.uuid4().hex[:8]}"
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "oci_application",
            "message": "start"
        })
        
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "oci_application",
            "message": "yes"
        })
        
        data = response.json()
        assert data["total_steps"] == 18
        assert "OCI Card Application" in data["response"]
        
    def test_birth_registration_template(self):
        """Test birth_registration has correct fields"""
        session_id = f"test-birth-{uuid.uuid4().hex[:8]}"
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "birth_registration",
            "message": "start"
        })
        
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "birth_registration",
            "message": "yes"
        })
        
        data = response.json()
        assert data["total_steps"] == 14
        assert "Child Birth Registration" in data["response"]
        
    def test_pcc_application_template(self):
        """Test pcc_application has correct fields"""
        session_id = f"test-pcc-{uuid.uuid4().hex[:8]}"
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "pcc_application",
            "message": "start"
        })
        
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "pcc_application",
            "message": "yes"
        })
        
        data = response.json()
        assert data["total_steps"] == 10
        assert "Police Clearance Certificate Application" in data["response"]


class TestFormSessionPersistence:
    """Test form session persistence in database"""
    
    def test_session_persists_form_data(self):
        """Test that form data is persisted in session"""
        session_id = f"test-persist-{uuid.uuid4().hex[:8]}"
        
        # Start and consent
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "start"
        })
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "yes"
        })
        
        # Confirm a few steps
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "yes"
        })
        
        # Get session
        response = requests.get(f"{BASE_URL}/api/consular/form-session/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["session_id"] == session_id
        assert data["profile_id"] == "AMIT-19850315-TEST"
        assert data["service_type"] == "passport_renewal"
        assert data["consent_given"] == True
        assert "form_data" in data
        assert "full_name" in data["form_data"]
        
    def test_session_not_found(self):
        """Test 404 for non-existent session"""
        response = requests.get(f"{BASE_URL}/api/consular/form-session/non-existent-session")
        assert response.status_code == 404


class TestFormFillingEdgeCases:
    """Test edge cases and error handling"""
    
    def test_alternate_yes_commands(self):
        """Test CORRECT and CONFIRM also work as YES"""
        session_id = f"test-alt-yes-{uuid.uuid4().hex[:8]}"
        
        # Start and consent
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "start"
        })
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "i agree"
        })
        
        # Test CORRECT
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "correct"
        })
        
        data = response.json()
        assert data["current_step"] == 2  # Should advance
        
    def test_alternate_no_commands(self):
        """Test EDIT and CHANGE also work as NO"""
        session_id = f"test-alt-no-{uuid.uuid4().hex[:8]}"
        
        # Start and consent
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "start"
        })
        
        requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "yes"
        })
        
        # Test EDIT
        response = requests.post(f"{BASE_URL}/api/consular/form-filling", json={
            "session_id": session_id,
            "profile_id": "AMIT-19850315-TEST",
            "service_type": "passport_renewal",
            "message": "edit"
        })
        
        data = response.json()
        assert data["waiting_for"] == "input"
        assert "Edit Mode" in data["response"]
