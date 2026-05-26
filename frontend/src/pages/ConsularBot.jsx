import React, { useState, useEffect, useRef, useCallback } from "react";
import { Mic, Camera, Send, FileText, Check, AlertTriangle, Globe, X, Volume2, VolumeX, Square, Eye, RefreshCw, Trash2, LogOut, List, Download, UserCheck, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import axios from "axios";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  BOT_CONFIG as DEFAULT_BOT_CONFIG,
  GREETING_MESSAGE as DEFAULT_GREETING,
  ADVISORY_MESSAGES as DEFAULT_ADVISORIES,
  SUPPORTED_LANGUAGES as DEFAULT_LANGUAGES
} from "../config/botMessages";
import { fetchBranding } from "../lib/widgetConfig";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// ── Custom markdown renderer for bot responses ──────────────────────────────
const MD = {
  h1: ({ children }) => (
    <h1 className="text-base font-bold text-[#1A2E40] mt-4 mb-1.5 first:mt-0 leading-snug border-b border-gray-100 pb-1">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-sm font-bold text-[#1A2E40] mt-3 mb-1 first:mt-0 leading-snug">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold text-[#E06F2C] mt-2 mb-0.5 first:mt-0">
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="text-sm text-[#1A2E40] mb-2 last:mb-0 leading-relaxed">
      {children}
    </p>
  ),
  ul: ({ children }) => (
    <ul className="mb-2 last:mb-0 space-y-1 pl-1">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-2 last:mb-0 space-y-1 pl-1">{children}</ol>
  ),
  li: ({ children, ordered, index }) => (
    <li className="flex items-start gap-2 text-sm text-[#1A2E40] leading-relaxed">
      <span className="mt-[3px] flex-shrink-0 text-[#E06F2C] font-bold text-xs select-none min-w-[1.1rem]">
        {ordered ? `${(index ?? 0) + 1}.` : "•"}
      </span>
      <span className="flex-1">{children}</span>
    </li>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-[#1A2E40]">{children}</strong>
  ),
  em: ({ children }) => (
    <em className="italic text-gray-500">{children}</em>
  ),
  hr: () => (
    <hr className="my-3 border-0 border-t border-gray-200" />
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[#E06F2C] underline underline-offset-2 hover:text-[#c45a1a] break-all"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-3 border-[#E06F2C] pl-3 my-2 text-sm text-gray-600 italic bg-orange-50 py-1 rounded-r">
      {children}
    </blockquote>
  ),
  code: ({ inline, children }) =>
    inline ? (
      <code className="bg-gray-100 text-[#1A2E40] px-1 py-0.5 rounded text-xs font-mono">
        {children}
      </code>
    ) : (
      <pre className="bg-gray-100 text-[#1A2E40] px-3 py-2 rounded text-xs font-mono overflow-x-auto my-2 whitespace-pre-wrap">
        <code>{children}</code>
      </pre>
    ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-2 rounded border border-gray-200">
      <table className="w-full text-sm border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
  th: ({ children }) => (
    <th className="border-b border-gray-200 px-3 py-1.5 text-left text-xs font-semibold text-[#1A2E40] uppercase tracking-wide">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border-b border-gray-100 px-3 py-1.5 text-sm text-[#1A2E40]">
      {children}
    </td>
  ),
  tr: ({ children }) => (
    <tr className="even:bg-gray-50 hover:bg-orange-50 transition-colors">
      {children}
    </tr>
  ),
};

const BotMessage = ({ content }) => (
  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
    {content}
  </ReactMarkdown>
);

// ── Service info card — shown before auth ─────────────────────────────────────
const ServiceInfoCard = ({ svc, onApply }) => (
  <div className="bg-white border-2 border-[#E06F2C] rounded-xl shadow-md px-5 py-4 max-w-[92%] space-y-3">
    <div className="flex items-center gap-2">
      <span className="text-2xl">{svc.emoji}</span>
      <h3 className="text-base font-bold text-[#1A2E40] flex-1">{svc.name}</h3>
      {svc.category === "TYPE_A" && (
        <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium whitespace-nowrap">Gov Portal</span>
      )}
    </div>
    <p className="text-sm text-gray-600 leading-relaxed">{svc.description}</p>
    <div>
      <p className="text-xs font-semibold text-[#1A2E40] uppercase tracking-wide mb-1.5">Required Documents</p>
      <ul className="space-y-1">
        {svc.documents.map((doc, i) => (
          <li key={i} className="flex items-start gap-1.5 text-xs text-gray-600">
            <span className="text-[#E06F2C] mt-0.5 flex-shrink-0">•</span>{doc}
          </li>
        ))}
      </ul>
    </div>
    <button
      onClick={onApply}
      className="w-full bg-[#E06F2C] text-white rounded-lg py-2.5 text-sm font-semibold hover:bg-[#c45a1a] transition"
    >
      Apply Now →
    </button>
  </div>
);

// ── TYPE A card with gov-reference input (self-contained state) ───────────────
const TypeACard = ({ msg, onFinalize }) => {
  const [govRef, setGovRef] = React.useState("");
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
    <div className="bg-white border border-[#E06F2C] rounded-xl shadow-sm px-4 py-4 max-w-[88%] space-y-3">
      {/* Reference ID */}
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">Reference</span>
        <span className="font-mono text-sm font-bold text-[#E06F2C]">{msg.service?.reference_id}</span>
      </div>

      {/* Required documents */}
      {(msg.service?.documents_required || []).length > 0 && (
        <div>
          <p className="text-xs font-semibold text-[#1A2E40] mb-1">Documents Required</p>
          <ul className="space-y-0.5">
            {msg.service.documents_required.map((d, i) => (
              <li key={i} className="flex items-start gap-1.5 text-xs text-gray-600">
                <span className="text-[#E06F2C] mt-0.5">•</span>{d}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Open portal button */}
      <a
        href={msg.govUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 bg-[#E06F2C] text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-[#c45a1a] transition w-full justify-center"
      >
        <ChevronRight className="w-4 h-4" /> Open Government Portal
      </a>

      {/* Gov reference input */}
      {!submitted ? (
        <div>
          <p className="text-xs text-gray-500 mb-1">After applying on the portal, enter your Government Reference / Application Number below to record it and receive your PDF:</p>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="e.g. AP2026XXXXXXX"
              value={govRef}
              onChange={e => setGovRef(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSubmit()}
              className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#E06F2C]"
            />
            <button
              onClick={handleSubmit}
              disabled={loading || !govRef.trim()}
              className="bg-[#1A2E40] text-white rounded-lg px-4 py-2 text-sm font-semibold hover:bg-[#243a52] transition disabled:opacity-50"
            >
              {loading ? "…" : "Submit"}
            </button>
          </div>
        </div>
      ) : (
        <p className="text-sm text-green-700 font-semibold text-center">✅ Recorded — check your email for the PDF!</p>
      )}
    </div>
  );
};

// ── Document card rendered inside chat for uploaded docs ─────────────────────
const DocumentCard = ({ doc, onView, onReplace, onRemove }) => (
  <div className="flex flex-col gap-2 mt-1">
    <div
      className="relative w-40 h-28 rounded-lg overflow-hidden border border-gray-200 cursor-pointer group shadow-sm"
      onClick={onView}
    >
      {doc.isPdf ? (
        <div className="flex flex-col items-center justify-center w-full h-full bg-red-50 text-red-500 gap-1">
          <FileText size={32} />
          <span className="text-xs font-medium">PDF</span>
        </div>
      ) : (
        <img src={doc.dataUrl} alt={doc.name} className="w-full h-full object-cover" />
      )}
      <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
        <Eye size={22} className="text-white" />
      </div>
    </div>
    <p className="text-xs text-gray-500 truncate max-w-[160px]">{doc.name}</p>
    <div className="flex gap-2">
      <button
        onClick={onReplace}
        className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-blue-50 text-blue-600 hover:bg-blue-100 transition"
      >
        <RefreshCw size={12} /> Replace
      </button>
      <button
        onClick={onRemove}
        className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-50 text-red-500 hover:bg-red-100 transition"
      >
        <Trash2 size={12} /> Remove
      </button>
    </div>
  </div>
);

const STEPS = [
  { id: 1, label: "Register", value: "register" },
  { id: 2, label: "Upload", value: "upload" },
  { id: 3, label: "Verify", value: "verify" },
  { id: 4, label: "Sign", value: "sign" }
];

// Service definitions and keyword detection patterns are tenant-driven and
// fetched on mount from /api/consular/widget-config (which returns the
// tenant's `tenant_services` rows). See `useMemo`/`useEffect` blocks inside
// the component below. No hardcoded service catalogue lives here.

// Normalize a single widget-config service row into the shape this page
// previously expected from `SERVICE_INFO` (the dialogue/cards use the same
// keys). `gov_url` is the legacy alias the cards read; map from
// `external_url` returned by the API.
function _normalizeService(row) {
  if (!row || !row.key) return null;
  return {
    key:         row.key,
    name:        row.name || row.key,
    emoji:       row.emoji || "",
    category:    row.category || "TYPE_A",
    gov_url:     row.external_url || "",
    description: row.description || "",
    documents:   Array.isArray(row.documents) ? row.documents : [],
    keywords:    Array.isArray(row.keywords)  ? row.keywords  : [],
    post_confirm_message: row.post_confirm_message || "",
  };
}

// Languages and BCP-47 speech codes are tenant-driven via widget-config.
// LANGUAGES + SPEECH_LANG_MAP are now derived inside the component below from
// `tenantBranding.supported_languages` — see `_LANGUAGES_LIST` and
// `_SPEECH_LANG_MAP` useMemo blocks. A minimal English-only fallback is kept
// here so the widget renders before widget-config resolves.
const _FALLBACK_LANGUAGES = [
  { code: "en", name: "English", flag: "" },
];


export default function ConsularBot() {
  // Tenant branding — fetched once on mount from /api/consular/widget-config.
  // Everything in this component reads through BOT_CONFIG / GREETING_MESSAGE
  // / ADVISORY_MESSAGES / SUPPORTED_LANGUAGES so the brand strings stay in
  // one place and fall back to neutral defaults until the fetch resolves.
  const [tenantBranding, setTenantBranding] = useState(null);
  const BOT_CONFIG = {
    title:        tenantBranding?.bot_name        || DEFAULT_BOT_CONFIG.title,
    subtitle:     tenantBranding?.header_tagline  || DEFAULT_BOT_CONFIG.subtitle,
    tagline:      tenantBranding?.footer_copy     || DEFAULT_BOT_CONFIG.tagline,
    organization: tenantBranding?.org_name        || DEFAULT_BOT_CONFIG.organization,
    location:     DEFAULT_BOT_CONFIG.location,
  };
  const GREETING_MESSAGE  = tenantBranding?.greeting || DEFAULT_GREETING;
  // widget-config returns only already-active advisories with no `active`
  // flag, so we stamp it back on so existing `.filter(a => a.active)` calls
  // downstream don't drop them.
  const ADVISORY_MESSAGES = (
    tenantBranding?.advisories?.length
      ? tenantBranding.advisories.map(a => ({ active: true, ...a }))
      : DEFAULT_ADVISORIES
  ) || [];
  const SUPPORTED_LANGUAGES = (
    Array.isArray(tenantBranding?.supported_languages) && tenantBranding.supported_languages.length
      ? tenantBranding.supported_languages.map(l => l?.name || l?.code).filter(Boolean)
      : DEFAULT_LANGUAGES
  );

  // Full language objects (code + name + optional flag) used by the picker.
  // Falls back to a minimal English-only list before widget-config resolves.
  const LANGUAGES = (
    Array.isArray(tenantBranding?.supported_languages) && tenantBranding.supported_languages.length
      ? tenantBranding.supported_languages
          .filter((l) => l?.code && l?.name)
          .map((l) => ({ code: l.code, name: l.name, flag: l.flag || "" }))
      : _FALLBACK_LANGUAGES
  );

  // BCP-47 lookup ({ "hi": "hi-IN", ... }) used by browser Web Speech API.
  // When a tenant entry omits `bcp47_code`, the language code itself is used
  // (e.g. "hi" → "hi"), which most speech APIs accept as a coarse hint.
  const SPEECH_LANG_MAP = (() => {
    const out = {};
    for (const l of (tenantBranding?.supported_languages || [])) {
      if (l?.code) out[l.code] = l.bcp47_code || l.code;
    }
    if (!out.en) out.en = "en-GB"; // safety net for chat default
    return out;
  })();

  // TTS voice preference per language ("female" | "male" | ""). Used by the
  // browser TTS voice-selection heuristic.
  const TTS_VOICE_PREFS = (() => {
    const out = {};
    for (const l of (tenantBranding?.supported_languages || [])) {
      if (l?.code && l.tts_voice_preference) out[l.code] = l.tts_voice_preference;
    }
    return out;
  })();

  // Tenant-driven service catalogue from widget-config. SERVICE_INFO_MAP is a
  // `{key: ServiceShape}` lookup matching the legacy hardcoded SERVICE_INFO
  // shape so the rest of the component doesn't need restructuring.
  // SERVICE_KEYWORDS is built from each service's `keywords` field — empty
  // when a tenant hasn't supplied any (no client-side detection happens).
  const SERVICE_INFO_MAP = (() => {
    const rows = Array.isArray(tenantBranding?.services) ? tenantBranding.services : [];
    const out = {};
    for (const r of rows) {
      const n = _normalizeService(r);
      if (n) out[n.key] = n;
    }
    return out;
  })();
  const SERVICE_KEYWORDS = (() => {
    const out = [];
    for (const svc of Object.values(SERVICE_INFO_MAP)) {
      for (const kw of (svc.keywords || [])) {
        const safe = String(kw).trim();
        if (!safe) continue;
        // Escape regex metacharacters so config-supplied keywords can't break out.
        const escaped = safe.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        out.push({ key: svc.key, pattern: new RegExp(`\\b(${escaped})\\b`, "i") });
      }
    }
    return out;
  })();

  useEffect(() => {
    let cancelled = false;
    fetchBranding()
      .then((b) => { if (!cancelled && b) setTenantBranding(b); })
      .catch(() => { /* fall back silently to defaults */ });
    return () => { cancelled = true; };
  }, []);

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(() => localStorage.getItem("consular_session_id") || null);
  const sessionIdRef = useRef(localStorage.getItem("consular_session_id") || null);
  const [currentStep, setCurrentStep] = useState("register");
  const [isRecording, setIsRecording] = useState(false);
  const [showCamera, setShowCamera] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [enableVoice, setEnableVoice] = useState(true);
  const enableVoiceRef = useRef(true); // always reflects latest value inside async handlers
  const [isTyping, setIsTyping] = useState(false);
  const typingIntervalRef = useRef(null);
  const typingStoppedRef = useRef(false);
  const welcomeBackShownRef = useRef(false); // prevents duplicate welcome-back on StrictMode double-mount
  const [selectedLanguage, setSelectedLanguage] = useState("en");
  const selectedLanguageRef = useRef("en"); // always reflects latest value inside async handlers
  const [showLanguageMenu, setShowLanguageMenu] = useState(false);
  const [showAllLangs, setShowAllLangs] = useState(false);
  const [cameraStream, setCameraStream] = useState(null);
  const [cameraError, setCameraError] = useState(null);
  const [mediaRecorder, setMediaRecorder] = useState(null);
  const [audioChunks, setAudioChunks] = useState([]);
  
  const [docModal, setDocModal] = useState(null); // { doc, msgIndex }
  const replaceInputRef = useRef(null);
  const replacingMsgIndexRef = useRef(null);

  // ── Seva Setu Auth + Application State ───────────────────────────────────────
  const [sevaToken, setSevaToken] = useState(() => sessionStorage.getItem("seva_token") || null);
  const sevaTokenRef = useRef(sessionStorage.getItem("seva_token") || null);
  const [sevaUser, setSevaUser] = useState(null);
  const [sevaAuthStep, setSevaAuthStep] = useState(null); // null|"name_email"|"otp"|"done"
  const [sevaAuthName, setSevaAuthName] = useState("");
  const [sevaAuthEmail, setSevaAuthEmail] = useState("");
  const [sevaOtpInput, setSevaOtpInput] = useState("");
  const [sevaAuthError, setSevaAuthError] = useState("");
  const [sevaAuthLoading, setSevaAuthLoading] = useState(false);
  const [sevaCurrentApp, setSevaCurrentApp] = useState(null);
  const [sevaApps, setSevaApps] = useState([]);
  const [showSevaApps, setShowSevaApps] = useState(false);
  const [sevaSelectedService, setSevaSelectedService] = useState(null);
  const [sevaFormMode, setSevaFormMode] = useState(null); // "upload"|"manual"|null
  const [sevaFormFieldIndex, setSevaFormFieldIndex] = useState(0);
  const [sevaFormData, setSevaFormData] = useState({});
  const [sevaFormInput, setSevaFormInput] = useState("");
  const [sevaUploadingDocName, setSevaUploadingDocName] = useState(null);
  const [sevaServices, setSevaServices] = useState({});
  const [sevaDocPreviews, setSevaDocPreviews] = useState({}); // appId → [{id,name,dataUrl,isPdf}]
  const [isApiLoading, setIsApiLoading] = useState(false);
  const sevaDocInputRef = useRef(null);
  const lastActivityRef = useRef(Date.now());

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);
  const audioRef = useRef(null);
  const messagesEndRef = useRef(null);
  const chatScrollRef = useRef(null);

  // Scroll the chat container directly to avoid page-level scroll jitter
  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (chatScrollRef.current) {
        chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
      }
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (!isTyping) scrollToBottom();
  }, [isTyping]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      const guestToken = "guest_" + Math.random().toString(36).substr(2, 9);
      localStorage.setItem("token", guestToken);
    }

    // Build initial messages array with greeting and active advisories
    const initialMessages = [
      {
        role: "assistant",
        content: GREETING_MESSAGE
      }
    ];

    // Add active advisory messages
    ADVISORY_MESSAGES.filter(adv => adv.active).forEach(advisory => {
      initialMessages.push({
        role: "advisory",
        type: advisory.type,
        title: advisory.title,
        content: advisory.content
      });
    });

    setMessages(initialMessages);

    // Persistence: if a saved session exists, check for an in-progress application
    const savedSession = localStorage.getItem("consular_session_id");
    if (savedSession && !welcomeBackShownRef.current) {
      welcomeBackShownRef.current = true; // guard against StrictMode double-mount
      axios.get(`${API}/consular/session/${savedSession}`)
        .then(res => {
          const flow = res.data?.flow;
          const inProgressStates = ["collecting", "docs_uploading", "docs_pending", "consent_pending", "paused"];
          if (flow && inProgressStates.includes(flow.state)) {
            const serviceName = flow.service
              ? flow.service.charAt(0).toUpperCase() + flow.service.slice(1)
              : "application";
            // Only show tracking ID if one has actually been assigned
            const trackingLine = flow.tracking_id
              ? ` (Tracking ID: \`${flow.tracking_id}\`)`
              : "";
            setMessages(prev => [
              ...prev,
              {
                role: "assistant",
                content: `Welcome back! You have an **in-progress ${serviceName} application**${trackingLine}.\n\nType **continue** to resume where you left off, or **discard** to start fresh.`
              }
            ]);
            // Sync currentStep so the flow UI (quick-reply chips etc.) renders correctly
            setCurrentStep(flow.state);
          } else if (!flow || !inProgressStates.includes(flow.state)) {
            // Flow is idle/completed — nothing to restore, clear stale flag
            welcomeBackShownRef.current = false;
          }
        })
        .catch(() => {
          // Session expired or not found — clear it silently
          localStorage.removeItem("consular_session_id");
          sessionIdRef.current = null;
          setSessionId(null);
          welcomeBackShownRef.current = false;
        });
    }
  }, []);

  // Cleanup camera stream on unmount
  useEffect(() => {
    return () => {
      if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
      }
    };
  }, [cameraStream]);

  // Load services catalogue on mount
  useEffect(() => {
    fetch(`${API}/seva-setu/services`)
      .then(r => r.json())
      .then(setSevaServices)
      .catch(() => {});
  }, []);

  // Inactivity auto-logout — per-tenant duration via widget-config.
  // Falls back to 10 minutes if the tenant hasn't overridden it.
  useEffect(() => {
    if (!sevaToken) return;
    const inactivityMinutes = Number(tenantBranding?.security?.client_inactivity_minutes) || 10;
    const inactivityMs = inactivityMinutes * 60 * 1000;
    const touch = () => { lastActivityRef.current = Date.now(); };
    window.addEventListener("mousemove", touch);
    window.addEventListener("keydown", touch);
    window.addEventListener("click", touch);
    const checkIntervalMs = Number(tenantBranding?.platform?.inactivity_check_ms) || 30000;
    const tick = setInterval(() => {
      if (Date.now() - lastActivityRef.current > inactivityMs) {
        handleSevaLogout(true);
      }
    }, checkIntervalMs);
    return () => {
      clearInterval(tick);
      window.removeEventListener("mousemove", touch);
      window.removeEventListener("keydown", touch);
      window.removeEventListener("click", touch);
    };
  }, [sevaToken]); // eslint-disable-line

  // ── Seva Setu API helpers ────────────────────────────────────────────────────

  const sevaApi = async (method, path, body, token) => {
    const headers = { "Content-Type": "application/json" };
    if (token || sevaTokenRef.current) headers["Authorization"] = `Bearer ${token || sevaTokenRef.current}`;
    const res = await fetch(`${API}/seva-setu${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Request failed");
    return data;
  };

  const handleSevaLogout = async (isTimeout = false) => {
    // Save text-only chat history to DB before clearing
    const saveable = messages
      .filter(m => (m.role === "user" || m.role === "assistant") && m.content)
      .map(m => ({ role: m.role, content: m.content }));
    try {
      await sevaApi("POST", "/auth/logout", { chat_history: saveable });
    } catch {}

    // Clear Seva Setu auth + application state
    sessionStorage.removeItem("seva_token");
    sessionStorage.removeItem("seva_user");
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

    // Clear consular session too
    localStorage.removeItem("consular_session_id");
    sessionIdRef.current = null;
    setSessionId(null);
    welcomeBackShownRef.current = false;

    // Reset chat to initial greeting
    const freshMessages = [{ role: "assistant", content: GREETING_MESSAGE }];
    ADVISORY_MESSAGES.filter(a => a.active).forEach(adv => {
      freshMessages.push({ role: "advisory", type: adv.type, title: adv.title, content: adv.content });
    });
    setMessages(freshMessages);
    setCurrentStep("register");

    if (isTimeout) {
      toast.info("⏱️ Logged out due to inactivity. Your applications are saved and accessible via your Reference ID.");
    }
  };

  const handleSevaShowInfo = (svcKey) => {
    const svcInfo = SERVICE_INFO_MAP[svcKey];
    if (!svcInfo) return;
    setMessages(prev => [...prev, { role: "seva_service_info", svc: svcInfo }]);
  };

  const handleSevaStartAuth = async (service) => {
    setSevaSelectedService(service);
    setSevaAuthStep("name_email");
    setSevaAuthError("");
    setMessages(prev => [...prev, {
      role: "assistant",
      content: `Great! To apply for **${service.name}**, I need to verify your identity first.\n\nPlease enter your details below.`
    }]);
  };

  const handleSevaSubmitNameEmail = async () => {
    if (!sevaAuthName.trim() || !sevaAuthEmail.trim()) {
      setSevaAuthError("Please enter both your name and email address.");
      return;
    }
    const emailRx = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
    if (!emailRx.test(sevaAuthEmail.trim())) {
      setSevaAuthError("Invalid email format. Please check and try again.");
      return;
    }
    setSevaAuthLoading(true);
    setIsApiLoading(true);
    setSevaAuthError("");
    try {
      const res = await sevaApi("POST", "/auth/start", { name: sevaAuthName.trim(), email: sevaAuthEmail.trim().toLowerCase() });
      setSevaAuthStep("otp");
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `📧 An OTP has been sent to **${sevaAuthEmail.trim()}**. Please enter it below to continue.\n\n*Valid for 10 minutes.*`
      }]);
      if (res.is_new_user === false) {
        setMessages(prev => [...prev, {
          role: "assistant",
          content: "ℹ️ We found an existing account with this email. You can view your past applications after logging in."
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
    if (!sevaOtpInput.trim()) { setSevaAuthError("Please enter the OTP."); return; }
    setSevaAuthLoading(true);
    setIsApiLoading(true);
    setSevaAuthError("");
    try {
      const res = await sevaApi("POST", "/auth/verify-otp", { email: sevaAuthEmail.trim().toLowerCase(), otp: sevaOtpInput.trim() });
      const token = res.session_token;
      sessionStorage.setItem("seva_token", token);
      sessionStorage.setItem("seva_user", JSON.stringify(res.user));
      sevaTokenRef.current = token;
      setSevaToken(token);
      setSevaUser(res.user);
      setSevaAuthStep("done");
      lastActivityRef.current = Date.now();

      // Create application for the selected service
      if (sevaSelectedService) {
        const appRes = await sevaApi("POST", "/applications", { service_type: sevaSelectedService.key }, token);
        setSevaCurrentApp(appRes);
        const svc = sevaSelectedService;

        if (appRes.service_category === "TYPE_A") {
          setMessages(prev => [...prev, {
            role: "assistant",
            content: `✅ **Verified!** Your Reference ID is \`${appRes.reference_id}\`.\n\n🔗 Redirecting you to the official government portal for **${svc.name}**...\n\nYour Reference ID has been created. Click below to open the portal.`
          }, {
            role: "seva_type_a",
            service: appRes,
            govUrl: appRes.gov_url,
          }]);
        } else {
          setMessages(prev => [...prev, {
            role: "assistant",
            content: `✅ **Verified!** Your Reference ID is \`${appRes.reference_id}\`.\n\nNow let's complete your **${svc.name}** application.\n\nHow would you like to fill in your details?`
          }, {
            role: "seva_form_mode",
            appId: appRes.application_id,
          }]);
        }
      }
    } catch (e) {
      setSevaAuthError(e.message);
    } finally {
      setSevaAuthLoading(false);
      setIsApiLoading(false);
    }
  };

  const handleSevaChooseFormMode = (mode) => {
    setSevaFormMode(mode);
    const fields = sevaCurrentApp?.fields || [];
    if (mode === "manual") {
      const prefilledData = { full_name: sevaUser?.name || "", email: sevaUser?.email || "" };
      setSevaFormData(prefilledData);
      const firstUnfilled = fields.findIndex(f => !prefilledData[f.key]);
      const startIdx = firstUnfilled >= 0 ? firstUnfilled : 0;
      setSevaFormFieldIndex(startIdx);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `📝 **Manual Form Entry**\n\nLet's fill in your details step by step. I'll ask one question at a time.\n\n**${fields[startIdx]?.label}:**`
      }]);
    } else {
      const svcInfo = sevaServices[sevaSelectedService?.key] || {};
      const docs = svcInfo.documents || sevaCurrentApp?.documents_required || [];
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `📤 **Upload Documents**\n\nPlease upload the required documents. I'll extract your details automatically.\n\n**Required documents:**\n${docs.map(d => `• ${d}`).join("\n")}\n\nUpload each document using the upload button below.`
      }, {
        role: "seva_doc_upload",
        appId: sevaCurrentApp?.application_id,
        docs: docs,
      }]);
    }
  };

  const handleSevaFormFieldSubmit = async () => {
    const fields = sevaCurrentApp?.fields || [];
    const value = sevaFormInput.trim();
    const field = fields[sevaFormFieldIndex];

    // Validation
    if (!value) {
      toast.error(`${field.label} is required.`);
      return;
    }
    if (field.key === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) {
      toast.error("Please enter a valid email address.");
      return;
    }
    if ((field.key === "dob" || field.key === "marriage_date") && !/^\d{2}\/\d{2}\/\d{4}$/.test(value)) {
      toast.error("Please use DD/MM/YYYY format (e.g. 15/08/1990).");
      return;
    }
    if (field.key === "phone" && !/^\+?[\d\s\-]{7,15}$/.test(value)) {
      toast.error("Please enter a valid phone number.");
      return;
    }

    const newData = { ...sevaFormData, [field.key]: value };
    setSevaFormData(newData);
    setSevaFormInput("");

    setMessages(prev => [...prev, { role: "user", content: value }]);

    const nextIndex = sevaFormFieldIndex + 1;
    if (nextIndex < fields.length) {
      setSevaFormFieldIndex(nextIndex);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `✓ Got it.\n\n**${fields[nextIndex].label}:**`
      }]);
    } else {
      // All fields filled — save, show summary, then show doc upload for TYPE_B services
      setIsApiLoading(true);
      try {
        await sevaApi("PUT", `/applications/${sevaCurrentApp.application_id}`, { form_data: newData });
        setSevaCurrentApp(prev => ({ ...prev, form_data: newData }));
        const summary = Object.entries(newData)
          .map(([k, v]) => `• **${k.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}:** ${v}`)
          .join("\n");
        const svcInfo = sevaServices[sevaSelectedService?.key] || {};
        const docs = svcInfo.documents || sevaCurrentApp?.documents_required || [];
        setMessages(prev => [...prev, {
          role: "assistant",
          content: `✅ **Form complete!** Here's your summary:\n\n${summary}\n\nNow please upload the required supporting documents below.`
        }, {
          role: "seva_doc_upload",
          appId: sevaCurrentApp.application_id,
          docs,
        }]);
        setSevaFormMode(null);
      } catch (e) {
        toast.error("Failed to save form data. Please try again.");
      } finally {
        setIsApiLoading(false);
      }
    }
  };

  const handleSevaPreviewPdf = async () => {
    if (!sevaCurrentApp) return;
    setIsApiLoading(true);
    try {
      if (Object.keys(sevaFormData).length > 0) {
        await sevaApi("PUT", `/applications/${sevaCurrentApp.application_id}`, { form_data: sevaFormData });
      }
      const url = `${API}/seva-setu/applications/${sevaCurrentApp.application_id}/preview?token=${encodeURIComponent(sevaTokenRef.current)}`;
      const a = document.createElement("a");
      a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
    } catch (e) {
      toast.error("Failed to generate PDF preview.");
    } finally {
      setIsApiLoading(false);
    }
  };

  const handleSevaUploadDoc = async (file, docName) => {
    if (!file || !sevaCurrentApp) return;
    const allowed = (tenantBranding?.security?.upload_allowed_mime_types
                    || ["application/pdf", "image/jpeg", "image/png", "image/jpg"]);
    if (!allowed.includes(file.type)) { toast.error(`Unsupported file type. Allowed: ${allowed.join(", ")}.`); return; }
    const maxBytes = Number(tenantBranding?.security?.upload_max_bytes) || (5 * 1024 * 1024);
    if (file.size > maxBytes) {
      const maxMB = (maxBytes / (1024 * 1024)).toFixed(1);
      toast.error(`File too large. Max size is ${maxMB} MB.`);
      return;
    }

    // Capture preview dataUrl before upload
    const previewDataUrl = await new Promise(resolve => {
      const reader = new FileReader();
      reader.onload = e => resolve(e.target.result);
      reader.readAsDataURL(file);
    });

    setSevaUploadingDocName(docName);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("app_id", sevaCurrentApp.application_id);
    fd.append("doc_name", docName || file.name);

    try {
      const res = await fetch(`${API}/seva-setu/upload-document`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${sevaTokenRef.current}` },
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");

      // Store preview (replace if same docName exists)
      const appId = sevaCurrentApp.application_id;
      setSevaDocPreviews(prev => ({
        ...prev,
        [appId]: [
          ...(prev[appId] || []).filter(d => d.name !== (docName || file.name)),
          { id: data.document?.id || Date.now().toString(), name: docName || file.name, dataUrl: previewDataUrl, isPdf: file.type === "application/pdf" },
        ],
      }));

      if (data.ocr_fields && Object.keys(data.ocr_fields).length > 0) {
        const extracted = Object.entries(data.ocr_fields)
          .map(([k, v]) => `• **${k.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}:** ${v}`)
          .join("\n");
        setMessages(prev => [...prev, {
          role: "assistant",
          content: `📋 **OCR extracted from ${docName || file.name}** (please verify):\n${extracted}`,
        }]);
        setSevaFormData(prev => {
          const merged = { ...prev, ...data.ocr_fields };
          sevaApi("PUT", `/applications/${appId}`, { form_data: merged }).catch(() => {});
          return merged;
        });
      }
      toast.success(`${docName || file.name} uploaded!`);
    } catch (e) {
      toast.error(e.message || "Upload failed");
    } finally {
      setSevaUploadingDocName(null);
    }
  };

  const handleSevaRemoveDoc = async (appId, docId, docName) => {
    setIsApiLoading(true);
    try {
      await sevaApi("DELETE", `/applications/${appId}/documents/${docId}`);
      setSevaDocPreviews(prev => ({
        ...prev,
        [appId]: (prev[appId] || []).filter(d => d.id !== docId),
      }));
      toast.success(`${docName} removed.`);
    } catch (e) {
      toast.error("Failed to remove document.");
    } finally {
      setIsApiLoading(false);
    }
  };

  const handleSevaSubmitApp = async () => {
    if (!sevaCurrentApp) return;
    setIsApiLoading(true);
    try {
      if (Object.keys(sevaFormData).length > 0) {
        await sevaApi("PUT", `/applications/${sevaCurrentApp.application_id}`, { form_data: sevaFormData });
      }
      const res = await sevaApi("POST", `/applications/${sevaCurrentApp.application_id}/submit`);
      setSevaCurrentApp(prev => ({ ...prev, status: "submitted" }));
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `📧 **Application Submitted for Review!**\n\nA review email has been sent to **${sevaUser?.email}** with a link to confirm your application within 24 hours.\n\nReference ID: \`${res.reference_id}\``
      }]);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setIsApiLoading(false);
    }
  };

  const handleSevaConfirmApp = async () => {
    if (!sevaCurrentApp) return;
    setIsApiLoading(true);
    try {
      if (Object.keys(sevaFormData).length > 0) {
        await sevaApi("PUT", `/applications/${sevaCurrentApp.application_id}`, { form_data: sevaFormData });
      }
      const res = await sevaApi("POST", `/applications/${sevaCurrentApp.application_id}/confirm`);
      setSevaCurrentApp(prev => ({ ...prev, status: "confirmed" }));
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `🎉 **Application Confirmed!**\n\nYour **${sevaCurrentApp.service_name}** application has been confirmed.\n\nA confirmation email with your **PDF** has been sent to ${sevaUser?.email}.\n\nReference: \`${res.reference_id}\``
      }]);
      setTimeout(() => {
        const pdfUrl = `${API}/seva-setu/applications/${sevaCurrentApp.application_id}/pdf?token=${encodeURIComponent(sevaTokenRef.current)}`;
        const a = document.createElement("a");
        a.href = pdfUrl; a.target = "_blank"; a.rel = "noopener noreferrer";
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
      }, 600);
      const postConfirm = sevaSelectedService?.post_confirm_message;
      if (postConfirm) {
        setMessages(prev => [...prev, {
          role: "assistant",
          content: postConfirm
        }]);
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setIsApiLoading(false);
    }
  };

  const handleSevaFetchApps = async () => {
    setIsApiLoading(true);
    try {
      const res = await sevaApi("GET", "/applications");
      setSevaApps(res.applications || []);
      setShowSevaApps(true);
    } catch (e) {
      toast.error("Failed to load applications. Please try again.");
    } finally {
      setIsApiLoading(false);
    }
  };

  const handleSevaTypeAFinalize = async (appId, govRef) => {
    if (!govRef.trim()) { toast.error("Please enter your government reference number."); return; }
    setIsApiLoading(true);
    try {
      const res = await sevaApi("POST", `/applications/${appId}/type-a-finalize`, { gov_reference: govRef.trim() });
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `✅ **Application Recorded!**\n\nGov Reference: \`${govRef.trim()}\`\n\nA confirmation email with your PDF has been sent to **${sevaUser?.email}**.\n\nReference: \`${res.reference_id}\``,
      }]);
      toast.success("Confirmation email sent with PDF!");
    } catch (e) {
      toast.error(e.message || "Failed to finalize application.");
    } finally {
      setIsApiLoading(false);
    }
  };

  const handleSevaDownloadPdf = (appId) => {
    const t = sevaTokenRef.current;
    window.open(`${API}/seva-setu/applications/${appId}/pdf${t ? `?token=${encodeURIComponent(t)}` : ""}`, "_blank");
  };

  // Notify backend that a document was uploaded so the flow advances
  const sendDocumentToBackend = useCallback(async (imageBase64) => {
    const UPLOAD_ACK = "📎 _Document uploaded, processing…_";
    setIsTyping(true);
    setMessages((prev) => [...prev, { role: "assistant", content: UPLOAD_ACK }]);
    try {
      const res = await fetch(`${API}/consular/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: "Document uploaded",
          image_base64: imageBase64,
          session_id: sessionIdRef.current,
          user_id: "guest",
          enable_voice: false,
          language: selectedLanguageRef.current,
        }),
        signal: AbortSignal.timeout(Number(tenantBranding?.platform?.chat_stream_timeout_ms) || 60000),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullText = "";
      let gotChunk = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.session_id && evt.session_id !== sessionIdRef.current) {
              sessionIdRef.current = evt.session_id;
              setSessionId(evt.session_id);
              localStorage.setItem("consular_session_id", evt.session_id);
            }
            if (evt.error) {
              toast.error(evt.error);
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: "assistant", content: evt.error };
                return updated;
              });
              setIsTyping(false);
              return;
            }
            if (evt.chunk) {
              if (!gotChunk) {
                fullText = "";
                gotChunk = true;
              }
              fullText += evt.chunk;
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: "assistant", content: fullText };
                return updated;
              });
            }
            if (evt.done) {
              if (enableVoiceRef.current && fullText) speakWithBackend(fullText);
            }
          } catch {}
        }
      }
      // Stream closed without ever sending a chunk → leave a definitive message
      // instead of the "processing…" placeholder.
      if (!gotChunk) {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", content: "Document received. Please continue." };
          return updated;
        });
      }
    } catch (e) {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", content: "Document received. Please continue." };
        return updated;
      });
    } finally {
      setIsTyping(false);
    }
  }, []);

  const handleSend = async (overrideText) => {
    if (isTyping) return;
    const text = overrideText !== undefined ? overrideText : input;
    if (!text.trim()) {
      toast.error("Please type a message before sending.");
      return;
    }

    // Stop any currently playing audio
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setIsSpeaking(false);
    }

    const userMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMessage]);
    const messageText = text;
    setInput("");

    // Detect service keyword — let LLM answer from knowledge base, then show Apply card
    let detectedServiceKey = null;
    if (!sevaAuthStep) {
      const matched = SERVICE_KEYWORDS.find(({ pattern }) => pattern.test(messageText));
      if (matched && SERVICE_INFO_MAP[matched.key]) {
        detectedServiceKey = matched.key;
      }
    }

    // Show typing indicator
    setIsTyping(true);

    // Add empty bot message placeholder — filled in as chunks arrive
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const res = await fetch(`${API}/consular/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: messageText,
          session_id: sessionIdRef.current,
          user_id: "guest",
          enable_voice: false,   // voice not supported over stream
          language: selectedLanguageRef.current,
        }),
        signal: AbortSignal.timeout(Number(tenantBranding?.platform?.chat_stream_timeout_ms) || 60000),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop(); // keep incomplete tail

        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          let evt;
          try { evt = JSON.parse(part.slice(6)); } catch { continue; }

          if (evt.error) {
            toast.error(evt.error);
            setMessages((prev) => prev.slice(0, -1));
            setIsTyping(false);
            return;
          }
          if (evt.chunk) {
            fullText += evt.chunk;
            setMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = { role: "assistant", content: fullText };
              return updated;
            });
          }
          if (evt.done) {
            const sid = evt.session_id;
            // Always sync — backend may create a new session when old one expires
            if (sid && sid !== sessionIdRef.current) {
              sessionIdRef.current = sid;
              setSessionId(sid);
              localStorage.setItem("consular_session_id", sid);
            }
            setCurrentStep(evt.step || "complete");
            if (evt.step === "submitted") {
              localStorage.removeItem("consular_session_id");
              sessionIdRef.current = null;
              setSessionId(null);
              if (evt.pdf_url) {
                setTimeout(() => {
                  window.open(`${process.env.REACT_APP_BACKEND_URL}${evt.pdf_url}`, "_blank");
                }, 800);
              }
            }
            // After LLM responds with knowledge base info, show Apply card for detected service
            if (detectedServiceKey && SERVICE_INFO_MAP[detectedServiceKey]) {
              setMessages(prev => [...prev, {
                role: "seva_service_action",
                svc: SERVICE_INFO_MAP[detectedServiceKey],
              }]);
            }
            // Speak the completed response if voice is enabled
            if (enableVoiceRef.current && fullText) {
              speakWithBackend(fullText);
            }
          }
        }
      }
    } catch (error) {
      console.error("Chat error:", error);
      toast.error("Failed to send message. Please try again.");
      setMessages((prev) => prev.slice(0, -2)); // remove user + empty bot
    } finally {
      setIsTyping(false);
    }
  };

  const typeMessage = async (fullMessage) => {
    typingStoppedRef.current = false;

    return new Promise((resolve) => {
      let currentText = "";
      let index = 0;
      const typingSpeed = 15;

      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      const typeInterval = setInterval(() => {
        if (typingStoppedRef.current) {
          clearInterval(typeInterval);
          typingIntervalRef.current = null;
          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = { role: "assistant", content: fullMessage };
            return newMessages;
          });
          resolve();
          return;
        }

        if (index < fullMessage.length) {
          currentText += fullMessage[index];
          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = { role: "assistant", content: currentText };
            return newMessages;
          });
          index++;
        } else {
          clearInterval(typeInterval);
          typingIntervalRef.current = null;
          resolve();
        }
      }, typingSpeed);

      typingIntervalRef.current = typeInterval;
    });
  };

  const handleStop = () => {
    if (!isTyping) return;
    typingStoppedRef.current = true;
    setIsTyping(false);
  };

  const playAudio = (audioBase64) => {
    try {
      // Stop any currently playing audio immediately
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.onended = null;
        audioRef.current.onerror = null;
        audioRef.current = null;
      }

      setIsSpeaking(true);
      const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
      audioRef.current = audio;

      audio.onended = () => {
        setIsSpeaking(false);
        audioRef.current = null;
      };

      audio.onerror = () => {
        setIsSpeaking(false);
        audioRef.current = null;
        toast.error("Audio playback failed");
      };

      audio.play();
    } catch (error) {
      setIsSpeaking(false);
      console.error("Audio play error:", error);
    }
  };

  // Browser TTS — strips markdown, speaks in the selected language
  const speakText = (text) => {
    if (!enableVoiceRef.current) return;
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();

    // Voices may not be loaded yet on first call — wait for them
    if (window.speechSynthesis.getVoices().length === 0) {
      window.speechSynthesis.onvoiceschanged = () => {
        window.speechSynthesis.onvoiceschanged = null;
        speakText(text);
      };
      return;
    }

    // Strip markdown so the bot doesn't read "asterisk asterisk" etc.
    const plain = text
      .replace(/\*\*?([^*]+)\*\*?/g, "$1")
      .replace(/#{1,6}\s/g, "")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/`[^`]+`/g, "")
      .replace(/•/g, "")
      .replace(/\n+/g, " ")
      .trim();

    if (!plain) return;

    const targetLang = SPEECH_LANG_MAP[selectedLanguageRef.current] || "en-GB";
    const langFamily = targetLang.split("-")[0];

    // Voice gender bias: tenants set ``tts_voice_preference`` per language
    // on bot_config (``female`` / ``male`` / unset = neutral). When set, we
    // prefer matching voices first; otherwise we accept any voice for the
    // target language.
    const VOICE_NAME_HINTS = {
      female: /heera|priya|aditi|neerja|kalpana|swara|zira|samantha|karen|moira|fiona|tessa|victoria|linda|emma|aria|jenny|sonia|natasha|susan|hazel|amelie|alice|alva|anna|claire|carmit|damayanti|ioana|joana|laura|lekha|luciana|mariska|mei\-jia|melina|milena|monica|paulina|sangeeta|sara|satu|sin\-ji|yelda|yuna|zosia|female|woman|girl/i,
      male:   /david|mark|james|fred|tom|alex|daniel|diego|jorge|luca|miguel|nicolas|oliver|rishi|ravi|amit|male|man|boy/i,
    };
    const allVoices  = window.speechSynthesis.getVoices();
    const voicePref  = TTS_VOICE_PREFS[selectedLanguageRef.current] || "";
    const preferRx   = VOICE_NAME_HINTS[voicePref] || null;
    const matches    = (v) => !preferRx || preferRx.test(v.name);

    // Find a voice for the selected language only.
    // Never fall back to an English voice when another language is selected —
    // instead leave .voice unset so Chrome/Edge use their cloud TTS engine
    // (Google TTS / Windows Speech) for the target language automatically.
    const matchingVoice =
      allVoices.find((v) => matches(v) && v.lang === targetLang) ||
      allVoices.find((v) => matches(v) && v.lang.startsWith(langFamily + "-")) ||
      allVoices.find((v) => v.lang === targetLang) ||
      allVoices.find((v) => v.lang.startsWith(langFamily + "-")) ||
      null;

    // Chrome bug: utterances > ~300 chars may cut off silently.
    // Split on sentence boundaries and queue them all.
    const CHUNK_SIZE = Number(tenantBranding?.platform?.tts_chunk_size_chars) || 250;
    const sentences = plain.match(/[^।॥.!?]+[।॥.!?]*/g) || [plain];
    const chunks = [];
    let current = "";
    for (const s of sentences) {
      if ((current + s).length > CHUNK_SIZE && current) {
        chunks.push(current.trim());
        current = s;
      } else {
        current += s;
      }
    }
    if (current.trim()) chunks.push(current.trim());

    chunks.forEach((chunk, i) => {
      const utter = new SpeechSynthesisUtterance(chunk);
      utter.lang = targetLang;
      utter.rate = 1.0;
      if (matchingVoice) {
        utter.voice = matchingVoice;
        utter.lang  = matchingVoice.lang;
      }
      if (i === 0)               utter.onstart = () => setIsSpeaking(true);
      if (i === chunks.length - 1) {
        utter.onend   = () => setIsSpeaking(false);
        utter.onerror = () => setIsSpeaking(false);
      }
      window.speechSynthesis.speak(utter);
    });
  };

  // Play a base64 audio clip and resolve when it finishes (or errors)
  const playAudioAsync = useCallback((audioBase64) => {
    return new Promise((resolve) => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.onended = null;
        audioRef.current.onerror = null;
        audioRef.current = null;
      }
      setIsSpeaking(true);
      const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
      audioRef.current = audio;
      audio.onended = () => { setIsSpeaking(false); audioRef.current = null; resolve(); };
      audio.onerror = () => { setIsSpeaking(false); audioRef.current = null; resolve(); };
      audio.play().catch(() => { setIsSpeaking(false); resolve(); });
    });
  }, []);

  // Fetch TTS audio for one chunk from backend
  const fetchTTSChunk = useCallback(async (chunk) => {
    const res = await fetch(`${API}/consular/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: chunk, language: selectedLanguageRef.current }),
      signal: AbortSignal.timeout(Number(tenantBranding?.platform?.tts_timeout_ms) || 30000),
    });
    if (!res.ok) throw new Error(`TTS HTTP ${res.status}`);
    const data = await res.json();
    return data.audio_base64 || null;
  }, []);

  // Backend TTS — splits text into sentence chunks, fires all fetches in parallel,
  // then plays them in order so audio starts as soon as the first chunk is ready.
  // Falls back to browser Web Speech API if the backend is unavailable.
  const speakWithBackend = useCallback(async (text) => {
    if (!enableVoiceRef.current) return;
    if (window.speechSynthesis) window.speechSynthesis.cancel();

    // Strip markdown so TTS doesn't read "asterisk asterisk" etc.
    const plain = text
      .replace(/\*\*?([^*]+)\*\*?/g, "$1")
      .replace(/#{1,6}\s/g, "")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/`[^`]+`/g, "")
      .replace(/•|-\s/g, "")
      .replace(/\n{2,}/g, ". ")
      .replace(/\n/g, " ")
      .trim();
    if (!plain) return;

    // Split on sentence/paragraph boundaries into ~300-char chunks
    const CHUNK = 300;
    const sentences = plain.match(/[^।॥.!?]+[।॥.!?]*/g) || [plain];
    const chunks = [];
    let cur = "";
    for (const s of sentences) {
      if (cur && (cur + s).length > CHUNK) { chunks.push(cur.trim()); cur = s; }
      else cur += s;
    }
    if (cur.trim()) chunks.push(cur.trim());

    // Fire all TTS requests in parallel — don't wait for one before starting the next
    const audioPromises = chunks.map(chunk => fetchTTSChunk(chunk).catch(() => null));

    // Play in order: wait for each clip in sequence
    let anyPlayed = false;
    for (const promise of audioPromises) {
      if (!enableVoiceRef.current) break;
      const audio = await promise;
      if (audio) { await playAudioAsync(audio); anyPlayed = true; }
    }

    if (!anyPlayed) {
      // All backend calls failed — fall back to browser TTS
      speakText(plain);
    }
  }, [fetchTTSChunk, playAudioAsync]);

  // =====================================================================
  // ENHANCED MICROPHONE INPUT - Using OpenAI Whisper via Backend
  // =====================================================================
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 44100
        } 
      });
      
      const recorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm'
      });
      
      const chunks = [];
      
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunks.push(e.data);
        }
      };
      
      recorder.onstop = async () => {
        const audioBlob = new Blob(chunks, { type: 'audio/webm' });
        stream.getTracks().forEach(track => track.stop());
        
        // Send to backend for Whisper transcription
        try {
          toast.info("🎤 Processing voice input...");
          
          const formData = new FormData();
          formData.append('audio', audioBlob, 'recording.webm');
          formData.append('language', selectedLanguageRef.current);

          const response = await axios.post(`${API}/consular/voice-input`, formData, {
            headers: {
              'Content-Type': 'multipart/form-data'
            }
          });

          if (response.data.success && response.data.transcription) {
            setInput(response.data.transcription);
            toast.success("✅ Voice captured successfully!");
          } else {
            toast.error("Voice recognition failed. Please try again or type your message.");
          }
        } catch (err) {
          console.error("Voice processing error:", err);

          // Fallback to Web Speech API if backend fails
          if ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window) {
            toast.info("Trying browser speech recognition...");
            const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
            recognition.lang = SPEECH_LANG_MAP[selectedLanguageRef.current] || 'en-GB';
            recognition.interimResults = false;
            
            recognition.onresult = (event) => {
              const transcript = event.results[0][0].transcript;
              setInput(transcript);
              toast.success("Voice captured (browser)!");
            };
            
            recognition.onerror = () => {
              toast.error("Voice recognition failed. Please type your message.");
            };
            
            recognition.start();
          } else {
            toast.error("Voice recognition unavailable. Please type your message.");
          }
        }
      };
      
      recorder.start();
      setMediaRecorder(recorder);
      setIsRecording(true);
      toast.info("🎤 Recording... Click again to stop");
      
    } catch (error) {
      console.error("Microphone access error:", error);
      if (error.name === 'NotAllowedError') {
        toast.error("Microphone access denied. Please allow microphone access in your browser settings.");
      } else if (error.name === 'NotFoundError') {
        toast.error("No microphone found. Please connect a microphone.");
      } else {
        toast.error("Failed to access microphone. Please try again.");
      }
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
      setIsRecording(false);
    }
  }, [mediaRecorder]);

  const handleVoice = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  // =====================================================================
  // ENHANCED CAMERA INPUT - Using MediaDevices API
  // =====================================================================
  const startCamera = useCallback(async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'environment', // Use back camera on mobile
          width: { ideal: 1920 },
          height: { ideal: 1080 }
        }
      });
      
      setCameraStream(stream);
      setShowCamera(true);
      
      // Wait for dialog to open, then attach stream
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      }, 100);
      
    } catch (error) {
      console.error("Camera access error:", error);
      if (error.name === 'NotAllowedError') {
        setCameraError("Camera access denied. Please allow camera access in your browser settings.");
        toast.error("Camera access denied. Please check browser permissions.");
      } else if (error.name === 'NotFoundError') {
        setCameraError("No camera found. Please connect a camera.");
        toast.error("No camera found.");
      } else {
        setCameraError("Failed to access camera. Please try again.");
        toast.error("Failed to access camera.");
      }
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (cameraStream) {
      cameraStream.getTracks().forEach(track => track.stop());
      setCameraStream(null);
    }
    setShowCamera(false);
    setCameraError(null);
  }, [cameraStream]);

  const captureImage = useCallback(async () => {
    if (!videoRef.current || !canvasRef.current) return;
    
    const video = videoRef.current;
    const canvas = canvasRef.current;
    const context = canvas.getContext('2d');
    
    // Set canvas size to video size
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    // Draw video frame to canvas
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    
    // Get image as base64
    const imageBase64 = canvas.toDataURL('image/jpeg', 0.8).split(',')[1];
    
    stopCamera();
    toast.success("Document captured!");
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        type: "document",
        content: "📄 **Document captured.** You can continue filling the form.",
        docData: { id: Date.now(), name: "Captured document", dataUrl: `data:image/jpeg;base64,${imageBase64}`, isPdf: false }
      }
    ]);
    sendDocumentToBackend(imageBase64);
  }, [sessionId, stopCamera, sendDocumentToBackend]);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif', 'application/pdf'];
    if (!allowedTypes.includes(file.type)) {
      toast.error('Invalid file format. Please upload JPG, PNG, WEBP, GIF, or PDF.');
      return;
    }

    // Use the tenant-configured upload cap; default 10 MB for chat
    // uploads (looser than the 5 MB Seva Setu doc upload).
    const _chatMaxBytes = Number(tenantBranding?.security?.upload_max_bytes) || (10 * 1024 * 1024);
    if (file.size > _chatMaxBytes) {
      const _chatMaxMB = (_chatMaxBytes / (1024 * 1024)).toFixed(1);
      toast.error(`File size exceeds ${_chatMaxMB} MB limit.`);
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      const base64 = dataUrl.split(',')[1];
      const isPdf = file.type === 'application/pdf';
      toast.success('Document uploaded!');
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          type: "document",
          content: `📄 **Document received:** ${file.name}. You can continue filling the form.`,
          docData: { id: Date.now(), name: file.name, dataUrl, isPdf }
        }
      ]);
      sendDocumentToBackend(base64);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  // ── Doc actions ────────────────────────────────────────────────────────────
  const handleDocReplace = (msgIndex) => {
    replacingMsgIndexRef.current = msgIndex;
    replaceInputRef.current?.click();
  };

  const handleReplaceFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif', 'application/pdf'];
    if (!allowedTypes.includes(file.type)) {
      toast.error('Invalid file format. Please upload JPG, PNG, WEBP, GIF, or PDF.');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      const isPdf = file.type === 'application/pdf';
      const idx = replacingMsgIndexRef.current;
      setMessages((prev) => {
        const updated = [...prev];
        updated[idx] = {
          ...updated[idx],
          content: `📄 **Document updated:** ${file.name}. You can continue filling the form.`,
          docData: { id: Date.now(), name: file.name, dataUrl, isPdf }
        };
        return updated;
      });
      setDocModal(null);
      toast.success('Document replaced!');
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const handleDocRemove = (msgIndex) => {
    setMessages((prev) => prev.filter((_, i) => i !== msgIndex));
    setDocModal(null);
    toast.success('Document removed.');
  };

  const currentStepIndex = STEPS.findIndex((s) => s.value === currentStep);
  const currentLang = LANGUAGES.find(l => l.code === selectedLanguage) || LANGUAGES[0];

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 to-blue-50 p-6">
      {/* Skip Link for Keyboard Navigation */}
      <a 
        href="#chat-input" 
        className="skip-link"
        tabIndex={0}
      >
        Skip to chat input
      </a>
      
      {/* Live Region for Screen Reader Announcements */}
      <div 
        role="status" 
        aria-live="polite" 
        aria-atomic="true"
        className="sr-only"
        id="status-announcer"
      >
        {isTyping && "Loading..."}
        {isSpeaking && "Playing voice response..."}
      </div>

      <div className="max-w-5xl mx-auto">
        {/* Language Selector - Top Right */}
        <div className="flex justify-end mb-4">
          <div className="relative">
            <Button
              variant="outline"
              onClick={() => setShowLanguageMenu(!showLanguageMenu)}
              className="flex items-center gap-2 bg-white shadow-sm hover:shadow-md transition-all min-h-[44px]"
              data-testid="language-selector"
              aria-haspopup="listbox"
              aria-expanded={showLanguageMenu}
              aria-label={`Current language: ${currentLang.name}. Click to change language`}
            >
              <Globe className="w-4 h-4 text-[#E06F2C]" aria-hidden="true" />
              <span className="text-lg" aria-hidden="true">{currentLang.flag}</span>
              <span className="font-medium">{currentLang.name}</span>
            </Button>
            
            {showLanguageMenu && (
              <div
                className="absolute right-0 mt-2 w-64 bg-white rounded-lg shadow-xl border z-50"
                data-testid="language-menu"
                role="listbox"
                aria-label="Select language"
              >
                <div className="p-2 max-h-80 overflow-y-auto">
                  <p className="text-xs text-gray-500 px-3 py-1 font-semibold uppercase" id="lang-label">Select Language</p>
                  {LANGUAGES.map((lang) => (
                    <button
                      key={lang.code}
                      onClick={() => {
                        if (lang.code === selectedLanguage) {
                          setShowLanguageMenu(false);
                          return;
                        }
                        // Stop any playing audio
                        if (audioRef.current) {
                          audioRef.current.pause();
                          audioRef.current.onended = null;
                          audioRef.current = null;
                          setIsSpeaking(false);
                        }
                        if (window.speechSynthesis) window.speechSynthesis.cancel();

                        // Save & close the old session in DB before starting fresh
                        const oldSessionId = sessionIdRef.current;
                        if (oldSessionId) {
                          fetch(`${API}/consular/session/${oldSessionId}/close`, {
                            method: "POST",
                          }).catch(() => {}); // fire-and-forget, don't block UI
                        }
                        localStorage.removeItem("consular_session_id");
                        sessionIdRef.current = null;
                        setSessionId(null);

                        // Switch language
                        selectedLanguageRef.current = lang.code;
                        setSelectedLanguage(lang.code);
                        setShowLanguageMenu(false);

                        // Reset chat to initial greeting
                        const freshMessages = [{ role: "assistant", content: GREETING_MESSAGE }];
                        ADVISORY_MESSAGES.filter(a => a.active).forEach(adv => {
                          freshMessages.push({ role: "advisory", type: adv.type, title: adv.title, content: adv.content });
                        });
                        setMessages(freshMessages);
                        setCurrentStep("register");
                        welcomeBackShownRef.current = false;

                        toast.success(`Language changed to ${lang.name} — new session started`);
                      }}
                      className={`w-full flex items-center gap-3 px-3 py-2 rounded-md transition-colors min-h-[44px] ${
                        selectedLanguage === lang.code 
                          ? 'bg-orange-50 text-[#E06F2C]' 
                          : 'hover:bg-gray-50'
                      }`}
                      data-testid={`lang-option-${lang.code}`}
                      role="option"
                      aria-selected={selectedLanguage === lang.code}
                    >
                      <span className="text-xl" aria-hidden="true">{lang.flag}</span>
                      <span className="font-medium">{lang.name}</span>
                      {selectedLanguage === lang.code && (
                        <Check className="w-4 h-4 ml-auto text-[#E06F2C]" aria-hidden="true" />
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Progress Stepper */}
        <nav aria-label="Application progress" className="flex justify-center mb-8">
          <ol className="flex items-center w-full max-w-2xl" data-testid="progress-stepper">
            {STEPS.map((step, index) => (
              <React.Fragment key={step.id}>
                <li className="flex flex-col items-center">
                  <div
                    className={`${
                      index <= currentStepIndex
                        ? "bg-[#E06F2C] text-white shadow-lg ring-4 ring-orange-100"
                        : "bg-slate-200 text-slate-500"
                    } w-12 h-12 rounded-full flex items-center justify-center font-bold transition-all`}
                    data-testid={`step-${step.value}`}
                    aria-current={index === currentStepIndex ? "step" : undefined}
                    role="img"
                    aria-label={`Step ${step.id}: ${step.label}${index < currentStepIndex ? ', completed' : index === currentStepIndex ? ', current step' : ''}`}
                  >
                    {index < currentStepIndex ? <Check className="w-6 h-6" aria-hidden="true" /> : <span aria-hidden="true">{step.id}</span>}
                  </div>
                  <span className="text-sm mt-2 font-medium text-[#1A2E40]">{step.label}</span>
                </li>
                {index < STEPS.length - 1 && (
                  <li
                    className={`h-1 flex-1 mx-4 ${index < currentStepIndex ? "bg-[#E06F2C]" : "bg-slate-200"}`}
                    aria-hidden="true"
                    role="presentation"
                  />
                )}
              </React.Fragment>
            ))}
          </ol>
        </nav>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Avatar Section */}
          <div className="lg:col-span-4">
            <div className="glass-card rounded-xl p-6 text-center" data-testid="bot-avatar">
              <div className={`relative w-full aspect-square max-w-xs mx-auto mb-4 rounded-full overflow-hidden transition-all duration-500 ${
                isSpeaking ? 'ring-4 ring-[#2E8B57] ring-offset-4 ring-offset-white shadow-2xl shadow-green-400/50 scale-105' : 'ring-4 ring-[#E06F2C] ring-offset-4 ring-offset-white shadow-xl'
              }`}>
                <div className="relative w-full h-full bg-gradient-to-br from-orange-50 to-blue-50">
                  <img
                    src="https://static.prod-images.emergentagent.com/jobs/41ee56b6-38da-4112-8da3-b4cf6bfcfd91/images/1fc401012f88731c201ca30b4be56212c44bad84c995e7ed04da381c8740f43b.png"
                    alt={BOT_CONFIG.title || 'Bot'}
                    className={`w-full h-full object-cover ${isSpeaking ? 'brightness-110 scale-105' : 'brightness-100 scale-100'} transition-all duration-500`}
                  />
                  
                  {isSpeaking && (
                    <div className="absolute inset-0 bg-gradient-to-t from-green-500/20 to-transparent pointer-events-none">
                      <div className="absolute bottom-1/3 left-1/2 transform -translate-x-1/2">
                        <div className="flex gap-1 animate-pulse">
                          <div className="w-3 h-3 bg-[#2E8B57] rounded-full animate-bounce" style={{animationDelay: '0ms'}}></div>
                          <div className="w-3 h-3 bg-[#2E8B57] rounded-full animate-bounce" style={{animationDelay: '100ms'}}></div>
                          <div className="w-3 h-3 bg-[#2E8B57] rounded-full animate-bounce" style={{animationDelay: '200ms'}}></div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                
                {isSpeaking && (
                  <div className="absolute -bottom-2 left-1/2 transform -translate-x-1/2 z-10">
                    <div className="flex gap-1 bg-white px-4 py-2 rounded-full shadow-lg border-2 border-[#2E8B57]">
                      <div className="flex gap-1">
                        <span className="w-2 h-2 bg-[#2E8B57] rounded-full animate-bounce" style={{animationDelay: '0ms'}}></span>
                        <span className="w-2 h-2 bg-[#2E8B57] rounded-full animate-bounce" style={{animationDelay: '150ms'}}></span>
                        <span className="w-2 h-2 bg-[#2E8B57] rounded-full animate-bounce" style={{animationDelay: '300ms'}}></span>
                      </div>
                      <span className="text-xs font-semibold text-[#2E8B57] ml-2">Speaking</span>
                    </div>
                  </div>
                )}
              </div>
              
              <div className="space-y-3">
                <h2 className="text-xl font-bold text-[#1A2E40] leading-tight">{BOT_CONFIG.title}</h2>
                <p className="text-lg font-semibold text-[#E06F2C]">{BOT_CONFIG.subtitle}</p>
                <p className="text-sm text-gray-600 italic">{BOT_CONFIG.tagline}</p>
                
                <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full transition-all duration-300 ${
                  isSpeaking ? 'bg-gradient-to-r from-green-100 to-green-50' : 'bg-gradient-to-r from-orange-100 to-orange-50'
                }`}>
                  <span className={`w-3 h-3 rounded-full ${isSpeaking ? 'bg-[#2E8B57] animate-pulse' : 'bg-[#E06F2C]'}`}></span>
                  <span className={`text-sm font-semibold ${isSpeaking ? 'text-[#2E8B57]' : 'text-[#1A2E40]'}`}>
                    {isSpeaking ? "🎙️ Speaking..." : "✨ Ready to Assist"}
                  </span>
                </div>
              </div>
              
              {/* Voice Toggle */}
              <div className="mt-6 pt-6 border-t-2 border-gray-100">
                <label className="flex items-center justify-center gap-3 cursor-pointer group">
                  <div className="relative">
                    <input
                      type="checkbox"
                      checked={enableVoice}
                      onChange={(e) => {
                        enableVoiceRef.current = e.target.checked;
                        setEnableVoice(e.target.checked);
                        if (!e.target.checked) {
                          // Stop base64 audio if playing
                          if (audioRef.current) {
                            audioRef.current.pause();
                            audioRef.current.onended = null;
                            audioRef.current.onerror = null;
                            audioRef.current = null;
                          }
                          // Stop browser TTS if speaking
                          if (window.speechSynthesis) {
                            window.speechSynthesis.cancel();
                          }
                          setIsSpeaking(false);
                        }
                      }}
                      className="sr-only peer"
                      data-testid="voice-toggle"
                    />
                    <div className="w-14 h-7 bg-gray-300 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-orange-300 rounded-full peer peer-checked:after:translate-x-7 peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[4px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all peer-checked:bg-[#2E8B57]"></div>
                  </div>
                  <div className="flex items-center gap-2">
                    {enableVoice ? <Volume2 className="w-6 h-6 text-[#2E8B57]" /> : <VolumeX className="w-6 h-6 text-gray-400" />}
                    <div className="text-left">
                      <p className="text-sm font-bold text-[#1A2E40] group-hover:text-[#E06F2C] transition-colors">
                        {enableVoice ? "Voice Enabled" : "Voice Disabled"}
                      </p>
                      <p className="text-xs text-gray-500">Toggle to hear responses</p>
                    </div>
                  </div>
                </label>
              </div>

              {/* Organization Info */}
              <div className="mt-6 pt-6 border-t-2 border-gray-100 space-y-3">
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Official Representative</p>
                  <p className="text-sm font-bold text-[#1A2E40] mt-1">{BOT_CONFIG.organization}</p>
                  <p className="text-sm text-gray-600">{BOT_CONFIG.location}</p>
                </div>
                
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Supported Languages</p>
                  <div className="flex flex-wrap justify-center gap-2">
                    {(showAllLangs ? SUPPORTED_LANGUAGES : SUPPORTED_LANGUAGES.slice(0, 5)).map((lang) => (
                      <span key={lang} className="text-xs px-3 py-1.5 bg-gradient-to-r from-orange-100 to-orange-50 text-[#E06F2C] rounded-full font-semibold border border-orange-200">{lang}</span>
                    ))}
                    <button
                      onClick={() => setShowAllLangs(v => !v)}
                      className="text-xs px-3 py-1.5 bg-gradient-to-r from-[#1A2E40] to-[#243a52] text-white rounded-full font-semibold border border-[#1A2E40] hover:opacity-90 transition-opacity"
                    >
                      {showAllLangs ? "Show Less" : `+${SUPPORTED_LANGUAGES.length - 5} More`}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Chat Section */}
          <div className="lg:col-span-8">
            {/* Persistent auth bar — always visible above the chat box when logged in */}
            {sevaToken && sevaUser && (
              <div className="flex items-center justify-between px-4 py-2 mb-2 rounded-xl bg-[#1A2E40] shadow">
                <div className="flex items-center gap-2 text-sm text-white">
                  <UserCheck className="w-4 h-4 text-white" />
                  <span className="font-semibold text-white">{sevaUser.name}</span>
                  <span className="text-gray-400 text-xs hidden sm:inline">· {sevaUser.email}</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleSevaFetchApps}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-white/10 text-white hover:bg-white/20 transition border border-white/20"
                  >
                    <List className="w-3.5 h-3.5" /> My Applications
                  </button>
                  <button
                    onClick={() => handleSevaLogout(false)}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-red-500 text-white hover:bg-red-600 transition"
                  >
                    <LogOut className="w-3.5 h-3.5" /> Logout
                  </button>
                </div>
              </div>
            )}

            <div
              className="glass-card rounded-xl shadow-lg flex flex-col relative"
              style={{ height: sevaToken && sevaUser ? "560px" : "600px" }}
              role="region"
              aria-label="Chat conversation"
            >
              {/* API loading overlay */}
              {isApiLoading && (
                <>
                  {/* progress bar */}
                  <div className="absolute top-0 left-0 right-0 h-0.5 rounded-t-xl overflow-hidden z-30 bg-gray-100">
                    <div className="h-full bg-[#E06F2C] rounded-full"
                      style={{ animation: "loading-bar 1.2s ease-in-out infinite" }} />
                  </div>
                  {/* centre spinner */}
                  <div className="absolute inset-0 bg-white/50 backdrop-blur-[2px] flex items-center justify-center z-20 rounded-xl pointer-events-none">
                    <div className="flex items-center gap-3 bg-white px-5 py-2.5 rounded-full shadow-lg border border-gray-100">
                      <div className="w-4 h-4 border-[3px] border-[#E06F2C] border-t-transparent rounded-full animate-spin" />
                      <span className="text-sm font-semibold text-[#1A2E40]">Please wait…</span>
                    </div>
                  </div>
                </>
              )}
              <div
                ref={chatScrollRef}
                className="flex-1 overflow-y-auto p-6 space-y-4"
                data-testid="chat-messages"
                role="log"
                aria-live="polite"
                aria-label="Message history"
                tabIndex={0}
              >
                {messages.map((msg, index) => (
                  <div
                    key={index}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                    data-testid={`message-${index}`}
                    role="article"
                    aria-label={`${msg.role === "user" ? "Your message" : "Bot response"}`}
                  >
                    {msg.role === "advisory" ? (
                      <div 
                        className={`max-w-lg px-4 py-3 rounded-lg border-l-4 ${
                          msg.type === "alert" 
                            ? "bg-red-50 border-red-500 text-red-900" 
                            : msg.type === "warning"
                            ? "bg-amber-50 border-amber-500 text-amber-900"
                            : "bg-blue-50 border-blue-500 text-blue-900"
                        }`}
                        role={msg.type === "alert" ? "alert" : "note"}
                      >
                        <div className="flex items-start gap-2 mb-2">
                          <AlertTriangle className={`w-5 h-5 flex-shrink-0 mt-0.5 ${
                            msg.type === "alert" ? "text-red-600" : 
                            msg.type === "warning" ? "text-amber-600" : "text-blue-600"
                          }`} aria-hidden="true" />
                          <h4 className="font-bold text-sm">{msg.title}</h4>
                        </div>
                        <div className="ml-7">
                          <BotMessage content={msg.content} />
                        </div>
                      </div>
                    ) : msg.type === "document" ? (
                      <div className="bg-white border border-gray-200 text-[#1A2E40] rounded-2xl rounded-bl-sm shadow-sm px-4 py-3 max-w-[88%]">
                        <BotMessage content={msg.content} />
                        <DocumentCard
                          doc={msg.docData}
                          onView={() => setDocModal({ doc: msg.docData, msgIndex: index })}
                          onReplace={() => handleDocReplace(index)}
                          onRemove={() => handleDocRemove(index)}
                        />
                      </div>
                    ) : msg.role === "seva_type_a" ? (
                      <TypeACard msg={msg} onFinalize={handleSevaTypeAFinalize} />
                    ) : msg.role === "seva_form_mode" ? (
                      <div className="bg-white border border-gray-200 rounded-xl shadow-sm px-4 py-3 max-w-[88%]">
                        <p className="text-sm font-semibold text-[#1A2E40] mb-3">How would you like to proceed?</p>
                        <div className="flex gap-3">
                          <button
                            onClick={() => handleSevaChooseFormMode("upload")}
                            className="flex-1 flex flex-col items-center gap-1.5 border-2 border-[#E06F2C] rounded-lg p-3 hover:bg-orange-50 transition text-sm font-medium text-[#E06F2C]"
                          >
                            <Download className="w-5 h-5" /> Upload Documents<span className="text-xs text-gray-400 font-normal">OCR auto-fill</span>
                          </button>
                          <button
                            onClick={() => handleSevaChooseFormMode("manual")}
                            className="flex-1 flex flex-col items-center gap-1.5 border-2 border-[#1A2E40] rounded-lg p-3 hover:bg-slate-50 transition text-sm font-medium text-[#1A2E40]"
                          >
                            <FileText className="w-5 h-5" /> Fill Manually<span className="text-xs text-gray-400 font-normal">Step by step</span>
                          </button>
                        </div>
                      </div>
                    ) : msg.role === "seva_doc_upload" ? (
                      (() => {
                        const appId = msg.appId || sevaCurrentApp?.application_id;
                        const previews = sevaDocPreviews[appId] || [];
                        return (
                          <div className="bg-white border border-gray-200 rounded-xl shadow-sm px-4 py-3 max-w-[92%] space-y-3">
                            <p className="text-sm font-semibold text-[#1A2E40]">Upload Required Documents</p>

                            {/* Upload rows */}
                            <div className="flex flex-col gap-2">
                              {(msg.docs || []).map((doc, i) => {
                                const preview = previews.find(p => p.name === doc);
                                return (
                                  <div key={i} className="space-y-1.5">
                                    {/* Upload row */}
                                    <label className={`flex items-center gap-2 cursor-pointer rounded p-1.5 border transition ${preview ? "border-green-300 bg-green-50" : "border-dashed border-gray-300 hover:bg-gray-50"}`}>
                                      <input type="file" accept=".pdf,.jpg,.jpeg,.png" className="hidden"
                                        onChange={e => { if (e.target.files[0]) handleSevaUploadDoc(e.target.files[0], doc); e.target.value = ""; }}
                                        disabled={sevaUploadingDocName === doc}
                                      />
                                      <FileText className={`w-4 h-4 flex-shrink-0 ${preview ? "text-green-600" : "text-[#E06F2C]"}`} />
                                      <span className="text-xs text-[#1A2E40] flex-1 line-clamp-1">{doc}</span>
                                      {sevaUploadingDocName === doc
                                        ? <span className="text-xs text-gray-400 animate-pulse">Uploading…</span>
                                        : preview
                                          ? <span className="text-xs text-green-600 font-medium">✓ Uploaded</span>
                                          : <span className="text-xs text-[#E06F2C] font-medium">Upload ↑</span>
                                      }
                                    </label>

                                    {/* Preview card */}
                                    {preview && (
                                      <div className="flex items-center gap-2 pl-2 py-1.5 bg-gray-50 rounded-lg border border-gray-200">
                                        {preview.isPdf ? (
                                          <div className="w-10 h-10 rounded bg-red-50 flex items-center justify-center flex-shrink-0">
                                            <FileText className="w-5 h-5 text-red-500" />
                                          </div>
                                        ) : (
                                          <img src={preview.dataUrl} alt={preview.name}
                                            className="w-10 h-10 rounded object-cover flex-shrink-0 border border-gray-200 cursor-pointer"
                                            onClick={() => setDocModal({ doc: { dataUrl: preview.dataUrl, name: preview.name, isPdf: false }, msgIndex: -1 })}
                                          />
                                        )}
                                        <span className="text-xs text-gray-600 flex-1 truncate">{preview.name}</span>
                                        <label className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-blue-50 text-blue-600 hover:bg-blue-100 transition cursor-pointer">
                                          <input type="file" accept=".pdf,.jpg,.jpeg,.png" className="hidden"
                                            onChange={e => { if (e.target.files[0]) handleSevaUploadDoc(e.target.files[0], doc); e.target.value = ""; }}
                                          />
                                          <RefreshCw className="w-3 h-3" /> Replace
                                        </label>
                                        <button
                                          onClick={() => handleSevaRemoveDoc(appId, preview.id, preview.name)}
                                          className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-50 text-red-500 hover:bg-red-100 transition"
                                        >
                                          <Trash2 className="w-3 h-3" /> Remove
                                        </button>
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>

                            {appId && (
                              <button
                                onClick={() => setMessages(prev => [...prev, { role: "seva_submit_review", appId }])}
                                className="w-full bg-[#E06F2C] text-white rounded-lg py-2 text-sm font-semibold hover:bg-[#c45a1a] transition"
                              >
                                Done Uploading — Review & Submit
                              </button>
                            )}
                          </div>
                        );
                      })()
                    ) : msg.role === "seva_submit_review" ? (
                      <div className="bg-white border border-[#059669] rounded-xl shadow-sm px-4 py-4 max-w-[88%] space-y-3">
                        <p className="text-sm font-semibold text-[#1A2E40]">Ready to submit?</p>
                        <p className="text-xs text-gray-500">A review email will be sent to <strong>{sevaUser?.email}</strong>. You can edit for 24 hours before it locks.</p>
                        <button
                          onClick={handleSevaPreviewPdf}
                          className="w-full border border-[#1A2E40] text-[#1A2E40] rounded-lg py-2 text-sm font-semibold hover:bg-gray-50 transition flex items-center justify-center gap-2"
                        >
                          <FileText className="w-4 h-4" /> Preview PDF
                        </button>
                        <div className="flex gap-2">
                          <button onClick={handleSevaSubmitApp} className="flex-1 bg-[#059669] text-white rounded-lg py-2 text-sm font-semibold hover:bg-[#047857] transition">
                            📤 Submit for Review
                          </button>
                          <button onClick={handleSevaConfirmApp} className="flex-1 bg-[#E06F2C] text-white rounded-lg py-2 text-sm font-semibold hover:bg-[#c45a1a] transition">
                            ✅ Confirm &amp; Get PDF
                          </button>
                        </div>
                      </div>
                    ) : msg.role === "seva_service_info" ? (
                      <ServiceInfoCard
                        svc={msg.svc}
                        onApply={() => {
                          setSevaToken(null);
                          setSevaUser(null);
                          sevaTokenRef.current = null;
                          sessionStorage.removeItem("seva_token");
                          sessionStorage.removeItem("seva_user");
                          setSevaCurrentApp(null);
                          setSevaFormMode(null);
                          setSevaFormData({});
                          setSevaFormFieldIndex(0);
                          setSevaAuthName("");
                          setSevaAuthEmail("");
                          setSevaOtpInput("");
                          setSevaAuthError("");
                          handleSevaStartAuth({ key: msg.svc.key, name: msg.svc.name, category: msg.svc.category });
                        }}
                      />
                    ) : msg.role === "seva_service_action" ? (
                      <div className="bg-white border border-[#E06F2C] rounded-xl shadow-sm px-4 py-3 max-w-[88%] flex items-center justify-between gap-4">
                        <div>
                          <p className="text-sm font-semibold text-[#1A2E40]">
                            {msg.svc.emoji} {msg.svc.name}
                          </p>
                          <p className="text-xs text-gray-500 mt-0.5">Ready to start your application?</p>
                        </div>
                        <button
                          onClick={() => {
                            setSevaToken(null);
                            setSevaUser(null);
                            sevaTokenRef.current = null;
                            sessionStorage.removeItem("seva_token");
                            sessionStorage.removeItem("seva_user");
                            setSevaCurrentApp(null);
                            setSevaFormMode(null);
                            setSevaFormData({});
                            setSevaFormFieldIndex(0);
                            setSevaAuthName("");
                            setSevaAuthEmail("");
                            setSevaOtpInput("");
                            setSevaAuthError("");
                            handleSevaStartAuth({ key: msg.svc.key, name: msg.svc.name, category: msg.svc.category });
                          }}
                          className="whitespace-nowrap bg-[#E06F2C] text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-[#c45a1a] transition flex-shrink-0"
                        >
                          Apply Now →
                        </button>
                      </div>
                    ) : (
                      <div
                        className={`max-w-[88%] px-4 py-3 rounded-2xl ${
                          msg.role === "user"
                            ? "bg-[#E06F2C] text-white rounded-br-sm text-sm leading-relaxed"
                            : "bg-white border border-gray-200 text-[#1A2E40] rounded-bl-sm shadow-sm"
                        }`}
                      >
                        {msg.role === "assistant" ? (
                          <BotMessage content={msg.content} />
                        ) : (
                          msg.content
                        )}
                      </div>
                    )}
                  </div>
                ))}
                
                {isTyping && (
                  <div
                    className="flex justify-start"
                    data-testid="typing-indicator"
                    role="status"
                    aria-label="Loading..."
                  >
                    <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex items-center gap-3">
                      <div className="flex gap-1" aria-hidden="true">
                        <span className="w-2 h-2 bg-[#E06F2C] rounded-full animate-bounce" style={{animationDelay: '0ms'}}></span>
                        <span className="w-2 h-2 bg-[#E06F2C] rounded-full animate-bounce" style={{animationDelay: '150ms'}}></span>
                        <span className="w-2 h-2 bg-[#E06F2C] rounded-full animate-bounce" style={{animationDelay: '300ms'}}></span>
                      </div>
                      <span className="text-sm text-gray-500">Loading...</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Suggestion Chips */}
              {!isTyping && (() => {
                const quickReplies =
                  currentStep === "consent_pending" ? [
                    { label: "✅ Yes, proceed", value: "yes" },
                    { label: "❌ No, cancel",   value: "no"  },
                  ] :
                  currentStep === "paused" ? [
                    { label: "▶️ Continue",       value: "continue" },
                    { label: "🗑️ Discard & Search", value: "discard"  },
                  ] :
                  currentStep === "docs_pending" ? [
                    {
                      label: "📄 Preview PDF",
                      value: "__preview_pdf__",
                      action: () => {
                        const sid = sessionIdRef.current;
                        if (!sid) {
                          toast.error("No active session found. Please start your application again.");
                          return;
                        }
                        const url = `${process.env.REACT_APP_BACKEND_URL}/api/consular/generate-pdf?session_id=${encodeURIComponent(sid)}`;
                        const a = document.createElement("a");
                        a.href = url;
                        a.target = "_blank";
                        a.rel = "noopener noreferrer";
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                      },
                    },
                    { label: "📤 Submit application",  value: "submit"  },
                    { label: "🗑️ Discard application", value: "discard" },
                  ] :
                  (currentStep === "collecting" || currentStep === "docs_uploading") ? [
                    { label: "🗑️ Discard application", value: "discard" },
                  ] : null;

                const chips = quickReplies || null;
                if (!chips) return null;

                return (
                  <div className="px-4 pb-2 flex flex-wrap gap-2">
                    {chips.map((chip) => (
                      <button
                        key={chip.value}
                        onClick={() => chip.action ? chip.action() : handleSend(chip.value)}
                        disabled={isTyping && !chip.action}
                        className="text-xs px-3 py-1.5 rounded-full border border-[#E06F2C] text-[#E06F2C] hover:bg-[#E06F2C] hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {chip.label}
                      </button>
                    ))}
                  </div>
                );
              })()}

              {/* Seva Auth Panel — name/email entry */}
              {sevaAuthStep === "name_email" && (
                <div className="border-t border-orange-200 bg-orange-50 px-4 py-3">
                  <p className="text-xs font-semibold text-[#E06F2C] mb-2">Step 1 of 2 — Your Details</p>
                  {sevaAuthError && <p className="text-xs text-red-500 mb-2">{sevaAuthError}</p>}
                  <div className="flex flex-col gap-2">
                    <input
                      type="text"
                      placeholder="Full Name"
                      value={sevaAuthName}
                      onChange={e => setSevaAuthName(e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#E06F2C]"
                    />
                    <input
                      type="email"
                      placeholder="Email Address"
                      value={sevaAuthEmail}
                      onChange={e => setSevaAuthEmail(e.target.value)}
                      onKeyDown={e => e.key === "Enter" && handleSevaSubmitNameEmail()}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#E06F2C]"
                    />
                    <button
                      onClick={handleSevaSubmitNameEmail}
                      disabled={sevaAuthLoading}
                      className="bg-[#E06F2C] text-white rounded-lg py-2 text-sm font-semibold hover:bg-[#c45a1a] transition disabled:opacity-50"
                    >
                      {sevaAuthLoading ? "Sending OTP…" : "Send OTP →"}
                    </button>
                  </div>
                </div>
              )}

              {/* Seva Auth Panel — OTP entry */}
              {sevaAuthStep === "otp" && (
                <div className="border-t border-orange-200 bg-orange-50 px-4 py-3">
                  <p className="text-xs font-semibold text-[#E06F2C] mb-2">Step 2 of 2 — Enter OTP</p>
                  {sevaAuthError && <p className="text-xs text-red-500 mb-2">{sevaAuthError}</p>}
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="6-digit OTP"
                      maxLength={6}
                      value={sevaOtpInput}
                      onChange={e => setSevaOtpInput(e.target.value.replace(/\D/g, ""))}
                      onKeyDown={e => e.key === "Enter" && handleSevaVerifyOtp()}
                      className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono tracking-widest focus:outline-none focus:ring-2 focus:ring-[#E06F2C]"
                    />
                    <button
                      onClick={handleSevaVerifyOtp}
                      disabled={sevaAuthLoading}
                      className="bg-[#E06F2C] text-white rounded-lg px-4 py-2 text-sm font-semibold hover:bg-[#c45a1a] transition disabled:opacity-50"
                    >
                      {sevaAuthLoading ? "…" : "Verify ✓"}
                    </button>
                  </div>
                  <button onClick={() => { setSevaAuthStep("name_email"); setSevaOtpInput(""); setSevaAuthError(""); }} className="text-xs text-gray-400 hover:text-gray-600 mt-1">← Back</button>
                </div>
              )}

              {/* Seva Form Field Panel — sequential manual entry */}
              {sevaFormMode === "manual" && sevaCurrentApp && (() => {
                const fields = sevaCurrentApp.fields || [];
                const field = fields[sevaFormFieldIndex];
                if (!field) return null;
                return (
                  <div className="border-t border-blue-200 bg-blue-50 px-4 py-3">
                    <p className="text-xs font-semibold text-blue-600 mb-1">{field.label} ({sevaFormFieldIndex + 1}/{fields.length})</p>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder={field.label}
                        value={sevaFormInput}
                        onChange={e => setSevaFormInput(e.target.value)}
                        onKeyDown={e => e.key === "Enter" && handleSevaFormFieldSubmit()}
                        className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                      />
                      <button
                        onClick={handleSevaFormFieldSubmit}
                        className="bg-blue-600 text-white rounded-lg px-4 py-2 text-sm font-semibold hover:bg-blue-700 transition"
                      >
                        Next →
                      </button>
                    </div>
                  </div>
                );
              })()}

              {/* Input Area */}
              <div className="border-t border-gray-200 p-4" role="form" aria-label="Message input form">
                <div className="flex gap-2">
                  <label htmlFor="chat-input-field" className="sr-only">
                    Type your message
                  </label>
                  <Textarea
                    id="chat-input-field"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyPress={(e) => e.key === "Enter" && !e.shiftKey && !isTyping && (e.preventDefault(), handleSend())}
                    placeholder={`Type your message in ${currentLang.name}...`}
                    className="flex-1 min-h-[60px]"
                    data-testid="chat-input"
                    aria-describedby="input-instructions"
                  />
                  <span id="input-instructions" className="sr-only">
                    Press Enter to send, Shift+Enter for new line
                  </span>
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileUpload}
                    accept=".jpg,.jpeg,.png,.pdf"
                    style={{ display: 'none' }}
                    data-testid="file-input"
                    aria-label="Upload document"
                  />
                  <div className="flex flex-col gap-2" role="toolbar" aria-label="Message actions">
                    <Button
                      onClick={handleVoice}
                      className={`${
                        isRecording ? "bg-red-500 hover:bg-red-600 animate-pulse" : "bg-[#2E8B57] hover:bg-[#256B47]"
                      } text-white min-h-[44px] min-w-[44px]`}
                      data-testid="voice-btn"
                      aria-label={isRecording ? "Stop recording" : "Start voice input"}
                      aria-pressed={isRecording}
                    >
                      <Mic className="w-5 h-5" aria-hidden="true" />
                    </Button>
                    <Button
                      onClick={startCamera}
                      className="bg-[#1A2E40] hover:bg-[#132230] text-white min-h-[44px] min-w-[44px]"
                      data-testid="camera-btn"
                      aria-label="Scan document with camera"
                    >
                      <Camera className="w-5 h-5" aria-hidden="true" />
                    </Button>
                    <Button
                      onClick={() => fileInputRef.current?.click()}
                      className="bg-[#E06F2C] hover:bg-[#C55D20] text-white min-h-[44px] min-w-[44px]"
                      data-testid="upload-btn"
                      aria-label="Upload document file (JPG, PNG, or PDF)"
                    >
                      <FileText className="w-5 h-5" aria-hidden="true" />
                    </Button>
                    {isTyping ? (
                      <Button
                        onClick={handleStop}
                        className="bg-red-500 hover:bg-red-600 text-white min-h-[44px] min-w-[44px]"
                        data-testid="stop-btn"
                        aria-label="Stop response"
                      >
                        <Square className="w-5 h-5 fill-current" aria-hidden="true" />
                      </Button>
                    ) : (
                      <Button
                        onClick={() => handleSend()}
                        disabled={isTyping}
                        className="bg-[#E06F2C] hover:bg-[#C55D20] text-white min-h-[44px] min-w-[44px] disabled:opacity-50 disabled:cursor-not-allowed"
                        data-testid="send-btn"
                        aria-label="Send message"
                      >
                        <Send className="w-5 h-5" aria-hidden="true" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        {/* Compliance Footer */}
        <footer className="text-center mt-6 text-xs text-gray-500" role="contentinfo">
          <p>GDPR, DPDA & POPIA Compliant • Your data is secure and private</p>
        </footer>
      </div>

      {/* My Applications Modal */}
      {showSevaApps && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={() => setShowSevaApps(false)}>
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h2 className="text-lg font-bold text-[#1A2E40]">My Applications</h2>
              <button onClick={() => setShowSevaApps(false)} className="text-gray-400 hover:text-gray-700"><X size={20} /></button>
            </div>
            <div className="overflow-y-auto flex-1 p-4 space-y-3">
              {sevaApps.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-8">No applications found.</p>
              ) : sevaApps.map(app => (
                <div key={app.id} className="border border-gray-200 rounded-xl p-4 hover:border-[#E06F2C] transition">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-semibold text-[#1A2E40] text-sm">{app.service_name}</p>
                      <p className="text-xs text-[#E06F2C] font-mono mt-0.5">{app.reference_id}</p>
                      <p className="text-xs text-gray-400 mt-1">{new Date(app.created_at).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" })}</p>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                      <span className={`text-xs px-2.5 py-1 rounded-full font-semibold ${
                        app.status === "confirmed" ? "bg-green-100 text-green-700" :
                        app.status === "submitted" ? "bg-blue-100 text-blue-700" :
                        "bg-gray-100 text-gray-600"
                      }`}>{app.status.charAt(0).toUpperCase() + app.status.slice(1)}</span>
                      {app.has_pdf && (
                        <button
                          onClick={() => handleSevaDownloadPdf(app.id)}
                          className="flex items-center gap-1 text-xs bg-[#1A2E40] text-white px-2.5 py-1 rounded-full hover:bg-[#243a52] transition"
                        >
                          <Download className="w-3 h-3" /> PDF
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Camera Dialog */}
      <Dialog open={showCamera} onOpenChange={(open) => !open && stopCamera()}>
        <DialogContent 
          className="max-w-2xl" 
          data-testid="camera-dialog"
          aria-labelledby="camera-dialog-title"
          aria-describedby="camera-dialog-desc"
        >
          <div className="flex justify-between items-center mb-4">
            <h2 id="camera-dialog-title" className="text-2xl font-bold text-[#1A2E40]">Capture Document</h2>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={stopCamera}
              aria-label="Close camera"
            >
              <X className="w-5 h-5" aria-hidden="true" />
            </Button>
          </div>
          
          <p id="camera-dialog-desc" className="sr-only">
            Use your device camera to capture a document image for processing
          </p>
          
          {cameraError ? (
            <div 
              className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700"
              role="alert"
            >
              <p className="font-semibold">Camera Error</p>
              <p className="text-sm mt-1">{cameraError}</p>
              <p className="text-sm mt-2">
                <strong>How to fix:</strong> Please ensure camera permissions are enabled in your browser settings.
              </p>
            </div>
          ) : (
            <>
              <div className="relative bg-black rounded-lg overflow-hidden">
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  className="w-full rounded-lg"
                  aria-label="Camera preview"
                />
                <canvas ref={canvasRef} className="hidden" aria-hidden="true" />
                
                {/* Guide overlay */}
                <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
                  <div className="absolute inset-8 border-2 border-dashed border-white/50 rounded-lg"></div>
                  <p className="absolute bottom-4 left-1/2 transform -translate-x-1/2 text-white text-sm bg-black/50 px-3 py-1 rounded">
                    Position document within frame
                  </p>
                </div>
              </div>
              
              <div className="flex gap-4 mt-4">
                <Button 
                  onClick={captureImage} 
                  className="flex-1 bg-[#E06F2C] hover:bg-[#C55D20] min-h-[44px]" 
                  data-testid="capture-btn"
                  aria-label="Capture document photo"
                >
                  <Camera className="w-5 h-5 mr-2" aria-hidden="true" />
                  Capture Document
                </Button>
                <Button 
                  onClick={stopCamera} 
                  variant="outline" 
                  className="flex-1 min-h-[44px]" 
                  data-testid="cancel-capture-btn"
                  aria-label="Cancel and close camera"
                >
                  Cancel
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Document Lightbox Modal */}
      {docModal && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setDocModal(null)}
        >
          <div
            className="relative bg-white rounded-xl shadow-2xl max-w-2xl w-full p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setDocModal(null)}
              className="absolute top-3 right-3 text-gray-500 hover:text-gray-800"
              aria-label="Close"
            >
              <X size={20} />
            </button>
            <p className="text-sm font-semibold text-[#1A2E40] mb-3 pr-6 truncate">{docModal.doc.name}</p>
            {docModal.doc.isPdf ? (
              <div className="flex flex-col items-center justify-center h-48 bg-red-50 rounded-lg text-red-500 gap-2">
                <FileText size={48} />
                <span className="text-sm font-medium">PDF Document</span>
                <span className="text-xs text-gray-400">{docModal.doc.name}</span>
              </div>
            ) : (
              <img
                src={docModal.doc.dataUrl}
                alt={docModal.doc.name}
                className="w-full rounded-lg max-h-[60vh] object-contain"
              />
            )}
            <div className="flex gap-3 mt-4 justify-end">
              <button
                onClick={() => { handleDocReplace(docModal.msgIndex); }}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700 transition"
              >
                <RefreshCw size={14} /> Replace
              </button>
              <button
                onClick={() => handleDocRemove(docModal.msgIndex)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-red-500 text-white text-sm hover:bg-red-600 transition"
              >
                <Trash2 size={14} /> Remove
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Hidden input for replacing a document */}
      <input
        ref={replaceInputRef}
        type="file"
        accept="image/jpeg,image/jpg,image/png,image/webp,image/gif,application/pdf"
        className="hidden"
        onChange={handleReplaceFileChange}
      />
    </div>
  );
}
