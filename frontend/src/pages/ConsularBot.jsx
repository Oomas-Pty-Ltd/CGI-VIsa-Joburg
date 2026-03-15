import React, { useState, useEffect, useRef, useCallback } from "react";
import { Mic, Camera, Send, FileText, Check, AlertTriangle, Globe, X, Volume2, VolumeX } from "lucide-react";
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

const STEPS = [
  { id: 1, label: "Register", value: "register" },
  { id: 2, label: "Upload", value: "upload" },
  { id: 3, label: "Verify", value: "verify" },
  { id: 4, label: "Sign", value: "sign" }
];

// Language configuration with codes
const LANGUAGES = [
  { code: "en", name: "English", flag: "🇬🇧" },
  { code: "hi", name: "हिंदी (Hindi)", flag: "🇮🇳" },
  { code: "ta", name: "தமிழ் (Tamil)", flag: "🇮🇳" },
  { code: "zu", name: "isiZulu", flag: "🇿🇦" },
  { code: "af", name: "Afrikaans", flag: "🇿🇦" }
];

export default function ConsularBot() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [currentStep, setCurrentStep] = useState("register");
  const [isRecording, setIsRecording] = useState(false);
  const [showCamera, setShowCamera] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [enableVoice, setEnableVoice] = useState(true);
  const [isTyping, setIsTyping] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState("en");
  const [showLanguageMenu, setShowLanguageMenu] = useState(false);
  const [cameraStream, setCameraStream] = useState(null);
  const [cameraError, setCameraError] = useState(null);
  const [mediaRecorder, setMediaRecorder] = useState(null);
  const [audioChunks, setAudioChunks] = useState([]);
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const fileInputRef = useRef(null);
  const audioRef = useRef(null);
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom
  const scrollToBottom = (smooth = true) => {
    messagesEndRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "instant" });
  };

  useEffect(() => {
    // Use instant scroll during typing to keep up with content growth
    scrollToBottom(!isTyping);
  }, [messages, isTyping]);

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
  }, []);

  // Cleanup camera stream on unmount
  useEffect(() => {
    return () => {
      if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
      }
    };
  }, [cameraStream]);

  const handleSend = async () => {
    if (!input.trim()) return;

    // Stop any currently playing audio
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setIsSpeaking(false);
    }

    const userMessage = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    const messageText = input;
    setInput("");
    
    // Show typing indicator
    setIsTyping(true);

    try {
      const response = await axios.post(
        `${API}/consular/chat`,
        {
          message: messageText,
          session_id: sessionId,
          user_id: "guest",
          enable_voice: enableVoice,
          language: selectedLanguage
        }
      );

      if (!sessionId) {
        setSessionId(response.data.session_id);
      }

      // Type out the response with animation
      const botResponse = response.data.response;
      await typeMessage(botResponse);
      
      setCurrentStep(response.data.step);
      setIsTyping(false);

      // Play audio response if available
      if (response.data.audio_base64 && enableVoice) {
        playAudio(response.data.audio_base64);
      }
    } catch (error) {
      console.error("Chat error:", error);
      toast.error("Failed to send message. Please try again.");
      setMessages((prev) => prev.slice(0, -1));
      setIsTyping(false);
    }
  };

  const typeMessage = async (fullMessage) => {
    return new Promise((resolve) => {
      let currentText = "";
      let index = 0;
      const typingSpeed = 15;
      
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
      
      const typeInterval = setInterval(() => {
        if (index < fullMessage.length) {
          currentText += fullMessage[index];
          setMessages((prev) => {
            const newMessages = [...prev];
            newMessages[newMessages.length - 1] = {
              role: "assistant",
              content: currentText
            };
            return newMessages;
          });
          index++;
        } else {
          clearInterval(typeInterval);
          resolve();
        }
      }, typingSpeed);
    });
  };

  const playAudio = (audioBase64) => {
    try {
      setIsSpeaking(true);
      const audio = new Audio(`data:audio/mp3;base64,${audioBase64}`);
      audioRef.current = audio;
      
      audio.onended = () => {
        setIsSpeaking(false);
      };
      
      audio.onerror = () => {
        setIsSpeaking(false);
        toast.error("Audio playback failed");
      };
      
      audio.play();
    } catch (error) {
      setIsSpeaking(false);
      console.error("Audio play error:", error);
    }
  };

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
          formData.append('language', selectedLanguage);
          
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
            recognition.lang = selectedLanguage === 'hi' ? 'hi-IN' : 
                              selectedLanguage === 'ta' ? 'ta-IN' :
                              selectedLanguage === 'zu' ? 'zu-ZA' :
                              selectedLanguage === 'af' ? 'af-ZA' : 'en-US';
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
  }, [selectedLanguage]);

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
    
    toast.success("Document captured! Processing...");
    stopCamera();
    
    // Send to backend for processing
    try {
      const response = await axios.post(`${API}/consular/document-scan`, {
        image_base64: imageBase64,
        document_type: 'passport',
        session_id: sessionId
      });
      
      if (response.data.success) {
        toast.success('Document processed! Data extracted.');
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `📄 **Document Scanned Successfully!**\n\n${response.data.extracted_data}` }
        ]);
      }
    } catch (error) {
      console.error("Document scan error:", error);
      toast.error('Document processing failed. Please try again.');
    }
  }, [sessionId, stopCamera]);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
    if (!allowedTypes.includes(file.type)) {
      toast.error('Invalid file format. Please upload JPG, PNG, or PDF only.');
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      toast.error('File size exceeds 10MB limit.');
      return;
    }

    toast.success(`Document "${file.name}" uploaded successfully!`);
    
    const reader = new FileReader();
    reader.onload = async () => {
      const base64 = reader.result.split(',')[1];
      
      try {
        const response = await axios.post(`${API}/consular/document-scan`, {
          image_base64: base64,
          document_type: 'passport',
          session_id: sessionId
        });
        
        if (response.data.success) {
          toast.success('Document processed! Data extracted and translated.');
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: `📄 **Document Scanned!**\n\n${response.data.extracted_data}` }
          ]);
        }
      } catch (error) {
        toast.error('Document processing failed. Please try again.');
      }
    };
    reader.readAsDataURL(file);
    e.target.value = '';
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
        {isTyping && "Seva Setu is typing a response..."}
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
                className="absolute right-0 mt-2 w-56 bg-white rounded-lg shadow-xl border z-50" 
                data-testid="language-menu"
                role="listbox"
                aria-label="Select language"
              >
                <div className="p-2">
                  <p className="text-xs text-gray-500 px-3 py-1 font-semibold uppercase" id="lang-label">Select Language</p>
                  {LANGUAGES.map((lang) => (
                    <button
                      key={lang.code}
                      onClick={() => {
                        setSelectedLanguage(lang.code);
                        setShowLanguageMenu(false);
                        toast.success(`Language set to ${lang.name}`);
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
                      onChange={(e) => setEnableVoice(e.target.checked)}
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
                    {SUPPORTED_LANGUAGES.map((lang) => (
                      <span key={lang} className="text-xs px-3 py-1.5 bg-gradient-to-r from-orange-100 to-orange-50 text-[#E06F2C] rounded-full font-semibold border border-orange-200">{lang}</span>
                    ))}
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
                        <div className="prose prose-sm max-w-none ml-7 prose-p:my-1 prose-p:text-current prose-ul:my-1 prose-li:text-current prose-strong:font-bold">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                      </div>
                    ) : (
                      <div
                        className={`max-w-md px-4 py-3 rounded-lg ${
                          msg.role === "user"
                            ? "bg-[#E06F2C] text-white"
                            : "bg-white border border-gray-200 text-[#1A2E40]"
                        }`}
                      >
                        {msg.role === "assistant" ? (
                          <div className="prose prose-sm max-w-none prose-headings:text-[#1A2E40] prose-headings:font-bold prose-p:text-[#1A2E40] prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:text-[#1A2E40] prose-strong:text-[#E06F2C] prose-strong:font-semibold prose-a:text-[#E06F2C] prose-a:no-underline hover:prose-a:underline">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {msg.content}
                            </ReactMarkdown>
                          </div>
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
                    aria-label="Seva Setu is typing"
                  >
                    <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex items-center gap-2">
                      <div className="flex gap-1" aria-hidden="true">
                        <span className="w-2 h-2 bg-[#E06F2C] rounded-full animate-bounce" style={{animationDelay: '0ms'}}></span>
                        <span className="w-2 h-2 bg-[#E06F2C] rounded-full animate-bounce" style={{animationDelay: '150ms'}}></span>
                        <span className="w-2 h-2 bg-[#E06F2C] rounded-full animate-bounce" style={{animationDelay: '300ms'}}></span>
                      </div>
                      <span className="text-sm text-gray-500">Seva Setu is typing...</span>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

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
                    onKeyPress={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSend())}
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
                    <Button
                      onClick={handleSend}
                      className="bg-[#E06F2C] hover:bg-[#C55D20] text-white min-h-[44px] min-w-[44px]"
                      data-testid="send-btn"
                      aria-label="Send message"
                    >
                      <Send className="w-5 h-5" aria-hidden="true" />
                    </Button>
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
    </div>
  );
}
