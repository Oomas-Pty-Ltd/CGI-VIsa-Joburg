import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Building2, Plus, TrendingUp, LogOut,
  MessageSquare, Shield, Download, ChevronLeft, ChevronRight,
  X, RefreshCw, Copy, Check, BookOpen, Upload, Trash2, FileText,
  Calendar, Clock, AlertCircle, Files, Search, Ban, Unlock,
  Workflow, Smartphone, Bot, Globe, UserPlus, KeyRound, Settings, Bell,
  DollarSign, Cpu,
} from "lucide-react";
import ChannelMappingsTab from "./super-admin/ChannelMappingsTab";
import TenantServicesTab from "./super-admin/TenantServicesTab";
import BotConfigTab from "./super-admin/BotConfigTab";
import ScrapersTab from "./super-admin/ScrapersTab";
import NotificationsTab from "./super-admin/NotificationsTab";
import KnowledgeBasePanel from "@/components/admin/KnowledgeBasePanel";
import PlatformSettingsTab from "./super-admin/PlatformSettingsTab";
import LlmUsageTab from "./super-admin/LlmUsageTab";
import ModelsTab from "./super-admin/ModelsTab";
import AdminShell from "@/components/AdminShell";
import { Section } from "@/components/admin/Section";
import { StatCard } from "@/components/admin/StatCard";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
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
      className="flex items-center gap-1.5 px-2 py-1 rounded bg-muted hover:bg-muted/70 transition-colors group"
      title="Copy company ID"
    >
      <span className="font-mono text-xs text-muted-foreground select-all">{id}</span>
      {copied
        ? <Check className="w-3.5 h-3.5 text-success shrink-0" />
        : <Copy className="w-3.5 h-3.5 text-muted-foreground/70 group-hover:text-foreground shrink-0" />}
    </button>
  );
}

// Tabs grouped semantically. AdminShell renders the group label above
// each cluster so super-admins can find the right section faster than
// scanning 10 unstructured items.
const TABS = [
  { key: "dashboard",         label: "Overview",        icon: TrendingUp,    group: "Overview" },
  { key: "conversations",     label: "Conversations",   icon: MessageSquare, group: "Activity" },
  { key: "audit-logs",        label: "Audit logs",      icon: Shield,        group: "Activity" },
  { key: "seva-applications", label: "Applications",    icon: Files,         group: "Activity" },
  { key: "llm-cost",          label: "LLM cost",        icon: DollarSign,    group: "Activity" },
  { key: "tenant-services",   label: "Services",        icon: Workflow,      group: "Content" },
  { key: "knowledge",         label: "Knowledge base",  icon: BookOpen,      group: "Content" },
  { key: "bot-config",        label: "Bot config",      icon: Bot,           group: "Configuration" },
  { key: "models",            label: "Models",          icon: Cpu,           group: "Configuration" },
  { key: "channel-mappings",  label: "Channels",        icon: Smartphone,    group: "Configuration" },
  { key: "scrapers",          label: "Scrapers",        icon: Globe,         group: "Configuration" },
  { key: "notifications",     label: "Notifications",   icon: Bell,          group: "Configuration" },
  { key: "platform-settings", label: "Platform",        icon: Settings,      group: "Configuration" },
];

// Token-based pill palette. We collapse the previous 18 hand-picked Tailwind
// shades into four semantic variants — subtle, info, warning, destructive —
// so a tenant theme override actually does something useful, and so adding a
// new channel/category doesn't require picking another hue out of thin air.
const PILL_SUBTLE      = "bg-muted text-muted-foreground border border-border";
const PILL_INFO        = "bg-primary/10 text-primary border border-primary/20";
const PILL_SUCCESS     = "bg-success/10 text-success border border-success/20";
const PILL_WARNING     = "bg-warning/10 text-warning border border-warning/20";
const PILL_DESTRUCTIVE = "bg-destructive/10 text-destructive border border-destructive/20";

const CHANNEL_COLORS = {
  web:      PILL_INFO,
  whatsapp: PILL_SUCCESS,
  facebook: PILL_INFO,
  widget:   PILL_SUBTLE,
};

const SEVERITY_COLORS = {
  info:     PILL_INFO,
  warning:  PILL_WARNING,
  error:    PILL_DESTRUCTIVE,
  critical: `${PILL_DESTRUCTIVE} font-semibold`,
};

