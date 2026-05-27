/**
 * Super-admin tab — Bot Config (Sprint 3D, redesigned Phase-2 of the admin
 * UX overhaul).
 *
 * Single source of truth for per-tenant `tenant_bot_config`. The tab is
 * structured as a horizontal sub-nav with seven focused pages so the
 * operator doesn't scroll through a flat 12-section form to find one
 * field. All saves go through one ``PUT /super-admin/bot-config/{id}``
 * call; the backend deep-merges nested dicts so editing one nested key
 * doesn't blank the others.
 *
 * If you add a new top-level key to ``services.bot_config.DEFAULT_CONFIG``,
 * surface a UI for it here and include it in the ``buildSaveBody`` payload
 * below — otherwise operators can't edit it.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  RefreshCw, Save, Plus, Trash2, AlertCircle, Circle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Section } from "@/components/admin/Section";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const FALLBACK_KEYS = ["greeting", "out_of_scope", "error", "blocked_input"];
const FALLBACK_HINTS = {
  greeting:      "First message users see when they open the chat.",
  out_of_scope:  "Shown when the user asks about something outside the bot's scope.",
  error:         "Shown when an internal error prevents the bot from replying.",
  blocked_input: "Shown when input is rejected by safety filters (profanity, prompt injection).",
};

const ADVISORY_TYPES = ["info", "warning", "error"];
const FLOW_KEYS = ["apply", "yes", "no", "discard", "continue", "menu", "my_applications"];
const INTENT_CATEGORIES = [
  "service_inquiry", "office_info", "escalation",
  "greeting", "appointment", "status_inquiry",
];

const SUB_TABS = [
  { key: "identity",  label: "Identity & branding" },
  { key: "contact",   label: "Contact" },
  { key: "content",   label: "Content & messages" },
  { key: "knowledge", label: "Knowledge" },
  { key: "behaviour", label: "Behaviour" },
  { key: "pdf",       label: "PDF & exports" },
  { key: "security",  label: "Security" },
];

const EMPTY_CFG = {
  bot_name: "", bot_avatar_url: "",
  org_name: "", org_short_name: "",
  header_tagline: "", footer_copy: "",
  advisories: [],
  features: { voice_input: true, file_upload: true, camera: true },
  contact: {
    address: "", phone: "", emergency_phone: "",
    email: "", website: "", office_hours: "", consular_hours: "",
  },
  phone_country_code: "",
  system_prompt_template: "",
  supported_languages: [{ code: "en", name: "English" }],
  default_language: "en",
  branding: {
    primary_color: "", secondary_color: "",
    logo_url: "", favicon_url: "",
  },
  pdf_branding: {
    header_color: "", accent_color: "", highlight_color: "",
    stripe_colors: [], notice_bg: "", muted_text: "", border: "",
    footer_text: "", notice_text: "",
  },
  knowledge_sources: { primary_url: "", sub_pages: [], secondary_urls: [] },
  knowledge_categories: [],
  ocr_patterns: { passport_regex: "", date_regex: "", name_blocklist: [] },
  security_config: {
    otp_ttl_minutes: 0, otp_max_attempts: 0, otp_lockout_minutes: 0, otp_dev_value: "",
    session_inactivity_minutes: 0, client_inactivity_minutes: 0,
    upload_max_bytes: 0, upload_max_pdf_pages: 0, upload_allowed_mime_types: [],
  },
  intent_keywords: {},
  flow_keywords: { apply: [], yes: [], no: [], discard: [], continue: [], menu: [], my_applications: [] },
  escalation_rules: {
    keywords: [], patterns: [], complaint_keywords: [],
    emergency_keywords: [], emergency_keywords_by_lang: {},
    blocked_patterns: [], priority_responses: {},
    emergency_response_by_lang: {},
    consecutive_failure_threshold: 0,
  },
  fallback_responses: {
    greeting: "", out_of_scope: "", error: "", blocked_input: "",
  },
};

/* ────────────────────────────────────────────────────────────────────── */

