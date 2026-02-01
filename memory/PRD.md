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

### Interactive Form Filling (NEW!)
| Feature | Status | Details |
|---------|--------|---------|
| **Consent-First Flow** | ✅ | Asks YES before processing documents |
| **Step-by-Step Confirmation** | ✅ | One field at a time |
| **YES/NO Commands** | ✅ | Confirm or edit current field |
| **STOP/CONTINUE** | ✅ | Pause and resume anytime |
| **Progress Tracking** | ✅ | Step X/Y with progress bar |
| **Review Mode** | ✅ | Shows all fields before submit |
| **EDIT [number]** | ✅ | Edit specific field in review |
| **SUBMIT** | ✅ | Generates Application ID |
| **Service Selector UI** | ✅ | Shows services with fees |
| **Form Templates** | ✅ | 5 templates (passport, visa, OCI, PCC, birth) |

### Admin
| Feature | Status | Details |
|---------|--------|---------|
| Super Admin Login | ✅ | JWT authentication |
| Super Admin Dashboard | ✅ | Analytics display |
| Company Management | ✅ | Create/manage companies |
| Local Admin Portal | ✅ | Basic routes |
| Knowledge Scraper | ✅ | Real-time from CGI/VFS |

---

## Form Templates Available

| Template | Steps | Description |
|----------|-------|-------------|
| passport_renewal | 12 | Passport Renewal Application |
| tourist_visa | 15 | Tourist Visa Application |
| oci_application | 18 | OCI Card Application |
| birth_registration | 14 | Child Birth Registration |
| pcc_application | 10 | Police Clearance Certificate |

---

## Interactive Commands

| Command | Aliases | Action |
|---------|---------|--------|
| YES | correct, confirm | Confirm current field, proceed |
| NO | edit, change | Edit current field |
| STOP | pause, wait | Pause application, save progress |
| CONTINUE | resume, proceed | Resume from paused state |
| SKIP | - | Skip optional field |
| SUBMIT | - | Submit application (in review) |
| EDIT [n] | - | Edit field number n (in review) |

---

## What's Remaining ❌

### P1 - High Priority
| Feature | Status | Notes |
|---------|--------|-------|
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

### Form Filling APIs (NEW)
```
POST   /api/consular/form-filling       - Interactive form filling
GET    /api/consular/form-session/{id}  - Get form session status
GET    /api/consular/applications/{id}  - Get applications for profile
```

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

---

## Test Credentials
- **Super Admin:** superadmin@sarthak.ai / Admin@2025
- **Test Profile:** AMIT-19850315-TEST
- **Preview:** https://seva-setu-1.preview.emergentagent.com

---

## Testing Status
- **Latest Report:** /app/test_reports/iteration_8.json
- **Backend:** 91% pass (CONTINUE bug fixed)
- **Frontend:** 100% pass
- **Use Cases:** 8 documented
- **Test Cases:** 36+ documented

---

*Last Updated: December 2025*
*Languages: 55 (50+ requirement met)*
*Form Templates: 5*
