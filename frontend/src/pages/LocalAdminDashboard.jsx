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
  Upload, Clock, AlertCircle, Calendar, Code, Copy, Sparkles, DollarSign,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

import TenantServicesTab from "./super-admin/TenantServicesTab";
import BotConfigTab from "./super-admin/BotConfigTab";
import ScrapersTab from "./super-admin/ScrapersTab";
import LlmUsageTab from "./super-admin/LlmUsageTab";
import AdminShell from "@/components/AdminShell";
import { Section } from "@/components/admin/Section";
import { StatCard } from "@/components/admin/StatCard";
import KnowledgeBasePanel from "@/components/admin/KnowledgeBasePanel";
import { ConversationsTab, AuditLogsTab, SevaApplicationsTab } from "./SuperAdminDashboard";
import { OnboardingCard } from "@/components/admin/OnboardingCard";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Mirrors SuperAdminDashboard's grouped TABS so role-switching feels
// like the same product. Local admin gets fewer items (no platform
// settings, no channel mappings — those are super-admin only).
const TABS = [
  { key: "dashboard",         label: "Overview",        icon: TrendingUp,    group: "Overview" },
  { key: "conversations",     label: "Conversations",   icon: MessageSquare, group: "Activity" },
  { key: "audit-logs",        label: "Audit logs",      icon: Shield,        group: "Activity" },
  { key: "seva-applications", label: "Applications",    icon: Files,         group: "Activity" },
  { key: "llm-cost",          label: "LLM cost",        icon: DollarSign,    group: "Activity" },
  { key: "tenant-services",   label: "Services",        icon: Workflow,      group: "Content" },
  { key: "knowledge",         label: "Knowledge base",  icon: BookOpen,      group: "Content" },
  { key: "bot-config",        label: "Bot config",      icon: Bot,           group: "Configuration" },
  { key: "scrapers",          label: "Scrapers",        icon: Globe,         group: "Configuration" },
];

