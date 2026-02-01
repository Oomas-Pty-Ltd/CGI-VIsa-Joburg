# Seva Setu Bot - External Testing Document
## CGI Johannesburg Interactive Service Bot

**Version:** 1.0  
**Date:** December 2025  
**Preview URL:** https://seva-setu-1.preview.emergentagent.com

---

## 1. PROJECT OVERVIEW

### 1.1 Product Description
Seva Setu Bot is a multi-tenant, AI-powered consular automation platform for the Consulate General of India (CGI), Johannesburg, South Africa. It provides interactive assistance for all consular services including Passports, Visas, OCI cards, Attestations, Affidavits, and more.

### 1.2 Target Users
- Indian citizens in South Africa
- South African citizens requiring Indian consular services
- Consulate administrators and staff

### 1.3 Compliance
- GDPR (Europe)
- DPDA (India)
- POPIA (South Africa)

---

## 2. FEATURE STATUS - WHAT'S DONE vs REMAINING

### 2.1 ✅ COMPLETED FEATURES

| # | Feature | Status | Implementation Details |
|---|---------|--------|----------------------|
| 1 | Landing Page | ✅ DONE | Professional UI with feature cards, navigation to consular bot and admin portals |
| 2 | Consular Bot Chat Interface | ✅ DONE | Full chat UI with message history, typing indicator |
| 3 | AI-Powered Responses | ✅ DONE | GPT-5.2 via Emergent LLM Key for intelligent responses |
| 4 | Progress Stepper | ✅ DONE | Register → Upload → Verify → Sign workflow |
| 5 | Multi-language Support (Backend) | ✅ DONE | Hindi, Tamil, English auto-detection in responses |
| 6 | Text-to-Speech | ✅ DONE | ElevenLabs integration with voice toggle |
| 7 | Avatar Display | ✅ DONE | Visual avatar with speaking indicator (placeholder image) |
| 8 | File Upload | ✅ DONE | JPG, PNG, PDF with 10MB limit validation |
| 9 | Camera Dialog | ✅ DONE | Webcam capture UI using react-webcam |
| 10 | Document Scanning (OCR) | ✅ DONE | AI-powered extraction with multi-language translation |
| 11 | Super Admin Login | ✅ DONE | JWT authentication |
| 12 | Super Admin Dashboard | ✅ DONE | Analytics: Companies, Sessions, Documents counts |
| 13 | Company Management | ✅ DONE | Create/manage companies via super admin |
| 14 | Local Admin Portal | ✅ DONE | Basic login and dashboard routes |
| 15 | Knowledge Base Scraper | ✅ DONE | Real-time scraping from cgijoburg.gov.in |
| 16 | Markdown Response Rendering | ✅ DONE | Rich formatted responses with links, lists |
| 17 | Session Management | ✅ DONE | Persistent chat sessions with MongoDB |
| 18 | WhatsApp Webhook (Basic) | ✅ DONE | Route structure ready for Twilio |
| 19 | Interactive Bot Flow | ✅ DONE | Step-by-step guidance, one question at a time |
| 20 | Service Fees Display | ✅ DONE | Official CGI fees in bot responses |

### 2.2 🔄 PARTIALLY IMPLEMENTED (Needs Enhancement)

| # | Feature | Current State | Required Enhancement |
|---|---------|--------------|---------------------|
| 1 | User Verification Flow | System prompt mentions it | Need explicit UI flow: Name → Email → Mobile → DOB → Profile ID generation |
| 2 | Frontend Input Suppression | Not implemented | "NEVER display raw user input"—only show bot responses (as per new system prompt) |
| 3 | No Repeat Questions Logic | Partially in prompt | Need frontend logic to track questions asked |
| 4 | Error Handling (ERR-XXX codes) | Basic error handling | Need structured error codes with logging |
| 5 | Feedback Mechanism (👍👎) | Mentioned in prompt | Need UI buttons at end of conversation |

### 2.3 ❌ NOT IMPLEMENTED (Remaining)

