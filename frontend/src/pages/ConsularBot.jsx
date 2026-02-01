import React, { useState, useEffect, useRef } from "react";
import { Mic, Camera, Send, FileText, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import axios from "axios";
import SpeechRecognition, { useSpeechRecognition } from "react-speech-recognition";
import Webcam from "react-webcam";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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
  const webcamRef = React.useRef(null);
  const fileInputRef = useRef(null);
  const audioRef = React.useRef(null);
  
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
        content: "🙏 Namaste! I'm Seva Setu Bot, ready to help you with consular services. How may I assist you today?"
      }
    ]);
  }, []);

  useEffect(() => {
    if (transcript) {
      setInput(transcript);
    }
  }, [transcript]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    const messageText = input;
    setInput("");
    resetTranscript();
    
    // Show typing indicator
    setIsTyping(true);

    try {
      // Detect language from input
      const isHindi = /[\u0900-\u097F]/.test(messageText);
      const isTamil = /[\u0B80-\u0BFF]/.test(messageText);
      const langCode = isHindi ? "hi" : isTamil ? "ta" : "en";

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
      SpeechRecognition.startListening({ continuous: true });
      setIsRecording(true);
    }
  };

  const handleFileUpload = async (e) => {
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
              <div className={`relative w-40 h-40 rounded-full mx-auto mb-4 transition-all duration-500 ${
                isSpeaking ? 'ring-4 ring-[#2E8B57] ring-offset-4 ring-offset-white shadow-2xl shadow-green-400/50 scale-105' : 'ring-4 ring-[#E06F2C] ring-offset-4 ring-offset-white shadow-xl'
              }`}>
                <img
                  src="https://images.unsplash.com/photo-1766857454322-d902dfb4a532?q=85"
                  alt="Seva Setu Bot - Modern India Representative"
                  className={`w-full h-full rounded-full object-cover ${isSpeaking ? 'brightness-110' : 'brightness-100'} transition-all duration-500`}
                />
                {isSpeaking && (
                  <div className="absolute -bottom-2 left-1/2 transform -translate-x-1/2">
                    <div className="flex gap-1 bg-white px-3 py-1 rounded-full shadow-lg">
                      <span className="w-2 h-2 bg-[#2E8B57] rounded-full animate-bounce" style={{animationDelay: '0ms'}}></span>
                      <span className="w-2 h-2 bg-[#2E8B57] rounded-full animate-bounce" style={{animationDelay: '150ms'}}></span>
                      <span className="w-2 h-2 bg-[#2E8B57] rounded-full animate-bounce" style={{animationDelay: '300ms'}}></span>
                    </div>
                  </div>
                )}
              </div>
              
              <h2 className="text-2xl font-bold text-[#1A2E40] mb-2">Seva Setu Bot</h2>
              <p className="text-lg text-[#E06F2C] font-semibold mb-1">🙏 Namaste</p>
              <p className="text-sm text-gray-600 italic mb-4">Representing Modern India</p>
              
              <div className="flex items-center justify-center gap-2 mb-4 bg-gradient-to-r from-orange-50 to-green-50 py-2 px-4 rounded-full">
                <span className={`w-3 h-3 rounded-full ${isSpeaking ? 'bg-[#2E8B57] animate-pulse' : 'bg-gray-400'}`}></span>
                <span className={`text-sm font-medium ${isSpeaking ? 'text-[#2E8B57]' : 'text-gray-600'}`}>
                  {isSpeaking ? "🎙️ Speaking..." : "Ready to Assist"}
                </span>
              </div>
              
              {/* Voice Toggle with better styling */}
              <div className="mb-4 pt-4 border-t border-gray-200">
                <label className="flex items-center justify-center gap-3 cursor-pointer group">
                  <div className="relative">
                    <input
                      type="checkbox"
                      checked={enableVoice}
                      onChange={(e) => setEnableVoice(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-orange-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#2E8B57]"></div>
                  </div>
                  <span className="text-sm font-semibold text-[#1A2E40] group-hover:text-[#E06F2C] transition-colors">
                    {enableVoice ? "🔊 Voice Enabled" : "🔇 Voice Disabled"}
                  </span>
                </label>
                <p className="text-xs text-gray-500 mt-2">Toggle to hear responses</p>
              </div>

              <div className="pt-4 border-t border-gray-200">
                <p className="text-xs text-gray-500 mb-1">Consulate General of India</p>
                <p className="text-xs text-gray-500 mb-3">Johannesburg, South Africa</p>
                <div className="flex flex-wrap justify-center gap-2">
                  <span className="text-xs px-2 py-1 bg-orange-100 text-[#E06F2C] rounded-full">Hindi</span>
                  <span className="text-xs px-2 py-1 bg-orange-100 text-[#E06F2C] rounded-full">English</span>
                  <span className="text-xs px-2 py-1 bg-orange-100 text-[#E06F2C] rounded-full">Zulu</span>
                  <span className="text-xs px-2 py-1 bg-orange-100 text-[#E06F2C] rounded-full">Afrikaans</span>
                </div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-8">
            <div className="glass-card rounded-xl shadow-lg flex flex-col" style={{ height: "600px" }}>
              <div className="flex-1 overflow-y-auto p-6 space-y-4" data-testid="chat-messages">
                {messages.map((msg, index) => (
                  <div
                    key={index}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
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
                        <ReactMarkdown 
                          remarkPlugins={[remarkGfm]}
                          className="prose prose-sm max-w-none
                            prose-headings:text-[#1A2E40] prose-headings:font-bold
                            prose-p:text-[#1A2E40] prose-p:my-2
                            prose-ul:my-2 prose-ol:my-2
                            prose-li:text-[#1A2E40]
                            prose-strong:text-[#E06F2C] prose-strong:font-semibold
                            prose-a:text-[#E06F2C] prose-a:no-underline hover:prose-a:underline"
                        >
                          {msg.content}
                        </ReactMarkdown>
                      ) : (
                        msg.content
                      )}
                    </div>
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
    </div>
  );
}