# Seva Setu Bot - Complete Documentation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Features](#features)
4. [Installation & Setup](#installation--setup)
5. [API Documentation](#api-documentation)
6. [Avatar System](#avatar-system)
7. [Multi-Language Support](#multi-language-support)
8. [Security Features](#security-features)
9. [Testing](#testing)
10. [Deployment](#deployment)

---

## Overview

**Seva Setu Bot** is an advanced AI-powered consular automation platform for the Consulate General of India, Johannesburg. It provides multi-lingual, audio-visual assistance for Indian and South African citizens.

### Key Capabilities
- **Interactive Talking Avatar** with real-time voice synthesis
- **Multi-language support** (Hindi, English, Afrikaans, Zulu, Tamil, etc.)
- **Document OCR** with translation
- **Real-time web scraping** from official sources
- **Multi-tenant architecture** for companies
- **GDPR/POPIA compliant** data handling

---

## Architecture

### Tech Stack
```
Frontend:  React 18 + Tailwind CSS + Shadcn UI
Backend:   FastAPI + Python 3.11
Database:  MongoDB
AI/ML:     OpenAI GPT-5.2 + TTS-1-HD
Voice:     Web Speech API + OpenAI TTS
```

### System Components

```
┌─────────────────────────────────────────┐
│         Frontend (React)                │
│  - Landing Page                         │
│  - Consular Bot (Avatar + Chat)         │
│  - Super Admin Dashboard                │
│  - Local Admin Portal                   │
└─────────────┬───────────────────────────┘
              │
              │ HTTPS/WebSocket
              │
┌─────────────▼───────────────────────────┐
│         Backend (FastAPI)               │
│  - Auth Routes                          │
│  - Consular Routes                      │
│  - Admin Routes                         │
│  - Voice Service                        │
│  - Knowledge Scraper                    │
└─────────────┬───────────────────────────┘
              │
    ┌─────────┴─────────┐
    │                   │
┌───▼────┐      ┌───────▼──────┐
│MongoDB │      │  External    │
│        │      │  - OpenAI    │
│        │      │  - CGI Site  │
│        │      │  - VFS Site  │
└────────┘      └──────────────┘
```

---

## Features

### 1. Interactive Talking Avatar

**Visual Characteristics:**
- Professional Indian woman in traditional attire
- Represents modern India
- Namaste greeting gesture
- Round profile with animated borders

**Speaking Indicators:**
- Green pulsing ring when speaking
- Animated status dots
- "Speaking..." text indicator
- Brightness increase during speech

**Voice Capabilities:**
- OpenAI TTS-1-HD (high quality)
- Language-specific voices:
  - English: "Nova" (energetic)
  - Hindi: "Shimmer" (bright)
  - Afrikaans: "Alloy" (neutral)
  - Zulu: "Coral" (warm)

### 2. Typing Animation

**Behavior:**
- Shows "Seva Setu is typing..." with bouncing dots
- Text appears character-by-character (20ms speed)
- Synchronized with voice playback
- Smooth markdown rendering

### 3. Real-Time Web Scraping

**Sources:**
- cgijoburg.gov.in
- visa.vfsglobal.com

**Features:**
- Scrapes every API call
- Change detection with MD5 hashing
- Logs: `/app/logs/knowledge_changes.log`
- Exception emails to: mayurakole@example.com

### 4. Document Processing

**OCR Capabilities:**
- Reads documents in ANY language
- Extracts: Name, DOB, Address, Document Number
- Translates to English for form-filling
- JSON structured output

**Supported Formats:**
- Images: JPG, JPEG, PNG
- Documents: PDF
- Max size: 10MB
- MIME validation for security

### 5. Multi-Tenant System

**Super Admin:**
- Create companies
- Manage LLM configurations
- View global analytics
- Monitor system health

**Local Admin:**
- Upload knowledge base documents
- View masked chat logs (Presidio)
- Toggle voice/camera features
- Generate analytics reports

---

## Installation & Setup

### Prerequisites
```bash
- Python 3.11+
- Node.js 18+
- MongoDB 6.0+
- Redis (optional, for caching)
```

### Backend Setup

```bash
cd /app/backend

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your keys

# Run backend
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### Frontend Setup

```bash
cd /app/frontend

# Install dependencies
yarn install

# Configure environment
cp .env.example .env
# Edit REACT_APP_BACKEND_URL

# Run frontend
yarn start
```

### Environment Variables

**Backend (.env):**
```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=seva_setu_db
EMERGENT_LLM_KEY=sk-emergent-xxxxx
JWT_SECRET=your-secret-key
SUPER_ADMIN_EMAIL=admin@example.com
SUPER_ADMIN_PASSWORD=SecurePassword123
CORS_ORIGINS=*
UPLOAD_DIR=/app/uploads
```

**Frontend (.env):**
```env
REACT_APP_BACKEND_URL=https://your-domain.com
WDS_SOCKET_PORT=443
ENABLE_HEALTH_CHECK=false
```

---

## API Documentation

### Authentication

#### Super Admin Login
```http
POST /api/auth/super-admin/login
Content-Type: application/json

{
  "email": "superadmin@sarthak.ai",
  "password": "Admin@2025"
}

Response:
{
  "token": "eyJhbGci...",
  "user_type": "super_admin",
  "user_id": "uuid"
}
```

#### Local Admin Login
```http
POST /api/auth/local-admin/login
Content-Type: application/json

{
  "email": "admin@company.com",
  "password": "password"
}
```

### Consular Bot

#### Chat with Avatar
```http
POST /api/consular/chat
Content-Type: application/json

{
  "message": "I need passport information",
  "session_id": "uuid" (optional),
  "user_id": "guest",
  "enable_voice": true,
  "language": "en"
}

Response:
{
  "session_id": "uuid",
  "response": "**Hello!** Here's passport info...",
  "step": "register",
  "audio_base64": "base64_encoded_mp3" (if enable_voice=true)
}
```

#### Document Scan with OCR
```http
POST /api/consular/document-scan
Content-Type: application/json

{
  "image_base64": "base64_encoded_image",
  "document_type": "passport",
  "session_id": "uuid"
}

Response:
{
  "success": true,
  "extracted_data": {
    "full_name": "John Doe",
    "date_of_birth": "1990-01-01",
    "document_number": "ABC123456",
    ...
  }
}
```

### Super Admin

#### Create Company
```http
POST /api/super-admin/companies
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Acme Corp",
  "email": "admin@acme.com",
  "admin_password": "SecurePass123",
  "llm_model": "gpt-5.2",
  "features": {
    "voice": true,
    "camera": true
  }
}
```

#### Get Analytics
```http
GET /api/super-admin/analytics/overview
Authorization: Bearer {token}

Response:
{
  "total_companies": 10,
  "total_sessions": 1500,
  "total_documents": 500
}
```

---

## Avatar System

### Visual States

**1. Idle State:**
- Orange ring (#E06F2C)
- Normal brightness
- "Ready to Assist" status

**2. Speaking State:**
- Green pulsing ring (#2E8B57)
- Increased brightness (110%)
- Scale: 105%
- "🎙️ Speaking..." status
- Bouncing dots animation

**3. Typing State:**
- Shows typing indicator in chat
- Orange bouncing dots
- "Seva Setu is typing..." message

### Voice Toggle

**Component:**
```jsx
<label>
  <input 
    type="checkbox" 
    checked={enableVoice}
    onChange={(e) => setEnableVoice(e.target.checked)}
  />
  {enableVoice ? "🔊 Voice Enabled" : "🔇 Voice Disabled"}
</label>
```

**Behavior:**
- User can toggle on/off
- Persists during session
- Shows clear visual feedback

---

## Multi-Language Support

### Supported Languages

| Language | Script | Voice | Detection |
|----------|--------|-------|-----------|
| English | Latin | Nova | Default |
| Hindi | देवनागरी | Shimmer | Regex: `[\u0900-\u097F]` |
| Tamil | தமிழ் | Nova | Regex: `[\u0B80-\u0BFF]` |
| Afrikaans | Latin | Alloy | User context |
| Zulu | Latin | Coral | User context |

### Language Detection

```javascript
// Auto-detect from user input
const isHindi = /[\u0900-\u097F]/.test(message);
const isTamil = /[\u0B80-\u0BFF]/.test(message);
const langCode = isHindi ? "hi" : isTamil ? "ta" : "en";
```

### Response Format

Bot ALWAYS responds in the SAME language and script:
- User writes Hindi (देवनागरी) → Bot responds in देवनागरी
- User writes English → Bot responds in English
- No romanization or script changes

---

## Security Features

### 1. File Upload Validation

```python
ALLOWED_FORMATS = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf']
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Checks:
- File extension
- MIME type (prevents spoofing)
- File size
- Filename sanitization
```

### 2. PII Masking (Microsoft Presidio)

```python
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

# Masks: PERSON, EMAIL, PHONE, LOCATION, DATE_TIME
masked_text = mask_pii(original_text)
```

### 3. JWT Authentication

```python
JWT_ALGORITHM = 'HS256'
TOKEN_EXPIRY = 7 days

# Roles: super_admin, local_admin, user
```

### 4. CORS Configuration

```python
CORS_ORIGINS = ["https://your-domain.com"]
allow_credentials = True
allow_methods = ["*"]
allow_headers = ["*"]
```

---

## Testing

### Manual Testing

**1. Test Avatar Speaking:**
```bash
curl -X POST "https://your-domain.com/api/consular/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me about passport services",
    "enable_voice": true,
    "language": "en"
  }'
```

**2. Test Multi-Language:**
```bash
# Hindi
curl -X POST "..." -d '{"message": "मुझे पासपोर्ट की जानकारी चाहिए"}'

# Tamil
curl -X POST "..." -d '{"message": "கடவுச்சீட்டு பற்றி"}'
```

**3. Test Document OCR:**
```bash
# Convert image to base64
base64 passport.jpg > passport_b64.txt

curl -X POST ".../document-scan" \
  -d '{"image_base64": "...base64...", "document_type": "passport"}'
```

### Automated Testing

Run testing agent:
```bash
testing_agent_v3 --task "Test all features"
```

---

## Deployment

### Production Checklist

- [ ] Update `.env` with production values
- [ ] Set `CORS_ORIGINS` to your domain
- [ ] Enable HTTPS
- [ ] Configure MongoDB replication
- [ ] Set up Redis for caching
- [ ] Enable rate limiting
- [ ] Configure backup system
- [ ] Set up monitoring (logs, errors)
- [ ] Test all endpoints
- [ ] Load testing

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: seva-setu-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: seva-setu-backend
  template:
    metadata:
      labels:
        app: seva-setu-backend
    spec:
      containers:
      - name: backend
        image: seva-setu-backend:latest
        ports:
        - containerPort: 8001
        env:
        - name: MONGO_URL
          valueFrom:
            secretKeyRef:
              name: seva-setu-secrets
              key: mongo-url
```

---

## Support & Maintenance

### Logs Location
```
/app/logs/knowledge_changes.log  - Web scraping changes
/app/logs/exception_emails.log   - Exception reports
/var/log/supervisor/backend.*.log - Backend logs
/var/log/supervisor/frontend.*.log - Frontend logs
```

### Exception Monitoring
All exceptions automatically emailed to: **mayurakole@example.com**

### Contact
- Emergency Support: +27 6830 38144
- Email: cons.joburg@mea.gov.in
- Documentation: This file

---

## Version History

**v1.0.0** (January 2026)
- Initial release
- Talking avatar with TTS
- Multi-language support
- Real-time web scraping
- Multi-tenant system
- Document OCR
- Security features

---

**Built with ❤️ for Consulate General of India, Johannesburg**
