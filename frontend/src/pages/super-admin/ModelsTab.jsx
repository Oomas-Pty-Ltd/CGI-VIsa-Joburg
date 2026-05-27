/**
 * Platform model registry — super-admin CRUD over `platform_models`.
 *
 * Replaces the hardcoded MODEL_MAP + _PRICING dicts that used to live
 * in the backend code. A super-admin can add a new model, edit pricing
 * / api routing, and toggle enabled — and the running chat path picks
 * up the change on the next 60s cache cycle. Tenants then pick from
 * this list via the per-company "Models" assignment dialog.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  Plus, RefreshCw, Edit2, Trash2, Cpu, Check, Ban, AlertCircle, CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Section } from "@/components/admin/Section";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { EmptyState } from "@/components/admin/EmptyState";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const EMPTY_MODEL = {
  key: "",
  display_name: "",
  provider: "openai",
  api_model: "",
  description: "",
  pricing: { input_per_1m_usd: 0, output_per_1m_usd: 0 },
  capabilities: { vision: true, streaming: true, max_tokens: 16384 },
  enabled: true,
};

function fmtUSD(v) {
  if (v == null) return "—";
  return `$${Number(v).toFixed(2)}`;
}

export default function ModelsTab({ token }) {
  const [models, setModels] = useState([]);
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null);   // "new" | row
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const fetchModels = useCallback(async () => {
    setLoading(true);
    try {
      // Two independent fetches. The Providers banner is a nice-to-have
      // — if its endpoint is missing (older backend, network blip), we
      // still want the models list to render. So we fail-soft on
      // /providers/status and don't toast for it.
      const modelsRes = await fetch(`${API}/super-admin/models`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const modelsData = await modelsRes.json();
      if (!modelsRes.ok) throw new Error(modelsData.detail || "Failed");
      setModels(modelsData.models || []);

      try {
        const provRes = await fetch(`${API}/super-admin/providers/status`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (provRes.ok) {
          const provData = await provRes.json();
          setProviders(provData.providers || []);
        } else {
          setProviders([]);
        }
      } catch {
        setProviders([]);
      }
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchModels(); }, [fetchModels]);

  const toggleEnabled = async (row) => {
    try {
      const res = await fetch(`${API}/super-admin/models/${row.key}`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !row.enabled }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      toast.success(`${row.key} ${!row.enabled ? "enabled" : "disabled"}`);
      fetchModels();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleDeleteConfirmed = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      const res = await fetch(`${API}/super-admin/models/${confirmDelete.key}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Failed");
      toast.success(`Removed ${confirmDelete.key}`);
      setConfirmDelete(null);
      fetchModels();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={fetchModels} disabled={loading}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
        <Button size="sm" onClick={() => setEditing("new")}>
          <Plus className="w-3.5 h-3.5 mr-1.5" /> Add model
        </Button>
      </div>

      <ProvidersStatus providers={providers} />

      <Section
        title="Model registry"
        description="Every model the platform supports. Tenants pick from this list via the per-company Models assignment. Disabled rows are hidden from tenants but kept for editing."
        bodyClassName="p-0"
      >
        {models.length === 0 && !loading ? (
          <EmptyState
            icon={Cpu}
            title="No models registered yet"
            description="Seed the registry by running migration 0011, or add one manually."
            action={<Button size="sm" onClick={() => setEditing("new")}><Plus className="w-3.5 h-3.5 mr-1.5" /> Add model</Button>}
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground border-b border-border">
              <tr>
                <th className="px-4 py-2.5 font-medium">Model</th>
                <th className="px-3 py-2.5 font-medium">Provider</th>
                <th className="px-3 py-2.5 font-medium">API model</th>
                <th className="px-3 py-2.5 font-medium text-right">In $/1M</th>
                <th className="px-3 py-2.5 font-medium text-right">Out $/1M</th>
                <th className="px-3 py-2.5 font-medium text-center w-20">Enabled</th>
                <th className="px-3 py-2.5 font-medium text-right w-24">Actions</th>
              </tr>
            </thead>
            <tbody>
              {models.map((m) => (
                <tr key={m.key} className="border-t border-border hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <div className="font-medium text-foreground">{m.display_name || m.key}</div>
                    <div className="text-xs font-mono text-muted-foreground">{m.key}</div>
                    {m.description && (
                      <div className="text-[11px] text-muted-foreground mt-0.5 max-w-md leading-snug">
                        {m.description}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <Badge variant="outline" className="text-[10px] uppercase tracking-wider">{m.provider}</Badge>
                  </td>
                  <td className="px-3 py-3 font-mono text-xs text-muted-foreground">{m.api_model}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{fmtUSD(m.pricing?.input_per_1m_usd)}</td>
                  <td className="px-3 py-3 text-right tabular-nums">{fmtUSD(m.pricing?.output_per_1m_usd)}</td>
                  <td className="px-3 py-3 text-center">
                    <Switch checked={!!m.enabled} onCheckedChange={() => toggleEnabled(m)} />
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex justify-end items-center gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(m)} aria-label="Edit model" className="h-8 w-8 p-0">
                        <Edit2 className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        size="sm" variant="ghost"
                        onClick={() => setConfirmDelete(m)}
                        aria-label="Delete model"
                        className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      {editing && (
        <ModelDialog
          token={token}
          model={editing === "new" ? null : editing}
          providers={providers}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchModels(); }}
        />
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title={`Delete model ${confirmDelete?.key || ""}?`}
        description="Tenants currently assigned this model will need a new default before this delete succeeds — the backend refuses with a 400 if it's still in use."
        confirmLabel="Delete model"
        destructive
        loading={deleting}
        onConfirm={handleDeleteConfirmed}
      />
    </div>
  );
}

/* ─── Add / edit dialog ─────────────────────────────────────────────────── */

