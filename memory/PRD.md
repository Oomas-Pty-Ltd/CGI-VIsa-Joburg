# Seva Setu Bot - Product Requirements Document

## Project Overview
**Name:** Seva Setu Bot  
**Type:** Multi-tenant consular automation platform for CGI Johannesburg  
**Target Users:** Indian and South African citizens  
**Reference:** https://www.cgijoburg.gov.in  
**Compliance:** GDPR, DPDA, POPIA

---

## What's Completed ✅

| Feature | Status | Details |
|---------|--------|---------|
| Landing Page | ✅ | Professional UI, navigation |
| Consular Bot Chat | ✅ | AI-powered (GPT-5.2), typing indicator |
| Multi-language (Backend) | ✅ | Hindi, Tamil, English auto-detect |
| **Language Selector Dropdown** | ✅ | **NEW** - 5 languages: English, Hindi, Tamil, Zulu, Afrikaans |
| **Feedback Mechanism (👍👎)** | ✅ | **NEW** - Under each bot response with toast notifications |
| **Mic Recording State** | ✅ | **NEW** - Green (idle) → Red (recording) with toast |
| Text-to-Speech | ✅ | ElevenLabs integration |
| Avatar Display | ✅ | Placeholder image with speaking indicator |
| File Upload | ✅ | JPG, PNG, PDF validation |
| Camera Dialog | ✅ | Webcam capture UI |
| Document OCR | ✅ | AI extraction with translation |
| Super Admin Login | ✅ | JWT authentication |
| Super Admin Dashboard | ✅ | Analytics display |
| Company Management | ✅ | Create/manage companies |
| Local Admin Portal | ✅ | Basic routes |
| Knowledge Scraper | ✅ | Real-time from cgijoburg.gov.in |
| Markdown Rendering | ✅ | Rich formatted responses |
| System Prompt (Updated) | ✅ | Aligned with CGI requirements |

---

## What's Remaining ❌

### P1 - High Priority
| Feature | Status | Notes |
|---------|--------|-------|
| User Profile Creation | ❌ | Name/Email/Mobile/DOB flow with unique ID |
| Document Unique ID | ❌ | [Name][DOB][App][Date][Doc] format |
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

## Test Credentials
- **Super Admin:** superadmin@sarthak.ai / Admin@2025
- **Preview:** https://seva-setu-1.preview.emergentagent.com

---

## Key Files
- Backend: `/app/backend/consular_routes.py`
- Frontend: `/app/frontend/src/pages/ConsularBot.jsx`
- Testing Doc: `/app/EXTERNAL_TESTING_DOCUMENT.md`
- Test Reports: `/app/test_reports/iteration_4.json`

---

## Testing Status
- **Latest Report:** /app/test_reports/iteration_5.json
- **Status:** 100% pass rate on new features

---

*Last Updated: December 2025*