// Categories collapse to subtle (read events), warning (mutations), and
// destructive (deletes / security). Icons in the row carry the precise
// semantic; the pill is just a coarse colour cue.
const CATEGORY_COLORS = {
  auth:              PILL_SUBTLE,
  data_access:       PILL_SUBTLE,
  data_modification: PILL_WARNING,
  data_deletion:     PILL_DESTRUCTIVE,
  data_export:       PILL_WARNING,
  admin_action:      PILL_WARNING,
  security_event:    PILL_DESTRUCTIVE,
  system_event:      PILL_SUBTLE,
  consent:           PILL_INFO,
  api_access:        PILL_SUBTLE,
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
    <div className="flex items-center gap-3 justify-end mt-4 text-sm text-muted-foreground">
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
  }, [sessionId, token]);

  return (
    <Dialog open={!!sessionId} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] p-0 flex flex-col gap-0">
        <DialogHeader className="px-5 py-4 border-b border-border">
          <DialogTitle className="text-base">Conversation detail</DialogTitle>
          {session && (
            <p className="text-xs text-muted-foreground mt-0.5">
              {session.id} · {session.channel} · {formatDate(session.created_at)}
            </p>
          )}
        </DialogHeader>

        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-3">
          {loading && <p className="text-muted-foreground text-center py-8 text-sm">Loading…</p>}
          {!loading && !session && <p className="text-destructive text-center py-8 text-sm">Session not found.</p>}
          {session && (session.messages || []).length === 0 && (
            <p className="text-muted-foreground text-center py-8 text-sm">No messages in this session.</p>
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
                      ? "bg-primary text-primary-foreground rounded-br-sm"
                      : "bg-muted text-foreground rounded-bl-sm"
                  }`}
                >
                  <p className="whitespace-pre-wrap break-words">{msg.content}</p>
                  <p className={`text-[11px] mt-1 ${msg.role === "user" ? "text-primary-foreground/70" : "text-muted-foreground"}`}>
                    {msg.role === "user" ? "User" : "Bot"} · {formatDate(msg.timestamp)}
                  </p>
                </div>
              </div>
            ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Conversations tab ────────────────────────────────────────────────────────
export function ConversationsTab({ companies = [], token, singleTenant = false }) {
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
    <div className="space-y-4">
      {/* Filters + actions row */}
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div className="flex gap-2 flex-wrap items-end">
          {!singleTenant && (
          <div className="w-44">
            <Label className="text-xs text-muted-foreground">Company</Label>
            <Select value={filters.company_id || "all"} onValueChange={(v) => { setFilters(f => ({ ...f, company_id: v === "all" ? "" : v })); setPage(1); }}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="All companies" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All companies</SelectItem>
                {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          )}
          <div className="w-40">
            <Label className="text-xs text-muted-foreground">Channel</Label>
            <Select value={filters.channel || "all"} onValueChange={(v) => { setFilters(f => ({ ...f, channel: v === "all" ? "" : v })); setPage(1); }}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="All channels" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All channels</SelectItem>
                {["web", "whatsapp", "facebook", "widget"].map((ch) => (
                  <SelectItem key={ch} value={ch}>{ch}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchSessions} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button size="sm" variant="outline" onClick={handleCsvDownload}>
            <Download className="mr-1.5 h-3.5 w-3.5" /> Export CSV
          </Button>
        </div>
      </div>

      <Section
        title="Sessions"
        description="Click any row to view the full message history. Filter by tenant or channel to narrow the view."
        bodyClassName="p-0"
      >
        {loading ? (
          <div className="px-5 py-12 text-center text-sm text-muted-foreground">Loading…</div>
        ) : sessions.length === 0 ? (
          <div className="px-5 py-12 text-center text-sm text-muted-foreground">No sessions found for the current filters.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-left text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-2.5">Session</th>
                <th className="px-4 py-2.5">Channel</th>
                <th className="px-4 py-2.5">User</th>
                <th className="px-4 py-2.5">First message</th>
                <th className="px-4 py-2.5 text-right">Msgs</th>
                <th className="px-4 py-2.5">Started</th>
                <th className="px-4 py-2.5">Last active</th>
                <th className="px-4 py-2.5 text-center">Status</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr
                  key={s.id}
                  onClick={() => setSelectedSession(s.id)}
                  className="border-t border-border hover:bg-muted/30 cursor-pointer transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{shortId(s.id)}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CHANNEL_COLORS[s.channel] || "bg-muted text-muted-foreground"}`}>
                      {s.channel}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-foreground max-w-[140px] truncate">{s.user_identifier}</td>
                  <td className="px-4 py-3 text-muted-foreground max-w-[260px] truncate">{s.first_message}</td>
                  <td className="px-4 py-3 text-right font-medium tabular-nums">{s.message_count}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">{formatDate(s.created_at)}</td>
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">{formatDate(s.last_activity)}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${s.is_active ? "bg-success/10 text-success border-success/20" : "bg-muted text-muted-foreground border-border"}`}>
                      {s.is_active ? "Active" : "Closed"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

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
export function AuditLogsTab({ companies = [], token, singleTenant = false }) {
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
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div className="flex gap-2 flex-wrap items-end">
          {!singleTenant && (
          <div className="w-44">
            <Label className="text-xs text-muted-foreground">Company</Label>
            <Select value={filters.company_id || "all"} onValueChange={(v) => { setFilters(f => ({ ...f, company_id: v === "all" ? "" : v })); setPage(1); }}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="All companies" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All companies</SelectItem>
                {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          )}
          <div className="w-44">
            <Label className="text-xs text-muted-foreground">Category</Label>
            <Select value={filters.category || "all"} onValueChange={(v) => { setFilters(f => ({ ...f, category: v === "all" ? "" : v })); setPage(1); }}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="All categories" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c.replace(/_/g," ")}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="w-32">
            <Label className="text-xs text-muted-foreground">Severity</Label>
            <Select value={filters.severity || "all"} onValueChange={(v) => { setFilters(f => ({ ...f, severity: v === "all" ? "" : v })); setPage(1); }}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="All" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                {["info","warning","error","critical"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchLogs} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={handleCsvDownload}>
            <Download className="mr-1.5 h-3.5 w-3.5" /> Export CSV
          </Button>
        </div>
      </div>

      <Section
        title="Audit log"
        description="Authentication, data-access, and admin-action events across all tenants."
        bodyClassName="p-0"
      >
        {loading ? (
          <div className="px-5 py-12 text-center text-sm text-muted-foreground">Loading…</div>
        ) : logs.length === 0 ? (
          <div className="px-5 py-12 text-center text-sm text-muted-foreground">No audit logs found for the current filters.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-left text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-2.5">Timestamp</th>
                <th className="px-4 py-2.5">Category</th>
                <th className="px-4 py-2.5">Action</th>
                <th className="px-4 py-2.5">User</th>
                <th className="px-4 py-2.5">Resource</th>
                <th className="px-4 py-2.5 text-center">Severity</th>
                <th className="px-4 py-2.5 text-center">Result</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log, i) => (
                <tr key={log.id || i} className="border-t border-border hover:bg-muted/30">
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">{formatDate(log.timestamp)}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CATEGORY_COLORS[log.category] || "bg-muted text-muted-foreground"}`}>
                      {(log.category || "—").replace(/_/g," ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-medium text-foreground">{log.action || "—"}</td>
                  <td className="px-4 py-3 text-xs">
                    <div className="text-foreground">{log.user_id ? shortId(log.user_id) : "—"}</div>
                    {log.user_type && <div className="text-muted-foreground">{log.user_type}</div>}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {log.resource_type
                      ? <><span className="font-medium text-foreground">{log.resource_type}</span>{log.resource_id && <span className="text-muted-foreground"> · {shortId(log.resource_id)}</span>}</>
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${SEVERITY_COLORS[log.severity] || "bg-muted text-muted-foreground"}`}>
                      {log.severity || "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${log.success ? "bg-success/10 text-success border-success/20" : "bg-destructive/10 text-destructive border-destructive/20"}`}>
                      {log.success ? "OK" : "FAIL"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Pagination page={page} total={total} limit={limit} onChange={setPage} />
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
    <div className="bg-card border border-border rounded-lg shadow-sm p-6 space-y-6">
      <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
        <Ban className="w-5 h-5 text-destructive" />
        Keyword Blocker
      </h2>
      <p className="text-sm text-muted-foreground">
        Search for a keyword across all knowledge base entries, then block it. When a user asks
        the bot about a blocked keyword, the bot will return no information.
      </p>

      {/* Search bar */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSearchResults(null); }}
            placeholder="Type a keyword to search (e.g. visa fee, oci, passport)"
            className="w-full pl-9 pr-4 py-2 border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-ring"
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
          className="h-[38px] bg-destructive hover:bg-destructive text-white"
        >
          <Ban className="w-4 h-4 mr-1" />
          {isAlreadyBlocked ? "Already Blocked" : "Block Keyword"}
        </Button>
      </form>

      {/* Search results */}
      {searchResults && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-semibold text-foreground">
              {searchResults.total} knowledge entries match
              <span className="ml-1 px-1.5 py-0.5 bg-muted rounded text-muted-foreground font-mono text-xs">
                "{searchResults.query}"
              </span>
            </p>
            {searchResults.total > 0 && !isAlreadyBlocked && (
              <span className="text-xs text-destructive">
                Blocking this keyword will suppress all {searchResults.total} entries from the bot.
              </span>
            )}
          </div>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-muted-foreground text-xs uppercase tracking-wide">
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
                    <td colSpan={4} className="text-center py-8 text-muted-foreground">
                      No knowledge entries found for this keyword.
                    </td>
                  </tr>
                )}
                {searchResults.matches.map((entry) => (
                  <tr key={entry.id} className="border-t border-border hover:bg-destructive/10 transition-colors">
                    <td className="px-4 py-3 text-foreground font-medium max-w-[220px] truncate" title={entry.title}>
                      {entry.title}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-warning/10 text-warning">
                        {entry.category || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground max-w-[140px] truncate" title={entry.pdf_filename || entry.source}>
                      {entry.pdf_filename || entry.source || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {(entry.keywords || []).slice(0, 5).map((kw) => (
                          <span key={kw} className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground text-xs">{kw}</span>
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
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-1.5">
            <Ban className="w-4 h-4 text-destructive/70" />
            Blocked Keywords
            {blocked.length > 0 && (
              <span className="ml-1 px-1.5 py-0.5 bg-destructive/10 text-destructive rounded-full text-xs font-medium">
                {blocked.length}
              </span>
            )}
          </h3>
          <Button variant="outline" size="sm" onClick={fetchBlocked} className="h-7">
            <RefreshCw className="w-3.5 h-3.5 mr-1" /> Refresh
          </Button>
        </div>

        {loadingBlocked && <p className="text-muted-foreground text-sm py-4 text-center">Loading…</p>}

        {!loadingBlocked && blocked.length === 0 && (
          <div className="border border-dashed border-border rounded-lg p-8 text-center text-muted-foreground text-sm">
            No keywords blocked yet. Search and block keywords above.
          </div>
        )}

        {!loadingBlocked && blocked.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-muted-foreground text-xs uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left">Keyword</th>
                  <th className="px-4 py-3 text-center">Entries Suppressed</th>
                  <th className="px-4 py-3 text-left">Blocked At</th>
                  <th className="px-4 py-3 text-center">Action</th>
                </tr>
              </thead>
              <tbody>
                {blocked.map((b) => (
                  <tr key={b.keyword} className="border-t border-border hover:bg-destructive/10 transition-colors">
                    <td className="px-4 py-3 font-mono font-semibold text-destructive">
                      <span className="flex items-center gap-1.5">
                        <Ban className="w-3.5 h-3.5 text-destructive/70 flex-shrink-0" />
                        {b.keyword}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-destructive/10 text-destructive">
                        {b.matches_count ?? "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                      {formatDate(b.blocked_at)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 text-success hover:bg-success/10 hover:text-success gap-1"
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

export function SevaApplicationsTab({ token, companies = [], singleTenant = false, companyId = "" }) {
  const [applications, setApplications] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selectedApp, setSelectedApp] = useState(null);
  const [documentPreview, setDocumentPreview] = useState(null);
  const [services, setServices] = useState([]);
  const [filters, setFilters] = useState({
    // For a tenant admin, scope to their own company up-front so the
    // service-type filter (which is per-tenant) works and the backend
    // returns only their applications.
    company_id: singleTenant ? (companyId || "") : "",
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
    setFilters({ company_id: singleTenant ? (companyId || "") : "", status: "", service_type: "", search: "", from_date: "", to_date: "", with_documents: true });
    setPage(1);
  };

  const hasActiveFilters = [singleTenant ? null : "company_id", "status", "service_type", "search", "from_date", "to_date"].filter(Boolean).some((k) => filters[k]);

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

  // Token-based status pill palette: subtle for in-progress states, success
  // for terminal-positive, destructive for rejection. No raw Tailwind shades
  // so a future theme swap (or per-tenant brand override) Just Works.
  const STATUS_COLORS = {
    draft:               "bg-muted text-muted-foreground border border-border",
    submitted:           "bg-primary/10 text-primary border border-primary/20",
    submission_pending:  "bg-warning/10 text-warning border border-warning/20",
    confirmed:           "bg-success/10 text-success border border-success/20",
    completed:           "bg-success/15 text-success border border-success/30",
    rejected:            "bg-destructive/10 text-destructive border border-destructive/20",
  };

  const [retrying, setRetrying] = useState(false);
  const handleRetrySubmission = async (appId) => {
    setRetrying(true);
    try {
      const { data } = await axios.post(
        `${API}/seva-setu/applications/${appId}/retry-submission`,
        {},
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (data.success) {
        toast.success(data.message || "Submission accepted on retry.");
      } else {
        toast.error(data.message || "Retry failed — still pending.");
      }
      // Refresh the list and re-open the same application with fresh data.
      const { data: listData } = await axios.get(`${API}/super-admin/seva-setu/applications`, {
        headers: { Authorization: `Bearer ${token}` },
        params: buildParams(),
      });
      setApplications(listData.applications);
      setTotal(listData.total);
      const fresh = (listData.applications || []).find((a) => a.id === appId);
      if (fresh) setSelectedApp(fresh);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Retry request failed");
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div className="flex gap-2 flex-wrap items-end">
          {!singleTenant && (
          <div className="w-44">
            <Label className="text-xs text-muted-foreground">Company</Label>
            <Select value={filters.company_id || "all"} onValueChange={(v) => setFilter({ company_id: v === "all" ? "" : v })}>
              <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All companies</SelectItem>
                {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          )}
          <div className="w-36">
            <Label className="text-xs text-muted-foreground">Status</Label>
            <Select value={filters.status || "all"} onValueChange={(v) => setFilter({ status: v === "all" ? "" : v })}>
              <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {SEVA_APP_STATUSES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="w-44">
            <Label className="text-xs text-muted-foreground">Service</Label>
            <Select
              value={filters.service_type || "all"}
              onValueChange={(v) => setFilter({ service_type: v === "all" ? "" : v })}
              disabled={!filters.company_id}
            >
              <SelectTrigger className="mt-1">
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
          <div className="w-44">
            <Label className="text-xs text-muted-foreground">Search reference</Label>
            <Input
              type="text"
              placeholder="e.g. PASS-2024"
              value={filters.search}
              onChange={(e) => setFilter({ search: e.target.value })}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">From</Label>
            <Input
              type="date"
              value={filters.from_date}
              onChange={(e) => setFilter({ from_date: e.target.value })}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground">To</Label>
            <Input
              type="date"
              value={filters.to_date}
              onChange={(e) => setFilter({ to_date: e.target.value })}
              className="mt-1"
            />
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchApplications} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={handleCsvDownload}>
            <Download className="mr-1.5 h-3.5 w-3.5" /> Export CSV
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={filters.with_documents}
            onChange={(e) => setFilter({ with_documents: e.target.checked })}
          />
          With documents only
        </label>
        <span>
          {total} application{total === 1 ? "" : "s"}
          {hasActiveFilters && <span className="ml-1">(filtered)</span>}
        </span>
        {hasActiveFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>Clear filters</Button>
        )}
      </div>

      <Section
        title="Applications"
        description="All applications submitted across the platform. Click the document icon to view the full record."
        bodyClassName="p-0"
      >
        {loading ? (
          <div className="px-5 py-12 text-center text-sm text-muted-foreground">Loading…</div>
        ) : applications.length === 0 ? (
          <div className="px-5 py-12 text-center text-sm text-muted-foreground">
            {hasActiveFilters ? "No applications match these filters." : "No applications found."}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-left text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-2.5">Reference</th>
                <th className="px-4 py-2.5">Service</th>
                <th className="px-4 py-2.5">User</th>
                <th className="px-4 py-2.5 text-center">Status</th>
                <th className="px-4 py-2.5 text-right">Docs</th>
                <th className="px-4 py-2.5">Created</th>
                <th className="px-4 py-2.5 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((app, i) => (
                <tr key={app.id || i} className="border-t border-border hover:bg-muted/30">
                  <td className="px-4 py-3 font-mono text-xs text-foreground">{shortId(app.reference_id)}</td>
                  <td className="px-4 py-3 text-foreground">{app.service_name || app.service_type}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground font-mono">{shortId(app.user_id)}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[app.status] || "bg-muted text-muted-foreground"}`}>
                      {app.status || "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    <span className={`font-mono text-xs ${app.document_count > 0 ? "text-success font-medium" : "text-muted-foreground"}`}>
                      {app.document_count}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">{formatDate(app.created_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 w-8 p-0"
                      onClick={() => setSelectedApp(app)}
                      title="View details"
                    >
                      <FileText className="w-3.5 h-3.5" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Pagination page={page} total={total} limit={limit} onChange={setPage} />

      {/* Application detail modal */}
      {selectedApp && (
        <Dialog open={!!selectedApp} onOpenChange={(o) => !o && setSelectedApp(null)}>
          <DialogContent className="max-w-3xl max-h-[85vh] p-0 flex flex-col gap-0">
            <DialogHeader className="px-5 py-4 border-b border-border">
              <DialogTitle className="text-base">Application details</DialogTitle>
              <p className="text-xs text-muted-foreground mt-0.5 font-mono">{selectedApp.reference_id}</p>
            </DialogHeader>

            <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Service</p>
                  <p className="text-sm text-foreground mt-0.5">{selectedApp.service_name}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Status</p>
                  <div className="mt-0.5">
                    <span className={`text-xs px-2 py-0.5 rounded-full inline-block font-medium ${STATUS_COLORS[selectedApp.status] || "bg-muted text-muted-foreground"}`}>
                      {selectedApp.status}
                    </span>
                  </div>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">User ID</p>
                  <p className="text-sm text-foreground font-mono mt-0.5">{selectedApp.user_id}</p>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">Created</p>
                  <p className="text-sm text-foreground mt-0.5">{formatDate(selectedApp.created_at)}</p>
                </div>
              </div>

              {selectedApp.form_data_fields > 0 && (
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-2">
                    Form fields ({selectedApp.form_data_fields})
                  </p>
                  <div className="bg-muted rounded p-3 text-xs text-foreground max-h-48 overflow-y-auto">
                    <pre>{JSON.stringify(selectedApp.form_data || {}, null, 2).slice(0, 500)}</pre>
                  </div>
                </div>
              )}

              {selectedApp.documents && selectedApp.documents.length > 0 && (
                <div>
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-2">
                    Uploaded documents ({selectedApp.documents.length})
                  </p>
                  <div className="space-y-2">
                    {selectedApp.documents.map((doc) => (
                      <div key={doc.id} className="bg-muted/50 border border-border rounded p-3">
                        <div className="flex items-center gap-2 justify-between">
                          <div className="flex items-center gap-2 flex-1 min-w-0">
                            <FileText className="w-4 h-4 text-primary flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium text-foreground truncate">{doc.name}</p>
                              <p className="text-xs text-muted-foreground">{doc.content_type} · {formatDate(doc.uploaded_at)}</p>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5 flex-shrink-0">
                            <Badge variant={doc.status === "uploaded" ? "default" : "secondary"} className={doc.status === "uploaded" ? "bg-success/10 text-success border-success/20 hover:bg-success/10" : ""}>
                              {doc.status}
                            </Badge>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
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
                                className="text-muted-foreground hover:text-foreground p-1.5"
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

              {/* External processing-service invocations — the round-trip(s)
                  to the downstream gov service, recorded at confirm time. */}
              {selectedApp.service_invocations && selectedApp.service_invocations.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                      Service API calls ({selectedApp.service_invocations.length})
                    </p>
                    {(selectedApp.service_status === "failed" || selectedApp.status === "submission_pending") && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 gap-1.5"
                        disabled={retrying}
                        onClick={() => handleRetrySubmission(selectedApp.id)}
                      >
                        <RefreshCw className={`w-3.5 h-3.5 ${retrying ? "animate-spin" : ""}`} />
                        {retrying ? "Retrying…" : "Retry submission"}
                      </Button>
                    )}
                  </div>
                  {selectedApp.gov_processing_ref && (
                    <p className="text-xs text-muted-foreground mb-2">
                      Gov processing ref:{" "}
                      <span className="font-mono text-foreground">{selectedApp.gov_processing_ref}</span>
                    </p>
                  )}
                  <div className="space-y-2">
                    {selectedApp.service_invocations.map((inv) => (
                      <div key={inv.id} className="bg-muted/50 border border-border rounded p-3 space-y-2">
                        <div className="flex items-center gap-2 justify-between">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-xs font-mono text-muted-foreground">{inv.method}</span>
                            <span className="text-xs font-mono text-foreground truncate">{inv.endpoint}</span>
                          </div>
                          <Badge
                            variant={inv.ok ? "default" : "secondary"}
                            className={inv.ok
                              ? "bg-success/10 text-success border-success/20 hover:bg-success/10"
                              : "bg-destructive/10 text-destructive border-destructive/20 hover:bg-destructive/10"}
                          >
                            {inv.ok ? "OK" : "Failed"}{inv.status_code != null ? ` · ${inv.status_code}` : ""}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                          {inv.duration_ms != null && <span>{inv.duration_ms} ms</span>}
                          {inv.invoked_at && <span>{formatDate(inv.invoked_at)}</span>}
                          {inv.error && <span className="text-destructive">{inv.error}</span>}
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Request</p>
                            <pre className="bg-background border border-border rounded p-2 text-[11px] text-foreground max-h-40 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(inv.request || {}, null, 2)}</pre>
                          </div>
                          <div>
                            <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Response</p>
                            <pre className="bg-background border border-border rounded p-2 text-[11px] text-foreground max-h-40 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(inv.response ?? inv.error ?? {}, null, 2)}</pre>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Document preview modal */}
      <Dialog open={!!documentPreview} onOpenChange={(o) => !o && setDocumentPreview(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] p-0 flex flex-col gap-0">
          <DialogHeader className="px-5 py-4 border-b border-border">
            <DialogTitle className="text-base">Document preview</DialogTitle>
            <p className="text-xs text-muted-foreground mt-0.5">{documentPreview?.name}</p>
          </DialogHeader>
          <div className="overflow-y-auto flex-1 p-5 flex items-center justify-center bg-muted/40 min-h-[280px]">
            {documentPreview?.content_type === "application/pdf" ? (
              <div className="text-center">
                <FileText className="w-16 h-16 text-muted-foreground mx-auto mb-3" />
                <p className="text-sm text-muted-foreground mb-4">PDF document</p>
                {documentPreview?.file_url && (
                  <Button asChild>
                    <a
                      href={documentPreview.file_url}
                      download={documentPreview.name}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <Download className="w-4 h-4 mr-1.5" />
                      Download PDF
                    </a>
                  </Button>
                )}
              </div>
            ) : documentPreview?.content_type?.startsWith("image/") ? (
              <img
                src={documentPreview.file_url || documentPreview.data_url}
                alt={documentPreview.name}
                className="max-w-full max-h-full object-contain rounded"
              />
            ) : documentPreview ? (
              <div className="text-center">
                <FileText className="w-16 h-16 text-muted-foreground mx-auto mb-3" />
                <p className="text-sm text-muted-foreground mb-2">{documentPreview.content_type}</p>
                {documentPreview.file_url && (
                  <Button asChild>
                    <a
                      href={documentPreview.file_url}
                      download={documentPreview.name}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <Download className="w-4 h-4 mr-1.5" />
                      Download file
                    </a>
                  </Button>
                )}
              </div>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
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
  const [modelsForCompany, setModelsForCompany] = useState(null);  // Sprint 14 — assign models
  const [statusTarget, setStatusTarget] = useState(null);          // { company, next }
  const [statusSaving, setStatusSaving] = useState(false);
  // The Create Company dialog's LLM dropdown is driven by the registry
  // (`platform_models`), not hardcoded labels — adding a model in the
  // Models tab makes it pickable here on the next dialog open.
  const [registryModels, setRegistryModels] = useState([]);
  const [newCompany, setNewCompany] = useState({
    name: "", email: "", admin_password: "", llm_model: "",
  });

  const token = localStorage.getItem("token");

  const fetchData = useCallback(async () => {
    try {
      const cfg = { headers: { Authorization: `Bearer ${token}` } };
      const [companiesRes, analyticsRes, modelsRes] = await Promise.all([
        axios.get(`${API}/super-admin/companies`, cfg),
        axios.get(`${API}/super-admin/analytics/overview`, cfg),
        axios.get(`${API}/super-admin/models`, cfg).catch(() => ({ data: { models: [] } })),
      ]);
      setCompanies(companiesRes.data);
      setAnalytics(analyticsRes.data);
      const enabled = (modelsRes.data?.models || []).filter((m) => m.enabled);
      setRegistryModels(enabled);
      // Seed the Create Company dialog's default to the first enabled
      // model in the registry rather than a hardcoded "gpt-5.2".
      if (enabled.length > 0) {
        setNewCompany((prev) => prev.llm_model ? prev : { ...prev, llm_model: enabled[0].key });
      }
    } catch {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token) { navigate("/login"); return; }
    fetchData();
  }, [token, navigate, fetchData]);

  const handleCreateCompany = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/super-admin/companies`, newCompany, {
        headers: { Authorization: `Bearer ${token}` },
      });
      toast.success("Company created successfully!");
      setShowCreateDialog(false);
      setNewCompany({
        name: "", email: "", admin_password: "",
        llm_model: registryModels[0]?.key || "",
      });
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to create company");
    }
  };

  const handleLogout = () => { localStorage.clear(); navigate("/"); };

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen text-muted-foreground">Loading…</div>;
  }

  // Decode the JWT sub claim for the sidebar user row. Super-admin tokens
  // carry the admin's email in `sub`; the manual base64 parse keeps us off
  // a `jwt-decode` dependency for one field.
  const userEmail = (() => {
    try {
      const payload = (token || "").split(".")[1] || "";
      // base64url → base64
      const b64 = payload.replace(/-/g, "+").replace(/_/g, "/").padEnd(
        Math.ceil(payload.length / 4) * 4, "="
      );
      return JSON.parse(atob(b64))?.sub || "";
    } catch { return ""; }
  })();

  // Per-tab metadata fed into AdminShell's pageTitle / pageDescription /
  // pageActions slots. Keeping it next to the rest of the tab logic so
  // adding a tab means touching one place, not three.
  const createCompanyButton = (
    <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
      <DialogTrigger asChild>
        <Button size="sm" data-testid="create-company-btn">
          <Plus className="mr-1.5 h-3.5 w-3.5" /> Create company
        </Button>
      </DialogTrigger>
      <DialogContent data-testid="create-company-dialog">
        <DialogHeader><DialogTitle>Create new company</DialogTitle></DialogHeader>
        <form onSubmit={handleCreateCompany} className="space-y-4">
          <div>
            <Label htmlFor="name">Company name</Label>
            <Input id="name" value={newCompany.name}
              onChange={(e) => setNewCompany({ ...newCompany, name: e.target.value })}
              required data-testid="company-name-input" className="mt-1" />
          </div>
          <div>
            <Label htmlFor="email">Admin email</Label>
            <Input id="email" type="email" value={newCompany.email}
              onChange={(e) => setNewCompany({ ...newCompany, email: e.target.value })}
              required data-testid="company-email-input" className="mt-1" />
          </div>
          <div>
            <Label htmlFor="password">Admin password</Label>
            <Input id="password" type="password" value={newCompany.admin_password}
              onChange={(e) => setNewCompany({ ...newCompany, admin_password: e.target.value })}
              required data-testid="company-password-input" className="mt-1" />
          </div>
          <div>
            <Label htmlFor="model">LLM model</Label>
            <Select value={newCompany.llm_model}
              onValueChange={(v) => setNewCompany({ ...newCompany, llm_model: v })}>
              <SelectTrigger data-testid="llm-model-select" className="mt-1">
                <SelectValue placeholder={registryModels.length === 0 ? "No models registered yet" : "Pick a model"} />
              </SelectTrigger>
              <SelectContent>
                {registryModels.map((m) => (
                  <SelectItem key={m.key} value={m.key}>
                    {m.display_name || m.key}{m.provider ? ` (${m.provider})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {registryModels.length === 0 && (
              <p className="text-xs text-destructive mt-1 leading-snug">
                No models registered yet. Add one from <strong>Configuration → Models</strong> first.
              </p>
            )}
            <p className="text-xs text-muted-foreground mt-1 leading-snug">
              Sets this tenant's default model. You can adjust the full allowlist after creation
              via the per-tenant <strong>Models</strong> button.
            </p>
          </div>
          <Button type="submit" className="w-full" data-testid="submit-create-company">
            Create company
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );

  const PAGE_META = {
    "dashboard":         { title: "Overview",       description: "Platform-wide activity across all tenants.",                          actions: createCompanyButton },
    "conversations":     { title: "Conversations",  description: "User conversations from chat, WhatsApp, and Facebook channels." },
    "audit-logs":        { title: "Audit logs",     description: "Authentication, admin actions, and data-access events." },
    "seva-applications": { title: "Applications",   description: "Submitted applications across all tenants." },
    "llm-cost":          { title: "LLM cost",       description: "Per-tenant token spend with budget tracking and projections. Pick a tenant to view." },
    "models":            { title: "Models",         description: "Platform model registry. Add, price, and toggle models — tenants pick from this list when assigning models." },
    "knowledge":         { title: "Knowledge base", description: "Q&A entries and uploaded PDFs the bot draws from." },
    "tenant-services":   { title: "Services",       description: "The catalogue each tenant's chatbot offers." },
    "channel-mappings":  { title: "Channels",       description: "Map inbound WhatsApp / Facebook webhook identities to tenants." },
    "bot-config":        { title: "Bot config",     description: "Per-tenant identity, branding, languages, contact, and security." },
    "scrapers":          { title: "Scrapers",       description: "Site crawler per tenant — keeps the knowledge base fresh." },
    "notifications":     { title: "Notifications",  description: "Configure email notifications for every platform scenario — who's notified, the copy, thresholds, and cooldowns." },
    "platform-settings": { title: "Platform",       description: "Global tuning that applies to every tenant. Changes take effect on the next request (cache TTL = 60s). Env-var overrides take precedence over what's saved here." },
  };
  const meta = PAGE_META[activeTab] || {};

  return (
    <AdminShell
      title="Super Admin"
      tabs={TABS}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      user={{ email: userEmail, type: "super_admin" }}
      onLogout={handleLogout}
      pageTitle={meta.title}
      pageDescription={meta.description}
      pageActions={meta.actions}
      companies={companies}
      onTenantSelect={(id) => {
        // Picking a tenant from the palette: jump to Bot config and seed
        // localStorage so the BotConfigTab picker opens on that row. The
        // BotConfigTab already auto-selects companies[0] when its own
        // state is empty, so this is just a hint.
        try { localStorage.setItem("super_admin_preferred_tenant", id); } catch { /* ignore */ }
        setActiveTab("bot-config");
      }}
    >

        {/* ── Dashboard tab ── */}
        {activeTab === "dashboard" && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <StatCard icon={Building2}      label="Total companies" value={analytics.total_companies ?? 0} />
              <StatCard icon={MessageSquare}  label="Total sessions"  value={analytics.total_sessions  ?? 0} />
              <StatCard icon={Files}          label="Total documents" value={analytics.total_documents ?? 0} />
            </div>

            <Section
              title="Companies"
              description="Every tenant in the platform. Click Admins on a row to manage that tenant's local-admin accounts."
              bodyClassName="p-0"
            >
              <ul className="divide-y divide-border">
                {companies.map((company) => (
                  <li key={company.id}
                    className="px-5 py-4 hover:bg-muted/30 transition-colors"
                    data-testid={`company-card-${company.id}`}>
                    <div className="flex justify-between items-start gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2.5 mb-1 flex-wrap">
                          <h3 className="text-sm font-medium text-foreground">{company.name}</h3>
                          <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${
                            company.status === "active"
                              ? "bg-success/10 text-success border border-success/20"
                              : "bg-muted text-muted-foreground border border-border"
                          }`}>{company.status}</span>
                        </div>
                        <p className="text-xs text-muted-foreground mb-2">{company.email}</p>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">ID</span>
                          <CopyId id={company.id} />
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-0.5">LLM</p>
                        <p className="text-xs font-mono text-foreground">{company.llm_model}</p>
                        {company.created_at && (
                          <p className="text-[11px] text-muted-foreground mt-1">
                            Created {formatDate(company.created_at)}
                          </p>
                        )}
                        <div className="flex items-center gap-1.5 mt-2 justify-end flex-wrap">
                          {company.status === "suspended" ? (
                            <Button
                              size="sm" variant="outline"
                              onClick={() => setStatusTarget({ company, next: "active" })}
                              className="border-success/40 text-success hover:bg-success/10 hover:text-success"
                              data-testid={`activate-tenant-${company.id}`}
                              title="Re-activate this tenant"
                            >
                              <Unlock className="w-3 h-3 mr-1" /> Activate
                            </Button>
                          ) : (
                            <Button
                              size="sm" variant="outline"
                              onClick={() => setStatusTarget({ company, next: "suspended" })}
                              className="border-destructive/30 text-destructive hover:bg-destructive/10 hover:text-destructive"
                              data-testid={`suspend-tenant-${company.id}`}
                              title="Suspend this tenant — bot will stop responding"
                            >
                              <Ban className="w-3 h-3 mr-1" /> Suspend
                            </Button>
                          )}
                          <Button
                            size="sm" variant="outline"
                            onClick={() => setModelsForCompany(company)}
                            data-testid={`manage-models-${company.id}`}
                            title="Assign LLM models to this tenant"
                          >
                            <Cpu className="w-3 h-3 mr-1" /> Models
                          </Button>
                          <Button
                            size="sm" variant="outline"
                            onClick={() => setAdminsForCompany(company)}
                            data-testid={`manage-admins-${company.id}`}
                          >
                            <UserPlus className="w-3 h-3 mr-1" /> Admins
                          </Button>
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          </>
        )}

        {/* ── Per-tab content. Headers and wrappers come from AdminShell now;
            each tab just renders its own component. ── */}
        {activeTab === "conversations"     && <ConversationsTab     companies={companies} token={token} />}
        {activeTab === "audit-logs"        && <AuditLogsTab         companies={companies} token={token} />}
        {activeTab === "seva-applications" && <SevaApplicationsTab  token={token} companies={companies} />}
        {activeTab === "knowledge" && (
          <div className="space-y-6">
            <KnowledgeBasePanel token={token} crossTenant companies={companies} />
            <BlockedKeywordsPanel token={token} />
          </div>
        )}
        {activeTab === "tenant-services"   && <TenantServicesTab    companies={companies} token={token} />}
        {activeTab === "channel-mappings"  && <ChannelMappingsTab   companies={companies} token={token} />}
        {activeTab === "bot-config"        && <BotConfigTab         companies={companies} token={token} />}
        {activeTab === "scrapers"          && <ScrapersTab          companies={companies} token={token} />}
        {activeTab === "notifications"     && <NotificationsTab     token={token} />}
        {activeTab === "platform-settings" && <PlatformSettingsTab  token={token} />}
        {activeTab === "llm-cost"          && <LlmUsageTab          token={token} companies={companies} />}
        {activeTab === "models"            && <ModelsTab            token={token} />}

      {/* Sprint 11 — admins manager modal */}
      {adminsForCompany && (
        <AdminsModal
          company={adminsForCompany}
          token={token}
          onClose={() => setAdminsForCompany(null)}
        />
      )}

      {/* Sprint 14 — per-tenant model assignment */}
      {modelsForCompany && (
        <ModelAssignmentModal
          company={modelsForCompany}
          token={token}
          onClose={() => setModelsForCompany(null)}
          onSaved={() => { setModelsForCompany(null); fetchData(); }}
        />
      )}

      {/* Suspend / Activate confirmation. The suspended-tenant boundary
          lives in `tenant.get_tenant_id`, which rejects requests with a
          400 — the bot effectively goes dark without any host-page
          changes. Cache TTL there is 60s, but the route invalidates the
          cache so the change is immediate. */}
      <ConfirmDialog
        open={!!statusTarget}
        onOpenChange={(o) => !o && setStatusTarget(null)}
        title={statusTarget?.next === "suspended" ? "Suspend this tenant?" : "Re-activate this tenant?"}
        description={
          statusTarget?.next === "suspended"
            ? `${statusTarget?.company?.name || "This tenant"} will stop responding immediately. The widget will fail-closed (400 from /widget-config) and any open chat sessions will be rejected on their next message. Existing data is preserved — re-activate at any time to resume service.`
            : `${statusTarget?.company?.name || "This tenant"} will start responding again. The widget will pick up the change on the next page load, and any visitors who hit the embed will be served normally.`
        }
        confirmLabel={statusTarget?.next === "suspended" ? "Suspend tenant" : "Activate tenant"}
        destructive={statusTarget?.next === "suspended"}
        loading={statusSaving}
        onConfirm={async () => {
          if (!statusTarget) return;
          setStatusSaving(true);
          try {
            const res = await fetch(`${API}/super-admin/companies/${statusTarget.company.id}/status`, {
              method: "PUT",
              headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
              body: JSON.stringify({ status: statusTarget.next }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Failed");
            toast.success(
              statusTarget.next === "suspended"
                ? `${statusTarget.company.name} suspended — bot is now offline for this tenant.`
                : `${statusTarget.company.name} re-activated.`,
            );
            setStatusTarget(null);
            fetchData();
          } catch (err) {
            toast.error(err.message);
          } finally {
            setStatusSaving(false);
          }
        }}
      />
    </AdminShell>
  );
}

/* ─── Sprint 11 — Admins manager modal ─────────────────────────────────── */

function AdminsModal({ company, token, onClose }) {
  // The modal manages two parallel collections — local_admins (full
  // access) and local_viewers (read-only). They share the same CRUD
  // shape, so a `kind` switch picks the right backend collection and
  // the rest of the UI stays identical.
  const [kind, setKind] = useState("admins"); // "admins" | "viewers"
  const isViewers = kind === "viewers";
  const collectionLabel  = isViewers ? "viewer"  : "admin";
  const collectionLabelP = isViewers ? "viewers" : "admins";
  const endpointSegment  = isViewers ? "viewers" : "admins";

  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newPass, setNewPass]   = useState("");
  const [resetting, setResetting] = useState(null); // row when reset prompt open
  const [resetPass, setResetPass] = useState("");
  const [confirmDeleteRow, setConfirmDeleteRow] = useState(null);
  const [deletingRow, setDeletingRow] = useState(false);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/super-admin/companies/${company.id}/${endpointSegment}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      setRows(data[endpointSegment] || []);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [company.id, token, endpointSegment]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (newPass.length < 8) { toast.error("Initial password must be at least 8 characters"); return; }
    setAdding(true);
    try {
      const res = await fetch(`${API}/super-admin/companies/${company.id}/${endpointSegment}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ email: newEmail.trim(), initial_password: newPass }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      toast.success(`Added ${data.email}. They'll be forced to set a new password on first login.`);
      setNewEmail(""); setNewPass("");
      fetchRows();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = (row) => setConfirmDeleteRow(row);
  const handleDeleteConfirmed = async () => {
    if (!confirmDeleteRow) return;
    setDeletingRow(true);
    try {
      const res = await fetch(`${API}/super-admin/companies/${company.id}/${endpointSegment}/${confirmDeleteRow.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed");
      toast.success(`${collectionLabel[0].toUpperCase()}${collectionLabel.slice(1)} removed`);
      setConfirmDeleteRow(null);
      fetchRows();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setDeletingRow(false);
    }
  };

  const handleReset = async () => {
    if (resetPass.length < 8) { toast.error("New password must be at least 8 characters"); return; }
    try {
      const res = await fetch(`${API}/super-admin/companies/${company.id}/${endpointSegment}/${resetting.id}/reset-password`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: resetPass }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      toast.success(`Password reset for ${resetting.email}. They'll be forced to change it on next login.`);
      setResetting(null); setResetPass("");
      fetchRows();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <>
      <Dialog open onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Tenant access — {company.name}</DialogTitle>
            <p className="text-xs text-muted-foreground">Tenant <code className="font-mono">{company.id.slice(0, 8)}…</code></p>
          </DialogHeader>

          {/* Role switch — Admins have full read/write, viewers are
              read-only (backend rejects POST/PUT/PATCH/DELETE from
              viewer tokens at `auth_utils.verify_admin`). */}
          <div className="flex gap-1 border-b border-border -mx-6 px-6">
            {[
              { key: "admins",  label: "Admins" },
              { key: "viewers", label: "Viewers (read-only)" },
            ].map((opt) => {
              const active = kind === opt.key;
              return (
                <button
                  key={opt.key}
                  type="button"
                  onClick={() => { setKind(opt.key); setNewEmail(""); setNewPass(""); }}
                  className={cn(
                    "px-3 py-2 text-sm whitespace-nowrap border-b-2 -mb-px transition-colors",
                    active
                      ? "border-foreground text-foreground font-medium"
                      : "border-transparent text-muted-foreground hover:text-foreground",
                  )}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>

          {loading ? (
            <div className="text-center text-muted-foreground py-4 text-sm">Loading…</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-left text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">Email</th>
                  <th className="px-3 py-2 font-medium">Created</th>
                  <th className="px-3 py-2 font-medium">Reset?</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <td className="px-3 py-2 font-mono text-xs">{r.email}</td>
                    <td className="px-3 py-2 text-xs text-muted-foreground">{(r.created_at || "").slice(0, 10)}</td>
                    <td className="px-3 py-2 text-xs">
                      {r.password_change_required ? <span className="text-warning">forced change pending</span> : "—"}
                    </td>
                    <td className="px-3 py-2 text-right space-x-1">
                      <Button size="sm" variant="ghost" onClick={() => { setResetting(r); setResetPass(""); }}>
                        <KeyRound className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleDelete(r)}
                        // Last-admin guard — viewers have no such rule
                        // (a tenant can have zero viewers).
                        disabled={!isViewers && rows.length <= 1}
                      >
                        <Trash2 className="w-3.5 h-3.5 text-destructive" />
                      </Button>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={4} className="text-center py-4 text-muted-foreground text-sm">
                    No {collectionLabelP} yet
                  </td></tr>
                )}
              </tbody>
            </table>
          )}

          {/* Add form */}
          <form onSubmit={handleAdd} className="border-t border-border pt-4 space-y-3">
            <div className="text-sm font-medium text-foreground">
              Add {collectionLabel}
              {isViewers && (
                <span className="ml-2 text-xs text-muted-foreground font-normal">read-only access</span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Email</Label>
                <Input value={newEmail} onChange={(e) => setNewEmail(e.target.value)}
                       type="email" required placeholder={`${collectionLabel}@example.com`} className="mt-1" />
              </div>
              <div>
                <Label className="text-xs">Initial password (≥8 chars)</Label>
                <Input value={newPass} onChange={(e) => setNewPass(e.target.value)}
                       type="text" required placeholder="They'll be forced to change it" className="mt-1" />
              </div>
            </div>
            <Button type="submit" disabled={adding}>
              <UserPlus className="w-4 h-4 mr-2" /> {adding ? "Adding…" : `Add ${collectionLabel}`}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Reset password sub-dialog */}
      <Dialog open={!!resetting} onOpenChange={(o) => !o && setResetting(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Reset password</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Set a new bootstrap password for <strong className="text-foreground">{resetting?.email}</strong>. They'll be forced
            to change it on next login.
          </p>
          <Input
            value={resetPass}
            onChange={(e) => setResetPass(e.target.value)}
            placeholder="New password (≥8 chars)"
            type="text"
          />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setResetting(null)}>Cancel</Button>
            <Button onClick={handleReset}>Reset password</Button>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!confirmDeleteRow}
        onOpenChange={(o) => !o && setConfirmDeleteRow(null)}
        title={`Remove ${collectionLabel}?`}
        description={confirmDeleteRow && `${confirmDeleteRow.email} will lose access to this tenant immediately. Their JWT will be rejected on the next request.`}
        confirmLabel={`Remove ${collectionLabel}`}
        destructive
        loading={deletingRow}
        onConfirm={handleDeleteConfirmed}
      />
    </>
  );
}

/* ─── Sprint 14 — per-tenant model assignment modal ───────────────────── */

function ModelAssignmentModal({ company, token, onClose, onSaved }) {
  const [allModels, setAllModels] = useState([]);   // platform_models (enabled only)
  const [allowed, setAllowed] = useState([]);       // current allowlist
  const [defaultKey, setDefaultKey] = useState(""); // current default
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [modelsRes, assignRes] = await Promise.all([
          fetch(`${API}/super-admin/models`, { headers: { Authorization: `Bearer ${token}` } }),
          fetch(`${API}/super-admin/companies/${company.id}/models`, { headers: { Authorization: `Bearer ${token}` } }),
        ]);
        const modelsBody = await modelsRes.json();
        const assignBody = await assignRes.json();
        if (!modelsRes.ok) throw new Error(modelsBody.detail || "Failed to load models");
        if (!assignRes.ok) throw new Error(assignBody.detail || "Failed to load assignment");
        if (cancelled) return;
        // Only enabled models can be newly assigned; show disabled rows
        // in the list with a muted hint so the operator knows why they
        // can't pick them.
        setAllModels(modelsBody.models || []);
        setAllowed(assignBody.allowed || []);
        setDefaultKey(assignBody.default || "");
      } catch (err) {
        toast.error(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [company.id, token]);

  const toggleAllowed = (key) => {
    setAllowed((prev) => {
      const set = new Set(prev);
      if (set.has(key)) {
        set.delete(key);
        // If we removed the current default, clear it so the operator
        // re-picks before save — the backend rejects mismatches anyway.
        if (defaultKey === key) setDefaultKey("");
      } else {
        set.add(key);
        if (!defaultKey) setDefaultKey(key);
      }
      return Array.from(set);
    });
  };

  const handleSave = async () => {
    if (allowed.length === 0) { toast.error("Pick at least one model"); return; }
    if (!defaultKey || !allowed.includes(defaultKey)) {
      toast.error("Pick a default from the allowed list"); return;
    }
    setSaving(true);
    try {
      const res = await fetch(`${API}/super-admin/companies/${company.id}/models`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ allowed, default: defaultKey }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Save failed");
      toast.success(`Models updated · ${allowed.length} allowed · default ${defaultKey}`);
      // The default flowing through here is what the company-list row
      // shows under "LLM". Trigger the parent's refresh so the row
      // reflects the new default immediately, not on next page load.
      if (onSaved) onSaved();
      else onClose();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Models — {company.name}</DialogTitle>
          <p className="text-xs text-muted-foreground">
            Pick which models this tenant can use. The default is what the chat
            path picks when no model is explicitly requested. Disabled platform
            models can't be newly assigned.
          </p>
        </DialogHeader>

        {loading ? (
          <p className="text-sm text-muted-foreground text-center py-8">Loading…</p>
        ) : allModels.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">
            No models registered yet. Add one from the Models tab first.
          </p>
        ) : (
          <ul className="space-y-2">
            {allModels.map((m) => {
              const isAllowed = allowed.includes(m.key);
              const isDefault = defaultKey === m.key;
              const isDisabled = !m.enabled && !isAllowed;
              return (
                <li
                  key={m.key}
                  className={cn(
                    "rounded-lg border px-3 py-2 flex items-center gap-3",
                    isAllowed ? "border-primary/30 bg-primary/5" : "border-border bg-card",
                    isDisabled && "opacity-50",
                  )}
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-primary shrink-0"
                    checked={isAllowed}
                    disabled={isDisabled}
                    onChange={() => toggleAllowed(m.key)}
                    aria-label={`Allow ${m.key} for ${company.name}`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-foreground truncate">{m.display_name || m.key}</span>
                      <Badge variant="outline" className="text-[10px] uppercase tracking-wider">{m.provider}</Badge>
                      {!m.enabled && (
                        <span className="text-[10px] text-muted-foreground uppercase tracking-wider">Disabled</span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground font-mono">{m.key}</div>
                    {m.pricing && (
                      <div className="text-[11px] text-muted-foreground mt-0.5">
                        In ${Number(m.pricing.input_per_1m_usd).toFixed(2)} · Out ${Number(m.pricing.output_per_1m_usd).toFixed(2)} per 1M tokens
                      </div>
                    )}
                  </div>
                  <label className="flex items-center gap-1.5 text-xs shrink-0 cursor-pointer">
                    <input
                      type="radio"
                      name="default-model"
                      checked={isDefault}
                      disabled={!isAllowed}
                      onChange={() => setDefaultKey(m.key)}
                      className="accent-primary"
                    />
                    <span className={isDefault ? "text-primary font-medium" : "text-muted-foreground"}>
                      Default
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}

        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving || loading || !allowed.length || !defaultKey}>
            {saving ? "Saving…" : "Save assignment"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