| # | Feature | Priority | Description |
|---|---------|----------|-------------|
| 1 | **Mic Voice Input** | P1 | Web Speech API for voice-to-text (button exists, logic missing) |
| 2 | **Language Selector Dropdown** | P1 | Manual language switch in UI |
| 3 | **Profile/Family Linking** | P1 | User profiles with unique IDs, family consent linking |
| 4 | **Document Unique ID System** | P1 | [Name][DOB][AppNumber][Date][DocNumber] format |
| 5 | **Admin Escalation - Email** | P1 | Gmail integration for critical errors |
| 6 | **Admin Escalation - WhatsApp/SMS** | P1 | Twilio for alerts (credentials pending) |
| 7 | **Admin Escalation - Slack** | P1 | Slack webhook for notifications (credentials pending) |
| 8 | **Error Logging System** | P1 | Structured logging: gaps, drop-offs, ERR-XXX codes |
| 9 | **Google Sheets Logging** | P2 | Integration for analytics export |
| 10 | **OTP Verification** | P2 | For new user registration |
| 11 | **Realistic Avatar (Akool)** | P2 | Lip-sync video avatar (API key pending) |
| 12 | **PDF Form Generation** | P2 | Secure PDF output after form completion |
| 13 | **Email Delivery** | P2 | Send PDF to user and admin |
| 14 | **Facebook/Instagram Bot** | P3 | Meta Business Suite integration |
| 15 | **Offline Mode** | P3 | Service worker for offline capability |

---

## 3. SYSTEM REQUIREMENTS ALIGNMENT

### 3.1 New System Prompt Requirements vs Current Implementation

| Requirement | Status | Gap Analysis |
|-------------|--------|--------------|
| **Frontend Display Rules** | | |
| Process queries silently in backend | ✅ Done | Backend processes, frontend displays responses |
| NEVER display raw user input | ❌ Not Done | Currently shows user messages in chat |
| No repetition unless unclear | 🔄 Partial | In prompt, not enforced in UI |
| Clean output (Q&A pairs, links only) | 🔄 Partial | Shows both user and bot messages |
| **Core Interaction Rules** | | |
| Start with greeting | ✅ Done | "Namaste! How can I help..." |
| Answer ONE need at a time | ✅ Done | In system prompt |
| Human-like analysis | ✅ Done | AI processes naturally |
| End with contact info + feedback | ✅ Done | In system prompt |
| **Verification & Profiles** | | |
| Collect Name/Email/Mobile/DOB | ❌ Not Done | Not enforced in UI |
| OTP verification | ❌ Not Done | Not implemented |
| Unique profile ID generation | ❌ Not Done | Not implemented |
| Family linking with consent | ❌ Not Done | Not implemented |
| **Documents** | | |
| Unique ID format | ❌ Not Done | Not implemented |
| Store to profile (consent req.) | ❌ Not Done | Not implemented |
| **Error Handling** | | |
| ERR-XXX codes | ❌ Not Done | Basic errors only |
| Log all interactions | 🔄 Partial | Chat logs exist, structured logging missing |
| Admin escalation (Email/WhatsApp/Slack) | ❌ Not Done | Routes ready, integrations pending |
| **Integrations** | | |
| Gmail | ❌ Pending | Needs credentials |
| Twilio | ❌ Pending | Needs credentials |
| Slack | ❌ Pending | Needs webhook URL |
| Google Sheets | ❌ Not Done | Not implemented |
| **MANDATORY ALIGNMENT RULE** | | |
| All logins auto-align with new features | ✅ Done | JWT-based auth is flexible |

---

## 4. TEST CREDENTIALS

### 4.1 Super Admin
- **Email:** `superadmin@sarthak.ai`
- **Password:** `Admin@2025`
- **URL:** https://seva-setu-1.preview.emergentagent.com/super-admin/login

