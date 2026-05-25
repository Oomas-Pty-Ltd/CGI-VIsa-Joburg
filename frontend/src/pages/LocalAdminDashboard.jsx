/**
 * Local admin console (Sprint 9).
 *
 * Same tab framework as SuperAdminDashboard, scoped to one tenant. All
 * tabs talk to the existing super-admin endpoints — the backend's
 * `verify_admin` + `enforce_tenant_scope` (Sprint 8) accept a
 * local-admin JWT and force every query to the JWT's company_id, so
 * the UI doesn't have to thread the scope explicitly.
 *
 * Hidden from local admin: Channels (infra routing), Companies CRUD.
 */
import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  TrendingUp, MessageSquare, Shield, BookOpen, Files,
  Workflow, Bot, Globe, LogOut, RefreshCw, Building2, Users, FileText,
  Upload, Clock, AlertCircle, Calendar, Code, Copy,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

import TenantServicesTab from "./super-admin/TenantServicesTab";
import BotConfigTab from "./super-admin/BotConfigTab";
import ScrapersTab from "./super-admin/ScrapersTab";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TABS = [
  { key: "dashboard",         label: "Dashboard",       icon: TrendingUp },
  { key: "conversations",     label: "Conversations",   icon: MessageSquare },
  { key: "audit-logs",        label: "Audit Logs",      icon: Shield },
  { key: "seva-applications", label: "Applications",    icon: Files },
  { key: "knowledge",         label: "Knowledge Base",  icon: BookOpen },
  { key: "tenant-services",   label: "Services",        icon: Workflow },
  { key: "bot-config",        label: "Bot Config",      icon: Bot },
  { key: "scrapers",          label: "Scrapers",        icon: Globe },
];

export default function LocalAdminDashboard() {
  const navigate = useNavigate();
  const [token]      = useState(localStorage.getItem("token"));
  const [companyId]  = useState(localStorage.getItem("company_id"));
  const [company, setCompany] = useState(null);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [dashboardStats, setDashboardStats] = useState(null);

  // Auth guard — if no token or wrong role, kick back to login
  useEffect(() => {
    const userType = localStorage.getItem("user_type");
    if (!token || userType !== "local_admin" || !companyId) {
      navigate("/login");
    }
  }, [token, companyId, navigate]);

  // Fetch company + tenant dashboard stats
  const fetchTenant = useCallback(async () => {
    if (!token || !companyId) return;
    try {
      const res = await fetch(`${API}/local-admin/dashboard`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to load tenant info");
      const data = await res.json();
      setCompany(data.company);
      setDashboardStats({
        sessions_today: data.sessions_today,
        total_documents: data.total_documents,
      });
    } catch (err) {
      toast.error(err.message);
    }
  }, [token, companyId]);

  useEffect(() => { fetchTenant(); }, [fetchTenant]);

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user_type");
    localStorage.removeItem("user_id");
    localStorage.removeItem("company_id");
    navigate("/login");
  };

  // Pass-through prop for tabs that expect a `companies` list — for local
  // admin it's just a single-entry list of their own tenant.
  const companies = company ? [company] : [];

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="w-64 bg-[#1A2E40] text-white flex flex-col">
        <div className="p-6 border-b border-white/10">
          <div className="flex items-center gap-2 mb-1">
            <Building2 className="w-7 h-7 text-[#E06F2C]" />
            <div className="text-lg font-bold">Tenant Admin</div>
          </div>
          {company && (
            <div className="text-xs text-white/60 truncate" title={company.name}>
              {company.name}
            </div>
          )}
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {TABS.map(({ key, label, icon: Icon }) => (
            <Button
              key={key}
              variant="ghost"
              onClick={() => setActiveTab(key)}
              className={`w-full justify-start text-white hover:bg-white/10 ${activeTab === key ? "bg-white/20" : ""}`}
              data-testid={`tab-${key}`}
            >
              <Icon className="w-4 h-4 mr-2" />
              {label}
            </Button>
          ))}
        </nav>

        <div className="p-3 border-t border-white/10">
          <Button
            variant="ghost"
            onClick={handleLogout}
            className="w-full justify-start text-white hover:bg-white/10"
          >
            <LogOut className="w-4 h-4 mr-2" />
            Logout
          </Button>
        </div>
      </aside>

      {/* Main area */}
      <div className="flex-1 p-8 overflow-x-auto">
        {activeTab === "dashboard" && (
          <DashboardOverview company={company} stats={dashboardStats} onRefresh={fetchTenant} />
        )}

        {activeTab === "conversations" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Conversations</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <ConversationsTab token={token} />
            </div>
          </>
        )}

        {activeTab === "audit-logs" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Audit Logs</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <AuditLogsTab token={token} />
            </div>
          </>
        )}

        {activeTab === "seva-applications" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Seva Applications</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <ApplicationsTab token={token} companyId={companyId} />
            </div>
          </>
        )}

        {activeTab === "knowledge" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Knowledge Base</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <KnowledgeTab token={token} companyId={companyId} />
            </div>
          </>
        )}

        {activeTab === "tenant-services" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Services</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <TenantServicesTab companies={companies} token={token} singleTenant />
            </div>
          </>
        )}

        {activeTab === "bot-config" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Bot Config</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <BotConfigTab companies={companies} token={token} singleTenant />
            </div>
          </>
        )}

        {activeTab === "scrapers" && (
          <>
            <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Scrapers</h1>
            <div className="bg-white rounded-xl shadow-md p-6">
              <ScrapersTab companies={companies} token={token} singleTenant />
            </div>
          </>
        )}
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────────────────────────────── */
/*  Dashboard overview — tenant-scoped stats card                              */
/* ─────────────────────────────────────────────────────────────────────────── */

