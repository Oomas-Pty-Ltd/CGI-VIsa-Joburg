# Seva Setu Bot - Complete Use Cases and Test Cases Document

## Version: 2.0
## Date: December 2025
## Reference Sites: 
- https://www.cgijoburg.gov.in
- https://vfs.matchlessmfs.com/

---

# PART 1: USE CASES

## UC-001: New User Registration & Profile Creation
**Actor:** Indian/South African citizen  
**Precondition:** User has internet access  
**Flow:**
1. User opens https://seva-bridge-1.preview.emergentagent.com/consular
2. User clicks "Create Profile" button
3. System displays profile form with fields:
   - Full Name (required)
   - Email (required)
   - Mobile (required)
   - Date of Birth (required)
   - Gender
   - Nationality (default: Indian)
   - Father's Name
   - Mother's Name
   - Spouse Name
   - Place of Birth
   - Current Address
   - Permanent Address
   - Passport Number
   - Aadhar Number
   - PAN Number
   - Emergency Contact
   - Occupation
4. User fills required fields and submits
5. System generates unique Profile ID: [NAME]-[DOB]-[HASH]
6. System displays confirmation with Profile ID
7. Profile info appears in left panel

**Expected Result:** Profile created with unique ID  
**Status:** ✅ IMPLEMENTED

---

## UC-002: Family Profile Linking
**Actor:** Primary profile holder  
**Precondition:** User has created profile  
**Flow:**
1. User accesses "Add Family Member" option
2. System displays family member form:
   - Name (required)
   - Relationship (spouse/child/parent/sibling)
   - Date of Birth
   - Gender
   - Passport Number
3. User fills form and confirms consent
4. System generates Family Member ID: FAM-[NAME]-[DOB]-[HASH]
5. Family member linked to primary profile
6. Family member can share documents with consent

**Expected Result:** Family member linked to profile  
**Status:** ✅ IMPLEMENTED (Backend API ready)

---

## UC-003: Document Upload with Validity Tracking
**Actor:** Profile holder  
**Precondition:** User has profile  
**Flow:**
1. User clicks document upload button
2. System prompts for document details:
   - Document Type (passport, birth certificate, etc.)
   - Is Original? (Yes/No)
   - Issue Date
   - Expiry Date (if applicable)
   - Document Number
   - Issuing Authority
3. User uploads document file (JPG, PNG, PDF)
4. System:
   - Generates Document ID: [ProfileID]-[DocType]-[Date]-[Hash]
   - Extracts data using AI OCR
   - Calculates validity status
   - Stores document securely

**Validity Rules:**
| Document Type | Original Validity | Copy Validity |
|---------------|-------------------|---------------|
| Passport | Until expiry date | 90 days from issue |
| Birth Certificate | Permanent | 90 days |
| Death Certificate | Permanent | 90 days |
| Marriage Certificate | Permanent (may need affidavit) | 90 days |
| Driving License | Until expiry date | 90 days |
| National ID/Aadhar | Permanent | 90 days |
| PAN Card | Permanent | 90 days |
| Photograph | 6 months max age | 90 days |
| Police Report | 90 days | 90 days |
| Affidavit | 90 days | 90 days |

**Expected Result:** Document stored with validity tracking  
**Status:** ✅ IMPLEMENTED

---

## UC-004: Service Application with Pre-filled Data
**Actor:** Profile holder with documents  
**Precondition:** User has profile and uploaded documents  
**Flow:**
1. User selects service (e.g., "Passport Renewal")
2. System checks profile and document completeness
3. System pre-fills form with:
   - Personal details from profile
   - Document details from uploaded documents
4. User reviews and confirms data
5. User uploads any missing documents
6. System validates all requirements met
7. Application submitted with unique Application ID

