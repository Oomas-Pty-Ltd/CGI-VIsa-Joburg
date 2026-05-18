# Seva Setu Bot - Pre-Production Checklist

> **Last Updated:** February 12, 2026  
> **Status:** IN PROGRESS  
> **Target:** Production-Ready Deployment

---

## 🔴 CRITICAL - Must Resolve Before Go-Live

### Infrastructure Requirements

| Item | Status | Notes |
|------|--------|-------|
| Redis Server | ⏳ PENDING | Required for AI call queue, rate limiting persistence |
| MongoDB Atlas (Production) | ⏳ PENDING | Current: Development cluster |
| SSL Certificate | ✅ DONE | Via Kubernetes ingress |
| Domain Configuration | ⏳ PENDING | Production domain setup |
| Environment Variables | ⏳ PENDING | Production secrets in vault |

### External Service Credentials

| Service | Status | Required For |
|---------|--------|--------------|
| Twilio Account SID | ⏳ PENDING | WhatsApp Business API |
| Twilio Auth Token | ⏳ PENDING | WhatsApp Business API |
| Twilio WhatsApp Number | ⏳ PENDING | WhatsApp sender ID |
| Facebook Page Access Token | ⏳ PENDING | Messenger integration |
| Facebook App Secret | ⏳ PENDING | Webhook verification |
| SMTP Server Credentials | ⏳ PENDING | Email notifications |
| Emergent LLM Key (Production) | ✅ DONE | AI services |

### Security Configurations

| Item | Status | Priority |
|------|--------|----------|
| CORS Whitelist | ⏳ PENDING | Restrict from `*` to production domains |
| HSTS Header | ⏳ PENDING | Enable strict transport security |
| Rate Limit Redis Backend | ⏳ PENDING | Currently in-memory (resets on restart) |
| JWT Secret Rotation | ⏳ PENDING | Production-grade secret |
| Document Encryption Keys | ⏳ PENDING | AES-256 master key in vault |

---

## 🟠 HIGH PRIORITY - Required for Full Functionality

### Feature Completion

| Feature | Status | Details |
|---------|--------|---------|
| Document Expiry Logic | 🔄 IN PROGRESS | 3-month recheck schedule |
| Profile Update Persistence | 🔄 IN PROGRESS | Fix save issues |
| Notification Service | 🔄 IN PROGRESS | Status change alerts |
| Feedback Storage | 🔄 IN PROGRESS | MongoDB with session ID |
| Knowledge Base Indexing | 🔄 IN PROGRESS | Search optimization |
| Audit Trail System | 🔄 IN PROGRESS | User action logging |
| GDPR Export/Delete | 🔄 IN PROGRESS | Compliance endpoints |

### WhatsApp Integration

| Item | Status | Notes |
|------|--------|-------|
| Emergency Rule Engine | 🔄 IN PROGRESS | Keyword detection |
| Session Context Storage | 🔄 IN PROGRESS | Last 5 messages |
| Media Message Handling | 🔄 IN PROGRESS | Vision OCR pipeline |
| Twilio Webhook Verification | ✅ DONE | Signature validation ready |

### Voice System

| Item | Status | Notes |
|------|--------|-------|
| Whisper Integration | ✅ DONE | Using whisper-1 model |
| Audio Chunking (>60s) | ⏳ PENDING | Split long recordings |
| Confidence Scoring | ⏳ PENDING | <0.7 triggers confirmation |
| Extended Language Support | ⏳ PENDING | 22 Indian + 11 SA languages |
| TTS Voice Mapping | ⏳ PENDING | Dynamic voice selection |
| Audio Playback Control | ⏳ PENDING | Stop/interrupt support |

---

## 🟡 MEDIUM PRIORITY - Performance & UX

### Performance Optimization

| Item | Status | Dependency |
|------|--------|------------|
| Redis Queue Workers | ⏳ PENDING | Requires Redis |
| DB Index: user_id | ⏳ PENDING | - |
| DB Index: session_id | ⏳ PENDING | - |
| DB Index: phone | ⏳ PENDING | - |
| Connection Pooling | ⏳ PENDING | MongoDB motor config |
| Worker Auto-Restart | ⏳ PENDING | Requires Redis |

### UI/UX Accessibility