export default function BotConfigTab({ companies, token, singleTenant = false }) {
  const [tenantId, setTenantId] = useState("");
  const [cfg, setCfg]           = useState(EMPTY_CFG);
  const [pristine, setPristine] = useState(EMPTY_CFG); // snapshot for dirty-check
  const [activeSub, setActiveSub] = useState("identity");
  const [loading, setLoading]   = useState(false);
  const [saving, setSaving]     = useState(false);
  const [noRow, setNoRow]       = useState(false);

  // The command palette stamps a preferred tenant in localStorage when an
  // operator jumps here from "⌘K → tenant name". We read it once on the
  // first render that has companies populated, then clear the storage so
  // subsequent direct visits default to the first row.
  //
  // The ref is needed because React Strict Mode runs effects twice in dev
  // (mount → cleanup → mount). Without the guard, run 1 clears the value
  // and run 2 sees nothing → falls through to `companies[0]`, defeating
  // the hint. The ref survives the Strict-Mode re-invocation since the
  // fiber isn't actually destroyed.
  const initialTenantAppliedRef = useRef(false);
  useEffect(() => {
    if (initialTenantAppliedRef.current) return;
    if (tenantId || companies.length === 0) return;
    initialTenantAppliedRef.current = true;
    let preferred = "";
    try { preferred = localStorage.getItem("super_admin_preferred_tenant") || ""; } catch { /* ignore */ }
    const match = preferred && companies.find((c) => c.id === preferred);
    setTenantId(match ? preferred : companies[0].id);
    if (preferred) {
      try { localStorage.removeItem("super_admin_preferred_tenant"); } catch { /* ignore */ }
    }
  }, [companies, tenantId]);

  const fetchCfg = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setNoRow(false);
    try {
      const res = await fetch(`${API}/super-admin/bot-config/${tenantId}?soft_404=1`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load");
      if (data.exists === false) {
        setCfg(EMPTY_CFG);
        setPristine(EMPTY_CFG);
        setNoRow(true);
        return;
      }
      const merged = mergeIntoEmpty(data);
      setCfg(merged);
      setPristine(merged);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [tenantId, token]);

  useEffect(() => { fetchCfg(); }, [fetchCfg]);

  // Generic setters — passed down into section components.
  const update              = (patch) => setCfg((c) => ({ ...c, ...patch }));
  const updateContact       = (patch) => setCfg((c) => ({ ...c, contact: { ...c.contact, ...patch } }));
  const updateBranding      = (patch) => setCfg((c) => ({ ...c, branding: { ...c.branding, ...patch } }));
  const updatePdfBranding   = (patch) => setCfg((c) => ({ ...c, pdf_branding: { ...c.pdf_branding, ...patch } }));
  const updateKnowledgeSources = (patch) => setCfg((c) => ({ ...c, knowledge_sources: { ...c.knowledge_sources, ...patch } }));
  const updateOcr           = (patch) => setCfg((c) => ({ ...c, ocr_patterns: { ...c.ocr_patterns, ...patch } }));
  const updateSecurity      = (patch) => setCfg((c) => ({ ...c, security_config: { ...c.security_config, ...patch } }));
  const updateFlowKeywords  = (patch) => setCfg((c) => ({ ...c, flow_keywords: { ...c.flow_keywords, ...patch } }));
  const updateIntentKeywords = (patch) => setCfg((c) => ({ ...c, intent_keywords: { ...c.intent_keywords, ...patch } }));
  const updateEscalation    = (patch) => setCfg((c) => ({ ...c, escalation_rules: { ...c.escalation_rules, ...patch } }));
  const updateFallback      = (key, value) => setCfg((c) => ({ ...c, fallback_responses: { ...c.fallback_responses, [key]: value } }));
  const updateFeatures      = (patch) => setCfg((c) => ({ ...c, features: { ...(c.features || {}), ...patch } }));

  const dirty = useMemo(() => JSON.stringify(cfg) !== JSON.stringify(pristine), [cfg, pristine]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const body = buildSaveBody(cfg);
      const res = await fetch(`${API}/super-admin/bot-config/${tenantId}`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Save failed");
      toast.success("Bot config saved");
      setNoRow(false);
      fetchCfg();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const sharedProps = {
    cfg,
    update, updateContact, updateBranding, updatePdfBranding,
    updateKnowledgeSources, updateOcr, updateSecurity,
    updateFlowKeywords, updateIntentKeywords, updateEscalation, updateFallback,
    updateFeatures,
    setCfg,
  };

  return (
    <div className="space-y-4">
      {/* ── Top bar: tenant picker + dirty indicator + Save/Refresh ── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        {!singleTenant ? (
          <div className="w-72">
            <Label className="text-xs text-muted-foreground">Tenant</Label>
            <Select value={tenantId} onValueChange={setTenantId}>
              <SelectTrigger><SelectValue placeholder="Pick a tenant" /></SelectTrigger>
              <SelectContent>
                {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        ) : <div />}

        <div className="flex items-center gap-3">
          <DirtyIndicator dirty={dirty} />
          <Button variant="outline" size="sm" onClick={fetchCfg} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving || !tenantId || !dirty}>
            <Save className="mr-1.5 h-3.5 w-3.5" />
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </div>

      {noRow && (
        <div className="rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-foreground flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-warning" />
          <div>
            <strong className="font-medium">No saved config for this tenant.</strong> The chatbot is using the built-in defaults.
            Fill in any field below and click Save changes to create the row.
          </div>
        </div>
      )}

      {/* ── Sub-nav ── */}
      <div className="border-b border-border">
        <div className="flex gap-1 overflow-x-auto -mb-px">
          {SUB_TABS.map(({ key, label }) => {
            const active = activeSub === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => setActiveSub(key)}
                className={cn(
                  "px-3 py-2 text-sm whitespace-nowrap border-b-2 transition-colors",
                  active
                    ? "border-foreground text-foreground font-medium"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Active sub-page ── */}
      <div className="space-y-4">
        {activeSub === "identity"  && <IdentitySection  {...sharedProps} />}
        {activeSub === "contact"   && <ContactSection   {...sharedProps} />}
        {activeSub === "content"   && <ContentSection   {...sharedProps} />}
        {activeSub === "knowledge" && <KnowledgeSection {...sharedProps} />}
        {activeSub === "behaviour" && <BehaviourSection {...sharedProps} />}
        {activeSub === "pdf"       && <PdfSection       {...sharedProps} />}
        {activeSub === "security"  && <SecuritySection  {...sharedProps} />}
      </div>
    </div>
  );
}

/* ─── Sub-pages ──────────────────────────────────────────────────────── */

function IdentitySection({ cfg, update, updateBranding, setCfg }) {
  return (
    <>
      <Section
        title="Identity"
        description="How the bot introduces itself. Surfaces in the chat header, the system prompt, and any rendered placeholder like {{bot_name}}."
      >
        <Grid2>
          <Field label="Bot name" value={cfg.bot_name} onChange={(v) => update({ bot_name: v })}
            placeholder="Assistant"
            hint="Display name the assistant uses to refer to itself." />
          <Field label="Bot avatar URL" value={cfg.bot_avatar_url} onChange={(v) => update({ bot_avatar_url: v })}
            placeholder="https://…/avatar.png"
            hint="Square image shown in the widget header (PNG or SVG)." />
          <Field label="Organisation name" value={cfg.org_name} onChange={(v) => update({ org_name: v })}
            placeholder="Full legal name"
            hint="Full organisation name. Used in formal replies and the system prompt." />
          <Field label="Org short name" value={cfg.org_short_name} onChange={(v) => update({ org_short_name: v })}
            placeholder="Short label"
            hint="Short abbreviation used in greetings and tight UI spaces." />
        </Grid2>
      </Section>

      <Section
        title="Branding colours and assets"
        description="Colours and images used by the embedded chat widget. Empty fields fall back to the platform default token palette."
      >
        <Grid2>
          <ColorField label="Primary colour" value={cfg.branding.primary_color}
            onChange={(v) => updateBranding({ primary_color: v })}
            hint="Main accent (header, primary buttons)." />
          <ColorField label="Secondary colour" value={cfg.branding.secondary_color}
            onChange={(v) => updateBranding({ secondary_color: v })}
            hint="Highlights and call-to-action elements." />
          <Field label="Logo URL" value={cfg.branding.logo_url} onChange={(v) => updateBranding({ logo_url: v })}
            placeholder="https://…/logo.png"
            hint="Logo shown in the widget header (transparent PNG or SVG)." />
          <Field label="Favicon URL" value={cfg.branding.favicon_url} onChange={(v) => updateBranding({ favicon_url: v })}
            placeholder="https://…/favicon.ico"
            hint="Favicon for any standalone bot page." />
        </Grid2>
      </Section>

      <Section
        title="Widget chrome"
        description="Optional copy that appears around the chat. All fields are optional — empty fields hide the element entirely."
      >
        <Grid2>
          <Field label="Header tagline" value={cfg.header_tagline} onChange={(v) => update({ header_tagline: v })}
            placeholder="e.g. Your 24/7 service assistant"
            hint="Small line rendered under the bot name. Supports {{org_name}} etc." />
          <Field label="Footer copy" value={cfg.footer_copy} onChange={(v) => update({ footer_copy: v })}
            placeholder="e.g. Official service of {{org_name}}"
            hint="Single-line credit at the bottom of the chat." />
        </Grid2>
      </Section>
    </>
  );
}

function ContactSection({ cfg, updateContact, setCfg }) {
  return (
    <Section
      title="Contact"
      description="Details the bot may share when asked. Surfaced via {{contact.*}} placeholders in the system prompt and PDFs."
    >
      <Grid2>
        <Field label="Address" value={cfg.contact.address} onChange={(v) => updateContact({ address: v })}
          hint="Physical office address." />
        <Field label="Phone" value={cfg.contact.phone} onChange={(v) => updateContact({ phone: v })}
          hint="Primary phone with country code." />
        <Field label="Emergency phone" value={cfg.contact.emergency_phone} onChange={(v) => updateContact({ emergency_phone: v })}
          hint="After-hours / emergency number, if any." />
        <Field label="Email" value={cfg.contact.email} onChange={(v) => updateContact({ email: v })}
          hint="Public contact email." />
        <Field label="Website" value={cfg.contact.website} onChange={(v) => updateContact({ website: v })}
          hint="Official website URL." />
        <Field label="Office hours" value={cfg.contact.office_hours} onChange={(v) => updateContact({ office_hours: v })}
          hint='e.g. "Mon–Fri 09:00–17:00".' />
        <Field label="Service hours" value={cfg.contact.consular_hours} onChange={(v) => updateContact({ consular_hours: v })}
          hint="Public-facing service window if different from office hours." />
        <Field label="Phone country code" value={cfg.phone_country_code}
          onChange={(v) => setCfg((c) => ({ ...c, phone_country_code: v }))}
          hint='ISD/country code without "+" (e.g. "1" for US, "44" for UK). Used to normalise inbound WhatsApp numbers.' />
      </Grid2>
    </Section>
  );
}

function ContentSection({ cfg, update, updateFallback, setCfg }) {
  /* ── advisories CRUD ─── */
  const setAdv = (i, patch) => setCfg((c) => {
    const advs = [...(c.advisories || [])];
    advs[i] = { ...advs[i], ...patch };
    return { ...c, advisories: advs };
  });
  const addAdv = () => setCfg((c) => ({
    ...c,
    advisories: [
      ...(c.advisories || []),
      { id: `adv_${Date.now()}`, type: "info", title: "", content: "", active: true },
    ],
  }));
  const delAdv = (i) => setCfg((c) => {
    const advs = [...(c.advisories || [])];
    advs.splice(i, 1);
    return { ...c, advisories: advs };
  });

  /* ── languages CRUD ─── */
  const setLang = (i, patch) => setCfg((c) => {
    const langs = [...c.supported_languages];
    langs[i] = { ...langs[i], ...patch };
    return { ...c, supported_languages: langs };
  });
  const addLang = () => setCfg((c) => ({
    ...c,
    supported_languages: [
      ...c.supported_languages,
      { code: "", name: "", native_name: "", aliases: [], bcp47_code: "", flag: "", tts_voice_preference: "", tts_voice: "", script_hint: "" },
    ],
  }));
  const delLang = (i) => setCfg((c) => {
    const langs = [...c.supported_languages];
    langs.splice(i, 1);
    return { ...c, supported_languages: langs };
  });

  return (
    <>
      <Section
        title="System prompt"
        description="Instructions the LLM gets at the start of every conversation. Placeholders are filled in from this config."
      >
        <Textarea
          value={cfg.system_prompt_template}
          onChange={(e) => update({ system_prompt_template: e.target.value })}
          rows={6}
          className="font-mono text-xs"
          placeholder="You are {{bot_name}}, the assistant for {{org_name}}…"
        />
        <p className="text-xs text-muted-foreground mt-2 leading-snug">
          Leave blank to use the platform default. Variables:
          {" "}<code className="text-foreground">{`{{bot_name}}`}</code>,
          {" "}<code className="text-foreground">{`{{org_name}}`}</code>,
          {" "}<code className="text-foreground">{`{{contact.email}}`}</code>, etc.
        </p>
      </Section>

      <Section
        title="Fallback responses"
        description="Used verbatim when the LLM is unavailable or input matches a trigger."
      >
        <div className="space-y-4">
          {FALLBACK_KEYS.map((k) => (
            <div key={k}>
              <Label className="text-xs capitalize">{k.replace(/_/g, " ")}</Label>
              <Textarea
                value={cfg.fallback_responses[k] || ""}
                onChange={(e) => updateFallback(k, e.target.value)}
                rows={2}
                placeholder={EMPTY_CFG.fallback_responses[k]}
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1">{FALLBACK_HINTS[k]}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Supported languages"
        description="Languages users can pick in the chat widget. The default is preselected on first open."
        actions={
          <Button size="sm" variant="outline" onClick={addLang}>
            <Plus className="mr-1.5 h-3 w-3" /> Add language
          </Button>
        }
      >
        <div className="space-y-3">
          {cfg.supported_languages.map((l, i) => (
            <div key={i} className="rounded-md border border-border bg-secondary/40 p-3 space-y-2">
              <div className="flex gap-2 items-end flex-wrap">
                <div className="w-20">
                  <Label className="text-xs">Code</Label>
                  <Input value={l.code} onChange={(e) => setLang(i, { code: e.target.value })} placeholder="en" className="font-mono mt-1" />
                </div>
                <div className="flex-1 min-w-[160px]">
                  <Label className="text-xs">Name</Label>
                  <Input value={l.name} onChange={(e) => setLang(i, { name: e.target.value })} placeholder="English" className="mt-1" />
                </div>
                <div className="flex-1 min-w-[140px]">
                  <Label className="text-xs">Native name</Label>
                  <Input value={l.native_name || ""} onChange={(e) => setLang(i, { native_name: e.target.value })} placeholder="हिंदी" className="mt-1" />
                </div>
                <div className="w-16">
                  <Label className="text-xs">Flag</Label>
                  <Input value={l.flag || ""} onChange={(e) => setLang(i, { flag: e.target.value })} placeholder="🇺🇸" className="mt-1" />
                </div>
                <Button size="sm" variant="ghost" onClick={() => delLang(i)} disabled={cfg.supported_languages.length === 1}>
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              </div>
              <div className="flex gap-2 items-end flex-wrap">
                <div className="flex-1 min-w-[200px]">
                  <Label className="text-xs">Aliases (comma-separated)</Label>
                  <Input
                    value={Array.isArray(l.aliases) ? l.aliases.join(", ") : (l.aliases || "")}
                    onChange={(e) => setLang(i, { aliases: e.target.value })}
                    placeholder="hindi, हिन्दी"
                    className="mt-1"
                  />
                </div>
                <div className="w-24">
                  <Label className="text-xs">BCP-47</Label>
                  <Input value={l.bcp47_code || ""} onChange={(e) => setLang(i, { bcp47_code: e.target.value })} placeholder="en-US" className="font-mono mt-1" />
                </div>
                <div className="w-28">
                  <Label className="text-xs">TTS voice ID</Label>
                  <Input value={l.tts_voice || ""} onChange={(e) => setLang(i, { tts_voice: e.target.value })} placeholder="nova" className="font-mono mt-1" />
                </div>
                <div className="w-32">
                  <Label className="text-xs">Voice gender</Label>
                  <Select value={l.tts_voice_preference || "neutral"} onValueChange={(v) => setLang(i, { tts_voice_preference: v === "neutral" ? "" : v })}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="neutral">Neutral</SelectItem>
                      <SelectItem value="female">Female</SelectItem>
                      <SelectItem value="male">Male</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label className="text-xs">Script hint (LLM instruction)</Label>
                <Input
                  value={l.script_hint || ""}
                  onChange={(e) => setLang(i, { script_hint: e.target.value })}
                  placeholder="You MUST write in Devanagari script (देवनागरी)."
                  className="mt-1"
                />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 w-48">
          <Label className="text-xs">Default language</Label>
          <Select value={cfg.default_language} onValueChange={(v) => update({ default_language: v })}>
            <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
            <SelectContent>
              {cfg.supported_languages
                .filter((l) => l.code)
                .map((l) => <SelectItem key={l.code} value={l.code}>{l.name || l.code}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </Section>

      <Section
        title="Pre-chat advisories"
        description="Optional cards shown above the first bot message — use for fraud warnings, service notices, or scheduled-outage alerts."
        actions={
          <Button size="sm" variant="outline" onClick={addAdv}>
            <Plus className="mr-1.5 h-3 w-3" /> Add advisory
          </Button>
        }
      >
        <div className="space-y-2">
          {(cfg.advisories || []).length === 0 && (
            <div className="text-xs text-muted-foreground italic">
              No advisories. The widget will not show this row.
            </div>
          )}
          {(cfg.advisories || []).map((adv, i) => (
            <div key={adv.id || i} className="rounded-md border border-border bg-secondary/40 p-3 space-y-2">
              <div className="grid grid-cols-12 gap-2 items-end">
                <div className="col-span-2">
                  <Label className="text-xs">Type</Label>
                  <Select value={adv.type || "info"} onValueChange={(v) => setAdv(i, { type: v })}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {ADVISORY_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="col-span-8">
                  <Label className="text-xs">Title</Label>
                  <Input value={adv.title || ""} onChange={(e) => setAdv(i, { title: e.target.value })} placeholder="Advisory title" className="mt-1" />
                </div>
                <div className="col-span-1 flex items-center justify-center pb-2">
                  <Switch checked={adv.active !== false} onCheckedChange={(v) => setAdv(i, { active: v })} />
                </div>
                <div className="col-span-1 flex justify-end pb-1">
                  <Button size="sm" variant="ghost" onClick={() => delAdv(i)}>
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </Button>
                </div>
              </div>
              <Textarea
                value={adv.content || ""}
                onChange={(e) => setAdv(i, { content: e.target.value })}
                rows={2}
                placeholder="Body text (markdown supported)"
              />
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}

function KnowledgeSection({ cfg, updateKnowledgeSources, updateOcr, setCfg }) {
  return (
    <>
      <Section
        title="Knowledge sources"
        description="URLs the scraper crawls to refresh the knowledge base. Leave blank to disable scraping for this tenant."
      >
        <Field label="Primary URL" value={cfg.knowledge_sources.primary_url}
          onChange={(v) => updateKnowledgeSources({ primary_url: v })}
          placeholder="https://your-official-site.example/"
          hint="Main site crawled on each refresh cycle. Contact details may be extracted from this page." />
        <div className="mt-3">
          <Field label="Sub-pages (one per line)"
            value={(cfg.knowledge_sources.sub_pages || []).join("\n")}
            onChange={(v) => updateKnowledgeSources({ sub_pages: v.split("\n").map((u) => u.trim()).filter(Boolean) })}
            placeholder={"https://your-official-site.example/services/passport\nhttps://your-official-site.example/services/visa"}
            hint="Additional pages on the same primary domain. One URL per line."
            multiline />
        </div>
        <div className="mt-3">
          <Field label="Secondary URLs (one per line)"
            value={(cfg.knowledge_sources.secondary_urls || []).join("\n")}
            onChange={(v) => updateKnowledgeSources({ secondary_urls: v.split("\n").map((u) => u.trim()).filter(Boolean) })}
            placeholder="https://partner.example.com/contact"
            hint="Auxiliary sources. Tried in order; first one that returns real content wins."
            multiline />
        </div>
      </Section>

      <Section
        title="Knowledge categories"
        description="Category taxonomy the admin dashboards render and POST /knowledge validates against. Empty falls back to the neutral platform set."
      >
        <Field label="Categories (one per line)"
          value={(cfg.knowledge_categories || []).join("\n")}
          onChange={(v) => setCfg((c) => ({ ...c, knowledge_categories: v.split("\n").map((s) => s.trim()).filter(Boolean) }))}
          placeholder={"general\nvisa\nfees\nemergency\nannouncement"}
          hint="Lowercase slugs, one per line. Used as the dropdown values when uploading PDFs or creating KB entries."
          multiline />
      </Section>

      <Section
        title="OCR pattern extraction"
        description="Heuristics applied to uploaded-document text to auto-fill form fields. Empty values inherit a neutral platform fallback."
      >
        <Grid2>
          <Field label="Passport regex" value={cfg.ocr_patterns?.passport_regex || ""}
            onChange={(v) => updateOcr({ passport_regex: v })}
            placeholder="\\b[A-Z]{1,2}\\d{6,8}\\b"
            hint="Single regex matching exactly one capture group containing the document number." />
          <Field label="Date regex" value={cfg.ocr_patterns?.date_regex || ""}
            onChange={(v) => updateOcr({ date_regex: v })}
            placeholder="\\b(\\d{2}[/\\-]\\d{2}[/\\-]\\d{4})\\b"
            hint="Regex matching dates in your tenant's preferred format." />
        </Grid2>
        <div className="mt-3">
          <Field label="Name blocklist (comma-separated)"
            value={(cfg.ocr_patterns?.name_blocklist || []).join(", ")}
            onChange={(v) => updateOcr({ name_blocklist: v.split(",").map((s) => s.trim()).filter(Boolean) })}
            placeholder="PASSPORT, REPUBLIC, NATIONALITY, GOVERNMENT"
            hint="ALL-CAPS tokens the name extractor should skip. Add region-specific labels here (country names, document headers)." />
        </div>
      </Section>
    </>
  );
}

function BehaviourSection({ cfg, updateFlowKeywords, updateIntentKeywords, updateEscalation, updateFeatures }) {
  // The features block was added with the contextual-input work: mic
  // is a tenant-global toggle (always-on / never-on), upload + camera
  // are also gateable globally but the *contextual* visibility is
  // driven by the chat-stream's ui_hints regardless. So setting these
  // to false hides the affordance entirely; setting to true allows it
  // to appear when the bot signals it expects a file/image.
  const features = cfg.features || {};
  const setFeature = (k, v) => updateFeatures({ [k]: v });
  return (
    <>
      <Section
        title="Input controls"
        description="Global on/off for the mic, upload, and camera affordances in the chat widget. Upload + camera are also contextual — they only appear when the bot has actually asked for a file, regardless of these toggles. Mic is purely tenant-controlled (always-on if enabled)."
      >
        <div className="space-y-3">
          <FeatureToggle
            label="Voice input (mic)"
            description="Show the microphone in the chat input bar so users can dictate messages. Disabling hides it completely."
            checked={features.voice_input !== false}
            onChange={(v) => setFeature("voice_input", v)}
          />
          <FeatureToggle
            label="File upload"
            description="Allow file uploads when the bot asks for documents. Disabling forces all flows to text-only — application flows that require document uploads will fail."
            checked={features.file_upload !== false}
            onChange={(v) => setFeature("file_upload", v)}
          />
          <FeatureToggle
            label="Camera capture"
            description="Allow in-widget camera capture for document scans. Same context rule as file upload — only appears when the bot expects an image."
            checked={features.camera !== false}
            onChange={(v) => setFeature("camera", v)}
          />
        </div>
      </Section>

      <Section
        title="Flow keywords"
        description="Phrases the bot treats as apply / yes / no / discard / continue intents. Empty inherits the platform default."
      >
        <Grid2>
          {FLOW_KEYS.map((cat) => (
            <Field key={cat}
              label={cat.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase())}
              value={(cfg.flow_keywords?.[cat] || []).join("\n")}
              onChange={(v) => updateFlowKeywords({ [cat]: v.split("\n").map((s) => s.trim()).filter(Boolean) })}
              placeholder={cat === "apply" ? "apply\nregister\nstart" : "one phrase per line"}
              hint="One phrase per line. Matches are case-insensitive substrings."
              multiline />
          ))}
        </Grid2>
      </Section>

      <Section
        title="Intent keywords"
        description="Extend the platform default keyword set for each intent category. Empty inherits the platform default — only add what's tenant-specific."
      >
        <Grid2>
          {INTENT_CATEGORIES.map((cat) => (
            <Field key={cat}
              label={cat.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase())}
              value={(cfg.intent_keywords?.[cat] || []).join("\n")}
              onChange={(v) => updateIntentKeywords({ [cat]: v.split("\n").map((s) => s.trim()).filter(Boolean) })}
              placeholder="one phrase per line"
              hint="Tenant-specific phrases that should trigger this intent (e.g. city names for office_info)."
              multiline />
          ))}
        </Grid2>
      </Section>

      <Section
        title="Escalation rules"
        description="When messages get flagged for a human handoff. Empty fields fall back to platform defaults."
      >
        <Grid2>
          <Field label="Escalation keywords"
            value={(cfg.escalation_rules?.keywords || []).join("\n")}
            onChange={(v) => updateEscalation({ keywords: v.split("\n").map((s) => s.trim()).filter(Boolean) })}
            placeholder={"speak to human\nagent\nmanager"}
            hint="Any-priority triggers. Case-insensitive substrings."
            multiline />
          <Field label="Regex patterns"
            value={(cfg.escalation_rules?.patterns || []).join("\n")}
            onChange={(v) => updateEscalation({ patterns: v.split("\n").map((s) => s.trim()).filter(Boolean) })}
            placeholder={"(speak|talk).*(human|agent)\n(lawyer|legal|court|sue)"}
            hint="Python regex patterns, one per line."
            multiline />
          <Field label="Complaint keywords (HIGH)"
            value={(cfg.escalation_rules?.complaint_keywords || []).join("\n")}
            onChange={(v) => updateEscalation({ complaint_keywords: v.split("\n").map((s) => s.trim()).filter(Boolean) })}
            placeholder={"complaint\nrefund\nsue"}
            hint="Triggers HIGH-priority escalation."
            multiline />
          <Field label="Emergency keywords (URGENT)"
            value={(cfg.escalation_rules?.emergency_keywords || []).join("\n")}
            onChange={(v) => updateEscalation({ emergency_keywords: v.split("\n").map((s) => s.trim()).filter(Boolean) })}
            placeholder={"emergency\nurgent\nhospital"}
            hint="Triggers URGENT-priority escalation."
            multiline />
          <Field label="Blocked spam patterns"
            value={(cfg.escalation_rules?.blocked_patterns || []).join("\n")}
            onChange={(v) => updateEscalation({ blocked_patterns: v.split("\n").map((s) => s.trim()).filter(Boolean) })}
            placeholder={"(?i)click here.*win\n(?i)free.*prize"}
            hint="WhatsApp messages matching any pattern are silently dropped."
            multiline />
          <Field label="Consecutive failures threshold"
            value={String(cfg.escalation_rules?.consecutive_failure_threshold || "")}
            onChange={(v) => updateEscalation({ consecutive_failure_threshold: Number(v) || 0 })}
            placeholder="3"
            hint="Escalate to a human after this many consecutive failed responses. Platform default: 3." />
        </Grid2>
      </Section>
    </>
  );
}

function PdfSection({ cfg, updatePdfBranding }) {
  return (
    <Section
      title="PDF branding"
      description="Colours and strings used on application-preview PDFs. Leave a field blank to inherit a neutral default."
    >
      <Grid2>
        <ColorField label="Header colour" value={cfg.pdf_branding.header_color}
          onChange={(v) => updatePdfBranding({ header_color: v })}
          hint="Top band + section dividers." />
        <ColorField label="Accent colour" value={cfg.pdf_branding.accent_color}
          onChange={(v) => updatePdfBranding({ accent_color: v })}
          hint="Sub-header + checklist markers." />
        <ColorField label="Highlight colour" value={cfg.pdf_branding.highlight_color}
          onChange={(v) => updatePdfBranding({ highlight_color: v })}
          hint="Thin stripe at the very top of the header." />
        <ColorField label="Notice background" value={cfg.pdf_branding.notice_bg}
          onChange={(v) => updatePdfBranding({ notice_bg: v })}
          hint="Background of the review-notice box." />
        <ColorField label="Muted text" value={cfg.pdf_branding.muted_text}
          onChange={(v) => updatePdfBranding({ muted_text: v })}
          hint="Secondary text (timestamps, field labels)." />
        <ColorField label="Border colour" value={cfg.pdf_branding.border}
          onChange={(v) => updatePdfBranding({ border: v })}
          hint="Dividers, field borders, signature lines." />
      </Grid2>
      <div className="mt-3">
        <Field label="Stripe colours (comma-separated hex)"
          value={(cfg.pdf_branding.stripe_colors || []).join(", ")}
          onChange={(v) => updatePdfBranding({ stripe_colors: v.split(",").map((s) => s.trim()).filter(Boolean) })}
          placeholder="#1A2E40, #FFFFFF, #6366F1"
          hint="Optional accent stripes at the top of the header. Empty = single highlight stripe." />
      </div>
      <div className="mt-3">
        <Field label="Notice text" value={cfg.pdf_branding.notice_text}
          onChange={(v) => updatePdfBranding({ notice_text: v })}
          hint="Shown inside the review-notice box near the top of the PDF." />
      </div>
      <div className="mt-3">
        <Field label="Footer text" value={cfg.pdf_branding.footer_text}
          onChange={(v) => updatePdfBranding({ footer_text: v })}
          hint="Single-line footer at the bottom of every PDF page." />
      </div>
    </Section>
  );
}

function SecuritySection({ cfg, updateSecurity }) {
  return (
    <Section
      title="Security & upload limits"
      description="OTP, session, and upload caps. Leave a field blank (or 0) to inherit the platform default shown in the placeholder."
    >
      <Grid2>
        <Field label="OTP TTL (minutes)" value={String(cfg.security_config.otp_ttl_minutes || "")}
          onChange={(v) => updateSecurity({ otp_ttl_minutes: Number(v) || 0 })}
          placeholder="10"
          hint="How long an issued OTP is valid. Platform default: 10." />
        <Field label="OTP max attempts" value={String(cfg.security_config.otp_max_attempts || "")}
          onChange={(v) => updateSecurity({ otp_max_attempts: Number(v) || 0 })}
          placeholder="3"
          hint="Wrong OTP entries before lockout. Platform default: 3." />
        <Field label="OTP lockout (minutes)" value={String(cfg.security_config.otp_lockout_minutes || "")}
          onChange={(v) => updateSecurity({ otp_lockout_minutes: Number(v) || 0 })}
          placeholder="5"
          hint="Lockout window after too many failed OTPs. Platform default: 5." />
        <Field label="OTP dev value" value={cfg.security_config.otp_dev_value || ""}
          onChange={(v) => updateSecurity({ otp_dev_value: v })}
          placeholder="123456"
          hint="Fixed OTP used when SMTP is not configured. Replace in production." />
        <Field label="Server session inactivity (minutes)" value={String(cfg.security_config.session_inactivity_minutes || "")}
          onChange={(v) => updateSecurity({ session_inactivity_minutes: Number(v) || 0 })}
          placeholder="10"
          hint="Idle minutes before the backend invalidates the session token." />
        <Field label="Client inactivity (minutes)" value={String(cfg.security_config.client_inactivity_minutes || "")}
          onChange={(v) => updateSecurity({ client_inactivity_minutes: Number(v) || 0 })}
          placeholder="10"
          hint="Browser idle minutes before the widget logs the user out." />
        <Field label="Upload max size (bytes)" value={String(cfg.security_config.upload_max_bytes || "")}
          onChange={(v) => updateSecurity({ upload_max_bytes: Number(v) || 0 })}
          placeholder="5242880"
          hint="Hard cap on uploaded file size. Platform default: 5 MB." />
        <Field label="Upload max PDF pages" value={String(cfg.security_config.upload_max_pdf_pages || "")}
          onChange={(v) => updateSecurity({ upload_max_pdf_pages: Number(v) || 0 })}
          placeholder="5"
          hint="How many pages of a PDF get rendered for OCR." />
      </Grid2>
      <div className="mt-3">
        <Field label="Upload allowed MIME types (comma-separated)"
          value={(cfg.security_config.upload_allowed_mime_types || []).join(", ")}
          onChange={(v) => updateSecurity({ upload_allowed_mime_types: v.split(",").map((s) => s.trim()).filter(Boolean) })}
          placeholder="application/pdf, image/jpeg, image/png"
          hint='Empty = platform default ("application/pdf, image/jpeg, image/png, image/jpg").' />
      </div>
    </Section>
  );
}

/* ─── primitives ─────────────────────────────────────────────────────── */

function Grid2({ children }) {
  return <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{children}</div>;
}

function FeatureToggle({ label, description, checked, onChange }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-md border border-border bg-card px-3 py-2.5">
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">{label}</p>
        {description && (
          <p className="text-xs text-muted-foreground mt-0.5 leading-snug">{description}</p>
        )}
      </div>
      <Switch checked={!!checked} onCheckedChange={onChange} aria-label={label} />
    </div>
  );
}

function Field({ label, value, onChange, placeholder, hint, multiline = false }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      {multiline ? (
        <Textarea
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={4}
          className="font-mono text-xs mt-1"
        />
      ) : (
        <Input value={value || ""} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className="mt-1" />
      )}
      {hint && <p className="text-xs text-muted-foreground mt-1 leading-snug">{hint}</p>}
    </div>
  );
}

// Matches /^#([0-9a-f]{3}|[0-9a-f]{6})$/i — anything else (including blank)
// is treated as "no value" so the swatch can render a dashed empty state
// instead of a misleading solid black square.
const HEX_RE = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i;

function ColorField({ label, value, onChange, hint }) {
  const valid = HEX_RE.test((value || "").trim());
  const pickerRef = React.useRef(null);
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <div className="flex gap-2 items-center mt-1">
        <button
          type="button"
          onClick={() => pickerRef.current?.click()}
          title={valid ? `Open picker (${value})` : "No colour set — click to pick"}
          className={cn(
            "relative w-9 h-9 rounded-md shrink-0 border border-border overflow-hidden transition-shadow hover:ring-2 hover:ring-ring/30 focus:outline-none focus:ring-2 focus:ring-ring",
            !valid && "bg-[repeating-linear-gradient(45deg,hsl(var(--muted)),hsl(var(--muted))_4px,hsl(var(--card))_4px,hsl(var(--card))_8px)]",
          )}
          style={valid ? { background: value } : undefined}
          aria-label={`${label} colour preview`}
        />
        <input
          ref={pickerRef}
          type="color"
          value={valid ? value : "#6366f1"}
          onChange={(e) => onChange(e.target.value)}
          className="sr-only"
          aria-hidden
          tabIndex={-1}
        />
        <Input
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder="#6366f1"
          className="font-mono"
        />
      </div>
      {hint && <p className="text-xs text-muted-foreground mt-1 leading-snug">{hint}</p>}
    </div>
  );
}

function DirtyIndicator({ dirty }) {
  if (!dirty) {
    return <span className="text-xs text-muted-foreground">All changes saved</span>;
  }
  return (
    <span className="text-xs text-warning flex items-center gap-1.5">
      <Circle className="h-2 w-2 fill-warning" />
      Unsaved changes
    </span>
  );
}

/* ─── helpers ────────────────────────────────────────────────────────── */

function mergeIntoEmpty(data) {
  return {
    ...EMPTY_CFG,
    ...data,
    contact:             { ...EMPTY_CFG.contact,            ...(data.contact            || {}) },
    branding:            { ...EMPTY_CFG.branding,           ...(data.branding           || {}) },
    pdf_branding:        { ...EMPTY_CFG.pdf_branding,       ...(data.pdf_branding       || {}) },
    knowledge_sources:   { ...EMPTY_CFG.knowledge_sources,  ...(data.knowledge_sources  || {}) },
    knowledge_categories: Array.isArray(data.knowledge_categories) ? data.knowledge_categories : [],
    ocr_patterns:        { ...EMPTY_CFG.ocr_patterns,       ...(data.ocr_patterns       || {}) },
    security_config:     { ...EMPTY_CFG.security_config,    ...(data.security_config    || {}) },
    intent_keywords:     { ...(data.intent_keywords || {}) },
    flow_keywords:       { ...EMPTY_CFG.flow_keywords,      ...(data.flow_keywords      || {}) },
    escalation_rules:    { ...EMPTY_CFG.escalation_rules,   ...(data.escalation_rules   || {}) },
    fallback_responses:  { ...EMPTY_CFG.fallback_responses, ...(data.fallback_responses || {}) },
    supported_languages: data.supported_languages?.length
      ? data.supported_languages
      : EMPTY_CFG.supported_languages,
    advisories: Array.isArray(data.advisories) ? data.advisories : [],
  };
}

function buildSaveBody(cfg) {
  return {
    bot_name:        cfg.bot_name || undefined,
    bot_avatar_url:  cfg.bot_avatar_url || undefined,
    org_name:        cfg.org_name || undefined,
    org_short_name:  cfg.org_short_name || undefined,
    header_tagline:  cfg.header_tagline ?? "",
    footer_copy:     cfg.footer_copy ?? "",
    advisories: (cfg.advisories || [])
      .filter((a) => (a.title || a.content))
      .map((a, idx) => ({
        id:      a.id || `adv_${idx}`,
        type:    a.type || "info",
        title:   a.title || "",
        content: a.content || "",
        active:  a.active !== false,
      })),
    // Tenant feature toggles — drives mic visibility and the global
    // on/off for file_upload + camera (their contextual visibility is
    // separately gated by chat-stream ui_hints).
    features: {
      voice_input: cfg.features?.voice_input !== false,
      file_upload: cfg.features?.file_upload !== false,
      camera:      cfg.features?.camera       !== false,
    },
    contact: cfg.contact,
    phone_country_code: (cfg.phone_country_code || "").trim() || undefined,
    system_prompt_template: cfg.system_prompt_template || undefined,
    supported_languages: cfg.supported_languages
      .filter((l) => l.code && l.name)
      .map((l) => ({
        ...l,
        aliases: Array.isArray(l.aliases)
          ? l.aliases.map((a) => String(a).trim()).filter(Boolean)
          : String(l.aliases || "").split(",").map((a) => a.trim()).filter(Boolean),
      })),
    default_language: cfg.default_language || undefined,
    branding: cfg.branding,
    pdf_branding: {
      ...cfg.pdf_branding,
      stripe_colors: (cfg.pdf_branding?.stripe_colors || []).filter(Boolean),
    },
    knowledge_sources: {
      primary_url:    (cfg.knowledge_sources?.primary_url || "").trim(),
      sub_pages:      (cfg.knowledge_sources?.sub_pages || []).map((u) => String(u).trim()).filter(Boolean),
      secondary_urls: (cfg.knowledge_sources?.secondary_urls || []).map((u) => String(u).trim()).filter(Boolean),
    },
    knowledge_categories: (cfg.knowledge_categories || []).map((s) => String(s).trim().toLowerCase()).filter(Boolean),
    ocr_patterns: {
      passport_regex: (cfg.ocr_patterns?.passport_regex || "").trim(),
      date_regex:     (cfg.ocr_patterns?.date_regex || "").trim(),
      name_blocklist: (cfg.ocr_patterns?.name_blocklist || []).map((s) => String(s).trim()).filter(Boolean),
    },
    security_config: {
      otp_ttl_minutes:            Number(cfg.security_config?.otp_ttl_minutes)            || 0,
      otp_max_attempts:           Number(cfg.security_config?.otp_max_attempts)           || 0,
      otp_lockout_minutes:        Number(cfg.security_config?.otp_lockout_minutes)        || 0,
      otp_dev_value:              (cfg.security_config?.otp_dev_value || "").trim(),
      session_inactivity_minutes: Number(cfg.security_config?.session_inactivity_minutes) || 0,
      client_inactivity_minutes:  Number(cfg.security_config?.client_inactivity_minutes)  || 0,
      upload_max_bytes:           Number(cfg.security_config?.upload_max_bytes)           || 0,
      upload_max_pdf_pages:       Number(cfg.security_config?.upload_max_pdf_pages)       || 0,
      upload_allowed_mime_types:  (Array.isArray(cfg.security_config?.upload_allowed_mime_types)
                                    ? cfg.security_config.upload_allowed_mime_types
                                    : (cfg.security_config?.upload_allowed_mime_types || "").split(","))
                                    .map((m) => String(m).trim()).filter(Boolean),
    },
    intent_keywords: Object.fromEntries(
      Object.entries(cfg.intent_keywords || {}).map(([k, v]) => [
        k,
        (Array.isArray(v) ? v : String(v).split("\n")).map((s) => String(s).trim()).filter(Boolean),
      ])
    ),
    flow_keywords: Object.fromEntries(
      Object.entries(cfg.flow_keywords || {}).map(([k, v]) => [
        k,
        (Array.isArray(v) ? v : String(v).split("\n")).map((s) => String(s).trim()).filter(Boolean),
      ])
    ),
    escalation_rules: {
      ...cfg.escalation_rules,
      keywords:           (cfg.escalation_rules?.keywords           || []).filter(Boolean),
      patterns:           (cfg.escalation_rules?.patterns           || []).filter(Boolean),
      complaint_keywords: (cfg.escalation_rules?.complaint_keywords || []).filter(Boolean),
      emergency_keywords: (cfg.escalation_rules?.emergency_keywords || []).filter(Boolean),
      blocked_patterns:   (cfg.escalation_rules?.blocked_patterns   || []).filter(Boolean),
      consecutive_failure_threshold: Number(cfg.escalation_rules?.consecutive_failure_threshold) || 0,
    },
    fallback_responses: cfg.fallback_responses,
  };
}
