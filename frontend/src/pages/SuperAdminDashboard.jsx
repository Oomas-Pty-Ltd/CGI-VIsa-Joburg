import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Building2, Plus, TrendingUp, LogOut,
  MessageSquare, Shield, Download, ChevronLeft, ChevronRight,
  X, RefreshCw, Copy, Check, BookOpen, Upload, Trash2, FileText,
  Calendar, Clock, AlertCircle, Files, Search, Ban, Unlock,
  Workflow, Smartphone, Bot, Globe, UserPlus, KeyRound,
} from "lucide-react";
import ChannelMappingsTab from "./super-admin/ChannelMappingsTab";
import TenantServicesTab from "./super-admin/TenantServicesTab";
import BotConfigTab from "./super-admin/BotConfigTab";
import ScrapersTab from "./super-admin/ScrapersTab";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function CopyId({ id }) {
  const [copied, setCopied] = useState(false);
  const copy = (e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button
      onClick={copy}
      className="flex items-center gap-1.5 px-2 py-1 rounded bg-gray-100 hover:bg-gray-200 transition-colors group"
      title="Copy company ID"
    >
      <span className="font-mono text-xs text-gray-600 select-all">{id}</span>
      {copied
        ? <Check className="w-3.5 h-3.5 text-green-600 shrink-0" />
        : <Copy className="w-3.5 h-3.5 text-gray-400 group-hover:text-gray-600 shrink-0" />}
    </button>
  );
}

const TABS = [
  { key: "dashboard", label: "Dashboard", icon: TrendingUp },
  { key: "conversations", label: "Conversations", icon: MessageSquare },
  { key: "audit-logs", label: "Audit Logs", icon: Shield },
  { key: "seva-applications", label: "Seva Applications", icon: Files },
  { key: "knowledge", label: "Knowledge Base", icon: BookOpen },
  { key: "tenant-services", label: "Services", icon: Workflow },
  { key: "channel-mappings", label: "Channels", icon: Smartphone },
  { key: "bot-config", label: "Bot Config", icon: Bot },
  { key: "scrapers", label: "Scrapers", icon: Globe },
];

const CHANNEL_COLORS = {
  web: "bg-blue-100 text-blue-700",
  whatsapp: "bg-green-100 text-green-700",
  facebook: "bg-indigo-100 text-indigo-700",
  widget: "bg-purple-100 text-purple-700",
};

const SEVERITY_COLORS = {
  info: "bg-blue-100 text-blue-700",
  warning: "bg-yellow-100 text-yellow-800",
  error: "bg-red-100 text-red-700",
  critical: "bg-red-200 text-red-900 font-bold",
};

const CATEGORY_COLORS = {
  auth: "bg-gray-100 text-gray-700",
  data_access: "bg-cyan-100 text-cyan-700",
  data_modification: "bg-orange-100 text-orange-700",
  data_deletion: "bg-red-100 text-red-700",
  data_export: "bg-purple-100 text-purple-700",
  admin_action: "bg-yellow-100 text-yellow-700",
  security_event: "bg-red-200 text-red-800",
  system_event: "bg-gray-100 text-gray-600",
  consent: "bg-teal-100 text-teal-700",
  api_access: "bg-blue-100 text-blue-600",
};

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-ZA", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function shortId(id = "") {
  return id.length > 16 ? `${id.slice(0, 8)}…${id.slice(-6)}` : id;
}

// ─── Pagination bar ───────────────────────────────────────────────────────────
function Pagination({ page, total, limit, onChange }) {
  const pages = Math.ceil(total / limit) || 1;
  return (
    <div className="flex items-center gap-3 justify-end mt-4 text-sm text-gray-600">
      <span>{total} records</span>
      <Button variant="outline" size="icon" className="h-7 w-7" onClick={() => onChange(page - 1)} disabled={page <= 1}>
        <ChevronLeft className="w-4 h-4" />
      </Button>
      <span className="font-medium">Page {page} / {pages}</span>
      <Button variant="outline" size="icon" className="h-7 w-7" onClick={() => onChange(page + 1)} disabled={page >= pages}>
        <ChevronRight className="w-4 h-4" />
      </Button>
    </div>
  );
}

// ─── Session detail modal ─────────────────────────────────────────────────────
function SessionDetailModal({ sessionId, onClose, token }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sessionId) return;
    axios
      .get(`${API}/super-admin/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((r) => setSession(r.data))
      .catch(() => toast.error("Failed to load session"))
      .finally(() => setLoading(false));
  }, [sessionId]);

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between p-5 border-b">
          <div>
            <h3 className="font-bold text-[#1A2E40] text-lg">Conversation Detail</h3>
            {session && (
              <p className="text-xs text-gray-500 mt-0.5">
                {session.id} · {session.channel} · {formatDate(session.created_at)}
              </p>
            )}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}><X className="w-5 h-5" /></Button>
        </div>

        <div className="overflow-y-auto flex-1 p-5 space-y-3">
          {loading && <p className="text-gray-500 text-center py-8">Loading…</p>}
          {!loading && !session && <p className="text-red-500 text-center py-8">Session not found.</p>}
          {session && (session.messages || []).length === 0 && (
            <p className="text-gray-400 text-center py-8">No messages in this session.</p>
          )}
          {session &&
            (session.messages || []).map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
                    msg.role === "user"
                      ? "bg-[#E06F2C] text-white rounded-br-sm"
                      : "bg-gray-100 text-gray-800 rounded-bl-sm"
                  }`}
                >
                  <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                  <p className={`text-xs mt-1 ${msg.role === "user" ? "text-orange-200" : "text-gray-400"}`}>
                    {msg.role === "user" ? "User" : "Bot"} · {formatDate(msg.timestamp)}
                  </p>
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

