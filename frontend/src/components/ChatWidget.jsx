import React, { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import axios from 'axios';
import { GREETING_MESSAGE, ADVISORY_MESSAGES } from '../config/botMessages';
import './ChatWidget.css';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';
const API = `${API_BASE}/api`;

const BOT_IMAGE = 'https://static.prod-images.emergentagent.com/jobs/41ee56b6-38da-4112-8da3-b4cf6bfcfd91/images/1fc401012f88731c201ca30b4be56212c44bad84c995e7ed04da381c8740f43b.png';

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
  en:  'Type your message in हिंदी (Hindi) or English...',
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

function timeNow() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function buildWelcomeMessages() {
  const msgs = [
    { id: 'welcome', role: 'bot', html: false, content: GREETING_MESSAGE, time: timeNow() }
  ];
  ADVISORY_MESSAGES.filter(a => a.active).forEach(adv => {
    msgs.push({ id: adv.id, role: 'advisory', type: adv.type, title: adv.title, content: adv.content, time: timeNow() });
  });
  return msgs;
}

export default function ChatWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const sessionIdRef = useRef(localStorage.getItem('consular_session_id') || null);
  const [isLoading, setIsLoading] = useState(false);
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
  const [showInfo, setShowInfo] = useState(false);
  const [isSwitchingLang, setIsSwitchingLang] = useState(false);

  const [langToast, setLangToast] = useState('');
  const langToastTimerRef = useRef(null);
  const langBtnRef = useRef(null);
  const [langDropPos, setLangDropPos] = useState({ top: 0, right: 0 });

  const messagesScrollRef = useRef(null);
  const textareaRef = useRef(null);
  const audioRef = useRef(null);
  const ttsAbortRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);
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

  // Keep currentLang ref in sync
  useEffect(() => { currentLangRef.current = currentLang; }, [currentLang]);

  // Safety net: stop all audio whenever voiceOn state goes false
  useEffect(() => {
    if (!voiceOn) stopAudio();
  }, [voiceOn, stopAudio]);

  // Close lang menu on outside click
  useEffect(() => {
    if (!showLangMenu) return;
    const handler = (e) => {
      if (!e.target.closest('.seva-lang-dropdown') && !e.target.closest('.seva-lang-btn')) {
        setShowLangMenu(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showLangMenu]);

  // Online/offline
  useEffect(() => {
    const on = () => setIsOnline(true);
    const off = () => setIsOnline(false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }, []);

  // Cleanup camera on unmount
  useEffect(() => {
    return () => { if (cameraStream) cameraStream.getTracks().forEach(t => t.stop()); };
  }, [cameraStream]);

  // Open widget → show welcome
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      scrollToTopNextRef.current = true;
      setMessages(buildWelcomeMessages());
    }
  }, [isOpen, messages.length]);

  // Scroll to bottom inside the widget messages div (not page scroll)
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

  // ── Streaming send ─────────────────────────────────────────────────────────
  const sendMsg = useCallback(async (overrideText) => {
    const trimmed = (overrideText !== undefined ? overrideText : input).trim();
    if (!trimmed || isLoading) return;

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
          user_id: 'guest',
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
          }
        }
      }
    } catch (err) {
      const errMsg = isOnline
        ? "I'm having trouble connecting to the server. Please try again."
        : "You appear to be offline. Please check your internet connection.";
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = { ...updated[updated.length - 1], content: errMsg };
        return updated;
      });
    } finally {
      setIsLoading(false);
    }
  }, [input, isLoading, isOnline, speakWithBackend]);

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

  // ── Whisper voice input ────────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 44100 }
      });
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      const chunks = [];
      recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        stream.getTracks().forEach(t => t.stop());
        try {
          const formData = new FormData();
          formData.append('audio', blob, 'recording.webm');
          formData.append('language', currentLangRef.current);
          const resp = await axios.post(`${API}/consular/voice-input`, formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
          });
          if (resp.data.success && resp.data.transcription) {
            setInput(resp.data.transcription);
          } else {
            fallbackSTT();
          }
        } catch {
          fallbackSTT();
        }
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      setIsRecording(true);
    } catch (err) {
      console.error('Mic error:', err);
    }
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
    const base64 = canvas.toDataURL('image/jpeg', 0.8).split(',')[1];
    stopCamera();
    setInput(`[Photo captured] Please help me with this document.`);
    // Send to backend
    sendDocToBackend(base64);
  }, [stopCamera]);

  const sendDocToBackend = useCallback(async (imageBase64) => {
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
          user_id: 'guest',
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
          if (evt.done && voiceOnRef.current && fullText) speakWithBackend(fullText);
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
  }, [speakWithBackend]);

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const allowed = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif', 'application/pdf'];
    if (!allowed.includes(file.type)) { alert('Invalid file type. Use JPG, PNG, or PDF.'); return; }
    if (file.size > 10 * 1024 * 1024) { alert('File exceeds 10MB limit.'); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const base64 = reader.result.split(',')[1];
      setMessages(prev => [...prev, {
        id: Date.now(), role: 'user',
        content: `📄 Document: ${file.name}`,
        time: timeNow()
      }]);
  
      sendDocToBackend(base64);
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

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

  const changeLang = useCallback(async (code) => {
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
    setIsSwitchingLang(true);

    // Close old session in DB (await so it's saved before we wipe local state)
    const oldSessionId = sessionIdRef.current;
    if (oldSessionId) {
      try {
        await fetch(`${API}/consular/session/${oldSessionId}/close`, { method: 'POST' });
      } catch { /* ignore — session will expire naturally */ }
    }

    localStorage.removeItem('consular_session_id');
    sessionIdRef.current = null;
    currentLangRef.current = code;
    setCurrentLang(code);
    scrollToTopNextRef.current = true;
    setMessages(buildWelcomeMessages());
    setInput('');
    setIsSwitchingLang(false);

    const lang = ALL_LANGS.find(l => l.code === code);
    if (lang) showLangToast(`${lang.flag} Language changed to ${lang.name}`);
  }, [currentLang, showLangToast]);

  const placeholder = LANG_PLACEHOLDERS[currentLang] || LANG_PLACEHOLDERS.en;

  return (
    <div className="seva-widget">
      {/* FAB */}
      <button
        className={`seva-fab${isSpeaking ? ' speaking' : ''}`}
        onClick={() => setIsOpen(o => !o)}
        title="Chat with Seva Setu"
        aria-label="Open Seva Setu chatbot"
      >
        <img src={BOT_IMAGE} alt="Seva Setu" className="seva-fab-img" />
        <div className="seva-fab-badge" />
      </button>

      {/* POPUP */}
      <div className={`seva-popup${isOpen ? ' open' : ''}`} role="dialog" aria-label="Seva Setu Chatbot">

        {/* HEADER */}
        <div className="seva-header">
          <div className="seva-header-top">
            <div className="seva-avatar-wrap">
              <div className={`seva-header-avatar${isSpeaking ? ' speaking' : ''}`}>
                <img src={BOT_IMAGE} alt="Seva Setu" />
              </div>
              <div className="seva-header-info">
                <div className="seva-header-name">
                  Seva Setu <span style={{ fontSize: 10, opacity: .65, fontWeight: 400 }}>सेवा सेतु</span>
                </div>
                <div className="seva-header-sub">Consulate General of India, Johannesburg</div>
                <div className="seva-status">
                  <div className={`seva-status-dot${isOnline ? '' : ' offline'}`} />
                  <div className={`seva-status-text${isOnline ? '' : ' offline'}`}>
                    {isSwitchingLang ? 'Saving session…' : isSpeaking ? 'Speaking…' : isLoading ? 'Thinking…' : isOnline ? 'Ready to Assist' : 'Offline — reconnecting…'}
                  </div>
                </div>
              </div>
            </div>
            {/* COMPACT LANG BUTTON */}
            {(() => { const cur = ALL_LANGS.find(l => l.code === currentLang) || ALL_LANGS[0]; return (
              <button ref={langBtnRef} className="seva-lang-btn" onClick={openLangMenu} disabled={isSwitchingLang}>
                <span className="seva-lang-btn-flag">{cur.flag}</span>
                <span className="seva-lang-btn-name">{cur.name}</span>
                <span className="seva-lang-btn-arrow">▼</span>
              </button>
            ); })()}
            <div className="seva-header-btns">
              <button className="seva-hbtn" title="Minimize" onClick={() => setIsOpen(false)}>−</button>
              <button className="seva-hbtn" title="Close" onClick={() => setIsOpen(false)}>✕</button>
            </div>
          </div>
        </div>


        {/* INFO TOGGLE BUTTON */}
        <button 
          className="seva-info-toggle"
          onClick={() => setShowInfo(!showInfo)}
          title={showInfo ? "Hide information" : "Show information"}
        >
          <span className="seva-info-icon">{showInfo ? '▼' : '▶'}</span>
          <span className="seva-info-label">About This Service</span>
          <span className="seva-info-count">ℹ️</span>
        </button>

        {/* INFO PANEL - COLLAPSIBLE */}
        {showInfo && (
          <div className="seva-info-panel">
            <div className="seva-info-section">
              <h4 className="seva-info-heading">🛂 What We Help With</h4>
              <ul className="seva-info-list">
                <li>Passport & Travel Documents</li>
                <li>Visa Services</li>
                <li>OCI / PIO Cards</li>
                <li>Document Attestation</li>
                <li>Appointment Booking</li>
                <li>Emergency Consular Help</li>
              </ul>
            </div>
            <div className="seva-info-section">
              <h4 className="seva-info-heading">⏰ Service Hours</h4>
              <p className="seva-info-text">Monday - Friday: 9:00 AM - 5:30 PM (SAST)</p>
            </div>
            <div className="seva-info-section">
              <h4 className="seva-info-heading">📍 Location</h4>
              <p className="seva-info-text">Consulate General of India<br/>Johannesburg, South Africa</p>
            </div>
          </div>
        )}

        {/* MESSAGES */}
        <div className="seva-messages" ref={messagesScrollRef}>
          {messages.map((msg, i) =>
            msg.role === 'user' ? (
              <div key={msg.id || i} className="seva-msg-user">
                <div className="seva-bubble-user">
                  {msg.content}
                  <div className="seva-msg-time">{msg.time}</div>
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
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              </div>
            ) : (
              <div key={msg.id || i} className="seva-msg-bot">
                <div className={`seva-msg-bot-av${isSpeaking ? ' speaking' : ''}`}>
                  <img src={BOT_IMAGE} alt="" />
                </div>
                <div className="seva-bubble-bot">
                  {msg.content ? (
                    <div className="prose">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  ) : (
                    <div className="seva-typing-dots"><span /><span /><span /></div>
                  )}
                  {msg.content && <div className="seva-msg-time">{msg.time}</div>}
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

        {/* INPUT AREA */}
        <div className="seva-input-area">
          {/* Voice toggle row */}
          <div className="seva-voice-row">
            <div className="seva-voice-info">
              <div
                className={`seva-toggle-track${voiceOn ? '' : ' off'}`}
                onClick={toggleVoice}
                title={voiceOn ? 'Disable voice' : 'Enable voice'}
              >
                <div className="seva-toggle-thumb" />
              </div>
              <div>
                <div className="seva-voice-label">{voiceOn ? '🔊 Voice Enabled' : '🔇 Voice Off'}</div>
                <div className="seva-voice-sub">Toggle to hear responses</div>
              </div>
            </div>
            <div className="seva-team-tag">Team Bharat 🇮🇳 SA</div>
          </div>

          <textarea
            ref={textareaRef}
            className="seva-textarea"
            rows={2}
            placeholder={placeholder}
            value={input}
            onChange={e => setInput(e.target.value)}
            onInput={autoResize}
            onKeyDown={handleKey}
            disabled={isLoading}
          />

          <div className="seva-actions-grid">
            <button
              className={`seva-ibtn seva-ibtn-mic${isRecording ? ' active' : ''}`}
              title={isRecording ? 'Stop recording' : 'Voice input (Whisper)'}
              onClick={handleVoiceInput}
            >
              🎤 Voice
            </button>
            <button className="seva-ibtn seva-ibtn-cam" title="Camera" onClick={startCamera}>
              📷 Camera
            </button>
            <button className="seva-ibtn seva-ibtn-doc" title="Upload document" onClick={() => fileInputRef.current?.click()}>
              📎 File
            </button>
            <button
              className="seva-send-btn-main"
              onClick={() => sendMsg()}
              disabled={isLoading || !input.trim()}
            >
              <span>{isLoading ? '⏳' : '✓'}</span> {isLoading ? 'Sending…' : 'Send'}
            </button>
            <input ref={fileInputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" style={{ display: 'none' }} onChange={handleFileUpload} />
          </div>
        </div>

        <div className="seva-footer">
          Official service of <span>Consulate General of India</span> · Johannesburg
        </div>
      </div>

      {/* LANGUAGE DROPDOWN — fixed, escapes overflow:hidden */}
      {showLangMenu && (
        <div
          className="seva-lang-dropdown"
          style={{ top: langDropPos.top, right: langDropPos.right }}
        >
          <div className="seva-lang-dropdown-hdr">Select Language</div>
          <div className="seva-lang-dropdown-list">
            {ALL_LANGS.map(l => (
              <button
                key={l.code}
                className={`seva-lang-opt${currentLang === l.code ? ' active' : ''}`}
                onClick={() => changeLang(l.code)}
              >
                <span className="seva-lang-flag">{l.flag}</span>
                <span className="seva-lang-name">{l.name}</span>
                {currentLang === l.code && <span className="seva-lang-check">✓</span>}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* LANG TOAST */}
      {langToast && <div className="seva-lang-toast">{langToast}</div>}

    </div>
  );
}