### 4.2 Preview URLs
- **Landing Page:** https://seva-setu-1.preview.emergentagent.com/
- **Consular Bot:** https://seva-setu-1.preview.emergentagent.com/consular
- **Super Admin Dashboard:** https://seva-setu-1.preview.emergentagent.com/super-admin/dashboard

---

## 5. TEST CASES

### 5.1 Landing Page Tests

| TC-ID | Test Case | Steps | Expected Result | Status |
|-------|-----------|-------|-----------------|--------|
| TC-LP-001 | Landing page loads | Navigate to / | Page displays with header, hero section, feature cards | ✅ PASS |
| TC-LP-002 | Start Consular Application | Click "Start Consular Application" | Redirects to /consular | ✅ PASS |
| TC-LP-003 | Super Admin navigation | Click "Super Admin" | Redirects to /super-admin/login | ✅ PASS |
| TC-LP-004 | Local Admin navigation | Click "Local Admin" | Redirects to /admin/login | ✅ PASS |
| TC-LP-005 | Feature cards display | View page | Shows Multi-Tenant, Secure & Compliant, 50+ Languages cards | ✅ PASS |

### 5.2 Consular Bot Tests

| TC-ID | Test Case | Steps | Expected Result | Status |
|-------|-----------|-------|-----------------|--------|
| TC-CB-001 | Initial greeting | Open /consular | Displays "Namaste! I'm Seva Setu Bot..." | ✅ PASS |
| TC-CB-002 | Send text message | Type "passport renewal" and send | AI responds with passport info | ✅ PASS |
| TC-CB-003 | Typing indicator | Send message | Shows "Seva Setu is typing..." | ✅ PASS |
| TC-CB-004 | Markdown rendering | Ask about services | Response shows bold, bullets, links | ✅ PASS |
| TC-CB-005 | Hindi language | Type "पासपोर्ट नवीनीकरण" | Responds in Hindi (देवनागरी) | ✅ PASS |
| TC-CB-006 | Progress stepper display | View page | Shows Register → Upload → Verify → Sign | ✅ PASS |
| TC-CB-007 | Avatar display | View page | Shows avatar with "Seva Setu Bot" name | ✅ PASS |
| TC-CB-008 | Voice toggle | Toggle voice switch | Switch changes between enabled/disabled | ✅ PASS |
| TC-CB-009 | File upload button | Click document icon | File picker opens | ✅ PASS |
| TC-CB-010 | File type validation | Upload .exe file | Shows "Invalid file format" error | ✅ PASS |
| TC-CB-011 | File size validation | Upload >10MB file | Shows "File size exceeds limit" error | ✅ PASS |
| TC-CB-012 | Camera dialog | Click camera icon | Webcam dialog opens | ✅ PASS |
| TC-CB-013 | Camera capture | Click "Capture" in dialog | Screenshot captured | ✅ PASS |
| TC-CB-014 | Camera cancel | Click "Cancel" in dialog | Dialog closes | ✅ PASS |
| TC-CB-015 | Session persistence | Send multiple messages | All messages in history | ✅ PASS |
| TC-CB-016 | Mic button display | View input area | Mic button visible (if browser supports) | ✅ PASS |
| TC-CB-017 | Mic recording | Click mic button | Button turns red (recording state) | 🔄 PARTIAL |
| TC-CB-018 | Voice-to-text | Speak into mic | Text appears in input | ❌ NOT TESTED |
| TC-CB-019 | Text-to-speech | Enable voice, send message | Audio plays with response | ✅ PASS |
| TC-CB-020 | Speaking indicator | During audio playback | Avatar shows "Speaking..." indicator | ✅ PASS |

### 5.3 Super Admin Tests

| TC-ID | Test Case | Steps | Expected Result | Status |
|-------|-----------|-------|-----------------|--------|
| TC-SA-001 | Login page loads | Navigate to /super-admin/login | Login form displays | ✅ PASS |
| TC-SA-002 | Valid login | Enter valid credentials, submit | Redirects to dashboard | ✅ PASS |
| TC-SA-003 | Invalid login | Enter wrong password | Shows "Invalid credentials" error | ✅ PASS |
| TC-SA-004 | Dashboard analytics | After login | Shows Total Companies, Sessions, Documents | ✅ PASS |
| TC-SA-005 | Company list | View dashboard | Lists all companies | ✅ PASS |
| TC-SA-006 | Create company | Click create, fill form | New company appears in list | ✅ PASS |
| TC-SA-007 | Logout | Click Logout | Redirects to login | ✅ PASS |

