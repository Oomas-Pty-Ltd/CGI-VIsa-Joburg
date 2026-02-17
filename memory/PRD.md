# Seva Setu Bot - Product Requirements Document

## Latest Updates (Feb 17, 2026)

### ✅ UI/UX Accessibility Enhancement Complete (WCAG 2.1 AA):

#### Accessibility Features Implemented:
- ✅ **Skip Links** - Keyboard navigation to main content
- ✅ **ARIA Labels** - All interactive elements labeled for screen readers
- ✅ **Focus Indicators** - 3px orange outline with 2px offset (visible on all browsers)
- ✅ **Reduced Motion Support** - Animations disabled when user prefers-reduced-motion
- ✅ **High Contrast Mode** - Enhanced borders and backgrounds for visibility
- ✅ **44px Touch Targets** - All buttons meet WCAG minimum touch size
- ✅ **Live Regions** - Screen reader announcements for dynamic content
- ✅ **Color Contrast** - All text meets WCAG AA 4.5:1 ratio
- ✅ **Form Accessibility** - Labels, hints, and error associations
- ✅ **Semantic HTML** - Proper roles (log, region, toolbar, dialog)

#### New Files Created:
- `/app/frontend/src/styles/accessibility.css` - Comprehensive accessibility styles
- `/app/frontend/src/components/Accessibility.jsx` - Reusable accessible components

#### Components Updated:
- `ConsularBot.jsx` - Full ARIA implementation
- `App.css` - Accessibility utilities added
- `index.css` - Imports accessibility styles

#### Accessibility Audit Checklist (WCAG 2.1 AA):
| Criterion | Status | Notes |
|-----------|--------|-------|
| 1.1.1 Non-text Content | ✅ | All images have alt text |
| 1.3.1 Info and Relationships | ✅ | Semantic HTML, ARIA roles |
| 1.4.3 Contrast Minimum | ✅ | 4.5:1 for text, verified colors |
| 1.4.4 Resize Text | ✅ | REM units, respects browser settings |
| 2.1.1 Keyboard | ✅ | All functions keyboard accessible |
| 2.4.1 Bypass Blocks | ✅ | Skip link implemented |
| 2.4.4 Link Purpose | ✅ | Clear aria-labels on all links |
| 2.4.7 Focus Visible | ✅ | 3px orange outline |
| 2.5.5 Target Size | ✅ | 44x44px minimum |
| 3.2.1 On Focus | ✅ | No unexpected changes |
| 3.3.2 Labels | ✅ | All inputs have labels |
| 4.1.2 Name, Role, Value | ✅ | ARIA attributes on all widgets |

---

### ✅ Major Security & Functional Enhancement Complete:

#### 1. FUNCTIONAL ENHANCEMENTS:
- ✅ File upload validation (MIME type + <10MB size check)
- ✅ Document expiry logic with 3-month recheck schedule
- ✅ Document encryption at rest (AES-256 via Fernet)
- ✅ Notification service for status changes
- ✅ Feedback storage with session ID in MongoDB
- ✅ Knowledge base text search indexes
- ✅ MongoDB indexes for all searchable fields

#### 2. SECURITY HARDENING:
- ✅ HSTS header (Strict-Transport-Security)
- ✅ X-Content-Type-Options, X-Frame-Options, X-XSS-Protection headers
- ✅ Comprehensive audit trail (user, action, timestamp, IP)
- ✅ GDPR/POPIA/DPDA compliance endpoints (export/delete)
- ✅ PII masking in audit logs
- ✅ MongoDB connection pooling (50 max, 10 min)

#### 3. WHATSAPP ENHANCEMENTS:
- ✅ Emergency keyword rule engine (multi-language)
- ✅ Session context storage (last 20 messages)
- ✅ Conversation history attached to GPT prompt (last 5)
- ✅ Media message handling preparation

#### 4. VOICE SYSTEM UPGRADES:
- ✅ Extended language support (22 Indian + 11 South African languages)
- ✅ Audio chunking for files >60 seconds
- ✅ Confidence scoring (<0.7 triggers confirmation)
- ✅ Number/currency to spoken format conversion
- ✅ Dynamic TTS voice selection by language
- ✅ Audio normalization before transcription

