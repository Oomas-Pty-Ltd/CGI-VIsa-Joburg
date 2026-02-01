# Seva Setu Bot - Product Requirements Document

## Overview
Multi-tenant consular automation platform for Indian and South African citizens. GDPR, DPDA, and POPIA compliant.

## Core Features Implemented ✅

### 1. Multi-Tenancy
- **Super Admin Dashboard** (`/super-admin/login`)
  - Credentials: `superadmin@sarthak.ai` / `Admin@2025`
  - Manage companies, view analytics, create local admins
- **Local Admin Dashboard** (`/admin/login`)
  - Company-specific configuration
  - Document uploads, feature toggles

### 2. Consular Bot Interface (`/bot`)
- Professional Indian avatar with "Seva Setu Bot" branding
- Progress stepper: Register → Upload → Verify → Sign
- Voice toggle for TTS responses
- Welcome message in Namaste style

### 3. AI-Powered Chat (GPT-5.2)
- Real-time AI responses with typing animation
- Multi-language support (Hindi, English, Tamil, Zulu, Afrikaans)
- RAG system scraping official government websites
- Markdown-formatted responses

### 4. Multimodal Input
- Text chat input
- Voice input via Web Speech API
- Camera document scanning (react-webcam)
- File upload (JPG, PNG, PDF - max 10MB)

### 5. Document Processing
- OCR via GPT-5.2 Vision API
- Multi-language document extraction
- Auto-translation to English for forms

### 6. Text-to-Speech (ElevenLabs)
- Voice responses when toggle enabled
- Multi-language support

## Architecture

```
/app/
├── backend/
│   ├── server.py          # FastAPI app
│   ├── consular_routes.py # Chat, document processing
│   ├── super_admin_routes.py
│   ├── local_admin_routes.py
│   ├── knowledge_scraper.py
│   └── voice_service.py
├── frontend/
│   ├── src/pages/
│   │   ├── LandingPage.jsx
│   │   ├── ConsularBot.jsx
│   │   ├── SuperAdminDashboard.jsx
│   │   └── LocalAdminDashboard.jsx
```

## Test Status (December 2025)
- Backend: 100% (13/13 tests passed)
- Frontend: 100% (all UI components verified)
- Test file: `/app/backend/tests/test_seva_setu_api.py`

## Integrations
- **OpenAI GPT-5.2** - via Emergent LLM Key
- **ElevenLabs TTS** - Voice synthesis
- **MongoDB** - Database

## Known Limitations
- Talking avatar shows static image (Akool.com API key needed for lip-sync)
- Some official website scraping has SSL issues (fallback in place)

## Upcoming Tasks (P1-P2)
1. Language selector dropdown UI
2. Facebook & Instagram integration
3. PDF/CSV analytics reports
4. Docker packaging for KVM deployment

## URLs
- Preview: https://consular-genius.preview.emergentagent.com
- Bot: https://consular-genius.preview.emergentagent.com/bot
- Super Admin: https://consular-genius.preview.emergentagent.com/super-admin/login
