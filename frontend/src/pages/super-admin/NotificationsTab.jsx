/**
 * Super-admin — Notifications
 *
 * One editable card per platform notification scenario (catalog comes from
 * the backend registry). Each card controls: enabled, recipient roles +
 * custom emails, editable subject/body templates ({{variables}}), threshold
 * params, and cooldown. A "Send test" sends the scenario's sample copy to an
 * address, and a delivery log shows recent sends.
 */
import React, { useCallback, useEffect, useState } from "react";
import { RefreshCw, Bell, Save, Send, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Section } from "@/components/admin/Section";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ROLE_LABELS = {
  super_admin: "Super admins",
  tenant_admin: "Tenant admins",
  applicant: "Applicant",
  custom: "Custom emails",
};
const SEV_STYLES = {
  info:     "bg-muted text-muted-foreground border border-border",
  warning:  "bg-warning/10 text-warning border border-warning/20",
  critical: "bg-destructive/10 text-destructive border border-destructive/20",
};

export default function NotificationsTab({ token }) {
  const [data, setData] = useState({ categories: [], roles: [], scenarios: [] });
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState({});      // scenario_key -> bool
  const [drafts, setDrafts] = useState({});           // scenario_key -> setting draft
  const [savingKey, setSavingKey] = useState(null);
  const [log, setLog] = useState([]);

  const authHdr = { Authorization: `Bearer ${token}` };

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [scRes, logRes] = await Promise.all([
        fetch(`${API}/super-admin/notifications/scenarios`, { headers: authHdr }),
        fetch(`${API}/super-admin/notifications/log?limit=50`, { headers: authHdr }),
      ]);
      const sc = await scRes.json();
      const lg = await logRes.json();
      if (!scRes.ok) throw new Error(sc.detail || "Failed to load scenarios");
      setData(sc);
      // seed drafts from settings
      const d = {};
      (sc.scenarios || []).forEach((s) => { d[s.key] = JSON.parse(JSON.stringify(s.setting || {})); });
      setDrafts(d);
      setLog(lg.log || []);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [token]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const patchDraft = (key, patch) => setDrafts((d) => ({ ...d, [key]: { ...d[key], ...patch } }));

  const toggleRole = (key, role) => {
    const cur = drafts[key]?.recipients || [];
    patchDraft(key, { recipients: cur.includes(role) ? cur.filter((r) => r !== role) : [...cur, role] });
  };

  const save = async (key, { silent } = {}) => {
    setSavingKey(key);
    try {
      const s = drafts[key];
      const body = {
        enabled: s.enabled,
        recipients: s.recipients,
        custom_emails: (s.custom_emails || []).filter(Boolean),
        subject: s.subject,
        body: s.body,
        params: s.params,
        cooldown_minutes: Number(s.cooldown_minutes) || 0,
      };
      const res = await fetch(`${API}/super-admin/notifications/settings/${key}`, {
        method: "PUT", headers: { ...authHdr, "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const out = await res.json();
      if (!res.ok) throw new Error(out.detail || "Save failed");
      if (!silent) toast.success("Saved");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSavingKey(null);
    }
  };

  // Toggle enable inline (auto-saves just the flag).
  const toggleEnabled = async (key, val) => {
    patchDraft(key, { enabled: val });
    try {
      await fetch(`${API}/super-admin/notifications/settings/${key}`, {
        method: "PUT", headers: { ...authHdr, "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: val }),
      });
    } catch { toast.error("Failed to update"); }
  };

  const sendTest = async (key) => {
    const email = window.prompt("Send a test of this notification to which email?");
    if (!email) return;
    try {
      const res = await fetch(`${API}/super-admin/notifications/test/${key}?email=${encodeURIComponent(email)}`, {
        method: "POST", headers: authHdr,
      });
      const out = await res.json();
      if (!res.ok) throw new Error(out.detail || "Test failed");
      const r = out.result || {};
      toast.success(`Test ${r.status} → ${email}${r.status !== "sent" ? ` (${r.reason || ""})` : ""}`);
      fetchAll();
    } catch (e) { toast.error(e.message); }
  };

  const scenariosByCat = (catKey) => (data.scenarios || []).filter((s) => s.category === catKey);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={fetchAll} disabled={loading}>
          <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {data.categories.map((cat) => {
        const scns = scenariosByCat(cat.key);
        if (scns.length === 0) return null;
        return (
          <Section key={cat.key} title={cat.label} bodyClassName="p-0">
            <div className="divide-y divide-border">
              {scns.map((s) => {
                const d = drafts[s.key] || s.setting || {};
                const open = expanded[s.key];
                return (
                  <div key={s.key} className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <button
                        className="flex items-center gap-2 flex-1 min-w-0 text-left"
                        onClick={() => setExpanded((e) => ({ ...e, [s.key]: !e[s.key] }))}
                      >
                        {open ? <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" /> : <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />}
                        <span className="font-medium text-foreground truncate">{s.name}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${SEV_STYLES[s.severity] || SEV_STYLES.info}`}>{s.severity}</span>
                        <span className="text-xs text-muted-foreground truncate hidden md:inline">· {s.description}</span>
                      </button>
                      <code className="text-[10px] text-muted-foreground hidden lg:inline">{s.key}</code>
                      <Switch checked={!!d.enabled} onCheckedChange={(v) => toggleEnabled(s.key, v)} />
                    </div>

                    {open && (
                      <div className="mt-3 pl-6 space-y-3">
                        {/* Recipients */}
                        <div>
                          <Label className="text-xs text-muted-foreground">Recipients</Label>
                          <div className="flex flex-wrap gap-2 mt-1">
                            {(data.roles || []).map((role) => (
                              <button
                                key={role}
                                onClick={() => toggleRole(s.key, role)}
                                className={`text-xs px-2 py-1 rounded-full border ${(d.recipients || []).includes(role)
                                  ? "bg-primary/10 text-primary border-primary/30"
                                  : "bg-muted text-muted-foreground border-border"}`}
                              >
                                {ROLE_LABELS[role] || role}
                              </button>
                            ))}
                          </div>
                          {(d.recipients || []).includes("custom") && (
                            <Input
                              className="mt-2 text-xs"
                              placeholder="comma-separated emails"
                              value={(d.custom_emails || []).join(", ")}
                              onChange={(e) => patchDraft(s.key, { custom_emails: e.target.value.split(",").map((x) => x.trim()) })}
                            />
                          )}
                        </div>

                        {/* Subject + body */}
                        <div>
                          <Label className="text-xs text-muted-foreground">Subject</Label>
                          <Input className="text-sm" value={d.subject || ""} onChange={(e) => patchDraft(s.key, { subject: e.target.value })} />
                        </div>
                        <div>
                          <Label className="text-xs text-muted-foreground">Body — use {"{{variables}}"} from the sample context</Label>
                          <Textarea rows={4} className="text-sm font-mono" value={d.body || ""} onChange={(e) => patchDraft(s.key, { body: e.target.value })} />
                        </div>

                        {/* Params + cooldown */}
                        <div className="flex flex-wrap gap-4">
                          {Object.keys(d.params || {}).map((p) => (
                            <div key={p}>
                              <Label className="text-xs text-muted-foreground">{p}</Label>
                              <Input
                                type="number" className="w-28 text-sm"
                                value={d.params[p]}
                                onChange={(e) => patchDraft(s.key, { params: { ...d.params, [p]: Number(e.target.value) } })}
                              />
                            </div>
                          ))}
                          <div>
                            <Label className="text-xs text-muted-foreground">Cooldown (min)</Label>
                            <Input
                              type="number" className="w-28 text-sm"
                              value={d.cooldown_minutes ?? 0}
                              onChange={(e) => patchDraft(s.key, { cooldown_minutes: Number(e.target.value) })}
                            />
                          </div>
                        </div>

                        <div className="flex gap-2 pt-1">
                          <Button size="sm" onClick={() => save(s.key)} disabled={savingKey === s.key}>
                            <Save className="h-3.5 w-3.5 mr-1.5" />{savingKey === s.key ? "Saving…" : "Save"}
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => sendTest(s.key)}>
                            <Send className="h-3.5 w-3.5 mr-1.5" />Send test
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Section>
        );
      })}

      {/* Delivery log */}
      <Section title="Delivery log" description="Recent notification sends across all scenarios (90-day retention)." bodyClassName="p-0">
        {log.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground flex items-center gap-2"><Bell className="h-4 w-4" /> No notifications sent yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-left text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-2.5">When</th>
                <th className="px-4 py-2.5">Scenario</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Recipients</th>
                <th className="px-4 py-2.5">Subject</th>
              </tr>
            </thead>
            <tbody>
              {log.map((r) => (
                <tr key={r.id} className="border-t border-border">
                  <td className="px-4 py-2 text-muted-foreground whitespace-nowrap text-xs">{formatDate(r.created_at)}</td>
                  <td className="px-4 py-2 font-mono text-xs">{r.scenario_key}</td>
                  <td className="px-4 py-2">
                    <Badge className={r.status === "sent" ? "bg-success/10 text-success border-success/20"
                      : r.status === "failed" ? "bg-destructive/10 text-destructive border-destructive/20"
                      : "bg-muted text-muted-foreground border-border"}>
                      {r.status}{r.reason ? ` · ${r.reason}` : ""}
                    </Badge>
                  </td>
                  <td className="px-4 py-2 text-xs text-muted-foreground max-w-[220px] truncate" title={(r.recipients || []).join(", ")}>
                    {(r.recipients || []).join(", ") || "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-muted-foreground max-w-[260px] truncate" title={r.subject}>{r.subject || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}

function formatDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}
