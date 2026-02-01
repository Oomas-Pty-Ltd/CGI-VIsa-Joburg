# Seva Setu Bot - Product Requirements Document

## Project Overview
**Name:** Seva Setu Bot  
**Type:** Multi-tenant consular automation platform  
**Target Users:** Indian and South African citizens  
**Compliance:** GDPR, DPDA, POPIA compliant

## Original Problem Statement
Build a multi-tenant, offline-capable consular automation platform for Indian and South African citizens. Features include:
- Multi-Tenant Infrastructure (Super Admin + Local Admin)
- Consular Workflow with White/Saffron themed UI
- Progress stepper: Register ➔ Upload ➔ Verify ➔ Sign
- Multi-language support (50+ languages)
- AI-powered document scanning and form auto-population
- Knowledge base from official consular websites
- Text-to-Speech with talking avatar
- Secure PDF generation and email delivery

## Tech Stack
- **Frontend:** React, Tailwind CSS, Shadcn/UI
- **Backend:** FastAPI, Python
- **Database:** MongoDB
- **AI/ML:** OpenAI GPT-5.2 (via Emergent LLM Key), ElevenLabs TTS
- **Authentication:** JWT

## Core Features - Status

### ✅ COMPLETED
| Feature | Status | Notes |
|---------|--------|-------|
| Landing Page | ✅ Complete | Professional UI with feature cards |
| Consular Bot Chat | ✅ Complete | AI-powered with typing indicator |
| Multi-language Support | ✅ Complete | Hindi, Tamil, English auto-detect |
| Progress Stepper | ✅ Complete | Register → Upload → Verify → Sign |
| Avatar Display | ✅ Complete | Placeholder (Akool integration pending) |
| Voice Toggle | ✅ Complete | Enable/disable TTS |
| Text-to-Speech | ✅ Complete | ElevenLabs integration |
| File Upload | ✅ Complete | JPG, PNG, PDF with validation |
| Camera Dialog | ✅ Complete | Webcam capture UI |
| Document Scanning | ✅ Complete | AI-powered OCR with translation |
| Super Admin Login | ✅ Complete | JWT authentication |
| Super Admin Dashboard | ✅ Complete | Analytics & company management |
| Local Admin System | ✅ Complete | Basic routes implemented |
| Knowledge Scraper | ✅ Complete | Real-time from cgijoburg.gov.in |
| Markdown Rendering | ✅ Complete | Rich formatted responses |

### 🔄 IN PROGRESS
| Feature | Status | Notes |
|---------|--------|-------|
| Professional Conversational Flow | 🔄 Pending | User verification, admin escalation, feedback |

### 📋 UPCOMING (P1)
| Feature | Priority | Notes |
|---------|----------|-------|
| Mic Voice Input | P1 | Web Speech API implementation |
| Language Selector Dropdown | P1 | Manual language switch |
| Admin Escalation Alerts | P1 | Slack, Twilio (awaiting credentials) |

### 🗓️ FUTURE/BACKLOG
| Feature | Priority | Notes |
|---------|----------|-------|
| Akool.com Avatar | P2 | Realistic talking avatar (user to provide API key) |
| Facebook/Instagram Integration | P2 | Meta Business Suite |
| KVM 8 Deployment Package | P2 | Production deployment |
| Feedback Analysis Dashboard | P3 | Scheduled analytics |

## API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/` | GET | Health check |
| `/api/auth/super-admin/login` | POST | Super admin authentication |
| `/api/auth/local-admin/login` | POST | Local admin authentication |
| `/api/consular/chat` | POST | Main chat endpoint |
| `/api/consular/document-scan` | POST | Document OCR |
| `/api/consular/session/{id}` | GET | Get session data |
| `/api/super-admin/analytics` | GET | Dashboard analytics |
| `/api/super-admin/companies` | POST | Create company |

## Database Schema
- **super_admins:** {id, email, password, created_at}
- **local_admins:** {id, email, password, company_id, created_at}
- **companies:** {id, name, llm_model, created_by, created_at}
- **chat_sessions:** {id, user_id, messages[], step, created_at}
- **knowledge_cache:** {url, content, last_scraped}

## Test Credentials
- **Super Admin:**
  - Email: `superadmin@sarthak.ai`
  - Password: `Admin@2025`

## Key Files
- `/app/backend/server.py` - Main FastAPI application
- `/app/backend/consular_routes.py` - Chat & document processing
- `/app/backend/knowledge_scraper.py` - Web scraping
- `/app/frontend/src/pages/ConsularBot.jsx` - Main chat UI
- `/app/frontend/src/pages/SuperAdminDashboard.jsx` - Admin panel

## Testing
- Backend tests: `/app/backend/tests/test_seva_setu_api.py`
- Test reports: `/app/test_reports/iteration_*.json`
- Latest: iteration_4.json - 100% pass rate

## Notes
- Avatar video is currently a placeholder image
- Twilio/Slack integrations ready but awaiting user credentials
- App uses Emergent LLM Key for AI services

---
*Last Updated: December 2025*
