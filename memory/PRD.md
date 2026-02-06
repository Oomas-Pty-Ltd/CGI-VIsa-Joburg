# Seva Setu Bot - Product Requirements Document

## Latest Updates (Feb 6, 2026)
### Deployment Fixes Applied:
1. Removed `.env` blocking entries from `.gitignore` (lines 84-97)
2. Added root-level `/health` endpoint for Kubernetes health checks
3. Optimized 4 database queries with field projections
4. Replaced inefficient message counting with MongoDB aggregation pipeline

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

---

## Test Status (February 2026)
- **Total Tests:** 33
- **Passed:** 33
- **Failed:** 0
- **Coverage:** Web, Widget, WhatsApp, Facebook, Templates, Monitoring, Auth

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
| Landing | https://consular-bot-1.preview.emergentagent.com |
| Full Bot | https://consular-bot-1.preview.emergentagent.com/consular |
| Widget Demo | https://consular-bot-1.preview.emergentagent.com/widget-demo |
| Super Admin | https://consular-bot-1.preview.emergentagent.com/super-admin/login |

---

## Widget Embed Code

```html
<script src="https://consular-bot-1.preview.emergentagent.com/embed.js"></script>
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
