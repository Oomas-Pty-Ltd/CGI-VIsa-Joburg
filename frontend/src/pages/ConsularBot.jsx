import React, { useState, useEffect } from "react";
import { Mic, Camera, Send, FileText, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import axios from "axios";
import SpeechRecognition, { useSpeechRecognition } from "react-speech-recognition";
import Webcam from "react-webcam";
import { Dialog, DialogContent } from "@/components/ui/dialog";

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
  const webcamRef = React.useRef(null);
  
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
        content: "🙏 Namaste! Welcome to the Consulate General of India, Johannesburg. I'm Sarthak, your dedicated consular assistant. How may I help you with your consular services today? I can assist you with passport applications, visa services, OCI cards, and document attestation."
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
    setInput("");
    resetTranscript();

    try {
      const token = localStorage.getItem("token");
      const response = await axios.post(
        `${API}/consular/chat`,
        {
          message: input,
          session_id: sessionId,
          user_id: "guest"
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (!sessionId) {
        setSessionId(response.data.session_id);
      }

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response.data.response }
      ]);
      setCurrentStep(response.data.step);
    } catch (error) {
      toast.error("Failed to send message");
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
              <img
                src="https://images.unsplash.com/photo-1705999942286-056551a9144d?q=85"
                alt="Sarthak AI Consular Assistant"
                className="w-32 h-32 rounded-full mx-auto mb-4 object-cover border-4 border-[#E06F2C] avatar-pulse"
              />
              <h2 className="text-2xl font-bold text-[#1A2E40] mb-2">Sarthak AI</h2>
              <div className="flex items-center justify-center gap-2">
                <span className="w-3 h-3 bg-[#2E8B57] rounded-full animate-pulse"></span>
                <span className="text-sm text-gray-600">Online</span>
              </div>
              <p className="text-sm text-gray-600 mt-4">Consulate General of India</p>
              <p className="text-xs text-gray-500 mt-1">Johannesburg, South Africa</p>
              <div className="mt-4 pt-4 border-t border-gray-200">
                <p className="text-xs text-gray-500">Multilingual Support</p>
                <p className="text-xs font-medium text-[#E06F2C]">Hindi | English | Zulu | Afrikaans</p>
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
                      {msg.content}
                    </div>
                  </div>
                ))}
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
                  <div className="flex flex-col gap-2">
                    {browserSupportsSpeechRecognition && (
                      <Button
                        onClick={handleVoice}
                        className={`${
                          isRecording ? "bg-red-500 hover:bg-red-600 mic-active" : "bg-[#2E8B57] hover:bg-[#256B47]"
                        } text-white`}
                        data-testid="voice-btn"
                      >
                        <Mic className="w-5 h-5" />
                      </Button>
                    )}
                    <Button
                      onClick={() => setShowCamera(true)}
                      className="bg-[#1A2E40] hover:bg-[#132230] text-white"
                      data-testid="camera-btn"
                    >
                      <Camera className="w-5 h-5" />
                    </Button>
                    <Button
                      onClick={handleSend}
                      className="bg-[#E06F2C] hover:bg-[#C55D20] text-white"
                      data-testid="send-btn"
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