| Item | Status | WCAG Level |
|------|--------|------------|
| ARIA Labels | ⏳ PENDING | AA |
| Form Label Association | ⏳ PENDING | AA |
| Responsive Grid Fixes | ⏳ PENDING | - |
| Color Contrast | ⏳ PENDING | AA |
| Keyboard Navigation | ⏳ PENDING | AA |
| Error Recovery Messages | ⏳ PENDING | - |

### Localization

| Item | Status | Languages |
|------|--------|-----------|
| Language Detection | 🔄 IN PROGRESS | Auto-detect input |
| Indian Languages | ⏳ PENDING | 22 official languages |
| South African Languages | ⏳ PENDING | 11 official languages |
| Font Rendering Tests | ⏳ PENDING | Devanagari, Tamil, etc. |
| RTL Support | ⏳ PENDING | If needed |

---

## 📋 CONFIGURATION TEMPLATES

### Production .env Template

```bash
# === DATABASE ===
MONGO_URL=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net
DB_NAME=seva_setu_prod

# === AI SERVICES ===
EMERGENT_LLM_KEY=sk-emergent-xxxxx

# === WHATSAPP (Twilio) ===
TWILIO_ACCOUNT_SID=ACxxxxx
TWILIO_AUTH_TOKEN=xxxxx
TWILIO_WHATSAPP_NUMBER=+14155238886

# === FACEBOOK MESSENGER ===
FB_PAGE_ACCESS_TOKEN=EAAxxxxx
FB_APP_SECRET=xxxxx
FB_VERIFY_TOKEN=seva_setu_verify_2026

# === EMAIL (SMTP) ===
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASS=SG.xxxxx
SMTP_FROM=noreply@sevasetu.gov.in

# === SECURITY ===
JWT_SECRET=<256-bit-random-string>
ENCRYPTION_KEY=<32-byte-AES-key-base64>

# === REDIS (when ready) ===
REDIS_URL=redis://<host>:6379/0

# === CORS ===
ALLOWED_ORIGINS=https://sevasetu.gov.in,https://admin.sevasetu.gov.in
```

### Redis Setup (When Ready)

```bash
# Option 1: Redis Cloud (Recommended)
# - Sign up at redis.com
# - Create free 30MB database
# - Copy connection string

# Option 2: Self-hosted
docker run -d --name redis -p 6379:6379 redis:alpine

# Option 3: AWS ElastiCache
# - Create Redis cluster in AWS console
# - Configure VPC access
```

---

## 🧪 PRE-LAUNCH TESTING CHECKLIST

### Security Testing
- [ ] Penetration test completed
- [ ] OWASP Top 10 vulnerabilities checked
- [ ] PII data handling verified
- [ ] Encryption at rest confirmed
- [ ] JWT token expiry tested
- [ ] Rate limiting stress tested

### Functional Testing
- [ ] All user flows tested
- [ ] Document upload/scan verified
- [ ] Multi-language responses confirmed
- [ ] WhatsApp mock flow tested
- [ ] Facebook mock flow tested
- [ ] Admin dashboard fully functional

### Performance Testing
- [ ] Load test: 100 concurrent users
- [ ] Response time <2s for chat
- [ ] Database queries optimized
- [ ] Memory usage stable

### Compliance
- [ ] GDPR compliance verified
- [ ] POPIA compliance verified
- [ ] DPDA compliance verified
- [ ] Data retention policy implemented
- [ ] User consent flows tested

---

## 📞 SUPPORT CONTACTS

| Role | Contact | Notes |
|------|---------|-------|
| Technical Lead | TBD | Architecture decisions |
| Security Officer | TBD | Compliance sign-off |
| Operations | TBD | Deployment support |
| Twilio Support | support@twilio.com | WhatsApp issues |
| MongoDB Support | TBD | Database issues |

---

## 📅 TIMELINE

| Phase | Target Date | Status |
|-------|-------------|--------|
| Security Hardening | Feb 15, 2026 | 🔄 IN PROGRESS |
| Functional Completion | Feb 20, 2026 | 🔄 IN PROGRESS |
| WhatsApp Integration | Feb 25, 2026 | ⏳ PENDING |
| Performance Optimization | Mar 1, 2026 | ⏳ PENDING |
| UAT Testing | Mar 5, 2026 | ⏳ PENDING |
| Production Deployment | Mar 10, 2026 | ⏳ PENDING |

---

*This document should be reviewed and updated weekly during the pre-production phase.*
