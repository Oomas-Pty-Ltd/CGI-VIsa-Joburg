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
  Plus, Trash2, Edit2, RefreshCw, Workflow, ExternalLink, Inbox, Info, ChevronUp, ChevronDown,
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
import { Section } from "@/components/admin/Section";
import { EmptyState } from "@/components/admin/EmptyState";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import FieldEditor from "./FieldEditor";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function TenantServicesTab({ companies, token, singleTenant = false }) {
  const [tenantId, setTenantId] = useState("");
  const [services, setServices] = useState([]);
  const [loading, setLoading]   = useState(false);
  const [editing, setEditing]   = useState(null); // null | row | "new"
  const [confirmDelete, setConfirmDelete] = useState(null); // service row pending confirmation
  const [deleting, setDeleting] = useState(false);

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

  const handleDeleteConfirmed = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      const res = await fetch(`${API}/super-admin/services/${tenantId}/${confirmDelete.service_key}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Delete failed");
      }
      toast.success(`Deleted ${confirmDelete.service_key}`);
      setConfirmDelete(null);
      fetchServices();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setDeleting(false);
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
      {/* Top bar: tenant picker (when applicable) + actions */}
      <div className="flex items-end justify-between gap-3 flex-wrap">
        {!singleTenant ? (
          <div className="w-72">
            <Label className="text-xs text-muted-foreground">Tenant</Label>
            <Select value={tenantId} onValueChange={setTenantId}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="Pick a tenant" /></SelectTrigger>
              <SelectContent>
                {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        ) : <div />}
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchServices} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button size="sm" onClick={() => setEditing("new")} disabled={!tenantId}>
            <Plus className="mr-1.5 h-3.5 w-3.5" /> New service
          </Button>
        </div>
      </div>

      {/* Services list */}
      {/* No title on this Section — the AdminShell already shows
          "Services" as the page header. The card is just a visual
          wrapper around the table; the helper text moved up to the
          page description so we don't render two stacked headings. */}
      <Section
        title="Catalogue"
        description="Drag-and-drop ordering isn't supported yet — change Display order in the edit dialog to move a row. Toggle Enabled to hide a service from the widget without deleting it."
        bodyClassName="p-0"
      >
        {loading ? (
          <div className="px-5 py-12 text-center text-sm text-muted-foreground">Loading…</div>
        ) : services.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title="No services yet"
            description="Add a service to start offering it in the chatbot. Each service collects its own form fields or redirects to an external portal."
            action={
              <Button size="sm" onClick={() => setEditing("new")} disabled={!tenantId}>
                <Plus className="mr-1.5 h-3.5 w-3.5" /> New service
              </Button>
            }
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-left text-xs uppercase tracking-wider">
              <tr>
                <th className="px-3 py-2.5 w-10 text-right">#</th>
                <th className="px-3 py-2.5">Service</th>
                <th className="px-3 py-2.5 w-24">Category</th>
                <th className="px-3 py-2.5 text-right w-16">Fields</th>
                <th className="px-3 py-2.5 text-right w-16">Docs</th>
                <th className="px-3 py-2.5 w-20 text-center">Enabled</th>
                <th className="px-3 py-2.5 text-right w-20">Actions</th>
              </tr>
            </thead>
            <tbody>
              {services.map((s) => {
                const stepTypes = (s.fields || []).map((f) => f.type || "input");
                const nonInput = stepTypes.filter((t) => t !== "input").length;
                return (
                  <tr key={s.service_key} className="border-t border-border hover:bg-muted/30">
                    <td className="px-3 py-3 text-muted-foreground tabular-nums text-right">{s.display_order}</td>
                    <td className="px-3 py-3">
                      <div className="font-medium text-foreground">{s.name}</div>
                      <div className="text-xs text-muted-foreground font-mono">{s.service_key}</div>
                    </td>
                    <td className="px-3 py-3">
                      {s.category === "TYPE_B" ? (
                        <Badge variant="secondary" className="gap-1">
                          <ExternalLink className="h-3 w-3" /> Redirect
                        </Badge>
                      ) : s.category === "INFO" ? (
                        <Badge variant="outline" className="gap-1 border-primary/30 text-primary bg-primary/5">
                          <Info className="h-3 w-3" /> Info
                        </Badge>
                      ) : (
                        <Badge variant="outline">In-house</Badge>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      <span className="font-mono text-foreground">{(s.fields || []).length}</span>
                      {nonInput > 0 && (
                        <span className="ml-2 text-primary inline-flex items-center gap-1 text-xs">
                          <Workflow className="h-3 w-3" /> {nonInput}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-3 font-mono text-right tabular-nums">{(s.documents || []).length}</td>
                    <td className="px-3 py-3 text-center">
                      <Switch checked={!!s.enabled} onCheckedChange={() => toggleEnabled(s)} />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex justify-end items-center gap-1">
                        <Button size="sm" variant="ghost" onClick={() => setEditing(s)} aria-label="Edit service" className="h-8 w-8 p-0">
                          <Edit2 className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setConfirmDelete(s)}
                          aria-label="Delete service"
                          className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Section>

      {editing && (
        <ServiceDialog
          tenantId={tenantId}
          service={editing === "new" ? null : editing}
          token={token}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchServices(); }}
        />
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title={`Delete service "${confirmDelete?.name || ""}"?`}
        description={
          'Sessions mid-flow on this service will be abandoned with a "no longer ' +
          'available" message on their next turn. Existing applications are kept.'
        }
        confirmLabel="Delete service"
        destructive
        loading={deleting}
        onConfirm={handleDeleteConfirmed}
      />
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
  emoji:         "",
  keywords:      [],
  enabled:       true,
  display_order: null,
  documents:     [""],
  fields:        [],
  post_confirm_message: "",
  hooks: {},
  // INFO services use this payload; ignored for TYPE_A/TYPE_B.
  info_content: { sections: [], primary_action: null },
};

// Sections in user-facing order. Visibility is category-dependent:
//
//   TYPE_A (in-house collect): Basics, Documents, Form fields, Messaging, Hooks
//   TYPE_B (redirect):         Basics, Messaging, Hooks
//   INFO   (reference card):   Basics, Content, Messaging
//
// The bot never runs the application state machine for INFO services, so
// Documents / Form fields / Hooks don't apply.
const ALL_DIALOG_SECTIONS = [
  { key: "basics",    label: "Basics" },
  { key: "content",   label: "Content",        infoOnly: true },
  { key: "docs",      label: "Documents",      typeAOnly: true },
  { key: "fields",    label: "Form fields",    typeAOnly: true },
  { key: "messaging", label: "Messaging",      hideForInfo: true },
  { key: "hooks",     label: "Workflow hooks", hideForInfo: true },
];

function sectionsFor(category) {
  if (category === "INFO") {
    return ALL_DIALOG_SECTIONS.filter((s) => !s.typeAOnly && !s.hideForInfo);
  }
  if (category === "TYPE_B") {
    return ALL_DIALOG_SECTIONS.filter((s) => !s.typeAOnly && !s.infoOnly);
  }
  // TYPE_A
  return ALL_DIALOG_SECTIONS.filter((s) => !s.infoOnly);
}

function ServiceDialog({ tenantId, service, token, onClose, onSaved }) {
  const isNew = !service;
  const [draft, setDraft] = useState(service ? { ...EMPTY_SERVICE, ...service } : EMPTY_SERVICE);
  const [saving, setSaving] = useState(false);
  const [section, setSection] = useState("basics");

  const update = (patch) => setDraft((d) => ({ ...d, ...patch }));

  const handleSave = async () => {
    if (!draft.name.trim()) { toast.error("Name is required"); return; }
    if (isNew && !draft.service_key.trim()) { toast.error("service_key is required"); return; }
    if (draft.category === "TYPE_B" && !draft.external_url) {
      toast.error("TYPE_B services require an external_url"); return;
    }

    // Drop fields the bot never uses for the chosen category — keeps
    // stored rows free of misleading half-state for a future operator.
    const isRedirect = draft.category === "TYPE_B";
    const isInfo     = draft.category === "INFO";
    const body = {
      name:          draft.name,
      description:   draft.description,
      documents:     (isRedirect || isInfo) ? [] : (draft.documents || []).map((d) => d.trim()).filter(Boolean),
      fields:        (isRedirect || isInfo) ? [] : draft.fields,
      category:      draft.category,
      external_url:  draft.external_url || null,
      emoji:         (draft.emoji || "").trim(),
      keywords:      (Array.isArray(draft.keywords) ? draft.keywords : (draft.keywords || "").split(","))
                       .map((k) => String(k).trim()).filter(Boolean),
      enabled:       draft.enabled,
      post_confirm_message: isInfo ? "" : (draft.post_confirm_message || "").trim(),
      hooks:         isInfo ? {} : (draft.hooks || {}),
      info_content:  isInfo ? (draft.info_content || { sections: [], primary_action: null }) : { sections: [], primary_action: null },
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

  // Hide irrelevant tabs based on category. If the operator flips to
  // TYPE_B while sitting on the now-hidden Documents or Form fields
  // tab, snap them back to Basics.
  const visibleSections = sectionsFor(draft.category);
  const visibleKeys = visibleSections.map((s) => s.key);
  if (!visibleKeys.includes(section)) {
    // Defer to next tick so we don't setState during render.
    setTimeout(() => setSection("basics"), 0);
  }

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>{isNew ? "New service" : `Edit ${service.service_key}`}</DialogTitle>
        </DialogHeader>

        {/* Sub-nav so the dialog isn't an endless wall of fields. The
            content area below scrolls; the nav + footer stay pinned. */}
        <div className="border-b border-border -mx-6">
          <div className="flex gap-1 px-6 -mb-px">
            {visibleSections.map(({ key, label }) => {
              const active = section === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSection(key)}
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

        <div className="overflow-y-auto -mx-6 px-6 flex-1 py-4 space-y-4">
          {section === "basics" && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">service_key <span className="text-muted-foreground">(immutable, lower_snake_case)</span></Label>
                  <Input
                    value={draft.service_key}
                    onChange={(e) => update({ service_key: e.target.value })}
                    placeholder="passport_renewal"
                    className="font-mono mt-1"
                    disabled={!isNew}
                  />
                  <p className="text-xs text-muted-foreground mt-1 leading-snug">
                    Internal identifier used by the backend and logs. Lower-case letters, digits and underscores only. Cannot be changed after creation.
                  </p>
                </div>
                <div>
                  <Label className="text-xs">Display name</Label>
                  <Input value={draft.name} onChange={(e) => update({ name: e.target.value })} placeholder="Passport Renewal" className="mt-1" />
                  <p className="text-xs text-muted-foreground mt-1 leading-snug">
                    Human-friendly name the chatbot shows the user in menus and confirmations.
                  </p>
                </div>
              </div>

              <div>
                <Label className="text-xs">Description (shown before consent)</Label>
                <Textarea value={draft.description} onChange={(e) => update({ description: e.target.value })} rows={3} className="mt-1" />
                <p className="text-xs text-muted-foreground mt-1 leading-snug">
                  One- or two-sentence summary the user reads before agreeing to start this service.
                </p>
              </div>

              <div className="grid grid-cols-3 gap-3 items-start">
                <div>
                  <Label className="text-xs">Category</Label>
                  <Select value={draft.category} onValueChange={(v) => update({ category: v })}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="TYPE_A">TYPE_A — collect in-house</SelectItem>
                      <SelectItem value="TYPE_B">TYPE_B — redirect to portal</SelectItem>
                      <SelectItem value="INFO">INFO — reference card (no application)</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground mt-1 leading-snug">
                    <strong>TYPE_A</strong>: bot collects all fields here. <strong>TYPE_B</strong>: bot redirects to an external portal. <strong>INFO</strong>: a reference card (status, support, announcement) — no application flow, optional single CTA.
                  </p>
                </div>
                <div className="col-span-2">
                  <Label className="text-xs">
                    External URL{draft.category === "TYPE_B" && <span className="text-destructive ml-1">*</span>}
                  </Label>
                  <Input
                    value={draft.external_url || ""}
                    onChange={(e) => update({ external_url: e.target.value })}
                    placeholder="https://portal.example.gov"
                    className="mt-1"
                    disabled={draft.category === "INFO"}
                  />
                  <p className="text-xs text-muted-foreground mt-1 leading-snug">
                    Where the user is sent for TYPE_B services. Required when category is TYPE_B; ignored otherwise. INFO services use the Content tab's optional <em>primary action</em> instead.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Emoji</Label>
                  <Input
                    value={draft.emoji || ""}
                    onChange={(e) => update({ emoji: e.target.value })}
                    placeholder="🛂"
                    className="w-24 mt-1"
                  />
                  <p className="text-xs text-muted-foreground mt-1 leading-snug">
                    Optional single emoji shown next to the service in the menu.
                  </p>
                </div>
                <div>
                  <Label className="text-xs">Keywords (comma-separated)</Label>
                  <Input
                    value={Array.isArray(draft.keywords) ? draft.keywords.join(", ") : (draft.keywords || "")}
                    onChange={(e) => update({ keywords: e.target.value })}
                    placeholder="passport, renewal, lost"
                    className="mt-1"
                  />
                  <p className="text-xs text-muted-foreground mt-1 leading-snug">
                    Trigger words the widget matches against user messages to surface this service.
                  </p>
                </div>
              </div>

              <div className="flex gap-6 items-start pt-2 border-t border-border">
                <label className="text-sm flex items-center gap-2 mt-2">
                  <Switch checked={!!draft.enabled} onCheckedChange={(v) => update({ enabled: v })} />
                  Enabled in widget
                </label>
                <div>
                  <Label className="text-xs">Display order</Label>
                  <Input
                    type="number"
                    value={draft.display_order ?? ""}
                    onChange={(e) => update({ display_order: e.target.value === "" ? null : Number(e.target.value) })}
                    placeholder="auto"
                    className="w-24 h-8 mt-1"
                  />
                  <p className="text-xs text-muted-foreground mt-1 leading-snug w-56">
                    Lower number = higher in the menu. Blank = automatic.
                  </p>
                </div>
              </div>
            </>
          )}

          {section === "content" && (
            <InfoContentEditor
              value={draft.info_content || { sections: [], primary_action: null }}
              onChange={(next) => update({ info_content: next })}
            />
          )}

          {section === "docs" && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <Label className="text-xs">Required documents</Label>
                <Button size="sm" variant="outline" onClick={addDoc}><Plus className="h-3 w-3 mr-1" /> Add doc</Button>
              </div>
              <p className="text-xs text-muted-foreground mb-3 leading-snug">
                One row per document the applicant must provide. The bot lists these to the user before starting the form.
              </p>
              <div className="space-y-1.5">
                {(draft.documents || []).filter((_, i) => true).map((doc, i) => (
                  <div key={i} className="flex gap-1">
                    <Input value={doc} onChange={(e) => setDoc(i, e.target.value)} placeholder='e.g. "Valid passport — original + photocopy"' />
                    <Button size="sm" variant="ghost" onClick={() => delDoc(i)}>
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                ))}
                {(!draft.documents || draft.documents.length === 0) && (
                  <div className="text-center text-muted-foreground text-sm py-6 border border-dashed border-border rounded">
                    No documents listed. Click <strong>Add doc</strong> to add one.
                  </div>
                )}
              </div>
            </div>
          )}

          {section === "fields" && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <Label className="text-xs">Form fields &amp; flow steps</Label>
                <Button size="sm" variant="outline" onClick={addField}><Plus className="h-3 w-3 mr-1" /> Add field</Button>
              </div>
              <p className="text-xs text-muted-foreground mb-3 leading-snug">
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
                  <div className="text-center text-muted-foreground text-sm py-6 border border-dashed border-border rounded">
                    No fields yet. Add an input field for each piece of data to collect.
                  </div>
                )}
              </div>
            </div>
          )}

          {section === "messaging" && (
            <>
              <div>
                <Label className="text-xs">Post-confirmation reminder (optional)</Label>
                <Textarea
                  value={draft.post_confirm_message || ""}
                  onChange={(e) => update({ post_confirm_message: e.target.value })}
                  rows={3}
                  placeholder='e.g. "Visit our office in person to hand over your original document."'
                  className="mt-1"
                />
                <p className="text-xs text-muted-foreground mt-1 leading-snug">
                  Extra message the bot shows the user after a successful application submission for this service. Leave empty to skip.
                </p>
              </div>
            </>
          )}

          {section === "hooks" && (
            <HooksEditor
              hooks={draft.hooks || {}}
              category={draft.category}
              onChange={(v) => update({ hooks: v })}
            />
          )}
        </div>

        <DialogFooter className="border-t border-border -mx-6 px-6 pt-4 mt-0">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : isNew ? "Create service" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Workflow hooks editor — JSON-textarea per hook point.                    */
/*                                                                            */
/*  We don't (yet) build a visual rule builder because the rule schema is     */
/*  small enough to write by hand, and a UI builder would lock us into the    */
/*  shape we ship today. Textarea + a "load template" button covers the       */
/*  common cases without committing to that yet.                              */
/* ────────────────────────────────────────────────────────────────────────── */

const HOOK_POINTS = [
  {
    key: "pre_consent",
    label: "Before consent",
    description:
      "Runs when the user has chosen this service but hasn't agreed to start. Use show_message to prepend an advisory, or block to refuse the service entirely.",
  },
  {
    key: "pre_submit",
    label: "Before submission",
    description:
      "Runs after all fields are collected and the user types submit, but before the application is persisted. Use block to reject, require_review to flag for manual review, or set_field to override a value.",
    typeAOnly: true,
  },
  {
    key: "post_submit",
    label: "After submission",
    description:
      "Runs after the application is persisted. Use send_email to notify a downstream team, or show_message to append text to the confirmation reply.",
    typeAOnly: true,
  },
];

const HOOK_TEMPLATES = {
  pre_consent: [
    {
      "if": true,
      "then": {
        "action": "show_message",
        "message": "⏰ Processing currently takes ~10 business days."
      }
    }
  ],
  pre_submit: [
    {
      "if": { "field": "fee_amount", "gt": 10000 },
      "then": { "action": "require_review", "reason": "high_value_application" }
    }
  ],
  post_submit: [
    {
      "if": true,
      "then": {
        "action": "send_email",
        "to": "ops@example.com",
        "subject": "New application submitted",
        "body": "A new application has been submitted. Tracking ID will be in the metadata."
      }
    }
  ],
};

function HooksEditor({ hooks, category, onChange }) {
  // Track raw text per hook point so the user can edit broken JSON mid-stroke.
  // We parse + validate on blur or save; intermediate invalid states stay
  // in the textarea without clobbering it.
  const [drafts, setDrafts] = React.useState(() => {
    const out = {};
    for (const { key } of HOOK_POINTS) {
      const v = hooks?.[key];
      out[key] = v && v.length ? JSON.stringify(v, null, 2) : "";
    }
    return out;
  });

  const [errors, setErrors] = React.useState({});

  const commit = (key, text) => {
    const trimmed = (text || "").trim();
    if (!trimmed) {
      const { [key]: _, ...rest } = hooks || {};
      onChange(rest);
      setErrors((e) => ({ ...e, [key]: null }));
      return;
    }
    try {
      const parsed = JSON.parse(trimmed);
      if (!Array.isArray(parsed)) {
        setErrors((e) => ({ ...e, [key]: "Must be a JSON array of rules." }));
        return;
      }
      onChange({ ...(hooks || {}), [key]: parsed });
      setErrors((e) => ({ ...e, [key]: null }));
    } catch (err) {
      setErrors((e) => ({ ...e, [key]: `Invalid JSON: ${err.message}` }));
    }
  };

  const loadTemplate = (key) => {
    const tpl = HOOK_TEMPLATES[key];
    const text = JSON.stringify(tpl, null, 2);
    setDrafts((d) => ({ ...d, [key]: text }));
    commit(key, text);
  };

  const visibleHooks = HOOK_POINTS.filter(
    (h) => !h.typeAOnly || category !== "TYPE_B"
  );

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground leading-relaxed">
        Workflow hooks let you change the bot's behaviour for this service
        without code. Each hook point fires at a known moment in the
        application flow; matched rules return actions like{" "}
        <code className="text-foreground">show_message</code>,{" "}
        <code className="text-foreground">block</code>,{" "}
        <code className="text-foreground">require_review</code>,{" "}
        <code className="text-foreground">send_email</code>, or{" "}
        <code className="text-foreground">set_field</code>. Leave a point
        empty to skip it.
      </div>

      {visibleHooks.map(({ key, label, description }) => (
        <div key={key} className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="text-xs">{label}</Label>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => loadTemplate(key)}
              disabled={!!(drafts[key] && drafts[key].trim())}
            >
              Load template
            </Button>
          </div>
          <p className="text-xs text-muted-foreground leading-snug">{description}</p>
          <Textarea
            value={drafts[key] ?? ""}
            onChange={(e) => setDrafts((d) => ({ ...d, [key]: e.target.value }))}
            onBlur={(e) => commit(key, e.target.value)}
            rows={5}
            placeholder='[ {"if": true, "then": {"action": "show_message", "message": "..."}} ]'
            className="font-mono text-xs"
          />
          {errors[key] && (
            <p className="text-xs text-destructive">{errors[key]}</p>
          )}
        </div>
      ))}
    </div>
  );
}

/* ─── INFO content editor ─────────────────────────────────────────────────── */

// The five section "kinds" that an INFO card supports. Each renders a
// slightly different editor (a callout has tone + body, a links section
// has an array of {label, url} pairs, etc). Keeping the kinds open-ended
// makes future additions cheap — both the editor and the bot renderer
// fall through to a plain text body for unknown kinds.
const SECTION_KIND_OPTIONS = [
  { value: "text",    label: "Text block" },
  { value: "bullets", label: "Bullet list" },
  { value: "callout", label: "Callout (info / warning / success)" },
  { value: "links",   label: "Link list" },
  { value: "contact", label: "Contact details" },
];

function blankSection(kind) {
  switch (kind) {
    case "bullets": return { kind, title: "", items: [""] };
    case "callout": return { kind, tone: "info", title: "", body: "" };
    case "links":   return { kind, title: "", items: [{ label: "", url: "" }] };
    case "contact": return { kind, title: "", items: [{ label: "", value: "", href: "" }] };
    default:        return { kind: "text", title: "", body: "" };
  }
}

function InfoContentEditor({ value, onChange }) {
  const sections = Array.isArray(value?.sections) ? value.sections : [];
  const primary  = value?.primary_action || null;

  const update = (patch) => onChange({ ...(value || {}), ...patch });
  const setSection = (idx, next) => {
    const copy = sections.slice();
    copy[idx] = next;
    update({ sections: copy });
  };
  const addSection = (kind) => update({ sections: [...sections, blankSection(kind)] });
  const removeSection = (idx) => {
    const copy = sections.slice();
    copy.splice(idx, 1);
    update({ sections: copy });
  };
  const moveSection = (idx, dir) => {
    const copy = sections.slice();
    const j = idx + dir;
    if (j < 0 || j >= copy.length) return;
    [copy[idx], copy[j]] = [copy[j], copy[idx]];
    update({ sections: copy });
  };

  return (
    <div className="space-y-5">
      <div>
        <Label className="text-xs">Content sections</Label>
        <p className="text-xs text-muted-foreground mt-1 leading-snug">
          Stack any number of typed blocks — text, bullets, callouts, links, contacts.
          The bot renders them in order under the service name and description.
        </p>
      </div>

      {sections.length === 0 && (
        <div className="rounded-lg border border-dashed border-border bg-muted/30 px-4 py-6 text-center">
          <p className="text-sm text-muted-foreground">No content sections yet. Add your first block below.</p>
        </div>
      )}

      <ol className="space-y-3">
        {sections.map((sec, idx) => (
          <li key={idx} className="rounded-lg border border-border bg-card">
            <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border bg-muted/30">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                  #{idx + 1} · {sec.kind || "text"}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <Button size="sm" variant="ghost" className="h-7 w-7 p-0" disabled={idx === 0} onClick={() => moveSection(idx, -1)} aria-label="Move up">
                  <ChevronUp className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="ghost" className="h-7 w-7 p-0" disabled={idx === sections.length - 1} onClick={() => moveSection(idx, +1)} aria-label="Move down">
                  <ChevronDown className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive hover:bg-destructive/10" onClick={() => removeSection(idx)} aria-label="Remove section">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
            <div className="px-3 py-3 space-y-2">
              <SectionEditor section={sec} onChange={(next) => setSection(idx, next)} />
            </div>
          </li>
        ))}
      </ol>

      <div className="flex flex-wrap gap-2">
        {SECTION_KIND_OPTIONS.map((opt) => (
          <Button key={opt.value} size="sm" variant="outline" onClick={() => addSection(opt.value)}>
            <Plus className="h-3 w-3 mr-1" />
            {opt.label}
          </Button>
        ))}
      </div>

      <div className="pt-4 border-t border-border">
        <Label className="text-xs">Primary action (optional)</Label>
        <p className="text-xs text-muted-foreground mt-1 mb-2 leading-snug">
          A single CTA rendered at the bottom of the info card. Use for "Open status portal", "Talk to support", etc. Leave blank for a pure-info card with no buttons.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <Input
            placeholder="Button label"
            value={primary?.label || ""}
            onChange={(e) => update({ primary_action: { ...(primary || {}), label: e.target.value } })}
          />
          <Input
            placeholder="https://…"
            value={primary?.url || ""}
            onChange={(e) => update({ primary_action: { ...(primary || {}), url: e.target.value } })}
          />
        </div>
        {(primary?.label || primary?.url) && (
          <Button
            size="sm"
            variant="ghost"
            className="mt-2 text-muted-foreground hover:text-destructive"
            onClick={() => update({ primary_action: null })}
          >
            <Trash2 className="h-3 w-3 mr-1" /> Remove primary action
          </Button>
        )}
      </div>
    </div>
  );
}

function SectionEditor({ section, onChange }) {
  const kind = section?.kind || "text";
  const set = (patch) => onChange({ ...(section || {}), ...patch });

  const titleInput = (
    <Input
      placeholder="Section title (optional)"
      value={section?.title || ""}
      onChange={(e) => set({ title: e.target.value })}
      className="h-8 text-sm"
    />
  );

  if (kind === "bullets") {
    const items = section.items || [];
    const setItem = (i, v) => { const next = items.slice(); next[i] = v; set({ items: next }); };
    const addItem = () => set({ items: [...items, ""] });
    const delItem = (i) => { const next = items.slice(); next.splice(i, 1); set({ items: next }); };
    return (
      <div className="space-y-2">
        {titleInput}
        {items.map((it, i) => (
          <div key={i} className="flex gap-2">
            <Input value={it} onChange={(e) => setItem(i, e.target.value)} className="h-8 text-sm" placeholder="Bullet text" />
            <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive" onClick={() => delItem(i)}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        <Button size="sm" variant="outline" onClick={addItem}><Plus className="h-3 w-3 mr-1" /> Add bullet</Button>
      </div>
    );
  }

  if (kind === "callout") {
    return (
      <div className="space-y-2">
        <div className="grid grid-cols-[120px_1fr] gap-2">
          <Select value={section.tone || "info"} onValueChange={(v) => set({ tone: v })}>
            <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="info">Info</SelectItem>
              <SelectItem value="warning">Warning</SelectItem>
              <SelectItem value="success">Success</SelectItem>
            </SelectContent>
          </Select>
          {titleInput}
        </div>
        <Textarea
          rows={3}
          placeholder="Callout body — what should users know?"
          value={section.body || ""}
          onChange={(e) => set({ body: e.target.value })}
          className="text-sm"
        />
      </div>
    );
  }

  if (kind === "links") {
    const items = section.items || [];
    const setItem = (i, patch) => { const next = items.slice(); next[i] = { ...next[i], ...patch }; set({ items: next }); };
    const addItem = () => set({ items: [...items, { label: "", url: "" }] });
    const delItem = (i) => { const next = items.slice(); next.splice(i, 1); set({ items: next }); };
    return (
      <div className="space-y-2">
        {titleInput}
        {items.map((it, i) => (
          <div key={i} className="flex gap-2">
            <Input value={it.label || ""} onChange={(e) => setItem(i, { label: e.target.value })} className="h-8 text-sm" placeholder="Label" />
            <Input value={it.url || ""} onChange={(e) => setItem(i, { url: e.target.value })} className="h-8 text-sm font-mono" placeholder="https://…" />
            <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive" onClick={() => delItem(i)}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        <Button size="sm" variant="outline" onClick={addItem}><Plus className="h-3 w-3 mr-1" /> Add link</Button>
      </div>
    );
  }

  if (kind === "contact") {
    const items = section.items || [];
    const setItem = (i, patch) => { const next = items.slice(); next[i] = { ...next[i], ...patch }; set({ items: next }); };
    const addItem = () => set({ items: [...items, { label: "", value: "", href: "" }] });
    const delItem = (i) => { const next = items.slice(); next.splice(i, 1); set({ items: next }); };
    return (
      <div className="space-y-2">
        {titleInput}
        {items.map((it, i) => (
          <div key={i} className="grid grid-cols-[110px_1fr_1fr_32px] gap-2">
            <Input value={it.label || ""} onChange={(e) => setItem(i, { label: e.target.value })} className="h-8 text-sm" placeholder="Email" />
            <Input value={it.value || ""} onChange={(e) => setItem(i, { value: e.target.value })} className="h-8 text-sm" placeholder="help@example.com" />
            <Input value={it.href || ""} onChange={(e) => setItem(i, { href: e.target.value })} className="h-8 text-sm font-mono" placeholder="mailto:… (optional)" />
            <Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive" onClick={() => delItem(i)}>
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        <Button size="sm" variant="outline" onClick={addItem}><Plus className="h-3 w-3 mr-1" /> Add contact</Button>
      </div>
    );
  }

  // text (default / unknown)
  return (
    <div className="space-y-2">
      {titleInput}
      <Textarea
        rows={4}
        placeholder="Paragraph text — markdown links allowed."
        value={section?.body || ""}
        onChange={(e) => set({ body: e.target.value })}
        className="text-sm"
      />
    </div>
  );
}