#### New Service Files Created:
- `/app/backend/services/document_service.py` - Document management & encryption
- `/app/backend/services/notification_service.py` - Multi-channel notifications
- `/app/backend/services/audit_service.py` - Comprehensive audit logging
- `/app/backend/services/feedback_service.py` - Feedback collection & analysis
- `/app/backend/services/compliance_service.py` - GDPR export/delete
- `/app/backend/services/whatsapp_rule_engine.py` - Emergency detection & routing
- `/app/backend/user_routes.py` - User-facing API endpoints

#### New API Endpoints:
- `POST /api/user/feedback` - Submit feedback (no auth)
- `GET /api/user/feedback/stats` - Feedback analytics (admin)
- `GET /api/user/notifications` - User notifications
- `GET/PUT /api/user/profile` - Profile management
- `GET /api/user/data-summary` - GDPR data summary
- `POST /api/user/data-export` - Request data export
- `POST /api/user/data-delete` - Request data deletion
- `GET /api/user/documents` - User's documents

#### Pre-Production Checklist:
- 📄 Created `/app/docs/PRE_PRODUCTION_CHECKLIST.md` with all open items

---

### Previous Updates (Feb 12, 2026)

#### Admin Dashboard & Mic/Camera Integration:
- ✅ Fixed blank Admin Dashboard page (localStorage key mismatch)
- ✅ Corrected logout navigation to `/super-admin/login`
- ✅ All 4 tabs working: Dashboard, Escalations, Knowledge Base, AI Observability
- ✅ Admin panel accessible at `/super-admin/admin-panel`

#### Mic/Camera Backend Integration:
- ✅ Created `/app/backend/speech_service.py` - OpenAI Whisper STT service
- ✅ Updated `/api/consular/voice-input` endpoint to use Whisper transcription
- ✅ Supports multiple languages: English, Hindi, Tamil, Zulu, Afrikaans
- ✅ Frontend sends audio to backend for transcription
- ✅ Fallback to browser Web Speech API if backend fails
- ✅ Document scan endpoint `/api/consular/document-scan` working with GPT-5.2

#### Test Results (Feb 12, 2026):
- **Backend:** 100% (13/13 tests passed)
- **Frontend:** 100% (All UI elements verified)
- All admin endpoints protected with authentication
- Voice-input accepts multipart/form-data (audio file + language)

---

### 🔒 Phase 3 Operational Hardening Implemented:

#### 8. Intent Classification Module
- ✅ Rule-based visa intent classifier with 10+ categories
- ✅ Keyword and regex pattern matching
- ✅ Confidence scoring (>50% = deterministic, <50% = LLM)
- ✅ Reduces LLM costs for common queries
- ✅ Visa type detection (tourist, business, student, medical, e-visa)

#### 9. Escalation Module  
- ✅ Human handoff triggers (user request, emergency, complaint)
- ✅ Priority levels: URGENT, HIGH, MEDIUM, LOW
- ✅ Ticket creation with reference IDs
- ✅ Conversation summary generation
- ✅ Admin notification system
- ✅ Escalation status tracking (open, in_progress, resolved, closed)

#### 10. Knowledge Base Module
- ✅ Structured FAQ collection (7 default entries)
- ✅ Version control for updates
- ✅ Source transparency tagging
- ✅ Category organization (passport, visa, oci, fees, etc.)
- ✅ Admin CRUD interface

#### 11. AI Observability Dashboard
- ✅ Intent classification stats
- ✅ Cost tracking breakdown
- ✅ Rate limiting metrics
- ✅ Escalation summary
- ✅ Knowledge base stats
- ✅ Consolidated admin dashboard endpoint

### New Admin API Endpoints:
- `/api/admin/dashboard` - Admin overview
- `/api/admin/observability` - AI metrics
- `/api/admin/escalations` - Escalation management
- `/api/admin/knowledge` - Knowledge base CRUD

---

### 🔒 Phase 2 Compliance & Cost Control Implemented:

#### 5. Rate Limiting Module
- ✅ IP-based limits: 30/min, 500/hour
- ✅ User-based limits: 20/min, 500/day
- ✅ Phone-based limits: 10/min, 100/day (WhatsApp/SMS)
- ✅ Global limit: 1000 requests/min
- ✅ Burst allowance for short spikes
- ✅ Automatic cleanup of stale rate limit buckets
- ✅ Stats endpoint: `/api/monitoring/rate-limits`

#### 6. Cost Monitoring Module
- ✅ Per-session token tracking
- ✅ Daily budget: $50 (configurable)
- ✅ Monthly budget: $1000 (configurable)
- ✅ Per-session limit: $1 (configurable)
- ✅ Alert thresholds: 70% warning, 90% critical
- ✅ Token cost calculation: $0.01/1K input, $0.03/1K output
- ✅ Stats endpoint: `/api/monitoring/costs`

