/**
 * Super-admin tab — Scrapers (Sprint 2F)
 *
 * Per-tenant scraper config + "run now" trigger + run history.
 * Each tenant has at most one scraper_config row. Manual runs are
 * queued via a FastAPI BackgroundTask; callers poll `/runs` to see
 * progress.
 */
import React, { useCallback, useEffect, useState } from "react";
import {
  RefreshCw, Save, Play, AlertCircle, Plus, Trash2, CheckCircle2, XCircle, Clock,
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
import { Section } from "@/components/admin/Section";
import { EmptyState } from "@/components/admin/EmptyState";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const EMPTY_CFG = {
  enabled: true,
  seed_urls: [""],
  allowed_domains: [""],
  max_depth: 3,
  max_pages: 200,
  include_patterns: [],
  exclude_patterns: [],
  respect_robots: true,
  use_sitemap: true,
  fetch_timeout_seconds: 30,
  fetch_delay_ms: 500,
  concurrency: 4,
  use_playwright: false,
  user_agent: "",
  schedule_cron: "",
};

export default function ScrapersTab({ companies, token, singleTenant = false }) {
  const [tenantId, setTenantId] = useState("");
  const [cfg, setCfg] = useState(EMPTY_CFG);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving]   = useState(false);
  const [running, setRunning] = useState(false);
  const [noRow, setNoRow]     = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
  // Per-page drill-down for a selected run.
  const [selectedRun, setSelectedRun] = useState(null);
  const [pages, setPages] = useState([]);
  const [pagesLoading, setPagesLoading] = useState(false);
  const [pageDetail, setPageDetail] = useState(null);

  useEffect(() => {
    if (!tenantId && companies.length > 0) setTenantId(companies[0].id);
  }, [companies, tenantId]);

  const fetchAll = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    setNoRow(false);
    try {
      // ?soft_404=1 keeps the DevTools console clean on the expected
      // no-row-yet path — backend returns 200 + {exists: false}.
      const [cfgRes, runsRes] = await Promise.all([
        fetch(`${API}/super-admin/scrapers/${tenantId}?soft_404=1`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API}/super-admin/scrapers/${tenantId}/runs?limit=20`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      const cfgData = await cfgRes.json();
      if (!cfgRes.ok) throw new Error(cfgData.detail || "Failed to load config");

      if (cfgData.exists === false) {
        setCfg(EMPTY_CFG);
        setNoRow(true);
      } else {
        setCfg({
          ...EMPTY_CFG,
          ...cfgData,
          seed_urls: cfgData.seed_urls?.length ? cfgData.seed_urls : [""],
          allowed_domains: cfgData.allowed_domains?.length ? cfgData.allowed_domains : [""],
          include_patterns: cfgData.include_patterns || [],
          exclude_patterns: cfgData.exclude_patterns || [],
        });
      }

      if (runsRes.ok) {
        const runsData = await runsRes.json();
        setRuns(runsData.runs || []);
      }
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [tenantId, token]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Reset the per-page drill-down whenever the tenant changes.
  useEffect(() => { setSelectedRun(null); setPages([]); setPageDetail(null); }, [tenantId]);

  const openRun = useCallback(async (run) => {
    const runId = run.run_id || run.id;
    setSelectedRun(run);
    setPages([]);
    setPageDetail(null);
    setPagesLoading(true);
    try {
      const res = await fetch(`${API}/super-admin/scrapers/${tenantId}/runs/${runId}/pages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load pages");
      setPages(data.pages || []);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setPagesLoading(false);
    }
  }, [tenantId, token]);

  const openPageDetail = useCallback(async (pageId) => {
    try {
      const res = await fetch(`${API}/super-admin/scrapers/${tenantId}/pages/${pageId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load page");
      setPageDetail(data);
    } catch (err) {
      toast.error(err.message);
    }
  }, [tenantId, token]);

  const update = (patch) => setCfg((c) => ({ ...c, ...patch }));

  const handleSave = async () => {
    setSaving(true);
    try {
      const body = {
        ...cfg,
        seed_urls:        (cfg.seed_urls        || []).map((s) => s.trim()).filter(Boolean),
        allowed_domains:  (cfg.allowed_domains  || []).map((s) => s.trim()).filter(Boolean),
        include_patterns: (cfg.include_patterns || []).map((s) => s.trim()).filter(Boolean),
        exclude_patterns: (cfg.exclude_patterns || []).map((s) => s.trim()).filter(Boolean),
        user_agent:    cfg.user_agent    || undefined,
        schedule_cron: cfg.schedule_cron || undefined,
      };
      const res = await fetch(`${API}/super-admin/scrapers/${tenantId}`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Save failed");
      toast.success("Scraper config saved");
      setNoRow(false);
      fetchAll();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleRunNowConfirmed = async () => {
    setRunning(true);
    try {
      const res = await fetch(`${API}/super-admin/scrapers/${tenantId}/run`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Trigger failed");
      toast.success(data.message || "Crawl triggered");
      setConfirmRun(false);
      // Refresh runs list shortly after to pick up the new run record
      setTimeout(fetchAll, 1500);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setRunning(false);
    }
  };

  /* ─── list helpers (seed_urls, allowed_domains, patterns) ─── */
  const setListItem = (key, i, v) => setCfg((c) => {
    const arr = [...(c[key] || [])]; arr[i] = v; return { ...c, [key]: arr };
  });
  const addListItem = (key) => setCfg((c) => ({ ...c, [key]: [...(c[key] || []), ""] }));
  const delListItem = (key, i) => setCfg((c) => {
    const arr = [...(c[key] || [])]; arr.splice(i, 1); return { ...c, [key]: arr };
  });

  return (
    <div className="space-y-4">
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
          <Button variant="outline" size="sm" onClick={fetchAll} disabled={loading}>
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={() => setConfirmRun(true)} disabled={running || noRow || !cfg.enabled}>
            <Play className={`mr-1.5 h-3.5 w-3.5 ${running ? "animate-pulse" : ""}`} />
            Run now
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving || !tenantId}>
            <Save className="mr-1.5 h-3.5 w-3.5" />
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      {noRow && (
        <div className="rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-sm text-foreground flex items-start gap-2">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-warning" />
          <div>
            <strong className="font-medium">No scraper config for this tenant yet.</strong> Fill in seeds + domains and click Save to create one.
          </div>
        </div>
      )}

      <Section
        title="General"
        description="Crawl-budget and behaviour knobs. Saving here doesn't trigger a run — use Run now."
      >
        <div className="mb-3">
          <label className="flex items-center gap-3">
            <Switch checked={!!cfg.enabled} onCheckedChange={(v) => update({ enabled: v })} />
            <span className="text-sm">Crawler enabled (also gates the Run-now button)</span>
          </label>
          <p className="text-[11px] text-muted-foreground mt-1 leading-snug">
            When off, scheduled runs are skipped and the manual trigger button is disabled.
            Existing entries already in the knowledge base are kept.
          </p>
        </div>
        <Grid2>
          <NumField
            label="Max depth" value={cfg.max_depth}
            onChange={(v) => update({ max_depth: v })}
            hint="How many link-hops away from a seed URL to follow. 1 = seeds only, 3 = a typical small site."
          />
          <NumField
            label="Max pages" value={cfg.max_pages}
            onChange={(v) => update({ max_pages: v })}
            hint="Hard cap on pages fetched per run. Stops a runaway crawl from chewing through a large site."
          />
          <NumField
            label="Concurrency" value={cfg.concurrency}
            onChange={(v) => update({ concurrency: v })}
            hint="Parallel fetches. Higher is faster but more load on the target site — keep ≤ 8 for public sites."
          />
          <NumField
            label="Fetch delay (ms)" value={cfg.fetch_delay_ms}
            onChange={(v) => update({ fetch_delay_ms: v })}
            hint="Pause between requests to the same host. Polite default is 500–1000 ms."
          />
          <NumField
            label="Fetch timeout (s)" value={cfg.fetch_timeout_seconds}
            onChange={(v) => update({ fetch_timeout_seconds: v })}
            hint="Give up on a single page after this many seconds. The run continues with the next URL."
          />
          <TextField
            label="Schedule (cron, optional)" value={cfg.schedule_cron}
            onChange={(v) => update({ schedule_cron: v })}
            placeholder="0 2 * * *" mono
            hint='Standard 5-field cron in UTC. Example: "0 2 * * *" runs daily at 02:00 UTC. Blank = manual only.'
          />
        </Grid2>
        <div className="grid grid-cols-3 gap-3 mt-3">
          <Toggle
            label="Respect robots.txt" value={cfg.respect_robots}
            onChange={(v) => update({ respect_robots: v })}
            hint="Skip URLs disallowed by the target site's robots.txt. Leave on for public crawls."
          />
          <Toggle
            label="Use sitemap.xml" value={cfg.use_sitemap}
            onChange={(v) => update({ use_sitemap: v })}
            hint="Discover URLs via /sitemap.xml first. Faster + more complete than link-crawling alone."
          />
          <Toggle
            label="Use Playwright" value={cfg.use_playwright}
            onChange={(v) => update({ use_playwright: v })}
            hint="Render JavaScript with a headless browser. Slower; only needed for SPAs that don't ship server-side HTML."
          />
        </div>
        <div className="mt-3">
          <TextField
            label="User agent (optional)" value={cfg.user_agent}
            onChange={(v) => update({ user_agent: v })}
            placeholder="Mozilla/5.0 …"
            hint="Override the User-Agent header. Leave blank to use the default crawler UA."
          />
        </div>
      </Section>

      <Section
        title="Seeds & domains"
        description="Where the crawler starts and how far it's allowed to wander. URLs outside the allowed domains are dropped."
      >
        <StringList
          label="Seed URLs"
          values={cfg.seed_urls}
          onChange={(i, v) => setListItem("seed_urls", i, v)}
          onAdd={() => addListItem("seed_urls")}
          onDel={(i) => delListItem("seed_urls", i)}
          placeholder="https://www.example.com/"
          hint="Starting pages. The crawl begins from each of these and walks outward. At least one is required."
        />
        <StringList
          label="Allowed domains"
          values={cfg.allowed_domains}
          onChange={(i, v) => setListItem("allowed_domains", i, v)}
          onAdd={() => addListItem("allowed_domains")}
          onDel={(i) => delListItem("allowed_domains", i)}
          placeholder="example.com"
          hint="Hostnames the crawler is allowed to fetch. Subdomains are matched by suffix (example.com also matches www.example.com)."
        />
      </Section>

      <Section
        title="URL filters"
        description="Optional per-URL regex filters applied before fetching. Use these to skip large or irrelevant sections (PDFs, image galleries, login pages)."
      >
        <StringList
          label="Include patterns (regex, optional)"
          values={cfg.include_patterns}
          onChange={(i, v) => setListItem("include_patterns", i, v)}
          onAdd={() => addListItem("include_patterns")}
          onDel={(i) => delListItem("include_patterns", i)}
          placeholder="^/services/"
          mono
          hint="If any are set, only URL paths matching at least one are kept. Leave empty to allow all paths."
        />
        <StringList
          label="Exclude patterns (regex, optional)"
          values={cfg.exclude_patterns}
          onChange={(i, v) => setListItem("exclude_patterns", i, v)}
          onAdd={() => addListItem("exclude_patterns")}
          onDel={(i) => delListItem("exclude_patterns", i)}
          placeholder="\\.pdf$"
          mono
          hint="URL paths matching any of these are dropped. Applied after Include patterns."
        />
      </Section>

      <Section
        title="Recent runs"
        description="Last 20 runs, newest first. Status flips to done/failed when the background task finishes — hit Refresh to update."
        bodyClassName={runs.length === 0 ? "p-0" : "p-0"}
      >
        {runs.length === 0 ? (
          <EmptyState
            icon={Clock}
            title="No runs yet"
            description="Crawls appear here once you click Run now or the scheduled cron fires."
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-left text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-2.5">Started</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Trigger</th>
                <th className="px-4 py-2.5 text-right">Pages</th>
                <th className="px-4 py-2.5 text-right">Processed</th>
                <th className="px-4 py-2.5 text-right">Failed</th>
                <th className="px-4 py-2.5 text-right">Skipped</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const f = r.summary?.frontier || {};
                const c = r.summary?.counts || {};
                const runId = r.run_id || r.id;
                const isSel = selectedRun && (selectedRun.run_id || selectedRun.id) === runId;
                return (
                  <tr
                    key={runId}
                    onClick={() => openRun(r)}
                    className={`border-t border-border cursor-pointer hover:bg-muted/30 ${isSel ? "bg-primary/5" : ""}`}
                  >
                    <td className="px-4 py-2.5 text-muted-foreground">{formatDate(r.started_at)}</td>
                    <td className="px-4 py-2.5"><RunStatusBadge status={r.status} /></td>
                    <td className="px-4 py-2.5 text-xs">{r.triggered_by || r.trigger || "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{f.total ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{c.processed ?? f.success ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{f.failed ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{f.skipped ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Section>

      {selectedRun && (
        <Section
          title="Per-page results"
          description={`Run ${(selectedRun.run_id || selectedRun.id || "").slice(0, 8)} — raw HTML, extracted content, processing artifacts (chunks · summary · keywords · embedding), logs, and status per URL. Click a row for the full record.`}
          bodyClassName="p-0"
        >
          {pagesLoading ? (
            <div className="p-6 text-sm text-muted-foreground">Loading pages…</div>
          ) : pages.length === 0 ? (
            <EmptyState icon={Clock} title="No page records" description="This run produced no per-page records yet." />
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-muted-foreground text-left text-xs uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-2.5">URL</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5 text-right">HTTP</th>
                  <th className="px-4 py-2.5 text-right">Depth</th>
                  <th className="px-4 py-2.5 text-right">Tries</th>
                  <th className="px-4 py-2.5 text-right">HTML</th>
                  <th className="px-4 py-2.5 text-right">Chunks</th>
                  <th className="px-4 py-2.5 text-right">KW</th>
                  <th className="px-4 py-2.5 text-right">Emb</th>
                </tr>
              </thead>
              <tbody>
                {pages.map((p) => (
                  <tr
                    key={p.id}
                    onClick={() => openPageDetail(p.id)}
                    className="border-t border-border cursor-pointer hover:bg-muted/30"
                  >
                    <td className="px-4 py-2.5 max-w-[280px] truncate font-mono text-xs" title={p.url}>{p.url}</td>
                    <td className="px-4 py-2.5"><PageStatusBadge status={p.status} /></td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{p.http_status ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{p.depth ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{p.attempts ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{p.raw_html_bytes ? `${(p.raw_html_bytes / 1024).toFixed(1)}k` : "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{p.processing?.chunk_count ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{p.processing?.keywords?.length ?? "—"}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs">{p.processing?.embedding_dim || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
      )}

      <PageDetailModal page={pageDetail} onClose={() => setPageDetail(null)} />

      <ConfirmDialog
        open={confirmRun}
        onOpenChange={setConfirmRun}
        title="Run a crawl now?"
        description="The crawler runs in the background; progress shows in the runs list below. Existing knowledge entries are not deleted — new pages are upserted on top."
        confirmLabel="Trigger crawl"
        loading={running}
        onConfirm={handleRunNowConfirmed}
      />
    </div>
  );
}

/* ─── helpers ─────────────────────────────────────────────────────────── */

// `Section` is imported from `@/components/admin/Section`. Remaining helpers
// here are tab-specific (grid + typed field wrappers + run-status badge).

function Grid2({ children }) { return <div className="grid grid-cols-2 gap-3">{children}</div>; }

function FieldHint({ hint }) {
  if (!hint) return null;
  return <p className="text-[11px] text-muted-foreground mt-1 leading-snug">{hint}</p>;
}

function TextField({ label, value, onChange, placeholder, mono, hint }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <Input
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={mono ? "font-mono text-xs" : ""}
      />
      <FieldHint hint={hint} />
    </div>
  );
}

function NumField({ label, value, onChange, hint }) {
  return (
    <div>
      <Label className="text-xs">{label}</Label>
      <Input
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
      <FieldHint hint={hint} />
    </div>
  );
}

function Toggle({ label, value, onChange, hint }) {
  return (
    <div>
      <label className="flex items-center gap-2 text-sm">
        <Switch checked={!!value} onCheckedChange={onChange} /> {label}
      </label>
      <FieldHint hint={hint} />
    </div>
  );
}

function StringList({ label, values, onChange, onAdd, onDel, placeholder, mono, hint }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <Label className="text-xs">{label}</Label>
        <Button size="sm" variant="outline" onClick={onAdd}><Plus className="h-3 w-3 mr-1" /> Add</Button>
      </div>
      {hint && <p className="text-[11px] text-muted-foreground mb-1 leading-snug">{hint}</p>}
      <div className="space-y-1">
        {(values || []).map((v, i) => (
          <div key={i} className="flex gap-1">
            <Input
              value={v}
              onChange={(e) => onChange(i, e.target.value)}
              placeholder={placeholder}
              className={mono ? "font-mono text-xs" : ""}
            />
            <Button size="sm" variant="ghost" onClick={() => onDel(i)}>
              <Trash2 className="h-3.5 w-3.5 text-destructive" />
            </Button>
          </div>
        ))}
        {(!values || values.length === 0) && (
          <div className="text-xs text-muted-foreground">(none)</div>
        )}
      </div>
    </div>
  );
}

function RunStatusBadge({ status }) {
  if (status === "completed" || status === "success") return <Badge className="bg-success/10 text-success border-success/20 gap-1"><CheckCircle2 className="h-3 w-3" />done</Badge>;
  if (status === "failed")    return <Badge className="bg-destructive/10 text-destructive border-destructive/20 gap-1"><XCircle className="h-3 w-3" />failed</Badge>;
  if (status === "running")   return <Badge className="bg-primary/10 text-primary border-primary/20 gap-1"><Clock className="h-3 w-3 animate-pulse" />running</Badge>;
  if (status === "skipped")   return <Badge className="bg-warning/10 text-warning border-warning/20">skipped</Badge>;
  return <Badge variant="secondary">{status || "—"}</Badge>;
}

function PageStatusBadge({ status }) {
  if (status === "processed") return <Badge className="bg-success/10 text-success border-success/20">processed</Badge>;
  if (status === "failed")    return <Badge className="bg-destructive/10 text-destructive border-destructive/20">failed</Badge>;
  if (status === "skipped")   return <Badge className="bg-warning/10 text-warning border-warning/20">skipped</Badge>;
  return <Badge variant="secondary">{status || "—"}</Badge>;
}

function PageDetailModal({ page, onClose }) {
  if (!page) return null;
  const proc = page.processing || {};
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="bg-card border border-border rounded-xl shadow-lg max-w-3xl w-full max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-border flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground truncate">{page.title || "(no title)"}</p>
            <p className="text-xs text-muted-foreground font-mono truncate">{page.url}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <PageStatusBadge status={page.status} />
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={onClose}><XCircle className="h-4 w-4" /></Button>
          </div>
        </div>
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4 text-sm">
          <div className="grid grid-cols-4 gap-3 text-xs">
            <Meta label="HTTP" value={page.http_status ?? "—"} />
            <Meta label="Depth" value={page.depth ?? "—"} />
            <Meta label="Attempts" value={page.attempts ?? "—"} />
            <Meta label="Category" value={page.category || "—"} />
            <Meta label="Raw HTML" value={page.raw_html_bytes ? `${(page.raw_html_bytes / 1024).toFixed(1)} KB` : "—"} />
            <Meta label="Extracted" value={page.extracted_length ? `${page.extracted_length} chars` : "—"} />
            <Meta label="Chunks" value={proc.chunk_count ?? "—"} />
            <Meta label="Embedding" value={proc.embedding_dim ? `${proc.embedding_dim}-dim` : "—"} />
          </div>
          {page.error && (
            <div className="rounded border border-destructive/30 bg-destructive/10 text-destructive text-xs p-2">{page.error}</div>
          )}
          {page.skip_reason && (
            <div className="rounded border border-warning/30 bg-warning/10 text-warning text-xs p-2">Skipped: {page.skip_reason}</div>
          )}
          {proc.summary && <Block label="Summary">{proc.summary}</Block>}
          {proc.keywords?.length > 0 && (
            <div>
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Keywords</p>
              <div className="flex flex-wrap gap-1">
                {proc.keywords.map((k) => <Badge key={k} variant="secondary" className="text-xs">{k}</Badge>)}
              </div>
            </div>
          )}
          {proc.embedding_preview?.length > 0 && (
            <Block label={`Dummy embedding (first ${proc.embedding_preview.length} of ${proc.embedding_dim})`} mono>
              [{proc.embedding_preview.join(", ")}, …]
            </Block>
          )}
          {proc.chunks?.length > 0 && (
            <div>
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">Chunks ({proc.chunk_count})</p>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {proc.chunks.map((ch, i) => (
                  <div key={i} className="bg-muted/50 border border-border rounded p-2 text-xs">
                    <span className="text-muted-foreground mr-2">#{i + 1}</span>{ch.slice(0, 240)}{ch.length > 240 ? "…" : ""}
                  </div>
                ))}
              </div>
            </div>
          )}
          {proc.log?.length > 0 && (
            <Block label="Processing log" mono>
              {proc.log.map((l, i) => <div key={i}>• {l}</div>)}
            </Block>
          )}
          {page.raw_html && (
            <Block label={`Raw HTML (${(page.raw_html_bytes / 1024).toFixed(1)} KB)`} mono scroll>
              {page.raw_html.slice(0, 4000)}{page.raw_html.length > 4000 ? "\n…(truncated)" : ""}
            </Block>
          )}
        </div>
      </div>
    </div>
  );
}

function Meta({ label, value }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="text-foreground font-mono">{value}</p>
    </div>
  );
}

function Block({ label, children, mono, scroll }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">{label}</p>
      <div className={`bg-muted/50 border border-border rounded p-2 text-xs ${mono ? "font-mono whitespace-pre-wrap break-all" : ""} ${scroll ? "max-h-48 overflow-y-auto" : ""}`}>
        {children}
      </div>
    </div>
  );
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch { return iso; }
}
