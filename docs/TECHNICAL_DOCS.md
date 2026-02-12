# Seva Setu Bot - Complete Technical Documentation

## Table of Contents
1. [Overview](#overview)
2. [LLM Configuration](#llm-configuration)
3. [Architecture](#architecture)
4. [Security Features](#security-features)
5. [Phase 3 Features](#phase-3-features)
6. [API Reference](#api-reference)
7. [Database Schema](#database-schema)
8. [Configuration](#configuration)
9. [Deployment](#deployment)

---

## Overview

**Seva Setu Bot** is a multi-tenant consular automation platform designed for Indian and South African citizens. It provides AI-powered assistance for consular services through multiple channels.

### Key Features
- Multi-channel support (Web, WhatsApp, Facebook Messenger)
- AI-powered responses using GPT-5.2
- Multi-language support (Hindi, English, Zulu, Afrikaans, Tamil)
- Real-time document scanning and form auto-fill
- Enterprise-grade security and compliance (GDPR, DPDA, POPIA)
- Rule-based intent classification (reduces LLM costs)
- Human escalation system
- Versioned knowledge base

---

## LLM Configuration

### Current Setup

| Component | Value |
|-----------|-------|
| **Provider** | OpenAI (via Emergent Integration) |
| **Model** | `gpt-5.2` |
| **API Key Type** | Emergent Universal Key |
| **Library** | `emergentintegrations` |

### Model Details

```python
# Configuration in consular_routes.py
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

chat_instance = LlmChat(
    api_key=os.environ.get('EMERGENT_LLM_KEY'),
    session_id=session_id,
    system_message=system_message
).with_model("openai", "gpt-5.2")
```

### Capabilities
- **Text Generation**: Multi-language conversational AI
- **Vision**: Document scanning and image analysis (via ImageContent)
- **Text-to-Speech**: Voice response generation (via OpenAITextToSpeech)

### Token Pricing (Configured)
| Type | Cost per 1K tokens |
|------|-------------------|
| Input | $0.01 |
| Output | $0.03 |

### Budget Limits (Default)
| Limit | Value |
|-------|-------|
| Daily Budget | $50.00 |
| Monthly Budget | $1,000.00 |
| Per Session | $1.00 |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
├─────────────────────────────────────────────────────────────────┤
│  Landing Page │ Consular Bot │ Widget │ Admin Dashboards        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Security   │  │   Routes     │  │   Services   │          │
│  │   Module     │  │              │  │              │          │
│  ├──────────────┤  ├──────────────┤  ├──────────────┤          │
│  │ • Webhook    │  │ • /consular  │  │ • LLM Chat   │          │
│  │   Validator  │  │ • /whatsapp  │  │ • Voice TTS  │          │
│  │ • Session    │  │ • /facebook  │  │ • Knowledge  │          │
│  │   Manager    │  │ • /auth      │  │   Scraper    │          │
│  │ • Input      │  │ • /templates │  │ • Presidio   │          │
│  │   Sanitizer  │  │ • /monitoring│  │   PII       │          │
│  │ • Guardrails │  │ • /admin     │  │ • File      │          │
│  │ • Rate       │  │              │  │   Security  │          │
│  │   Limiter    │  │              │  │              │          │
│  │ • Cost       │  │              │  │              │          │
│  │   Monitor    │  │              │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   MongoDB    │   │   OpenAI     │   │   External   │
│              │   │   (GPT-5.2)  │   │   Services   │
│ • Sessions   │   │              │   │              │
│ • Users      │   │ • Chat       │   │ • Twilio     │
│ • Companies  │   │ • Vision     │   │ • Facebook   │
│ • Templates  │   │ • TTS        │   │ • SMTP       │
│ • Messages   │   │              │   │              │
└──────────────┘   └──────────────┘   └──────────────┘
```

---

## Security Features

### Phase 1: Critical Security (Implemented ✅)

#### 1. Webhook Signature Validation
- **Twilio**: HMAC-SHA1 signature via `X-Twilio-Signature`
- **Facebook**: HMAC-SHA256 signature via `X-Hub-Signature-256`
- Location: `/app/backend/security/webhook_validator.py`

#### 2. Session Isolation
- Unique session IDs: `{channel}_{user_hash}_{uuid}_{timestamp}`
- 24-hour TTL with automatic cleanup
- Channel isolation (web, whatsapp, facebook, widget)
- Location: `/app/backend/security/session_manager.py`

#### 3. Prompt Injection Protection
- 20+ injection pattern detection
- Blocks: jailbreak, DAN mode, system extraction, role manipulation
- Server-side hardened system prompts
- Location: `/app/backend/security/input_sanitizer.py`

#### 4. PII Protection (Guardrails)
- Masks: Email, Phone, Passport, Aadhaar, PAN, Credit Card, SA ID
- Unsafe output detection and auto-disclaimers
- Sanitized logging
- Location: `/app/backend/security/guardrail.py`

### Phase 2: Compliance & Cost Control (Implemented ✅)

#### 5. Rate Limiting
- IP-based: 30/min, 500/hour
- User-based: 20/min, 500/day
- Phone-based: 10/min, 100/day
- Global: 1000/min
- Location: `/app/backend/security/rate_limiter.py`

#### 6. Cost Monitoring
- Per-session token tracking
- Daily/monthly budget limits
- Alert thresholds (70% warning, 90% critical)
- Location: `/app/backend/security/cost_monitor.py`

#### 7. WhatsApp 24-Hour Policy
- Conversation window tracking
- Auto-template switching when window expires
- Expiry reminders
- Location: `/app/backend/security/whatsapp_policy.py`

---

## Phase 3 Features

### Intent Classification (Rule-Based)

Reduces LLM calls by handling common queries deterministically.

**Location:** `/app/backend/services/intent_classifier.py`

**Categories:**
- PASSPORT, VISA, OCI, PIO, CONSULAR
- APPOINTMENT, FEES, DOCUMENTS, STATUS
- EMERGENCY, OFFICE_INFO, ESCALATION, GREETING

**How it works:**
1. User query is analyzed using keywords and regex patterns
2. If confidence > 50%, deterministic response is returned (no LLM cost)
3. If confidence < 50%, query falls through to GPT-5.2

**Stats Endpoint:** `GET /api/admin/observability`

### Human Escalation System

**Location:** `/app/backend/services/escalation_service.py`

**Triggers:**
- User requests: "speak to human", "talk to agent"
- Complaints: "frustrated", "not working", "complaint"
- Emergencies: "help", "arrested", "emergency"

**Priority Levels:**
- URGENT: Emergency situations
- HIGH: Complaints, legal matters
- MEDIUM: User requests
- LOW: Complex queries

**Admin Endpoints:**
- `GET /api/admin/escalations` - List all escalations
- `PUT /api/admin/escalations/{id}` - Update status
- `GET /api/admin/escalations/stats` - Statistics

### Knowledge Base (Versioned)

**Location:** `/app/backend/services/knowledge_service.py`

**Features:**
- Structured FAQ collection
- Version history for each entry
- Source transparency (verified vs unverified)
- Category-based organization

**Categories:** passport, visa, oci, consular, fees, emergency, office, general

**Admin Endpoints:**
- `GET /api/admin/knowledge` - List entries
- `POST /api/admin/knowledge` - Create entry
- `PUT /api/admin/knowledge/{id}` - Update (creates new version)
- `GET /api/admin/knowledge/{id}/history` - Version history

### AI Observability Dashboard

**Endpoint:** `GET /api/admin/observability`

**Metrics:**
- Intent classification stats (rule-based vs LLM)
- Rate limiting stats
- Cost tracking (daily/budget)
- Guardrail detections
- Escalation counts
- Knowledge base stats

---

## API Reference

### Chat Endpoints

#### POST /api/consular/chat
Full-featured chat endpoint with voice support.

```json
Request:
{
  "message": "How do I renew my passport?",
  "session_id": "optional-session-id",
  "company_id": "optional-company-id",
  "user_id": "optional-user-id",
  "image_base64": "optional-base64-image",
  "enable_voice": false,
  "language": "en"
}

Response:
{
  "session_id": "web_abc123_xyz789_20260212110000",
  "response": "**Passport Renewal Steps:**\n1. Book appointment...",
  "step": "start",
  "audio_base64": null
}
```

#### POST /api/consular/chat-widget
Lightweight widget chat with concise responses.

```json
Request:
{
  "message": "What is OCI?",
  "session_id": "optional",
  "mode": "concise"
}

Response:
{
  "session_id": "wgt_abc123_xyz789_20260212110000",
  "response": "OCI is a lifelong visa for Indian origin foreigners..."
}
```

### Webhook Endpoints

#### POST /api/whatsapp/webhook
Twilio WhatsApp webhook receiver.

#### GET/POST /api/facebook/webhook
Facebook Messenger webhook (GET for verification, POST for messages).

### Monitoring Endpoints

#### GET /api/monitoring/health
```json
{
  "status": "healthy",
  "services": {"mongodb": true, "llm": true}
}
```

#### GET /api/monitoring/security
```json
{
  "guardrails": {"pii_detections": 49, "unsafe_output_detections": 0},
  "session_security": {"ttl_hours": 24, "channel_isolation": true},
  "rate_limiting": {"total_requests": 100, "blocked_requests": 2},
  "cost_monitoring": {"total_cost_usd": 1.25, "daily_budget": 50.0}
}
```

#### GET /api/monitoring/costs
```json
{
  "daily_stats": {
    "total_tokens": 15000,
    "total_cost_usd": 1.25,
    "budget": {"daily_limit": 50.0, "remaining": 48.75}
  }
}
```

#### GET /api/monitoring/rate-limits
```json
{
  "stats": {
    "total_requests": 100,
    "blocked_requests": 2,
    "block_rate": 2.0
  }
}
```

---

## Database Schema

### Collections

#### chat_sessions
```json
{
  "id": "web_abc123_xyz789_20260212110000",
  "channel": "web",
  "user_identifier": "user@example.com",
  "messages": [
    {"role": "user", "content": "...", "timestamp": "..."},
    {"role": "assistant", "content": "...", "timestamp": "..."}
  ],
  "step": "start",
  "created_at": "2026-02-12T11:00:00Z",
  "expires_at": "2026-02-13T11:00:00Z",
  "is_active": true
}
```

#### companies
```json
{
  "id": "uuid",
  "name": "Company Name",
  "email": "admin@company.com",
  "llm_model": "gpt-5.2",
  "features": {"voice": true, "documents": true},
  "status": "active"
}
```

#### whatsapp_users
```json
{
  "id": "uuid",
  "phone_number": "+27123456789",
  "profile_name": "John Doe",
  "last_interaction": "2026-02-12T11:00:00Z",
  "interaction_count": 15
}
```

#### cost_summaries
```json
{
  "date": "2026-02-12",
  "total_requests": 100,
  "total_sessions": 25,
  "total_tokens": 15000,
  "total_cost_usd": 1.25,
  "budget_exceeded": false
}
```

---

## Configuration

### Environment Variables

#### Required
```bash
MONGO_URL="mongodb://localhost:27017"
DB_NAME="seva_setu_db"
EMERGENT_LLM_KEY="sk-emergent-..."
JWT_SECRET="your-secret-key"
```

#### Security Configuration
```bash
# Rate Limiting
RATE_LIMIT_IP_PER_MIN=30
RATE_LIMIT_IP_PER_HOUR=500
RATE_LIMIT_USER_PER_DAY=500
RATE_LIMIT_PHONE_PER_DAY=100

# Cost Monitoring
DAILY_TOKEN_BUDGET=50.0
MONTHLY_TOKEN_BUDGET=1000.0
SESSION_TOKEN_BUDGET=1.0
LLM_INPUT_COST_PER_1K=0.01
LLM_OUTPUT_COST_PER_1K=0.03

# Session Management
SESSION_TTL_HOURS=24
MAX_SESSIONS_PER_USER=10
```

#### External Services (Optional)
```bash
# Twilio WhatsApp
TWILIO_ACCOUNT_SID=""
TWILIO_AUTH_TOKEN=""
TWILIO_WHATSAPP_NUMBER=""

# Facebook Messenger
FB_PAGE_ACCESS_TOKEN=""
FB_VERIFY_TOKEN=""
FB_APP_SECRET=""

# Alerts
SMTP_HOST="smtp.gmail.com"
SMTP_PORT=587
ALERT_EMAILS=""
```

---

## Deployment

### Preview Environment
- **URL**: https://visa-aide.preview.emergentagent.com
- **Backend Port**: 8001 (internal)
- **Frontend Port**: 3000 (internal)

### Health Check
```bash
curl https://visa-aide.preview.emergentagent.com/health
# {"status": "healthy", "service": "seva-setu-bot"}
```

### Files Structure
```
/app/
├── backend/
│   ├── security/           # Security modules
│   │   ├── webhook_validator.py
│   │   ├── session_manager.py
│   │   ├── input_sanitizer.py
│   │   ├── guardrail.py
│   │   ├── rate_limiter.py
│   │   ├── cost_monitor.py
│   │   └── whatsapp_policy.py
│   ├── server.py          # Main FastAPI app
│   ├── consular_routes.py # Chat endpoints
│   ├── whatsapp_routes.py # WhatsApp integration
│   ├── facebook_routes.py # Facebook integration
│   └── monitoring_routes.py # Health & metrics
├── frontend/
│   ├── public/
│   │   └── embed.js       # Embeddable widget
│   └── src/
│       └── pages/         # React pages
└── docs/
    └── TECHNICAL_DOCS.md  # This file
```

---

## Credentials (Development)

| Account | Email | Password |
|---------|-------|----------|
| Super Admin | superadmin@sarthak.ai | Admin@2025 |

---

## Support & Contact

- **Emergency Consular**: +27 6830 38144
- **Email**: cons.joburg@mea.gov.in
- **Website**: https://www.cgijoburg.gov.in