#### 7. WhatsApp 24-Hour Policy Manager
- ✅ Conversation window tracking (24h from last user message)
- ✅ Auto-detection of window expiry
- ✅ Template message switching when window closes
- ✅ Expiry reminder support
- ✅ Batch status checking for campaigns

---

### 🔒 Phase 1 Critical Security Fixes Implemented:

#### 1. Channel Module - Webhook Security
- ✅ Twilio signature validation (`X-Twilio-Signature` header)
- ✅ Facebook signature validation (`X-Hub-Signature-256` header)
- ✅ Webhook attempt logging for security audit
- ✅ HTTPS enforcement via signature validation

#### 2. Session & Authentication Module
- ✅ Unique session IDs per channel: `{channel}_{user_hash}_{uuid}_{timestamp}`
- ✅ Session TTL (24 hours default, configurable)
- ✅ Channel isolation (web, whatsapp, facebook, widget sessions are separate)
- ✅ Automatic session cleanup (old/expired sessions)
- ✅ Max sessions per user limit (10 default)

#### 3. LLM Module - Prompt Injection Protection
- ✅ Server-side hardened system prompts (immutable identity)
- ✅ Input sanitizer with 20+ injection pattern detection
- ✅ Blocks: instruction override, role manipulation, system extraction, jailbreak attempts
- ✅ Code injection prevention
- ✅ SQL injection detection

#### 4. Guardrail Module - PII & Output Protection
- ✅ Enhanced PII masking: Email, Phone, SA ID, Aadhaar, PAN, Passport, Credit Card
- ✅ Unsafe output detection (guarantees, legal/medical/financial advice)
- ✅ Auto-disclaimers for risky content
- ✅ Sanitized logging (PII redacted in logs)
- ✅ Security metrics endpoint: `/api/monitoring/security`

### Security Testing Results (31/31 tests passed):
- Prompt injection protection: ✅
- PII masking in input/output: ✅
- Session isolation: ✅
- Webhook endpoints: ✅
- Security metrics: ✅

---

## Previous Updates (Feb 6, 2026)
### Deployment Fixes Applied:
1. Removed `.env` blocking entries from `.gitignore` (lines 84-97)
2. Added root-level `/health` endpoint for Kubernetes health checks
3. Optimized 4 database queries with field projections
4. Replaced inefficient message counting with MongoDB aggregation pipeline
5. Fixed Atlas MongoDB compatibility - changed `client.admin.command('ping')` to `db.command('ping')`
6. Implemented lazy loading for Presidio/Spacy to avoid heavy startup
7. Added comprehensive error handling to lifespan startup function

## Overview
Multi-tenant consular automation platform for Indian and South African citizens. GDPR, DPDA, and POPIA compliant.

---

## Core Features Implemented ✅

### 1. Multi-Channel Chat
- **Web Chat (Full):** `/consular` - Full interface with avatar, progress stepper, voice
- **Widget (Embeddable):** `/widget-demo` - Lightweight chat bubble for websites
- **WhatsApp:** `/api/whatsapp/webhook` - Twilio integration (mock mode ready)
- **Facebook Messenger:** `/api/facebook/webhook` - Meta integration (mock mode ready)

### 2. AI-Powered Responses (GPT-5.2)
- Concise, specific answers (widget: 2-4 sentences)
- Multi-language support (Hindi, English, Zulu, Afrikaans)
- Context-aware conversation memory
- RAG system with government website scraping

### 3. Template Management System
- **Email Templates:** Welcome, status updates, appointment reminders
- **WhatsApp Templates:** Welcome, reminders
- **Alert Templates:** System alerts, fraud warnings
- **Custom Templates:** User-created with variable substitution
- **Languages:** English, Hindi

### 4. Monitoring & Alerting
- Health check endpoint
- CPU/Memory/Disk monitoring
- Alert thresholds (90% load)
- Email/Webhook notifications

### 5. Multi-Tenancy
- Super Admin Dashboard
- Local Admin Dashboard
- Company management

---

## Architecture

