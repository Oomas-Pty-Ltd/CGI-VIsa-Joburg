/**
 * Super-admin tab — Bot Config (Sprint 3D)
 *
 * Per-tenant branding, contact info, system prompt, supported languages,
 * colors, fallback responses. Backed by `tenant_bot_config` collection;
 * the PUT endpoint deep-merges `contact` and `branding` so editing one
 * nested field doesn't blank the others.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  RefreshCw, Save, Plus, Trash2, AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const FALLBACK_KEYS = ["greeting", "out_of_scope", "error", "blocked_input"];

const FALLBACK_HINTS = {
  greeting: "First message users see when they open the chat.",
  out_of_scope: "Shown when the user asks about something the bot is not configured to answer.",
  error: "Shown when an internal error prevents the bot from replying.",
  blocked_input: "Shown when input is rejected by safety filters (profanity, prompt injection, etc.).",
};

const EMPTY_CFG = {
  bot_name: "",
  bot_avatar_url: "",
  org_name: "",
  org_short_name: "",
  contact: {
    address: "", phone: "", emergency_phone: "",
    email: "", website: "", office_hours: "", consular_hours: "",
  },
  system_prompt_template: "",
  supported_languages: [{ code: "en", name: "English" }],
  default_language: "en",
  branding: {
    primary_color: "#1A237E", secondary_color: "#FF6F00",
    logo_url: "", favicon_url: "",
  },
  fallback_responses: {
    greeting: "", out_of_scope: "", error: "", blocked_input: "",
  },
};

export default function BotConfigTab({ companies, token, singleTenant = false }) {
  const [tenantId, setTenantId] = useState("");
  const [cfg, setCfg] = useState(EMPTY_CFG);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving]   = useState(false);
  const [noRow, setNoRow]     = useState(false); // true when tenant has no config row yet

  useEffect(() => {
    if (!tenantId && companies.length > 0) setTenantId(companies[0].id);
  }, [companies, tenantId]);

  const fetchCfg = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setNoRow(false);
    try {
      // Use ?soft_404=1 so the backend returns 200 + {exists: false}
      // instead of 404 when no row exists. This is the expected first
      // run of the tab (UI shows the amber "no saved config" banner),
      // and browsers log every 4xx as "Failed to load resource" in
      // DevTools regardless of fetch's error handling, so the 200 form
      // keeps the console clean.
      const res = await fetch(`${API}/super-admin/bot-config/${tenantId}?soft_404=1`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load");
      if (data.exists === false) {
        setCfg(EMPTY_CFG);
        setNoRow(true);
        return;
      }
      // Merge stored into defaults so missing keys still have inputs
      setCfg({
        ...EMPTY_CFG,
        ...data,
        contact: { ...EMPTY_CFG.contact, ...(data.contact || {}) },
        branding: { ...EMPTY_CFG.branding, ...(data.branding || {}) },
        fallback_responses: { ...EMPTY_CFG.fallback_responses, ...(data.fallback_responses || {}) },
        supported_languages: data.supported_languages?.length
          ? data.supported_languages
          : EMPTY_CFG.supported_languages,
      });
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [tenantId, token]);

  useEffect(() => { fetchCfg(); }, [fetchCfg]);

  const update = (patch) => setCfg((c) => ({ ...c, ...patch }));
  const updateContact = (patch) => setCfg((c) => ({ ...c, contact: { ...c.contact, ...patch } }));
  const updateBranding = (patch) => setCfg((c) => ({ ...c, branding: { ...c.branding, ...patch } }));
  const updateFallback = (key, value) => setCfg((c) => ({
    ...c, fallback_responses: { ...c.fallback_responses, [key]: value },
  }));

  const handleSave = async () => {
    setSaving(true);
    try {
      // Build the update body — exclude internal/empty stuff
      const body = {
        bot_name: cfg.bot_name || undefined,
        bot_avatar_url: cfg.bot_avatar_url || undefined,
        org_name: cfg.org_name || undefined,
        org_short_name: cfg.org_short_name || undefined,
        contact: cfg.contact,
        system_prompt_template: cfg.system_prompt_template || undefined,
        supported_languages: cfg.supported_languages.filter((l) => l.code && l.name),
        default_language: cfg.default_language || undefined,
        branding: cfg.branding,
        fallback_responses: cfg.fallback_responses,
      };
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

  /* ─── languages CRUD ─── */
  const setLang = (i, patch) => setCfg((c) => {
    const langs = [...c.supported_languages];
    langs[i] = { ...langs[i], ...patch };
    return { ...c, supported_languages: langs };
  });
  const addLang = () => setCfg((c) => ({
    ...c, supported_languages: [...c.supported_languages, { code: "", name: "" }],
  }));
  const delLang = (i) => setCfg((c) => {
    const langs = [...c.supported_languages];
    langs.splice(i, 1);
    return { ...c, supported_languages: langs };
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-xl font-semibold">Bot Config</h2>
          <p className="text-sm text-slate-500">
            {singleTenant
              ? "Branding, contact info, system prompt and fallback messaging for your bot."
              : "Per-tenant branding, contact info, system prompt and fallback messaging."}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchCfg} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button onClick={handleSave} disabled={saving || !tenantId}>
            <Save className="mr-2 h-4 w-4" />
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      {!singleTenant && (
        <div className="w-96">
          <Label className="text-xs">Tenant</Label>
          <Select value={tenantId} onValueChange={setTenantId}>
            <SelectTrigger><SelectValue placeholder="Pick a tenant" /></SelectTrigger>
            <SelectContent>
              {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      )}

      {noRow && (
        <div className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          <div>
            <strong>No saved config for this tenant.</strong> The chatbot is using the
            built-in defaults. Filling in any field below and clicking Save creates the row.
          </div>
        </div>
      )}

      {/* Identity */}
      <Section
        title="Identity"
        description="How the bot introduces itself and which organisation it speaks for. Shown in the widget header and used inside the system prompt."
      >
        <Grid2>
          <Field
            label="Bot name"
            value={cfg.bot_name}
            onChange={(v) => update({ bot_name: v })}
            placeholder="Seva Setu"
            hint="Display name the assistant uses to refer to itself in chat."
          />
          <Field
            label="Bot avatar URL"
            value={cfg.bot_avatar_url}
            onChange={(v) => update({ bot_avatar_url: v })}
            placeholder="https://…/avatar.png"
            hint="Square image shown in the widget header (PNG or SVG)."
          />
          <Field
            label="Organisation name"
            value={cfg.org_name}
            onChange={(v) => update({ org_name: v })}
            placeholder="Full legal name"
            hint="Full name of your organisation. Used in formal replies and the system prompt."
          />
          <Field
            label="Org short name"
            value={cfg.org_short_name}
            onChange={(v) => update({ org_short_name: v })}
            placeholder="Short label"
            hint="Short abbreviation used in greetings and tight UI spaces."
          />
        </Grid2>
      </Section>

      {/* Contact */}
      <Section
        title="Contact"
        description="Contact details the bot may share with users when asked (address, phones, email, hours)."
      >
        <Grid2>
          <Field label="Address" value={cfg.contact.address} onChange={(v) => updateContact({ address: v })} hint="Physical office address." />
          <Field label="Phone" value={cfg.contact.phone} onChange={(v) => updateContact({ phone: v })} hint="Primary phone with country code." />
          <Field label="Emergency phone" value={cfg.contact.emergency_phone} onChange={(v) => updateContact({ emergency_phone: v })} hint="After-hours / emergency number, if any." />
          <Field label="Email" value={cfg.contact.email} onChange={(v) => updateContact({ email: v })} hint="Public contact email." />
          <Field label="Website" value={cfg.contact.website} onChange={(v) => updateContact({ website: v })} hint="Official website URL." />
          <Field label="Office hours" value={cfg.contact.office_hours} onChange={(v) => updateContact({ office_hours: v })} hint='e.g. "Mon–Fri 09:00–17:00".' />
          <Field label="Service hours" value={cfg.contact.consular_hours} onChange={(v) => updateContact({ consular_hours: v })} hint="Public-facing service window if different from office hours." />
        </Grid2>
      </Section>

      {/* Branding */}
      <Section
        title="Branding"
        description="Colours and images used by the embedded widget."
      >
        <Grid2>
          <ColorField label="Primary color" value={cfg.branding.primary_color} onChange={(v) => updateBranding({ primary_color: v })} hint="Main accent colour (header, primary buttons)." />
          <ColorField label="Secondary color" value={cfg.branding.secondary_color} onChange={(v) => updateBranding({ secondary_color: v })} hint="Used for highlights and call-to-action elements." />
          <Field label="Logo URL" value={cfg.branding.logo_url} onChange={(v) => updateBranding({ logo_url: v })} placeholder="https://…/logo.png" hint="Logo shown in the widget header (recommend transparent PNG/SVG)." />
          <Field label="Favicon URL" value={cfg.branding.favicon_url} onChange={(v) => updateBranding({ favicon_url: v })} placeholder="https://…/favicon.ico" hint="Favicon for any standalone bot page." />
        </Grid2>
      </Section>

      {/* System prompt */}
      <Section
        title="System prompt"
        description="The instructions the LLM gets at the start of every conversation. Placeholders like {{bot_name}} are filled in from this config."
      >
        <Label className="text-xs">Template <span className="text-slate-400">(supports {`{{var}}`} and {`{{nested.path}}`} from this config)</span></Label>
        <Textarea
          value={cfg.system_prompt_template}
          onChange={(e) => update({ system_prompt_template: e.target.value })}
          rows={6}
          className="font-mono text-xs"
          placeholder="You are {{bot_name}}, the official assistant for {{org_name}}…"
        />
        <p className="text-[11px] text-slate-500 leading-snug">
          Leave blank to use the platform default. Variables you can reference:
          {" "}<code>{`{{bot_name}}`}</code>, <code>{`{{org_name}}`}</code>,
          {" "}<code>{`{{org_short_name}}`}</code>, <code>{`{{contact.email}}`}</code>, etc.
        </p>
      </Section>

      {/* Languages */}
      <Section
        title="Supported languages"
        description="Languages the user can pick in the chat widget. The default is preselected on first open."
      >
        <div className="space-y-2">
          {cfg.supported_languages.map((l, i) => (
            <div key={i} className="flex gap-2 items-end">
              <div className="w-24">
                <Label className="text-xs">Code</Label>
                <Input value={l.code} onChange={(e) => setLang(i, { code: e.target.value })} placeholder="en" className="font-mono" />
              </div>
              <div className="flex-1">
                <Label className="text-xs">Name</Label>
                <Input value={l.name} onChange={(e) => setLang(i, { name: e.target.value })} placeholder="English" />
              </div>
              <Button size="sm" variant="ghost" onClick={() => delLang(i)} disabled={cfg.supported_languages.length === 1}>
                <Trash2 className="h-3.5 w-3.5 text-red-500" />
              </Button>
            </div>
          ))}
          <Button size="sm" variant="outline" onClick={addLang}>
            <Plus className="mr-2 h-3 w-3" /> Add language
          </Button>
        </div>
        <div className="mt-3 w-40">
          <Label className="text-xs">Default language</Label>
          <Select value={cfg.default_language} onValueChange={(v) => update({ default_language: v })}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              {cfg.supported_languages
                .filter((l) => l.code)
                .map((l) => <SelectItem key={l.code} value={l.code}>{l.name || l.code}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </Section>

      {/* Fallback responses */}
      <Section
        title="Fallback responses"
        description="What the bot says in specific situations. Used verbatim when the LLM is unavailable or the input matches one of these triggers."
      >
        <div className="space-y-2">
          {FALLBACK_KEYS.map((k) => (
            <div key={k}>
              <Label className="text-xs">{k}</Label>
              <Textarea
                value={cfg.fallback_responses[k] || ""}
                onChange={(e) => updateFallback(k, e.target.value)}
                rows={2}
                placeholder={EMPTY_CFG.fallback_responses[k]}
              />
              <p className="text-[11px] text-slate-500 mt-1 leading-snug">{FALLBACK_HINTS[k]}</p>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

/* ─── helpers ─────────────────────────────────────────────────────────── */

function Section({ title, description, children }) {
  return (
    <div className="rounded-lg border bg-white p-4 space-y-3">
      <div>
        <h3 className="font-medium text-sm text-slate-700">{title}</h3>
        {description && <p className="text-xs text-slate-500 mt-0.5">{description}</p>}
      </div>
      {children}
    </div>
  );
}

function Grid2({ children }) {
  return <div className="grid grid-cols-2 gap-3">{children}</div>;
}

function Field({ label, value, onChange, placeholder, hint }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <Input value={value || ""} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      {hint && <p className="text-[11px] text-slate-500 mt-1 leading-snug">{hint}</p>}
    </div>
  );
}

function ColorField({ label, value, onChange, hint }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <div className="flex gap-2 items-center">
        <Input type="color" value={value || "#000000"} onChange={(e) => onChange(e.target.value)} className="w-12 h-9 p-1 cursor-pointer" />
        <Input value={value || ""} onChange={(e) => onChange(e.target.value)} placeholder="#1A237E" className="font-mono" />
      </div>
      {hint && <p className="text-[11px] text-slate-500 mt-1 leading-snug">{hint}</p>}
    </div>
  );
}