// ─── Conversations tab ────────────────────────────────────────────────────────
function ConversationsTab({ companies, token }) {
  const [sessions, setSessions] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ company_id: "", channel: "" });
  const [selectedSession, setSelectedSession] = useState(null);

  const limit = 50;

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit };
      if (filters.company_id) params.company_id = filters.company_id;
      if (filters.channel) params.channel = filters.channel;
      const { data } = await axios.get(`${API}/super-admin/sessions`, {
        headers: { Authorization: `Bearer ${token}` },
        params,
      });
      setSessions(data.sessions);
      setTotal(data.total);
    } catch {
      toast.error("Failed to load sessions");
    } finally {
      setLoading(false);
    }
  }, [page, filters, token]);

  useEffect(() => { fetchSessions(); }, [fetchSessions]);

  const downloadCsv = () => {
    const params = new URLSearchParams();
    if (filters.company_id) params.set("company_id", filters.company_id);
    if (filters.channel) params.set("channel", filters.channel);
    const token_ = localStorage.getItem("token");
    // Trigger download via hidden link
    const url = `${API}/super-admin/sessions/export/csv?${params}&_token=${token_}`;
    const a = document.createElement("a");
    a.href = url;
    a.click();
  };

  // Use fetch for CSV (need auth header)
  const handleCsvDownload = async () => {
    try {
      const params = new URLSearchParams();
      if (filters.company_id) params.set("company_id", filters.company_id);
      if (filters.channel) params.set("channel", filters.channel);
      const res = await fetch(`${API}/super-admin/sessions/export/csv?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sessions_${new Date().toISOString().slice(0,10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("CSV export failed");
    }
  };

  return (
    <div>
      {/* Filters row */}
      <div className="flex flex-wrap items-end gap-3 mb-5">
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">Company</Label>
          <Select value={filters.company_id} onValueChange={(v) => { setFilters(f => ({ ...f, company_id: v === "all" ? "" : v })); setPage(1); }}>
            <SelectTrigger className="w-44 h-9 text-sm">
              <SelectValue placeholder="All companies" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All companies</SelectItem>
              {companies.map((c) => (
                <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">Channel</Label>
          <Select value={filters.channel} onValueChange={(v) => { setFilters(f => ({ ...f, channel: v === "all" ? "" : v })); setPage(1); }}>
            <SelectTrigger className="w-36 h-9 text-sm">
              <SelectValue placeholder="All channels" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All channels</SelectItem>
              {["web", "whatsapp", "facebook", "widget"].map((ch) => (
                <SelectItem key={ch} value={ch}>{ch}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" onClick={fetchSessions} className="h-9">
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
        <Button onClick={handleCsvDownload} size="sm" className="h-9 bg-[#2E8B57] hover:bg-[#246b43] text-white ml-auto">
          <Download className="w-4 h-4 mr-1" /> Export CSV
        </Button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-4 py-3 text-left">Session ID</th>
              <th className="px-4 py-3 text-left">Channel</th>
              <th className="px-4 py-3 text-left">User</th>
              <th className="px-4 py-3 text-left">First Message</th>
              <th className="px-4 py-3 text-center">Msgs</th>
              <th className="px-4 py-3 text-left">Started</th>
              <th className="px-4 py-3 text-left">Last Active</th>
              <th className="px-4 py-3 text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={8} className="text-center py-10 text-gray-400">Loading…</td></tr>
            )}
            {!loading && sessions.length === 0 && (
              <tr><td colSpan={8} className="text-center py-10 text-gray-400">No sessions found.</td></tr>
            )}
            {!loading && sessions.map((s) => (
              <tr
                key={s.id}
                onClick={() => setSelectedSession(s.id)}
                className="border-t border-gray-100 hover:bg-orange-50 cursor-pointer transition-colors"
              >
                <td className="px-4 py-3 font-mono text-xs text-gray-500">{shortId(s.id)}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CHANNEL_COLORS[s.channel] || "bg-gray-100 text-gray-600"}`}>
                    {s.channel}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-700 max-w-[120px] truncate">{s.user_identifier}</td>
                <td className="px-4 py-3 text-gray-600 max-w-[240px] truncate">{s.first_message}</td>
                <td className="px-4 py-3 text-center font-semibold text-[#1A2E40]">{s.message_count}</td>
                <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{formatDate(s.created_at)}</td>
                <td className="px-4 py-3 text-gray-500 whitespace-nowrap">{formatDate(s.last_activity)}</td>
                <td className="px-4 py-3 text-center">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${s.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                    {s.is_active ? "Active" : "Closed"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Pagination page={page} total={total} limit={limit} onChange={setPage} />

      {selectedSession && (
        <SessionDetailModal
          sessionId={selectedSession}
          token={token}
          onClose={() => setSelectedSession(null)}
        />
      )}
    </div>
  );
}

// ─── Audit Logs tab ───────────────────────────────────────────────────────────
function AuditLogsTab({ companies, token }) {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ company_id: "", category: "", severity: "" });

  const limit = 50;

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, limit };
      if (filters.company_id) params.company_id = filters.company_id;
      if (filters.category) params.category = filters.category;
      if (filters.severity) params.severity = filters.severity;
      const { data } = await axios.get(`${API}/super-admin/audit-logs`, {
        headers: { Authorization: `Bearer ${token}` },
        params,
      });
      setLogs(data.logs);
      setTotal(data.total);
    } catch {
      toast.error("Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  }, [page, filters, token]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  const handleCsvDownload = async () => {
    try {
      const params = new URLSearchParams();
      if (filters.company_id) params.set("company_id", filters.company_id);
      if (filters.category) params.set("category", filters.category);
      const res = await fetch(`${API}/super-admin/audit-logs/export/csv?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_logs_${new Date().toISOString().slice(0,10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("CSV export failed");
    }
  };

  const CATEGORIES = [
    "auth","data_access","data_modification","data_deletion",
    "data_export","admin_action","security_event","system_event","consent","api_access"
  ];

  return (
    <div>
      {/* Filters row */}
      <div className="flex flex-wrap items-end gap-3 mb-5">
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">Company</Label>
          <Select value={filters.company_id} onValueChange={(v) => { setFilters(f => ({ ...f, company_id: v === "all" ? "" : v })); setPage(1); }}>
            <SelectTrigger className="w-44 h-9 text-sm"><SelectValue placeholder="All companies" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All companies</SelectItem>
              {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">Category</Label>
          <Select value={filters.category} onValueChange={(v) => { setFilters(f => ({ ...f, category: v === "all" ? "" : v })); setPage(1); }}>
            <SelectTrigger className="w-44 h-9 text-sm"><SelectValue placeholder="All categories" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c.replace(/_/g," ")}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">Severity</Label>
          <Select value={filters.severity} onValueChange={(v) => { setFilters(f => ({ ...f, severity: v === "all" ? "" : v })); setPage(1); }}>
            <SelectTrigger className="w-32 h-9 text-sm"><SelectValue placeholder="All" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              {["info","warning","error","critical"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <Button variant="outline" size="sm" onClick={fetchLogs} className="h-9">
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
        <Button onClick={handleCsvDownload} size="sm" className="h-9 bg-[#2E8B57] hover:bg-[#246b43] text-white ml-auto">
          <Download className="w-4 h-4 mr-1" /> Export CSV
        </Button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-4 py-3 text-left">Timestamp</th>
              <th className="px-4 py-3 text-left">Category</th>
              <th className="px-4 py-3 text-left">Action</th>
              <th className="px-4 py-3 text-left">User</th>
              <th className="px-4 py-3 text-left">Resource</th>
              <th className="px-4 py-3 text-center">Severity</th>
              <th className="px-4 py-3 text-center">Result</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="text-center py-10 text-gray-400">Loading…</td></tr>
            )}
            {!loading && logs.length === 0 && (
              <tr><td colSpan={7} className="text-center py-10 text-gray-400">No audit logs found.</td></tr>
            )}
            {!loading && logs.map((log, i) => (
              <tr key={log.id || i} className="border-t border-gray-100 hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 text-gray-500 whitespace-nowrap text-xs">{formatDate(log.timestamp)}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CATEGORY_COLORS[log.category] || "bg-gray-100 text-gray-600"}`}>
                    {(log.category || "—").replace(/_/g," ")}
                  </span>
                </td>
                <td className="px-4 py-3 font-medium text-[#1A2E40]">{log.action || "—"}</td>
                <td className="px-4 py-3 text-gray-600 text-xs">
                  <div>{log.user_id ? shortId(log.user_id) : "—"}</div>
                  {log.user_type && <div className="text-gray-400">{log.user_type}</div>}
                </td>
                <td className="px-4 py-3 text-gray-600 text-xs">
                  {log.resource_type
                    ? <><span className="font-medium">{log.resource_type}</span>{log.resource_id && <span className="text-gray-400"> · {shortId(log.resource_id)}</span>}</>
                    : "—"}
                </td>
                <td className="px-4 py-3 text-center">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${SEVERITY_COLORS[log.severity] || "bg-gray-100 text-gray-600"}`}>
                    {log.severity || "—"}
                  </span>
                </td>
                <td className="px-4 py-3 text-center">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${log.success ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                    {log.success ? "OK" : "FAIL"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Pagination page={page} total={total} limit={limit} onChange={setPage} />
    </div>
  );
}

// ─── Knowledge Base tab ───────────────────────────────────────────────────────

const EVENT_STATUS_STYLES = {
  past:    { bg: "bg-gray-100 text-gray-600",    icon: Clock,         label: "Past" },
  present: { bg: "bg-green-100 text-green-700",  icon: AlertCircle,   label: "Live" },
  future:  { bg: "bg-blue-100 text-blue-700",    icon: Calendar,      label: "Upcoming" },
  general: { bg: "bg-orange-100 text-orange-700", icon: FileText,     label: "General" },
};

function EventBadge({ status }) {
  const cfg = EVENT_STATUS_STYLES[status] || EVENT_STATUS_STYLES.general;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg}`}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}

function KnowledgeTab({ token, companies = [] }) {
  /* ── upload state ── */
  const [file, setFile]           = useState(null);
  const [docTitle, setDocTitle]   = useState("");
  const [category, setCategory]   = useState("general");
  const [uploadCompanyId, setUploadCompanyId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver]   = useState(false);
  const fileInputRef = useRef(null);

  /* ── entries list state ── */
  const [entries, setEntries]         = useState([]);
  const [total, setTotal]             = useState(0);
  const [page, setPage]               = useState(1);
  const [loadingList, setLoadingList] = useState(false);
  const [filterStatus, setFilterStatus] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterCompany, setFilterCompany]   = useState(""); // Sprint 14
  const [pdfFiles, setPdfFiles]       = useState([]);
  const [filterFile, setFilterFile]   = useState("");

  /* ── entry preview ── */
  const [preview, setPreview] = useState(null);

  const limit = 50;

  const CATEGORIES = [
    "general","visa","passport","oci","pcc","fees","emergency","services","event","announcement","other"
  ];

  const companyName = (id) => companies.find((c) => c.id === id)?.name ?? id;

  // Default the upload selector to the first tenant once companies loads
  useEffect(() => {
    if (!uploadCompanyId && companies.length > 0) setUploadCompanyId(companies[0].id);
  }, [companies, uploadCompanyId]);

  const fetchEntries = useCallback(async () => {
    setLoadingList(true);
    try {
      const params = new URLSearchParams({ page, limit });
      if (filterStatus)   params.set("event_status",  filterStatus);
      if (filterCategory) params.set("category",      filterCategory);
      if (filterFile)     params.set("pdf_filename",  filterFile);
      if (filterCompany)  params.set("company_id",    filterCompany);
      const [entriesRes, filesRes] = await Promise.all([
        fetch(`${API}/super-admin/knowledge/entries?${params}`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API}/super-admin/knowledge/pdf-files`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);
      const entData  = await entriesRes.json();
      const fileData = await filesRes.json();
      setEntries(entData.entries || []);
      setTotal(entData.total   || 0);
      setPdfFiles(fileData.files || []);
    } catch {
      toast.error("Failed to load knowledge entries");
    } finally {
      setLoadingList(false);
    }
  }, [page, filterStatus, filterCategory, filterFile, filterCompany, token]);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);

  /* ── upload handler ── */
  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) { toast.error("Please select a PDF file."); return; }
    if (!uploadCompanyId) { toast.error("Pick a tenant to upload the PDF under."); return; }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file",       file);
      form.append("title",      docTitle);
      form.append("category",   category);
      form.append("company_id", uploadCompanyId);

      let res;
      try {
        res = await fetch(`${API}/super-admin/knowledge/upload-pdf`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: form,
        });
      } catch {
        toast.error("Network error — could not reach the server. Check your connection.", { duration: 6000 });
        return;
      }

      let data;
      try {
        data = await res.json();
      } catch {
        toast.error(`Server error (${res.status}) — unexpected response format.`, { duration: 6000 });
        return;
      }

      if (!res.ok) {
        // FastAPI returns detail as a string for HTTPException, but an array for 422 validation errors
        let msg = "Upload failed";
        if (typeof data.detail === "string") {
          msg = data.detail;
        } else if (Array.isArray(data.detail)) {
          msg = data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
        } else if (data.message) {
          msg = data.message;
        }
        toast.error(msg, { duration: 8000 });
        return;
      }

      const ocrNote = data.ocr_used ? " via OCR" : "";
      const modeNote = data.faq_mode ? " as FAQ pairs" : "";
      toast.success(`PDF processed — ${data.sections_created} entries created${modeNote}${ocrNote}.`);
      setFile(null);
      setDocTitle("");
      setCategory("general");
      if (fileInputRef.current) fileInputRef.current.value = "";
      fetchEntries();
    } catch (err) {
      toast.error(err.message || "Upload failed — please try again.", { duration: 6000 });
    } finally {
      setUploading(false);
    }
  };

  /* ── delete handler ── */
  const handleDelete = async (entryId, entryTitle) => {
    if (!window.confirm(`Delete entry: "${entryTitle}"?`)) return;
    try {
      const res = await fetch(`${API}/super-admin/knowledge/entries/${entryId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error();
      toast.success("Entry deleted.");
      fetchEntries();
    } catch {
      toast.error("Failed to delete entry.");
    }
  };

  /* ── drag-and-drop ── */
  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.type === "application/pdf") {
      setFile(dropped);
      if (!docTitle) setDocTitle(dropped.name.replace(/\.pdf$/i, "").replace(/_/g, " "));
    } else {
      toast.error("Only PDF files are accepted.");
    }
  };

  return (
    <div className="space-y-8">

      {/* ── Upload card ── */}
      <div className="bg-white rounded-xl shadow-md p-6">
        <h2 className="text-xl font-bold text-[#1A2E40] mb-4 flex items-center gap-2">
          <Upload className="w-5 h-5 text-[#E06F2C]" />
          Upload PDF to Knowledge Base
        </h2>

        <form onSubmit={handleUpload} className="space-y-4">
          {/* Drop zone */}
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              dragOver
                ? "border-[#E06F2C] bg-orange-50"
                : file
                ? "border-green-400 bg-green-50"
                : "border-gray-300 hover:border-[#E06F2C] hover:bg-orange-50"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files[0];
                if (f) {
                  setFile(f);
                  if (!docTitle) setDocTitle(f.name.replace(/\.pdf$/i, "").replace(/_/g, " "));
                }
              }}
            />
            {file ? (
              <div className="flex items-center justify-center gap-2 text-green-700">
                <FileText className="w-6 h-6" />
                <span className="font-medium">{file.name}</span>
                <span className="text-sm text-gray-500">({(file.size / 1024).toFixed(0)} KB)</span>
              </div>
            ) : (
              <div className="text-gray-500">
                <Upload className="w-10 h-10 mx-auto mb-2 text-gray-400" />
                <p className="font-medium">Drag &amp; drop a PDF here, or click to browse</p>
                <p className="text-sm mt-1">Max 50 MB · PDF only</p>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label className="text-sm text-gray-600 mb-1 block">Document Title (optional)</Label>
              <Input
                value={docTitle}
                onChange={(e) => setDocTitle(e.target.value)}
                placeholder="e.g. Visa Policy Update April 2026"
              />
            </div>
            <div>
              <Label className="text-sm text-gray-600 mb-1 block">Category</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger>
                  <SelectValue placeholder="Select category" />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm text-gray-600 mb-1 block">Tenant</Label>
              <Select value={uploadCompanyId} onValueChange={setUploadCompanyId}>
                <SelectTrigger>
                  <SelectValue placeholder="Pick a tenant" />
                </SelectTrigger>
                <SelectContent>
                  {companies.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button
              type="submit"
              disabled={uploading || !file}
              className="bg-[#E06F2C] hover:bg-[#C55D20] text-white"
            >
              {uploading ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Processing PDF…
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4 mr-2" />
                  Upload &amp; Extract
                </>
              )}
            </Button>
            {file && (
              <Button
                type="button"
                variant="outline"
                onClick={() => { setFile(null); setDocTitle(""); if (fileInputRef.current) fileInputRef.current.value = ""; }}
              >
                Clear
              </Button>
            )}
          </div>

          {/* How date-awareness works */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
            <p className="font-semibold mb-1">Date-aware extraction</p>
            <p>
              Dates found in the PDF are automatically parsed. Each section is labelled:
              <span className="mx-1 px-1.5 py-0.5 rounded bg-gray-200 text-gray-700 text-xs font-medium">Past</span> — historical info shown as occurred,
              <span className="mx-1 px-1.5 py-0.5 rounded bg-green-200 text-green-800 text-xs font-medium">Live</span> — today,
              <span className="mx-1 px-1.5 py-0.5 rounded bg-blue-200 text-blue-800 text-xs font-medium">Upcoming</span> — future events,
              <span className="mx-1 px-1.5 py-0.5 rounded bg-orange-200 text-orange-800 text-xs font-medium">General</span> — no date detected.
              The bot uses this context to answer questions accurately.
            </p>
          </div>
        </form>
      </div>

      {/* ── Entries list ── */}
      <div className="bg-white rounded-xl shadow-md p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-[#1A2E40] flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-[#E06F2C]" />
            Uploaded Knowledge Entries
            {total > 0 && <span className="text-sm font-normal text-gray-500">({total} total)</span>}
          </h2>
          <Button variant="outline" size="sm" onClick={fetchEntries} className="h-8">
            <RefreshCw className="w-4 h-4 mr-1" /> Refresh
          </Button>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-5">
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Tenant</Label>
            <Select value={filterCompany || "all"} onValueChange={(v) => { setFilterCompany(v === "all" ? "" : v); setPage(1); }}>
              <SelectTrigger className="w-52 h-9 text-sm"><SelectValue placeholder="All tenants" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All tenants</SelectItem>
                {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Date Status</Label>
            <Select value={filterStatus} onValueChange={(v) => { setFilterStatus(v === "all" ? "" : v); setPage(1); }}>
              <SelectTrigger className="w-36 h-9 text-sm"><SelectValue placeholder="All statuses" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="past">Past</SelectItem>
                <SelectItem value="present">Live / Today</SelectItem>
                <SelectItem value="future">Upcoming</SelectItem>
                <SelectItem value="general">General</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-gray-500 mb-1 block">Category</Label>
            <Select value={filterCategory} onValueChange={(v) => { setFilterCategory(v === "all" ? "" : v); setPage(1); }}>
              <SelectTrigger className="w-36 h-9 text-sm"><SelectValue placeholder="All categories" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {pdfFiles.length > 0 && (
            <div>
              <Label className="text-xs text-gray-500 mb-1 block">PDF File</Label>
              <Select value={filterFile} onValueChange={(v) => { setFilterFile(v === "all" ? "" : v); setPage(1); }}>
                <SelectTrigger className="w-52 h-9 text-sm"><SelectValue placeholder="All files" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All files</SelectItem>
                  {pdfFiles.map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
              <tr>
                <th className="px-4 py-3 text-left">Title</th>
                <th className="px-4 py-3 text-left">Category</th>
                <th className="px-4 py-3 text-left">Date Status</th>
                <th className="px-4 py-3 text-left">Date Range</th>
                <th className="px-4 py-3 text-left">Source PDF</th>
                <th className="px-4 py-3 text-left">Added</th>
                <th className="px-4 py-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loadingList && (
                <tr><td colSpan={7} className="text-center py-10 text-gray-400">Loading…</td></tr>
              )}
              {!loadingList && entries.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center py-12 text-gray-400">
                    <BookOpen className="w-10 h-10 mx-auto mb-2 text-gray-300" />
                    No entries yet. Upload a PDF to get started.
                  </td>
                </tr>
              )}
              {!loadingList && entries.map((entry) => (
                <tr key={entry.id} className="border-t border-gray-100 hover:bg-orange-50 transition-colors">
                  <td className="px-4 py-3 max-w-[220px]">
                    <button
                      className="text-left font-medium text-[#1A2E40] hover:text-[#E06F2C] hover:underline truncate block max-w-full"
                      title={entry.title}
                      onClick={() => setPreview(entry)}
                    >
                      {entry.title}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                      {entry.category}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <EventBadge status={entry.event_status} />
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {entry.valid_from
                      ? entry.valid_from === entry.valid_until || !entry.valid_until
                        ? entry.valid_from
                        : `${entry.valid_from} → ${entry.valid_until}`
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 max-w-[140px] truncate" title={entry.pdf_filename}>
                    {entry.pdf_filename || "—"}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                    {formatDate(entry.created_at)}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-red-500 hover:bg-red-50 hover:text-red-700"
                      onClick={() => handleDelete(entry.id, entry.title)}
                      title="Delete entry"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <Pagination page={page} total={total} limit={limit} onChange={setPage} />
      </div>

      {/* ── Entry preview modal ── */}
      {preview && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setPreview(null)}>
          <div
            className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between p-5 border-b gap-4">
              <div className="flex-1 min-w-0">
                <h3 className="font-bold text-[#1A2E40] text-lg leading-tight">{preview.title}</h3>
                <div className="flex items-center gap-2 mt-2">
                  <EventBadge status={preview.event_status} />
                  <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                    {preview.category}
                  </span>
                  {preview.valid_from && (
                    <span className="text-xs text-gray-500">
                      {preview.valid_from}{preview.valid_until && preview.valid_until !== preview.valid_from ? ` → ${preview.valid_until}` : ""}
                    </span>
                  )}
                </div>
                {preview.keywords?.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {preview.keywords.map((kw) => (
                      <span key={kw} className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 text-xs">{kw}</span>
                    ))}
                  </div>
                )}
              </div>
              <Button variant="ghost" size="icon" onClick={() => setPreview(null)}><X className="w-5 h-5" /></Button>
            </div>
            <div className="overflow-y-auto flex-1 p-5">
              <p className="text-sm text-gray-400 mb-3">Source: {preview.pdf_filename}</p>
              <pre className="whitespace-pre-wrap text-sm text-gray-700 font-sans leading-relaxed">
                {preview.answer_preview}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ─── Keyword Blocker panel ────────────────────────────────────────────────────
function BlockedKeywordsPanel({ token }) {
  const [query, setQuery]               = useState("");
  const [searching, setSearching]       = useState(false);
  const [searchResults, setSearchResults] = useState(null);
  const [blocked, setBlocked]           = useState([]);
  const [loadingBlocked, setLoadingBlocked] = useState(true);
  const [blocking, setBlocking]         = useState(false);

  const fetchBlocked = useCallback(async () => {
    setLoadingBlocked(true);
    try {
      const { data } = await axios.get(`${API}/super-admin/knowledge/blocked-keywords`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setBlocked(data.keywords || []);
    } catch {
      toast.error("Failed to load blocked keywords");
    } finally {
      setLoadingBlocked(false);
    }
  }, [token]);

  useEffect(() => { fetchBlocked(); }, [fetchBlocked]);

  const handleSearch = async (e) => {
    e?.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      const { data } = await axios.get(`${API}/super-admin/knowledge/keyword-search`, {
        headers: { Authorization: `Bearer ${token}` },
        params: { q: query.trim() },
      });
      setSearchResults(data);
    } catch {
      toast.error("Search failed");
    } finally {
      setSearching(false);
    }
  };

  const handleBlock = async () => {
    const kw = query.trim().toLowerCase();
    if (!kw) return;
    setBlocking(true);
    try {
      const { data } = await axios.post(
        `${API}/super-admin/knowledge/blocked-keywords`,
        { keyword: kw },
        { headers: { Authorization: `Bearer ${token}` } },
      );
      toast.success(`"${kw}" blocked — ${data.matches_count} entries suppressed.`);
      setQuery("");
      setSearchResults(null);
      fetchBlocked();
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to block keyword";
      toast.error(msg);
    } finally {
      setBlocking(false);
    }
  };

  const handleUnblock = async (kw) => {
    try {
      await axios.delete(`${API}/super-admin/knowledge/blocked-keywords/${encodeURIComponent(kw)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success(`"${kw}" unblocked.`);
      fetchBlocked();
    } catch {
      toast.error("Failed to unblock keyword");
    }
  };

  const isAlreadyBlocked = blocked.some(b => b.keyword === query.trim().toLowerCase());

  return (
    <div className="bg-white rounded-xl shadow-md p-6 space-y-6">
      <h2 className="text-xl font-bold text-[#1A2E40] flex items-center gap-2">
        <Ban className="w-5 h-5 text-red-500" />
        Keyword Blocker
      </h2>
      <p className="text-sm text-gray-500">
        Search for a keyword across all knowledge base entries, then block it. When a user asks
        the bot about a blocked keyword, the bot will return no information.
      </p>

      {/* Search bar */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSearchResults(null); }}
            placeholder="Type a keyword to search (e.g. visa fee, oci, passport)"
            className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[#E06F2C]"
          />
        </div>
        <Button type="submit" disabled={searching || !query.trim()} variant="outline" className="h-[38px]">
          {searching ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          <span className="ml-1">Search</span>
        </Button>
        <Button
          type="button"
          disabled={blocking || !query.trim() || isAlreadyBlocked}
          onClick={handleBlock}
          className="h-[38px] bg-red-600 hover:bg-red-700 text-white"
        >
          <Ban className="w-4 h-4 mr-1" />
          {isAlreadyBlocked ? "Already Blocked" : "Block Keyword"}
        </Button>
      </form>

      {/* Search results */}
      {searchResults && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-semibold text-gray-700">
              {searchResults.total} knowledge entries match
              <span className="ml-1 px-1.5 py-0.5 bg-gray-100 rounded text-gray-600 font-mono text-xs">
                "{searchResults.query}"
              </span>
            </p>
            {searchResults.total > 0 && !isAlreadyBlocked && (
              <span className="text-xs text-red-500">
                Blocking this keyword will suppress all {searchResults.total} entries from the bot.
              </span>
            )}
          </div>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left">Title</th>
                  <th className="px-4 py-3 text-left">Category</th>
                  <th className="px-4 py-3 text-left">Source</th>
                  <th className="px-4 py-3 text-left">Keywords</th>
                </tr>
              </thead>
              <tbody>
                {searchResults.matches.length === 0 && (
                  <tr>
                    <td colSpan={4} className="text-center py-8 text-gray-400">
                      No knowledge entries found for this keyword.
                    </td>
                  </tr>
                )}
                {searchResults.matches.map((entry) => (
                  <tr key={entry.id} className="border-t border-gray-100 hover:bg-red-50 transition-colors">
                    <td className="px-4 py-3 text-[#1A2E40] font-medium max-w-[220px] truncate" title={entry.title}>
                      {entry.title}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                        {entry.category || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500 max-w-[140px] truncate" title={entry.pdf_filename || entry.source}>
                      {entry.pdf_filename || entry.source || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(entry.keywords || []).slice(0, 5).map((kw) => (
                          <span key={kw} className="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 text-xs">{kw}</span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Blocked keywords list */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
            <Ban className="w-4 h-4 text-red-400" />
            Blocked Keywords
            {blocked.length > 0 && (
              <span className="ml-1 px-1.5 py-0.5 bg-red-100 text-red-700 rounded-full text-xs font-medium">
                {blocked.length}
              </span>
            )}
          </h3>
          <Button variant="outline" size="sm" onClick={fetchBlocked} className="h-7">
            <RefreshCw className="w-3.5 h-3.5 mr-1" /> Refresh
          </Button>
        </div>

        {loadingBlocked && <p className="text-gray-400 text-sm py-4 text-center">Loading…</p>}

        {!loadingBlocked && blocked.length === 0 && (
          <div className="border border-dashed border-gray-200 rounded-lg p-8 text-center text-gray-400 text-sm">
            No keywords blocked yet. Search and block keywords above.
          </div>
        )}

        {!loadingBlocked && blocked.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left">Keyword</th>
                  <th className="px-4 py-3 text-center">Entries Suppressed</th>
                  <th className="px-4 py-3 text-left">Blocked At</th>
                  <th className="px-4 py-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody>
                {blocked.map((b) => (
                  <tr key={b.keyword} className="border-t border-gray-100 hover:bg-red-50 transition-colors">
                    <td className="px-4 py-3 font-mono font-semibold text-red-700">
                      <span className="flex items-center gap-1.5">
                        <Ban className="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                        {b.keyword}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
                        {b.matches_count ?? "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">
                      {formatDate(b.blocked_at)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-green-600 hover:bg-green-50 hover:text-green-800 gap-1"
                        onClick={() => handleUnblock(b.keyword)}
                        title="Unblock keyword"
                      >
                        <Unlock className="w-3.5 h-3.5" /> Unblock
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main dashboard ───────────────────────────────────────────────────────────
// ─── Seva Setu Applications tab ──────────────────────────────────────────────────
const SEVA_APP_STATUSES = ["created", "submitted", "confirmed"];

function SevaApplicationsTab({ token, companies = [] }) {
  const [applications, setApplications] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selectedApp, setSelectedApp] = useState(null);
  const [documentPreview, setDocumentPreview] = useState(null);
  const [services, setServices] = useState([]);
  const [filters, setFilters] = useState({
    company_id: "",
    status: "",
    service_type: "",
    search: "",
    from_date: "",
    to_date: "",
    with_documents: true,
  });

  const limit = 50;

  // Service dropdown only makes sense when scoped to one tenant — service_key
  // is per-tenant so the same key can map to different services across tenants.
  useEffect(() => {
    if (!filters.company_id) { setServices([]); return; }
    (async () => {
      try {
        const { data } = await axios.get(
          `${API}/super-admin/services/${filters.company_id}?include_disabled=true`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        setServices(data.services || []);
      } catch {
        setServices([]);
      }
    })();
  }, [filters.company_id, token]);

  // When the operator switches company, drop the now-meaningless service filter.
  useEffect(() => {
    setFilters((f) => f.service_type ? { ...f, service_type: "" } : f);
  }, [filters.company_id]);

  const buildParams = (extra = {}) => {
    const p = {
      page, limit,
      with_documents: filters.with_documents,
      ...extra,
    };
    if (filters.company_id)   p.company_id   = filters.company_id;
    if (filters.status)       p.status       = filters.status;
    if (filters.service_type) p.service_type = filters.service_type;
    if (filters.search)       p.search       = filters.search;
    if (filters.from_date)    p.from_date    = filters.from_date;
    if (filters.to_date)      p.to_date      = filters.to_date;
    return p;
  };

  const fetchApplications = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/super-admin/seva-setu/applications`, {
        headers: { Authorization: `Bearer ${token}` },
        params: buildParams(),
      });
      setApplications(data.applications);
      setTotal(data.total);
    } catch {
      toast.error("Failed to load applications");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, token, filters]);

  useEffect(() => { fetchApplications(); }, [fetchApplications]);

  const setFilter = (patch) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  const clearFilters = () => {
    setFilters({ company_id: "", status: "", service_type: "", search: "", from_date: "", to_date: "", with_documents: true });
    setPage(1);
  };

  const hasActiveFilters = ["company_id", "status", "service_type", "search", "from_date", "to_date"].some((k) => filters[k]);

  const handleCsvDownload = async () => {
    try {
      const qs = new URLSearchParams();
      Object.entries(buildParams()).forEach(([k, v]) => {
        if (v === "" || v === undefined || v === null) return;
        if (k === "page" || k === "limit") return; // CSV is full-export, not paginated
        qs.set(k, String(v));
      });
      const res = await fetch(`${API}/super-admin/seva-setu/applications-export/csv?${qs}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `applications_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("CSV export failed");
    }
  };

  const STATUS_COLORS = {
    draft: "bg-gray-100 text-gray-700",
    submitted: "bg-blue-100 text-blue-700",
    confirmed: "bg-green-100 text-green-700",
    completed: "bg-green-200 text-green-800",
    rejected: "bg-red-100 text-red-700",
  };

  return (
    <div>
      {/* Filters row */}
      <div className="flex flex-wrap items-end gap-3 mb-3">
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">Company</Label>
          <Select
            value={filters.company_id || "all"}
            onValueChange={(v) => setFilter({ company_id: v === "all" ? "" : v })}
          >
            <SelectTrigger className="w-44 h-9 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All companies</SelectItem>
              {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">Status</Label>
          <Select
            value={filters.status || "all"}
            onValueChange={(v) => setFilter({ status: v === "all" ? "" : v })}
          >
            <SelectTrigger className="w-36 h-9 text-sm"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {SEVA_APP_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">Service</Label>
          <Select
            value={filters.service_type || "all"}
            onValueChange={(v) => setFilter({ service_type: v === "all" ? "" : v })}
            disabled={!filters.company_id}
          >
            <SelectTrigger className="w-44 h-9 text-sm">
              <SelectValue placeholder={filters.company_id ? "All services" : "Pick a company first"} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All services</SelectItem>
              {services.map((s) => (
                <SelectItem key={s.service_key} value={s.service_key}>{s.name || s.service_key}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">Search reference</Label>
          <input
            type="text"
            className="border rounded h-9 px-2 text-sm w-44"
            placeholder="e.g. PASS-2024"
            value={filters.search}
            onChange={(e) => setFilter({ search: e.target.value })}
          />
        </div>
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">From</Label>
          <input
            type="date"
            className="border rounded h-9 px-2 text-sm"
            value={filters.from_date}
            onChange={(e) => setFilter({ from_date: e.target.value })}
          />
        </div>
        <div>
          <Label className="text-xs text-gray-500 mb-1 block">To</Label>
          <input
            type="date"
            className="border rounded h-9 px-2 text-sm"
            value={filters.to_date}
            onChange={(e) => setFilter({ to_date: e.target.value })}
          />
        </div>
        <Button variant="outline" size="sm" onClick={fetchApplications} className="h-9">
          <RefreshCw className="w-4 h-4 mr-1" /> Refresh
        </Button>
        <Button onClick={handleCsvDownload} size="sm" className="h-9 bg-[#2E8B57] hover:bg-[#246b43] text-white ml-auto">
          <Download className="w-4 h-4 mr-1" /> Export CSV
        </Button>
      </div>

      {/* Second row: with_documents toggle + count + clear */}
      <div className="flex items-center gap-4 mb-3 text-xs text-gray-600">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={filters.with_documents}
            onChange={(e) => setFilter({ with_documents: e.target.checked })}
          />
          With documents only
        </label>
        <span>{total} application{total === 1 ? "" : "s"}{hasActiveFilters && <span className="ml-1 text-gray-400">(filtered)</span>}</span>
        {hasActiveFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters} className="h-7 text-xs">
            Clear filters
          </Button>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600 text-xs uppercase tracking-wide">
            <tr>
              <th className="px-4 py-3 text-left">Reference ID</th>
              <th className="px-4 py-3 text-left">Service</th>
              <th className="px-4 py-3 text-left">User</th>
              <th className="px-4 py-3 text-center">Status</th>
              <th className="px-4 py-3 text-center">Docs</th>
              <th className="px-4 py-3 text-left">Created</th>
              <th className="px-4 py-3 text-center">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="text-center py-10 text-gray-400">Loading…</td></tr>
            )}
            {!loading && applications.length === 0 && (
              <tr><td colSpan={7} className="text-center py-10 text-gray-400">
                {hasActiveFilters ? "No applications match these filters." : "No applications found."}
              </td></tr>
            )}
            {!loading && applications.map((app, i) => (
              <tr key={app.id || i} className="border-t border-gray-100 hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 font-mono text-xs text-gray-700">{shortId(app.reference_id)}</td>
                <td className="px-4 py-3 text-gray-700">{app.service_name || app.service_type}</td>
                <td className="px-4 py-3 text-xs text-gray-600">{shortId(app.user_id)}</td>
                <td className="px-4 py-3 text-center">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[app.status] || "bg-gray-100 text-gray-600"}`}>
                    {app.status || "—"}
                  </span>
                </td>
                <td className="px-4 py-3 text-center">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${app.document_count > 0 ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"}`}>
                    {app.document_count}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">{formatDate(app.created_at)}</td>
                <td className="px-4 py-3 text-center">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-blue-600 hover:bg-blue-50"
                    onClick={() => setSelectedApp(app)}
                    title="View details"
                  >
                    <FileText className="w-4 h-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Pagination page={page} total={total} limit={limit} onChange={setPage} />

      {/* Application detail modal */}
      {selectedApp && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setSelectedApp(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b">
              <div>
                <h3 className="font-bold text-[#1A2E40] text-lg">Application Details</h3>
                <p className="text-xs text-gray-500 mt-0.5">{selectedApp.reference_id}</p>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setSelectedApp(null)}><X className="w-5 h-5" /></Button>
            </div>

            <div className="overflow-y-auto flex-1 p-5 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-gray-500 font-semibold">Service</p>
                  <p className="text-sm text-gray-800">{selectedApp.service_name}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-semibold">Status</p>
                  <p className={`text-sm px-2 py-0.5 rounded-full inline-block font-medium ${STATUS_COLORS[selectedApp.status] || "bg-gray-100 text-gray-600"}`}>
                    {selectedApp.status}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-semibold">User ID</p>
                  <p className="text-sm text-gray-800 font-mono">{selectedApp.user_id}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 font-semibold">Created</p>
                  <p className="text-sm text-gray-800">{formatDate(selectedApp.created_at)}</p>
                </div>
              </div>

              {selectedApp.form_data_fields > 0 && (
                <div>
                  <p className="text-xs text-gray-500 font-semibold mb-2">Form Fields ({selectedApp.form_data_fields})</p>
                  <div className="bg-gray-50 rounded p-3 text-xs text-gray-700 max-h-48 overflow-y-auto">
                    <pre>{JSON.stringify(selectedApp.form_data || {}, null, 2).slice(0, 500)}</pre>
                  </div>
                </div>
              )}

              {selectedApp.documents && selectedApp.documents.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 font-semibold mb-2">Uploaded Documents ({selectedApp.documents.length})</p>
                  <div className="space-y-2">
                    {selectedApp.documents.map((doc) => (
                      <div key={doc.id} className="bg-blue-50 border border-blue-200 rounded p-3">
                        <div className="flex items-center gap-2 justify-between">
                          <div className="flex items-center gap-2 flex-1 min-w-0">
                            <FileText className="w-4 h-4 text-blue-600 flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-gray-800 truncate">{doc.name}</p>
                              <p className="text-xs text-gray-500">{doc.content_type} · {formatDate(doc.uploaded_at)}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5 flex-shrink-0">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${doc.status === "uploaded" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"}`}>
                              {doc.status}
                            </span>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-blue-600 hover:bg-blue-100"
                              onClick={() => setDocumentPreview(doc)}
                              title="View document"
                            >
                              <FileText className="w-4 h-4" />
                            </Button>
                            {doc.file_url && (
                              <a
                                href={doc.file_url}
                                download={doc.name}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:text-blue-800 p-1.5"
                                title="Download document"
                              >
                                <Download className="w-4 h-4" />
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Document preview modal */}
      {documentPreview && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setDocumentPreview(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b">
              <div>
                <h3 className="font-bold text-[#1A2E40] text-lg">Document Preview</h3>
                <p className="text-xs text-gray-500 mt-0.5">{documentPreview.name}</p>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setDocumentPreview(null)}><X className="w-5 h-5" /></Button>
            </div>
            <div className="overflow-y-auto flex-1 p-5 flex items-center justify-center bg-gray-100">
              {documentPreview.content_type === "application/pdf" ? (
                <div className="text-center">
                  <FileText className="w-16 h-16 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-600 mb-4">PDF Document</p>
                  {documentPreview.file_url && (
                    <a
                      href={documentPreview.file_url}
                      download={documentPreview.name}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
                    >
                      <Download className="w-4 h-4" />
                      Download PDF
                    </a>
                  )}
                </div>
              ) : documentPreview.content_type?.startsWith("image/") ? (
                <img
                  src={documentPreview.file_url || documentPreview.data_url}
                  alt={documentPreview.name}
                  className="max-w-full max-h-full object-contain rounded"
                />
              ) : (
                <div className="text-center">
                  <FileText className="w-16 h-16 text-gray-400 mx-auto mb-3" />
                  <p className="text-gray-600 mb-2">{documentPreview.content_type}</p>
                  {documentPreview.file_url && (
                    <a
                      href={documentPreview.file_url}
                      download={documentPreview.name}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
                    >
                      <Download className="w-4 h-4" />
                      Download File
                    </a>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ─── Main SuperAdminDashboard component ───────────────────────────────────────
export default function SuperAdminDashboard() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("dashboard");
  const [companies, setCompanies] = useState([]);
  const [analytics, setAnalytics] = useState({});
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [adminsForCompany, setAdminsForCompany] = useState(null);  // Sprint 11
  const [newCompany, setNewCompany] = useState({
    name: "", email: "", admin_password: "", llm_model: "gpt-5.2",
  });

  const token = localStorage.getItem("token");

  useEffect(() => {
    if (!token) { navigate("/login"); return; }
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const cfg = { headers: { Authorization: `Bearer ${token}` } };
      const [companiesRes, analyticsRes] = await Promise.all([
        axios.get(`${API}/super-admin/companies`, cfg),
        axios.get(`${API}/super-admin/analytics/overview`, cfg),
      ]);
      setCompanies(companiesRes.data);
      setAnalytics(analyticsRes.data);
    } catch {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateCompany = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/super-admin/companies`, newCompany, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success("Company created successfully!");
      setShowCreateDialog(false);
      setNewCompany({ name: "", email: "", admin_password: "", llm_model: "gpt-5.2" });
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to create company");
    }
  };

  const handleLogout = () => { localStorage.clear(); navigate("/"); };

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen text-gray-500">Loading…</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Sidebar */}
      <div className="admin-sidebar fixed left-0 top-0 h-full w-64 text-white p-6 flex flex-col">
        <div className="flex items-center gap-3 mb-10">
          <Building2 className="w-8 h-8" />
          <h2 className="text-xl font-bold">Super Admin</h2>
        </div>
        <nav className="space-y-1 flex-1">
          {TABS.map(({ key, label, icon: Icon }) => (
            <Button
              key={key}
              variant="ghost"
              className={`w-full justify-start text-white hover:bg-white/10 ${activeTab === key ? "bg-white/20" : ""}`}
              onClick={() => setActiveTab(key)}
              data-testid={`nav-${key}`}
            >
              <Icon className="w-5 h-5 mr-3" />
              {label}
            </Button>
          ))}
        </nav>
        <Button
          variant="ghost"
          className="w-full justify-start text-white hover:bg-white/10"
          onClick={handleLogout}
          data-testid="logout-btn"
        >
          <LogOut className="w-5 h-5 mr-3" />
          Logout
        </Button>
      </div>

      {/* Main content */}
      <div className="ml-64 p-8">

        {/* ── Dashboard tab ── */}
        {activeTab === "dashboard" && (
          <>
            <div className="flex justify-between items-center mb-8">
              <h1 className="text-4xl font-bold text-[#1A2E40]">Dashboard</h1>
              <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
                <DialogTrigger asChild>
                  <Button className="bg-[#E06F2C] hover:bg-[#C55D20] text-white" data-testid="create-company-btn">
                    <Plus className="w-5 h-5 mr-2" /> Create Company
                  </Button>
                </DialogTrigger>
                <DialogContent data-testid="create-company-dialog">
                  <DialogHeader><DialogTitle>Create New Company</DialogTitle></DialogHeader>
                  <form onSubmit={handleCreateCompany} className="space-y-4">
                    <div>
                      <Label htmlFor="name">Company Name</Label>
                      <Input id="name" value={newCompany.name}
                        onChange={(e) => setNewCompany({ ...newCompany, name: e.target.value })}
                        required data-testid="company-name-input" />
                    </div>
                    <div>
                      <Label htmlFor="email">Admin Email</Label>
                      <Input id="email" type="email" value={newCompany.email}
                        onChange={(e) => setNewCompany({ ...newCompany, email: e.target.value })}
                        required data-testid="company-email-input" />
                    </div>
                    <div>
                      <Label htmlFor="password">Admin Password</Label>
                      <Input id="password" type="password" value={newCompany.admin_password}
                        onChange={(e) => setNewCompany({ ...newCompany, admin_password: e.target.value })}
                        required data-testid="company-password-input" />
                    </div>
                    <div>
                      <Label htmlFor="model">LLM Model</Label>
                      <Select value={newCompany.llm_model}
                        onValueChange={(v) => setNewCompany({ ...newCompany, llm_model: v })}>
                        <SelectTrigger data-testid="llm-model-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="gpt-5.2">GPT-5.2 (OpenAI)</SelectItem>
                          <SelectItem value="gpt-5.1">GPT-5.1 (OpenAI)</SelectItem>
                          <SelectItem value="claude-sonnet-4-5-20250929">Claude Sonnet 4.5</SelectItem>
                          <SelectItem value="gemini-2.5-pro">Gemini 2.5 Pro</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <Button type="submit" className="w-full bg-[#E06F2C] hover:bg-[#C55D20]"
                      data-testid="submit-create-company">
                      Create Company
                    </Button>
                  </form>
                </DialogContent>
              </Dialog>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              <div className="bg-white rounded-xl p-6 shadow-md" data-testid="stats-companies">
                <h3 className="text-gray-500 text-sm mb-1">Total Companies</h3>
                <p className="text-4xl font-bold text-[#E06F2C]">{analytics.total_companies ?? 0}</p>
              </div>
              <div className="bg-white rounded-xl p-6 shadow-md" data-testid="stats-sessions">
                <h3 className="text-gray-500 text-sm mb-1">Total Sessions</h3>
                <p className="text-4xl font-bold text-[#2E8B57]">{analytics.total_sessions ?? 0}</p>
              </div>
              <div className="bg-white rounded-xl p-6 shadow-md" data-testid="stats-documents">
                <h3 className="text-gray-500 text-sm mb-1">Total Documents</h3>
                <p className="text-4xl font-bold text-[#1A2E40]">{analytics.total_documents ?? 0}</p>
              </div>
            </div>

            <div className="bg-white rounded-xl shadow-md p-6">
              <h2 className="text-2xl font-bold text-[#1A2E40] mb-6">Companies</h2>
              <div className="space-y-3">
                {companies.map((company) => (
                  <div key={company.id}
                    className="border border-gray-200 rounded-lg p-4 hover:border-[#E06F2C] transition-colors"
                    data-testid={`company-card-${company.id}`}>
                    <div className="flex justify-between items-start gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-1">
                          <h3 className="text-lg font-semibold text-[#1A2E40]">{company.name}</h3>
                          <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            company.status === "active" ? "bg-green-100 text-green-800" : "bg-gray-100 text-gray-600"
                          }`}>{company.status}</span>
                        </div>
                        <p className="text-gray-500 text-sm mb-2">{company.email}</p>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-400 font-medium uppercase tracking-wide">Company ID</span>
                          <CopyId id={company.id} />
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">LLM Model</p>
                        <p className="text-sm font-medium text-[#1A2E40]">{company.llm_model}</p>
                        {company.created_at && (
                          <p className="text-xs text-gray-400 mt-1">
                            Created {formatDate(company.created_at)}
                          </p>
                        )}
                        <Button
                          size="sm" variant="outline" className="mt-2"
                          onClick={() => setAdminsForCompany(company)}
                          data-testid={`manage-admins-${company.id}`}
                        >
                          <UserPlus className="w-3 h-3 mr-1" /> Admins
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {/* ── Conversations tab ── */}
        {activeTab === "conversations" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Conversations</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <ConversationsTab companies={companies} token={token} />
            </div>
          </>
        )}

        {/* ── Audit Logs tab ── */}
        {activeTab === "audit-logs" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Audit Logs</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <AuditLogsTab companies={companies} token={token} />
            </div>
          </>
        )}

        {/* ── Seva Setu Applications tab ── */}
        {activeTab === "seva-applications" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Seva Setu Applications</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <SevaApplicationsTab token={token} companies={companies} />
            </div>
          </>
        )}

        {/* ── Knowledge Base tab ── */}
        {activeTab === "knowledge" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Knowledge Base</h1>
            <KnowledgeTab token={token} companies={companies} />
            <div className="mt-8">
              <BlockedKeywordsPanel token={token} />
            </div>
          </>
        )}

        {/* ── Tenant Services tab (Sprint 4D/4E) ── */}
        {activeTab === "tenant-services" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Services</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <TenantServicesTab companies={companies} token={token} />
            </div>
          </>
        )}

        {/* ── Channel Mappings tab (Sprint 5) ── */}
        {activeTab === "channel-mappings" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Channel Mappings</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <ChannelMappingsTab companies={companies} token={token} />
            </div>
          </>
        )}

        {/* ── Bot Config tab (Sprint 3D) ── */}
        {activeTab === "bot-config" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Bot Config</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <BotConfigTab companies={companies} token={token} />
            </div>
          </>
        )}

        {/* ── Scrapers tab (Sprint 2F) ── */}
        {activeTab === "scrapers" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Scrapers</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <ScrapersTab companies={companies} token={token} />
            </div>
          </>
        )}

      </div>

      {/* Sprint 11 — admins manager modal */}
      {adminsForCompany && (
        <AdminsModal
          company={adminsForCompany}
          token={token}
          onClose={() => setAdminsForCompany(null)}
        />
      )}
    </div>
  );
}

/* ─── Sprint 11 — Admins manager modal ─────────────────────────────────── */

function AdminsModal({ company, token, onClose }) {
  const [admins, setAdmins] = useState([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newPass, setNewPass]   = useState("");
  const [resetting, setResetting] = useState(null); // admin row when reset prompt open
  const [resetPass, setResetPass] = useState("");

  const fetchAdmins = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/super-admin/companies/${company.id}/admins`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      setAdmins(data.admins || []);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [company.id, token]);

  useEffect(() => { fetchAdmins(); }, [fetchAdmins]);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (newPass.length < 8) { toast.error("Initial password must be at least 8 characters"); return; }
    setAdding(true);
    try {
      const res = await fetch(`${API}/super-admin/companies/${company.id}/admins`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ email: newEmail.trim(), initial_password: newPass }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      toast.success(`Added ${data.email}. They'll be forced to set a new password on first login.`);
      setNewEmail(""); setNewPass("");
      fetchAdmins();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (admin) => {
    if (!window.confirm(`Remove admin ${admin.email}? They'll lose access immediately.`)) return;
    try {
      const res = await fetch(`${API}/super-admin/companies/${company.id}/admins/${admin.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed");
      toast.success("Admin removed");
      fetchAdmins();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleReset = async () => {
    if (resetPass.length < 8) { toast.error("New password must be at least 8 characters"); return; }
    try {
      const res = await fetch(`${API}/super-admin/companies/${company.id}/admins/${resetting.id}/reset-password`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: resetPass }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      toast.success(`Password reset for ${resetting.email}. They'll be forced to change it on next login.`);
      setResetting(null); setResetPass("");
      fetchAdmins();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold">Admins — {company.name}</h3>
            <p className="text-xs text-slate-400">Tenant {company.id.slice(0, 8)}…</p>
          </div>
          <Button variant="ghost" onClick={onClose}>Close</Button>
        </div>

        {loading ? (
          <div className="text-center text-slate-400 py-4">Loading…</div>
        ) : (
          <table className="w-full text-sm mb-6">
            <thead className="bg-slate-50 text-left text-slate-600">
              <tr>
                <th className="px-3 py-2">Email</th>
                <th className="px-3 py-2">Created</th>
                <th className="px-3 py-2">Reset?</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {admins.map((a) => (
                <tr key={a.id} className="border-t">
                  <td className="px-3 py-2 font-mono text-xs">{a.email}</td>
                  <td className="px-3 py-2 text-xs text-slate-500">{(a.created_at || "").slice(0, 10)}</td>
                  <td className="px-3 py-2 text-xs">
                    {a.password_change_required ? <span className="text-amber-600">forced change pending</span> : "—"}
                  </td>
                  <td className="px-3 py-2 text-right space-x-1">
                    <Button size="sm" variant="ghost" onClick={() => { setResetting(a); setResetPass(""); }}>
                      <KeyRound className="w-3.5 h-3.5" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => handleDelete(a)} disabled={admins.length <= 1}>
                      <Trash2 className="w-3.5 h-3.5 text-red-500" />
                    </Button>
                  </td>
                </tr>
              ))}
              {admins.length === 0 && (
                <tr><td colSpan={4} className="text-center py-4 text-slate-400">No admins yet</td></tr>
              )}
            </tbody>
          </table>
        )}

        {/* Add admin form */}
        <form onSubmit={handleAdd} className="border-t pt-4 space-y-3">
          <div className="text-sm font-medium text-[#1A2E40]">Add admin</div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-xs">Email</Label>
              <Input value={newEmail} onChange={(e) => setNewEmail(e.target.value)}
                     type="email" required placeholder="admin@example.com" />
            </div>
            <div>
              <Label className="text-xs">Initial password (≥8 chars)</Label>
              <Input value={newPass} onChange={(e) => setNewPass(e.target.value)}
                     type="text" required placeholder="They'll be forced to change it" />
            </div>
          </div>
          <Button type="submit" disabled={adding} className="bg-[#E06F2C] hover:bg-[#C55D20] text-white">
            <UserPlus className="w-4 h-4 mr-2" /> {adding ? "Adding…" : "Add admin"}
          </Button>
        </form>

        {/* Reset password sub-modal */}
        {resetting && (
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => setResetting(null)}>
            <div className="bg-white rounded-xl max-w-md w-full p-6" onClick={(e) => e.stopPropagation()}>
              <h4 className="font-semibold mb-2">Reset password</h4>
              <p className="text-sm text-slate-500 mb-3">
                Set a new bootstrap password for <strong>{resetting.email}</strong>. They'll be forced
                to change it on next login.
              </p>
              <Input
                value={resetPass}
                onChange={(e) => setResetPass(e.target.value)}
                placeholder="New password (≥8 chars)"
                type="text"
              />
              <div className="flex justify-end gap-2 mt-4">
                <Button variant="outline" onClick={() => setResetting(null)}>Cancel</Button>
                <Button onClick={handleReset}>Reset password</Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