**Services Available:**
| Service | Fee (ZAR) | Processing Time | Documents Required |
|---------|-----------|-----------------|-------------------|
| New Passport | 1,395 | 4-6 weeks | 2 |
| Passport Renewal | 1,395 | 4-6 weeks | 2 |
| Tourist Visa | 510 | 5-7 days | 1 |
| Business Visa | 1,500 | 5-7 days | 1 |
| Student Visa | 150 | 4-6 weeks | 4 |
| Fresh OCI | 5,015 | 8-12 weeks | 3 |
| OCI Renewal | 765 | 4-6 weeks | 2 |
| PCC | 495 | 2-4 weeks | 2 |
| Birth Registration | 405 | 1-4 weeks | 4 |
| Marriage Certificate | 492 | 1-2 weeks | 2 |
| Attestation | 225 | 1-2 weeks | 1 |

**Expected Result:** Application submitted with pre-filled data  
**Status:** 🔄 PARTIAL (Service selection in progress)

---

## UC-005: Multi-language Conversation
**Actor:** User (any language)  
**Precondition:** None  
**Flow:**
1. User selects language from 50+ options:
   - 22 Indian languages (Hindi, Bengali, Telugu, Tamil, etc.)
   - 11 South African languages (Zulu, Xhosa, Afrikaans, etc.)
   - 20+ International languages
2. User types/speaks query in selected language
3. Bot detects language and responds in same language/script
4. All UI elements adapt to language direction (LTR/RTL)

**Expected Result:** Full conversation in user's language  
**Status:** ✅ IMPLEMENTED (50+ languages)

---

## UC-006: Document Expiry Alert
**Actor:** System (automated)  
**Precondition:** Documents uploaded with expiry dates  
**Flow:**
1. System daily checks document validity
2. For documents expiring within 30 days:
   - Status changes to "expiring_soon"
   - Alert message displayed in profile
3. For expired documents:
   - Status changes to "expired"
   - Document marked as invalid for applications

**Expected Result:** Proactive expiry notifications  
**Status:** ✅ IMPLEMENTED

---

## UC-007: Marriage Certificate Affidavit Flow
**Actor:** User needing marriage certificate reproduction  
**Precondition:** Original marriage certificate uploaded  
**Flow:**
1. System detects marriage certificate document
2. If certificate needs reproduction:
   - System flags "needs_affidavit": true
   - Prompts user to upload affidavit
3. User uploads sworn affidavit
4. System links affidavit to marriage certificate
5. Combined document valid for application

**Expected Result:** Marriage certificate with affidavit properly handled  
**Status:** ✅ IMPLEMENTED

---

## UC-008: Super Admin Analytics
**Actor:** System administrator  
**Precondition:** Admin login  
**Flow:**
1. Admin logs in with credentials
2. Dashboard displays:
   - Total profiles created
   - Total documents uploaded
   - Applications by status
   - Document validity summary
   - Language usage statistics
   - Service popularity metrics

**Expected Result:** Comprehensive analytics dashboard  
**Status:** ✅ IMPLEMENTED (Basic)

---

# PART 2: TEST CASES

## Backend API Tests

### TC-API-001: Create Profile (Basic)
- **Endpoint:** POST /api/consular/create-profile
- **Input:** {name, email, mobile, dob, profile_id}
- **Expected:** {success: true, profile_id: "XXXX-YYYYMMDD-HASH"}
- **Status:** ✅ PASS

### TC-API-002: Create Profile (Full)
- **Endpoint:** POST /api/consular/create-profile
- **Input:** All profile fields including extended data
- **Expected:** Profile created with all fields stored
- **Status:** ✅ PASS

### TC-API-003: Get Profile
- **Endpoint:** GET /api/consular/profile/{profile_id}
- **Expected:** Full profile data returned
- **Status:** ✅ PASS

### TC-API-004: Update Profile
- **Endpoint:** PUT /api/consular/profile/{profile_id}
- **Input:** Updated fields
- **Expected:** Profile updated, updated_at changed
- **Status:** ✅ PASS

### TC-API-005: Add Family Member
- **Endpoint:** POST /api/consular/profile/{id}/family
- **Input:** {name, relationship, dob, gender}
- **Expected:** Family member ID returned
- **Status:** ✅ PASS

