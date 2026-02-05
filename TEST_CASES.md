# Seva Setu Bot - Test Cases Document

## Test Environment
- **Preview URL:** https://consular-genius.preview.emergentagent.com
- **Super Admin:** `superadmin@sarthak.ai` / `Admin@2025`
- **API Base:** https://consular-genius.preview.emergentagent.com/api

---

## 1. Web Chat Tests

### TC-WEB-001: Landing Page Load
- **Steps:** Navigate to `/`
- **Expected:** Landing page loads with "Start Consular Application" button
- **Status:** ✅ PASS

### TC-WEB-002: Bot Interface Load
- **Steps:** Navigate to `/consular`
- **Expected:** Bot interface with avatar, progress stepper, chat area loads
- **Status:** ✅ PASS

### TC-WEB-003: Send Text Message
- **Steps:** Type message → Click Send
- **Expected:** Message appears, AI response received within 15 seconds
- **Status:** ✅ PASS

### TC-WEB-004: Hindi Language Support
- **Steps:** Send message in Hindi: "पासपोर्ट कैसे बनवाएं?"
- **Expected:** Response in Hindi with relevant information
- **Status:** ✅ PASS

### TC-WEB-005: Voice Toggle
- **Steps:** Toggle voice switch ON → Send message
- **Expected:** AI response is spoken via TTS
- **Status:** ✅ PASS

### TC-WEB-006: File Upload
- **Steps:** Click file upload → Select PDF/Image
- **Expected:** File uploads successfully, bot acknowledges
- **Status:** ✅ PASS

---

## 2. Widget Tests

### TC-WID-001: Widget Button Visible
- **Steps:** Navigate to `/widget-demo`
- **Expected:** Orange chat button visible in bottom-right
- **Status:** ✅ PASS

### TC-WID-002: Widget Opens
- **Steps:** Click widget button
- **Expected:** Chat window opens with greeting message
- **Status:** ✅ PASS

### TC-WID-003: Widget Chat Response
- **Steps:** Type "What is OCI?" → Send
- **Expected:** Concise response (< 300 chars)
- **Status:** ✅ PASS

### TC-WID-004: Widget Minimize/Close
- **Steps:** Click minimize → Click button again
- **Expected:** Widget minimizes and reopens correctly
- **Status:** ✅ PASS

---

## 3. WhatsApp Integration Tests

### TC-WA-001: Webhook Status
- **Endpoint:** GET /api/whatsapp/status
- **Expected:** 
```json
{
  "status": "active",
  "webhook_url": "/api/whatsapp/webhook"
}
```
- **Status:** ✅ PASS

### TC-WA-002: Incoming Message (Mock)
- **Endpoint:** POST /api/whatsapp/webhook
- **Payload:** `From=whatsapp:+27123456789&Body=What is OCI?&MessageSid=SM123`
- **Expected:** TwiML response with AI-generated answer
- **Status:** ✅ PASS

### TC-WA-003: Send Message (Mock)
- **Endpoint:** POST /api/whatsapp/send
- **Payload:** `{"to_number": "+27123456789", "message": "Hello"}`
- **Expected:** Success response with mock message_sid
- **Status:** ✅ PASS

### TC-WA-004: Conversation History
- **Endpoint:** GET /api/whatsapp/conversations
- **Expected:** List of conversations with last message
- **Status:** ✅ PASS

### TC-WA-005: Message Retrieval
- **Endpoint:** GET /api/whatsapp/messages/{phone_number}
- **Expected:** List of messages for phone number
- **Status:** ✅ PASS

---

## 4. Facebook Messenger Tests

### TC-FB-001: Webhook Status
- **Endpoint:** GET /api/facebook/status
- **Expected:**
```json
{
  "status": "active",
  "webhook_url": "/api/facebook/webhook"
}
```
- **Status:** ✅ PASS

### TC-FB-002: Webhook Verification
- **Endpoint:** GET /api/facebook/webhook?hub.mode=subscribe&hub.verify_token=seva_setu_verify_token&hub.challenge=123
- **Expected:** Returns challenge "123"
- **Status:** ✅ PASS

### TC-FB-003: Incoming Message (Mock)
- **Endpoint:** POST /api/facebook/webhook
- **Payload:**
```json
{
  "object": "page",
  "entry": [{
    "messaging": [{
      "sender": {"id": "123"},
      "message": {"text": "Hello", "mid": "mid123"}
    }]
  }]
}
```
- **Expected:** 200 OK, message stored in database
- **Status:** ✅ PASS

