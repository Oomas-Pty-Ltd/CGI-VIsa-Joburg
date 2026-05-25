/**
 * Super-admin tab — Tenant Services (Sprint 4D / 4E)
 *
 * CRUD over `tenant_services` rows, including the rich field editor
 * for the three step types (input / conditional / api_call).
 *
 * The tenant selector at the top filters which tenant's catalogue is
 * shown — super-admin doesn't pick a default tenant, the operator must
 * choose explicitly.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  Plus, Trash2, Edit2, RefreshCw, Eye, EyeOff, Workflow, ExternalLink, GripVertical,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import FieldEditor from "./FieldEditor";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function TenantServicesTab({ companies, token, singleTenant = false }) {
  const [tenantId, setTenantId] = useState("");
  const [services, setServices] = useState([]);
  const [loading, setLoading]   = useState(false);
  const [editing, setEditing]   = useState(null); // null | row | "new"

  // Default to the first available tenant on mount
  useEffect(() => {
    if (!tenantId && companies.length > 0) setTenantId(companies[0].id);
  }, [companies, tenantId]);

  const fetchServices = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/super-admin/services/${tenantId}?include_disabled=true`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed");
      setServices(data.services || []);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [tenantId, token]);

  useEffect(() => { fetchServices(); }, [fetchServices]);

  const handleDelete = async (svc) => {
    if (!window.confirm(`Delete service "${svc.name}"? Sessions mid-flow on this service will be abandoned with a "no longer available" message on their next turn.`)) return;
    try {
      const res = await fetch(`${API}/super-admin/services/${tenantId}/${svc.service_key}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Delete failed");
      }
      toast.success(`Deleted ${svc.service_key}`);
      fetchServices();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const toggleEnabled = async (svc) => {
    try {
      const res = await fetch(`${API}/super-admin/services/${tenantId}/${svc.service_key}`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !svc.enabled }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Save failed");
      toast.success(`${svc.service_key} is now ${data.enabled ? "enabled" : "disabled"}`);
      fetchServices();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header + actions */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-xl font-semibold">{singleTenant ? "Services" : "Tenant Services"}</h2>
          <p className="text-sm text-slate-500">
            {singleTenant
              ? "Configure what services the chatbot offers — and how it walks the user through each one."
              : "Configure what services the chatbot offers for each tenant — and how it walks the user through them."}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchServices} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button onClick={() => setEditing("new")} disabled={!tenantId}>
            <Plus className="mr-2 h-4 w-4" /> New service
          </Button>
        </div>
      </div>

      {/* Tenant selector — only when the operator has multiple tenants to pick from */}
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

      {/* Services list */}
      <div className="rounded-lg border bg-white overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading…</div>
        ) : services.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            This tenant has no services yet. Click <strong>New service</strong> to add one.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-left">
              <tr>
                <th className="px-3 py-2 w-10">#</th>
                <th className="px-3 py-2">Service</th>
                <th className="px-3 py-2">Category</th>
                <th className="px-3 py-2">Fields</th>
                <th className="px-3 py-2">Docs</th>
                <th className="px-3 py-2">Enabled</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {services.map((s) => {
                const stepTypes = (s.fields || []).map((f) => f.type || "input");
                const nonInput = stepTypes.filter((t) => t !== "input").length;
                return (
                  <tr key={s.service_key} className="border-t hover:bg-slate-50">
                    <td className="px-3 py-2 text-slate-400">
                      <span className="flex items-center gap-1">
                        <GripVertical className="h-3.5 w-3.5" />
                        {s.display_order}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium">{s.name}</div>
                      <div className="text-xs text-slate-400 font-mono">{s.service_key}</div>
                    </td>
                    <td className="px-3 py-2">
                      {s.category === "TYPE_B" ? (
                        <Badge variant="secondary" className="gap-1">
                          <ExternalLink className="h-3 w-3" /> Redirect
                        </Badge>
                      ) : (
                        <Badge variant="outline">In-house</Badge>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <span className="font-mono">{(s.fields || []).length}</span>
                      {nonInput > 0 && (
                        <span className="ml-1 text-violet-600">
                          <Workflow className="h-3 w-3 inline" /> {nonInput} step{nonInput > 1 ? "s" : ""}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{(s.documents || []).length}</td>
                    <td className="px-3 py-2">
                      <Switch checked={!!s.enabled} onCheckedChange={() => toggleEnabled(s)} />
                    </td>
                    <td className="px-3 py-2 text-right space-x-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(s)}>
                        <Edit2 className="h-3.5 w-3.5" />
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => handleDelete(s)}>
                        <Trash2 className="h-3.5 w-3.5 text-red-500" />
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {editing && (
        <ServiceDialog
          tenantId={tenantId}
          service={editing === "new" ? null : editing}
          token={token}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchServices(); }}
        />
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */

const EMPTY_SERVICE = {
  service_key:   "",
  name:          "",
  description:   "",
  category:      "TYPE_A",
  external_url:  "",
  enabled:       true,
  display_order: null,
  documents:     [""],
  fields:        [],
};

function ServiceDialog({ tenantId, service, token, onClose, onSaved }) {
  const isNew = !service;
  const [draft, setDraft] = useState(service ? { ...EMPTY_SERVICE, ...service } : EMPTY_SERVICE);
  const [saving, setSaving] = useState(false);

  const update = (patch) => setDraft((d) => ({ ...d, ...patch }));

  const handleSave = async () => {
    if (!draft.name.trim()) { toast.error("Name is required"); return; }
    if (isNew && !draft.service_key.trim()) { toast.error("service_key is required"); return; }
    if (draft.category === "TYPE_B" && !draft.external_url) {
      toast.error("TYPE_B services require an external_url"); return;
    }

    const body = {
      name:          draft.name,
      description:   draft.description,
      documents:     (draft.documents || []).map((d) => d.trim()).filter(Boolean),
      fields:        draft.fields,
      category:      draft.category,
      external_url:  draft.external_url || null,
      enabled:       draft.enabled,
    };
    if (draft.display_order !== null && draft.display_order !== "" && draft.display_order !== undefined) {
      body.display_order = Number(draft.display_order);
    }

    setSaving(true);
    try {
      const url = isNew
        ? `${API}/super-admin/services/${tenantId}`
        : `${API}/super-admin/services/${tenantId}/${service.service_key}`;
      const payload = isNew ? { service_key: draft.service_key, ...body } : body;
      const res = await fetch(url, {
        method: isNew ? "POST" : "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Save failed");
      toast.success(isNew ? `Created ${data.service_key}` : `Updated ${data.service_key}`);
      onSaved();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  /* ─── docs CRUD ─── */
  const setDoc = (i, v) => setDraft((d) => {
    const docs = [...(d.documents || [])]; docs[i] = v; return { ...d, documents: docs };
  });
  const addDoc = () => setDraft((d) => ({ ...d, documents: [...(d.documents || []), ""] }));
  const delDoc = (i) => setDraft((d) => {
    const docs = [...(d.documents || [])]; docs.splice(i, 1); return { ...d, documents: docs };
  });

  /* ─── fields CRUD ─── */
  const setField = (i, v) => setDraft((d) => {
    const fields = [...(d.fields || [])]; fields[i] = v; return { ...d, fields };
  });
  const addField = () => setDraft((d) => ({
    ...d,
    fields: [...(d.fields || []), { key: "", type: "input", question: "" }],
  }));
  const delField = (i) => setDraft((d) => {
    const fields = [...(d.fields || [])]; fields.splice(i, 1); return { ...d, fields };
  });
  const moveField = (i, dir) => setDraft((d) => {
    const fields = [...(d.fields || [])];
    const j = i + dir;
    if (j < 0 || j >= fields.length) return d;
    [fields[i], fields[j]] = [fields[j], fields[i]];
    return { ...d, fields };
  });

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isNew ? "New service" : `Edit ${service.service_key}`}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* basic fields */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">service_key <span className="text-slate-400">(immutable, lower_snake_case)</span></Label>
              <Input
                value={draft.service_key}
                onChange={(e) => update({ service_key: e.target.value })}
                placeholder="passport_renewal"
                className="font-mono"
                disabled={!isNew}
              />
              <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                Internal identifier used by the backend and logs. Lower-case letters, digits and underscores only. Cannot be changed after creation.
              </p>
            </div>
            <div>
              <Label className="text-xs">Display name</Label>
              <Input value={draft.name} onChange={(e) => update({ name: e.target.value })} placeholder="Passport Renewal" />
              <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                Human-friendly name the chatbot shows the user in menus and confirmations.
              </p>
            </div>
          </div>

          <div>
            <Label className="text-xs">Description (shown before consent)</Label>
            <Textarea value={draft.description} onChange={(e) => update({ description: e.target.value })} rows={3} />
            <p className="text-[11px] text-slate-500 mt-1 leading-snug">
              One- or two-sentence summary the user reads before agreeing to start this service. Explain what they'll get and what you'll ask for.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-3 items-end">
            <div>
              <Label className="text-xs">Category</Label>
              <Select value={draft.category} onValueChange={(v) => update({ category: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="TYPE_A">TYPE_A — collect in-house</SelectItem>
                  <SelectItem value="TYPE_B">TYPE_B — redirect to portal</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                <strong>TYPE_A</strong>: the bot collects all fields and creates an application here.
                {" "}<strong>TYPE_B</strong>: the bot answers questions and then hands the user off to an external portal.
              </p>
            </div>
            <div className="col-span-2">
              <Label className="text-xs">External URL {draft.category === "TYPE_B" && <span className="text-red-500">*</span>}</Label>
              <Input
                value={draft.external_url || ""}
                onChange={(e) => update({ external_url: e.target.value })}
                placeholder="https://portal.example.gov"
              />
              <p className="text-[11px] text-slate-500 mt-1 leading-snug">
                Where the user is sent for TYPE_B services. Required when category is TYPE_B; ignored otherwise.
              </p>
            </div>
          </div>

          <div className="flex gap-6 items-center">
            <label className="text-sm flex items-center gap-2">
              <Switch checked={!!draft.enabled} onCheckedChange={(v) => update({ enabled: v })} />
              Enabled (chatbot offers this service)
            </label>
            <div>
              <Label className="text-xs">Display order</Label>
              <Input
                type="number"
                value={draft.display_order ?? ""}
                onChange={(e) => update({ display_order: e.target.value === "" ? null : Number(e.target.value) })}
                placeholder="auto"
                className="w-24 h-8"
              />
              <p className="text-[11px] text-slate-500 mt-1 leading-snug w-56">
                Position in the service menu (lower number = higher). Leave blank for automatic ordering.
              </p>
            </div>
          </div>

          {/* docs */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <Label className="text-xs">Required documents</Label>
              <Button size="sm" variant="outline" onClick={addDoc}><Plus className="h-3 w-3 mr-1" /> Add doc</Button>
            </div>
            <p className="text-[11px] text-slate-500 mb-2 leading-snug">
              One row per document the applicant must provide. The bot lists these to the user before starting the form.
            </p>
            <div className="space-y-1">
              {(draft.documents || []).map((doc, i) => (
                <div key={i} className="flex gap-1">
                  <Input value={doc} onChange={(e) => setDoc(i, e.target.value)} placeholder='e.g. "Valid passport — original + photocopy"' />
                  <Button size="sm" variant="ghost" onClick={() => delDoc(i)}>
                    <Trash2 className="h-3.5 w-3.5 text-red-500" />
                  </Button>
                </div>
              ))}
            </div>
          </div>

          {/* fields with rich editor */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <Label className="text-xs">Form fields & flow steps</Label>
              <Button size="sm" variant="outline" onClick={addField}><Plus className="h-3 w-3 mr-1" /> Add field</Button>
            </div>
            <p className="text-[11px] text-slate-500 mb-2 leading-snug">
              The questions the bot asks, in order. Each row is one input, branching condition, or API call step.
            </p>
            <div className="space-y-2">
              {(draft.fields || []).map((f, i) => (
                <FieldEditor
                  key={i}
                  field={f}
                  index={i}
                  totalFields={draft.fields.length}
                  priorFieldKeys={draft.fields.slice(0, i).map((p) => p.key).filter(Boolean)}
                  onChange={(v) => setField(i, v)}
                  onDelete={() => delField(i)}
                  onMoveUp={() => moveField(i, -1)}
                  onMoveDown={() => moveField(i, +1)}
                />
              ))}
              {draft.fields.length === 0 && (
                <div className="text-center text-slate-400 text-sm py-4 border border-dashed rounded">
                  No fields yet. Add an input field for each piece of data to collect.
                </div>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : isNew ? "Create" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
