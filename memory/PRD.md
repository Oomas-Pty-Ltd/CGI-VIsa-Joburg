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
| **Realistic Namaste Avatar** | ✅ | AI-generated Indian woman with animated effects |
| File Upload | ✅ | JPG, PNG, PDF validation |
| Camera Dialog | ✅ | Webcam capture UI |
| Document OCR | ✅ | AI extraction with translation |

### 🆕 Structured Conversation Flow (Feb 2026)
| Feature | Status | Details |
|---------|--------|---------|
| **Consent-First Flow** | ✅ | Asks YES/NO before proceeding |
| **One Question Per Turn** | ✅ | Single question at a time |
| **Service Prioritization** | ✅ | Top 5 services → Others option |
| **Progress Indicator** | ✅ | Step X/5 with percentage bar |
| **Personalized Responses** | ✅ | Uses user's name throughout |
| **Session History** | ✅ | Tracks "Last time you did X" |
| **STOP/CONTINUE/HELP** | ✅ | Universal commands supported |

### 🆕 Admin Configuration System (Feb 2026)
| Feature | Status | Details |
|---------|--------|---------|
| **Service Links Config** | ✅ | Admin can edit VFS URLs |
| **Warnings Config** | ✅ | Configurable warning messages |
| **Bot Behavior Config** | ✅ | Enable/disable features |
| **Document Requirements** | ✅ | Per-service document checklist |
| **View All Conversations** | ✅ | Admin can see visitor chats |
| **Exception Logging** | ✅ | Error tracking dashboard |
| **Application Tracking** | ✅ | Full lifecycle management |
| **Document Access** | ✅ | Admin can view submitted docs |

### 🆕 Compliance (Feb 2026)
| Feature | Status | Details |
|---------|--------|---------|
| **Cookie Consent Banner** | ✅ | Accept All / Decline / Customize |
| **GDPR Compliance** | ✅ | Full consent flow |
| **POPIA Compliance** | ✅ | South Africa data protection |
| **DPDA Compliance** | ✅ | Indian data protection |
| **Compliance Badges** | ✅ | Green indicators in banner |

### 🆕 Application Tracking System (Feb 2026)
| Feature | Status | Details |
|---------|--------|---------|
| **Application Creation** | ✅ | Unique APP-[SERVICE]-[DATE]-[ID] |
| **Status Tracking** | ✅ | 10 status states |
| **Status History** | ✅ | Full audit trail |
| **Appointment Linking** | ✅ | Book and track appointments |
| **Admin Notes** | ✅ | Add notes to applications |
| **Statistics Dashboard** | ✅ | Analytics by status/service |

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

### Interactive Form Filling
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

### Form Templates (Official CGI Johannesburg Forms)
| Template | Steps | Description | Fee |
|----------|-------|-------------|-----|
| **misc_services** | 20 | General Miscellaneous Services | R 225-495 |
| **birth_certificate** | 22 | Birth Certificate Application | R 405 |
| **marriage_certificate** | 24 | Marriage Certificate Application | R 492 |
| **death_certificate** | 18 | Death Certificate Application | R 405 |
| **attestation** | 16 | Document Attestation | R 225-417/page |
| **life_certificate** | 14 | Life Certificate (Pensioners) | R 225 |
| **passport_renewal** | 12 | Passport Renewal | R 1,395 |
| **tourist_visa** | 15 | Tourist Visa Application | R 510 |
| **oci_application** | 18 | OCI Card Application | R 5,015 |
| **pcc_application** | 10 | Police Clearance Certificate | R 495 |

### Admin
| Feature | Status | Details |
|---------|--------|---------|
| Super Admin Login | ✅ | JWT authentication |
| Super Admin Dashboard | ✅ | Analytics display |
| Company Management | ✅ | Create/manage companies |
| Local Admin Portal | ✅ | Basic routes |
| Knowledge Scraper | ✅ | Real-time from CGI/VFS |

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

## Bug Fixes (Feb 2026)

### Bug #1: Interactive Form-Filling Error ✅ FIXED
- **Issue:** "Sorry, there was an error. Please try again or type STOP to pause."
- **Root Cause:** Session ID was null when form-filling started (before any chat message)
- **Fix:** Initialize session ID on component mount (ConsularBot.jsx line 167)

### Bug #2: Document Upload Failed ✅ FIXED
- **Issue:** "document upload failed" message
- **Root Cause:** Frontend only called `/document-scan` but never saved to profile
- **Fix:** Now calls both `/document-scan` AND `/profile/{id}/document` endpoints (ConsularBot.jsx lines 560-593)

---

## Test Credentials
- **Super Admin:** superadmin@sarthak.ai / Admin@2025
- **Test Profile:** AMIT-19850315-TEST
- **Preview:** https://seva-bridge-1.preview.emergentagent.com

---

## Testing Status
- **Latest Report:** /app/test_reports/iteration_9.json
- **Form Templates:** 10 templates tested
- **Backend:** 100% pass
- **Frontend:** 100% pass
- **Bug Fixes Verified:** Both bugs fixed and tested

---

*Last Updated: February 2026*
*Languages: 55 (50+ requirement met)*
*Form Templates: 10 (based on official CGI form)*