### TC-API-006: Get Family Members
- **Endpoint:** GET /api/consular/profile/{id}/family
- **Expected:** List of family members
- **Status:** ✅ PASS

### TC-API-007: Add Document
- **Endpoint:** POST /api/consular/profile/{id}/document
- **Input:** Document details + file
- **Expected:** Document ID + validity status
- **Status:** ✅ PASS

### TC-API-008: Get Documents with Validity
- **Endpoint:** GET /api/consular/profile/{id}/documents
- **Expected:** Documents list with recalculated validity
- **Status:** ✅ PASS

### TC-API-009: Document Validity - Original Passport
- **Input:** is_original=true, expiry_date=future
- **Expected:** status="active", valid until expiry
- **Status:** ✅ PASS

### TC-API-010: Document Validity - Copy (90 days)
- **Input:** is_original=false, issue_date=80 days ago
- **Expected:** status="expiring_soon", 10 days remaining
- **Status:** ✅ PASS

### TC-API-011: Document Validity - Expired Copy
- **Input:** is_original=false, issue_date=100 days ago
- **Expected:** status="expired", is_valid=false
- **Status:** ✅ PASS

### TC-API-012: Document Validity - Birth Certificate
- **Input:** document_type="birth_certificate", is_original=true
- **Expected:** status="permanent", no expiry
- **Status:** ✅ PASS

### TC-API-013: Document Validity - Marriage Certificate
- **Input:** document_type="marriage_certificate"
- **Expected:** needs_affidavit=true in response
- **Status:** ✅ PASS

### TC-API-014: Chat Endpoint
- **Endpoint:** POST /api/consular/chat
- **Input:** {message, session_id, language}
- **Expected:** AI response in same language
- **Status:** ✅ PASS

### TC-API-015: Feedback Endpoint
- **Endpoint:** POST /api/consular/feedback
- **Input:** {session_id, message_index, feedback: "positive/negative"}
- **Expected:** Feedback recorded
- **Status:** ✅ PASS

---

## Frontend UI Tests

### TC-UI-001: Landing Page Load
- **URL:** /
- **Expected:** Page loads with navigation buttons
- **Status:** ✅ PASS

### TC-UI-002: Consular Bot Page Load
- **URL:** /consular
- **Expected:** Avatar, chat area, stepper visible
- **Status:** ✅ PASS

### TC-UI-003: Language Selector
- **Action:** Click language dropdown
- **Expected:** 50+ languages displayed
- **Status:** ✅ PASS

### TC-UI-004: Language Selection Hindi
- **Action:** Select Hindi, send message
- **Expected:** Response in Devanagari script
- **Status:** ✅ PASS

### TC-UI-005: Create Profile Button
- **Action:** Click "Create Profile"
- **Expected:** Profile form modal opens
- **Status:** ✅ PASS

### TC-UI-006: Profile Form Validation
- **Action:** Submit empty form
- **Expected:** Validation errors shown
- **Status:** ✅ PASS

### TC-UI-007: Profile Creation Success
- **Action:** Fill all fields, submit
- **Expected:** Profile ID generated, shown in UI
- **Status:** ✅ PASS

### TC-UI-008: Profile Badge Display
- **Action:** After profile creation
- **Expected:** Profile badge at bottom left
- **Status:** ✅ PASS

### TC-UI-009: Feedback Buttons
- **Action:** View bot response
- **Expected:** 👍👎 buttons visible
- **Status:** ✅ PASS

### TC-UI-010: Feedback Click
- **Action:** Click 👍
- **Expected:** Toast shows, button changes color
- **Status:** ✅ PASS

### TC-UI-011: File Upload
- **Action:** Click upload, select PDF
- **Expected:** File accepted, processing starts
- **Status:** ✅ PASS

### TC-UI-012: File Validation
- **Action:** Upload .exe file
- **Expected:** Error: Invalid format
- **Status:** ✅ PASS

### TC-UI-013: Camera Dialog
- **Action:** Click camera button
- **Expected:** Webcam dialog opens
- **Status:** ✅ PASS

