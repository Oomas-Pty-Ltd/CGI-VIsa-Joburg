# Seva Setu Bot - Complete Technical Documentation

**Version:** 2.0.0  
**Last Updated:** February 17, 2026  
**Status:** Production-Ready with WCAG 2.1 AA Compliance

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Security Features](#security-features)
4. [UI/UX Design System](#uiux-design-system)
5. [Dynamic Theme System](#dynamic-theme-system)
6. [Error Handling & Auto-Recovery](#error-handling--auto-recovery)
7. [API Reference](#api-reference)
8. [Database Schema](#database-schema)
9. [Configuration Guide](#configuration-guide)
10. [Deployment Guide](#deployment-guide)
11. [Accessibility Compliance](#accessibility-compliance)
12. [Testing Guidelines](#testing-guidelines)

---

## 1. System Overview

### Purpose
Seva Setu Bot is a sophisticated, multi-tenant consular automation platform designed for Indian and South African citizens. It provides AI-powered assistance for passport services, visa applications, OCI services, and emergency consular support.

### Key Features
- 🤖 **AI-Powered Chat**: GPT-5.2 powered conversational interface
- 🎤 **Voice Input**: OpenAI Whisper speech-to-text (33 languages)
- 📸 **Document Scanning**: Real-time OCR and data extraction
- 🌍 **Multi-Language**: 22 Indian + 11 South African languages
- 🔒 **Security**: GDPR, POPIA, DPDA compliant
- 📊 **Analytics**: Real-time monitoring and cost tracking
- 🎨 **Dynamic Themes**: Context-aware UI that adapts to conversations

### Technology Stack
| Layer | Technology |
|-------|------------|
| Frontend | React 18, Tailwind CSS, Shadcn UI |
| Backend | FastAPI, Python 3.11 |
| Database | MongoDB with Motor (async) |
| AI/ML | OpenAI GPT-5.2, Whisper, Vision |
| Auth | JWT with HS256 |
| Messaging | Twilio (WhatsApp), Facebook Messenger |

---

## 2. Architecture

### System Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Theme    │  │ Error    │  │ Access-  │  │ Consular │       │
│  │ Provider │  │ Boundary │  │ ibility  │  │ Bot UI   │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼─────────────┼─────────────┼─────────────┼───────────────┘
        │             │             │             │
        └─────────────┴──────┬──────┴─────────────┘
                             │ HTTPS
┌────────────────────────────▼────────────────────────────────────┐
│                     BACKEND (FastAPI)                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Security Layer                         │  │
│  │  • Rate Limiter  • Input Sanitizer  • PII Guardrails    │  │
│  │  • HSTS Headers  • JWT Auth         • Audit Logging     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Auth     │  │ Consular │  │ Admin    │  │ User     │       │
│  │ Routes   │  │ Routes   │  │ Routes   │  │ Routes   │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       │             │             │             │               │
│  ┌────▼─────────────▼─────────────▼─────────────▼────┐         │
│  │                   Services Layer                    │         │
│  │  • AI Chat    • Speech  • Document  • Notification │         │
│  │  • Feedback   • Audit   • GDPR      • Escalation  │         │
│  └────────────────────────┬────────────────────────────┘         │
└───────────────────────────┼─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                       MongoDB                                    │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐           │
│  │ users   │  │sessions │  │documents│  │ audit   │           │
│  │         │  │         │  │         │  │ _logs   │           │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

### File Structure
```
/app/
├── backend/
│   ├── server.py              # Main FastAPI application
│   ├── database.py            # MongoDB connection & indexes
│   ├── auth_utils.py          # JWT authentication
│   ├── voice_service.py       # TTS with 33 language support
│   ├── speech_service.py      # STT with Whisper
│   ├── security/              # Security middleware
│   │   ├── rate_limiter.py    # 30 req/min per IP
│   │   ├── guardrail.py       # PII detection & masking
│   │   ├── input_sanitizer.py # XSS/injection prevention
│   │   └── webhook_validator.py
│   ├── services/              # Business logic
│   │   ├── document_service.py    # Document management
│   │   ├── notification_service.py
│   │   ├── audit_service.py       # Compliance logging
│   │   ├── feedback_service.py
│   │   ├── compliance_service.py  # GDPR export/delete
│   │   └── whatsapp_rule_engine.py
│   └── routes/
│       ├── auth_routes.py
│       ├── consular_routes.py
│       ├── admin_routes.py
│       └── user_routes.py
│
├── frontend/
│   ├── src/
│   │   ├── App.js             # Main app with providers
│   │   ├── context/
│   │   │   └── ThemeContext.jsx  # Dynamic theming
│   │   ├── components/
│   │   │   ├── ErrorSystem.jsx   # Error boundary
│   │   │   ├── Accessibility.jsx # A11y components
│   │   │   └── ui/               # Shadcn components
│   │   ├── pages/
│   │   │   ├── ConsularBot.jsx   # Main chat interface
│   │   │   └── AdminDashboardPage.jsx
│   │   └── styles/
│   │       ├── accessibility.css  # WCAG styles
│   │       └── google-design.css  # Google AI design
│   └── public/
│
└── docs/
    ├── TECHNICAL_DOCS.md
    ├── PRE_PRODUCTION_CHECKLIST.md
    └── USER_GUIDE.md
```

---

## 3. Security Features

### Authentication Flow
```
┌────────────┐     ┌────────────┐     ┌────────────┐
│   User     │────▶│  Login API │────▶│ Verify     │
│            │     │            │     │ Credentials│
└────────────┘     └────────────┘     └─────┬──────┘
                                            │
                   ┌────────────┐     ┌─────▼──────┐
                   │  Return    │◀────│ Generate   │
                   │  JWT Token │     │ JWT Token  │
                   └────────────┘     └────────────┘
```

### Rate Limiting
- **Limit**: 30 requests per minute per IP
- **Burst**: 1.5x multiplier for short bursts
- **Penalty**: 429 status code with retry-after header

### Security Headers
```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

### PII Handling
- **Detection**: Microsoft Presidio with custom Indian ID patterns
- **Masking**: Aadhaar, PAN, passport numbers auto-masked in logs
- **Encryption**: AES-256 for documents at rest

---

## 4. UI/UX Design System

### Design Philosophy
Inspired by Google's Material Design 3 and Gemini AI interface:
- Clean, minimal surfaces
- Subtle animations and transitions
- Glass morphism effects
- High-contrast focus indicators
- 44px minimum touch targets

### Color System
| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| Primary | #4285F4 | #60A5FA | CTAs, links |
| Secondary | #34A853 | #34D399 | Success states |
| Error | #EA4335 | #F87171 | Error states |
| Surface | #FFFFFF | #1E293B | Card backgrounds |
| Text | #202124 | #F1F5F9 | Primary text |

### Animation Timing
```css
--ease-standard: cubic-bezier(0.4, 0.0, 0.2, 1);    /* General */
--ease-decelerate: cubic-bezier(0.0, 0.0, 0.2, 1);  /* Entering */
--ease-accelerate: cubic-bezier(0.4, 0.0, 1, 1);    /* Exiting */
--duration-short: 100ms;   /* Hover, ripple */
--duration-medium: 250ms;  /* Most transitions */
--duration-long: 400ms;    /* Complex animations */
```

---

## 5. Dynamic Theme System

### Available Themes
| Theme | Trigger Keywords | Primary Color | Use Case |
|-------|-----------------|---------------|----------|
| Welcome | (default) | #FF6B35 (Saffron) | Initial greeting |
| Passport | passport, renew, tatkal | #1A2E40 (Navy) | Passport services |
| Visa | visa, tourist, business | #6366F1 (Indigo) | Visa applications |
| OCI | oci, overseas citizen | #0EA5E9 (Sky) | OCI services |
| Emergency | emergency, lost, urgent | #DC2626 (Red) | Crisis situations |
| Success | thank, completed, done | #059669 (Green) | Completion |
| Night | (auto 8PM-6AM) | #60A5FA (Blue) | Low-light mode |

### Implementation
```jsx
import { useTheme } from '@/context/ThemeContext';

function MyComponent() {
  const { theme, changeTheme, updateThemeFromConversation } = useTheme();
  
  // Auto-detect theme from messages
  useEffect(() => {
    updateThemeFromConversation(messages);
  }, [messages]);
  
  return (
    <div style={{ background: theme.background }}>
      {/* Content */}
    </div>
  );
}
```

---

## 6. Error Handling & Auto-Recovery

### Error Boundary
Catches all React render errors and provides recovery options:
- Automatic error reporting to admin
- User-friendly error screen
- One-click recovery attempt
- Page refresh fallback

### Error Types & Recovery
| Type | Auto-Retry | Admin Alert | Recovery Action |
|------|------------|-------------|-----------------|
| NETWORK | Yes (3x) | No | Check connection |
| API | Yes (3x) | On 3rd fail | Retry request |
| TIMEOUT | Yes (2x) | No | Shorten message |
| AUTH | No | No | Re-login |
| BOT_STUCK | Yes | Yes | Restart conversation |
| RATE_LIMIT | Wait 30s | No | Slow down |
| CRITICAL | No | Immediate | Manual intervention |

### Admin Error Reports Endpoint
```http
POST /api/admin/error-report
Content-Type: application/json

{
  "error_type": "bot_stuck",
  "error_message": "No response for 30 seconds",
  "severity": "high",
  "context": {
    "url": "https://example.com/consular",
    "userAgent": "...",
    "timestamp": "2026-02-17T20:00:00Z"
  }
}
```

---

## 7. API Reference

### Authentication
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/auth/super-admin/login` | POST | None | Super admin login |
| `/api/auth/local-admin/login` | POST | None | Local admin login |

### Consular Services
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/consular/chat` | POST | Optional | Main chat endpoint |
| `/api/consular/voice-input` | POST | None | Speech-to-text |
| `/api/consular/document-scan` | POST | None | OCR processing |
| `/api/consular/tts` | POST | None | Text-to-speech |

### User Endpoints
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/user/feedback` | POST | None | Submit feedback |
| `/api/user/profile` | GET/PUT | JWT | Profile management |
| `/api/user/notifications` | GET | JWT | Get notifications |
| `/api/user/data-export` | POST | JWT | GDPR data export |
| `/api/user/data-delete` | POST | JWT | GDPR data deletion |

### Admin Endpoints
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/admin/dashboard` | GET | Super Admin | Dashboard metrics |
| `/api/admin/escalations` | GET | Admin | View escalations |
| `/api/admin/knowledge` | GET/POST | Admin | Knowledge base |
| `/api/admin/error-reports` | GET | Super Admin | Error reports |
| `/api/admin/observability` | GET | Admin | AI metrics |

---

## 8. Database Schema

### Collections & Indexes
```javascript
// users
{
  id: { unique: true },
  email: { unique: true, sparse: true },
  phone: { sparse: true }
}

// chat_sessions
{
  id: { unique: true },
  user_id: { index: true },
  session_id: { index: true },
  created_at: { index: true },
  compound: [user_id, created_at]
}

// documents
{
  id: { unique: true },
  user_id: { index: true },
  expiry_status: { index: true },
  next_check_date: { index: true }
}

// audit_logs
{
  id: { unique: true },
  user_id: { index: true },
  timestamp: { index: true },
  compound: [category, timestamp],
  compound: [user_id, timestamp]
}

// knowledge_base
{
  id: { unique: true },
  category: { index: true },
  text_search: [title, question, answer]
}
```

---

## 9. Configuration Guide

### Environment Variables

#### Backend (.env)
```bash
# Database
MONGO_URL=mongodb+srv://user:pass@cluster.mongodb.net
DB_NAME=seva_setu_prod

# AI Services
EMERGENT_LLM_KEY=sk-emergent-xxxxx

# Security
JWT_SECRET=<256-bit-random-string>
DOCUMENT_ENCRYPTION_KEY=<32-byte-base64>

# WhatsApp (when ready)
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=xxxxx
TWILIO_WHATSAPP_NUMBER=+14155238886

# Facebook (when ready)
FB_PAGE_ACCESS_TOKEN=EAAxxxxx
FB_APP_SECRET=xxxxx

# CORS (production)
CORS_ORIGINS=https://yourdomain.com
```

#### Frontend (.env)
```bash
REACT_APP_BACKEND_URL=https://api.yourdomain.com
```

---

## 10. Deployment Guide

### Prerequisites
- Node.js 18+
- Python 3.11+
- MongoDB 6.0+
- Redis (optional, for persistent rate limiting)

### Production Checklist
See `/app/docs/PRE_PRODUCTION_CHECKLIST.md` for complete list.

Key items:
- [ ] Set production CORS origins
- [ ] Configure SMTP for notifications
- [ ] Set up Redis for rate limiting persistence
- [ ] Configure document encryption key
- [ ] Enable HTTPS everywhere
- [ ] Set up monitoring/alerting

---

## 11. Accessibility Compliance

### WCAG 2.1 AA Checklist
| Criterion | Status | Implementation |
|-----------|--------|----------------|
| 1.1.1 Non-text Content | ✅ | All images have alt text |
| 1.3.1 Info and Relationships | ✅ | Semantic HTML, ARIA roles |
| 1.4.3 Contrast Minimum | ✅ | 4.5:1 ratio verified |
| 2.1.1 Keyboard | ✅ | All functions accessible |
| 2.4.1 Bypass Blocks | ✅ | Skip links |
| 2.4.7 Focus Visible | ✅ | 3px orange outline |
| 2.5.5 Target Size | ✅ | 44x44px minimum |
| 4.1.2 Name, Role, Value | ✅ | Full ARIA support |

### Accessibility Features
- Skip link to main content
- Screen reader announcements for dynamic content
- Reduced motion support
- High contrast mode support
- Keyboard navigation throughout
- Form labels and error associations

---

## 12. Testing Guidelines

### Test Commands
```bash
# Backend unit tests
cd /app/backend && pytest tests/ -v

# Frontend lint
cd /app/frontend && yarn lint

# Run negative test suite
pytest tests/test_negative_scenarios.py -v
```

### Test Coverage Requirements
- All API endpoints: 100%
- Negative scenarios: 18 categories
- UI components: Visual regression
- Accessibility: Automated axe-core audit

### Key Test Scenarios
1. Empty/whitespace input handling
2. Long message processing (>5000 chars)
3. Invalid file type rejection
4. Large file rejection (>10MB)
5. Malformed JSON handling
6. Authentication failures
7. Rate limiting enforcement
8. SQL injection prevention
9. XSS attack prevention
10. Unicode/special character support

---

## Support

- **Technical Issues**: Check `/api/admin/error-reports`
- **Documentation Updates**: Edit files in `/app/docs/`
- **Security Concerns**: Contact security team immediately

---

*Document maintained by Seva Setu Development Team*