function ModelDialog({ token, model, providers = [], onClose, onSaved }) {
  const isNew = !model;
  // Only providers that are fully runtime-ready (env key set + SDK
  // installed + LlmChat dispatch wired) are pickable. Showing the
  // others would only confuse — the backend would 400 on save anyway.
  const readyProviders = providers.filter((p) => p.ready);
  const [draft, setDraft] = useState(() => {
    if (model) return { ...EMPTY_MODEL, ...model };
    // For new rows, default to the first ready provider so the operator
    // doesn't have to pick from an empty dropdown.
    return { ...EMPTY_MODEL, provider: readyProviders[0]?.provider || "openai" };
  });
  const [saving, setSaving] = useState(false);

  const update = (patch) => setDraft((d) => ({ ...d, ...patch }));
  const updatePricing = (patch) => setDraft((d) => ({ ...d, pricing: { ...(d.pricing || {}), ...patch } }));
  const updateCaps = (patch) => setDraft((d) => ({ ...d, capabilities: { ...(d.capabilities || {}), ...patch } }));

  const handleSave = async () => {
    if (isNew && !draft.key.trim()) { toast.error("key is required"); return; }
    if (!draft.display_name.trim()) { toast.error("Display name is required"); return; }
    if (!draft.api_model.trim()) { toast.error("API model is required"); return; }

    const body = {
      display_name: draft.display_name.trim(),
      provider:     draft.provider.trim(),
      api_model:    draft.api_model.trim(),
      description:  draft.description || "",
      pricing: {
        input_per_1m_usd:  Number(draft.pricing.input_per_1m_usd)  || 0,
        output_per_1m_usd: Number(draft.pricing.output_per_1m_usd) || 0,
      },
      capabilities: {
        vision:     !!draft.capabilities?.vision,
        streaming:  !!draft.capabilities?.streaming,
        max_tokens: Number(draft.capabilities?.max_tokens) || null,
      },
      enabled: !!draft.enabled,
    };

    setSaving(true);
    try {
      const url = isNew
        ? `${API}/super-admin/models`
        : `${API}/super-admin/models/${model.key}`;
      const payload = isNew ? { key: draft.key.trim(), ...body } : body;
      const res = await fetch(url, {
        method: isNew ? "POST" : "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Save failed");
      toast.success(isNew ? `Created ${data.key}` : `Updated ${data.key}`);
      onSaved();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isNew ? "Add model" : `Edit ${model.key}`}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">key <span className="text-muted-foreground">(immutable identifier)</span></Label>
              <Input
                value={draft.key}
                onChange={(e) => update({ key: e.target.value })}
                placeholder="gpt-4o-mini"
                className="font-mono mt-1"
                disabled={!isNew}
              />
              <p className="text-xs text-muted-foreground mt-1 leading-snug">
                Tenant-facing key. Lowercase letters, digits, hyphen/dot/underscore. Used in cost rows + tenant assignments — can't be renamed after creation.
              </p>
            </div>
            <div>
              <Label className="text-xs">Display name</Label>
              <Input
                value={draft.display_name}
                onChange={(e) => update({ display_name: e.target.value })}
                placeholder="GPT-4o mini"
                className="mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1 leading-snug">
                Human-friendly label shown to operators in dropdowns.
              </p>
            </div>
          </div>

          <div>
            <Label className="text-xs">Description</Label>
            <Textarea
              value={draft.description || ""}
              onChange={(e) => update({ description: e.target.value })}
              rows={2}
              className="mt-1"
              placeholder="Fast, low-cost general-purpose model."
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Provider</Label>
              {readyProviders.length === 0 ? (
                <>
                  <Input value="" disabled placeholder="No ready providers" className="mt-1" />
                  <p className="text-xs text-destructive mt-1 leading-snug">
                    No providers are runtime-ready. Check the Providers status banner above
                    — set an env key, install the SDK, and ensure dispatch is wired before
                    registering a model.
                  </p>
                </>
              ) : (
                <>
                  <Select value={draft.provider} onValueChange={(v) => update({ provider: v })}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {readyProviders.map((p) => (
                        <SelectItem key={p.provider} value={p.provider}>
                          {p.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground mt-1 leading-snug">
                    Only providers that are fully wired up are listed. Others appear on the
                    Providers status card with what's missing.
                  </p>
                </>
              )}
            </div>
            <div>
              <Label className="text-xs">API model</Label>
              <Input
                value={draft.api_model}
                onChange={(e) => update({ api_model: e.target.value })}
                placeholder="gpt-4o-mini"
                className="font-mono mt-1"
              />
              <p className="text-xs text-muted-foreground mt-1 leading-snug">
                What gets sent to the provider's API. Differs from <code>key</code> only when aliasing — e.g. <code>gpt-5.2</code> → <code>gpt-4o-mini</code>.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Input price (USD per 1M tokens)</Label>
              <Input
                type="number"
                step="0.01"
                value={draft.pricing?.input_per_1m_usd ?? 0}
                onChange={(e) => updatePricing({ input_per_1m_usd: e.target.value })}
                className="mt-1 font-mono"
              />
            </div>
            <div>
              <Label className="text-xs">Output price (USD per 1M tokens)</Label>
              <Input
                type="number"
                step="0.01"
                value={draft.pricing?.output_per_1m_usd ?? 0}
                onChange={(e) => updatePricing({ output_per_1m_usd: e.target.value })}
                className="mt-1 font-mono"
              />
            </div>
          </div>

          <div>
            <Label className="text-xs">Capabilities <span className="text-muted-foreground">(declared metadata)</span></Label>
            <p className="text-xs text-muted-foreground mt-1 mb-2 leading-snug">
              These flags describe what this model <em>can</em> do — they're trusted as-is, not
              auto-discovered from the provider's API. The runtime uses them to decide things
              like whether to offer image uploads. Set them to match the provider's published
              spec.
            </p>
            <div className="grid grid-cols-3 gap-3 items-end">
              <div className="flex items-center gap-2">
                <Switch
                  checked={!!draft.capabilities?.vision}
                  onCheckedChange={(v) => updateCaps({ vision: v })}
                />
                <span className="text-sm">Vision</span>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={!!draft.capabilities?.streaming}
                  onCheckedChange={(v) => updateCaps({ streaming: v })}
                />
                <span className="text-sm">Streaming</span>
              </div>
              <div>
                <Label className="text-xs">Max output tokens</Label>
                <Input
                  type="number"
                  value={draft.capabilities?.max_tokens || ""}
                  onChange={(e) => updateCaps({ max_tokens: e.target.value })}
                  placeholder="16384"
                  className="mt-1 font-mono"
                />
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-2 border-t border-border">
            <Switch checked={!!draft.enabled} onCheckedChange={(v) => update({ enabled: v })} />
            <span className="text-sm">
              {draft.enabled
                ? <span className="text-success inline-flex items-center gap-1"><Check className="h-3.5 w-3.5" /> Enabled — tenants can assign this model</span>
                : <span className="text-muted-foreground inline-flex items-center gap-1"><Ban className="h-3.5 w-3.5" /> Disabled — hidden from tenant assignment</span>}
            </span>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t border-border">
          <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? "Saving…" : isNew ? "Create model" : "Save changes"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ─── Providers status banner ────────────────────────────────────────────
 *
 * A model is only as good as the provider runtime behind it. This card
 * tells the operator which providers are wired up RIGHT NOW versus which
 * ones they'd need to install + configure before adding a model under
 * that provider.
 *
 * "Configured" = the API-key env var is present in backend/.env.
 * "Runtime supported" = the platform actually ships a client (LlmChat
 * dispatch). Both must be true for the model to work end-to-end.
 */
function ProvidersStatus({ providers }) {
  if (!providers || providers.length === 0) return null;
  return (
    <Section
      title="LLM providers"
      description="Status of the provider runtimes that back the model registry. Adding a model with a provider that's not configured / supported will register the row but chat calls using it will fail at runtime."
    >
      <ul className="space-y-2">
        {providers.map((p) => {
          const ok = p.configured && p.runtime_supported;
          const partial = p.configured !== p.runtime_supported;
          const tone = ok ? "success" : partial ? "warning" : "muted";
          const toneClasses = {
            success: "border-success/30 bg-success/5",
            warning: "border-warning/30 bg-warning/5",
            muted:   "border-border bg-muted/30",
          }[tone];
          const Icon = ok ? CheckCircle2 : AlertCircle;
          const iconClass = ok ? "text-success" : partial ? "text-warning" : "text-muted-foreground";
          return (
            <li key={p.provider} className={`rounded-lg border px-3 py-2.5 ${toneClasses}`}>
              <div className="flex items-start gap-3">
                <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${iconClass}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-foreground">{p.label}</span>
                    <span className="text-[10px] uppercase tracking-wider font-mono px-1.5 py-0.5 rounded bg-card border border-border text-muted-foreground">
                      provider:{p.provider}
                    </span>
                    {p.configured ? (
                      <span className="text-[10px] uppercase tracking-wider font-medium text-success">
                        env key set{p.matched_env_var && p.matched_env_var !== p.env_var ? ` (via ${p.matched_env_var})` : ""}
                      </span>
                    ) : (
                      <span className="text-[10px] uppercase tracking-wider font-medium text-muted-foreground">
                        env key missing
                      </span>
                    )}
                    {p.runtime_supported ? (
                      <span className="text-[10px] uppercase tracking-wider font-medium text-success">
                        runtime ready
                      </span>
                    ) : (
                      <span className="text-[10px] uppercase tracking-wider font-medium text-warning">
                        runtime not wired
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1 leading-snug">
                    {p.install_hint}
                    {p.env_var && (
                      <>
                        {" "}<code className="font-mono bg-card border border-border rounded px-1 py-0.5">{p.env_var}</code>
                      </>
                    )}
                  </p>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
