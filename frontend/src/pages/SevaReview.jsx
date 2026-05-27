import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { CheckCircle, AlertTriangle, FileText } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Review page rendered after a user submits an application — they land
 * here from an emailed link, double-check the auto-filled fields, edit
 * if needed, then confirm. Once confirmed the PDF is mailed and the
 * record locks.
 *
 * Tenant-neutral by design (no CGI / Acme styling baked in). Branding
 * and reference colours come from the design tokens; tenants can
 * override by setting CSS custom properties on the root.
 */
export default function SevaReview() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [editedData, setEditedData] = useState({});
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    fetch(`${API}/seva-setu/review/${token}`)
      .then(r => r.json())
      .then(d => {
        setData(d);
        setEditedData(d.form_data || {});
        setLoading(false);
      })
      .catch(() => { setError("Failed to load review. Please try again."); setLoading(false); });
  }, [token]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API}/seva-setu/review/${token}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ form_data: editedData }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Save failed");
      toast.success("Changes saved.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      await handleSave();
      const res = await fetch(`${API}/seva-setu/review/${token}/confirm`, { method: "POST" });
      if (!res.ok) throw new Error((await res.json()).detail || "Confirmation failed");
      setConfirmed(true);
      toast.success("Application confirmed. Check your email for the PDF.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setConfirming(false);
    }
  };

  if (loading) {
    return (
      <CenteredCard>
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-sm text-muted-foreground">Loading your application…</p>
      </CenteredCard>
    );
  }

  if (error) {
    return (
      <CenteredCard>
        <div className="h-12 w-12 rounded-full bg-destructive/10 flex items-center justify-center mx-auto mb-4">
          <AlertTriangle className="h-6 w-6 text-destructive" />
        </div>
        <h2 className="text-base font-semibold text-foreground mb-1">Error</h2>
        <p className="text-sm text-muted-foreground">{error}</p>
      </CenteredCard>
    );
  }

  if (data?.expired) {
    return (
      <CenteredCard>
        <div className="h-12 w-12 rounded-full bg-warning/10 flex items-center justify-center mx-auto mb-4">
          <AlertTriangle className="h-6 w-6 text-warning" />
        </div>
        <h2 className="text-base font-semibold text-foreground mb-1">Review link expired</h2>
        <p className="text-sm text-muted-foreground">{data.message}</p>
        {data.reference_id && (
          <p className="text-xs text-muted-foreground mt-3">
            Reference <code className="font-mono text-foreground">{data.reference_id}</code>
          </p>
        )}
        <Button className="mt-6" onClick={() => navigate("/consular")}>Back to chat</Button>
      </CenteredCard>
    );
  }

  if (confirmed) {
    return (
      <CenteredCard>
        <div className="h-14 w-14 rounded-full bg-success/10 flex items-center justify-center mx-auto mb-4">
          <CheckCircle className="h-7 w-7 text-success" />
        </div>
        <h2 className="text-lg font-semibold text-foreground mb-1">Application confirmed</h2>
        <p className="text-sm text-muted-foreground">
          Your <span className="font-medium text-foreground">{data?.service_name}</span> application is locked.
        </p>
        <p className="text-xs font-mono text-foreground mt-3">{data?.reference_id}</p>
        <p className="text-xs text-muted-foreground mt-2">
          A confirmation email with your PDF has been sent.
        </p>
        <Button className="mt-6" onClick={() => navigate("/consular")}>Back to chat</Button>
      </CenteredCard>
    );
  }

  const fields = data?.fields || [];
  const entries = fields.length > 0
    ? fields.map(f => ({ key: f.key, label: f.label }))
    : Object.keys(editedData).map(k => ({ key: k, label: k.replace(/_/g, " ") }));

  return (
    <div className="min-h-screen bg-background text-foreground p-4">
      <div className="max-w-2xl mx-auto pt-8 space-y-4">
        {/* Header */}
        <div className="bg-card border border-border rounded-lg px-5 py-4">
          <h1 className="text-lg font-semibold tracking-tight">Review your application</h1>
          {data?.brand && <p className="text-xs text-muted-foreground mt-0.5">{data.brand}</p>}
        </div>

        {/* Meta */}
        <div className="bg-card border border-border rounded-lg px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Service</p>
              <p className="text-sm font-medium text-foreground mt-0.5">{data?.service_name}</p>
            </div>
            <div className="text-right">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground">Reference</p>
              <p className="text-sm font-mono font-semibold text-foreground mt-0.5">{data?.reference_id}</p>
            </div>
          </div>
        </div>

        {/* Editable form */}
        <div className="bg-card border border-border rounded-lg">
          <div className="px-5 py-3 border-b border-border">
            <h3 className="text-sm font-semibold text-foreground">Your details</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Please check every field. Saved changes apply immediately; confirming locks the application.
            </p>
          </div>
          <div className="px-5 py-4 space-y-4">
            {entries.map(({ key, label }) => (
              <div key={key}>
                <Label className="text-xs">{label}</Label>
                <Input
                  type="text"
                  value={editedData[key] || ""}
                  onChange={e => setEditedData(prev => ({ ...prev, [key]: e.target.value }))}
                  className="mt-1"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Documents */}
        {(data?.documents || []).length > 0 && (
          <div className="bg-card border border-border rounded-lg">
            <div className="px-5 py-3 border-b border-border">
              <h3 className="text-sm font-semibold text-foreground">Uploaded documents</h3>
            </div>
            <ul className="divide-y divide-border">
              {data.documents.map((d, i) => (
                <li key={i} className="px-5 py-3 flex items-center gap-3 text-sm">
                  <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-foreground flex-1 min-w-0 truncate">{d.name || d.filename}</span>
                  <span className="text-xs text-success font-medium shrink-0">Uploaded</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 sticky bottom-4 bg-background/95 backdrop-blur p-3 border border-border rounded-lg shadow-sm">
          <Button
            variant="outline"
            onClick={handleSave}
            disabled={saving || confirming}
            className="flex-1"
          >
            {saving ? "Saving…" : "Save changes"}
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={saving || confirming}
            className="flex-1"
          >
            {confirming ? "Confirming…" : "Confirm & submit"}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground text-center">
          Confirming locks this application and emails your PDF.
        </p>
      </div>
    </div>
  );
}

function CenteredCard({ children }) {
  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-4">
      <div className="bg-card border border-border rounded-lg p-8 max-w-md w-full text-center shadow-sm">
        {children}
      </div>
    </div>
  );
}
