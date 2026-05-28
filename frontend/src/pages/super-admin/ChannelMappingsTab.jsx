/**
 * Super-admin tab — Channel Mappings (Sprint 5)
 *
 * CRUD for `messaging_channel_map` rows. Each row maps an inbound
 * webhook channel identity (channel_type + external_id) to a tenant.
 * Without a mapping the resolver falls back to the env-var default
 * tenant with a WARNING log on every inbound message.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  Plus, Trash2, Edit2, RefreshCw, Smartphone, Facebook, AlertCircle, KeyRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Section } from "@/components/admin/Section";
import { EmptyState } from "@/components/admin/EmptyState";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const CHANNELS = [
  { value: "whatsapp_twilio", label: "WhatsApp (Twilio)", icon: Smartphone },
  { value: "ics_waba",        label: "WhatsApp (ICS WABA)", icon: Smartphone },
  { value: "facebook",        label: "Facebook Page", icon: Facebook },
];

const channelLabel = (v) => CHANNELS.find((c) => c.value === v)?.label ?? v;
const ChannelIcon  = ({ type, ...p }) => {
  const Icon = CHANNELS.find((c) => c.value === type)?.icon;
  return Icon ? <Icon {...p} /> : null;
};

export default function ChannelMappingsTab({ companies, token }) {
  const [mappings, setMappings] = useState([]);
  const [loading, setLoading]   = useState(false);
  const [filterChannel, setFilterChannel] = useState("");
  const [filterCompany, setFilterCompany] = useState("");
  const [editing, setEditing]   = useState(null); // null | row | "new"
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const companyName = (id) => companies.find((c) => c.id === id)?.name ?? id;

  const fetchMappings = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterChannel) params.set("channel_type", filterChannel);
      if (filterCompany) params.set("company_id", filterCompany);
      const res = await fetch(`${API}/super-admin/channel-mappings?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load");
      setMappings(data.mappings || []);
    } catch (err) {
      toast.error(err.message || "Failed to load channel mappings");
    } finally {
      setLoading(false);
    }
  }, [filterChannel, filterCompany, token]);

  useEffect(() => { fetchMappings(); }, [fetchMappings]);

  const handleDeleteConfirmed = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      const row = confirmDelete;
      const path = `${API}/super-admin/channel-mappings/${row.channel_type}/${encodeURIComponent(row.external_id)}`;
      const res = await fetch(path, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Delete failed");
      }
      toast.success("Mapping deleted");
      setConfirmDelete(null);
      fetchMappings();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top bar: filters + actions */}
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div className="flex gap-2 flex-wrap items-end">
          <div className="w-56">
            <Label className="text-xs text-muted-foreground">Channel type</Label>
            <Select value={filterChannel || "all"} onValueChange={(v) => setFilterChannel(v === "all" ? "" : v)}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="All channels" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All channels</SelectItem>
                {CHANNELS.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="w-72">
            <Label className="text-xs text-muted-foreground">Tenant</Label>
            <Select value={filterCompany || "all"} onValueChange={(v) => setFilterCompany(v === "all" ? "" : v)}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="All tenants" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All tenants</SelectItem>
                {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={fetchMappings} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button size="sm" onClick={() => setEditing("new")}>
            <Plus className="mr-1.5 h-3.5 w-3.5" /> New mapping
          </Button>
        </div>
      </div>

      <Section
        title="Channel mappings"
        description="Each row maps an inbound webhook identity (channel + external ID) to a tenant. Unmapped channels fall back to the env-var default tenant with a WARNING log on every inbound message."
        bodyClassName="p-0"
      >
        {loading ? (
          <div className="px-5 py-12 text-center text-sm text-muted-foreground">Loading…</div>
        ) : mappings.length === 0 ? (
          <EmptyState
            icon={AlertCircle}
            title="No mappings configured"
            description="All inbound traffic falls back to the env-var default tenant. Add a mapping to route a specific WhatsApp number or Facebook page to its tenant."
            action={
              <Button size="sm" onClick={() => setEditing("new")}>
                <Plus className="mr-1.5 h-3.5 w-3.5" /> New mapping
              </Button>
            }
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-left text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-2.5">Channel</th>
                <th className="px-4 py-2.5">External ID</th>
                <th className="px-4 py-2.5">Tenant</th>
                <th className="px-4 py-2.5">Metadata</th>
                <th className="px-4 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((row) => (
                <tr key={`${row.channel_type}::${row.external_id}`} className="border-t border-border hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <Badge variant="secondary" className="gap-1">
                      <ChannelIcon type={row.channel_type} className="h-3 w-3" />
                      {channelLabel(row.channel_type)}
                    </Badge>
                    {row.has_credentials && (
                      <Badge variant="outline" className="ml-1 gap-1" title="Sends from this tenant's own ICS account">
                        <KeyRound className="h-3 w-3" /> own creds
                      </Badge>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">{row.external_id}</td>
                  <td className="px-4 py-3">
                    <div className="text-foreground">{row.company_name || companyName(row.company_id)}</div>
                    <div className="text-xs text-muted-foreground font-mono">{row.company_id?.slice(0, 8)}…</div>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {row.metadata && Object.keys(row.metadata).length > 0
                      ? JSON.stringify(row.metadata)
                      : <span>—</span>}
                  </td>
                  <td className="px-4 py-3 text-right space-x-1">
                    <Button size="sm" variant="ghost" onClick={() => setEditing(row)}>
                      <Edit2 className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(row)}>
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      {editing && (
        <MappingDialog
          row={editing === "new" ? null : editing}
          companies={companies}
          token={token}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchMappings(); }}
        />
      )}

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title="Delete channel mapping?"
        description={confirmDelete && (
          `Removes the mapping ${channelLabel(confirmDelete.channel_type)}: ${confirmDelete.external_id}. ` +
          "Inbound messages from this channel will fall back to the env-var default tenant."
        )}
        confirmLabel="Delete mapping"
        destructive
        loading={deleting}
        onConfirm={handleDeleteConfirmed}
      />
    </div>
  );
}

function MappingDialog({ row, companies, token, onClose, onSaved }) {
  const isNew = !row;
  const [channelType, setChannelType] = useState(row?.channel_type ?? "ics_waba");
  const [externalId,  setExternalId]  = useState(row?.external_id ?? "");
  const [companyId,   setCompanyId]   = useState(row?.company_id ?? "");
  const [metadata,    setMetadata]    = useState(
    row?.metadata && Object.keys(row.metadata).length > 0
      ? JSON.stringify(row.metadata, null, 2)
      : ""
  );
  // Per-tenant ICS WABA send credentials. The password is never returned by the
  // API (redacted to `has_credentials`), so it's never prefilled — blank on save
  // means "keep the existing password".
  const [sendUser, setSendUser] = useState(row?.send_user ?? "");
  const [sendPass, setSendPass] = useState("");
  const hasCreds = !!row?.has_credentials;
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!externalId.trim()) { toast.error("External ID is required"); return; }
    if (!companyId)         { toast.error("Pick a tenant"); return; }

    let metaObj = {};
    if (metadata.trim()) {
      try { metaObj = JSON.parse(metadata); }
      catch { toast.error("Metadata must be valid JSON or empty"); return; }
    }

    const payload = { company_id: companyId, metadata: metaObj };
    if (channelType === "ics_waba") {
      const u = sendUser.trim();
      // Require a username alongside a new password (unless one is already stored).
      if (sendPass && !u && !hasCreds) {
        toast.error("ICS username is required when setting a password");
        return;
      }
      if (u) payload.send_user = u;
      if (sendPass) payload.send_pass = sendPass;  // omit when blank → keep existing
    }

    setSaving(true);
    try {
      const path = `${API}/super-admin/channel-mappings/${channelType}/${encodeURIComponent(externalId.trim())}`;
      const res = await fetch(path, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Save failed");
      toast.success(isNew ? "Mapping created" : "Mapping updated");
      onSaved();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isNew ? "New channel mapping" : "Edit channel mapping"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label className="text-xs">Channel type</Label>
            <Select value={channelType} onValueChange={setChannelType} disabled={!isNew}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {CHANNELS.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">
              External ID
              <span className="text-muted-foreground ml-1">
                ({channelType === "facebook" ? "Page ID" : "phone number incl. country code"})
              </span>
            </Label>
            <Input
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              placeholder={channelType === "facebook" ? "1234567890" : "+27115819800"}
              disabled={!isNew}
              className="font-mono"
            />
          </div>
          <div>
            <Label className="text-xs">Tenant</Label>
            <Select value={companyId} onValueChange={setCompanyId}>
              <SelectTrigger><SelectValue placeholder="Pick a tenant" /></SelectTrigger>
              <SelectContent>
                {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs">Metadata (optional JSON)</Label>
            <Textarea
              value={metadata}
              onChange={(e) => setMetadata(e.target.value)}
              rows={4}
              placeholder='{"note": "main consulate number"}'
              className="font-mono text-xs"
            />
          </div>

          {channelType === "ics_waba" && (
            <div className="space-y-3 rounded-md border border-border bg-muted/30 p-3">
              <div className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <KeyRound className="h-3.5 w-3.5" />
                Per-tenant ICS WABA credentials
                <span className="text-muted-foreground font-normal">(optional)</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Leave blank to send from the platform's default ICS account. Set these to send
                as this tenant's own ICS account. The password is stored encrypted and never
                shown again.
              </p>
              <div>
                <Label className="text-xs">ICS username</Label>
                <Input
                  value={sendUser}
                  onChange={(e) => setSendUser(e.target.value)}
                  placeholder="ics-username"
                  className="font-mono"
                  autoComplete="off"
                />
              </div>
              <div>
                <Label className="text-xs">ICS password</Label>
                <Input
                  type="password"
                  value={sendPass}
                  onChange={(e) => setSendPass(e.target.value)}
                  placeholder={hasCreds ? "•••••••• (leave blank to keep current)" : "ics-password"}
                  autoComplete="new-password"
                />
                {hasCreds && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Credentials are configured. Leave blank to keep the existing password.
                  </p>
                )}
              </div>
            </div>
          )}
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