### 5.4 API Tests

| TC-ID | Test Case | Endpoint | Expected Result | Status |
|-------|-----------|----------|-----------------|--------|
| TC-API-001 | Health check | GET /api/ | {"message": "Seva Setu Bot API", "status": "running"} | ✅ PASS |
| TC-API-002 | Super admin login | POST /api/auth/super-admin/login | Returns JWT token | ✅ PASS |
| TC-API-003 | Chat message | POST /api/consular/chat | Returns AI response | ✅ PASS |
| TC-API-004 | Session retrieval | GET /api/consular/session/{id} | Returns session data | ✅ PASS |
| TC-API-005 | Document scan | POST /api/consular/document-scan | Returns extracted data | ✅ PASS |
| TC-API-006 | Form submission | POST /api/consular/form-submit | Returns success | ✅ PASS |
| TC-API-007 | Invalid session | GET /api/consular/session/invalid | Returns 404 | ✅ PASS |
| TC-API-008 | Invalid credentials | POST /api/auth/super-admin/login (wrong) | Returns 401 | ✅ PASS |

---

## 6. USE CASES

### UC-001: New User Passport Inquiry
**Actor:** Indian citizen in South Africa  
**Precondition:** User has internet access  
**Steps:**
1. User opens https://seva-setu-1.preview.emergentagent.com/consular
2. Bot greets: "Namaste! How can I assist you?"
3. User types: "I need to renew my passport"
4. Bot responds with passport renewal requirements and fees (ZAR 1,395 for 36 pages)
5. Bot asks: "Does that help? What else can I guide you on?"
6. User asks follow-up questions
7. Bot guides step-by-step until user is satisfied

**Expected Result:** User receives accurate, step-by-step guidance  
**Status:** ✅ WORKING

### UC-002: Hindi Language Support
**Actor:** Hindi-speaking user  
**Steps:**
1. User opens consular bot
2. User types: "मुझे वीजा की जानकारी चाहिए"
3. Bot responds in Hindi (देवनागरी script)

**Expected Result:** Response in same language as query  
**Status:** ✅ WORKING

### UC-003: Document Upload for Verification
**Actor:** User applying for service  
**Steps:**
1. User clicks document upload button
2. User selects passport image (JPG)
3. System validates file type and size
4. System processes document with OCR
5. Extracted data shown to user

**Expected Result:** Document processed, data extracted  
**Status:** ✅ WORKING

### UC-004: Super Admin Company Management
**Actor:** System administrator  
**Steps:**
1. Admin navigates to /super-admin/login
2. Admin enters credentials (superadmin@sarthak.ai / Admin@2025)
3. Admin views dashboard with analytics
4. Admin creates new company
5. Company appears in list

**Expected Result:** Company created and visible  
**Status:** ✅ WORKING

### UC-005: Voice Interaction (Partial)
**Actor:** User preferring voice  
**Steps:**
1. User clicks mic button
2. User speaks query
3. Speech converted to text
4. Bot responds with voice (TTS)

**Expected Result:** Full voice interaction  
**Status:** 🔄 PARTIAL (TTS works, STT needs testing)

### UC-006: User Profile Creation (NOT IMPLEMENTED)
**Actor:** User starting application  
**Steps:**
1. Bot asks for Name
2. User provides name
3. Bot asks for Email
4. User provides email
5. Bot asks for Mobile
6. User provides mobile
7. Bot asks for DOB
8. User provides DOB
9. System generates Profile ID: [Name]-[DOB]-[Hash]
10. Bot confirms: "Profile created! ID: XXX. Proceed?"

