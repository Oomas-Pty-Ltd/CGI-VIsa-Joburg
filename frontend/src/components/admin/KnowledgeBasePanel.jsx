/**
 * KnowledgeBasePanel — the knowledge-base manager shared by the Super Admin
 * and Tenant Admin consoles so both have identical UX (columns, filters,
 * source badges, PDF upload, preview, manual create/edit, delete).
 *
 * Props:
 *   token       — bearer token
 *   crossTenant — true for super-admin (adds the cross-tenant Tenant selector
 *                 on upload/create + a Tenant filter). false for a tenant
 *                 admin, who is implicitly scoped to their own tenant by the
 *                 backend (enforce_tenant_scope).
 *   companies   — [{id,name}] for the tenant selectors (super-admin only)
 *   companyId   — the tenant-admin's own company id; required so manual
 *                 create can pass ?company_id (the backend re-scopes it to
 *                 the JWT tenant anyway, but the query param is mandatory).
 *
 * List/upload/delete hit /super-admin/knowledge/*; manual create/edit hit
 * /admin/knowledge — both behind verify_admin + enforce_tenant_scope, so a
 * local-admin is always re-scoped to their own tenant server-side.
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Upload, FileText, BookOpen, RefreshCw, Trash2, Clock, AlertCircle,
  Calendar, ChevronLeft, ChevronRight, Plus, Pencil,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const KB = `${API}/super-admin/knowledge`;

const CATEGORIES = ["general", "fees", "emergency", "office", "announcement", "event", "other"];

const EVENT_STATUS_STYLES = {
  past:    { bg: "bg-muted text-muted-foreground",  icon: Clock,        label: "Past" },
  present: { bg: "bg-success/10 text-success",      icon: AlertCircle,  label: "Live" },
  future:  { bg: "bg-primary/10 text-primary",      icon: Calendar,     label: "Upcoming" },
  general: { bg: "bg-warning/10 text-warning",      icon: FileText,     label: "General" },
};

function EventBadge({ status }) {
  const cfg = EVENT_STATUS_STYLES[status] || EVENT_STATUS_STYLES.general;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg}`}>
      <Icon className="w-3 h-3" />{cfg.label}
    </span>
  );
}

const SOURCE_STYLES = {
  manual: { label: "Manual",  cls: "bg-muted text-muted-foreground border border-border" },
  crawl:  { label: "Crawler", cls: "bg-primary/10 text-primary border border-primary/20" },
  pdf:    { label: "PDF",     cls: "bg-warning/10 text-warning border border-warning/20" },
};

function SourceBadge({ type }) {
  const cfg = SOURCE_STYLES[type] || SOURCE_STYLES.manual;
  return <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cfg.cls}`}>{cfg.label}</span>;
}

function Pagination({ page, total, limit, onChange }) {
  const pages = Math.ceil(total / limit) || 1;
  return (
    <div className="flex items-center gap-3 justify-end mt-4 text-sm text-muted-foreground">
      <span>{total} records</span>
      <Button variant="outline" size="icon" className="h-7 w-7" onClick={() => onChange(page - 1)} disabled={page <= 1}>
        <ChevronLeft className="w-4 h-4" />
      </Button>
      <span className="font-medium">Page {page} / {pages}</span>
      <Button variant="outline" size="icon" className="h-7 w-7" onClick={() => onChange(page + 1)} disabled={page >= pages}>
        <ChevronRight className="w-4 h-4" />
      </Button>
    </div>
  );
}

function formatDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

const EVENT_STATUS_OPTIONS = [
  { value: "auto", label: "Auto / general" },
  { value: "past", label: "Past" },
  { value: "present", label: "Live / Today" },
  { value: "future", label: "Upcoming" },
];

const EMPTY_DRAFT = {
  title: "", question: "", answer: "", category: "general", keywords: "",
  source: "", valid_from: "", valid_until: "", event_status: "auto",
};

export default function KnowledgeBasePanel({ token, crossTenant = false, companies = [], companyId = "" }) {
  const authHdr = { Authorization: `Bearer ${token}` };

  /* upload */
  const [file, setFile] = useState(null);
  const [docTitle, setDocTitle] = useState("");
  const [category, setCategory] = useState("general");
  const [uploadCompanyId, setUploadCompanyId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  /* list */
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loadingList, setLoadingList] = useState(false);
  const [filterStatus, setFilterStatus] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterCompany, setFilterCompany] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [sourceCounts, setSourceCounts] = useState({});
  const [pdfFiles, setPdfFiles] = useState([]);
  const [filterFile, setFilterFile] = useState("");

  const [preview, setPreview] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  /* manual create / edit */
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState(null);          // null = create, else the entry being edited
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [editorCompanyId, setEditorCompanyId] = useState("");
  const [savingEntry, setSavingEntry] = useState(false);
  const [loadingEntry, setLoadingEntry] = useState(false);

  const limit = 50;

  useEffect(() => {
    if (crossTenant && !uploadCompanyId && companies.length > 0) setUploadCompanyId(companies[0].id);
  }, [crossTenant, companies, uploadCompanyId]);

  const fetchEntries = useCallback(async () => {
    setLoadingList(true);
    try {
      const params = new URLSearchParams({ page, limit });
      if (filterStatus) params.set("event_status", filterStatus);
      if (filterCategory) params.set("category", filterCategory);
      if (filterFile) params.set("pdf_filename", filterFile);
      if (filterSource) params.set("source_type", filterSource);
      if (crossTenant && filterCompany) params.set("company_id", filterCompany);
      const [entriesRes, filesRes] = await Promise.all([
        fetch(`${KB}/entries?${params}`, { headers: authHdr }),
        fetch(`${KB}/pdf-files`, { headers: authHdr }),
      ]);
      const entData = await entriesRes.json();
      const fileData = await filesRes.json();
      if (!entriesRes.ok) throw new Error(entData.detail || "Failed to load");
      setEntries(entData.entries || []);
      setTotal(entData.total || 0);
      setSourceCounts(entData.source_counts || {});
      setPdfFiles(fileData.files || []);
    } catch (e) {
      toast.error(typeof e.message === "string" ? e.message : "Failed to load knowledge entries");
    } finally {
      setLoadingList(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, filterStatus, filterCategory, filterFile, filterSource, filterCompany, crossTenant, token]);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) { toast.error("Please select a PDF file."); return; }
    if (crossTenant && !uploadCompanyId) { toast.error("Pick a tenant to upload the PDF under."); return; }
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("title", docTitle);
      form.append("category", category);
      // Tenant admins omit company_id — the backend scopes to their tenant.
      if (crossTenant) form.append("company_id", uploadCompanyId);

      const res = await fetch(`${KB}/upload-pdf`, { method: "POST", headers: authHdr, body: form });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string" ? data.detail
          : Array.isArray(data.detail) ? data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
          : (data.message || "Upload failed");
        toast.error(msg, { duration: 8000 });
        return;
      }
      const ocrNote = data.ocr_used ? " via OCR" : "";
      const modeNote = data.faq_mode ? " as FAQ pairs" : "";
      toast.success(`PDF processed — ${data.sections_created} entries created${modeNote}${ocrNote}.`);
      setFile(null); setDocTitle(""); setCategory("general");
      if (fileInputRef.current) fileInputRef.current.value = "";
      fetchEntries();
    } catch (err) {
      toast.error(err.message || "Upload failed — please try again.", { duration: 6000 });
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteConfirmed = async () => {
    if (!confirmDelete) return;
    setDeleting(true);
    try {
      const res = await fetch(`${KB}/entries/${confirmDelete.id}`, { method: "DELETE", headers: authHdr });
      if (!res.ok) throw new Error();
      toast.success("Entry deleted.");
      setConfirmDelete(null);
      fetchEntries();
    } catch {
      toast.error("Failed to delete entry.");
    } finally {
      setDeleting(false);
    }
  };

  const openCreate = () => {
    setEditing(null);
    setDraft(EMPTY_DRAFT);
    // Default the tenant to whatever the list is filtered to, else the first.
    setEditorCompanyId(crossTenant ? (filterCompany || companies[0]?.id || "") : companyId);
    setEditorOpen(true);
  };

  const openEdit = async (entry) => {
    setEditing(entry);
    setEditorCompanyId(crossTenant ? (entry.company_id || "") : companyId);
    setEditorOpen(true);
    setLoadingEntry(true);
    // The list endpoint only returns a truncated answer_preview + 6 keywords,
    // so pull the full row from /admin/knowledge/{id} to pre-fill the form.
    try {
      const params = new URLSearchParams();
      if (crossTenant && entry.company_id) params.set("company_id", entry.company_id);
      const res = await fetch(`${API}/admin/knowledge/${entry.id}?${params}`, { headers: authHdr });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load entry");
      setDraft({
        title: data.title || "",
        question: data.question || "",
        answer: data.answer || "",
        category: data.category || "general",
        keywords: (data.keywords || []).join(", "),
        source: data.source || "",
        valid_from: data.valid_from || "",
        valid_until: data.valid_until || "",
        event_status: data.event_status || "auto",
      });
    } catch (e) {
      toast.error(typeof e.message === "string" ? e.message : "Failed to load entry");
      setEditorOpen(false);
    } finally {
      setLoadingEntry(false);
    }
  };

  const handleSaveEntry = async (e) => {
    e.preventDefault();
    if (!draft.title.trim() || !draft.answer.trim()) {
      toast.error("Title and answer are required."); return;
    }
    const effectiveCompanyId = crossTenant ? editorCompanyId : companyId;
    if (!effectiveCompanyId) {
      toast.error(crossTenant ? "Pick a tenant for this entry." : "Missing tenant context."); return;
    }
    const keywords = draft.keywords.split(",").map((k) => k.trim()).filter(Boolean);
    const eventStatus = draft.event_status === "auto" ? "" : draft.event_status;
    setSavingEntry(true);
    try {
      let res;
      if (editing) {
        // PUT — company_id is an optional scoping query param.
        const params = new URLSearchParams();
        if (crossTenant && effectiveCompanyId) params.set("company_id", effectiveCompanyId);
        res = await fetch(`${API}/admin/knowledge/${editing.id}?${params}`, {
          method: "PUT", headers: { ...authHdr, "Content-Type": "application/json" },
          body: JSON.stringify({
            title: draft.title.trim(), question: draft.question.trim(), answer: draft.answer.trim(),
            keywords, source: draft.source.trim(),
            valid_from: draft.valid_from, valid_until: draft.valid_until, event_status: eventStatus,
          }),
        });
      } else {
        // POST — company_id is a required query param.
        res = await fetch(`${API}/admin/knowledge?company_id=${encodeURIComponent(effectiveCompanyId)}`, {
          method: "POST", headers: { ...authHdr, "Content-Type": "application/json" },
          body: JSON.stringify({
            category: draft.category, title: draft.title.trim(),
            question: draft.question.trim(), answer: draft.answer.trim(),
            keywords, source: draft.source.trim(),
            valid_from: draft.valid_from || null, valid_until: draft.valid_until || null,
            event_status: eventStatus || null,
          }),
        });
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = typeof data.detail === "string" ? data.detail
          : Array.isArray(data.detail) ? data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
          : "Failed to save entry";
        toast.error(msg, { duration: 8000 });
        return;
      }
      toast.success(editing ? "Entry updated." : "Knowledge entry created.");
      setEditorOpen(false);
      fetchEntries();
    } catch (err) {
      toast.error(err.message || "Failed to save entry.");
    } finally {
      setSavingEntry(false);
    }
  };

  const setField = (k, v) => setDraft((d) => ({ ...d, [k]: v }));

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.type === "application/pdf") {
      setFile(dropped);
      if (!docTitle) setDocTitle(dropped.name.replace(/\.pdf$/i, "").replace(/_/g, " "));
    } else {
      toast.error("Only PDF files are accepted.");
    }
  };

  const allCount = (sourceCounts.manual || 0) + (sourceCounts.crawl || 0) + (sourceCounts.pdf || 0);

  return (
    <div className="space-y-8">
      {/* Upload card */}
      <div className="bg-card border border-border rounded-lg shadow-sm p-6">
        <h2 className="text-sm font-semibold tracking-tight text-foreground mb-4 flex items-center gap-2">
          <Upload className="w-4 h-4 text-primary" /> Upload PDF to knowledge base
        </h2>
        <form onSubmit={handleUpload} className="space-y-4">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              dragOver ? "border-primary bg-warning/10" : file ? "border-success/40 bg-success/10" : "border-border hover:border-primary hover:bg-warning/10"
            }`}
          >
            <input
              ref={fileInputRef} type="file" accept=".pdf" className="hidden"
              onChange={(e) => { const f = e.target.files[0]; if (f) { setFile(f); if (!docTitle) setDocTitle(f.name.replace(/\.pdf$/i, "").replace(/_/g, " ")); } }}
            />
            {file ? (
              <div className="flex items-center justify-center gap-2 text-success">
                <FileText className="w-6 h-6" />
                <span className="font-medium">{file.name}</span>
                <span className="text-sm text-muted-foreground">({(file.size / 1024).toFixed(0)} KB)</span>
              </div>
            ) : (
              <div className="text-muted-foreground">
                <Upload className="w-10 h-10 mx-auto mb-2 text-muted-foreground" />
                <p className="font-medium">Drag &amp; drop a PDF here, or click to browse</p>
                <p className="text-sm mt-1">Max 50 MB · PDF only</p>
              </div>
            )}
          </div>

          <div className={`grid grid-cols-1 gap-4 ${crossTenant ? "md:grid-cols-3" : "md:grid-cols-2"}`}>
            <div>
              <Label className="text-sm text-muted-foreground mb-1 block">Document Title (optional)</Label>
              <Input value={docTitle} onChange={(e) => setDocTitle(e.target.value)} placeholder="e.g. Visa Policy Update April 2026" />
            </div>
            <div>
              <Label className="text-sm text-muted-foreground mb-1 block">Category</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger><SelectValue placeholder="Select category" /></SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            {crossTenant && (
              <div>
                <Label className="text-sm text-muted-foreground mb-1 block">Tenant</Label>
                <Select value={uploadCompanyId} onValueChange={setUploadCompanyId}>
                  <SelectTrigger><SelectValue placeholder="Pick a tenant" /></SelectTrigger>
                  <SelectContent>
                    {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={uploading || !file}>
              {uploading ? (<><RefreshCw className="w-4 h-4 mr-2 animate-spin" />Processing PDF…</>) : (<><Upload className="w-4 h-4 mr-2" />Upload &amp; Extract</>)}
            </Button>
            {file && (
              <Button type="button" variant="outline" onClick={() => { setFile(null); setDocTitle(""); if (fileInputRef.current) fileInputRef.current.value = ""; }}>
                Clear
              </Button>
            )}
          </div>

          <div className="bg-primary/10 border border-primary/20 rounded-lg p-4 text-sm text-primary">
            <p className="font-semibold mb-1">Date-aware extraction</p>
            <p>
              Dates found in the PDF are automatically parsed. Each section is labelled:
              <span className="mx-1 px-1.5 py-0.5 rounded bg-muted text-foreground text-xs font-medium">Past</span>,
              <span className="mx-1 px-1.5 py-0.5 rounded bg-success/15 text-success text-xs font-medium">Live</span>,
              <span className="mx-1 px-1.5 py-0.5 rounded bg-primary/15 text-primary text-xs font-medium">Upcoming</span>,
              <span className="mx-1 px-1.5 py-0.5 rounded bg-warning/15 text-warning text-xs font-medium">General</span>.
              The bot uses this context to answer accurately.
            </p>
          </div>
        </form>
      </div>

      {/* Entries list */}
      <div className="bg-card border border-border rounded-lg shadow-sm p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-primary" /> Knowledge entries
            {total > 0 && <span className="text-xs font-normal text-muted-foreground">({total} total)</span>}
          </h2>
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={openCreate} className="h-8" data-testid="kb-new-entry">
              <Plus className="w-4 h-4 mr-1" /> New entry
            </Button>
            <Button variant="outline" size="sm" onClick={fetchEntries} className="h-8">
              <RefreshCw className="w-4 h-4 mr-1" /> Refresh
            </Button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-5">
          {crossTenant && (
            <div>
              <Label className="text-xs text-muted-foreground mb-1 block">Tenant</Label>
              <Select value={filterCompany || "all"} onValueChange={(v) => { setFilterCompany(v === "all" ? "" : v); setPage(1); }}>
                <SelectTrigger className="w-52 h-9 text-sm"><SelectValue placeholder="All tenants" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All tenants</SelectItem>
                  {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          <div>
            <Label className="text-xs text-muted-foreground mb-1 block">Date Status</Label>
            <Select value={filterStatus} onValueChange={(v) => { setFilterStatus(v === "all" ? "" : v); setPage(1); }}>
              <SelectTrigger className="w-36 h-9 text-sm"><SelectValue placeholder="All statuses" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="past">Past</SelectItem>
                <SelectItem value="present">Live / Today</SelectItem>
                <SelectItem value="future">Upcoming</SelectItem>
                <SelectItem value="general">General</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-muted-foreground mb-1 block">Category</Label>
            <Select value={filterCategory} onValueChange={(v) => { setFilterCategory(v === "all" ? "" : v); setPage(1); }}>
              <SelectTrigger className="w-36 h-9 text-sm"><SelectValue placeholder="All categories" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-muted-foreground mb-1 block">Source</Label>
            <Select value={filterSource} onValueChange={(v) => { setFilterSource(v === "all" ? "" : v); setPage(1); }}>
              <SelectTrigger className="w-40 h-9 text-sm"><SelectValue placeholder="All sources" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All sources{sourceCounts.manual != null ? ` (${allCount})` : ""}</SelectItem>
                <SelectItem value="manual">Manual{sourceCounts.manual != null ? ` (${sourceCounts.manual})` : ""}</SelectItem>
                <SelectItem value="crawl">Crawler{sourceCounts.crawl != null ? ` (${sourceCounts.crawl})` : ""}</SelectItem>
                <SelectItem value="pdf">PDF{sourceCounts.pdf != null ? ` (${sourceCounts.pdf})` : ""}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {pdfFiles.length > 0 && (
            <div>
              <Label className="text-xs text-muted-foreground mb-1 block">PDF File</Label>
              <Select value={filterFile} onValueChange={(v) => { setFilterFile(v === "all" ? "" : v); setPage(1); }}>
                <SelectTrigger className="w-52 h-9 text-sm"><SelectValue placeholder="All files" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All files</SelectItem>
                  {pdfFiles.map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {/* Table */}
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-muted-foreground text-xs uppercase tracking-wide">
              <tr>
                <th className="px-4 py-3 text-left">Title</th>
                <th className="px-4 py-3 text-left">Category</th>
                <th className="px-4 py-3 text-left">Date Status</th>
                <th className="px-4 py-3 text-left">Date Range</th>
                <th className="px-4 py-3 text-left">Source</th>
                <th className="px-4 py-3 text-left">Added</th>
                <th className="px-4 py-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loadingList && (<tr><td colSpan={7} className="text-center py-10 text-muted-foreground">Loading…</td></tr>)}
              {!loadingList && entries.length === 0 && (
                <tr><td colSpan={7} className="text-center py-12 text-muted-foreground">
                  <BookOpen className="w-10 h-10 mx-auto mb-2 text-muted-foreground/60" />
                  No entries yet. Upload a PDF or run a website crawl to populate the knowledge base.
                </td></tr>
              )}
              {!loadingList && entries.map((entry) => (
                <tr key={entry.id} className="border-t border-border hover:bg-warning/10 transition-colors">
                  <td className="px-4 py-3 max-w-[220px]">
                    <button className="text-left font-medium text-foreground hover:text-primary hover:underline truncate block max-w-full" title={entry.title} onClick={() => setPreview(entry)}>
                      {entry.title}
                    </button>
                  </td>
                  <td className="px-4 py-3"><span className="px-2 py-0.5 rounded-full text-xs font-medium bg-warning/10 text-warning">{entry.category}</span></td>
                  <td className="px-4 py-3"><EventBadge status={entry.event_status} /></td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {entry.valid_from ? (entry.valid_from === entry.valid_until || !entry.valid_until ? entry.valid_from : `${entry.valid_from} → ${entry.valid_until}`) : "—"}
                  </td>
                  <td className="px-4 py-3 max-w-[200px]">
                    <SourceBadge type={entry.source_type} />
                    {entry.source_detail && (
                      <div className="text-[11px] text-muted-foreground truncate mt-0.5" title={entry.source_detail}>
                        {entry.source_detail}{entry.source_type === "crawl" && entry.version > 1 ? ` · v${entry.version}` : ""}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">{formatDate(entry.created_at)}</td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:bg-primary/10 hover:text-primary"
                        onClick={() => openEdit(entry)} title="Edit entry">
                        <Pencil className="w-4 h-4" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive hover:bg-destructive/10 hover:text-destructive"
                        onClick={() => setConfirmDelete({ id: entry.id, title: entry.title })} title="Delete entry">
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <Pagination page={page} total={total} limit={limit} onChange={setPage} />
      </div>

      {/* Preview modal */}
      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] p-0 flex flex-col gap-0">
          <DialogHeader className="px-5 py-4 border-b border-border gap-2">
            <DialogTitle className="text-base leading-tight">{preview?.title}</DialogTitle>
            <div className="flex items-center gap-2 flex-wrap">
              {preview && <EventBadge status={preview.event_status} />}
              {preview && <Badge variant="outline" className="font-normal">{preview.category}</Badge>}
              {preview?.valid_from && (
                <span className="text-xs text-muted-foreground">
                  {preview.valid_from}{preview.valid_until && preview.valid_until !== preview.valid_from ? ` → ${preview.valid_until}` : ""}
                </span>
              )}
            </div>
            {preview?.keywords?.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {preview.keywords.map((kw) => <span key={kw} className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground text-xs">{kw}</span>)}
              </div>
            )}
          </DialogHeader>
          <div className="overflow-y-auto flex-1 px-5 py-4">
            <p className="text-xs text-muted-foreground mb-3 flex items-center gap-2">
              {preview && <SourceBadge type={preview.source_type} />}
              {preview?.source_detail || "Manually authored"}
              {preview?.source_type === "crawl" && preview?.version > 1 ? ` · v${preview.version}` : ""}
            </p>
            <pre className="whitespace-pre-wrap text-sm text-foreground font-sans leading-relaxed">{preview?.answer_preview}</pre>
          </div>
        </DialogContent>
      </Dialog>

      {/* Create / edit modal */}
      <Dialog open={editorOpen} onOpenChange={(o) => { if (!o) { setEditorOpen(false); setEditing(null); } }}>
        <DialogContent className="max-w-2xl max-h-[90vh] p-0 flex flex-col gap-0">
          <DialogHeader className="px-5 py-4 border-b border-border">
            <DialogTitle className="text-base">
              {editing ? `Edit: ${editing.title}` : "New knowledge entry"}
            </DialogTitle>
          </DialogHeader>
          {loadingEntry ? (
            <div className="px-5 py-12 text-center text-muted-foreground text-sm">Loading entry…</div>
          ) : (
          <form onSubmit={handleSaveEntry} className="flex flex-col flex-1 min-h-0">
            <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">
              <p className="text-xs text-muted-foreground">
                Entries are searched at chat time and used as grounding context for the bot's answers.
              </p>
              <div>
                <Label className="text-sm mb-1 block">Title <span className="text-destructive">*</span></Label>
                <Input value={draft.title} onChange={(e) => setField("title", e.target.value)}
                  placeholder="e.g. Visa fee schedule 2026" data-testid="kb-editor-title" />
              </div>
              <div>
                <Label className="text-sm mb-1 block">Question <span className="text-xs text-muted-foreground">(optional)</span></Label>
                <Input value={draft.question} onChange={(e) => setField("question", e.target.value)}
                  placeholder="A representative question a user might ask — helps retrieval match this entry." />
              </div>
              <div>
                <Label className="text-sm mb-1 block">Answer <span className="text-destructive">*</span></Label>
                <Textarea rows={6} value={draft.answer} onChange={(e) => setField("answer", e.target.value)}
                  placeholder="The information the bot should use to answer. Write it as you'd want it spoken to the user."
                  data-testid="kb-editor-answer" />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {editing ? (
                  <div>
                    <Label className="text-sm mb-1 block">Category</Label>
                    <div className="h-10 flex items-center">
                      <Badge variant="outline" className="font-normal">{editing.category}</Badge>
                      <span className="text-xs text-muted-foreground ml-2">(set at creation)</span>
                    </div>
                  </div>
                ) : (
                  <div>
                    <Label className="text-sm mb-1 block">Category</Label>
                    <Select value={draft.category} onValueChange={(v) => setField("category", v)}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <div>
                  <Label className="text-sm mb-1 block">Date status</Label>
                  <Select value={draft.event_status} onValueChange={(v) => setField("event_status", v)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {EVENT_STATUS_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {crossTenant && !editing && (
                <div>
                  <Label className="text-sm mb-1 block">Tenant <span className="text-destructive">*</span></Label>
                  <Select value={editorCompanyId} onValueChange={setEditorCompanyId}>
                    <SelectTrigger><SelectValue placeholder="Pick a tenant" /></SelectTrigger>
                    <SelectContent>
                      {companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label className="text-sm mb-1 block">Valid from <span className="text-xs text-muted-foreground">(optional)</span></Label>
                  <Input type="date" value={draft.valid_from} onChange={(e) => setField("valid_from", e.target.value)} />
                </div>
                <div>
                  <Label className="text-sm mb-1 block">Valid until <span className="text-xs text-muted-foreground">(optional)</span></Label>
                  <Input type="date" value={draft.valid_until} onChange={(e) => setField("valid_until", e.target.value)} />
                </div>
              </div>
              <div>
                <Label className="text-sm mb-1 block">Keywords <span className="text-xs text-muted-foreground">(comma-separated, optional)</span></Label>
                <Input value={draft.keywords} onChange={(e) => setField("keywords", e.target.value)}
                  placeholder="visa, fee, payment" />
              </div>
              <div>
                <Label className="text-sm mb-1 block">Source <span className="text-xs text-muted-foreground">(optional)</span></Label>
                <Input value={draft.source} onChange={(e) => setField("source", e.target.value)}
                  placeholder="e.g. Official fee circular, April 2026" />
              </div>
            </div>
            <DialogFooter className="px-5 py-4 border-t border-border">
              <Button type="button" variant="outline" onClick={() => { setEditorOpen(false); setEditing(null); }}>Cancel</Button>
              <Button type="submit" disabled={savingEntry} data-testid="kb-editor-save">
                {savingEntry ? (<><RefreshCw className="w-4 h-4 mr-2 animate-spin" />Saving…</>) : (editing ? "Save changes" : "Create entry")}
              </Button>
            </DialogFooter>
          </form>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(o) => !o && setConfirmDelete(null)}
        title="Delete knowledge entry?"
        description={confirmDelete && `This removes "${confirmDelete.title}" from the knowledge base. The bot will stop using it on the next chat request.`}
        confirmLabel="Delete entry"
        destructive
        loading={deleting}
        onConfirm={handleDeleteConfirmed}
      />
    </div>
  );
}