### TC-FB-004: Send Message (Mock)
- **Endpoint:** POST /api/facebook/send
- **Payload:** `{"recipient_id": "123", "message": "Hello"}`
- **Expected:** Success response with mock message_id
- **Status:** ✅ PASS

---

## 5. Template Management Tests

### TC-TMP-001: List Templates
- **Endpoint:** GET /api/templates/
- **Expected:** Array of templates with count
- **Status:** ✅ PASS

### TC-TMP-002: List Categories
- **Endpoint:** GET /api/templates/categories
- **Expected:** Categories (email, whatsapp, alert) with counts
- **Status:** ✅ PASS

### TC-TMP-003: Filter by Category
- **Endpoint:** GET /api/templates/?category=email
- **Expected:** Only email templates returned
- **Status:** ✅ PASS

### TC-TMP-004: Create Template
- **Endpoint:** POST /api/templates/
- **Payload:**
```json
{
  "name": "Test Template",
  "category": "custom",
  "body": "Hello {{user_name}}"
}
```
- **Expected:** Template created with ID
- **Status:** ✅ PASS

### TC-TMP-005: Render Template
- **Endpoint:** POST /api/templates/render
- **Payload:** `{"template_id": "uuid", "variables": {"user_name": "John"}}`
- **Expected:** Rendered body with variables replaced
- **Status:** ✅ PASS

### TC-TMP-006: Save as Template
- **Endpoint:** POST /api/templates/save-as-template
- **Expected:** New template saved with auto-detected variables
- **Status:** ✅ PASS

---

## 6. Monitoring Tests

### TC-MON-001: Health Check
- **Endpoint:** GET /api/monitoring/health
- **Expected:** Status "healthy", mongodb/llm status
- **Status:** ✅ PASS

### TC-MON-002: Detailed Status
- **Endpoint:** GET /api/monitoring/status
- **Expected:** CPU, memory, disk, uptime metrics
- **Status:** ✅ PASS

### TC-MON-003: Performance Metrics
- **Endpoint:** GET /api/monitoring/metrics
- **Expected:** Comprehensive metrics with thresholds
- **Status:** ✅ PASS

---

## 7. Authentication Tests

### TC-AUTH-001: Super Admin Login
- **Endpoint:** POST /api/auth/super-admin/login
- **Credentials:** `superadmin@sarthak.ai` / `Admin@2025`
- **Expected:** JWT token returned
- **Status:** ✅ PASS

### TC-AUTH-002: Invalid Login
- **Endpoint:** POST /api/auth/super-admin/login
- **Credentials:** `wrong@email.com` / `wrongpass`
- **Expected:** 401 Unauthorized
- **Status:** ✅ PASS

### TC-AUTH-003: User Registration
- **Endpoint:** POST /api/auth/user/register
- **Payload:** `{"email": "test@test.com", "password": "Test@123"}`
- **Expected:** User created, token returned
- **Status:** ✅ PASS

---

## 8. Admin Dashboard Tests

### TC-ADM-001: Super Admin Dashboard Access
- **Steps:** Login → Navigate to /super-admin/dashboard
- **Expected:** Dashboard loads with company management
- **Status:** ✅ PASS

### TC-ADM-002: Create Company
- **Steps:** Click Add Company → Fill form → Submit
- **Expected:** Company created successfully
- **Status:** ✅ PASS

---

## Test Summary

| Category | Total | Passed | Failed |
|----------|-------|--------|--------|
| Web Chat | 6 | 6 | 0 |
| Widget | 4 | 4 | 0 |
| WhatsApp | 5 | 5 | 0 |
| Facebook | 4 | 4 | 0 |
| Templates | 6 | 6 | 0 |
| Monitoring | 3 | 3 | 0 |
| Authentication | 3 | 3 | 0 |
| Admin | 2 | 2 | 0 |
| **TOTAL** | **33** | **33** | **0** |

---

## Notes

### Mock Mode
WhatsApp and Facebook integrations run in **MOCK MODE** without credentials. To test with real integrations:
1. Add Twilio credentials to `.env`
2. Add Facebook credentials to `.env`
3. Configure webhook URLs in respective consoles

### Known Limitations
1. Twilio sandbox has rate limits (1 msg/3 sec)
2. Facebook requires business verification for production
3. Voice TTS requires ElevenLabs API key for full functionality
