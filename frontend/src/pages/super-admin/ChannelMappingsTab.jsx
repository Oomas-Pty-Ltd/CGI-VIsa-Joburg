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
  Plus, Trash2, Edit2, RefreshCw, Smartphone, Facebook, AlertCircle,
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

  const handleDelete = async (row) => {
    if (!window.confirm(`Delete mapping ${channelLabel(row.channel_type)}: ${row.external_id}? Inbound messages will fall back to the default tenant.`)) return;
    try {
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
      fetchMappings();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header + actions */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Channel Mappings</h2>
          <p className="text-sm text-slate-500">
            Route inbound WhatsApp / Facebook webhook traffic to the right tenant.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchMappings} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button onClick={() => setEditing("new")}>
            <Plus className="mr-2 h-4 w-4" /> New mapping
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap items-end">
        <div className="w-56">
          <Label className="text-xs">Channel type</Label>
          <Select value={filterChannel || "all"} onValueChange={(v) => setFilterChannel(v === "all" ? "" : v)}>
            <SelectTrigger><SelectValue placeholder="All channels" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All channels</SelectItem>
              {CHANNELS.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="w-72">
          <Label className="text-xs">Tenant</Label>
          <Select value={filterCompany || "all"} onValueChange={(v) => setFilterCompany(v === "all" ? "" : v)}>
            <SelectTrigger><SelectValue placeholder="All tenants" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All tenants</SelectItem>
              {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-lg border bg-white overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-500">Loading…</div>
        ) : mappings.length === 0 ? (
          <div className="p-8 text-center text-slate-500 flex flex-col items-center gap-2">
            <AlertCircle className="h-8 w-8 text-amber-500" />
            <div>No mappings configured.</div>
            <div className="text-xs">All inbound traffic falls back to the env-var default tenant. Add a mapping to route a specific channel.</div>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-left">
              <tr>
                <th className="px-3 py-2">Channel</th>
                <th className="px-3 py-2">External ID</th>
                <th className="px-3 py-2">Tenant</th>
                <th className="px-3 py-2">Metadata</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {mappings.map((row) => (
                <tr key={`${row.channel_type}::${row.external_id}`} className="border-t hover:bg-slate-50">
                  <td className="px-3 py-2">
                    <Badge variant="secondary" className="gap-1">
                      <ChannelIcon type={row.channel_type} className="h-3 w-3" />
                      {channelLabel(row.channel_type)}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{row.external_id}</td>
                  <td className="px-3 py-2">
                    <div>{row.company_name || companyName(row.company_id)}</div>
                    <div className="text-xs text-slate-400 font-mono">{row.company_id?.slice(0, 8)}…</div>
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-500">
                    {row.metadata && Object.keys(row.metadata).length > 0
                      ? JSON.stringify(row.metadata)
                      : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-3 py-2 text-right space-x-1">
                    <Button size="sm" variant="ghost" onClick={() => setEditing(row)}>
                      <Edit2 className="h-3.5 w-3.5" />
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => handleDelete(row)}>
                      <Trash2 className="h-3.5 w-3.5 text-red-500" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {editing && (
        <MappingDialog
          row={editing === "new" ? null : editing}
          companies={companies}
          token={token}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); fetchMappings(); }}
        />
      )}
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
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!externalId.trim()) { toast.error("External ID is required"); return; }
    if (!companyId)         { toast.error("Pick a tenant"); return; }

    let metaObj = {};
    if (metadata.trim()) {
      try { metaObj = JSON.parse(metadata); }
      catch { toast.error("Metadata must be valid JSON or empty"); return; }
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
        body: JSON.stringify({ company_id: companyId, metadata: metaObj }),
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
              <span className="text-slate-400 ml-1">
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
