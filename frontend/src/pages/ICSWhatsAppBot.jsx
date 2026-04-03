import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  Send, RefreshCw, MessageCircle, Phone, Circle, Check, CheckCheck,
  Clock, Wifi, WifiOff, Plus, X, Bot, User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// ── Delivery status icon ─────────────────────────────────────────────────────
function DeliveryIcon({ status }) {
  if (!status) return <Clock size={12} className="text-gray-400" />;
  if (status === "read") return <CheckCheck size={12} className="text-blue-400" />;
  if (status === "delivered") return <CheckCheck size={12} className="text-gray-400" />;
  if (status === "sent") return <Check size={12} className="text-gray-400" />;
  if (status?.toLowerCase() === "failed") return <Circle size={12} className="text-red-400 fill-red-400" />;
  return <Check size={12} className="text-gray-400" />;
}

// ── Format helpers ────────────────────────────────────────────────────────────
function fmtTime(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return "Today";
  const yest = new Date();
  yest.setDate(yest.getDate() - 1);
  if (d.toDateString() === yest.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
}

// ── Group messages by date ────────────────────────────────────────────────────
function groupByDate(messages) {
  const groups = [];
  let currentDate = null;
  for (const msg of messages) {
    const label = fmtDate(msg.timestamp);
    if (label !== currentDate) {
      groups.push({ type: "divider", label });
      currentDate = label;
    }
    groups.push({ type: "message", msg });
  }
  return groups;
}

// ── Date divider ─────────────────────────────────────────────────────────────
function DateDivider({ label }) {
  return (
    <div className="flex items-center justify-center my-3">
      <span className="bg-[#e1f3fb] text-[#54656f] text-xs px-3 py-0.5 rounded-full shadow-sm">
        {label}
      </span>
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────
function MessageBubble({ msg, simulateMode }) {
  const isOutbound = msg.direction === "outbound";
  // In simulate mode: outbound = bot reply, inbound = simulated user message
  // Show user-side bubble on left, bot-side on right when simulating
  const alignRight = simulateMode ? !isOutbound : isOutbound;

  return (
    <div className={`flex ${alignRight ? "justify-end" : "justify-start"} mb-1.5`}>
      <div
        className={`relative max-w-[75%] px-3 py-2 rounded-lg shadow-sm text-sm leading-relaxed whitespace-pre-wrap break-words ${
          isOutbound
            ? "bg-[#dcf8c6] text-gray-800 rounded-br-none"
            : "bg-white text-gray-800 rounded-bl-none"
        }`}
      >
        {/* Label in simulate mode */}
        {simulateMode && (
          <span className={`text-[10px] font-semibold block mb-0.5 ${isOutbound ? "text-[#00a884]" : "text-[#667781]"}`}>
            {isOutbound ? "🤖 Bot" : "👤 User"}
          </span>
        )}
        {msg.message}
        <span className="flex items-center gap-1 justify-end mt-0.5">
          <span className="text-[10px] text-gray-400">{fmtTime(msg.timestamp)}</span>
          {isOutbound && <DeliveryIcon status={msg.delivery_status} />}
        </span>
      </div>
    </div>
  );
}

// ── Conversation list item ────────────────────────────────────────────────────
function ConvItem({ conv, selected, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[#f0f2f5] transition-colors ${
        selected ? "bg-[#f0f2f5]" : "bg-white"
      } border-b border-gray-100`}
    >
      <div className="w-10 h-10 rounded-full bg-[#00a884] flex items-center justify-center flex-shrink-0 text-white font-semibold text-sm">
        {(conv.phone_number || "?").slice(-2)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-center">
          <span className="font-medium text-[#111b21] text-sm truncate">{conv.phone_number}</span>
          <span className="text-[11px] text-[#667781] flex-shrink-0 ml-2">{fmtTime(conv.last_timestamp)}</span>
        </div>
        <p className="text-xs text-[#667781] truncate mt-0.5">{conv.last_message || "No messages"}</p>
      </div>
      {conv.message_count > 0 && (
        <span className="bg-[#00a884] text-white text-[10px] rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1 flex-shrink-0">
          {conv.message_count}
        </span>
      )}
    </button>
  );
}

// ── New conversation modal ────────────────────────────────────────────────────
function NewConvModal({ onClose, onStart }) {
  const [phone, setPhone] = useState("");
  const [firstMsg, setFirstMsg] = useState("hi");
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const p = phone.trim().replace(/\s+/g, "");
    if (!p) return toast.error("Enter a phone number");
    setLoading(true);
    try {
      await onStart(p, firstMsg || "hi");
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <form
        onSubmit={handleSubmit}
        className="bg-white rounded-2xl shadow-xl w-80 p-5 flex flex-col gap-4"
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-[#111b21] text-base">New Conversation</h3>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={18} />
          </button>
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-[#667781] font-medium">Phone number (with country code)</label>
          <input
            ref={inputRef}
            type="tel"
            value={phone}
            onChange={e => setPhone(e.target.value)}
            placeholder="e.g. 918430774785"
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-[#128C7E] transition"
          />
          <p className="text-[11px] text-gray-400">No leading + required. Example: 918430774785</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-[#667781] font-medium">Opening message (simulated from user)</label>
          <input
            type="text"
            value={firstMsg}
            onChange={e => setFirstMsg(e.target.value)}
            placeholder="hi"
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-[#128C7E] transition"
          />
        </div>
        <Button
          type="submit"
          disabled={loading || !phone.trim()}
          className="bg-[#128C7E] hover:bg-[#0e7268] text-white rounded-lg"
        >
          {loading ? "Starting…" : "Start Bot Conversation"}
        </Button>
      </form>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════
export default function ICSWhatsAppBot() {
  const [conversations, setConversations] = useState([]);
  const [selectedPhone, setSelectedPhone] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loadingConvs, setLoadingConvs] = useState(false);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const [sending, setSending] = useState(false);
  const [botStatus, setBotStatus] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  // simulateMode = true  → messages typed by admin are treated as user→bot (bot processes & replies)
  // simulateMode = false → messages are sent as raw outbound text
  const [simulateMode, setSimulateMode] = useState(true);
  const [showNewConv, setShowNewConv] = useState(false);

  const messagesEndRef = useRef(null);
  const chatScrollRef = useRef(null);
  const inputRef = useRef(null);
  const pollRef = useRef(null);
  const textareaRef = useRef(null);

  // ── Scroll to bottom ────────────────────────────────────────────────────────
  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (chatScrollRef.current) {
        chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
      }
    });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, scrollToBottom]);

  // ── Fetch bot status ────────────────────────────────────────────────────────
  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/ics-whatsapp/status`);
      setBotStatus(res.data);
    } catch { setBotStatus(null); }
  }, []);

  // ── Fetch conversations ─────────────────────────────────────────────────────
  const fetchConversations = useCallback(async () => {
    setLoadingConvs(true);
    try {
      const res = await axios.get(`${API}/ics-whatsapp/conversations?limit=100`);
      setConversations(res.data.conversations || []);
    } catch { toast.error("Failed to load conversations"); }
    finally { setLoadingConvs(false); }
  }, []);

  // ── Fetch messages ──────────────────────────────────────────────────────────
  const fetchMessages = useCallback(async (phone) => {
    if (!phone) return;
    setLoadingMsgs(true);
    try {
      const res = await axios.get(`${API}/ics-whatsapp/messages/${encodeURIComponent(phone)}?limit=200`);
      setMessages(res.data.messages || []);
    } catch { toast.error("Failed to load messages"); }
    finally { setLoadingMsgs(false); }
  }, []);

  // ── Initial load ────────────────────────────────────────────────────────────
  useEffect(() => {
    fetchStatus();
    fetchConversations();
  }, [fetchStatus, fetchConversations]);

  // ── Poll every 5s when a conversation is open ───────────────────────────────
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (selectedPhone) {
      pollRef.current = setInterval(() => {
        fetchMessages(selectedPhone);
        fetchConversations();
      }, 5000);
    }
    return () => clearInterval(pollRef.current);
  }, [selectedPhone, fetchMessages, fetchConversations]);

  // ── Select conversation ─────────────────────────────────────────────────────
  const selectConv = useCallback((phone) => {
    setSelectedPhone(phone);
    setMessages([]);
    fetchMessages(phone);
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [fetchMessages]);

  // ── Start new conversation via simulate ─────────────────────────────────────
  const startNewConv = async (phone, message) => {
    try {
      await axios.post(`${API}/ics-whatsapp/simulate`, {
        phone,
        message,
        reply_type: "TEXT",
      });
      toast.success(`Bot conversation started with ${phone}`);
      // Refresh convs then open the conversation
      await fetchConversations();
      setSelectedPhone(phone);
      // Give bot a moment to respond then fetch
      setTimeout(() => fetchMessages(phone), 2000);
    } catch {
      toast.error("Failed to start conversation");
      throw new Error("failed");
    }
  };

  // ── Send message ────────────────────────────────────────────────────────────
  const handleSend = async () => {
    const text = input.trim();
    if (!text || !selectedPhone || sending) return;
    setSending(true);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    try {
      if (simulateMode) {
        // Feed message through bot logic — bot processes it and sends reply via ICS
        await axios.post(`${API}/ics-whatsapp/simulate`, {
          phone: selectedPhone,
          message: text,
          reply_type: "TEXT",
        });
        // Optimistic user bubble (inbound direction = from user)
        setMessages(prev => [
          ...prev,
          {
            id: "tmp_in_" + Date.now(),
            phone_number: selectedPhone,
            direction: "inbound",
            message: text,
            timestamp: new Date().toISOString(),
          },
        ]);
        // Poll sooner to pick up bot reply
        setTimeout(() => fetchMessages(selectedPhone), 2500);
      } else {
        // Raw outbound send — bypasses bot
        await axios.post(`${API}/ics-whatsapp/send`, {
          to: selectedPhone,
          message: text,
          type: "text",
        });
        setMessages(prev => [
          ...prev,
          {
            id: "tmp_out_" + Date.now(),
            phone_number: selectedPhone,
            direction: "outbound",
            message: text,
            timestamp: new Date().toISOString(),
            delivery_status: null,
          },
        ]);
      }
    } catch {
      toast.error("Failed to send message");
      setInput(text);
    } finally {
      setSending(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Filtered conversations ─────────────────────────────────────────────────
  const filteredConvs = conversations.filter(c =>
    c.phone_number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    c.last_message?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const grouped = groupByDate(messages);

  return (
    <div className="flex flex-col h-screen bg-[#f0f2f5] font-sans">
      {showNewConv && (
        <NewConvModal
          onClose={() => setShowNewConv(false)}
          onStart={startNewConv}
        />
      )}

      {/* ── Top bar ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between bg-[#128C7E] px-4 py-3 shadow-sm flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-white/20 flex items-center justify-center">
            <MessageCircle size={20} className="text-white" />
          </div>
          <div>
            <h1 className="text-white font-semibold text-sm leading-none">Seva Setu — WhatsApp Bot</h1>
            <p className="text-green-100 text-xs mt-0.5">Consulate General of India, Johannesburg</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {botStatus && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
              botStatus.ics_configured ? "bg-green-400/20 text-green-100" : "bg-red-400/20 text-red-100"
            }`}>
              {botStatus.ics_configured ? <Wifi size={12} /> : <WifiOff size={12} />}
              {botStatus.ics_configured ? "ICS Connected" : "ICS Offline"}
            </div>
          )}
          <Button
            variant="ghost" size="icon"
            className="text-white hover:bg-white/10 h-8 w-8"
            onClick={() => { fetchConversations(); if (selectedPhone) fetchMessages(selectedPhone); }}
            title="Refresh"
          >
            <RefreshCw size={15} className={loadingConvs ? "animate-spin" : ""} />
          </Button>
        </div>
      </div>

      {/* ── Main area ────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">

        {/* ── Left panel: conversations ──────────────────────────────────────── */}
        <div className="w-80 flex-shrink-0 flex flex-col bg-white border-r border-gray-200">
          {/* Search + new conv */}
          <div className="px-3 py-2 bg-[#f0f2f5] flex gap-2">
            <input
              type="text"
              placeholder="Search conversations…"
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              className="flex-1 bg-white rounded-lg px-3 py-1.5 text-sm text-gray-700 placeholder-gray-400 outline-none border border-gray-200 focus:border-[#128C7E] transition"
            />
            <button
              onClick={() => setShowNewConv(true)}
              className="bg-[#128C7E] hover:bg-[#0e7268] text-white rounded-lg px-2 flex items-center justify-center transition"
              title="Start new conversation"
            >
              <Plus size={16} />
            </button>
          </div>

          {/* Conversation list */}
          <div className="flex-1 overflow-y-auto">
            {loadingConvs && conversations.length === 0 ? (
              <div className="flex items-center justify-center h-32 text-gray-400 text-sm">Loading…</div>
            ) : filteredConvs.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-48 text-gray-400 text-sm gap-2 p-4 text-center">
                <MessageCircle size={28} className="opacity-40" />
                <span>No conversations yet</span>
                <span className="text-xs text-gray-300">Click + to start a new bot conversation</span>
              </div>
            ) : (
              filteredConvs.map(conv => (
                <ConvItem
                  key={conv.phone_number}
                  conv={conv}
                  selected={selectedPhone === conv.phone_number}
                  onClick={() => selectConv(conv.phone_number)}
                />
              ))
            )}
          </div>
        </div>

        {/* ── Right panel: chat ──────────────────────────────────────────────── */}
        <div className="flex-1 flex flex-col min-w-0">
          {selectedPhone ? (
            <>
              {/* Chat header */}
              <div className="flex items-center gap-3 bg-[#f0f2f5] px-4 py-2 border-b border-gray-200 flex-shrink-0">
                <div className="w-9 h-9 rounded-full bg-[#00a884] flex items-center justify-center text-white font-semibold text-sm flex-shrink-0">
                  {selectedPhone.slice(-2)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-[#111b21] text-sm truncate">{selectedPhone}</p>
                  <p className="text-xs text-[#667781]">{messages.length} message{messages.length !== 1 ? "s" : ""}</p>
                </div>

                {/* Mode toggle */}
                <div className="flex items-center gap-1 bg-white border border-gray-200 rounded-lg p-0.5">
                  <button
                    onClick={() => setSimulateMode(true)}
                    className={`flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition ${
                      simulateMode
                        ? "bg-[#128C7E] text-white"
                        : "text-[#667781] hover:bg-gray-100"
                    }`}
                    title="Simulate user message — bot processes & replies"
                  >
                    <Bot size={12} /> Bot Flow
                  </button>
                  <button
                    onClick={() => setSimulateMode(false)}
                    className={`flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium transition ${
                      !simulateMode
                        ? "bg-[#128C7E] text-white"
                        : "text-[#667781] hover:bg-gray-100"
                    }`}
                    title="Send raw outbound message directly"
                  >
                    <User size={12} /> Raw Send
                  </button>
                </div>

                <a href={`tel:${selectedPhone}`} className="text-[#54656f] hover:text-[#128C7E] transition ml-1" title="Call">
                  <Phone size={18} />
                </a>
              </div>

              {/* Mode hint bar */}
              <div className={`text-[11px] px-4 py-1.5 font-medium flex items-center gap-1.5 flex-shrink-0 ${
                simulateMode
                  ? "bg-green-50 text-green-700 border-b border-green-100"
                  : "bg-amber-50 text-amber-700 border-b border-amber-100"
              }`}>
                {simulateMode ? (
                  <><Bot size={11} /> Bot Flow mode — your message is processed by the bot and it replies to the user via WhatsApp</>
                ) : (
                  <><User size={11} /> Raw Send mode — message is sent directly outbound, bypassing bot logic</>
                )}
              </div>

              {/* Messages */}
              <div
                ref={chatScrollRef}
                className="flex-1 overflow-y-auto px-4 py-3"
                style={{ backgroundColor: "#e5ddd5" }}
              >
                {loadingMsgs && messages.length === 0 ? (
                  <div className="flex items-center justify-center h-24 text-gray-500 text-sm">Loading messages…</div>
                ) : messages.length === 0 ? (
                  <div className="flex items-center justify-center h-24 text-gray-500 text-sm">No messages yet</div>
                ) : (
                  grouped.map((item, i) =>
                    item.type === "divider" ? (
                      <DateDivider key={`div-${i}`} label={item.label} />
                    ) : (
                      <MessageBubble key={item.msg.id || i} msg={item.msg} simulateMode={simulateMode} />
                    )
                  )
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              <div className="flex items-end gap-2 bg-[#f0f2f5] px-3 py-2 border-t border-gray-200 flex-shrink-0">
                <textarea
                  ref={(el) => { inputRef.current = el; textareaRef.current = el; }}
                  rows={1}
                  value={input}
                  onChange={e => {
                    setInput(e.target.value);
                    e.target.style.height = "auto";
                    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
                  }}
                  onKeyDown={handleKeyDown}
                  placeholder={simulateMode ? "Type as the user (bot will respond)…" : "Type an outbound message…"}
                  className="flex-1 bg-white rounded-lg px-3 py-2 text-sm text-gray-800 placeholder-gray-400 outline-none resize-none border border-gray-200 focus:border-[#128C7E] transition max-h-28 overflow-y-auto"
                  style={{ minHeight: "38px" }}
                  disabled={sending}
                />
                <Button
                  onClick={handleSend}
                  disabled={!input.trim() || sending}
                  className="h-9 w-9 p-0 rounded-full bg-[#128C7E] hover:bg-[#0e7268] text-white flex-shrink-0"
                  title={simulateMode ? "Simulate user message" : "Send raw message"}
                >
                  <Send size={16} />
                </Button>
              </div>
            </>
          ) : (
            /* No conversation selected */
            <div className="flex-1 flex flex-col items-center justify-center bg-[#f0f2f5] gap-4 p-6">
              <div className="w-20 h-20 rounded-full bg-[#128C7E]/10 flex items-center justify-center">
                <MessageCircle size={36} className="text-[#128C7E]" />
              </div>
              <div className="text-center">
                <h2 className="text-xl font-light text-[#41525d] mb-1">Seva Setu WhatsApp Bot</h2>
                <p className="text-sm text-[#667781] mb-3">Select a conversation or start a new one</p>
                <Button
                  onClick={() => setShowNewConv(true)}
                  className="bg-[#128C7E] hover:bg-[#0e7268] text-white rounded-full px-5 gap-2"
                >
                  <Plus size={15} /> New Conversation
                </Button>
              </div>
              {botStatus && (
                <div className="bg-white rounded-xl px-5 py-3 shadow-sm text-sm text-[#54656f] space-y-1 max-w-xs w-full mt-2">
                  <div className="flex justify-between">
                    <span className="text-gray-400">ICS number</span>
                    <span className="font-medium">{botStatus.ics_from || "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">ICS status</span>
                    <span className={`font-medium ${botStatus.ics_configured ? "text-green-600" : "text-red-500"}`}>
                      {botStatus.ics_configured ? "Connected" : "Not configured"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">LLM</span>
                    <span className={`font-medium ${botStatus.llm_available ? "text-green-600" : "text-gray-400"}`}>
                      {botStatus.llm_available ? "Available" : "Disabled"}
                    </span>
                  </div>
                  <div className="flex justify-between items-start gap-2">
                    <span className="text-gray-400 flex-shrink-0">Webhook</span>
                    <span className="font-medium text-xs text-right break-all">{botStatus.webhook_incoming}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