function DashboardOverview({ company, stats, onRefresh }) {
  return (
    <>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-4xl font-bold text-[#1A2E40]">Dashboard</h1>
        <Button variant="outline" onClick={onRefresh}>
          <RefreshCw className="w-4 h-4 mr-2" /> Refresh
        </Button>
      </div>

      {company && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <StatCard icon={MessageSquare} label="Sessions today"   value={stats?.sessions_today ?? "—"} />
          <StatCard icon={FileText}      label="Total documents"  value={stats?.total_documents ?? "—"} />
          <StatCard icon={Users}         label="Status"           value={company.status || "active"} valueClass="capitalize" />
        </div>
      )}

      {company && (
        <div className="bg-white rounded-xl shadow-md p-6">
          <h2 className="text-lg font-semibold mb-4">Tenant details</h2>
          <div className="grid grid-cols-2 gap-y-3 text-sm">
            <span className="text-slate-500">Name</span>
            <span>{company.name}</span>
            <span className="text-slate-500">Company ID</span>
            <code className="text-xs font-mono text-slate-600">{company.id}</code>
            <span className="text-slate-500">Email</span>
            <span>{company.email || "—"}</span>
            <span className="text-slate-500">LLM model</span>
            <span><Badge variant="secondary">{company.llm_model || "—"}</Badge></span>
            <span className="text-slate-500">Created</span>
            <span className="text-xs text-slate-600">{(company.created_at || "").replace("T", " ").slice(0, 19)}</span>
          </div>
        </div>
      )}

      {company && <EmbedSnippetCard companyId={company.id} />}
    </>
  );
}

