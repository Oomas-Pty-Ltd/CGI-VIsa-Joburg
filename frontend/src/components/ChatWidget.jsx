import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import axios from 'axios';
// botMessages.js is kept as a historical reference but NO content from it
// is shown at runtime — tenant config (or empty defaults) replace everything.
import { fetchBranding, getWidgetTokens } from '../lib/widgetConfig';
import './ChatWidget.css';

// Module-level constant — resolved once at import time, used by every
// inline style across the widget. Tenants override individual keys via
// the embed script tag's data-widget-tokens attribute; see widgetConfig.js.
const T = getWidgetTokens();

// All links rendered inside chat markdown must open in a new tab.
const MD_COMPONENTS = {
  a: ({ node, ...props }) => (
    <a {...props} target="_blank" rel="noopener noreferrer" />
  ),
};

// ── Inline SVG icons ───────────────────────────────────────────────────────────
// style prop overrides host-page CSS resets (e.g. Bootstrap/Tailwind svg{max-width:100%})
const _svgStyle = (size) => ({ display:'inline-block', width:size, height:size, minWidth:size, minHeight:size, maxWidth:'none', maxHeight:'none', flexShrink:0, verticalAlign:'middle', overflow:'visible' });
const MicIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" style={_svgStyle(size)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
    <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
    <line x1="12" x2="12" y1="19" y2="22" />
  </svg>
);
const CameraIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" style={_svgStyle(size)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
    <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" />
    <circle cx="12" cy="13" r="3" />
  </svg>
);
const SendIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" style={_svgStyle(size)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
    <path d="m22 2-7 20-4-9-9-4Z" />
    <path d="M22 2 11 13" />
  </svg>
);
const FileTextIcon = ({ size = 20, className = '' }) => (
  <svg xmlns="http://www.w3.org/2000/svg" style={_svgStyle(size)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
    <path d="M14 2v4a2 2 0 0 0 2 2h4" />
    <path d="M10 9H8" />
    <path d="M16 13H8" />
    <path d="M16 17H8" />
  </svg>
);

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';
const API = `${API_BASE}/api`;

// Used as the initial value + fallback if the tenant hasn't set bot_avatar_url
// (or while the /widget-config fetch is in flight). Per-tenant override comes
// from the backend `tenant_bot_config.bot_avatar_url`.
const BOT_IMAGE = 'https://www.image2url.com/r2/default/images/1777573167951-14d72ab0-5694-47e9-91f4-318ff86d81c1.jpeg?v=2';
const DEFAULT_BOT_NAME = '';
const ALL_LANGS = [
  { code: 'en',  name: 'English',                flag: '🇬🇧' },
  { code: 'hi',  name: 'हिंदी (Hindi)',            flag: '🇮🇳' },
  { code: 'bn',  name: 'বাংলা (Bengali)',           flag: '🇮🇳' },
  { code: 'mr',  name: 'मराठी (Marathi)',           flag: '🇮🇳' },
  { code: 'te',  name: 'తెలుగు (Telugu)',           flag: '🇮🇳' },
  { code: 'ta',  name: 'தமிழ் (Tamil)',             flag: '🇮🇳' },
  { code: 'gu',  name: 'ગુજરાતી (Gujarati)',        flag: '🇮🇳' },
  { code: 'ur',  name: 'اردو (Urdu)',               flag: '🇮🇳' },
  { code: 'kn',  name: 'ಕನ್ನಡ (Kannada)',           flag: '🇮🇳' },
  { code: 'ml',  name: 'മലയാളം (Malayalam)',        flag: '🇮🇳' },
  { code: 'pa',  name: 'ਪੰਜਾਬੀ (Punjabi)',          flag: '🇮🇳' },
  { code: 'or',  name: 'ଓଡ଼ିଆ (Odia)',              flag: '🇮🇳' },
  { code: 'as',  name: 'অসমীয়া (Assamese)',         flag: '🇮🇳' },
  { code: 'ne',  name: 'नेपाली (Nepali)',            flag: '🇮🇳' },
  { code: 'zu',  name: 'isiZulu',                   flag: '🇿🇦' },
  { code: 'xh',  name: 'isiXhosa',                  flag: '🇿🇦' },
  { code: 'af',  name: 'Afrikaans',                 flag: '🇿🇦' },
  { code: 'st',  name: 'Sesotho',                   flag: '🇿🇦' },
  { code: 'tn',  name: 'Setswana',                  flag: '🇿🇦' },
  { code: 'ar',  name: 'العربية (Arabic)',           flag: '🇸🇦' },
  { code: 'fr',  name: 'Français (French)',          flag: '🇫🇷' },
  { code: 'sw',  name: 'Kiswahili (Swahili)',        flag: '🇹🇿' },
];

const SPEECH_LANG_MAP = {
  en: 'en-IN', hi: 'hi-IN', bn: 'bn-IN', mr: 'mr-IN', te: 'te-IN',
  ta: 'ta-IN', gu: 'gu-IN', ur: 'ur-IN', kn: 'kn-IN', or: 'or-IN',
  ml: 'ml-IN', pa: 'pa-IN', as: 'as-IN', ne: 'ne-NP',
  zu: 'zu-ZA', xh: 'xh-ZA', af: 'af-ZA', st: 'st-ZA', tn: 'af-ZA',
  ar: 'ar-SA', fr: 'fr-FR', sw: 'sw-KE',
};

const LANG_PLACEHOLDERS = {
  en:  'Type your message ...',
  hi:  'अपना प्रश्न हिंदी या English में लिखें...',
  bn:  'আপনার প্রশ্ন বাংলায় বা ইংরেজিতে লিখুন...',
  mr:  'तुमचा प्रश्न मराठी किंवा English मध्ये टाइप करा...',
  te:  'మీ ప్రశ్నను తెలుగులో లేదా English లో టైప్ చేయండి...',
  ta:  'உங்கள் கேள்வியை தமிழில் அல்லது ஆங்கிலத்தில் தட்டச்சு செய்யுங்கள்...',
  gu:  'તમારો પ્રશ્ન ગુજરાતી અથવા English માં ટાઇપ કરો...',
  ur:  'اپنا سوال اردو یا انگریزی میں لکھیں...',
  kn:  'ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಕನ್ನಡ ಅಥವಾ English ನಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ...',
  ml:  'നിങ്ങളുടെ ചോദ്യം മലയാളത്തിൽ അല്ലെങ്കിൽ ഇംഗ്ലീഷിൽ ടൈപ്പ് ചെയ്യൂ...',
  pa:  'ਆਪਣਾ ਸਵਾਲ ਪੰਜਾਬੀ ਜਾਂ English ਵਿੱਚ ਲਿਖੋ...',
  or:  'ଆପଣଙ୍କ ପ୍ରଶ୍ନ ଓଡ଼ିଆ ବା English ରେ ଟାଇପ୍ କରନ୍ତୁ...',
  as:  'আপোনাৰ প্ৰশ্ন অসমীয়া বা English ত লিখক...',
  ne:  'आफ्नो प्रश्न नेपाली वा English मा टाइप गर्नुहोस्...',
  ar:  'اكتب سؤالك باللغة العربية أو الإنجليزية...',
  fr:  'Tapez votre message en français ou en anglais...',
  sw:  'Andika ujumbe wako kwa Kiswahili au Kiingereza...',
  zu:  'Bhala umbuzo wakho ngeZulu noma ngeNgisi...',
  xh:  'Bhala umbuzo wakho ngesiXhosa okanye ngesiNgesi...',
  af:  'Tik jou vraag in Afrikaans of Engels...',
  st:  'Ngola potso ea hau ka Sesotho kapa Senyesemane...',
  tn:  'Kwala potso ya gago ka Setswana kgotsa Sekgoa...',
};

// Greetings (English + common Indian/SA/Arabic/French) — whole-message match.
// Allows trailing punctuation/emoji and a few optional fillers ("hi there", "good morning sir").
const GREETING_PATTERN = /^\s*(hi|hii+|hey+|hello+|hola|yo|howdy|greetings|namaste|namaskar|namaskaram|salaam|salam|salam alaikum|assalam(?:u)? ?alaikum|vanakkam|sat sri akal|adab|pranam|jai hind|good\s*(morning|afternoon|evening|day)|bonjour|sawubona|molo|hallo|dumela|sanibonani)\b[\s\W]*(there|sir|madam|ma'am|bot|seva|setu|team)?[\s\W]*$/i;
// Neutral fallback when the tenant hasn't configured a greeting in bot_config.
const DEFAULT_GREETING_REPLY = "Hello! How can I help you today? Pick a service below or type your question.";

function timeNow() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function dataUrlToFile(dataUrl, filename = 'photo.jpg') {
  const [header, data] = dataUrl.split(',');
  const mime = header.match(/:(.*?);/)[1];
  const bytes = atob(data);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new File([arr], filename, { type: mime });
}

// Last-resort emoji for legacy service_keys when the tenant hasn't set
// `tenant_services.emoji`. Per-tenant overrides (the admin emoji field on
// each service row) take precedence — see the mapper in fetchBranding.
const SERVICE_EMOJI_FALLBACK = {
  passport: '🛂', visa: '✈️', pcc: '📋',
  ec_death: '📄', marriage: '💍', misc: '🗂️',
  appointment: '📅',
};

// Welcome messages are built entirely from tenant config.
// If a tenant has not configured a greeting or advisories, we show a neutral
// default — never CGI-specific copy from botMessages.js.
const GENERIC_GREETING = "Hello! How can I help you today? Pick a service below or type your question.";

function buildWelcomeMessages(opts = {}) {
  const greeting = opts.greeting || GENERIC_GREETING;
  const advisories = (opts.advisories && opts.advisories.length)
    ? opts.advisories
    : [];
  const msgs = [
    { id: 'welcome', role: 'bot', html: false, content: greeting, time: timeNow() }
  ];
  advisories.forEach((adv, idx) => {
    msgs.push({
      id: adv.id || `adv_${idx}`,
      role: 'advisory',
      type: adv.type || 'info',
      title: adv.title || '',
      content: adv.content || '',
      time: timeNow(),
    });
  });
  msgs.push({ id: `seva_tabs_${Date.now()}`, role: 'seva_service_tabs' });
  return msgs;
}

// ── TypeA card: gov portal link + reference input ─────────────────────────
const TypeACard = ({ msg, onFinalize }) => {
  const [govRef, setGovRef] = React.useState('');
  const [submitted, setSubmitted] = React.useState(false);
  const [loading, setLoading] = React.useState(false);

  const handleSubmit = async () => {
    if (!govRef.trim()) return;
    setLoading(true);
    try {
      await onFinalize(msg.service?.application_id, govRef);
      setSubmitted(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="seva-svc-card">
      <div className="seva-svc-card-row">
        <span className="seva-svc-label">Reference</span>
        <span className="seva-svc-refid">{msg.service?.reference_id}</span>
      </div>
      {(msg.service?.documents_required || []).length > 0 && (
        <div>
          <p className="seva-svc-docs-title">Documents Required</p>
          <ul className="seva-svc-docs-list">
            {msg.service.documents_required.map((d, i) => (
              <li key={i}><span className="seva-svc-dot">•</span>{d}</li>
            ))}
          </ul>
        </div>
      )}
      {msg.govUrl && (
        <a
          href={msg.govUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="seva-svc-primary-btn"
        >
          🔗 Open Application Portal
        </a>
      )}
      {!submitted ? (
        <div>
          <p className="seva-svc-gov-hint">
            {msg.govUrl
              ? 'After completing the application on the portal, enter your reference or application number below to record it and receive your PDF:'
              : 'Enter your reference or application number below to record it and receive your PDF:'}
          </p>
          <div className="seva-svc-input-row">
            <input
              type="text"
              placeholder="Your application / reference number"
              value={govRef}
              onChange={e => setGovRef(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              className="seva-svc-input"
            />
            <button
              onClick={handleSubmit}
              disabled={loading || !govRef.trim()}
              className="seva-svc-submit-btn"
            >
              {loading ? '…' : 'Submit'}
            </button>
          </div>
        </div>
      ) : (
        <p className="seva-svc-success">✅ Recorded — check your email for the PDF!</p>
      )}
    </div>
  );
};

// ── Service tabs — clickable chips shown under the greeting ────────────────
const ServiceTabs = ({ services, onPick }) => (
  <div className="seva-svc-tabs-card">
    <p className="seva-svc-tabs-title">🏛️ I Can Help You With</p>
    <p className="seva-svc-tabs-hint">Pick a service to see details, or type your question below.</p>
    <div className="seva-svc-tabs-grid">
      {services.map(svc => (
        <button
          key={svc.key}
          className="seva-svc-tab"
          onClick={() => onPick(svc)}
          type="button"
        >
          <span className="seva-svc-tab-emoji">{svc.emoji}</span>
          <span className="seva-svc-tab-name">{svc.name}</span>
        </button>
      ))}
    </div>
  </div>
);

// ── Service info card — shown when user asks about a service ──────────────
// INFO services get a distinct lightweight variant (no docs block, optional
// single CTA) so users see at a glance that this is reference content, not
// an application start.
const ServiceInfoCard = ({ svc }) => {
  if (svc.category === 'INFO') {
    return <WidgetInfoCard svc={svc} />;
  }
  return (
    <div className="seva-svc-info-card">
      <div className="seva-svc-info-header">
        <span className="seva-svc-emoji">{svc.emoji}</span>
        <h3 className="seva-svc-name">{svc.name}</h3>
        {svc.category === 'TYPE_A' && (
          <span className="seva-svc-badge">Gov Portal</span>
        )}
      </div>
      {svc.description && <p className="seva-svc-desc">{svc.description}</p>}
      {svc.documents && svc.documents.length > 0 && (
        <div>
          <p className="seva-svc-docs-title">Required Documents</p>
          <ul className="seva-svc-docs-list">
            {svc.documents.map((doc, i) => (
              <li key={i}><span className="seva-svc-dot">•</span>{doc}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

const WidgetInfoCard = ({ svc }) => {
  const sections = svc.info_content?.sections || [];
  const primary  = svc.info_content?.primary_action;
  return (
    <div className="seva-svc-info-card" style={{ borderColor: 'hsl(var(--border))' }}>
      <div className="seva-svc-info-header">
        {svc.emoji && <span className="seva-svc-emoji">{svc.emoji}</span>}
        <h3 className="seva-svc-name">{svc.name}</h3>
        <span className="seva-svc-badge" style={{ background: 'hsl(var(--muted))', color: 'hsl(var(--muted-foreground))' }}>Info</span>
      </div>
      {svc.description && <p className="seva-svc-desc">{svc.description}</p>}
      {sections.map((sec, i) => <WidgetInfoSection key={i} section={sec} />)}
      {primary?.url && primary?.label && (
        <a
          href={primary.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            marginTop: 8,
            padding: '8px 14px',
            background: 'hsl(var(--primary))',
            color: 'hsl(var(--primary-foreground))',
            borderRadius: 8,
            fontSize: 13,
            fontWeight: 600,
            textDecoration: 'none',
            width: '100%',
          }}
        >
          {primary.label}
        </a>
      )}
    </div>
  );
};

const WidgetInfoSection = ({ section }) => {
  const kind = section?.kind || 'text';
  const title = section?.title;
  const titleEl = title ? <p className="seva-svc-docs-title">{title}</p> : null;

  if (kind === 'bullets') {
    return (
      <div>
        {titleEl}
        <ul className="seva-svc-docs-list">
          {(section.items || []).map((it, i) => (
            <li key={i}><span className="seva-svc-dot">•</span>{it}</li>
          ))}
        </ul>
      </div>
    );
  }

  if (kind === 'callout') {
    const tone = (section.tone || 'info').toLowerCase();
    const palette = {
      info:    { bg: 'hsl(var(--primary) / 0.06)', border: 'hsl(var(--primary) / 0.25)' },
      warning: { bg: T.successBg && 'hsl(var(--warning) / 0.10)', border: 'hsl(var(--warning) / 0.30)' },
      success: { bg: 'hsl(var(--success) / 0.10)', border: 'hsl(var(--success) / 0.30)' },
    }[tone] || { bg: 'hsl(var(--primary) / 0.06)', border: 'hsl(var(--primary) / 0.25)' };
    return (
      <div style={{
        borderRadius: 8,
        border: `1px solid ${palette.border}`,
        background: palette.bg,
        padding: '8px 10px',
      }}>
        {title && <p style={{ fontSize: 11, fontWeight: 700, margin: 0, marginBottom: 2 }}>{title}</p>}
        {section.body && <p style={{ fontSize: 12, margin: 0, lineHeight: 1.45 }}>{section.body}</p>}
      </div>
    );
  }

  if (kind === 'links') {
    return (
      <div>
        {titleEl}
        <ul className="seva-svc-docs-list" style={{ listStyle: 'none', paddingLeft: 0 }}>
          {(section.items || []).map((it, i) => (
            <li key={i}>
              <a href={it.url} target="_blank" rel="noopener noreferrer" style={{ color: 'hsl(var(--primary))', fontSize: 12, textDecoration: 'underline', wordBreak: 'break-all' }}>
                {it.label || it.url}
              </a>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  if (kind === 'contact') {
    return (
      <div>
        {titleEl}
        <ul style={{ listStyle: 'none', paddingLeft: 0, margin: 0, fontSize: 12 }}>
          {(section.items || []).map((it, i) => (
            <li key={i} style={{ marginBottom: 2 }}>
              {it.label && <span style={{ fontWeight: 600, marginRight: 4 }}>{it.label}:</span>}
              {it.href
                ? <a href={it.href} style={{ color: 'hsl(var(--primary))', textDecoration: 'underline' }}>{it.value}</a>
                : <span style={{ color: 'hsl(var(--muted-foreground))' }}>{it.value}</span>}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  // text / unknown
  return (
    <div>
      {titleEl}
      {section?.body && <p className="seva-svc-desc" style={{ whiteSpace: 'pre-wrap' }}>{section.body}</p>}
    </div>
  );
};

export default function ChatWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [showTip, setShowTip] = useState(true);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const sessionIdRef = useRef(localStorage.getItem('consular_session_id') || null);
  // Stable per-browser identifier. Sent on every chat request so the
  // session manager can bucket each visitor into their own session — the
  // server previously fell back to a hashed-IP key, so two real users on
  // the same Wi-Fi / NAT would share a session. Persisted in localStorage
  // so a visitor returning later resumes their own thread.
  const visitorIdRef = useRef(
    (() => {
      try {
        let v = localStorage.getItem('widget_visitor_id');
        if (v && v.length >= 8) return v;
        v = (window.crypto && window.crypto.randomUUID)
          ? window.crypto.randomUUID()
          : 'v-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
        localStorage.setItem('widget_visitor_id', v);
        return v;
      } catch {
        // localStorage unavailable (private mode etc.) — fall back to a
        // per-pageload value; visitor "persists" for one tab session.
        return 'v-' + Math.random().toString(36).slice(2);
      }
    })()
  );
  const [isLoading, setIsLoading] = useState(false);

  // Per-tenant branding loaded from /api/consular/widget-config on mount.
  // Defaults match the legacy hardcoded values so the widget renders
  // immediately while the fetch is in flight (and stays usable if it fails).
  const [botName, setBotName] = useState(DEFAULT_BOT_NAME);
  const [botAvatarUrl, setBotAvatarUrl] = useState(BOT_IMAGE);
  // CSS custom-property overrides applied to the widget root. Stays empty
  // until branding loads, then carries --seva-primary / --seva-secondary
  // so the operator's Bot Config colors actually take effect. ChatWidget.css
  // declares the same vars with the legacy hex values as defaults, so the
  // widget renders correctly during the fetch and if the fetch fails.
  const [brandingStyle, setBrandingStyle] = useState({});
  // Tenant-driven chat-chrome copy. Empty strings render the legacy hardcoded
  // values (see fallbacks at the render sites) so an unconfigured tenant
  // still gets a sensible default.
  const [headerTagline, setHeaderTagline] = useState('');
  const [footerCopy, setFooterCopy] = useState('');
  const [orgName, setOrgName] = useState('');
  const [orgShortName, setOrgShortName] = useState('');
  const [tenantGreeting, setTenantGreeting] = useState('');
  const [tenantAdvisories, setTenantAdvisories] = useState([]);
  // Tenant language list — codes the operator has enabled. Empty = all languages.
  // Falls back to ['en'] when branding fetch fails (default_language is 'en').
  const [tenantLanguageCodes, setTenantLanguageCodes] = useState(['en']);
  // Tenant services from /widget-config. Until populated (null), the menu shows nothing.
  const [tenantServices, setTenantServices] = useState(null); // null = still loading
  // Tenant feature toggles (mic gating). Surfaced via widget-config; the
  // defaults preserve legacy behaviour for tenants that haven't set the
  // `features` block on their stored row yet.
  const [tenantFeatures, setTenantFeatures] = useState({
    voice_input: true,
    file_upload: true,
    camera:      true,
  });
  // Per-turn hints from the chat stream's done event. The widget reads
  // these to decide whether to surface the upload + camera affordances
  // for the NEXT user turn — hidden by default so the input bar stays
  // text-only unless the bot has actually asked for a file.
  const [uiHints, setUiHints] = useState({
    expects_upload: false,
    expects_image:  false,
    expects_text:   true,
  });

  useEffect(() => {
    let cancelled = false;
    fetchBranding().then((branding) => {
      if (cancelled) return;
      if (!branding) {
        // Endpoint down — leave defaults in place but populate services with
        // empty array so the menu shows the empty state rather than a spinner.
        setTenantServices([]);
        return;
      }
      if (branding.bot_name) setBotName(branding.bot_name);
      if (branding.bot_avatar_url) setBotAvatarUrl(branding.bot_avatar_url);
      const b = branding.branding || {};
      const style = {};
      if (b.primary_color)   style['--seva-primary']   = b.primary_color;
      if (b.secondary_color) style['--seva-secondary'] = b.secondary_color;
      if (Object.keys(style).length) setBrandingStyle(style);

      if (typeof branding.header_tagline === 'string') setHeaderTagline(branding.header_tagline);
      if (typeof branding.footer_copy === 'string')    setFooterCopy(branding.footer_copy);
      if (branding.org_name)        setOrgName(branding.org_name);
      if (branding.org_short_name)  setOrgShortName(branding.org_short_name);
      if (branding.greeting)        setTenantGreeting(branding.greeting);
      if (Array.isArray(branding.advisories)) setTenantAdvisories(branding.advisories);
      // Tenant features (mic / upload / camera global enables). Default
      // each to true if missing so this is opt-out, not opt-in.
      if (branding.features && typeof branding.features === 'object') {
        setTenantFeatures((prev) => ({ ...prev, ...branding.features }));
      }

      // Language whitelist — only show languages the operator enabled.
      if (Array.isArray(branding.supported_languages) && branding.supported_languages.length > 0) {
        setTenantLanguageCodes(branding.supported_languages.map(l => l.code).filter(Boolean));
      }

      // Reshape services to the {key, name, emoji, category, gov_url, description, documents}
      // shape the rest of the widget already expects.
      const services = Array.isArray(branding.services) ? branding.services : [];
      setTenantServices(services.map((s) => ({
        key:         s.key,
        name:        s.name,
        category:    s.category || 'TYPE_A',
        info_content: (s.info_content && typeof s.info_content === 'object')
          ? s.info_content
          : { sections: [], primary_action: null },
        emoji:       s.emoji || SERVICE_EMOJI_FALLBACK[s.key] || '',
        gov_url:     s.external_url || null,
        description: s.description || '',
        documents:   s.documents || [],
      })));
    });
    return () => { cancelled = true; };
  }, []);

  const [currentLang, setCurrentLang] = useState('en');
  const currentLangRef = useRef('en');
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceOn, setVoiceOn] = useState(true);
  const voiceOnRef = useRef(true);
  const [showCamera, setShowCamera] = useState(false);
  const [cameraStream, setCameraStream] = useState(null);
  const [cameraError, setCameraError] = useState(null);
  const [showLangMenu, setShowLangMenu] = useState(false);
  const isSwitchingLang = false;
  const [docViewModal, setDocViewModal] = useState(null);
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);
  const [showAuthDiscardConfirm, setShowAuthDiscardConfirm] = useState(false);

  const [langToast, setLangToast] = useState('');
  const langToastTimerRef = useRef(null);
  const langBtnRef = useRef(null);
  const [langDropPos, setLangDropPos] = useState({ top: 0, right: 0 });

  // ── Seva Setu Auth State ───────────────────────────────────────────────────
  const [sevaToken, setSevaToken] = useState(() => sessionStorage.getItem('seva_token') || null);
  const sevaTokenRef = useRef(sessionStorage.getItem('seva_token') || null);
  const [sevaUser, setSevaUser] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem('seva_user')) || null; } catch { return null; }
  });
  const [sevaAuthStep, setSevaAuthStep] = useState(null); // null | 'name_email' | 'otp' | 'done'
  const [sevaAuthName, setSevaAuthName] = useState('');
  const [sevaAuthEmail, setSevaAuthEmail] = useState('');
  const [sevaOtpInput, setSevaOtpInput] = useState('');
  const [sevaAuthError, setSevaAuthError] = useState('');
  const [sevaAuthLoading, setSevaAuthLoading] = useState(false);

  // ── Seva Setu Application State ───────────────────────────────────────────
  const [sevaCurrentApp, setSevaCurrentApp] = useState(null);
  const [sevaApps, setSevaApps] = useState([]);
  const [showSevaApps, setShowSevaApps] = useState(false);
  const [sevaSelectedService, setSevaSelectedService] = useState(null);
  const [sevaFormMode, setSevaFormMode] = useState(null); // 'upload' | 'manual' | null
  const [sevaFormFieldIndex, setSevaFormFieldIndex] = useState(0);
  const [sevaFormData, setSevaFormData] = useState({});
  const [sevaFormInput, setSevaFormInput] = useState('');
  const [sevaUploadingDocName, setSevaUploadingDocName] = useState(null);
  const [sevaServices, setSevaServices] = useState({});
  const [sevaDocPreviews, setSevaDocPreviews] = useState({}); // appId → [{id,name,dataUrl,isPdf}]
  const [sevaFormError, setSevaFormError] = useState('');
  const [sevaFormFilePreview, setSevaFormFilePreview] = useState(null); // {dataUrl,name,isPdf}
  const [sevaEditingField, setSevaEditingField] = useState(null); // {key,label} of field being edited in review
  const [sevaEditInput, setSevaEditInput] = useState('');
  const [isApiLoading, setIsApiLoading] = useState(false);
  const lastActivityRef = useRef(Date.now());

  const messagesScrollRef = useRef(null);
  const textareaRef = useRef(null);
  const audioRef = useRef(null);
  const ttsAbortRef = useRef(null);
  const langChangedRef = useRef(false);
  const mediaRecorderRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);
  const cameraOnCaptureRef = useRef(null); // set to fn(dataUrl) to redirect camera capture to form/doc
  const scrollToTopNextRef = useRef(false);

  const stopAudio = useCallback(() => {
    if (ttsAbortRef.current) { ttsAbortRef.current.abort(); ttsAbortRef.current = null; }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    if (window.speechSynthesis) {
      window.speechSynthesis.pause();
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
  }, []);

  useEffect(() => { currentLangRef.current = currentLang; }, [currentLang]);
  useEffect(() => { if (!voiceOn) stopAudio(); }, [voiceOn, stopAudio]);

  // Close lang menu on outside click
  useEffect(() => {
    if (!showLangMenu) return;
    const handler = (e) => {
      if (!e.target.closest('.lang-dropdown') && !e.target.closest('.lang-btn')) {
        setShowLangMenu(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showLangMenu]);

  useEffect(() => {
    const on = () => setIsOnline(true);
    const off = () => setIsOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }, []);

  useEffect(() => {
    return () => { if (cameraStream) cameraStream.getTracks().forEach(t => t.stop()); };
  }, [cameraStream]);

  // Open widget → show welcome (scroll to bottom so service tabs are visible).
  // The effect re-runs when tenant copy arrives, but the messages.length===0
  // guard means we only build the welcome once per open session — we don't
  // overwrite the user's chat history.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      setMessages(buildWelcomeMessages({ greeting: tenantGreeting, advisories: tenantAdvisories }));
    }
  }, [isOpen, messages.length, tenantGreeting, tenantAdvisories]);

  // If the user opened the chat before /widget-config returned, the welcome
  // was built with hardcoded fallbacks. Replace it in place when the tenant
  // copy arrives, but ONLY while the conversation is still on its initial
  // welcome view (no user turns yet). Detected by: every message is one of
  // the welcome-screen roles.
  useEffect(() => {
    if (!isOpen || messages.length === 0) return;
    const initialRoles = new Set(['bot', 'advisory', 'seva_service_tabs']);
    const onWelcome = messages.every((m) => initialRoles.has(m.role));
    if (!onWelcome) return;
    if (!tenantGreeting && (!tenantAdvisories || tenantAdvisories.length === 0)) return;
    setMessages(buildWelcomeMessages({ greeting: tenantGreeting, advisories: tenantAdvisories }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantGreeting, tenantAdvisories]);

  // Load services catalogue on mount
  useEffect(() => {
    fetch(`${API}/seva-setu/services`)
      .then(r => r.json())
      .then(setSevaServices)
      .catch(() => {});
  }, []);

  // Scroll management
  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (messagesScrollRef.current) {
        messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
      }
    });
  }, []);

  useEffect(() => {
    if (scrollToTopNextRef.current) {
      scrollToTopNextRef.current = false;
      requestAnimationFrame(() => {
        if (messagesScrollRef.current) messagesScrollRef.current.scrollTop = 0;
      });
    } else {
      scrollToBottom();
    }
  }, [messages, scrollToBottom]);

  // Inactivity auto-logout — 15 minutes
  useEffect(() => {
    if (!sevaToken) return;
    const touch = () => { lastActivityRef.current = Date.now(); };
    window.addEventListener('mousemove', touch);
    window.addEventListener('keydown', touch);
    window.addEventListener('click', touch);
    const tick = setInterval(() => {
      if (Date.now() - lastActivityRef.current > 15 * 60 * 1000) {
        handleSevaLogout(true);
      }
    }, 30000);
    return () => {
      clearInterval(tick);
      window.removeEventListener('mousemove', touch);
      window.removeEventListener('keydown', touch);
      window.removeEventListener('click', touch);
    };
  }, [sevaToken]); // eslint-disable-line

  // ── TTS via backend with browser fallback ──────────────────────────────────
  const speakText = useCallback((text) => {
    if (!voiceOnRef.current || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const plain = text
      .replace(/\*\*?([^*]+)\*\*?/g, '$1')
      .replace(/#{1,6}\s/g, '')
      .replace(/`[^`]+`/g, '')
      .replace(/•|-\s/g, '')
      .replace(/\n+/g, ' ')
      .trim();
    if (!plain) return;

    const targetLang = SPEECH_LANG_MAP[currentLangRef.current] || 'en-IN';
    const langFamily = targetLang.split('-')[0];
    const allVoices = window.speechSynthesis.getVoices();
    const voice =
      allVoices.find(v => v.lang === targetLang) ||
      allVoices.find(v => v.lang.startsWith(langFamily + '-')) || null;

    const CHUNK = 250;
    const sentences = plain.match(/[^।॥.!?]+[।॥.!?]*/g) || [plain];
    const chunks = [];
    let cur = '';
    for (const s of sentences) {
      if (cur && (cur + s).length > CHUNK) { chunks.push(cur.trim()); cur = s; }
      else cur += s;
    }
    if (cur.trim()) chunks.push(cur.trim());

    chunks.forEach((chunk, i) => {
      const utter = new SpeechSynthesisUtterance(chunk);
      utter.lang = targetLang;
      utter.rate = 0.95;
      if (voice) { utter.voice = voice; utter.lang = voice.lang; }
      if (i === 0) utter.onstart = () => setIsSpeaking(true);
      if (i === chunks.length - 1) {
        utter.onend = () => setIsSpeaking(false);
        utter.onerror = () => setIsSpeaking(false);
      }
      window.speechSynthesis.speak(utter);
    });
  }, []);

  const playAudioAsync = useCallback((base64) => {
    return new Promise(resolve => {
      if (!voiceOnRef.current) { resolve(); return; }
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.onended = null;
        audioRef.current.onerror = null;
        audioRef.current = null;
      }
      setIsSpeaking(true);
      const audio = new Audio(`data:audio/mp3;base64,${base64}`);
      audioRef.current = audio;
      audio.onended = () => { setIsSpeaking(false); audioRef.current = null; resolve(); };
      audio.onerror = () => { setIsSpeaking(false); audioRef.current = null; resolve(); };
      audio.play().catch(() => { setIsSpeaking(false); resolve(); });
    });
  }, []);

  const speakWithBackend = useCallback(async (text) => {
    if (!voiceOnRef.current) return;
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    const plain = text
      .replace(/\*\*?([^*]+)\*\*?/g, '$1')
      .replace(/#{1,6}\s/g, '')
      .replace(/`[^`]+`/g, '')
      .replace(/•|-\s/g, '')
      .replace(/\n+/g, ' ')
      .trim();
    if (!plain) return;

    const CHUNK = 300;
    const sentences = plain.match(/[^।॥.!?]+[।॥.!?]*/g) || [plain];
    const chunks = [];
    let cur = '';
    for (const s of sentences) {
      if (cur && (cur + s).length > CHUNK) { chunks.push(cur.trim()); cur = s; }
      else cur += s;
    }
    if (cur.trim()) chunks.push(cur.trim());

    if (ttsAbortRef.current) ttsAbortRef.current.abort();
    const controller = new AbortController();
    ttsAbortRef.current = controller;

    const fetchChunk = async (chunk) => {
      const res = await fetch(`${API}/consular/tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: chunk, language: currentLangRef.current }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error('TTS failed');
      const data = await res.json();
      return data.audio_base64 || null;
    };

    const audioPromises = chunks.map(c => fetchChunk(c).catch(() => null));
    let anyPlayed = false;
    for (const promise of audioPromises) {
      if (!voiceOnRef.current) break;
      const audio = await promise;
      if (!voiceOnRef.current) break;
      if (audio) { await playAudioAsync(audio); anyPlayed = true; }
    }
    ttsAbortRef.current = null;
    if (!anyPlayed && voiceOnRef.current) speakText(plain);
  }, [playAudioAsync, speakText]);

  // ── Seva Setu API helper ────────────────────────────────────────────────────
  const sevaApi = useCallback(async (method, path, body, token) => {
    const headers = { 'Content-Type': 'application/json' };
    if (token || sevaTokenRef.current) {
      headers['Authorization'] = `Bearer ${token || sevaTokenRef.current}`;
    }
    const res = await fetch(`${API}/seva-setu${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Request failed');
    return data;
  }, []);

  // ── Seva Setu logout ────────────────────────────────────────────────────────
  const handleSevaLogout = useCallback(async (isTimeout = false) => {
    const saveable = messages
      .filter(m => (m.role === 'user' || m.role === 'bot') && m.content)
      .map(m => ({ role: m.role === 'bot' ? 'assistant' : m.role, content: m.content }));
    try {
      await sevaApi('POST', '/auth/logout', { chat_history: saveable });
    } catch {}

    sessionStorage.removeItem('seva_token');
    sessionStorage.removeItem('seva_user');
    sevaTokenRef.current = null;
    setSevaToken(null);
    setSevaUser(null);
    setSevaAuthStep(null);
    setSevaCurrentApp(null);
    setSevaApps([]);
    setShowSevaApps(false);
    setSevaFormMode(null);
    setSevaSelectedService(null);
    setSevaFormData({});
    setSevaFormFieldIndex(0);
    setSevaDocPreviews({});

    localStorage.removeItem('consular_session_id');
    sessionIdRef.current = null;

    scrollToTopNextRef.current = true;
    setMessages(buildWelcomeMessages({ greeting: tenantGreeting, advisories: tenantAdvisories }));
    setInput('');

    if (isTimeout) {
      // show brief inline notice
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'bot', html: false,
        content: '⏱️ You were logged out due to inactivity. Your applications are saved and accessible via your Reference ID.',
        time: timeNow(),
      }]);
    }
  }, [messages, sevaApi, tenantGreeting, tenantAdvisories]);

  // ── Seva auth flow ──────────────────────────────────────────────────────────
  const handleSevaStartAuth = async (service) => {
    setSevaSelectedService(service);
    setSevaAuthError('');

    // Already authenticated — skip name/email/OTP, create application directly
    if (sevaToken) {
      setSevaAuthStep('done');
      setIsApiLoading(true);
      try {
        const appRes = await sevaApi('POST', '/applications', { service_type: service.key });
        setSevaCurrentApp(appRes);
        lastActivityRef.current = Date.now();

        setMessages(prev => [...prev, {
          id: Date.now(), role: 'bot', html: false,
          content: `👋 Welcome back, **${sevaUser?.name}**!\n\nStarting your **${service.name}** application.\n\nReference ID: \`${appRes.reference_id}\``,
          time: timeNow(),
        }]);

        if (appRes.service_category === 'TYPE_A' && appRes.gov_url) {
          setMessages(prev => [...prev,
            { id: Date.now() + 1, role: 'seva_type_a', service: appRes, govUrl: appRes.gov_url },
          ]);
        } else {
          setMessages(prev => [...prev,
            {
              id: Date.now() + 1, role: 'bot', html: false,
              content: `How would you like to fill in your details?`,
              time: timeNow(),
            },
            { id: Date.now() + 2, role: 'seva_form_mode', appId: appRes.application_id },
          ]);
        }
      } catch (e) {
        setMessages(prev => [...prev, {
          id: Date.now(), role: 'bot', html: false,
          content: `❌ Could not start application: ${e.message}`,
          time: timeNow(),
        }]);
        setSevaAuthStep(null);
      } finally {
        setIsApiLoading(false);
      }
      return;
    }

    // Not yet authenticated — ask for name & email
    setSevaAuthStep('name_email');
    setMessages(prev => [...prev, {
      id: Date.now(), role: 'bot', html: false,
      content: `To apply for **${service.name}**, I need to verify your identity first.\n\nPlease enter your details below.`,
      time: timeNow(),
    }]);
  };

  const handleSevaSubmitNameEmail = async () => {
    if (!sevaAuthName.trim() || !sevaAuthEmail.trim()) {
      setSevaAuthError('Please enter both your name and email address.');
      return;
    }
    const emailRx = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
    if (!emailRx.test(sevaAuthEmail.trim())) {
      setSevaAuthError('Invalid email format. Please check and try again.');
      return;
    }
    setSevaAuthLoading(true);
    setIsApiLoading(true);
    setSevaAuthError('');
    try {
      const res = await sevaApi('POST', '/auth/start', {
        name: sevaAuthName.trim(),
        email: sevaAuthEmail.trim().toLowerCase(),
      });
      setSevaAuthStep('otp');
      const otpMsg = res.email_sent === false
        ? `⚠️ Email delivery unavailable. Use OTP **123456** to continue.`
        : `📧 An OTP has been sent to **${sevaAuthEmail.trim()}**. Please enter it below.\n\n*Valid for 10 minutes.*`;
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'bot', html: false,
        content: otpMsg,
        time: timeNow(),
      }]);
      if (res.is_new_user === false) {
        setMessages(prev => [...prev, {
          id: Date.now() + 1, role: 'bot', html: false,
          content: 'ℹ️ We found an existing account. You can view past applications after logging in.',
          time: timeNow(),
        }]);
      }
    } catch (e) {
      setSevaAuthError(e.message);
    } finally {
      setSevaAuthLoading(false);
      setIsApiLoading(false);
    }
  };

  const handleSevaVerifyOtp = async () => {
    if (!sevaOtpInput.trim()) { setSevaAuthError('Please enter the OTP.'); return; }
    setSevaAuthLoading(true);
    setIsApiLoading(true);
    setSevaAuthError('');
    try {
      const res = await sevaApi('POST', '/auth/verify-otp', {
        email: sevaAuthEmail.trim().toLowerCase(),
        otp: sevaOtpInput.trim(),
      });
      const token = res.session_token;
      sessionStorage.setItem('seva_token', token);
      sessionStorage.setItem('seva_user', JSON.stringify(res.user));
      sevaTokenRef.current = token;
      setSevaToken(token);
      setSevaUser(res.user);
      setSevaAuthStep('done');
      lastActivityRef.current = Date.now();

      if (sevaSelectedService) {
        const appRes = await sevaApi('POST', '/applications', { service_type: sevaSelectedService.key }, token);
        setSevaCurrentApp(appRes);
        const svc = sevaSelectedService;

        if (appRes.service_category === 'TYPE_A' && appRes.gov_url) {
          setMessages(prev => [...prev,
            {
              id: Date.now(), role: 'bot', html: false,
              content: `✅ **Verified!** Your Reference ID is \`${appRes.reference_id}\`.\n\n🔗 Click below to open the application portal for **${svc.name}**.`,
              time: timeNow(),
            },
            { id: Date.now() + 1, role: 'seva_type_a', service: appRes, govUrl: appRes.gov_url },
          ]);
        } else {
          setMessages(prev => [...prev,
            {
              id: Date.now(), role: 'bot', html: false,
              content: `✅ **Verified!** Your Reference ID is \`${appRes.reference_id}\`.\n\nNow let's complete your **${svc.name}** application.\n\nHow would you like to fill in your details?`,
              time: timeNow(),
            },
            { id: Date.now() + 1, role: 'seva_form_mode', appId: appRes.application_id },
          ]);
        }
      }
    } catch (e) {
      setSevaAuthError(e.message);
    } finally {
      setSevaAuthLoading(false);
      setIsApiLoading(false);
    }
  };

  // ── Seva form flow ──────────────────────────────────────────────────────────
  const handleSevaChooseFormMode = (mode) => {
    setSevaFormMode(mode);
    const fields = sevaCurrentApp?.fields || [];
    if (mode === 'manual') {
      const prefilledData = { full_name: sevaUser?.name || '', email: sevaUser?.email || '' };
      setSevaFormData(prefilledData);
      const firstUnfilled = fields.findIndex(f => !prefilledData[f.key]);
      const startIdx = firstUnfilled >= 0 ? firstUnfilled : 0;
      setSevaFormFieldIndex(startIdx);
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'bot', html: false,
        content: `📝 **Manual Form Entry**\n\nLet's fill in your details step by step.\n\n**${fields[startIdx]?.label}:**`,
        time: timeNow(),
      }]);
    } else {
      const svcInfo = sevaServices[sevaSelectedService?.key] || {};
      const docs = svcInfo.documents || sevaCurrentApp?.documents_required || [];
      setMessages(prev => [...prev,
        {
          id: Date.now(), role: 'bot', html: false,
          content: `📤 **Upload Documents**\n\nPlease upload the required documents. I'll extract your details automatically.\n\n**Required:**\n${docs.map(d => `• ${d}`).join('\n')}`,
          time: timeNow(),
        },
        { id: Date.now() + 1, role: 'seva_doc_upload', appId: sevaCurrentApp?.application_id, docs },
      ]);
    }
  };

  const handleSevaFormFieldSubmit = async () => {
    const fields = sevaCurrentApp?.fields || [];
    const value = sevaFormInput.trim();
    const field = fields[sevaFormFieldIndex];

    if (!value) { setSevaFormError('This field is required.'); return; }
    if (field.key === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) {
      setSevaFormError('Please enter a valid email address.'); return;
    }
    if ((field.key === 'dob' || field.key === 'marriage_date') && !/^\d{2}\/\d{2}\/\d{4}$/.test(value)) {
      setSevaFormError('Please use DD/MM/YYYY format (e.g. 01/01/1990).'); return;
    }
    if (field.key === 'phone' && !/^\+?[\d\s\-()+]{7,15}$/.test(value)) {
      setSevaFormError('Please enter a valid phone number.'); return;
    }
    if ((field.key === 'passport_number' || field.key === 'passport_no') && !/^[A-Z0-9]{6,20}$/i.test(value)) {
      setSevaFormError('Passport number should be 6–20 alphanumeric characters.'); return;
    }
    setSevaFormError('');

    const newData = { ...sevaFormData, [field.key]: value };
    setSevaFormData(newData);
    setSevaFormInput('');
    setMessages(prev => [...prev, { id: Date.now(), role: 'user', content: value, time: timeNow() }]);

    const nextIndex = sevaFormFieldIndex + 1;
    if (nextIndex < fields.length) {
      setSevaFormFieldIndex(nextIndex);
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'bot', html: false,
        content: `✓ Got it.\n\n**${fields[nextIndex].label}:**`,
        time: timeNow(),
      }]);
    } else {
      setIsApiLoading(true);
      try {
        await sevaApi('PUT', `/applications/${sevaCurrentApp.application_id}`, { form_data: newData });
        setSevaCurrentApp(prev => ({ ...prev, form_data: newData }));
        const summary = Object.entries(newData)
          .map(([k, v]) => `• **${k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}:** ${v}`)
          .join('\n');
        const svcInfo = sevaServices[sevaSelectedService?.key] || {};
        const docs = svcInfo.documents || sevaCurrentApp?.documents_required || [];
        setMessages(prev => [...prev,
          {
            id: Date.now(), role: 'bot', html: false,
            content: `✅ **Form complete!** Here's your summary:\n\n${summary}\n\nNow please upload the required supporting documents.`,
            time: timeNow(),
          },
          { id: Date.now() + 1, role: 'seva_doc_upload', appId: sevaCurrentApp.application_id, docs },
        ]);
        setSevaFormMode(null);
      } catch {
        // silent fail — user can retry
      } finally {
        setIsApiLoading(false);
      }
    }
  };

  // ── Seva document upload ────────────────────────────────────────────────────
  const handleSevaUploadDoc = async (file, docName) => {
    if (!file || !sevaCurrentApp) return;
    const allowed = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg'];
    if (!allowed.includes(file.type)) return;
    if (file.size > 5 * 1024 * 1024) return;

    const previewDataUrl = await new Promise(resolve => {
      const reader = new FileReader();
      reader.onload = e => resolve(e.target.result);
      reader.readAsDataURL(file);
    });

    setSevaUploadingDocName(docName);
    const fd = new FormData();
    fd.append('file', file);
    fd.append('app_id', sevaCurrentApp.application_id);
    fd.append('doc_name', docName || file.name);

    try {
      const res = await fetch(`${API}/seva-setu/upload-document`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${sevaTokenRef.current}` },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upload failed');

      const appId = sevaCurrentApp.application_id;
      setSevaDocPreviews(prev => ({
        ...prev,
        [appId]: [
          ...(prev[appId] || []).filter(d => d.name !== (docName || file.name)),
          {
            id: data.document?.id || Date.now().toString(),
            name: docName || file.name,
            dataUrl: previewDataUrl,
            isPdf: file.type === 'application/pdf',
          },
        ],
      }));

      if (data.ocr_fields && Object.keys(data.ocr_fields).length > 0) {
        const extracted = Object.entries(data.ocr_fields)
          .map(([k, v]) => `• **${k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}:** ${v}`)
          .join('\n');
        setMessages(prev => [...prev, {
          id: Date.now(), role: 'bot', html: false,
          content: `📋 **OCR extracted from ${docName || file.name}** (please verify):\n${extracted}`,
          time: timeNow(),
        }]);
        setSevaFormData(prev => {
          const merged = { ...prev, ...data.ocr_fields };
          sevaApi('PUT', `/applications/${appId}`, { form_data: merged }).catch(() => {});
          return merged;
        });
      }
    } catch {
      // silent fail
    } finally {
      setSevaUploadingDocName(null);
    }
  };

  const handleSevaRemoveDoc = async (appId, docId) => {
    setIsApiLoading(true);
    try {
      await sevaApi('DELETE', `/applications/${appId}/documents/${docId}`);
      setSevaDocPreviews(prev => ({
        ...prev,
        [appId]: (prev[appId] || []).filter(d => d.id !== docId),
      }));
    } catch {}
    finally { setIsApiLoading(false); }
  };

  // ── Seva submit / confirm ──────────────────────────────────────────────────
  const handleSevaPreviewPdf = async () => {
    if (!sevaCurrentApp) return;
    setIsApiLoading(true);
    try {
      if (Object.keys(sevaFormData).length > 0) {
        await sevaApi('PUT', `/applications/${sevaCurrentApp.application_id}`, { form_data: sevaFormData });
      }
      const url = `${API}/seva-setu/applications/${sevaCurrentApp.application_id}/preview?token=${encodeURIComponent(sevaTokenRef.current)}`;
      const a = document.createElement('a');
      a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer';
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
    } catch {}
    finally { setIsApiLoading(false); }
  };

  const handleSevaSubmitApp = async () => {
    if (!sevaCurrentApp) return;
    setIsApiLoading(true);
    try {
      if (Object.keys(sevaFormData).length > 0) {
        await sevaApi('PUT', `/applications/${sevaCurrentApp.application_id}`, { form_data: sevaFormData });
      }
      const res = await sevaApi('POST', `/applications/${sevaCurrentApp.application_id}/submit`);
      setSevaCurrentApp(prev => ({ ...prev, status: 'submitted' }));
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'bot', html: false,
        content: `📧 **Application Submitted for Review!**\n\nA review email has been sent to **${sevaUser?.email}** with a link to confirm within 24 hours.\n\n**Reference ID:** \`${res.reference_id}\``,
        time: timeNow(),
      }]);
      // Add action buttons
      setMessages(prev => [...prev, {
        id: Date.now() + 1, role: 'seva_app_complete', appId: sevaCurrentApp.application_id
      }]);
      // Reset application state but keep auth for potential new applications
      resetAfterApplicationCompletion(true);
    } catch (e) {
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'bot', html: false,
        content: `❌ Submission failed: ${e.message}`,
        time: timeNow(),
      }]);
    } finally {
      setIsApiLoading(false);
    }
  };

  const handleSevaConfirmApp = async () => {
    if (!sevaCurrentApp) return;
    setIsApiLoading(true);
    try {
      if (Object.keys(sevaFormData).length > 0) {
        await sevaApi('PUT', `/applications/${sevaCurrentApp.application_id}`, { form_data: sevaFormData });
      }
      const res = await sevaApi('POST', `/applications/${sevaCurrentApp.application_id}/confirm`);

      // The processing authority is the system of record: a `submission_pending`
      // result means it didn't accept yet, so we DON'T claim confirmation or
      // offer a PDF — we tell the user honestly and let them know we'll retry.
      if (res.status === 'submission_pending') {
        setSevaCurrentApp(prev => ({ ...prev, status: 'submission_pending' }));
        setMessages(prev => [...prev, {
          id: Date.now(), role: 'bot', html: false,
          content: `⏳ **Submission pending**\n\nWe've saved your **${sevaCurrentApp.service_name}** details (Reference \`${res.reference_id}\`), but the processing authority hasn't confirmed it yet.\n\nNo confirmation has been issued — we'll keep retrying and email **${sevaUser?.email}** as soon as it goes through.`,
          time: timeNow(),
        }]);
        resetAfterApplicationCompletion(true);
        return;
      }

      setSevaCurrentApp(prev => ({ ...prev, status: 'confirmed' }));
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'bot', html: false,
        content: `🎉 **Application Confirmed!**\n\nYour **${sevaCurrentApp.service_name}** application has been confirmed.\n\n**Reference ID:** \`${res.reference_id}\`${res.gov_processing_ref ? `\n**Processing ref:** \`${res.gov_processing_ref}\`` : ''}\n\nA confirmation email with your PDF has been sent to **${sevaUser?.email}**.`,
        time: timeNow(),
      }]);
      setTimeout(() => {
        const pdfUrl = `${API}/seva-setu/applications/${sevaCurrentApp.application_id}/pdf?token=${encodeURIComponent(sevaTokenRef.current)}`;
        const a = document.createElement('a');
        a.href = pdfUrl; a.target = '_blank'; a.rel = 'noopener noreferrer';
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
      }, 600);
      // Add action buttons
      setMessages(prev => [...prev, {
        id: Date.now() + 1, role: 'seva_app_complete', appId: sevaCurrentApp.application_id
      }]);
      // Reset application state but keep auth for potential new applications
      resetAfterApplicationCompletion(true);
    } catch (e) {
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'bot', html: false,
        content: `❌ Confirmation failed: ${e.message}`,
        time: timeNow(),
      }]);
    } finally {
      setIsApiLoading(false);
    }
  };

  const handleSevaTypeAFinalize = async (appId, govRef) => {
    if (!govRef.trim()) return;
    setIsApiLoading(true);
    try {
      const res = await sevaApi('POST', `/applications/${appId}/type-a-finalize`, { gov_reference: govRef.trim() });
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'bot', html: false,
        content: `✅ **Application Recorded!**\n\nGov Reference: \`${govRef.trim()}\`\n\nA confirmation email with your PDF has been sent to **${sevaUser?.email}**.\n\nReference: \`${res.reference_id}\``,
        time: timeNow(),
      }]);
    } catch (e) {
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'bot', html: false,
        content: `❌ Failed to record: ${e.message}`,
        time: timeNow(),
      }]);
    } finally {
      setIsApiLoading(false);
    }
  };

  const handleSevaFetchApps = async () => {
    setIsApiLoading(true);
    try {
      const res = await sevaApi('GET', '/applications');
      setSevaApps(res.applications || []);
      setShowSevaApps(true);
    } catch {}
    finally { setIsApiLoading(false); }
  };

  const handleSevaDownloadPdf = (appId) => {
    const t = sevaTokenRef.current;
    window.open(`${API}/seva-setu/applications/${appId}/pdf${t ? `?token=${encodeURIComponent(t)}` : ''}`, '_blank');
  };

  // ── Streaming send ─────────────────────────────────────────────────────────
  const sendMsg = async (overrideText) => {
    const trimmed = (overrideText !== undefined ? overrideText : input).trim();
    if (!trimmed || isLoading) return;

    // Greeting short-circuit — respond with service tabs instead of streaming.
    // Only kicks in when the entire message is a greeting and we're not mid-auth.
    if (!sevaAuthStep && !sevaUser && GREETING_PATTERN.test(trimmed)) {
      setInput('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
      const now = Date.now();
      setMessages(prev => [
        ...prev,
        { id: now, role: 'user', content: trimmed, time: timeNow() },
        { id: now + 1, role: 'bot', html: false, content: (tenantGreeting || DEFAULT_GREETING_REPLY), time: timeNow() },
        { id: now + 2, role: 'seva_service_tabs' },
      ]);
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
      setIsSpeaking(false);
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    const userMsg = { id: Date.now(), role: 'user', content: trimmed, time: timeNow() };
    setMessages(prev => [...prev, userMsg, { id: Date.now() + 1, role: 'bot', html: false, content: '', time: timeNow() }]);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    setIsLoading(true);

    try {
      const res = await fetch(`${API}/consular/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: trimmed,
          session_id: sessionIdRef.current,
          user_id: sevaUser?.email || 'guest',
          visitor_id: visitorIdRef.current,
          enable_voice: false,
          language: currentLangRef.current,
        }),
        signal: AbortSignal.timeout(60000),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();
        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          let evt;
          try { evt = JSON.parse(part.slice(6)); } catch { continue; }
          if (evt.session_id && evt.session_id !== sessionIdRef.current) {
            sessionIdRef.current = evt.session_id;
            localStorage.setItem('consular_session_id', evt.session_id);
          }
          if (evt.chunk) {
            fullText += evt.chunk;
            setMessages(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = { ...updated[updated.length - 1], content: fullText };
              return updated;
            });
          }
          if (evt.done) {
            if (voiceOnRef.current && fullText) speakWithBackend(fullText);
            if (evt.lang_switch) {
              setTimeout(() => changeLang(evt.lang_switch), 800);
            }
            // ui_hints tells us which input controls to show for the
            // user's NEXT turn — populated by the backend based on
            // flow state (see services.application_flow.ui_hints_for_state).
            if (evt.ui_hints && typeof evt.ui_hints === 'object') {
              setUiHints((prev) => ({ ...prev, ...evt.ui_hints }));
            }
          }
        }
      }
    } catch (err) {
      const errMsg = isOnline
        ? "I'm having trouble connecting to the server. Please try again."
        : 'You appear to be offline. Please check your internet connection.';
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = { ...updated[updated.length - 1], content: errMsg };
        return updated;
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
  };

  const autoResize = (e) => {
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  const toggleVoice = () => {
    if (voiceOn) {
      voiceOnRef.current = false;
      setVoiceOn(false);
      stopAudio();
    } else {
      voiceOnRef.current = true;
      setVoiceOn(true);
    }
  };

  // ── Voice input ────────────────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    // Pick the first MIME type the browser actually supports
    // (iOS Safari only supports audio/mp4; Chrome/Firefox prefer audio/webm)
    const MIME_CANDIDATES = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/mp4',
      'audio/ogg;codecs=opus',
      '',  // empty string = let browser choose
    ];
    const supportedMime = MIME_CANDIDATES.find(
      m => !m || (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(m))
    ) ?? '';

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 44100 }
      });
    } catch {
      fallbackSTT();
      return;
    }

    let recorder;
    try {
      recorder = supportedMime
        ? new MediaRecorder(stream, { mimeType: supportedMime })
        : new MediaRecorder(stream);
    } catch {
      stream.getTracks().forEach(t => t.stop());
      fallbackSTT();
      return;
    }

    const chunks = [];
    const actualMime = recorder.mimeType || supportedMime || 'audio/webm';
    const ext = actualMime.includes('mp4') ? 'm4a' : actualMime.includes('ogg') ? 'ogg' : 'webm';

    recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    recorder.onstop = async () => {
      const blob = new Blob(chunks, { type: actualMime });
      stream.getTracks().forEach(t => t.stop());
      try {
        const formData = new FormData();
        formData.append('audio', blob, `recording.${ext}`);
        formData.append('language', currentLangRef.current);
        const resp = await axios.post(`${API}/consular/voice-input`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        if (resp.data.success && resp.data.transcription) {
          setInput(resp.data.transcription);
        } else { fallbackSTT(); }
      } catch { fallbackSTT(); }
    };
    recorder.start();
    mediaRecorderRef.current = recorder;
    setIsRecording(true);
  }, []);

  const fallbackSTT = () => {
    if (!('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = SPEECH_LANG_MAP[currentLangRef.current] || 'en-IN';
    rec.onresult = e => setInput(e.results[0][0].transcript);
    rec.start();
  };

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }, []);

  const handleVoiceInput = () => {
    if (isRecording) stopRecording();
    else startRecording();
  };

  // ── Camera ─────────────────────────────────────────────────────────────────
  const startCamera = useCallback(async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }
      });
      setCameraStream(stream);
      setShowCamera(true);
      setTimeout(() => { if (videoRef.current) videoRef.current.srcObject = stream; }, 100);
    } catch (err) {
      setCameraError(err.name === 'NotAllowedError'
        ? 'Camera access denied. Please allow camera in browser settings.'
        : 'Camera not available. Please try uploading a file instead.');
      setShowCamera(true);
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (cameraStream) { cameraStream.getTracks().forEach(t => t.stop()); setCameraStream(null); }
    setShowCamera(false);
    setCameraError(null);
  }, [cameraStream]);

  const capturePhoto = useCallback(() => {
    if (!videoRef.current || !canvasRef.current) return;
    const canvas = canvasRef.current;
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    canvas.getContext('2d').drawImage(videoRef.current, 0, 0);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
    stopCamera();
    if (cameraOnCaptureRef.current) {
      const cb = cameraOnCaptureRef.current;
      cameraOnCaptureRef.current = null;
      cb(dataUrl);
    } else {
      setInput('[Photo captured] Please help me with this document.');
      sendDocToBackend(dataUrl.split(',')[1]);
    }
    // sendDocToBackend is declared after this callback; the closure
    // resolves it at call time (which only happens after a user click).
    // Listing it as a dep would TDZ on the first render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopCamera]);

  const sendDocToBackend = async (imageBase64) => {
    setIsLoading(true);
    setMessages(prev => [...prev, { id: Date.now(), role: 'bot', html: false, content: '', time: timeNow() }]);
    try {
      const res = await fetch(`${API}/consular/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: 'Document uploaded',
          image_base64: imageBase64,
          session_id: sessionIdRef.current,
          user_id: sevaUser?.email || 'guest',
          visitor_id: visitorIdRef.current,
          enable_voice: false,
          language: currentLangRef.current,
        }),
        signal: AbortSignal.timeout(60000),
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '', fullText = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();
        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          let evt;
          try { evt = JSON.parse(part.slice(6)); } catch { continue; }
          if (evt.session_id && evt.session_id !== sessionIdRef.current) {
            sessionIdRef.current = evt.session_id;
            localStorage.setItem('consular_session_id', evt.session_id);
          }
          if (evt.chunk) {
            fullText += evt.chunk;
            setMessages(prev => {
              const updated = [...prev];
              updated[updated.length - 1] = { ...updated[updated.length - 1], content: fullText };
              return updated;
            });
          }
          if (evt.done) {
            if (voiceOnRef.current && fullText) speakWithBackend(fullText);
            if (evt.ui_hints && typeof evt.ui_hints === 'object') {
              setUiHints((prev) => ({ ...prev, ...evt.ui_hints }));
            }
          }
        }
      }
    } catch {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = { ...updated[updated.length - 1], content: 'Document received. Please continue.' };
        return updated;
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const allowed = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif', 'application/pdf'];
    if (!allowed.includes(file.type)) { alert('Invalid file type. Use JPG, PNG, or PDF.'); return; }
    if (file.size > 10 * 1024 * 1024) { alert('File exceeds 10MB limit.'); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      const base64 = dataUrl.split(',')[1];
      const isPdf = file.type === 'application/pdf';
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'user',
        content: file.name,
        docPreview: { dataUrl, name: file.name, isPdf },
        time: timeNow(),
      }]);
      sendDocToBackend(base64);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  // ── Lang helpers ───────────────────────────────────────────────────────────
  const showLangToast = useCallback((msg) => {
    setLangToast(msg);
    clearTimeout(langToastTimerRef.current);
    langToastTimerRef.current = setTimeout(() => setLangToast(''), 2800);
  }, []);

  const openLangMenu = useCallback(() => {
    if (langBtnRef.current) {
      const rect = langBtnRef.current.getBoundingClientRect();
      setLangDropPos({ top: rect.bottom + 6, right: window.innerWidth - rect.right });
    }
    setShowLangMenu(true);
  }, []);

  const changeLang = useCallback((code) => {
    if (code === currentLang) { setShowLangMenu(false); return; }

    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    setIsSpeaking(false);
    setShowLangMenu(false);

    // Fire-and-forget — don't block the UI on session close
    const oldSessionId = sessionIdRef.current;
    if (oldSessionId) {
      fetch(`${API}/consular/session/${oldSessionId}/close`, { method: 'POST' }).catch(() => {});
    }

    localStorage.removeItem('consular_session_id');
    sessionIdRef.current = null;
    currentLangRef.current = code;
    langChangedRef.current = true; // signal the greeting useEffect
    setCurrentLang(code);
    setInput('');

    const lang = ALL_LANGS.find(l => l.code === code);
    if (lang) showLangToast(`${lang.flag} Language changed to ${lang.name}`);
  }, [currentLang, showLangToast]);

  // When language changes, fetch a greeting in the new language from the backend
  useEffect(() => {
    if (!langChangedRef.current) return;
    langChangedRef.current = false;

    scrollToTopNextRef.current = true;
    // Show just the greeting placeholder while we fetch from backend —
    // advisories are not repeated on language switch (user already saw them).
    setMessages([{ id: 'lang-greet', role: 'bot', html: false, content: '', time: timeNow() }]);

    const code = currentLangRef.current;
    (async () => {
      setIsLoading(true);
      try {
        const res = await fetch(`${API}/consular/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: 'hello', session_id: null, user_id: 'guest', visitor_id: visitorIdRef.current, enable_voice: false, language: code }),
          signal: AbortSignal.timeout(30000),
        });
        if (!res.ok) throw new Error();
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '', fullText = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop();
          for (const part of parts) {
            if (!part.startsWith('data: ')) continue;
            let evt;
            try { evt = JSON.parse(part.slice(6)); } catch { continue; }
            if (evt.session_id && evt.session_id !== sessionIdRef.current) {
              sessionIdRef.current = evt.session_id;
              localStorage.setItem('consular_session_id', evt.session_id);
            }
            if (evt.chunk) {
              fullText += evt.chunk;
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { ...updated[updated.length - 1], content: fullText };
                return updated;
              });
            }
          }
        }
        if (!fullText) throw new Error('empty');
      } catch {
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = { ...updated[updated.length - 1], content: GENERIC_GREETING };
          return updated;
        });
      } finally {
        setIsLoading(false);
      }
    })();
  }, [currentLang]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Reset seva application state (used by "Apply Now" buttons) ─────────────
  const resetSevaAppState = () => {
    setSevaToken(null);
    setSevaUser(null);
    sevaTokenRef.current = null;
    sessionStorage.removeItem('seva_token');
    sessionStorage.removeItem('seva_user');
    setSevaCurrentApp(null);
    setSevaFormMode(null);
    setSevaFormData({});
    setSevaFormFieldIndex(0);
    setSevaAuthName('');
    setSevaAuthEmail('');
    setSevaOtpInput('');
    setSevaAuthError('');
    setSevaSelectedService(null);
    setSevaAuthStep(null);
  };

  // ── Reset after successful application completion ──────────────────────────
  const resetAfterApplicationCompletion = (keepAuth = false) => {
    setSevaCurrentApp(null);
    setSevaFormMode(null);
    setSevaFormData({});
    setSevaFormFieldIndex(0);
    setSevaSelectedService(null);
    setSevaDocPreviews({});
    if (!keepAuth) {
      setSevaOtpInput('');
      setSevaAuthError('');
      setSevaAuthStep(null);
      setSevaToken(null);
      setSevaUser(null);
      sevaTokenRef.current = null;
      sessionStorage.removeItem('seva_token');
      sessionStorage.removeItem('seva_user');
    }
  };

  const placeholder = LANG_PLACEHOLDERS[currentLang] || LANG_PLACEHOLDERS.en;

  // Pre-computed so the JSX ternary chain stays simple (avoids IIFE syntax error)
  const _sevaFormField = (sevaFormMode === 'manual' && sevaCurrentApp)
    ? ((sevaCurrentApp.fields || [])[sevaFormFieldIndex] || null)
    : null;

  return (
    <div className="seva-widget" style={brandingStyle}>
      {/* WELCOME TIP — disappears when chat is opened */}
      {showTip && !isOpen && (
        <div className="seva-fab-tip">
          <button
            className="seva-fab-tip-close"
            onClick={e => { e.stopPropagation(); setShowTip(false); }}
            aria-label="Dismiss"
          >✕</button>
          👋 Chat with {botName}
        </div>
      )}

      {/* FAB */}
      <button
        className={`seva-fab${isSpeaking ? ' speaking' : ''}`}
        onClick={() => { setShowTip(false); setIsOpen(o => !o); }}
        title={`Chat with ${botName}`}
        aria-label={`Open ${botName} chatbot`}
      >
        <img src={botAvatarUrl} alt={botName} className="seva-fab-img" />
        <div className="seva-fab-badge" />
      </button>

      {/* POPUP */}
      <div id="seva-popup" className={`${isOpen ? 'open' : ''}`} role="dialog" aria-label={`${botName} Chatbot`}>

        {/* HEADER */}
        <div className="chat-header">
          {/* TOP ROW */}
          <div className="header-row">
            <div className="header-av">
              <img id="popup-avatar" src={botAvatarUrl} alt={botName} />
            </div>
            <div className="header-info">
              <div className="header-name">{botName}</div>
              <div className="header-status-row">
                <div className="status-dot" id="status-dot" style={{ background: isOnline ? T.statusOnline : T.statusOffline }} />
                <div className="status-text" id="status-text" style={{ color: isOnline ? T.statusOnline : T.statusOffline }}>
                  {isSwitchingLang ? 'Saving session…' : isSpeaking ? 'Speaking…' : isLoading ? 'Thinking…' : isOnline ? 'Ready to Assist' : 'Offline'}
                </div>
              </div>
            </div>
            {/* LANGUAGE DROPDOWN */}
            <div className="lang-dropdown-wrap" style={{ flex: 1, display: 'flex', justifyContent: 'flex-end', minWidth: 0 }}>
              {(() => {
                // Filter to the languages the operator has enabled.
                // If only one language is configured, hide the picker entirely.
                const availLangs = ALL_LANGS.filter(l => tenantLanguageCodes.includes(l.code));
                const cur = availLangs.find(l => l.code === currentLang) || availLangs[0] || ALL_LANGS[0];
                if (availLangs.length <= 1) return null;
                return (
                  <>
                    <button
                      className="lang-btn"
                      ref={langBtnRef}
                      id="langBtn"
                      onClick={openLangMenu}
                      disabled={isSwitchingLang}
                    >
                      <span className="lang-btn-flag" id="langBtnFlag">{cur.flag}</span>
                      <span className="lang-btn-name" id="langBtnName">{cur.name}</span>
                      <span className="lang-btn-arrow">▼</span>
                    </button>
                    {showLangMenu && (
                      <div className="lang-dropdown open" id="langDropdown" style={{ position: 'fixed', top: langDropPos.top, right: langDropPos.right, zIndex: 100000 }}>
                        <div className="lang-dropdown-header">Select Language</div>
                        <div className="lang-dropdown-list" id="langList">
                          {availLangs.map(l => (
                            <button
                              key={l.code}
                              className={`lang-item${currentLang === l.code ? ' active' : ''}`}
                              onClick={() => changeLang(l.code)}
                            >
                              <span className="lang-item-flag">{l.flag}</span>
                              <span className="lang-item-name">{l.name}</span>
                              {currentLang === l.code && <span className="lang-item-check">✓</span>}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
            {/* HEADER BUTTONS */}
            <div className="header-btns">
              <button className="hbtn" title="Minimize" onClick={() => setIsOpen(false)}>−</button>
              <button className="hbtn" title="Close" onClick={() => setIsOpen(false)}>✕</button>
            </div>
          </div>

          {/* VOICE ROW */}
          <div className="voice-row">
            <div className="voice-row-left">
              <div
                className={`toggle-track${voiceOn ? '' : ' off'}`}
                id="voiceToggle"
                onClick={toggleVoice}
              >
                <div className="toggle-thumb" />
              </div>
              <div>
                <div className="voice-row-label" id="voiceLabel">{voiceOn ? '🔊 Voice Response On' : '🔇 Voice Off'}</div>
                <div className="voice-row-sub">Tap to hear spoken answers</div>
              </div>
            </div>
            {headerTagline && (
              <div style={{ fontSize: '10px', color: 'rgba(255,255,255,.35)', fontWeight: 500, letterSpacing: '.03em' }}>{headerTagline}</div>
            )}
          </div>
        </div>

        {/* Advisory banner: driven by tenant config — advisories are shown
            inline as chat cards (role='advisory') in the message flow.
            A separate always-visible banner would duplicate and was
            previously hardcoded to CGI copy, so it is intentionally absent. */}

        {/* AUTHENTICATED ACTION BAR — Applications + Logout */}
        {sevaToken && (
          <div style={{ display: 'flex', gap: '6px', padding: '7px 10px', borderTop: '1px solid rgba(255,255,255,0.12)', background: 'rgba(0,0,0,0.15)' }}>
            <button
              onClick={handleSevaFetchApps}
              style={{ flex: 1, background: 'rgba(255,255,255,0.15)', color: T.buttonInverse, border: 'none', borderRadius: '8px', padding: '6px 10px', fontSize: '11px', fontWeight: '600', cursor: 'pointer', fontFamily: 'Poppins' }}
            >
              📂 My Applications
            </button>
            <button
              onClick={() => handleSevaLogout(false)}
              style={{ flex: 1, background: T.destructiveSoft, color: T.buttonInverse, border: 'none', borderRadius: '8px', padding: '6px 10px', fontSize: '11px', fontWeight: '600', cursor: 'pointer', fontFamily: 'Poppins' }}
            >
              🚪 Logout
            </button>
          </div>
        )}

        {/* My Applications Panel */}
        {showSevaApps && sevaApps.length > 0 && (
          <div className="seva-apps-panel">
            <div className="seva-apps-panel-header">
              <span>📂 My Applications</span>
              <button onClick={() => setShowSevaApps(false)} className="seva-apps-close">✕</button>
            </div>
            <div className="seva-apps-list">
              {sevaApps.map(app => (
                <div key={app.application_id} className="seva-app-row">
                  <div className="seva-app-info">
                    <span className="seva-app-name">{app.service_name}</span>
                    <span className={`seva-app-status seva-app-status-${app.status}`}>{app.status}</span>
                  </div>
                  <div className="seva-app-meta">
                    <span className="seva-app-ref">{app.reference_id}</span>
                    <button
                      onClick={() => handleSevaDownloadPdf(app.application_id)}
                      className="seva-app-pdf-btn"
                    >
                      📥 PDF
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* MESSAGES */}
        <div className="chat-messages" ref={messagesScrollRef} id="chatMessages">
          {/* API loading overlay */}
          {isApiLoading && (
            <div className="seva-api-overlay">
              <div className="seva-api-spinner" />
              <span>Please wait…</span>
            </div>
          )}

          {messages.map((msg, i) =>
            msg.role === 'user' ? (
              <div key={msg.id || i} className="msg-user">
                <div className="msg-bubble-user">
                  {msg.docPreview ? (
                    <div
                      onClick={() => setDocViewModal(msg.docPreview)}
                      style={{ cursor: 'pointer', marginBottom: msg.content ? 6 : 0 }}
                    >
                      {msg.docPreview.isPdf ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7, background: 'rgba(255,255,255,0.18)', borderRadius: 8, padding: '7px 10px' }}>
                          <span style={{ fontSize: 22 }}>📄</span>
                          <span style={{ fontSize: 11, fontWeight: 600, wordBreak: 'break-all' }}>{msg.docPreview.name}</span>
                        </div>
                      ) : (
                        <img
                          src={msg.docPreview.dataUrl}
                          alt={msg.docPreview.name}
                          style={{ maxWidth: 200, maxHeight: 150, borderRadius: 8, display: 'block', border: '2px solid rgba(255,255,255,0.35)' }}
                        />
                      )}
                      <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.6)', marginTop: 3 }}>Tap to view</div>
                    </div>
                  ) : (
                    msg.content
                  )}
                  <div className="msg-time">{msg.time}</div>
                </div>
              </div>
            ) : msg.role === 'advisory' ? (
              <div key={msg.id || i} className={`seva-advisory-card seva-advisory-${msg.type}`}>
                <div className="seva-advisory-card-title">
                  <span className="seva-advisory-card-icon">
                    {msg.type === 'alert' ? '🚨' : '⚠️'}
                  </span>
                  {msg.title}
                </div>
                <div className="seva-advisory-card-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>{msg.content}</ReactMarkdown>
                </div>
              </div>
            ) : msg.role === 'seva_service_tabs' ? (
              sevaUser ? null : (
                <div key={msg.id || i} className="seva-msg-bot">
                  <div className={`seva-msg-bot-av${isSpeaking ? ' speaking' : ''}`}>
                    <img src={botAvatarUrl} alt="" />
                  </div>
                  {tenantServices === null ? (
                    <div style={{ padding: '8px 12px', fontSize: 12, color: 'rgba(0,0,0,.5)' }}>
                      Loading services…
                    </div>
                  ) : tenantServices.length === 0 ? null : (
                  <ServiceTabs
                    services={tenantServices}
                    onPick={(svc) => {
                      const now = Date.now();
                      if (svc.url) {
                        window.open(svc.url, '_blank', 'noopener,noreferrer');
                        return;
                      }
                      // INFO services have no application flow — the
                      // info card already carries any CTA the operator
                      // set via `info_content.primary_action`. Suppress
                      // the extra "Apply Now" card that the application
                      // services get appended.
                      const isInfo = svc.category === 'INFO';
                      setMessages(prev => {
                        const next = [
                          ...prev,
                          {
                            id: now,
                            role: 'user',
                            content: `${svc.emoji || ''} ${svc.name}`.trim(),
                            time: timeNow(),
                          },
                          { id: now + 1, role: 'seva_service_info', svc },
                        ];
                        if (!isInfo) {
                          next.push({ id: now + 2, role: 'seva_service_action', svc });
                        }
                        return next;
                      });
                    }}
                  />
                  )}
                </div>
              )
            ) : msg.role === 'seva_service_action' ? (
              <div key={msg.id || i} className="seva-svc-action-card">
                <div className="seva-svc-action-info">
                  <span className="seva-svc-emoji">{msg.svc.emoji}</span>
                  <div>
                    <p className="seva-svc-name">{msg.svc.name}</p>
                    <p className="seva-svc-action-hint">Ready to start your application?</p>
                  </div>
                </div>
                <button
                  className="seva-svc-apply-btn"
                  onClick={() => {
                    resetSevaAppState();
                    handleSevaStartAuth({ key: msg.svc.key, name: msg.svc.name, category: msg.svc.category });
                  }}
                >
                  Apply Now →
                </button>
              </div>
            ) : msg.role === 'seva_service_info' ? (
              <div key={msg.id || i} className="seva-msg-bot">
                <div className={`seva-msg-bot-av${isSpeaking ? ' speaking' : ''}`}>
                  <img src={botAvatarUrl} alt="" />
                </div>
                <ServiceInfoCard svc={msg.svc} />
              </div>
            ) : msg.role === 'seva_type_a' ? (
              <div key={msg.id || i} className="msg-bot">
                <div className={`msg-bot-av${isSpeaking ? ' speaking' : ''}`}>
                  <img src={botAvatarUrl} alt="" />
                </div>
                <TypeACard msg={msg} onFinalize={handleSevaTypeAFinalize} />
              </div>
            ) : msg.role === 'seva_form_mode' ? (
              <div key={msg.id || i} className="msg-bot">
                <div className={`msg-bot-av${isSpeaking ? ' speaking' : ''}`}>
                  <img src={botAvatarUrl} alt="" />
                </div>
                <div className="seva-form-mode-card">
                  <p className="seva-form-mode-title">How would you like to proceed?</p>
                  <div className="seva-form-mode-btns">
                    <button
                      onClick={() => handleSevaChooseFormMode('upload')}
                      className="seva-form-mode-btn seva-form-mode-upload"
                    >
                      📤 Upload Docs<span className="seva-form-mode-hint">OCR auto-fill</span>
                    </button>
                    <button
                      onClick={() => handleSevaChooseFormMode('manual')}
                      className="seva-form-mode-btn seva-form-mode-manual"
                    >
                      📝 Fill Manually<span className="seva-form-mode-hint">Step by step</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : msg.role === 'seva_doc_upload' ? (
              <div key={msg.id || i} className="msg-bot">
                <div className={`msg-bot-av${isSpeaking ? ' speaking' : ''}`}>
                  <img src={botAvatarUrl} alt="" />
                </div>
                {(() => {
                  const appId = msg.appId || sevaCurrentApp?.application_id;
                  const previews = sevaDocPreviews[appId] || [];
                  return (
                    <div className="seva-doc-upload-card">
                      <p className="seva-doc-upload-title">Upload Required Documents</p>
                      <div className="seva-doc-list">
                        {(msg.docs || []).map((doc, di) => {
                          const preview = previews.find(p => p.name === doc);
                          return (
                            <div key={di} className="seva-doc-item">
                              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                              {/* Per-doc affordances respect the tenant feature
                                * flags, same as the input-bar controls: file
                                * picker only when file_upload is enabled, camera
                                * button only when camera is enabled. If a
                                * required-docs workflow has both disabled (a
                                * misconfiguration), we still show the doc name so
                                * the user knows what's needed, with a clear
                                * "unavailable" status. */}
                              {tenantFeatures.file_upload ? (
                                <label className={`seva-doc-label ${preview ? 'uploaded' : ''}`} style={{ flex: 1 }}>
                                  <input
                                    type="file"
                                    accept=".pdf,.jpg,.jpeg,.png"
                                    style={{ display: 'none' }}
                                    onChange={e => { if (e.target.files[0]) handleSevaUploadDoc(e.target.files[0], doc); e.target.value = ''; }}
                                    disabled={sevaUploadingDocName === doc}
                                  />
                                  <span className="seva-doc-icon">{preview ? '✅' : '📎'}</span>
                                  <span className="seva-doc-name">{doc}</span>
                                  {sevaUploadingDocName === doc
                                    ? <span className="seva-doc-status uploading">Uploading…</span>
                                    : preview
                                      ? <span className="seva-doc-status done">✓ Done</span>
                                      : <span className="seva-doc-status pending">Upload ↑</span>
                                  }
                                </label>
                              ) : (
                                <div className={`seva-doc-label ${preview ? 'uploaded' : ''}`} style={{ flex: 1 }}>
                                  <span className="seva-doc-icon">{preview ? '✅' : '📎'}</span>
                                  <span className="seva-doc-name">{doc}</span>
                                  {sevaUploadingDocName === doc
                                    ? <span className="seva-doc-status uploading">Uploading…</span>
                                    : preview
                                      ? <span className="seva-doc-status done">✓ Done</span>
                                      : <span className="seva-doc-status pending">{tenantFeatures.camera ? 'Use camera →' : 'Unavailable'}</span>
                                  }
                                </div>
                              )}
                              {tenantFeatures.camera && !preview && sevaUploadingDocName !== doc && (
                                <button
                                  type="button"
                                  title="Take photo"
                                  style={{ padding: '6px 8px', border: `1px solid ${T.cameraAccent}`, borderRadius: 6, background: T.cameraBg, color: T.cameraAccent, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3, fontSize: '11px', flexShrink: 0 }}
                                  onClick={() => {
                                    cameraOnCaptureRef.current = (dataUrl) => {
                                      handleSevaUploadDoc(dataUrlToFile(dataUrl, `${doc}.jpg`), doc);
                                    };
                                    startCamera();
                                  }}
                                >
                                  <CameraIcon size={13} />
                                </button>
                              )}
                              </div>
                              {preview && (
                                <div className="seva-doc-preview-row">
                                  {preview.isPdf ? (
                                    <div
                                      className="seva-doc-preview-pdf"
                                      style={{ cursor: 'pointer' }}
                                      onClick={() => setDocViewModal({ dataUrl: preview.dataUrl, name: preview.name, isPdf: true })}
                                    >📄</div>
                                  ) : (
                                    <img
                                      src={preview.dataUrl}
                                      alt={preview.name}
                                      className="seva-doc-preview-img"
                                      style={{ cursor: 'pointer' }}
                                      onClick={() => setDocViewModal({ dataUrl: preview.dataUrl, name: preview.name, isPdf: false })}
                                    />
                                  )}
                                  <span className="seva-doc-preview-name">{preview.name}</span>
                                  <label className="seva-doc-replace-btn">
                                    <input
                                      type="file"
                                      accept=".pdf,.jpg,.jpeg,.png"
                                      style={{ display: 'none' }}
                                      onChange={e => { if (e.target.files[0]) handleSevaUploadDoc(e.target.files[0], doc); e.target.value = ''; }}
                                    />
                                    🔄
                                  </label>
                                  <button
                                    onClick={() => handleSevaRemoveDoc(appId, preview.id)}
                                    className="seva-doc-remove-btn"
                                  >
                                    🗑
                                  </button>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                      {appId && (
                        <button
                          onClick={() => setMessages(prev => [...prev, { id: Date.now(), role: 'seva_submit_review', appId }])}
                          className="seva-doc-done-btn"
                        >
                          Done — Review &amp; Submit
                        </button>
                      )}
                    </div>
                  );
                })()}
              </div>
            ) : msg.role === 'seva_submit_review' ? (
              <div key={msg.id || i} className="msg-bot">
                <div className={`msg-bot-av${isSpeaking ? ' speaking' : ''}`}>
                  <img src={botAvatarUrl} alt="" />
                </div>
                <div className="seva-submit-card" style={{ minWidth: 260, maxWidth: 340 }}>
                  <p className="seva-submit-title">📋 Review &amp; Submit</p>

                  {/* Editable form data summary */}
                  {sevaCurrentApp?.fields?.length > 0 && (
                    <div style={{ marginBottom: 10 }}>
                      <p style={{ fontSize: '11px', fontWeight: 700, color: 'hsl(var(--foreground))', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                        Application Details
                      </p>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {sevaCurrentApp.fields.map(f => (
                          <div key={f.key} style={{ background: T.fieldSurface, borderRadius: 8, padding: '6px 8px', border: `1px solid ${T.borderDefault}` }}>
                            {sevaEditingField?.key === f.key ? (
                              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                <span style={{ fontSize: '10px', color: T.textMuted, fontWeight: 600 }}>{f.label}</span>
                                {f.field_type === 'file' ? (
                                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', padding: '5px 8px', border: `1px dashed ${T.infoAccent}`, borderRadius: 6, background: T.infoBg, fontSize: '11px', color: T.infoAccent }}>
                                    📎 Choose replacement file
                                    <input
                                      type="file"
                                      accept=".pdf,.jpg,.jpeg,.png"
                                      style={{ display: 'none' }}
                                      onChange={e => {
                                        if (!e.target.files[0]) return;
                                        const file = e.target.files[0];
                                        const reader = new FileReader();
                                        reader.onload = () => {
                                          const dataUrl = reader.result;
                                          const newData = { ...sevaFormData, [f.key]: dataUrl };
                                          setSevaFormData(newData);
                                          sevaApi('PUT', `/applications/${sevaCurrentApp.application_id}`, { form_data: newData }).catch(() => {});
                                          setSevaEditingField(null);
                                        };
                                        reader.readAsDataURL(file);
                                        e.target.value = '';
                                      }}
                                    />
                                  </label>
                                ) : (
                                  <div style={{ display: 'flex', gap: 4 }}>
                                    <input
                                      type="text"
                                      value={sevaEditInput}
                                      onChange={e => setSevaEditInput(e.target.value)}
                                      onKeyDown={e => {
                                        if (e.key === 'Enter') {
                                          if (!sevaEditInput.trim()) return;
                                          const newData = { ...sevaFormData, [f.key]: sevaEditInput.trim() };
                                          setSevaFormData(newData);
                                          sevaApi('PUT', `/applications/${sevaCurrentApp.application_id}`, { form_data: newData }).catch(() => {});
                                          setSevaEditingField(null);
                                        }
                                        if (e.key === 'Escape') setSevaEditingField(null);
                                      }}
                                      autoFocus
                                      style={{ flex: 1, border: `1px solid ${T.infoAccent}`, borderRadius: 6, padding: '4px 7px', fontSize: '12px', outline: 'none' }}
                                    />
                                    <button
                                      onClick={() => {
                                        if (!sevaEditInput.trim()) return;
                                        const newData = { ...sevaFormData, [f.key]: sevaEditInput.trim() };
                                        setSevaFormData(newData);
                                        sevaApi('PUT', `/applications/${sevaCurrentApp.application_id}`, { form_data: newData }).catch(() => {});
                                        setSevaEditingField(null);
                                      }}
                                      style={{ background: T.successAccent, color: T.buttonInverse, border: 'none', borderRadius: 6, padding: '4px 8px', fontSize: '11px', fontWeight: 600, cursor: 'pointer' }}
                                    >Save</button>
                                    <button
                                      onClick={() => setSevaEditingField(null)}
                                      style={{ background: T.borderDefault, color: T.textSecondary, border: 'none', borderRadius: 6, padding: '4px 7px', fontSize: '11px', cursor: 'pointer' }}
                                    >✕</button>
                                  </div>
                                )}
                              </div>
                            ) : (
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 4 }}>
                                <div>
                                  <span style={{ fontSize: '10px', color: T.textMuted, display: 'block' }}>{f.label}</span>
                                  {f.field_type === 'file' ? (
                                    sevaFormData[f.key] ? (
                                      <span
                                        style={{ fontSize: '11px', color: T.infoDeep, fontWeight: 600, cursor: 'pointer' }}
                                        onClick={() => setDocViewModal({ dataUrl: sevaFormData[f.key], name: f.label, isPdf: sevaFormData[f.key]?.startsWith('data:application/pdf') })}
                                      >📎 View document</span>
                                    ) : <span style={{ fontSize: '11px', color: T.textFaint }}>Not uploaded</span>
                                  ) : (
                                    <span style={{ fontSize: '12px', color: T.textPrimary, fontWeight: 500 }}>
                                      {sevaFormData[f.key] || <span style={{ color: T.textFaint }}>—</span>}
                                    </span>
                                  )}
                                </div>
                                <button
                                  onClick={() => { setSevaEditingField(f); setSevaEditInput(sevaFormData[f.key] || ''); }}
                                  style={{ background: 'transparent', border: 'none', color: T.infoAccent, cursor: 'pointer', fontSize: '11px', padding: '2px 4px', flexShrink: 0 }}
                                  title={`Edit ${f.label}`}
                                >✏️</button>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Uploaded documents */}
                  {(() => {
                    const appId = msg.appId || sevaCurrentApp?.application_id;
                    const docs = sevaDocPreviews[appId] || [];
                    if (!docs.length) return null;
                    return (
                      <div style={{ marginBottom: 10 }}>
                        <p style={{ fontSize: '11px', fontWeight: 700, color: 'hsl(var(--foreground))', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.04em' }}>
                          Uploaded Documents
                        </p>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                          {docs.map(doc => (
                            <div key={doc.id} style={{ display: 'flex', alignItems: 'center', gap: 8, background: T.successBg, border: `1px solid ${T.successBorder}`, borderRadius: 8, padding: '5px 8px' }}>
                              {doc.isPdf ? (
                                <span style={{ fontSize: 18 }}>📄</span>
                              ) : (
                                <img
                                  src={doc.dataUrl}
                                  alt={doc.name}
                                  style={{ width: 32, height: 32, objectFit: 'cover', borderRadius: 5, cursor: 'pointer' }}
                                  onClick={() => setDocViewModal(doc)}
                                />
                              )}
                              <span style={{ fontSize: '11px', color: T.successText, fontWeight: 500, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.name}</span>
                              <button
                                style={{ background: 'transparent', border: 'none', color: T.textMuted, cursor: 'pointer', fontSize: 12 }}
                                onClick={() => setDocViewModal(doc)}
                              >👁</button>
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })()}

                  <p className="seva-submit-hint">
                    Review email → <strong>{sevaUser?.email}</strong>. Editable for 24 hrs.
                  </p>
                  <button onClick={handleSevaPreviewPdf} className="seva-submit-preview-btn">
                    📄 Preview PDF
                  </button>
                  <div className="seva-submit-actions">
                    <button onClick={handleSevaSubmitApp} className="seva-submit-review-btn">
                      📤 Submit for Review
                    </button>
                    <button onClick={handleSevaConfirmApp} className="seva-submit-confirm-btn">
                      ✅ Confirm &amp; Get PDF
                    </button>
                  </div>
                </div>
              </div>
            ) : msg.role === 'seva_app_complete' ? (
              <div key={msg.id || i} className="msg-bot">
                <div className={`msg-bot-av${isSpeaking ? ' speaking' : ''}`}>
                  <img src={botAvatarUrl} alt="" />
                </div>
                <div className="seva-app-complete-card" style={{ background: `linear-gradient(135deg, ${T.successBg} 0%, ${T.infoBgSoft} 100%)`, borderRadius: '12px', padding: '14px', borderLeft: `4px solid ${T.successAccent}` }}>
                  <p style={{ fontSize: '13px', fontWeight: '700', color: T.successDeep, margin: '0 0 8px 0' }}>✅ Application successfully completed!</p>
                  <p style={{ fontSize: '11px', color: T.textSecondary, margin: '0 0 12px 0' }}>What would you like to do next?</p>
                  <div style={{ display: 'flex', gap: '8px', flexDirection: 'column' }}>
                    <button
                      onClick={() => {
                        resetSevaAppState();
                        setMessages(prev => [
                          ...prev,
                          { id: Date.now(), role: 'bot', html: false, content: 'How can I assist you? Pick a service below or ask me a question.', time: timeNow() },
                          { id: `seva_tabs_${Date.now()}`, role: 'seva_service_tabs' },
                        ]);
                      }}
                      style={{ background: T.infoAccent, color: T.buttonInverse, border: 'none', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', fontWeight: '600', cursor: 'pointer', fontFamily: 'Poppins' }}
                    >
                      📋 Apply for Another Service
                    </button>
                    <button
                      onClick={() => handleSevaFetchApps()}
                      style={{ background: T.secondaryAccent, color: T.buttonInverse, border: 'none', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', fontWeight: '600', cursor: 'pointer', fontFamily: 'Poppins' }}
                    >
                      📂 View All My Applications
                    </button>
                    <button
                      onClick={() => {
                        handleSevaLogout(false);
                      }}
                      style={{ background: T.destructiveAccent, color: T.buttonInverse, border: 'none', borderRadius: '8px', padding: '8px 12px', fontSize: '12px', fontWeight: '600', cursor: 'pointer', fontFamily: 'Poppins' }}
                    >
                      🚪 Logout
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div key={msg.id || i} className="msg-bot">
                <div className={`msg-bot-av${isSpeaking ? ' speaking' : ''}`}>
                  <img src={botAvatarUrl} alt="" />
                </div>
                <div className="msg-bubble-bot">
                  {msg.content ? (
                    <div className="prose">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>{msg.content}</ReactMarkdown>
                    </div>
                  ) : (
                    <div className="typing-dots"><span /><span /><span /></div>
                  )}
                  {msg.content && <div className="msg-time">{msg.time}</div>}
                </div>
              </div>
            )
          )}
          <div />
        </div>

        {/* CAMERA OVERLAY */}
        {showCamera && (
          <div className="seva-camera-overlay">
            <div className="seva-camera-header">
              <span>📷 Document Camera</span>
              <button className="seva-camera-close" onClick={stopCamera}>✕</button>
            </div>
            {cameraError ? (
              <div className="seva-camera-error">{cameraError}</div>
            ) : (
              <video ref={videoRef} autoPlay playsInline muted className="seva-camera-video" />
            )}
            <canvas ref={canvasRef} style={{ display: 'none' }} />
            {!cameraError && (
              <button className="seva-camera-capture" onClick={capturePhoto}>📸 Capture</button>
            )}
          </div>
        )}

        {/* INPUT AREA — switches between auth/form panels and normal textarea */}
        {/* INPUT */}
        <div className="wa-input-area">

          {/* AUTH PANEL: Name & Email */}
          {sevaAuthStep === 'name_email' && (
            <div className="seva-auth-panel">
              <p className="seva-auth-panel-step">Step 1: Verify Identity</p>
              {sevaAuthError && <p className="seva-auth-panel-error">⚠️ {sevaAuthError}</p>}
              <input
                type="text"
                className="seva-auth-input"
                placeholder="Full Name"
                value={sevaAuthName}
                onChange={e => setSevaAuthName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSevaSubmitNameEmail()}
                disabled={sevaAuthLoading}
                autoFocus
              />
              <input
                type="email"
                className="seva-auth-input"
                placeholder="Email Address"
                value={sevaAuthEmail}
                onChange={e => setSevaAuthEmail(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSevaSubmitNameEmail()}
                disabled={sevaAuthLoading}
              />
              <button
                className="seva-auth-submit-btn"
                onClick={handleSevaSubmitNameEmail}
                disabled={sevaAuthLoading || !sevaAuthName.trim() || !sevaAuthEmail.trim()}
              >
                {sevaAuthLoading ? '⏳ Sending OTP…' : '🔐 Send OTP →'}
              </button>
              <button 
                className="seva-auth-back-btn" 
                onClick={() => { 
                  if (sevaAuthName.trim() || sevaAuthEmail.trim()) {
                    setShowAuthDiscardConfirm(true);
                  } else {
                    resetSevaAppState();
                  }
                }} 
                disabled={sevaAuthLoading}
              >
                ← Back to Chat
              </button>
            </div>
          )}

          {/* AUTH PANEL: OTP */}
          {sevaAuthStep === 'otp' && (
            <div className="seva-auth-panel">
              <p className="seva-auth-panel-step">Step 2: Verify OTP</p>
              <p style={{ fontSize: '11px', color: T.textOnDark, margin: '0 0 8px 0' }}>Check your email for the OTP code</p>
              {sevaAuthError && <p className="seva-auth-panel-error">⚠️ {sevaAuthError}</p>}
              <div className="seva-auth-otp-row">
                <input
                  type="text"
                  className="seva-auth-input seva-auth-otp-input"
                  placeholder="Enter OTP"
                  value={sevaOtpInput}
                  onChange={e => setSevaOtpInput(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  onKeyDown={e => e.key === 'Enter' && handleSevaVerifyOtp()}
                  disabled={sevaAuthLoading}
                  maxLength="6"
                  autoFocus
                />
                <button
                  className="seva-auth-verify-btn"
                  onClick={handleSevaVerifyOtp}
                  disabled={sevaAuthLoading || !sevaOtpInput.trim()}
                >
                  {sevaAuthLoading ? '⏳' : '✓'}
                </button>
              </div>
              <button 
                className="seva-auth-back-btn" 
                onClick={() => { setSevaAuthStep('name_email'); setSevaOtpInput(''); setSevaAuthError(''); }} 
                disabled={sevaAuthLoading}
              >
                ← Back
              </button>
            </div>
          )}

          {/* FORM PANEL: Manual form field input */}
          {sevaAuthStep === 'done' && sevaFormMode === 'manual' && _sevaFormField && (
            <div className="seva-form-panel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                <button 
                  className="seva-auth-back-btn" 
                  onClick={() => setShowDiscardConfirm(true)}
                  style={{ flex: 0, marginRight: 'auto', marginBottom: 0, padding: '6px 10px', fontSize: '11px' }}
                >
                  ← Back
                </button>
                <p className="seva-form-panel-label" style={{ margin: 0, flex: 1, textAlign: 'center' }}>
                  {_sevaFormField.label}
                  <span style={{ color: T.destructiveAccent, marginLeft: 2 }}>*</span>
                </p>
                <span style={{ fontSize: '10px', color: T.textFaint, flex: 0 }}>
                  {sevaFormFieldIndex + 1} / {(sevaCurrentApp?.fields || []).length}
                </span>
              </div>

              {/* Validation error */}
              {sevaFormError && (
                <p style={{ fontSize: '11px', color: T.destructiveAccent, margin: '2px 0 6px 0', fontWeight: 500 }}>
                  ⚠️ {sevaFormError}
                </p>
              )}

              {_sevaFormField.field_type === 'file' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {/* File preview if already selected */}
                  {sevaFormFilePreview && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: T.successBg, border: `1px solid ${T.successBorder}`, borderRadius: 8, padding: '6px 10px' }}>
                      {sevaFormFilePreview.isPdf ? (
                        <span style={{ fontSize: 20 }}>📄</span>
                      ) : (
                        <img
                          src={sevaFormFilePreview.dataUrl}
                          alt={sevaFormFilePreview.name}
                          style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 6, cursor: 'pointer' }}
                          onClick={() => setDocViewModal(sevaFormFilePreview)}
                        />
                      )}
                      <span style={{ fontSize: 11, color: T.successText, fontWeight: 600, flex: 1, wordBreak: 'break-all' }}>{sevaFormFilePreview.name}</span>
                      <button
                        onClick={() => setSevaFormFilePreview(null)}
                        style={{ background: 'transparent', border: 'none', color: T.textMuted, cursor: 'pointer', fontSize: 14 }}
                      >✕</button>
                    </div>
                  )}
                  {/* Upload + camera affordances for a file-type form field
                    * respect the tenant feature flags (same gating as the
                    * doc-upload card and the input bar). */}
                  <div style={{ display: 'flex', gap: 8 }}>
                    {tenantFeatures.file_upload && (
                    <label style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', padding: '8px', border: `2px dashed ${T.infoBorder}`, borderRadius: '8px', background: T.infoBgAlt }}>
                      <span>📎</span>
                      <span style={{ fontSize: '12px', color: T.infoBorder, fontWeight: '500' }}>
                        {sevaFormFilePreview ? 'Replace' : 'Upload file'}
                      </span>
                      <input
                        type="file"
                        accept=".pdf,.jpg,.jpeg,.png"
                        style={{ display: 'none' }}
                        onChange={e => {
                          if (!e.target.files[0]) return;
                          const file = e.target.files[0];
                          const reader = new FileReader();
                          reader.onload = () => {
                            const dataUrl = reader.result;
                            const isPdf = file.type === 'application/pdf';
                            const fieldLabel = _sevaFormField.label;
                            const fieldKey = _sevaFormField.key;
                            setSevaFormFilePreview({ dataUrl, name: file.name, isPdf });
                            setSevaFormData(p => ({ ...p, [fieldKey]: dataUrl }));
                            setSevaFormError('');
                            setMessages(prev => [
                              ...prev,
                              { id: Date.now(), role: 'user', content: file.name, docPreview: { dataUrl, name: file.name, isPdf }, time: timeNow() },
                              { id: Date.now() + 1, role: 'bot', html: false, content: `✓ **${fieldLabel}** uploaded.`, time: timeNow() },
                            ]);
                            setSevaFormFieldIndex(p => p + 1);
                            setSevaFormInput('');
                            setSevaFormFilePreview(null);
                          };
                          reader.readAsDataURL(file);
                          e.target.value = '';
                        }}
                      />
                    </label>
                    )}
                    {tenantFeatures.camera && (
                    <button
                      type="button"
                      title="Take photo"
                      style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, cursor: 'pointer', padding: '8px', border: `2px solid ${T.cameraAccent}`, borderRadius: '8px', background: T.cameraBg, color: T.cameraAccent, fontWeight: '500', fontSize: '12px' }}
                      onClick={() => {
                        const fieldLabel = _sevaFormField.label;
                        const fieldKey = _sevaFormField.key;
                        cameraOnCaptureRef.current = (dataUrl) => {
                          setSevaFormData(p => ({ ...p, [fieldKey]: dataUrl }));
                          setSevaFormError('');
                          setMessages(prev => [
                            ...prev,
                            { id: Date.now(), role: 'user', content: 'Photo.jpg', docPreview: { dataUrl, name: 'Photo.jpg', isPdf: false }, time: timeNow() },
                            { id: Date.now() + 1, role: 'bot', html: false, content: `✓ **${fieldLabel}** captured.`, time: timeNow() },
                          ]);
                          setSevaFormFieldIndex(p => p + 1);
                          setSevaFormInput('');
                          setSevaFormFilePreview(null);
                        };
                        startCamera();
                      }}
                    >
                      <CameraIcon size={15} />
                      <span>Take photo</span>
                    </button>
                    )}
                    {!tenantFeatures.file_upload && !tenantFeatures.camera && (
                      <p style={{ flex: 1, fontSize: '11px', color: T.textMuted, margin: 0, padding: '8px' }}>
                        File upload is disabled for this service.
                      </p>
                    )}
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {/* Hint for date/special fields */}
                  {((_sevaFormField.key === 'dob' || _sevaFormField.key === 'marriage_date')) && (
                    <p style={{ fontSize: '10px', color: T.textMuted, margin: '0 0 2px 0' }}>Format: DD/MM/YYYY</p>
                  )}
                  {_sevaFormField.key === 'phone' && (
                    <p style={{ fontSize: '10px', color: T.textMuted, margin: '0 0 2px 0' }}>Include country code (e.g. +27 82 123 4567)</p>
                  )}
                  <div className="seva-form-panel-row">
                    <input
                      type={_sevaFormField.field_type || 'text'}
                      className={`seva-auth-input${sevaFormError ? ' seva-input-error' : ''}`}
                      placeholder={_sevaFormField.label}
                      value={sevaFormInput}
                      onChange={e => { setSevaFormInput(e.target.value); if (sevaFormError) setSevaFormError(''); }}
                      onKeyDown={e => { if (e.key === 'Enter') handleSevaFormFieldSubmit(); }}
                      autoFocus
                    />
                    <button
                      className="seva-form-next-btn"
                      onClick={handleSevaFormFieldSubmit}
                      disabled={!sevaFormInput.trim()}
                    >
                      Next →
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Normal Textarea Input — shown when not mid-auth/form AND no active in-progress app.
              Buttons are gated to keep the bar uncluttered:
                * Upload — visible when the bot signalled `ui_hints.expects_upload`
                * Camera — visible when the bot signalled `ui_hints.expects_image`
                * Mic    — visible only if the tenant has `features.voice_input` on
              Both attach + camera also respect their tenant feature flag, so an
              operator who never wants either can disable them platform-wide. */}
           {(!sevaAuthStep || sevaAuthStep === 'done') && sevaFormMode === null && !sevaCurrentApp && (
            <div className="wa-bar" style={{display:'flex',alignItems:'flex-end',gap:6,background:T.chatInputBar,borderRadius:24,padding:'6px 10px',overflow:'hidden',boxSizing:'border-box',width:'100%'}}>
              {tenantFeatures.file_upload && uiHints.expects_upload && (
                <button className="wa-attach" title="Attach document" style={{flexShrink:0}} onClick={() => fileInputRef.current?.click()}><FileTextIcon size={18} /></button>
              )}
              <textarea
                ref={textareaRef}
                className="wa-text"
                id="msgInput"
                rows={1}
                placeholder={placeholder}
                value={input}
                onChange={e => setInput(e.target.value)}
                onInput={autoResize}
                onKeyDown={handleKey}
                disabled={isLoading}
                style={{flex:'1 1 0',minWidth:0,width:'auto',boxSizing:'border-box'}}
              />
              {tenantFeatures.camera && uiHints.expects_image && (
                <button className="wa-cam" title="Camera" style={{flexShrink:0}} onClick={startCamera}><CameraIcon size={18} /></button>
              )}
              {tenantFeatures.voice_input && (
                <button className={`wa-mic${isRecording ? ' active' : ''}`} id="micBtn" title="Voice input" style={{flexShrink:0}} onClick={handleVoiceInput}><MicIcon size={18} /></button>
              )}
              <button className="wa-send" id="sendBtn" style={{flexShrink:0}} onClick={() => sendMsg()} disabled={isLoading || !input.trim()}><SendIcon size={18} /></button>
              <input ref={fileInputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" style={{ display: 'none' }} onChange={handleFileUpload} />
            </div>
          )}

          {/* Form upload mode textarea. The attach button respects the tenant
              file_upload flag (the doc-upload card carries its own per-doc
              affordances); when disabled the bar is just a text field. */}
          {sevaAuthStep === 'done' && sevaFormMode === 'upload' && (
            <div className="wa-bar" style={{display:'flex',alignItems:'flex-end',gap:6,background:T.chatInputBar,borderRadius:24,padding:'6px 10px',overflow:'hidden',boxSizing:'border-box',width:'100%'}}>
              {tenantFeatures.file_upload && (
                <button className="wa-attach" title="Attach document" style={{flexShrink:0}} onClick={() => fileInputRef.current?.click()}><FileTextIcon size={18} /></button>
              )}
              <textarea
                ref={textareaRef}
                className="wa-text"
                id="msgInput"
                rows={1}
                placeholder={tenantFeatures.file_upload ? "Upload your documents..." : "Type your message ..."}
                value={input}
                onChange={e => setInput(e.target.value)}
                onInput={autoResize}
                onKeyDown={handleKey}
                disabled={isLoading}
                style={{flex:'1 1 0',minWidth:0,width:'auto',boxSizing:'border-box'}}
              />
              <button className="wa-send" id="sendBtn" style={{flexShrink:0}} onClick={() => sendMsg()} disabled={isLoading || !input.trim()}><SendIcon size={18} /></button>
              <input ref={fileInputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" style={{ display: 'none' }} onChange={handleFileUpload} />
            </div>
          )}
        </div>

        {/* FOOTER NOTE — admin-configured copy wins; otherwise compose from
            org_name / org_short_name; otherwise hide. The previous hardcoded
            CGI line is the worst-case visible default only for very old
            unconfigured tenants and is preserved as a sentinel. */}
        {(footerCopy || orgName) && (
          <div className="chat-footer-note">
            {footerCopy
              ? footerCopy
              : <>Official service of <span>{orgName}</span>{orgShortName ? <> · {orgShortName}</> : null}</>
            }
          </div>
        )}
      </div>

      {/* LANG TOAST */}
      {langToast && <div className="seva-lang-toast">{langToast}</div>}

      {/* DOCUMENT VIEW MODAL */}
      {docViewModal && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.88)', zIndex: 200000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
          onClick={() => setDocViewModal(null)}
        >
          <div
            style={{ background: T.buttonInverse, borderRadius: 16, padding: 20, maxWidth: '92vw', maxHeight: '88vh', overflow: 'auto', position: 'relative', minWidth: 260 }}
            onClick={e => e.stopPropagation()}
          >
            <button
              onClick={() => setDocViewModal(null)}
              style={{ position: 'absolute', top: 10, right: 10, background: 'transparent', border: 'none', fontSize: 20, cursor: 'pointer', color: T.textOnDark, lineHeight: 1 }}
            >✕</button>
            <p style={{ fontSize: 13, fontWeight: 600, color: 'hsl(var(--foreground))', marginBottom: 12, paddingRight: 28, wordBreak: 'break-all' }}>{docViewModal.name}</p>
            {docViewModal.isPdf ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: '16px 0' }}>
                <span style={{ fontSize: 64 }}>📄</span>
                <p style={{ fontSize: 13, color: T.textOnDark, margin: 0 }}>PDF Document</p>
                <a
                  href={docViewModal.dataUrl}
                  download={docViewModal.name}
                  style={{ background: 'hsl(var(--primary))', color: T.buttonInverse, borderRadius: 8, padding: '8px 18px', textDecoration: 'none', fontSize: 12, fontWeight: 600 }}
                >
                  ⬇ Download
                </a>
              </div>
            ) : (
              <img
                src={docViewModal.dataUrl}
                alt={docViewModal.name}
                style={{ maxWidth: '100%', maxHeight: '70vh', borderRadius: 8, display: 'block' }}
              />
            )}
          </div>
        </div>
      )}

      {/* DISCARD CONFIRMATION MODAL */}
      {showDiscardConfirm && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200001, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
          onClick={() => setShowDiscardConfirm(false)}
        >
          <div
            style={{ background: T.buttonInverse, borderRadius: 16, padding: 20, maxWidth: '320px', position: 'relative', minWidth: 260 }}
            onClick={e => e.stopPropagation()}
          >
            <button
              onClick={() => setShowDiscardConfirm(false)}
              style={{ position: 'absolute', top: 10, right: 10, background: 'transparent', border: 'none', fontSize: 20, cursor: 'pointer', color: T.textOnDark, lineHeight: 1 }}
            >✕</button>
            <p style={{ fontSize: 14, fontWeight: 600, color: 'hsl(var(--foreground))', marginBottom: 8, paddingRight: 20 }}>⚠️ Discard Application?</p>
            <p style={{ fontSize: 12, color: T.textOnDark, marginBottom: 16 }}>
              Are you sure you want to go back? Any information you've entered will be lost.
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setShowDiscardConfirm(false)}
                style={{ flex: 1, background: T.borderDefault, color: T.textSecondary, border: 'none', borderRadius: 8, padding: '10px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'Poppins' }}
              >
                Keep Filling
              </button>
              <button
                onClick={() => {
                  resetSevaAppState();
                  setShowDiscardConfirm(false);
                  scrollToTopNextRef.current = true;
                  setMessages(buildWelcomeMessages({ greeting: tenantGreeting, advisories: tenantAdvisories }));
                }}
                style={{ flex: 1, background: T.destructiveAccent, color: T.buttonInverse, border: 'none', borderRadius: 8, padding: '10px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'Poppins' }}
              >
                Discard
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AUTH DISCARD CONFIRMATION MODAL */}
      {showAuthDiscardConfirm && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 200001, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}
          onClick={() => setShowAuthDiscardConfirm(false)}
        >
          <div
            style={{ background: T.buttonInverse, borderRadius: 16, padding: 20, maxWidth: '320px', position: 'relative', minWidth: 260 }}
            onClick={e => e.stopPropagation()}
          >
            <button
              onClick={() => setShowAuthDiscardConfirm(false)}
              style={{ position: 'absolute', top: 10, right: 10, background: 'transparent', border: 'none', fontSize: 20, cursor: 'pointer', color: T.textOnDark, lineHeight: 1 }}
            >✕</button>
            <p style={{ fontSize: 14, fontWeight: 600, color: 'hsl(var(--foreground))', marginBottom: 8, paddingRight: 20 }}>⚠️ Discard Verification?</p>
            <p style={{ fontSize: 12, color: T.textOnDark, marginBottom: 16 }}>
              Are you sure you want to go back? Your information will not be saved.
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => setShowAuthDiscardConfirm(false)}
                style={{ flex: 1, background: T.borderDefault, color: T.textSecondary, border: 'none', borderRadius: 8, padding: '10px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'Poppins' }}
              >
                Continue
              </button>
              <button
                onClick={() => {
                  resetSevaAppState();
                  setShowAuthDiscardConfirm(false);
                  scrollToTopNextRef.current = true;
                  setMessages(buildWelcomeMessages({ greeting: tenantGreeting, advisories: tenantAdvisories }));
                }}
                style={{ flex: 1, background: T.destructiveAccent, color: T.buttonInverse, border: 'none', borderRadius: 8, padding: '10px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'Poppins' }}
              >
                Go Back
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
