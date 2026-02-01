import React, { useState, useEffect, useRef } from "react";
import { Mic, Camera, Send, FileText, Check, ThumbsUp, ThumbsDown, Globe, User, Mail, Phone, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import axios from "axios";
import SpeechRecognition, { useSpeechRecognition } from "react-speech-recognition";
import Webcam from "react-webcam";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// 50+ Languages support for Indian and South African citizens
const LANGUAGES = [
  // Indian Languages
  { code: "en", label: "English", flag: "🇮🇳" },
  { code: "hi", label: "हिंदी (Hindi)", flag: "🇮🇳" },
  { code: "bn", label: "বাংলা (Bengali)", flag: "🇮🇳" },
  { code: "te", label: "తెలుగు (Telugu)", flag: "🇮🇳" },
  { code: "mr", label: "मराठी (Marathi)", flag: "🇮🇳" },
  { code: "ta", label: "தமிழ் (Tamil)", flag: "🇮🇳" },
  { code: "gu", label: "ગુજરાતી (Gujarati)", flag: "🇮🇳" },
  { code: "kn", label: "ಕನ್ನಡ (Kannada)", flag: "🇮🇳" },
  { code: "ml", label: "മലയാളം (Malayalam)", flag: "🇮🇳" },
  { code: "or", label: "ଓଡ଼ିଆ (Odia)", flag: "🇮🇳" },
  { code: "pa", label: "ਪੰਜਾਬੀ (Punjabi)", flag: "🇮🇳" },
  { code: "as", label: "অসমীয়া (Assamese)", flag: "🇮🇳" },
  { code: "mai", label: "मैथिली (Maithili)", flag: "🇮🇳" },
  { code: "sat", label: "ᱥᱟᱱᱛᱟᱲᱤ (Santali)", flag: "🇮🇳" },
  { code: "ks", label: "کٲشُر (Kashmiri)", flag: "🇮🇳" },
  { code: "ne", label: "नेपाली (Nepali)", flag: "🇮🇳" },
  { code: "sd", label: "سنڌي (Sindhi)", flag: "🇮🇳" },
  { code: "kok", label: "कोंकणी (Konkani)", flag: "🇮🇳" },
  { code: "doi", label: "डोगरी (Dogri)", flag: "🇮🇳" },
  { code: "mni", label: "মৈতৈলোন্ (Manipuri)", flag: "🇮🇳" },
  { code: "brx", label: "बड़ो (Bodo)", flag: "🇮🇳" },
  { code: "ur", label: "اردو (Urdu)", flag: "🇮🇳" },
  { code: "sa", label: "संस्कृतम् (Sanskrit)", flag: "🇮🇳" },
  // South African Languages
  { code: "af", label: "Afrikaans", flag: "🇿🇦" },
  { code: "zu", label: "isiZulu", flag: "🇿🇦" },
  { code: "xh", label: "isiXhosa", flag: "🇿🇦" },
  { code: "nso", label: "Sepedi", flag: "🇿🇦" },
  { code: "st", label: "Sesotho", flag: "🇿🇦" },
  { code: "tn", label: "Setswana", flag: "🇿🇦" },
  { code: "ss", label: "siSwati", flag: "🇿🇦" },
  { code: "ve", label: "Tshivenda", flag: "🇿🇦" },
  { code: "ts", label: "Xitsonga", flag: "🇿🇦" },
  { code: "nr", label: "isiNdebele", flag: "🇿🇦" },
  // International Languages
  { code: "ar", label: "العربية (Arabic)", flag: "🌍" },
  { code: "fr", label: "Français (French)", flag: "🌍" },
  { code: "pt", label: "Português (Portuguese)", flag: "🌍" },
  { code: "es", label: "Español (Spanish)", flag: "🌍" },
  { code: "de", label: "Deutsch (German)", flag: "🌍" },
  { code: "it", label: "Italiano (Italian)", flag: "🌍" },
  { code: "ru", label: "Русский (Russian)", flag: "🌍" },
  { code: "zh", label: "中文 (Chinese)", flag: "🌍" },
  { code: "ja", label: "日本語 (Japanese)", flag: "🌍" },
  { code: "ko", label: "한국어 (Korean)", flag: "🌍" },
  { code: "th", label: "ไทย (Thai)", flag: "🌍" },
  { code: "vi", label: "Tiếng Việt (Vietnamese)", flag: "🌍" },
  { code: "id", label: "Bahasa Indonesia", flag: "🌍" },
  { code: "ms", label: "Bahasa Melayu", flag: "🌍" },
  { code: "sw", label: "Kiswahili (Swahili)", flag: "🌍" },
  { code: "am", label: "አማርኛ (Amharic)", flag: "🌍" },
  { code: "he", label: "עברית (Hebrew)", flag: "🌍" },
  { code: "fa", label: "فارسی (Persian)", flag: "🌍" },
  { code: "tr", label: "Türkçe (Turkish)", flag: "🌍" },
  { code: "pl", label: "Polski (Polish)", flag: "🌍" },
  { code: "uk", label: "Українська (Ukrainian)", flag: "🌍" },
  { code: "nl", label: "Nederlands (Dutch)", flag: "🌍" }
];

// Document types with validity rules
const DOCUMENT_TYPES = {
  passport: { name: "Passport", validityType: "expiry", copyValidDays: 90 },
  birthCertificate: { name: "Birth Certificate", validityType: "permanent", copyValidDays: 90 },
  deathCertificate: { name: "Death Certificate", validityType: "permanent", copyValidDays: 90 },
  marriageCertificate: { name: "Marriage Certificate", validityType: "affidavit", copyValidDays: 90, needsAffidavit: true },
  drivingLicense: { name: "Driving License", validityType: "expiry", copyValidDays: 90 },
  nationalId: { name: "National ID / Aadhar", validityType: "permanent", copyValidDays: 90 },
  panCard: { name: "PAN Card", validityType: "permanent", copyValidDays: 90 },
  voterCard: { name: "Voter ID Card", validityType: "permanent", copyValidDays: 90 },
  addressProof: { name: "Address Proof", validityType: "expiry", copyValidDays: 90 },
  photograph: { name: "Passport Photo", validityType: "expiry", maxAgeDays: 180, copyValidDays: 90 },
  policeReport: { name: "Police Report", validityType: "expiry", maxAgeDays: 90, copyValidDays: 90 },
  affidavit: { name: "Affidavit", validityType: "expiry", maxAgeDays: 90, copyValidDays: 90 }
};

// Available services from CGI and VFS
const SERVICES = [
  { id: "passport_new", name: "New Passport", category: "Passport", fee: 1395, processingDays: "4-6 weeks", docsRequired: 2 },
  { id: "passport_renewal", name: "Passport Renewal", category: "Passport", fee: 1395, processingDays: "4-6 weeks", docsRequired: 2 },
  { id: "passport_lost", name: "Lost Passport", category: "Passport", fee: 1395, processingDays: "4-6 weeks", docsRequired: 4 },
  { id: "visa_tourist", name: "Tourist Visa", category: "Visa", fee: 510, processingDays: "5-7 days", docsRequired: 1 },
  { id: "visa_business", name: "Business Visa", category: "Visa", fee: 1500, processingDays: "5-7 days", docsRequired: 1 },
  { id: "visa_student", name: "Student Visa", category: "Visa", fee: 150, processingDays: "4-6 weeks", docsRequired: 4 },
  { id: "oci_fresh", name: "Fresh OCI Card", category: "OCI", fee: 5015, processingDays: "8-12 weeks", docsRequired: 3 },
  { id: "oci_renewal", name: "OCI Renewal", category: "OCI", fee: 765, processingDays: "4-6 weeks", docsRequired: 2 },
  { id: "pcc", name: "Police Clearance Certificate", category: "Miscellaneous", fee: 495, processingDays: "2-4 weeks", docsRequired: 2 },
  { id: "birth_reg", name: "Child Birth Registration", category: "Miscellaneous", fee: 405, processingDays: "1-4 weeks", docsRequired: 4 },
  { id: "marriage_cert", name: "Marriage Certificate", category: "Miscellaneous", fee: 492, processingDays: "1-2 weeks", docsRequired: 2 },
  { id: "attestation", name: "Document Attestation", category: "Miscellaneous", fee: 225, processingDays: "1-2 weeks", docsRequired: 1 },
  { id: "renunciation", name: "Renunciation of Citizenship", category: "Miscellaneous", fee: 1395, processingDays: "4-8 weeks", docsRequired: 5 },
  { id: "emergency_cert", name: "Emergency Travel Document", category: "Emergency", fee: 315, processingDays: "1-3 days", docsRequired: 2 }
];


const STEPS = [
  { id: 1, label: "Register", value: "register" },
  { id: 2, label: "Upload", value: "upload" },
  { id: 3, label: "Verify", value: "verify" },
  { id: 4, label: "Sign", value: "sign" }
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
  const [feedbackGiven, setFeedbackGiven] = useState({});
  const [userProfile, setUserProfile] = useState(null);
  const [showProfileForm, setShowProfileForm] = useState(false);
  const [profileForm, setProfileForm] = useState({
    name: '',
    email: '',
    mobile: '',
    dob: ''
  });
  // Form-filling mode states
  const [formFillingMode, setFormFillingMode] = useState(false);
  const [selectedService, setSelectedService] = useState(null);
  const [formProgress, setFormProgress] = useState({ current: 0, total: 0, percent: 0 });
  const [formStatus, setFormStatus] = useState(null);
  const [showServiceSelector, setShowServiceSelector] = useState(false);
  
  const webcamRef = React.useRef(null);
  const fileInputRef = useRef(null);
  const audioRef = React.useRef(null);
  const messagesEndRef = useRef(null);
  
  const { transcript, resetTranscript, browserSupportsSpeechRecognition } = useSpeechRecognition();

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      const guestToken = "guest_" + Math.random().toString(36).substr(2, 9);
      localStorage.setItem("token", guestToken);
    }
    
    setMessages([
      {
        role: "assistant",
        content: "🙏 Namaste! I'm **Seva Setu Bot**, ready to help you with consular services.\n\n**Quick Actions:**\n- 📝 Start a new application\n- 💬 Ask questions about services\n- 📄 Upload documents\n\nHow may I assist you today?"
      }
    ]);
  }, []);

  useEffect(() => {
    if (transcript) {
      setInput(transcript);
    }
  }, [transcript]);

  // Handle form-filling mode messages
  const handleFormFillingMessage = async (messageText) => {
    if (!userProfile) {
      toast.error("Please create a profile first to start an application");
      setShowProfileForm(true);
      return;
    }

    if (!selectedService) {
      toast.error("Please select a service first");
      setShowServiceSelector(true);
      return;
    }

    setIsTyping(true);
    
    try {
      const response = await axios.post(`${API}/consular/form-filling`, {
        session_id: sessionId,
        profile_id: userProfile.profile_id,
        service_type: selectedService.id,
        message: messageText,
        current_step: formProgress.current,
        form_data: {}
      });

      const data = response.data;
      
      // Update form progress
      setFormProgress({
        current: data.current_step,
        total: data.total_steps,
        percent: data.progress_percent
      });
      setFormStatus(data.status);

      // Add bot response
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response, formData: data.form_data }
      ]);

      // Check if form is completed
      if (data.status === "completed") {
        setFormFillingMode(false);
        setSelectedService(null);
        toast.success("Application submitted successfully!");
      }

    } catch (error) {
      toast.error("Error processing form. Please try again.");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "❌ Sorry, there was an error. Please try again or type **STOP** to pause." }
      ]);
    } finally {
      setIsTyping(false);
    }
  };

  // Start form filling for a service
  const startFormFilling = async (service) => {
    if (!userProfile) {
      toast.error("Please create a profile first");
      setShowProfileForm(true);
      return;
    }

    setSelectedService(service);
    setFormFillingMode(true);
    setShowServiceSelector(false);
    setFormProgress({ current: 0, total: 0, percent: 0 });
    
    // Add initial message
    setMessages((prev) => [
      ...prev,
      { role: "user", content: `I want to apply for ${service.name}` }
    ]);

    // Trigger form filling start
    await handleFormFillingMessage("start");
  };

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    const messageText = input;
    setInput("");
    resetTranscript();
    
    // Check for form filling mode
    if (formFillingMode) {
      await handleFormFillingMessage(messageText);
      return;
    }

    // Check for service application intent
    const applicationKeywords = ['apply', 'application', 'start form', 'fill form', 'passport', 'visa', 'oci', 'pcc'];
    const isApplicationIntent = applicationKeywords.some(kw => messageText.toLowerCase().includes(kw));
    
    if (isApplicationIntent && userProfile) {
      // Show service selector
      setShowServiceSelector(true);
      setMessages((prev) => [
        ...prev,
        { 
          role: "assistant", 
          content: "📋 **Select a Service to Apply**\n\nI'll guide you through the application step-by-step using your saved documents. Which service would you like to apply for?\n\n*Click on a service below to begin:*"
        }
      ]);
      setIsTyping(false);
      return;
    }
    
    // Show typing indicator
    setIsTyping(true);

    try {
      // Use selected language or auto-detect from input
      const isHindi = /[\u0900-\u097F]/.test(messageText);
      const isTamil = /[\u0B80-\u0BFF]/.test(messageText);
      const langCode = isHindi ? "hi" : isTamil ? "ta" : selectedLanguage;

      const response = await axios.post(
        `${API}/consular/chat`,
        {
          message: messageText,
          session_id: sessionId,
          user_id: "guest",
          enable_voice: enableVoice,
          language: langCode
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
      const typingSpeed = 20; // milliseconds per character
      
      // Add empty message that will be updated
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

  const handleVoice = () => {
    if (isRecording) {
      SpeechRecognition.stopListening();
      setIsRecording(false);
    } else {
      SpeechRecognition.startListening({ continuous: true, language: selectedLanguage === 'hi' ? 'hi-IN' : selectedLanguage === 'ta' ? 'ta-IN' : 'en-US' });
      setIsRecording(true);
      toast.info("Listening... Speak now");
    }
  };

  const handleFeedback = async (messageIndex, isPositive) => {
    const feedbackType = isPositive ? 'positive' : 'negative';
    setFeedbackGiven(prev => ({ ...prev, [messageIndex]: feedbackType }));
    
    try {
      await axios.post(`${API}/consular/feedback`, {
        session_id: sessionId,
        message_index: messageIndex,
        feedback: feedbackType,
        timestamp: new Date().toISOString()
      });
      toast.success(isPositive ? "Thanks for the positive feedback! 👍" : "Thanks for the feedback. We'll improve! 🙏");
    } catch (error) {
      // Silently log - feedback is non-critical
      console.log("Feedback logged locally");
      toast.success(isPositive ? "Thanks for the feedback! 👍" : "We appreciate your feedback! 🙏");
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Generate unique profile ID
  const generateProfileId = (name, dob) => {
    const namePart = name.replace(/\s+/g, '').substring(0, 4).toUpperCase();
    const dobPart = dob.replace(/-/g, '');
    const hash = Math.random().toString(36).substring(2, 6).toUpperCase();
    return `${namePart}-${dobPart}-${hash}`;
  };

  // Handle profile creation
  const handleCreateProfile = async () => {
    const { name, email, mobile, dob } = profileForm;
    
    if (!name || !email || !mobile || !dob) {
      toast.error('Please fill in all fields');
      return;
    }
    
    // Email validation
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      toast.error('Please enter a valid email address');
      return;
    }
    
    // Mobile validation (basic)
    if (!/^\+?[\d\s-]{8,}$/.test(mobile)) {
      toast.error('Please enter a valid mobile number');
      return;
    }
    
    const profileId = generateProfileId(name, dob);
    
    try {
      const response = await axios.post(`${API}/consular/create-profile`, {
        name,
        email,
        mobile,
        dob,
        profile_id: profileId,
        session_id: sessionId
      });
      
      if (response.data.success) {
        setUserProfile({
          ...profileForm,
          profile_id: profileId
        });
        setShowProfileForm(false);
        setCurrentStep("upload");
        
        // Add confirmation message to chat
        setMessages((prev) => [
          ...prev,
          { 
            role: "assistant", 
            content: `✅ **Profile Created Successfully!**\n\n**Your Profile ID:** \`${profileId}\`\n\n**Name:** ${name}\n**Email:** ${email}\n**Mobile:** ${mobile}\n**DOB:** ${dob}\n\n---\n\nYou can now proceed with document upload. What service do you need help with?`
          }
        ]);
        
        toast.success(`Profile created! ID: ${profileId}`);
      }
    } catch (error) {
      toast.error('Failed to create profile. Please try again.');
    }
  };

  // Check if user needs profile for certain actions
  const requiresProfile = (action) => {
    const profileActions = ['apply', 'submit', 'application', 'form', 'document', 'upload'];
    return profileActions.some(a => action.toLowerCase().includes(a));
  };

  const handleFileUpload = async (e) => {
    // Check if profile exists for document upload
    if (!userProfile) {
      toast.info('Please create a profile first to upload documents');
      setShowProfileForm(true);
      return;
    }
    
    const file = e.target.files[0];
    if (!file) return;

    // Validate file type
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf'];
    if (!allowedTypes.includes(file.type)) {
      toast.error('Invalid file format. Please upload JPG, PNG, or PDF only.');
      return;
    }

    // Validate file size (10MB max)
    if (file.size > 10 * 1024 * 1024) {
      toast.error('File size exceeds 10MB limit.');
      return;
    }

    toast.success(`Document "${file.name}" uploaded successfully!`);
    
    // Convert to base64 and process
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
            { role: "assistant", content: `Document scanned successfully! \\n\\n${response.data.extracted_data}` }
          ]);
        }
      } catch (error) {
        toast.error('Document processing failed. Please try again.');
      }
    };
    reader.readAsDataURL(file);
    
    // Reset input
    e.target.value = '';
  };

  const handleCapture = () => {
    const imageSrc = webcamRef.current.getScreenshot();
    if (imageSrc) {
      toast.success("Document captured! Processing...");
      setShowCamera(false);
    }
  };

  const currentStepIndex = STEPS.findIndex((s) => s.value === currentStep);

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 to-blue-50 p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex justify-center mb-8">
          <div className="flex items-center w-full max-w-2xl" data-testid="progress-stepper">
            {STEPS.map((step, index) => (
              <React.Fragment key={step.id}>
                <div className="flex flex-col items-center">
                  <div
                    className={`${
                      index <= currentStepIndex
                        ? "bg-[#E06F2C] text-white shadow-lg ring-4 ring-orange-100"
                        : "bg-slate-200 text-slate-500"
                    } w-12 h-12 rounded-full flex items-center justify-center font-bold transition-all`}
                    data-testid={`step-${step.value}`}
                  >
                    {index < currentStepIndex ? <Check className="w-6 h-6" /> : step.id}
                  </div>
                  <span className="text-sm mt-2 font-medium text-[#1A2E40]">{step.label}</span>
                </div>
                {index < STEPS.length - 1 && (
                  <div
                    className={`h-1 flex-1 mx-4 ${index < currentStepIndex ? "step-line-active" : "bg-slate-200"}`}
                  />
                )}
              </React.Fragment>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          <div className="lg:col-span-4">
            <div className="glass-card rounded-xl p-6 text-center" data-testid="bot-avatar">
              {/* Video Avatar Container */}
              <div className={`relative w-full aspect-square max-w-xs mx-auto mb-4 rounded-full overflow-hidden transition-all duration-500 ${
                isSpeaking ? 'ring-4 ring-[#2E8B57] ring-offset-4 ring-offset-white shadow-2xl shadow-green-400/50 scale-105' : 'ring-4 ring-[#E06F2C] ring-offset-4 ring-offset-white shadow-xl'
              }`}>
                {/* Avatar Image/Video */}
                <div className="relative w-full h-full bg-gradient-to-br from-orange-50 to-blue-50">
                  <img
                    src="https://images.unsplash.com/photo-1766857454322-d902dfb4a532?q=85&w=400"
                    alt="Seva Setu Bot - Professional Indian Consular Assistant"
                    className={`w-full h-full object-cover ${isSpeaking ? 'brightness-110 scale-105' : 'brightness-100 scale-100'} transition-all duration-500`}
                  />
                  
                  {/* Overlay when speaking - simulates mouth movement */}
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
                
                {/* Speaking indicator badge */}
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
              
              {/* Bot Info */}
              <div className="space-y-3">
                <h2 className="text-2xl font-bold text-[#1A2E40]">Seva Setu Bot</h2>
                <p className="text-lg font-semibold text-[#E06F2C]">🙏 Namaste</p>
                <p className="text-sm text-gray-600 italic">Representing Modern India</p>
                
                {/* Status Indicator */}
                <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full transition-all duration-300 ${
                  isSpeaking ? 'bg-gradient-to-r from-green-100 to-green-50' : formFillingMode ? 'bg-gradient-to-r from-blue-100 to-blue-50' : 'bg-gradient-to-r from-orange-100 to-orange-50'
                }`}>
                  <span className={`w-3 h-3 rounded-full ${isSpeaking ? 'bg-[#2E8B57] animate-pulse' : formFillingMode ? 'bg-blue-500 animate-pulse' : 'bg-[#E06F2C]'}`}></span>
                  <span className={`text-sm font-semibold ${isSpeaking ? 'text-[#2E8B57]' : formFillingMode ? 'text-blue-700' : 'text-[#1A2E40]'}`}>
                    {isSpeaking ? "🎙️ Speaking..." : formFillingMode ? "📝 Form Mode" : "✨ Ready to Assist"}
                  </span>
                </div>
                
                {/* Profile Button */}
                {!userProfile ? (
                  <Button
                    onClick={() => setShowProfileForm(true)}
                    className="w-full bg-[#1A2E40] hover:bg-[#132230] text-white mt-2"
                    data-testid="open-profile-btn"
                  >
                    <User className="w-4 h-4 mr-2" />
                    Create Profile
                  </Button>
                ) : (
                  <div className="mt-2 space-y-2">
                    <div className="p-3 bg-green-50 rounded-lg border border-green-200" data-testid="profile-info">
                      <p className="text-xs font-semibold text-green-800 uppercase">Your Profile</p>
                      <p className="text-sm font-bold text-green-700">{userProfile.name}</p>
                      <p className="text-xs text-green-600">ID: {userProfile.profile_id}</p>
                    </div>
                    
                    {/* Start Application Button */}
                    <Button
                      onClick={() => setShowServiceSelector(true)}
                      className="w-full bg-gradient-to-r from-[#E06F2C] to-[#FF8C42] hover:from-[#C55D20] hover:to-[#E06F2C] text-white"
                      data-testid="start-application-btn"
                    >
                      <FileText className="w-4 h-4 mr-2" />
                      Start Application
                    </Button>
                  </div>
                )}
              </div>
              
              {/* Voice Toggle - Premium Design */}
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
                    <span className="text-2xl">{enableVoice ? "🔊" : "🔇"}</span>
                    <div className="text-left">
                      <p className="text-sm font-bold text-[#1A2E40] group-hover:text-[#E06F2C] transition-colors">
                        {enableVoice ? "Voice Enabled" : "Voice Disabled"}
                      </p>
                      <p className="text-xs text-gray-500">Toggle to hear responses</p>
                    </div>
                  </div>
                </label>
                
                {/* Note about video avatar */}
                <div className="mt-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
                  <p className="text-xs text-blue-800">
                    💡 <strong>Demo Mode:</strong> Full video avatar with lip-sync available with Akool upgrade
                  </p>
                </div>
              </div>

              {/* Organization Info */}
              <div className="mt-6 pt-6 border-t-2 border-gray-100 space-y-3">
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Official Representative</p>
                  <p className="text-sm font-bold text-[#1A2E40] mt-1">Consulate General of India</p>
                  <p className="text-sm text-gray-600">Johannesburg, South Africa</p>
                </div>
                
                {/* Language Badges */}
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Supported Languages</p>
                  <div className="flex flex-wrap justify-center gap-2">
                    <span className="text-xs px-3 py-1.5 bg-gradient-to-r from-orange-100 to-orange-50 text-[#E06F2C] rounded-full font-semibold border border-orange-200">Hindi</span>
                    <span className="text-xs px-3 py-1.5 bg-gradient-to-r from-orange-100 to-orange-50 text-[#E06F2C] rounded-full font-semibold border border-orange-200">English</span>
                    <span className="text-xs px-3 py-1.5 bg-gradient-to-r from-orange-100 to-orange-50 text-[#E06F2C] rounded-full font-semibold border border-orange-200">Zulu</span>
                    <span className="text-xs px-3 py-1.5 bg-gradient-to-r from-orange-100 to-orange-50 text-[#E06F2C] rounded-full font-semibold border border-orange-200">Afrikaans</span>
                  </div>
                </div>
                
                {/* Language Selector */}
                <div className="mt-4 pt-4 border-t-2 border-gray-100">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Select Language</p>
                  <Select value={selectedLanguage} onValueChange={setSelectedLanguage}>
                    <SelectTrigger className="w-full" data-testid="language-selector">
                      <Globe className="w-4 h-4 mr-2" />
                      <SelectValue placeholder="Select Language" />
                    </SelectTrigger>
                    <SelectContent>
                      {LANGUAGES.map((lang) => (
                        <SelectItem key={lang.code} value={lang.code} data-testid={`lang-${lang.code}`}>
                          <span className="flex items-center gap-2">
                            <span>{lang.flag}</span>
                            <span>{lang.label}</span>
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-8">
            <div className="glass-card rounded-xl shadow-lg flex flex-col" style={{ height: "600px" }}>
              {/* Form Filling Progress Bar */}
              {formFillingMode && formProgress.total > 0 && (
                <div className="px-6 py-3 bg-gradient-to-r from-orange-50 to-white border-b border-orange-200" data-testid="form-progress">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-[#E06F2C]" />
                      <span className="text-sm font-semibold text-[#1A2E40]">{selectedService?.name}</span>
                    </div>
                    <span className="text-xs font-bold text-[#E06F2C]">
                      Step {formProgress.current}/{formProgress.total} • {formProgress.percent}%
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-gradient-to-r from-[#E06F2C] to-[#FF8C42] h-2 rounded-full transition-all duration-500"
                      style={{ width: `${formProgress.percent}%` }}
                    ></div>
                  </div>
                  <div className="flex justify-between mt-1">
                    <span className="text-xs text-gray-500">
                      {formStatus === 'consent_pending' && '⏳ Waiting for consent'}
                      {formStatus === 'in_progress' && '📝 Filling form...'}
                      {formStatus === 'paused' && '⏸️ Paused'}
                      {formStatus === 'review' && '👁️ Review mode'}
                      {formStatus === 'completed' && '✅ Completed'}
                    </span>
                    {formFillingMode && (
                      <button 
                        onClick={() => { setFormFillingMode(false); setSelectedService(null); }}
                        className="text-xs text-red-500 hover:text-red-700"
                      >
                        Cancel Application
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Service Selector */}
              {showServiceSelector && (
                <div className="px-6 py-4 bg-gradient-to-r from-blue-50 to-white border-b border-blue-200" data-testid="service-selector">
                  <p className="text-sm font-semibold text-[#1A2E40] mb-3">📋 Select a Service:</p>
                  <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                    {SERVICES.map((service) => (
                      <button
                        key={service.id}
                        onClick={() => startFormFilling(service)}
                        className="p-3 text-left bg-white border border-gray-200 rounded-lg hover:border-[#E06F2C] hover:bg-orange-50 transition-all"
                        data-testid={`service-${service.id}`}
                      >
                        <p className="text-sm font-semibold text-[#1A2E40]">{service.name}</p>
                        <p className="text-xs text-gray-500">R {service.fee} • {service.processingDays}</p>
                      </button>
                    ))}
                  </div>
                  <button 
                    onClick={() => setShowServiceSelector(false)}
                    className="mt-2 text-xs text-gray-500 hover:text-gray-700"
                  >
                    ← Back to chat
                  </button>
                </div>
              )}

              <div className="flex-1 overflow-y-auto p-6 space-y-4" data-testid="chat-messages">
                {messages.map((msg, index) => (
                  <div
                    key={index}
                    className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
                    data-testid={`message-${index}`}
                  >
                    <div
                      className={`max-w-md px-4 py-3 rounded-lg ${
                        msg.role === "user"
                          ? "bg-[#E06F2C] text-white"
                          : "bg-white border border-gray-200 text-[#1A2E40]"
                      }`}
                    >
                      {msg.role === "assistant" ? (
                        <div className="prose prose-sm max-w-none
                            prose-headings:text-[#1A2E40] prose-headings:font-bold
                            prose-p:text-[#1A2E40] prose-p:my-2
                            prose-ul:my-2 prose-ol:my-2
                            prose-li:text-[#1A2E40]
                            prose-strong:text-[#E06F2C] prose-strong:font-semibold
                            prose-a:text-[#E06F2C] prose-a:no-underline hover:prose-a:underline">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        msg.content
                      )}
                    </div>
                    
                    {/* Feedback buttons for assistant messages */}
                    {msg.role === "assistant" && index > 0 && (
                      <div className="flex items-center gap-2 mt-2" data-testid={`feedback-${index}`}>
                        <span className="text-xs text-gray-400">Was this helpful?</span>
                        <button
                          onClick={() => handleFeedback(index, true)}
                          className={`p-1.5 rounded-full transition-all ${
                            feedbackGiven[index] === 'positive' 
                              ? 'bg-green-100 text-green-600' 
                              : 'hover:bg-gray-100 text-gray-400 hover:text-green-600'
                          }`}
                          disabled={!!feedbackGiven[index]}
                          data-testid={`feedback-up-${index}`}
                        >
                          <ThumbsUp className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleFeedback(index, false)}
                          className={`p-1.5 rounded-full transition-all ${
                            feedbackGiven[index] === 'negative' 
                              ? 'bg-red-100 text-red-600' 
                              : 'hover:bg-gray-100 text-gray-400 hover:text-red-600'
                          }`}
                          disabled={!!feedbackGiven[index]}
                          data-testid={`feedback-down-${index}`}
                        >
                          <ThumbsDown className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                
                {/* Typing Indicator */}
                {isTyping && (
                  <div className="flex justify-start" data-testid="typing-indicator">
                    <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex items-center gap-2">
                      <div className="flex gap-1">
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

              <div className="border-t border-gray-200 p-4">
                <div className="flex gap-2">
                  <Textarea
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyPress={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), handleSend())}
                    placeholder="Type your message..."
                    className="flex-1 min-h-[60px]"
                    data-testid="chat-input"
                  />
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleFileUpload}
                    accept=".jpg,.jpeg,.png,.pdf"
                    style={{ display: 'none' }}
                    data-testid="file-input"
                  />
                  <div className="flex flex-col gap-2">
                    {browserSupportsSpeechRecognition && (
                      <Button
                        onClick={handleVoice}
                        className={`${
                          isRecording ? "bg-red-500 hover:bg-red-600 mic-active" : "bg-[#2E8B57] hover:bg-[#256B47]"
                        } text-white`}
                        data-testid="voice-btn"
                        title="Voice Input"
                      >
                        <Mic className="w-5 h-5" />
                      </Button>
                    )}
                    <Button
                      onClick={() => setShowCamera(true)}
                      className="bg-[#1A2E40] hover:bg-[#132230] text-white"
                      data-testid="camera-btn"
                      title="Scan Document with Camera"
                    >
                      <Camera className="w-5 h-5" />
                    </Button>
                    <Button
                      onClick={() => fileInputRef.current?.click()}
                      className="bg-[#E06F2C] hover:bg-[#C55D20] text-white"
                      data-testid="upload-btn"
                      title="Upload Document (JPG, PNG, PDF)"
                    >
                      <FileText className="w-5 h-5" />
                    </Button>
                    <Button
                      onClick={handleSend}
                      className="bg-[#E06F2C] hover:bg-[#C55D20] text-white"
                      data-testid="send-btn"
                      title="Send Message"
                    >
                      <Send className="w-5 h-5" />
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={showCamera} onOpenChange={setShowCamera}>
        <DialogContent className="max-w-2xl" data-testid="camera-dialog">
          <h2 className="text-2xl font-bold text-[#1A2E40] mb-4">Capture Document</h2>
          <Webcam
            ref={webcamRef}
            screenshotFormat="image/jpeg"
            className="w-full rounded-lg"
          />
          <div className="flex gap-4 mt-4">
            <Button onClick={handleCapture} className="flex-1 bg-[#E06F2C] hover:bg-[#C55D20]" data-testid="capture-btn">
              <Camera className="w-5 h-5 mr-2" />
              Capture
            </Button>
            <Button onClick={() => setShowCamera(false)} variant="outline" className="flex-1" data-testid="cancel-capture-btn">
              Cancel
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Profile Creation Dialog */}
      <Dialog open={showProfileForm} onOpenChange={setShowProfileForm}>
        <DialogContent className="max-w-md" data-testid="profile-dialog">
          <DialogHeader>
            <DialogTitle className="text-2xl font-bold text-[#1A2E40] flex items-center gap-2">
              <User className="w-6 h-6 text-[#E06F2C]" />
              Create Your Profile
            </DialogTitle>
          </DialogHeader>
          
          <div className="space-y-4 mt-4">
            <p className="text-sm text-gray-600">
              To proceed with your application, please provide your details. This helps us serve you better.
            </p>
            
            <div className="space-y-3">
              <div>
                <Label htmlFor="profile-name" className="flex items-center gap-2">
                  <User className="w-4 h-4" /> Full Name
                </Label>
                <Input
                  id="profile-name"
                  value={profileForm.name}
                  onChange={(e) => setProfileForm(prev => ({ ...prev, name: e.target.value }))}
                  placeholder="Enter your full name"
                  className="mt-1"
                  data-testid="profile-name-input"
                />
              </div>
              
              <div>
                <Label htmlFor="profile-email" className="flex items-center gap-2">
                  <Mail className="w-4 h-4" /> Email Address
                </Label>
                <Input
                  id="profile-email"
                  type="email"
                  value={profileForm.email}
                  onChange={(e) => setProfileForm(prev => ({ ...prev, email: e.target.value }))}
                  placeholder="your.email@example.com"
                  className="mt-1"
                  data-testid="profile-email-input"
                />
              </div>
              
              <div>
                <Label htmlFor="profile-mobile" className="flex items-center gap-2">
                  <Phone className="w-4 h-4" /> Mobile Number
                </Label>
                <Input
                  id="profile-mobile"
                  type="tel"
                  value={profileForm.mobile}
                  onChange={(e) => setProfileForm(prev => ({ ...prev, mobile: e.target.value }))}
                  placeholder="+27 XX XXX XXXX"
                  className="mt-1"
                  data-testid="profile-mobile-input"
                />
              </div>
              
              <div>
                <Label htmlFor="profile-dob" className="flex items-center gap-2">
                  <Calendar className="w-4 h-4" /> Date of Birth
                </Label>
                <Input
                  id="profile-dob"
                  type="date"
                  value={profileForm.dob}
                  onChange={(e) => setProfileForm(prev => ({ ...prev, dob: e.target.value }))}
                  className="mt-1"
                  data-testid="profile-dob-input"
                />
              </div>
            </div>
            
            <div className="flex gap-3 pt-4">
              <Button
                onClick={handleCreateProfile}
                className="flex-1 bg-[#E06F2C] hover:bg-[#C55D20] text-white"
                data-testid="create-profile-btn"
              >
                <Check className="w-4 h-4 mr-2" />
                Create Profile
              </Button>
              <Button
                onClick={() => setShowProfileForm(false)}
                variant="outline"
                className="flex-1"
                data-testid="cancel-profile-btn"
              >
                Cancel
              </Button>
            </div>
            
            <p className="text-xs text-gray-500 text-center">
              Your information is secure and will only be used for consular services.
            </p>
          </div>
        </DialogContent>
      </Dialog>

      {/* Profile Status Badge */}
      {userProfile && (
        <div className="fixed bottom-4 left-4 bg-green-100 border border-green-300 rounded-lg px-4 py-2 shadow-lg" data-testid="profile-badge">
          <div className="flex items-center gap-2">
            <Check className="w-4 h-4 text-green-600" />
            <span className="text-sm text-green-800 font-medium">
              Profile: {userProfile.profile_id}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}