export default function LocalAdminDashboard() {
  const navigate = useNavigate();
  const [token]      = useState(localStorage.getItem("token"));
  const [companyId]  = useState(localStorage.getItem("company_id"));
  const [company, setCompany] = useState(null);
  const [adminEmail, setAdminEmail] = useState("");
  const [activeTab, setActiveTab] = useState("dashboard");
  const [dashboardStats, setDashboardStats] = useState(null);
  const [onboarding, setOnboarding] = useState(null);

  // Dismissal is per-tenant: a super-admin who supports multiple tenants
  // from one browser shouldn't have one tenant's dismissal hide the guide
  // on a tenant that still needs setup.
  const dismissKey = companyId ? `onboarding_dismissed_${companyId}` : null;
  const [dismissed, setDismissed] = useState(() => {
    try { return dismissKey ? localStorage.getItem(dismissKey) === "1" : false; }
    catch { return false; }
  });
  const [guideDialogOpen, setGuideDialogOpen] = useState(false);

  // Auth guard — if no token or wrong role, kick back to login. Viewers
  // share this surface with local_admins (read-only — the shell badge
  // and backend gating in `verify_admin` handle the distinction).
  const userType = localStorage.getItem("user_type");
  const isViewer = userType === "viewer";
  useEffect(() => {
    if (!token || !["local_admin", "viewer"].includes(userType) || !companyId) {
      navigate("/login");
    }
  }, [token, companyId, navigate, userType]);

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
      setAdminEmail(data.admin_email || "");
      setDashboardStats({
        sessions_today: data.sessions_today,
        total_documents: data.total_documents,
      });
      setOnboarding(data.onboarding || null);
    } catch (err) {
      toast.error(err.message);
    }
  }, [token, companyId]);

  useEffect(() => { fetchTenant(); }, [fetchTenant]);

  const dismissOnboarding = () => {
    setDismissed(true);
    try { if (dismissKey) localStorage.setItem(dismissKey, "1"); } catch { /* ignore */ }
  };

  // Compute the three onboarding steps from backend signals. Centralised
  // so the inline card on Overview and the dialog re-opened from the top
  // bar always show the same state.
  const onboardingSteps = onboarding
    ? [
        {
          key: "bot-config",
          title: "Configure your bot",
          description: "Name, branding, languages, and contact details.",
          done: onboarding.has_bot_config,
          onAction: () => { setGuideDialogOpen(false); setActiveTab("bot-config"); },
        },
        {
          key: "services",
          title: "Add a service",
          description: "Define an application flow your bot can guide users through.",
          done: (onboarding.services_count || 0) > 0,
          onAction: () => { setGuideDialogOpen(false); setActiveTab("tenant-services"); },
        },
        {
          key: "embed",
          title: "Embed the widget",
          description: "Copy the snippet below and paste it on your website.",
          done: !!onboarding.has_sessions,
          onAction: () => {
            setGuideDialogOpen(false);
            setActiveTab("dashboard");
            // Defer scroll until after the tab transition renders.
            setTimeout(() => {
              document.getElementById("embed-snippet")?.scrollIntoView({ behavior: "smooth", block: "center" });
            }, 100);
          },
        },
      ]
    : [];

  // The inline guide on Overview only renders if (a) the tenant hasn't
  // dismissed it AND (b) at least one step is still incomplete. Once
  // everything's done we hide it automatically — the persistent top-bar
  // launcher is the way back in if they want a victory lap.
  const allDone = onboardingSteps.length > 0 && onboardingSteps.every((s) => s.done);
  const showInlineGuide = !dismissed && onboardingSteps.length > 0 && !allDone;

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

  // The JWT doesn't carry the admin's email (only user_id), so we read it
  // from the /local-admin/dashboard response. Shows as a brief "Signed in"
  // fallback until that call returns.
  const userEmail = adminEmail;

  // Per-tab page-level headers — keeps the shell generic and pulls the
  // human-readable title close to the content it labels.
  const PAGE_META = {
    "dashboard":         { title: "Overview",        description: "Your tenant's bot activity and embed snippet." },
    "conversations":     { title: "Conversations",   description: "User conversations from chat, WhatsApp, and Facebook channels." },
    "audit-logs":        { title: "Audit logs",      description: "Authentication, admin actions, and data-access events." },
    "seva-applications": { title: "Applications",    description: "Submitted applications and their PDFs." },
    "llm-cost":          { title: "LLM cost",        description: "Per-day token spend with budget tracking and projections." },
    "knowledge":         { title: "Knowledge base",  description: "Q&A entries and PDF uploads the bot draws from." },
    "tenant-services":   { title: "Services",        description: "The catalogue of services your bot offers." },
    "bot-config":        { title: "Bot configuration", description: "Identity, branding, languages, contact, and security." },
    "scrapers":          { title: "Scrapers",        description: "Site crawler for keeping the knowledge base fresh." },
  };
  const meta = PAGE_META[activeTab] || {};

  return (
    <AdminShell
      title="Tenant Admin"
      tabs={TABS}
      activeTab={activeTab}
      onTabChange={setActiveTab}
      user={{
        email: userEmail,
        type: userType || "local_admin",
        company_name: company?.name,
      }}
      readOnly={isViewer}
      onLogout={handleLogout}
      pageTitle={meta.title}
      pageDescription={meta.description}
      pageActions={
        activeTab === "dashboard" ? (
          <Button variant="outline" size="sm" onClick={fetchTenant}>
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Refresh
          </Button>
        ) : undefined
      }
      topBarSlot={
        onboardingSteps.length > 0 ? (
          <button
            type="button"
            onClick={() => setGuideDialogOpen(true)}
            className="hidden sm:inline-flex items-center gap-2 h-8 px-2.5 rounded-md border border-border bg-card text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
            aria-label="Open setup guide"
            title="Setup guide"
          >
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            <span>Setup guide</span>
            {!allDone && (
              <span className="ml-1 inline-flex items-center justify-center h-4 min-w-[16px] px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-semibold leading-none">
                {onboardingSteps.filter((s) => !s.done).length}
              </span>
            )}
          </button>
        ) : null
      }
    >
      {activeTab === "dashboard" && (
        <>
          {showInlineGuide && (
            <div className="mb-6">
              <OnboardingCard
                steps={onboardingSteps}
                onDismiss={dismissOnboarding}
              />
            </div>
          )}
          <DashboardOverview company={company} stats={dashboardStats} />
        </>
      )}
      {activeTab === "conversations" && <ConversationsTab token={token} singleTenant />}
      {activeTab === "audit-logs" && <AuditLogsTab token={token} singleTenant />}
      {activeTab === "seva-applications" && <SevaApplicationsTab token={token} singleTenant companyId={companyId} />}
      {activeTab === "llm-cost" && <LlmUsageTab token={token} />}
      {activeTab === "knowledge" && <KnowledgeBasePanel token={token} crossTenant={false} companyId={companyId} />}
      {activeTab === "tenant-services" && <TenantServicesTab companies={companies} token={token} singleTenant />}
      {activeTab === "bot-config" && <BotConfigTab companies={companies} token={token} singleTenant />}
      {activeTab === "scrapers" && <ScrapersTab companies={companies} token={token} singleTenant />}

      {/* "Setup guide" can be re-opened anytime from the top bar, even
          after dismissal. Renders the same OnboardingCard inside a Dialog
          using the `compact` variant so the modal supplies its own framing. */}
      <Dialog open={guideDialogOpen} onOpenChange={setGuideDialogOpen}>
        <DialogContent className="max-w-lg p-0 overflow-hidden">
          <DialogTitle className="sr-only">Setup guide</DialogTitle>
          {onboardingSteps.length > 0 && (
            <OnboardingCard steps={onboardingSteps} compact />
          )}
        </DialogContent>
      </Dialog>
    </AdminShell>
  );
}


