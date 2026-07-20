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

## Repository

- `backend/` — FastAPI service, multi-tenant chat/application logic
- `frontend/` — chat widget + admin dashboard
