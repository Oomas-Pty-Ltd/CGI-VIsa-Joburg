# Seva Setu Bot - Complete Documentation

## Overview
Seva Setu Bot is a multi-channel consular automation platform for the Consulate General of India, Johannesburg. It serves Indian and South African citizens with 24/7 AI-powered assistance.

---

## Table of Contents
1. [Architecture](#architecture)
2. [Features](#features)
3. [API Reference](#api-reference)
4. [Integrations](#integrations)
5. [Templates](#templates)
6. [Testing](#testing)
7. [Deployment](#deployment)

---

## Architecture

### Tech Stack
| Component | Technology |
|-----------|------------|
| Frontend | React, Tailwind CSS, Shadcn UI |
| Backend | FastAPI (Python) |
| Database | MongoDB |
| AI | OpenAI GPT-5.2 (via Emergent LLM) |
| Messaging | Twilio (WhatsApp), Facebook Messenger |
| Monitoring | Custom monitoring service |

### Directory Structure
```
/app/
├── backend/
│   ├── server.py              # Main FastAPI app
│   ├── consular_routes.py     # Chat endpoints
│   ├── whatsapp_routes.py     # WhatsApp integration
│   ├── facebook_routes.py     # Facebook integration
│   ├── template_routes.py     # Template management
│   ├── monitoring_routes.py   # Health & metrics
│   └── auth_routes.py         # Authentication
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── ConsularBot.jsx    # Full bot interface
│   │   │   └── Landing.jsx        # Landing page
│   │   ├── components/
│   │   │   └── ChatWidget.jsx     # Embeddable widget
│   │   └── config/
│   │       └── botMessages.js     # Configurable messages
│   └── public/
│       └── embed.js               # Widget embed script
```

---

## Features

### 1. Web Chat (Full Interface)
- **URL:** `/consular`
- Full-featured chat with progress stepper
- Document upload, camera, voice input
- Multi-language support (50+ languages)

### 2. Embeddable Widget
- **Demo:** `/widget-demo`
- Lightweight chat bubble for embedding on any website
- Concise AI responses
- Easy installation with single script tag

### 3. WhatsApp Integration
- **Webhook:** `/api/whatsapp/webhook`
- Twilio-powered messaging
- AI-powered automatic responses
- Message history tracking

### 4. Facebook Messenger
- **Webhook:** `/api/facebook/webhook`
- Messenger API integration
- Automatic AI responses
- Conversation management

### 5. Template Management
- Email, WhatsApp, Alert templates
- Variable substitution
- User-created custom templates
- Multi-language support

---

## API Reference

### Chat Endpoints

#### Full Chat (Web)
```
POST /api/consular/chat
Content-Type: application/json

{
  "message": "What is OCI?",
  "session_id": "optional-session-id",
  "enable_voice": false
}
```

#### Widget Chat (Concise)
```
POST /api/consular/chat-widget
Content-Type: application/json

{
  "message": "What is OCI?",
  "session_id": "optional-session-id"
}
```

### WhatsApp Endpoints

#### Status Check
```
GET /api/whatsapp/status
```

#### Send Message
```
POST /api/whatsapp/send
Content-Type: application/json

{
  "to_number": "+27123456789",
  "message": "Hello from Seva Setu"
}
```

#### Webhook (for Twilio)
```
POST /api/whatsapp/webhook
Content-Type: application/x-www-form-urlencoded

From=whatsapp:+27123456789
To=whatsapp:+14155238886
Body=Hello
MessageSid=SM123456
```

### Facebook Endpoints

#### Webhook Verification
```
GET /api/facebook/webhook?hub.mode=subscribe&hub.verify_token=seva_setu_verify_token&hub.challenge=CHALLENGE_STRING
```

#### Webhook (for Messages)
```
POST /api/facebook/webhook
Content-Type: application/json

{
  "object": "page",
  "entry": [...]
}
```

### Template Endpoints

#### List Templates
```
GET /api/templates/?category=email&language=en
```

#### Create Template
```
POST /api/templates/
Content-Type: application/json

{
  "name": "My Template",
  "category": "email",
  "subject": "Hello {{user_name}}",
  "body": "Dear {{user_name}}, ...",
  "variables": ["user_name"],
  "language": "en"
}
```

#### Render Template
```
POST /api/templates/render
Content-Type: application/json

{
  "template_id": "template-uuid",
  "variables": {
    "user_name": "John"
  }
}
```

### Monitoring Endpoints

```
GET /api/monitoring/health     # Quick health check
GET /api/monitoring/status     # Detailed status
GET /api/monitoring/metrics    # Performance metrics
GET /api/monitoring/history    # Historical data
```

---

## Integrations

### WhatsApp (Twilio)

#### Setup
1. Create Twilio account at https://console.twilio.com
2. Navigate to Messaging > Try WhatsApp
3. Get Account SID and Auth Token
4. Configure in `.env`:
```
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_token
TWILIO_WHATSAPP_NUMBER=+14155238886
```

5. Configure Webhook URL in Twilio Console:
```
When a message comes in: https://your-domain.com/api/whatsapp/webhook
Status callback URL: https://your-domain.com/api/whatsapp/status-callback
```

### Facebook Messenger

#### Setup
1. Create Facebook App at https://developers.facebook.com
2. Add Messenger product
3. Generate Page Access Token
4. Configure in `.env`:
```
FB_PAGE_ACCESS_TOKEN=your_token
FB_VERIFY_TOKEN=seva_setu_verify_token
FB_APP_SECRET=your_secret
```

5. Configure Webhook URL in Facebook App:
```
Callback URL: https://your-domain.com/api/facebook/webhook
Verify Token: seva_setu_verify_token
```

---

## Templates

### Default Templates

| Name | Category | Language |
|------|----------|----------|
| Welcome Email | email | en |
| Application Status Update | email | en |
| Appointment Reminder | email | en |
| WhatsApp Welcome | whatsapp | en |
| WhatsApp Appointment Reminder | whatsapp | en |
| System Alert - High Load | alert | en |
| Fraud Alert | alert | en |
| स्वागत ईमेल | email | hi |

### Variables
Templates support variable substitution using `{{variable_name}}` syntax:
- `{{user_name}}` - User's name
- `{{appointment_date}}` - Appointment date
- `{{service_type}}` - Service type
- `{{status}}` - Application status

---

## Testing

### Test Credentials
- **Super Admin:** `superadmin@sarthak.ai` / `Admin@2025`
- **Bot URL:** https://consular-bot-1.preview.emergentagent.com/consular
- **Widget Demo:** https://consular-bot-1.preview.emergentagent.com/widget-demo

### Test Commands

#### WhatsApp (Mock Mode)
```bash
curl -X POST "https://consular-bot-1.preview.emergentagent.com/api/whatsapp/webhook" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+27123456789&To=whatsapp:+14155238886&Body=Hello&MessageSid=SM123"
```

#### Facebook (Mock Mode)
```bash
curl -X POST "https://consular-bot-1.preview.emergentagent.com/api/facebook/webhook" \
  -H "Content-Type: application/json" \
  -d '{"object":"page","entry":[{"messaging":[{"sender":{"id":"123"},"message":{"text":"Hello"}}]}]}'
```

#### Templates
```bash
curl "https://consular-bot-1.preview.emergentagent.com/api/templates/"
```

---

## Deployment

### Environment Variables
```env
# Required
MONGO_URL=mongodb://localhost:27017
DB_NAME=seva_setu
EMERGENT_LLM_KEY=your_key

# WhatsApp (Twilio)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=

# Facebook
FB_PAGE_ACCESS_TOKEN=
FB_VERIFY_TOKEN=
FB_APP_SECRET=

# Monitoring
SMTP_HOST=smtp.gmail.com
SMTP_USER=
SMTP_PASSWORD=
ALERT_EMAILS=
```

### Production Checklist
- [ ] Configure Twilio credentials
- [ ] Configure Facebook credentials
- [ ] Set up SMTP for email alerts
- [ ] Configure webhook URLs in Twilio/Facebook
- [ ] Set up SSL/TLS
- [ ] Configure monitoring alerts
- [ ] Test all channels

---

## Widget Embedding

### Installation
Add this code to your website before `</body>`:

```html
<script src="https://consular-bot-1.preview.emergentagent.com/embed.js"></script>
<script>
  SevaSetu.init({
    position: 'bottom-right',
    primaryColor: '#E06F2C',
    headerTitle: 'Seva Setu Assistant',
    greeting: '🙏 Namaste! How can I help you?'
  });
</script>
```

### Customization Options
| Option | Default | Description |
|--------|---------|-------------|
| position | 'bottom-right' | Widget position |
| primaryColor | '#E06F2C' | Brand color |
| headerTitle | 'Seva Setu Assistant' | Header title |
| headerSubtitle | 'Consulate General of India' | Header subtitle |
| greeting | 'Namaste! How can I help you?' | Welcome message |
| placeholder | 'Type your question...' | Input placeholder |

---

## Support

For technical support or integration assistance:
- **Email:** cons.joburg@mea.gov.in
- **Emergency:** +27 6830 38144
- **Website:** https://www.cgijohannesburg.gov.in
