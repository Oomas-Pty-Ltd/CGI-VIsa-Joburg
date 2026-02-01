# Seva Setu Bot - Product Requirements Document

## Project Overview
**Name:** Seva Setu Bot  
**Type:** Multi-tenant consular automation platform for CGI Johannesburg  
**Target Users:** Indian and South African citizens  
**Reference Sites:** 
- https://www.cgijoburg.gov.in
- https://vfs.matchlessmfs.com/
**Compliance:** GDPR, DPDA, POPIA

---

## What's Completed ✅

### Core Features
| Feature | Status | Details |
|---------|--------|---------|
| Landing Page | ✅ | Professional UI, navigation |
| Consular Bot Chat | ✅ | AI-powered (GPT-5.2), typing indicator |
| **50+ Languages** | ✅ | 22 Indian + 11 South African + 22 International |
| Language Selector Dropdown | ✅ | Full language selector in UI |
| Feedback Mechanism (👍👎) | ✅ | Under each bot response |
| Mic Recording | ✅ | Language-aware speech recognition |
| Text-to-Speech | ✅ | ElevenLabs integration |
| Avatar Display | ✅ | Placeholder (Akool.com pending) |
| File Upload | ✅ | JPG, PNG, PDF validation |
| Camera Dialog | ✅ | Webcam capture UI |
| Document OCR | ✅ | AI extraction with translation |

### Profile & Family
| Feature | Status | Details |
|---------|--------|---------|
| **User Profile Creation** | ✅ | Unique ID: [NAME]-[DOB]-[HASH] |
| **Extended Profile Fields** | ✅ | 17+ fields including parents, spouse, addresses |
| **Family Linking** | ✅ | Spouse, child, parent, sibling with consent |
| Profile Badge | ✅ | Shows at bottom left |

### Document Management
| Feature | Status | Details |
|---------|--------|---------|
| **Document Upload** | ✅ | Store documents with metadata |
| **Document Unique ID** | ✅ | [ProfileID]-[DocType]-[Date]-[Hash] |
| **Validity Tracking** | ✅ | Original vs Copy rules |
| **90-Day Copy Rule** | ✅ | Copies expire after 90 days |
| **Permanent Documents** | ✅ | Birth/Death certificates |
| **Marriage Affidavit** | ✅ | Flags need for affidavit |
| **Document Summary** | ✅ | Counts: valid, expired, expiring_soon |

### Admin
| Feature | Status | Details |
|---------|--------|---------|
| Super Admin Login | ✅ | JWT authentication |
| Super Admin Dashboard | ✅ | Analytics display |
| Company Management | ✅ | Create/manage companies |
| Local Admin Portal | ✅ | Basic routes |
| Knowledge Scraper | ✅ | Real-time from CGI/VFS |

---

## Document Validity Rules

| Document Type | Original Validity | Copy Validity |
|---------------|-------------------|---------------|
| Passport | Until expiry date | 90 days |
| Birth Certificate | Permanent | 90 days |
| Death Certificate | Permanent | 90 days |
| Marriage Certificate | Permanent (may need affidavit) | 90 days |
| Driving License | Until expiry date | 90 days |
| National ID / Aadhar | Permanent | 90 days |
| PAN Card | Permanent | 90 days |
| Photograph | 6 months max | 90 days |
| Police Report | 90 days | 90 days |
| Affidavit | 90 days | 90 days |

---

## Services Available

| Service | Fee (ZAR) | Processing | Docs Required |
|---------|-----------|------------|---------------|
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

---

## What's Remaining ❌

### P1 - High Priority
| Feature | Status | Notes |
|---------|--------|-------|
| Service Selection UI | ❌ | Service picker in chat |
| Pre-fill Form from Profile | ❌ | Auto-populate with saved data |
| Admin Escalation - Email | ❌ | Awaiting Gmail credentials |
| Admin Escalation - SMS | ❌ | Awaiting Twilio credentials |
| Admin Escalation - Slack | ❌ | Awaiting webhook URL |

### P2 - Medium Priority
| Feature | Status | Notes |
|---------|--------|-------|
| OTP Verification | ❌ | For new user registration |
| Realistic Avatar (Akool) | ❌ | Awaiting API key |
| PDF Form Generation | ❌ | Post-completion |
| Email Delivery | ❌ | Send to user/admin |
| Google Sheets Logging | ❌ | Analytics export |

### P3 - Backlog
| Feature | Status | Notes |
|---------|--------|-------|
| Facebook/Instagram Bot | ❌ | Meta integration |
| Offline Mode | ❌ | Service worker |

---

## API Endpoints

### Profile APIs
```
POST   /api/consular/create-profile     - Create profile
GET    /api/consular/profile/{id}       - Get profile
PUT    /api/consular/profile/{id}       - Update profile
POST   /api/consular/profile/{id}/family - Add family member
GET    /api/consular/profile/{id}/family - Get family members
POST   /api/consular/profile/{id}/document - Add document
GET    /api/consular/profile/{id}/documents - Get documents with validity
```

### Chat APIs
```
POST   /api/consular/chat               - Send chat message
POST   /api/consular/feedback           - Submit feedback
GET    /api/consular/session/{id}       - Get session
```

### Admin APIs
```
POST   /api/auth/super-admin/login      - Admin login
GET    /api/super-admin/analytics       - Dashboard data
POST   /api/super-admin/companies       - Create company
```

---

## Test Credentials
- **Super Admin:** superadmin@sarthak.ai / Admin@2025
- **Test Profile:** AMIT-19850315-TEST
- **Preview:** https://seva-setu-1.preview.emergentagent.com

---

## Testing Status
- **Latest Report:** /app/test_reports/iteration_7.json
- **Backend:** 100% pass (20/20 tests)
- **Frontend:** 100% pass
- **Use Cases:** 8 documented
- **Test Cases:** 36 documented

---

## GitHub Repository Structure
```
/app/
├── backend/
│   ├── consular_routes.py        # Main API endpoints
│   ├── server.py                 # FastAPI server
│   └── tests/
│       ├── test_seva_setu_api.py
│       ├── test_profile_api.py
│       └── test_enhanced_features.py
├── frontend/src/pages/
│   ├── ConsularBot.jsx           # 50+ languages, services
│   ├── Landing.jsx
│   └── SuperAdminDashboard.jsx
├── memory/
│   └── PRD.md                    # This document
├── test_reports/
│   └── iteration_1-7.json
├── USE_CASES_AND_TEST_CASES.md   # Full test documentation
├── EXTERNAL_TESTING_DOCUMENT.md
└── DOCUMENTATION.md
```

---

*Last Updated: December 2025*
*Languages: 55 (50+ requirement met)*
*Test Pass Rate: 100%*
