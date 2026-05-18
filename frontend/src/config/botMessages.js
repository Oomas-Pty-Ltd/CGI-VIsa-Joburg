/**
 * ====================================================================
 * SEVA SETU BOT - MESSAGE CONFIGURATION
 * ====================================================================
 * 
 * This file contains all configurable messages, greetings, and warnings
 * that are displayed in the Seva Setu Bot interface.
 * 
 * TO UPDATE MESSAGES:
 * 1. Edit the relevant section below
 * 2. Save the file
 * 3. The changes will reflect automatically (hot reload)
 * 
 * SECTIONS:
 * - BOT_CONFIG: Title and basic info
 * - GREETING_MESSAGE: Initial welcome message
 * - ADVISORY_MESSAGES: Important warnings and alerts
 * - LANGUAGE_BADGES: Supported languages display
 * ====================================================================
 */

// =====================================================================
// BOT CONFIGURATION - Basic bot information
// =====================================================================
export const BOT_CONFIG = {
  title: "Team Bharat in South Africa Welcomes you",
  subtitle: "🙏 Namaste",
  tagline: "Here to help you, always!",
  organization: "Consulate General of India",
  location: "Johannesburg, South Africa",
};

// =====================================================================
// GREETING MESSAGE - Initial welcome shown when bot loads
// =====================================================================
export const GREETING_MESSAGE = `🙏 नमस्ते भाईयो और बहनो!

मैं हूं "सेवा सेतु स्वचालित सहायक (बॉट)", आपकी सेवा में सदैव तत्पर।

🗣 भारतीय काउंसलर सर्विसेज के साथ हाज़िर हूं। बताएं, मैं आपकी किस प्रकार सहायता कर सकता हूं? आज मैं आपकी मदद करने में सक्षम हूं।

Namaste, brothers and sisters!

I am "Seva Setu Automated Assistant (Bot)", always ready to serve you.

🗣 Here to assist with your Indian consular service queries. Please let me know how I can help you today. I am fully equipped to assist you.`;

// =====================================================================
// ADVISORY MESSAGES - Important warnings and alerts
// Update these as needed. Set 'active: true' to display, 'active: false' to hide
// =====================================================================
export const ADVISORY_MESSAGES = [
  {
    id: "fraud_warning_1",
    active: true,
    type: "warning", // warning, info, alert
    title: "Important Advisory from the Consulate General of India, Johannesburg",
    content: `The Consulate does not make phone calls demanding money for fines, penalties, or any other reason. It is not within our mandate to conduct criminal investigations.

Do not engage with such callers under any circumstance.

• Do not share any personal or financial information. • If you receive a suspicious call, note the caller's number and any details. • Report it immediately to your local police station.

Be vigilant. Stay safe.`
  },
  {
    id: "fraud_alert_spoofing",
    active: true,
    type: "alert", // warning, info, alert
    title: "🗣 Fraud Alert: Extortion Calls Using Spoofed Numbers",
    content: `It has come to our attention that certain individuals are fraudulently spoofing the Consulate General's phone numbers to contact persons of Indian origin. These calls attempt to intimidate recipients with false legal threats and demand payments, claiming affiliation with the Consulate General or Government of India agencies.

Please be advised:

• No representative of the Consulate General will call to request payments for any governmental purpose. • If you receive such a call, note the caller's details and report the incident to your local police immediately.`
  }
];

// =====================================================================
// LANGUAGE BADGES - Languages displayed on the bot interface
// =====================================================================
export const SUPPORTED_LANGUAGES = [
  "English", "Hindi", "Bengali", "Marathi", "Telugu", "Tamil",
  "Gujarati", "Urdu", "Kannada", "Odia", "Malayalam", "Punjabi",
  "Assamese", "Maithili", "Sanskrit", "Santali", "Kashmiri", "Nepali",
  "Sindhi", "Dogri", "Konkani", "Manipuri", "Bodo", "Marwari",
  "isiZulu", "isiXhosa", "Afrikaans", "Sepedi", "Setswana", "Sesotho",
  "Xitsonga", "siSwati", "Tshivenda", "isiNdebele",
  "Arabic", "French", "Swahili", "Hausa", "Yoruba", "Igbo",
  "Amharic", "Oromo"
];

// =====================================================================
// CONTACT INFORMATION
// =====================================================================
export const CONTACT_INFO = {
  emergency: "+27 6830 38144",
  email: "cons.joburg@mea.gov.in",
  website: "https://www.cgijohannesburg.gov.in"
};
