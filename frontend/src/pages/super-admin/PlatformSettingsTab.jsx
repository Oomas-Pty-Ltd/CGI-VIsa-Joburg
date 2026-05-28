import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { RefreshCw, Save } from "lucide-react";
import { Section } from "@/components/admin/Section";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

/**
 * Platform Settings — singleton ops-level tuning (cache TTLs, crawler
 * interval, WhatsApp channel limits, frontend HTTP timeouts). Edits the
 * `platform_config` document via /api/super-admin/platform-config.
 *
 * Schema lives on the backend in services/platform_config.DEFAULTS — this
 * tab reads `defaults` from the GET response and renders one row per key.
 * Empty / 0 / [] means "inherit the platform default" (the row shows that
 * default in the hint underneath).
 */
export default function PlatformSettingsTab({ token }) {
  const [config, setConfig]     = useState({});
  const [defaults, setDefaults] = useState({});
  const [envOver, setEnvOver]   = useState({});
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/super-admin/platform-config`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setConfig(res.data.config || {});
      setDefaults(res.data.defaults || {});
      setEnvOver(res.data.env_overrides || {});
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load platform config");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  const setVal = (key, val) => setConfig((c) => ({ ...c, [key]: val }));

  const handleSave = async () => {
    setSaving(true);
    try {
      // Coerce numeric values back to ints before PUT — text inputs always
      // give us strings, but the backend validates the type against the
      // default. Lists stay as JSON arrays (already parsed in the editor).
      const patch = {};
      for (const [k, v] of Object.entries(config)) {
        const dflt = defaults[k];
        if (typeof dflt === "number" && typeof v === "string") {
          patch[k] = v.trim() === "" ? 0 : Number(v);
        } else {
          patch[k] = v;
        }
      }
      const res = await axios.put(`${API}/super-admin/platform-config`, patch, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setConfig(res.data.config || {});
      toast.success("Platform settings saved");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-sm text-muted-foreground">Loading platform config…</div>;
  }

  // Group keys by prefix so the UI scans top-to-bottom in a logical order.
  // Anything that doesn't match a known group falls into "Other".
  const groups = [
    {
      title: "Cache TTLs (seconds)",
      keys: [
        "cache_bot_config_ttl_seconds",
        "cache_tenant_ttl_seconds",
        "cache_service_registry_ttl_seconds",
        "cache_messaging_channel_ttl_seconds",
        "cache_token_blacklist_ttl_seconds",
      ],
    },
    {
      title: "Knowledge base",
      keys: [
        "kb_cache_ttl_seconds",
        "kb_blocked_kw_ttl_seconds",
        "kb_deep_scan_ttl_seconds",
        "kb_crawl_interval_seconds",
        "kb_hit_threshold",
        "kb_max_deep_urls",
      ],
    },
    {
      title: "Maintenance loops",
      keys: ["session_cleanup_interval_seconds", "notification_job_interval_seconds"],
    },
    {
      title: "Auth",
      keys: ["dev_auth_mode"],
    },
    {
      title: "WhatsApp channel",
      keys: [
        "whatsapp_body_char_limit",
        "whatsapp_text_char_limit",
        "whatsapp_visible_service_categories",
        "whatsapp_ui_phrase_mappings",
      ],
    },
    {
      title: "Frontend HTTP timeouts (ms)",
      keys: [
        "frontend_chat_stream_timeout_ms",
        "frontend_tts_timeout_ms",
        "frontend_inactivity_check_ms",
        "frontend_tts_chunk_size_chars",
      ],
    },
    {
      // Platform-wide limits on /chat + /chat/stream. 0 on any row disables
      // that dimension. Per-second rows are off (0) by default — enable with
      // care if many users share an IP behind NAT.
      title: "Rate limits (0 = no limit on that dimension)",
      keys: [
        "rate_limit_ip_per_sec",
        "rate_limit_ip_per_min",
        "rate_limit_ip_per_hour",
        "rate_limit_burst_multiplier",
        "rate_limit_user_per_sec",
        "rate_limit_user_per_min",
        "rate_limit_user_per_day",
      ],
    },
  ];

  const knownKeys = new Set(groups.flatMap((g) => g.keys));
  const otherKeys = Object.keys(defaults).filter((k) => !knownKeys.has(k));
  if (otherKeys.length) groups.push({ title: "Other", keys: otherKeys });

  return (
    <div className="space-y-4">
      <div className="flex justify-end gap-2 flex-wrap">
        <Button variant="outline" size="sm" onClick={fetchConfig}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> Reload
        </Button>
        <Button size="sm" onClick={handleSave} disabled={saving}>
          <Save className="w-3.5 h-3.5 mr-1.5" /> {saving ? "Saving…" : "Save changes"}
        </Button>
      </div>

      {groups.map((group) => (
        <Section key={group.title} title={group.title}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {group.keys.map((key) => (
              <PlatformField
                key={key}
                fieldKey={key}
                value={config[key]}
                defaultValue={defaults[key]}
                envVar={envOver[key]}
                onChange={(v) => setVal(key, v)}
              />
            ))}
          </div>
        </Section>
      ))}
    </div>
  );
}


/** One row in the Platform Settings editor. Picks a control based on the
 *  type of the platform default (number → numeric input, list → JSON-array
 *  textarea, string → text input). */
function PlatformField({ fieldKey, value, defaultValue, envVar, onChange }) {
  const label = fieldKey
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());

  // List default → JSON-array textarea (so admins can paste regex objects, etc.).
  if (Array.isArray(defaultValue)) {
    const raw = Array.isArray(value) ? JSON.stringify(value, null, 2) : (value ?? "[]");
    return (
      <div className="md:col-span-2">
        <Label className="text-xs">{label}</Label>
        <Textarea
          value={raw}
          onChange={(e) => {
            try {
              onChange(JSON.parse(e.target.value));
            } catch {
              // Keep the raw string so the user can finish editing; the
              // backend will reject malformed JSON on save.
              onChange(e.target.value);
            }
          }}
          rows={4}
          className="font-mono text-xs"
        />
        <p className="text-xs text-muted-foreground mt-1 leading-snug">
          JSON array. Platform default: <code>{JSON.stringify(defaultValue)}</code>.
          {envVar && <> Env var: <code>{envVar}</code>.</>}
        </p>
      </div>
    );
  }

  // Boolean default → toggle switch.
  if (typeof defaultValue === "boolean") {
    const on = value === undefined || value === null ? defaultValue : !!value;
    return (
      <div>
        <Label className="text-xs">{label}</Label>
        <div className="flex items-center gap-2 mt-1">
          <Switch checked={on} onCheckedChange={(v) => onChange(v)} />
          <span className="text-sm text-muted-foreground">{on ? "On" : "Off"}</span>
        </div>
        <p className="text-xs text-muted-foreground mt-1 leading-snug">
          Platform default: <code>{String(defaultValue)}</code>.
          {envVar && <> Env var: <code>{envVar}</code>.</>}
        </p>
      </div>
    );
  }

  // Numeric default → numeric input. Empty string is allowed and means
  // "inherit default" (the backend treats 0 the same way for some keys).
  if (typeof defaultValue === "number") {
    return (
      <div>
        <Label className="text-xs">{label}</Label>
        <Input
          type="number"
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={String(defaultValue)}
        />
        <p className="text-xs text-muted-foreground mt-1 leading-snug">
          Platform default: <code>{defaultValue}</code>.
          {envVar && <> Env var: <code>{envVar}</code>.</>}
        </p>
      </div>
    );
  }

  // String default → text input.
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <Input
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={String(defaultValue ?? "")}
      />
      <p className="text-xs text-muted-foreground mt-1 leading-snug">
        Platform default: <code>{String(defaultValue)}</code>.
        {envVar && <> Env var: <code>{envVar}</code>.</>}
      </p>
    </div>
  );
}
