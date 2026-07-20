# Seva Setu Bot

A conversational service tool deployed by the Consulate General of India in Johannesburg. Seva Setu assists the Indian diaspora in South Africa by providing consular service guidance and application processing through a conversational interface.

## Core Purpose

The bot guides users through consular services end-to-end — from service discovery to application submission — via a chat-based widget embedded on the consulate's site.

## Service Categories

- **Type A — Government Redirect:** Passport, Visa, and PCC services. After account creation, users are redirected to the official government portal to complete the application.
- **Type B — In-Bot Processing:** OCI, Emergency/Death Certificates, Surrender of Citizenship, and Miscellaneous forms. These are handled entirely within the bot, with document upload or manual form completion.

## Key Process Flow

1. User initiates chat via the bot avatar.
2. Bilingual greeting and service menu are displayed.
3. User selects a service.
4. Bot provides the required documents checklist and a process overview.
5. User clicks "Apply Now."
6. Bot collects name and email; an account is created with a Reference ID.
7. **Type A:** redirect to the government portal. **Type B:** in-bot form submission options.
8. Type B applications include a review email with a 24-hour edit window before final confirmation.
9. A PDF is generated and a confirmation email is sent.

## Technical Specifications

- 40+ supported languages
- Voice input/output
- Real-time form validation
- Document uploads, max 5MB per file
- 30-minute inactivity timeout, with a warning at 25 minutes
- Submitted applications remain accessible via email + Reference ID; unsubmitted work is permanently cleared on logout

## Deployment

The app is a single FastAPI backend + React frontend, deployed multi-tenant (one backend instance serves several client bots, resolved per-request via nginx origin mapping).

| Environment | Host | Notes |
|---|---|---|
| **Stage** | kvm1 (Hostinger VPS) | PM2-managed process, served via nginx at `sevasetu-stage.seva.org.za`. Also runs a parallel Dockerized `staging` stack (auto-built via CI/CD from `ghcr.io/mobimerz/cgi-visa-joburg-{frontend,backend}` images) for CI verification, independent of the main PM2 deployment. |
| **Production** | AWS EC2 (ap-south-1), `t4g.small`, Graviton | PM2 process `seva_setu_multi`, MongoDB colocated on the same instance. Fronted by Cloudflare on the primary domain. |

Tenants served from the same backend, distinguished by nginx setting `X-Company-Id` based on request `Origin`:

- **CGI Johannesburg** — `www.cgijoburg.gov.in` (live consular client, Indian Visa/OCI/PCC/passport services configured)
- **Ruha**
- **Mobimerz** — `mobimerz.com`

Deploy flow (manual): `git pull` → `npm run build:widget` (frontend) → copy build output → `pm2 restart <process> --update-env`.

## Modules

### Backend (`backend/`, FastAPI)

**Entry point:** `server.py` (app + periodic job loop), `run_server.py`, `config.py`, `database.py` (Mongo), `tenant.py` (multi-tenant resolution).

**Routes:**
- `consular_routes.py` — core chat/bot conversation endpoints
- `seva_setu_auth_routes.py` — application submission, confirmation, retry
- `auth_routes.py`, `user_routes.py` — end-user auth
- `admin_routes.py`, `local_admin_routes.py`, `super_admin_routes.py` — tenant-level and platform-level admin APIs
- `whatsapp_routes.py`, `ics_whatsapp_routes.py`, `facebook_routes.py` — channel-specific webhooks (Twilio WhatsApp, ICS WABA/WASimple, Facebook Messenger)
- `template_routes.py`, `monitoring_routes.py`

**Services (`backend/services/`):**
- `application_flow.py`, `flow_steps.py` — the multi-step application flow engine
- `processing_service.py` — submits confirmed applications to the (mock) government processing endpoint
- `pdf_service.py`, `email_service.py` — confirmation PDF + email generation
- `notification_service.py`, `notification_dispatcher.py`, `notification_jobs.py`, `notification_registry.py` — alerting, including the periodic stuck-pending-application check
- `hybrid_retrieval.py`, `knowledge_service.py` — knowledge base / RAG retrieval for bot answers
- `intent_classifier.py` — user intent detection
- `messaging_channel_resolver.py` — routes a conversation to the right channel handler (web/WhatsApp/Facebook)
- `ics_waba_service.py` — ICS WhatsApp Business API integration
- `budget_guard.py`, `llm_usage.py` — per-tenant LLM budget enforcement
- `document_service.py` — upload handling
- `escalation_service.py` — human handoff/escalation
- `feedback_service.py` — user feedback capture
- `compliance_service.py`, `audit_service.py` — compliance checks + audit trail
- `bot_config.py`, `platform_config.py`, `model_registry.py`, `service_registry.py` — tenant/bot configuration and registries
- `response_cache.py`, `service_hooks.py`

**Other backend modules:** `presidio_service.py` (PII detection/redaction), `virus_scanner.py`, `file_security.py` (upload safety), `speech_service.py`, `voice_service.py` (voice I/O), `knowledge_scraper.py`, `monitoring_service.py`, `sevasetu_api_client.py`.

**Integrations configured via env:** OpenAI, Google AI, Twilio (WhatsApp), ICS WABA/WASimple (WhatsApp), Facebook Graph API, SMTP (email), MongoDB.

### Frontend (`frontend/src/`, React)

- `ChatWidget.jsx` — the embeddable chat widget (the core product, loaded on tenant sites)
- `pages/ConsularBot.jsx` — main bot page
- `pages/ICSWhatsAppBot.jsx` — WhatsApp-specific bot view
- `pages/SevaReview.jsx` — the application review page (24-hour edit window before confirmation)
- `pages/LocalAdminDashboard.jsx`, `pages/SuperAdminDashboard.jsx`, `AdminShell.jsx` — tenant-level and platform-level admin dashboards
- `pages/LoginPage.jsx`, `pages/ChangePasswordPage.jsx` — auth
- `pages/Landing.jsx` — marketing/landing page
- `components/admin/` — admin dashboard widgets (KnowledgeBasePanel, StatCard, CommandPalette, OnboardingCard, etc.)
- `components/ui/` — shared shadcn/ui-style component library
- `Accessibility.jsx`, `ErrorSystem.jsx` — accessibility support + error handling

## Repository

- `backend/` — FastAPI service, multi-tenant chat/application logic
- `frontend/` — chat widget + admin dashboard
