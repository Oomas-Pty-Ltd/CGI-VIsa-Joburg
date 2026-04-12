import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Building2, Plus, Settings, TrendingUp, LogOut,
  MessageSquare, Shield, Download, ChevronLeft, ChevronRight,
  X, RefreshCw, Copy, Check
} from "lucide-react";
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
  { key: "settings", label: "Settings", icon: Settings },
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

// ─── Main dashboard ───────────────────────────────────────────────────────────
export default function SuperAdminDashboard() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("dashboard");
  const [companies, setCompanies] = useState([]);
  const [analytics, setAnalytics] = useState({});
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newCompany, setNewCompany] = useState({
    name: "", email: "", admin_password: "", llm_model: "gpt-5.2",
  });

  const token = localStorage.getItem("token");

  useEffect(() => {
    if (!token) { navigate("/super-admin/login"); return; }
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

        {/* ── Settings tab ── */}
        {activeTab === "settings" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Settings</h1>
            <div className="bg-white rounded-xl shadow-md p-6 text-gray-500">
              Settings coming soon.
            </div>
          </>
        )}
      </div>
    </div>
  );
}