/* ─────────────────────────────────────────────────────────────────────────── */
/*  Dashboard overview — tenant-scoped stats card                              */
/* ─────────────────────────────────────────────────────────────────────────── */

function DashboardOverview({ company, stats }) {
  return (
    <div className="space-y-6">
      {company && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatCard icon={MessageSquare} label="Sessions today"   value={stats?.sessions_today ?? "—"} />
          <StatCard icon={FileText}      label="Total documents"  value={stats?.total_documents ?? "—"} />
          <StatCard icon={Users}         label="Status"           value={company.status || "active"} valueClass="capitalize" />
        </div>
      )}

      {company && (
        <Section title="Tenant details">
          <dl className="grid grid-cols-[160px_1fr] gap-y-3 text-sm">
            <dt className="text-muted-foreground">Name</dt>
            <dd className="text-foreground">{company.name}</dd>
            <dt className="text-muted-foreground">Company ID</dt>
            <dd><code className="text-xs font-mono text-foreground">{company.id}</code></dd>
            <dt className="text-muted-foreground">Email</dt>
            <dd className="text-foreground">{company.email || "—"}</dd>
            <dt className="text-muted-foreground">LLM model</dt>
            <dd><Badge variant="secondary">{company.llm_model || "—"}</Badge></dd>
            <dt className="text-muted-foreground">Created</dt>
            <dd className="text-xs text-foreground">{(company.created_at || "").replace("T", " ").slice(0, 19)}</dd>
          </dl>
        </Section>
      )}

      {company && <EmbedSnippetCard companyId={company.id} />}
    </div>
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
    <Section
      // The id is the scroll target for the Onboarding step "Embed the widget".
      className="scroll-mt-24"
      title={
        <span id="embed-snippet" className="flex items-center gap-2">
          <Code className="w-4 h-4 text-primary" />
          Embed on your website
        </span>
      }
      description="Paste this just before the closing </body> tag on every page where you want the chatbot to appear. The data-company-id attribute is what routes traffic to your tenant."
      actions={
        <Button size="sm" variant="outline" onClick={handleCopy}>
          <Copy className="w-4 h-4 mr-1.5" /> Copy
        </Button>
      }
    >
      <pre className="bg-foreground text-background rounded-lg p-4 text-xs leading-relaxed overflow-x-auto font-mono">
{snippet}
      </pre>
      <p className="text-[11px] text-muted-foreground mt-2 leading-snug">
        Hosting the widget on a CDN? Replace the <code>src</code> URL with your CDN path —
        the <code>data-company-id</code> attribute is what links it to this tenant.
      </p>
    </Section>
  );
}