function EmbedSnippetCard({ companyId }) {
  // The widget script is served as a static asset from the frontend host.
  // We default to the current origin, which is the right answer when the
  // tenant embeds via the same domain that serves this dashboard. Operators
  // hosting the widget on a CDN can hand-edit the URL when they paste it.
  const widgetSrc = `${window.location.origin}/seva-widget.js`;
  const snippet =
`<!-- Chatbot widget -->
<script src="${widgetSrc}" data-company-id="${companyId}"></script>`;

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(snippet);
      toast.success("Snippet copied to clipboard");
    } catch {
      toast.error("Copy failed — select the text and copy manually");
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-md p-6 mt-6">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <Code className="w-5 h-5 text-[#E06F2C]" />
          <h2 className="text-lg font-semibold">Embed on your website</h2>
        </div>
        <Button size="sm" variant="outline" onClick={handleCopy}>
          <Copy className="w-4 h-4 mr-1.5" /> Copy
        </Button>
      </div>
      <p className="text-xs text-slate-500 mb-3 leading-relaxed">
        Paste this just before the closing <code>&lt;/body&gt;</code> tag on every page
        where you want the chatbot to appear. The script reads
        <code className="mx-1">data-company-id</code> to route every request to your tenant,
        so this is the only thing the host page needs.
      </p>
      <pre className="bg-slate-900 text-slate-100 rounded-lg p-4 text-xs leading-relaxed overflow-x-auto font-mono">
{snippet}
      </pre>
      <p className="text-[11px] text-slate-400 mt-2 leading-snug">
        Hosting the widget on a CDN? Replace the <code>src</code> URL with your CDN path —
        the <code>data-company-id</code> attribute is what links it to this tenant.
      </p>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, valueClass = "" }) {
  return (
    <div className="bg-white rounded-xl shadow-md p-5 flex items-center gap-4">
      <div className="bg-orange-50 p-3 rounded-lg">
        <Icon className="w-6 h-6 text-[#E06F2C]" />
      </div>
      <div>
        <div className="text-xs text-slate-500 uppercase">{label}</div>
        <div className={`text-2xl font-bold text-[#1A2E40] ${valueClass}`}>{value}</div>
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────────────────────────────── */
/*  Conversations — list sessions for own tenant                               */
/* ─────────────────────────────────────────────────────────────────────────── */

function ConversationsTab({ token }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState(null);
  const limit = 50;

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      // The endpoint uses verify_admin + enforce_tenant_scope, so it
      // automatically restricts to this admin's tenant.
      const res = await fetch(`${API}/super-admin/sessions?page=${page}&limit=${limit}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      setRows(data.sessions || []);
      setTotal(data.total || 0);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, page]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-500">{total} sessions</div>
        <Button variant="outline" size="sm" onClick={fetchRows} disabled={loading}>
          <RefreshCw className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>
      {loading ? (
        <div className="text-center text-slate-400 py-8">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="text-center text-slate-400 py-8">No conversations yet for your tenant.</div>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-3 py-2">Channel</th>
              <th className="px-3 py-2">User</th>
              <th className="px-3 py-2">Messages</th>
              <th className="px-3 py-2">Created</th>
              <th className="px-3 py-2">First message</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className="border-t hover:bg-slate-50">
                <td className="px-3 py-2"><Badge variant="secondary">{s.channel}</Badge></td>
                <td className="px-3 py-2 text-xs font-mono">{s.user_identifier?.slice(0, 18) ?? "—"}</td>
                <td className="px-3 py-2 text-center">{s.message_count}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{(s.created_at || "").slice(0, 16).replace("T", " ")}</td>
                <td className="px-3 py-2 text-xs text-slate-600 truncate max-w-xs">{s.first_message}</td>
                <td className="px-3 py-2 text-right">
                  <Button size="sm" variant="ghost" onClick={() => setDetail(s.id)}>View</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {total > limit && (
        <Pagination page={page} total={total} limit={limit} onChange={setPage} />
      )}
      {detail && <SessionDetailModal token={token} sessionId={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

function SessionDetailModal({ token, sessionId, onClose }) {
  const [session, setSession] = useState(null);
  useEffect(() => {
    fetch(`${API}/super-admin/sessions/${sessionId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setSession)
      .catch(() => toast.error("Failed to load session"));
  }, [sessionId, token]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl max-w-3xl max-h-[80vh] w-full overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-4 py-3 border-b flex items-center justify-between">
          <div>
            <div className="font-semibold">Session detail</div>
            <div className="text-xs text-slate-400 font-mono">{sessionId}</div>
          </div>
          <Button variant="ghost" onClick={onClose}>Close</Button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {!session ? (
            <div className="text-center text-slate-400 py-6">Loading…</div>
          ) : (
            (session.messages || []).map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`rounded-lg px-3 py-2 max-w-md text-sm ${m.role === "user" ? "bg-orange-500 text-white" : "bg-slate-100"}`}>
                  <div className="whitespace-pre-wrap">{m.content}</div>
                  <div className={`text-xs mt-1 ${m.role === "user" ? "text-orange-100" : "text-slate-400"}`}>
                    {m.role} · {(m.timestamp || "").slice(0, 19).replace("T", " ")}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function Pagination({ page, total, limit, onChange }) {
  const pages = Math.ceil(total / limit);
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-500">Page {page} of {pages}</span>
      <div className="space-x-1">
        <Button size="sm" variant="outline" disabled={page === 1} onClick={() => onChange(page - 1)}>Prev</Button>
        <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next</Button>
      </div>
    </div>
  );
}


/* ─────────────────────────────────────────────────────────────────────────── */
/*  Audit Logs — list for own tenant                                           */
/* ─────────────────────────────────────────────────────────────────────────── */

function AuditLogsTab({ token }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const limit = 50;

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/super-admin/audit-logs?page=${page}&limit=${limit}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      setRows(data.logs || []);
      setTotal(data.total || 0);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, page]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-500">{total} audit entries</div>
        <Button variant="outline" size="sm" onClick={fetchRows} disabled={loading}>
          <RefreshCw className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>
      {loading ? (
        <div className="text-center text-slate-400 py-8">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="text-center text-slate-400 py-8">
          No audit entries yet for your tenant. Entries appear as actions are taken.
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-3 py-2">Timestamp</th>
              <th className="px-3 py-2">Category</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">User</th>
              <th className="px-3 py-2">Resource</th>
              <th className="px-3 py-2">OK</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t">
                <td className="px-3 py-2 text-xs text-slate-500">{(r.timestamp || "").slice(0, 19).replace("T", " ")}</td>
                <td className="px-3 py-2"><Badge variant="secondary">{r.category}</Badge></td>
                <td className="px-3 py-2 font-mono text-xs">{r.action}</td>
                <td className="px-3 py-2 text-xs">{r.user_type ? `${r.user_type}` : "—"}</td>
                <td className="px-3 py-2 text-xs">{r.resource_type || ""}{r.resource_id ? `/${r.resource_id.slice(0,8)}` : ""}</td>
                <td className="px-3 py-2">{r.success ? "✓" : "✗"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {total > limit && <Pagination page={page} total={total} limit={limit} onChange={setPage} />}
    </div>
  );
}


/* ─────────────────────────────────────────────────────────────────────────── */
/*  Seva Applications — list for own tenant                                    */
/* ─────────────────────────────────────────────────────────────────────────── */

const APPLICATION_STATUSES = ["created", "submitted", "confirmed"];

function ApplicationsTab({ token, companyId }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [services, setServices] = useState([]);
  const [filters, setFilters] = useState({
    status: "",
    service_type: "",
    search: "",
    from_date: "",
    to_date: "",
    with_documents: false,
  });
  const limit = 50;

  // Load this tenant's services to populate the Service dropdown
  useEffect(() => {
    if (!companyId) return;
    (async () => {
      try {
        const res = await fetch(`${API}/super-admin/services/${companyId}?include_disabled=true`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const data = await res.json();
        if (res.ok) setServices(data.services || []);
      } catch {
        // Service list is a nice-to-have for the filter; ignore failures.
      }
    })();
  }, [companyId, token]);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        limit: String(limit),
        with_documents: String(filters.with_documents),
      });
      if (filters.status)       params.set("status", filters.status);
      if (filters.service_type) params.set("service_type", filters.service_type);
      if (filters.search)       params.set("search", filters.search);
      if (filters.from_date)    params.set("from_date", filters.from_date);
      if (filters.to_date)      params.set("to_date", filters.to_date);

      const res = await fetch(`${API}/super-admin/seva-setu/applications?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      setRows(data.applications || []);
      setTotal(data.total || 0);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [token, page, filters]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  // Any filter change should drop the user back to page 1; otherwise an
  // empty page 5 result looks like "no matches" when really we just need to reset.
  const setFilter = (patch) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  const clearFilters = () => {
    setFilters({ status: "", service_type: "", search: "", from_date: "", to_date: "", with_documents: false });
    setPage(1);
  };

  const hasActiveFilters = Object.entries(filters).some(([k, v]) =>
    k === "with_documents" ? v : Boolean(v)
  );

  return (
    <div className="space-y-3">
      {/* Filter row */}
      <div className="grid grid-cols-1 md:grid-cols-6 gap-2 items-end">
        <div className="md:col-span-2">
          <label className="text-xs text-slate-500 block mb-1">Search reference</label>
          <input
            type="text"
            className="w-full border rounded px-2 py-1.5 text-sm"
            placeholder="e.g. PASS-2024"
            value={filters.search}
            onChange={(e) => setFilter({ search: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs text-slate-500 block mb-1">Status</label>
          <select
            className="w-full border rounded px-2 py-1.5 text-sm bg-white"
            value={filters.status}
            onChange={(e) => setFilter({ status: e.target.value })}
          >
            <option value="">All</option>
            {APPLICATION_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-slate-500 block mb-1">Service</label>
          <select
            className="w-full border rounded px-2 py-1.5 text-sm bg-white"
            value={filters.service_type}
            onChange={(e) => setFilter({ service_type: e.target.value })}
          >
            <option value="">All</option>
            {services.map((s) => (
              <option key={s.service_key} value={s.service_key}>{s.name || s.service_key}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-slate-500 block mb-1">From</label>
          <input
            type="date"
            className="w-full border rounded px-2 py-1.5 text-sm"
            value={filters.from_date}
            onChange={(e) => setFilter({ from_date: e.target.value })}
          />
        </div>
        <div>
          <label className="text-xs text-slate-500 block mb-1">To</label>
          <input
            type="date"
            className="w-full border rounded px-2 py-1.5 text-sm"
            value={filters.to_date}
            onChange={(e) => setFilter({ to_date: e.target.value })}
          />
        </div>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <div className="text-sm text-slate-500">
            {total} application{total === 1 ? "" : "s"}
            {hasActiveFilters && <span className="ml-1 text-xs text-slate-400">(filtered)</span>}
          </div>
          <label className="text-xs text-slate-500 flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={filters.with_documents}
              onChange={(e) => setFilter({ with_documents: e.target.checked })}
            />
            With documents only
          </label>
          {hasActiveFilters && (
            <Button variant="ghost" size="sm" onClick={clearFilters} className="text-xs h-7">
              Clear filters
            </Button>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={fetchRows} disabled={loading}>
          <RefreshCw className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {loading ? (
        <div className="text-center text-slate-400 py-8">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="text-center text-slate-400 py-8">
          {hasActiveFilters
            ? "No applications match these filters."
            : "No applications yet for your tenant."}
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-3 py-2">Reference</th>
              <th className="px-3 py-2">Service</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Documents</th>
              <th className="px-3 py-2">Created</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.id} className="border-t">
                <td className="px-3 py-2 font-mono text-xs">{a.reference_id || a.id.slice(0, 8)}</td>
                <td className="px-3 py-2">{a.service_name || a.service_type}</td>
                <td className="px-3 py-2"><Badge variant="secondary">{a.status}</Badge></td>
                <td className="px-3 py-2 text-center">{a.document_count}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{(a.created_at || "").slice(0, 16).replace("T", " ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {total > limit && <Pagination page={page} total={total} limit={limit} onChange={setPage} />}
    </div>
  );
}


/* ─────────────────────────────────────────────────────────────────────────── */
/*  Knowledge Base — list + create + edit (per-tenant entries via /api/admin)  */
/* ─────────────────────────────────────────────────────────────────────────── */

const KB_EVENT_STATUS_STYLES = {
  past:    { bg: "bg-gray-100 text-gray-600",     icon: Clock,        label: "Past" },
  present: { bg: "bg-green-100 text-green-700",   icon: AlertCircle,  label: "Live" },
  future:  { bg: "bg-blue-100 text-blue-700",     icon: Calendar,     label: "Upcoming" },
  general: { bg: "bg-orange-100 text-orange-700", icon: FileText,     label: "General" },
};

function EventBadge({ status }) {
  const cfg = KB_EVENT_STATUS_STYLES[status] || KB_EVENT_STATUS_STYLES.general;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg}`}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}

function formatDateRange(from, until) {
  if (!from && !until) return "—";
  if (!until || from === until) return from || until;
  return `${from} → ${until}`;
}

const KB_PDF_CATEGORIES = [
  "general", "visa", "passport", "oci", "pcc",
  "fees", "emergency", "services", "event", "announcement", "other",
];

function PdfUploadCard({ token, companyId, onUploaded }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("general");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const pickFile = (f) => {
    if (!f) return;
    if (f.type !== "application/pdf") {
      toast.error("Only PDF files are accepted.");
      return;
    }
    setFile(f);
    if (!title) setTitle(f.name.replace(/\.pdf$/i, "").replace(/_/g, " "));
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) { toast.error("Pick a PDF first."); return; }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("title", title);
      form.append("category", category);
      form.append("company_id", companyId);

      const res = await fetch(`${API}/super-admin/knowledge/upload-pdf`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : "Upload failed";
        toast.error(msg, { duration: 6000 });
        return;
      }
      const ocrNote = data.ocr_used ? " via OCR" : "";
      const modeNote = data.faq_mode ? " as FAQ pairs" : "";
      toast.success(`PDF processed — ${data.sections_created} entries created${modeNote}${ocrNote}.`);
      setFile(null);
      setTitle("");
      setCategory("general");
      if (fileInputRef.current) fileInputRef.current.value = "";
      onUploaded?.();
    } catch (err) {
      toast.error(err.message || "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="rounded-xl bg-white p-5 shadow-sm border">
      <div className="flex items-center gap-2 mb-1">
        <Upload className="h-4 w-4 text-[#E06F2C]" />
        <h2 className="font-semibold text-[#1A2E40]">Upload PDF to Knowledge Base</h2>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        Drop a PDF and it will be split into knowledge entries the bot can search.
        FAQ-style documents are parsed into Q&amp;A pairs; other PDFs are chunked
        by section. Dates in the text are detected and used to mark past/upcoming
        events. Max 50&nbsp;MB.
      </p>

      <form onSubmit={handleUpload} className="space-y-3">
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            pickFile(e.dataTransfer.files?.[0]);
          }}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
            dragOver ? "border-[#E06F2C] bg-orange-50" : "border-slate-300 hover:bg-slate-50"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf"
            onChange={(e) => pickFile(e.target.files?.[0])}
            className="hidden"
          />
          {file ? (
            <div className="text-sm">
              <div className="font-medium text-slate-700">{file.name}</div>
              <div className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB — click or drop another to replace</div>
            </div>
          ) : (
            <div className="text-sm text-slate-500">
              <Upload className="h-5 w-5 mx-auto mb-2 text-slate-400" />
              Click or drop a PDF here
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-slate-500">Document title (optional)</label>
            <input
              type="text"
              className="w-full border rounded p-2 text-sm"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Auto-filled from filename"
            />
            <p className="text-[11px] text-slate-500 mt-1 leading-snug">
              Label shown alongside each generated entry. Leave blank to use the filename.
            </p>
          </div>
          <div>
            <label className="text-xs text-slate-500">Category</label>
            <select
              className="w-full border rounded p-2 text-sm bg-white"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {KB_PDF_CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <p className="text-[11px] text-slate-500 mt-1 leading-snug">
              Topical bucket applied to every entry from this PDF. You can edit it per-entry later.
            </p>
          </div>
        </div>

        <div className="flex justify-end">
          <Button type="submit" disabled={!file || uploading}>
            {uploading ? "Uploading…" : "Upload PDF"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function KnowledgeTab({ token, companyId }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null); // null | row | "new"

  const fetchEntries = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/admin/knowledge?limit=200`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      setEntries(data.entries || []);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);

  return (
    <div className="space-y-4">
      <PdfUploadCard token={token} companyId={companyId} onUploaded={fetchEntries} />

      <div className="flex items-center justify-between">
        <div className="text-sm text-slate-500">{entries.length} entries</div>
        <div className="space-x-2">
          <Button variant="outline" size="sm" onClick={fetchEntries} disabled={loading}>
            <RefreshCw className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button size="sm" onClick={() => setEditing("new")}>+ New entry</Button>
        </div>
      </div>
      {loading ? (
        <div className="text-center text-slate-400 py-8">Loading…</div>
      ) : entries.length === 0 ? (
        <div className="text-center text-slate-400 py-8">
          No knowledge entries yet. Click <strong>New entry</strong> to add one.
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-slate-600">
            <tr>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Category</th>
              <th className="px-3 py-2">Date Status</th>
              <th className="px-3 py-2">Date Range</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Version</th>
              <th className="px-3 py-2">Updated</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.id} className="border-t hover:bg-slate-50">
                <td className="px-3 py-2 font-medium">{e.title}</td>
                <td className="px-3 py-2"><Badge variant="secondary">{e.category}</Badge></td>
                <td className="px-3 py-2"><EventBadge status={e.event_status} /></td>
                <td className="px-3 py-2 text-xs text-slate-500">
                  {formatDateRange((e.valid_from || "").slice(0, 10), (e.valid_until || "").slice(0, 10))}
                </td>
                <td className="px-3 py-2 text-xs">{e.status}</td>
                <td className="px-3 py-2 text-xs">v{e.version}</td>
                <td className="px-3 py-2 text-xs text-slate-500">{(e.updated_at || "").slice(0, 16).replace("T", " ")}</td>
                <td className="px-3 py-2 text-right">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(e)}>Edit</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {editing && (
        <KnowledgeDialog
          token={token}
          companyId={companyId}
          entry={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchEntries(); }}
        />
      )}
    </div>
  );
}

const EVENT_STATUS_OPTIONS = [
  { value: "",        label: "(auto / none)" },
  { value: "general", label: "General — not time-sensitive" },
  { value: "future",  label: "Future — upcoming event" },
  { value: "present", label: "Present — happening now" },
  { value: "past",    label: "Past — archived" },
];

// Backend stores valid_from/valid_until as ISO datetime strings (e.g. from
// PDF parsing). The <input type="date"> control only knows YYYY-MM-DD, so
// trim anything after the date part when populating the form.
const toDateInput = (iso) => (iso || "").slice(0, 10);

function KnowledgeDialog({ token, companyId, entry, onClose, onSaved }) {
  const isNew = !entry;
  const [draft, setDraft] = useState(entry ? {
    ...entry,
    keywords:     (entry.keywords || []).join(", "),
    valid_from:   toDateInput(entry.valid_from),
    valid_until:  toDateInput(entry.valid_until),
    event_status: entry.event_status || "",
  } : {
    category: "general", title: "", question: "", answer: "", keywords: "", source: "",
    valid_from: "", valid_until: "", event_status: "",
  });
  const [saving, setSaving] = useState(false);

  const set = (k, v) => setDraft((d) => ({ ...d, [k]: v }));

  const handleSave = async () => {
    if (!draft.title.trim() || !draft.answer.trim()) {
      toast.error("Title and answer are required"); return;
    }
    if (draft.valid_from && draft.valid_until && draft.valid_from > draft.valid_until) {
      toast.error('"Valid from" cannot be after "valid until".'); return;
    }
    setSaving(true);
    try {
      const keywords = draft.keywords.split(",").map((s) => s.trim()).filter(Boolean);
      const dateBits = {
        valid_from:   draft.valid_from || "",   // empty string clears on update
        valid_until:  draft.valid_until || "",
        event_status: draft.event_status || "",
      };
      let res;
      if (isNew) {
        res = await fetch(`${API}/admin/knowledge?company_id=${companyId}`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({
            category: draft.category, title: draft.title,
            question: draft.question, answer: draft.answer,
            keywords, source: draft.source || "",
            ...dateBits,
          }),
        });
      } else {
        res = await fetch(`${API}/admin/knowledge/${entry.id}`, {
          method: "PUT",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({
            title: draft.title, question: draft.question, answer: draft.answer,
            keywords, source: draft.source || "",
            ...dateBits,
          }),
        });
      }
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Save failed");
      toast.success(isNew ? "Entry created" : "Entry updated");
      onSaved();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl max-w-2xl w-full p-6 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-1">{isNew ? "New knowledge entry" : `Edit: ${entry.title}`}</h3>
        <p className="text-xs text-slate-500 mb-4">
          Knowledge entries are searched at chat time and used as grounding context for the bot's answers.
          Each entry should cover one topic — split long material into multiple entries.
        </p>
        <div className="space-y-3">
          <Field
            label="Title"
            value={draft.title}
            onChange={(v) => set("title", v)}
            hint="Short headline shown in the admin list. Required."
          />
          <Field
            label="Question (FAQ)"
            value={draft.question}
            onChange={(v) => set("question", v)}
            hint="A representative question a user might ask. Helps retrieval match this entry. Optional."
          />
          <div>
            <label className="text-xs text-slate-500">Answer</label>
            <textarea className="w-full border rounded p-2 text-sm" rows={6}
              value={draft.answer} onChange={(e) => set("answer", e.target.value)} />
            <p className="text-[11px] text-slate-500 mt-1 leading-snug">
              The information the bot should use to answer. Write it as you'd want it spoken to the user. Required.
            </p>
          </div>
          <Field
            label="Category"
            value={draft.category}
            onChange={(v) => set("category", v)}
            placeholder="general"
            hint="Topical bucket for filtering and analytics (e.g. fees, hours, eligibility). Free-form."
          />
          <Field
            label="Keywords (comma-separated)"
            value={draft.keywords}
            onChange={(v) => set("keywords", v)}
            placeholder="renewal, fees, eligibility"
            hint="Extra terms that should match this entry during search, beyond what's in the answer."
          />
          <Field
            label="Source URL (optional)"
            value={draft.source || ""}
            onChange={(v) => set("source", v)}
            hint="Where this information came from. Surfaced to users as a citation when available."
          />

          {/* Optional date metadata — for time-bound events or to override
              the bot's automatic recency boost. */}
          <div className="border-t pt-3 mt-2">
            <div className="text-xs font-medium text-slate-700 mb-2">Validity window (optional)</div>
            <p className="text-[11px] text-slate-500 mb-3 leading-snug">
              Set these for events with a clear start/end date, or to override the bot's
              automatic past/future classification. Leave blank for evergreen information.
            </p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-slate-500">Valid from</label>
                <input
                  type="date"
                  className="w-full border rounded p-2 text-sm"
                  value={draft.valid_from || ""}
                  onChange={(e) => set("valid_from", e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-slate-500">Valid until</label>
                <input
                  type="date"
                  className="w-full border rounded p-2 text-sm"
                  value={draft.valid_until || ""}
                  onChange={(e) => set("valid_until", e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-slate-500">Event status</label>
                <select
                  className="w-full border rounded p-2 text-sm bg-white"
                  value={draft.event_status || ""}
                  onChange={(e) => set("event_status", e.target.value)}
                >
                  {EVENT_STATUS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
            </div>
            <p className="text-[11px] text-slate-500 mt-2 leading-snug">
              Search ranks <code>future</code> events highest and <code>past</code> lowest, so an
              upcoming registration deadline outranks a finished one for the same keyword.
            </p>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? "Saving…" : isNew ? "Create" : "Save"}</Button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, hint }) {
  return (
    <div>
      <label className="text-xs text-slate-500">{label}</label>
      <input
        type="text"
        className="w-full border rounded p-2 text-sm"
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      {hint && <p className="text-[11px] text-slate-500 mt-1 leading-snug">{hint}</p>}
    </div>
  );
}
