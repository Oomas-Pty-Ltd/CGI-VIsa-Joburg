import React, { useState, useEffect, useRef, useCallback } from "react";
import { Mic, Camera, Send, FileText, Check, AlertTriangle, Globe, X, Volume2, VolumeX, Square, Eye, RefreshCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import axios from "axios";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { 
  BOT_CONFIG, 
  GREETING_MESSAGE, 
  ADVISORY_MESSAGES, 
  SUPPORTED_LANGUAGES 
} from "../config/botMessages";

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

// Language configuration with codes
const LANGUAGES = [
  // English
  { code: "en",  name: "English",                flag: "🇬🇧" },
  // Indian languages
  { code: "hi",  name: "हिंदी (Hindi)",            flag: "🇮🇳" },
  { code: "bn",  name: "বাংলা (Bengali)",           flag: "🇮🇳" },
  { code: "mr",  name: "मराठी (Marathi)",           flag: "🇮🇳" },
  { code: "te",  name: "తెలుగు (Telugu)",           flag: "🇮🇳" },
  { code: "ta",  name: "தமிழ் (Tamil)",             flag: "🇮🇳" },
  { code: "gu",  name: "ગુજરાતી (Gujarati)",        flag: "🇮🇳" },
  { code: "ur",  name: "اردو (Urdu)",               flag: "🇮🇳" },
  { code: "kn",  name: "ಕನ್ನಡ (Kannada)",           flag: "🇮🇳" },
  { code: "or",  name: "ଓଡ଼ିଆ (Odia)",              flag: "🇮🇳" },
  { code: "ml",  name: "മലയാളം (Malayalam)",        flag: "🇮🇳" },
  { code: "pa",  name: "ਪੰਜਾਬੀ (Punjabi)",          flag: "🇮🇳" },
  { code: "as",  name: "অসমীয়া (Assamese)",         flag: "🇮🇳" },
  { code: "mai", name: "मैथिली (Maithili)",          flag: "🇮🇳" },
  { code: "sa",  name: "संस्कृत (Sanskrit)",         flag: "🇮🇳" },
  { code: "sat", name: "ᱥᱟᱱᱛᱟᱲᱤ (Santali)",        flag: "🇮🇳" },
  { code: "ks",  name: "کٲشُر (Kashmiri)",          flag: "🇮🇳" },
  { code: "ne",  name: "नेपाली (Nepali)",            flag: "🇮🇳" },
  { code: "sd",  name: "سنڌي (Sindhi)",             flag: "🇮🇳" },
  { code: "doi", name: "डोगरी (Dogri)",              flag: "🇮🇳" },
  { code: "kok", name: "कोंकणी (Konkani)",           flag: "🇮🇳" },
  { code: "mni", name: "মৈতৈলোন্ (Manipuri)",        flag: "🇮🇳" },
  { code: "brx", name: "बड़ो (Bodo)",                flag: "🇮🇳" },
  { code: "mwr", name: "मारवाड़ी (Marwari)",          flag: "🇮🇳" },
  // South African languages
  { code: "zu",  name: "isiZulu",                   flag: "🇿🇦" },
  { code: "xh",  name: "isiXhosa",                  flag: "🇿🇦" },
  { code: "af",  name: "Afrikaans",                 flag: "🇿🇦" },
  { code: "nso", name: "Sepedi",                    flag: "🇿🇦" },
  { code: "tn",  name: "Setswana",                  flag: "🇿🇦" },
  { code: "st",  name: "Sesotho",                   flag: "🇿🇦" },
  { code: "ts",  name: "Xitsonga",                  flag: "🇿🇦" },
  { code: "ss",  name: "siSwati",                   flag: "🇿🇦" },
  { code: "ve",  name: "Tshivenda",                 flag: "🇿🇦" },
  { code: "nr",  name: "isiNdebele",                flag: "🇿🇦" },
  // Other languages
  { code: "ar",  name: "العربية (Arabic)",           flag: "🇸🇦" },
  { code: "fr",  name: "Français (French)",          flag: "🇫🇷" },
  { code: "sw",  name: "Kiswahili (Swahili)",        flag: "🇹🇿" },
  { code: "ha",  name: "Hausa",                     flag: "🇳🇬" },
  { code: "yo",  name: "Yorùbá (Yoruba)",            flag: "🇳🇬" },
  { code: "ig",  name: "Igbo",                      flag: "🇳🇬" },
  { code: "am",  name: "አማርኛ (Amharic)",             flag: "🇪🇹" },
  { code: "om",  name: "Oromoo (Oromo)",             flag: "🇪🇹" },
];

// BCP-47 codes for speech recognition (browser Web Speech API)
const SPEECH_LANG_MAP = {
  en: "en-GB", hi: "hi-IN", bn: "bn-IN", mr: "mr-IN", te: "te-IN",
  ta: "ta-IN", gu: "gu-IN", ur: "ur-IN", kn: "kn-IN", or: "or-IN",
  ml: "ml-IN", pa: "pa-IN", as: "as-IN", mai: "hi-IN", sa: "sa-IN",
  sat: "hi-IN", ks: "hi-IN", ne: "ne-NP", sd: "ur-IN", doi: "hi-IN",
  kok: "mr-IN", mni: "hi-IN", brx: "hi-IN", mwr: "hi-IN",
  zu: "zu-ZA", xh: "xh-ZA", af: "af-ZA", nso: "af-ZA", tn: "af-ZA",
  st: "st-ZA", ts: "af-ZA", ss: "af-ZA", ve: "af-ZA", nr: "af-ZA",
  ar: "ar-SA", fr: "fr-FR", sw: "sw-KE", ha: "ha-NE", yo: "yo-NG",
  ig: "ig-NG", am: "am-ET", om: "om-ET",
};

export default function ConsularBot() {
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

  // Notify backend that a document was uploaded so the flow advances
  const sendDocumentToBackend = useCallback(async (imageBase64) => {
    setIsTyping(true);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
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
        signal: AbortSignal.timeout(60000),
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
            if (evt.chunk) {
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
        signal: AbortSignal.timeout(60000),
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

    const FEMALE_NAMES = /heera|priya|aditi|neerja|kalpana|swara|zira|samantha|karen|moira|fiona|tessa|victoria|linda|emma|aria|jenny|sonia|natasha|susan|hazel|amelie|alice|alva|anna|claire|carmit|damayanti|ioana|joana|laura|lekha|luciana|mariska|mei\-jia|melina|milena|monica|paulina|sangeeta|sara|satu|sin\-ji|yelda|yuna|zosia/i;
    const allVoices  = window.speechSynthesis.getVoices();
    const isFemale   = (v) => FEMALE_NAMES.test(v.name) || /female|woman|girl/i.test(v.name);

    // Find a voice for the selected language only.
    // Never fall back to an English voice when another language is selected —
    // instead leave .voice unset so Chrome/Edge use their cloud TTS engine
    // (Google TTS / Windows Speech) for the target language automatically.
    const matchingVoice =
      allVoices.find((v) => isFemale(v) && v.lang === targetLang) ||
      allVoices.find((v) => isFemale(v) && v.lang.startsWith(langFamily + "-")) ||
      allVoices.find((v) => v.lang === targetLang) ||
      allVoices.find((v) => v.lang.startsWith(langFamily + "-")) ||
      null;

    // Chrome bug: utterances > ~300 chars may cut off silently.
    // Split on sentence boundaries and queue them all.
    const CHUNK_SIZE = 250;
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
      signal: AbortSignal.timeout(30000),
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

    if (file.size > 10 * 1024 * 1024) {
      toast.error('File size exceeds 10MB limit.');
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
                    alt="Seva Setu Bot"
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
            <div 
              className="glass-card rounded-xl shadow-lg flex flex-col" 
              style={{ height: "600px" }}
              role="region"
              aria-label="Chat conversation"
            >
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
                    aria-label={`${msg.role === "user" ? "Your message" : "Seva Setu response"}`}
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
                        if (sid) {
                          window.open(`${process.env.REACT_APP_BACKEND_URL}/api/consular/generate-pdf?session_id=${encodeURIComponent(sid)}`, "_blank");
                        }
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