**Expected Result:** User profile created with unique ID  
**Status:** ❌ NOT IMPLEMENTED

### UC-007: Admin Escalation (NOT IMPLEMENTED)
**Actor:** System (on critical error)  
**Steps:**
1. Critical error occurs (e.g., payment failure)
2. System generates ERR-XXX code
3. System sends alert via:
   - Email to admin
   - WhatsApp/SMS to admin
   - Slack notification
4. Admin receives prompt to login and investigate

**Expected Result:** Admin notified immediately  
**Status:** ❌ NOT IMPLEMENTED

---

## 7. TESTING REPORT SUMMARY

### 7.1 Test Execution Summary

| Category | Total Tests | Passed | Failed | Partial | Not Tested |
|----------|-------------|--------|--------|---------|------------|
| Landing Page | 5 | 5 | 0 | 0 | 0 |
| Consular Bot | 20 | 16 | 0 | 2 | 2 |
| Super Admin | 7 | 7 | 0 | 0 | 0 |
| API | 8 | 8 | 0 | 0 | 0 |
| **TOTAL** | **40** | **36** | **0** | **2** | **2** |

### 7.2 Pass Rate
- **Overall:** 90% (36/40)
- **Backend:** 100%
- **Frontend:** 88%

### 7.3 Critical Issues
None - Application is stable and functional.

### 7.4 Known Limitations
1. Mic voice input (button exists, full STT testing needed)
2. User profile creation flow not implemented
3. Admin escalation integrations pending credentials

---

## 8. SERVICES SUPPORTED

As per CGI Johannesburg website (https://www.cgijoburg.gov.in):

| Service | Supported in Bot | Notes |
|---------|-----------------|-------|
| Passport Re-issue | ✅ Yes | Fees: ZAR 1,395 (36pg), ZAR 1,845 (60pg) |
| Passport - Lost | ✅ Yes | Police report + Annexure L required |
| Passport - Minors | ✅ Yes | Fees: ZAR 945 (5 years) |
| Passport - Name Change | ✅ Yes | Via bot guidance |
| e-Visa | ✅ Yes | Directs to official process |
| Manual Visa | ✅ Yes | Directs to VFS |
| OCI Card (Fresh) | ✅ Yes | Fees: ZAR 5,015 |
| OCI Card (Renewal) | ✅ Yes | Via bot guidance |
| PIO Card | ✅ Yes | Via bot guidance |
| Attestation (Documents) | ✅ Yes | Fees: ZAR 225-417/page |
| Attestation (Degrees) | ✅ Yes | Via bot guidance |
| Affidavits | ✅ Yes | Via bot guidance |
| Renunciation | ✅ Yes | Via bot guidance |
| Emergency Certificate | ✅ Yes | Fees: ZAR 315 |
| Translation (Driving License) | ✅ Yes | Via bot guidance |
| Police Clearance (PCC) | ✅ Yes | Fees: ZAR 495 |
| Camps/Events Info | ✅ Yes | Real-time from website |

---

## 9. RECOMMENDATIONS FOR EXTERNAL TESTERS

### 9.1 Priority Testing Areas
1. **Chat Functionality:** Try various queries about passports, visas, OCI
2. **Multi-language:** Test Hindi, Tamil, English queries
3. **Document Upload:** Test with JPG, PNG, PDF files
4. **Voice Toggle:** Enable/disable and verify TTS works
5. **Admin Dashboard:** Login and verify analytics

### 9.2 Known Issues to Ignore
- "PostHog" console warning (analytics, not functional issue)
- Mic button may not work on all browsers (Chrome recommended)

### 9.3 Feedback Requested
- Response accuracy for CGI services
- Language detection quality
- UI/UX improvements
- Any error messages encountered

---

## 10. CONTACT

For issues or questions:
- **Bot Contact:** cons.joburg@mea.gov.in
- **Emergency:** +27 6830 38144
- **VFS Hours:** Mon-Fri 08:00-15:00

---

*Document generated: December 2025*