### TC-UI-014: Voice Toggle
- **Action:** Toggle voice switch
- **Expected:** TTS enabled/disabled
- **Status:** ✅ PASS

### TC-UI-015: Mic Recording
- **Action:** Click mic button
- **Expected:** Button turns red, recording starts
- **Status:** ✅ PASS

### TC-UI-016: Super Admin Login
- **Action:** Login with credentials
- **Expected:** Redirect to dashboard
- **Status:** ✅ PASS

### TC-UI-017: Dashboard Analytics
- **Action:** View dashboard
- **Expected:** Companies, Sessions, Documents counts
- **Status:** ✅ PASS

---

## Integration Tests

### TC-INT-001: Profile + Document Flow
1. Create profile
2. Upload passport document
3. Verify document appears in profile
4. Check validity status
- **Status:** ✅ PASS

### TC-INT-002: Family Member + Document
1. Create profile
2. Add family member
3. Upload document for family member
4. Verify linked correctly
- **Status:** ✅ PASS

### TC-INT-003: Multi-language Chat Session
1. Start chat in English
2. Switch to Hindi
3. Continue conversation
4. Verify context maintained
- **Status:** ✅ PASS

### TC-INT-004: Document Validity Update
1. Upload document
2. Wait (simulate time)
3. Check validity recalculation
- **Status:** ✅ PASS

---

# PART 3: TEST SUMMARY

## Test Execution Results

| Category | Total | Passed | Failed | Partial |
|----------|-------|--------|--------|---------|
| Backend API | 15 | 15 | 0 | 0 |
| Frontend UI | 17 | 17 | 0 | 0 |
| Integration | 4 | 4 | 0 | 0 |
| **TOTAL** | **36** | **36** | **0** | **0** |

## Pass Rate: 100%

---

# PART 4: DOCUMENT VALIDITY RULES REFERENCE

## Original Documents
| Document Type | Validity | Notes |
|---------------|----------|-------|
| Passport | Until expiry date | Check expiry before travel |
| Birth Certificate | Permanent | Never expires |
| Death Certificate | Permanent | Never expires |
| Marriage Certificate | Permanent* | *May need affidavit for reproduction |
| Driving License | Until expiry date | Country-specific rules |
| National ID / Aadhar | Permanent | Lifetime validity |
| PAN Card | Permanent | Lifetime validity |
| Voter ID | Permanent | Lifetime validity |

## Copies/Duplicates
| Document Type | Copy Validity | Renewal Required |
|---------------|---------------|------------------|
| All Documents | 90 days from issue | Must be re-certified after 90 days |

## Special Cases
| Document | Special Rule |
|----------|-------------|
| Marriage Certificate | May require affidavit for legal proceedings |
| Photographs | Must be recent (< 6 months old) |
| Police Reports | Valid only 90 days |
| Affidavits | Valid only 90 days |

---

# PART 5: GITHUB REPOSITORY STRUCTURE

```
/app/
├── backend/
│   ├── consular_routes.py     # Main API endpoints
│   ├── server.py              # FastAPI server
│   ├── knowledge_scraper.py   # CGI/VFS content scraper
│   ├── voice_service.py       # TTS integration
│   └── tests/
│       ├── test_seva_setu_api.py
│       └── test_profile_api.py
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── ConsularBot.jsx    # Main bot UI (50+ languages)
│       │   ├── Landing.jsx
│       │   └── SuperAdminDashboard.jsx
│       └── components/ui/
├── memory/
│   └── PRD.md                 # Product requirements
├── test_reports/
│   ├── iteration_1.json
│   ├── iteration_2.json
│   ├── iteration_3.json
│   ├── iteration_4.json
│   ├── iteration_5.json
│   └── iteration_6.json
├── EXTERNAL_TESTING_DOCUMENT.md
├── USE_CASES_AND_TEST_CASES.md    # This document
├── DOCUMENTATION.md
└── FEATURE_CHECKLIST.md
```

---

*Document Version: 2.0*
*Last Updated: December 2025*
*Total Use Cases: 8*
*Total Test Cases: 36*
*Pass Rate: 100%*