```
Frontend (React)     Backend (FastAPI)      External Services
     │                    │                      │
     ├── Web Chat ────────┤                      │
     ├── Widget ──────────┼──── GPT-5.2 ─────────┤
     │                    ├──── MongoDB ─────────┤
     │                    ├──── Twilio ──────────┤ WhatsApp
     │                    ├──── Facebook ────────┤ Messenger
     │                    └──── SMTP ────────────┤ Alerts
```

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/consular/chat` | POST | Full chat (verbose) |
| `/api/consular/chat-widget` | POST | Widget chat (concise) |
| `/api/whatsapp/webhook` | POST | WhatsApp messages |
| `/api/whatsapp/send` | POST | Send WhatsApp |
| `/api/facebook/webhook` | GET/POST | Facebook messages |
| `/api/facebook/send` | POST | Send Facebook |
| `/api/templates/` | GET/POST | Template CRUD |
| `/api/templates/render` | POST | Render with variables |
| `/api/monitoring/health` | GET | Health check |
| `/api/monitoring/metrics` | GET | Performance metrics |
| `/api/monitoring/security` | GET | **NEW** Security metrics & guardrail stats |

---

## Security Module Files

| File | Purpose |
|------|---------|
| `/app/backend/security/webhook_validator.py` | Twilio/Facebook signature validation |
| `/app/backend/security/session_manager.py` | Secure session management with TTL |
| `/app/backend/security/input_sanitizer.py` | Prompt injection protection |
| `/app/backend/security/guardrail.py` | PII masking & output validation |

---

## Test Status (February 2026)
- **Phase 1 Security Tests:** 31 passed, 0 failed
- **Phase 2 Security Tests:** All endpoints working ✅
- **Phase 3 Admin Tests:** All endpoints working ✅
- **Previous Tests:** 33 passed, 0 failed
- **Total Coverage:** Web, Widget, WhatsApp, Facebook, Templates, Monitoring, Auth, Security, Rate Limiting, Cost Monitoring, Intent Classification, Escalations, Knowledge Base

---

## Documentation Downloads
- **Technical Docs:** https://consulai.preview.emergentagent.com/TECHNICAL_DOCS.md
- **Database Export:** https://consulai.preview.emergentagent.com/db_export.zip

---

## Pending Tasks (Priority Order)

### P2 - In Progress
- [ ] Connect Mic/Camera buttons to auto-send transcribed text (currently fills input field)
- [ ] Real-time document scan preview with extracted fields

### P3 - Feature Work
- [ ] User profile system
- [ ] Talking avatar feature
- [ ] Instagram integration

### P4 - Deployment & Documentation
- [ ] Docker packaging for KVM deployment
- [ ] Restrict CORS from `*` to specific frontend domain

---

## Recently Completed ✅
- [x] Admin Dashboard UI (Feb 12, 2026)
- [x] Mic/Camera backend integration (Feb 12, 2026)
- [x] Speech-to-text using OpenAI Whisper (Feb 12, 2026)
- [x] Language selector UI dropdown (Feb 12, 2026)
- [x] Phase 1-3 Security Hardening (Feb 6-12, 2026)

---

## Credentials

### Super Admin
- **URL:** `/super-admin/login`
- **Email:** `superadmin@sarthak.ai`
- **Password:** `Admin@2025`

### Integration Placeholders (Configure in .env)
- `TWILIO_ACCOUNT_SID` - Twilio Account
- `TWILIO_AUTH_TOKEN` - Twilio Auth
- `FB_PAGE_ACCESS_TOKEN` - Facebook Page Token

---

## URLs

| Page | URL |
|------|-----|
| Landing | https://consulai.preview.emergentagent.com |
| Full Bot | https://consulai.preview.emergentagent.com/consular |
| Widget Demo | https://consulai.preview.emergentagent.com/widget-demo |
| Super Admin Login | https://consulai.preview.emergentagent.com/super-admin/login |
| Super Admin Dashboard | https://consulai.preview.emergentagent.com/super-admin/dashboard |
| Admin Panel (NEW) | https://consulai.preview.emergentagent.com/super-admin/admin-panel |

---

## Widget Embed Code

```html
<script src="https://consulai.preview.emergentagent.com/embed.js"></script>
<script>
  SevaSetu.init({
    position: 'bottom-right',
    primaryColor: '#E06F2C'
  });
</script>
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `/app/backend/.env` | Backend config & API keys |
| `/app/frontend/src/config/botMessages.js` | Bot greeting & advisory messages |
| `/app/backend/template_routes.py` | Default templates |

---

## Documentation

- `/app/DOCUMENTATION.md` - Complete API & integration docs
- `/app/TEST_CASES.md` - Test cases & results
- `/app/ARCHITECTURE_GUIDE.md` - Production deployment guide
