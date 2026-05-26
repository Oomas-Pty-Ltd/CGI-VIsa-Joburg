import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { CheckCircle, AlertTriangle, FileText, Download } from "lucide-react";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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
      toast.success("Changes saved successfully.");
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
      toast.success("Application confirmed! Check your email for the PDF.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setConfirming(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-orange-50 to-blue-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-10 h-10 border-4 border-[#E06F2C] border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-600">Loading your application…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-orange-50 to-blue-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-xl p-8 max-w-md w-full text-center">
          <AlertTriangle className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-[#1A2E40] mb-2">Error</h2>
          <p className="text-gray-600">{error}</p>
        </div>
      </div>
    );
  }

  if (data?.expired) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-orange-50 to-blue-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-xl p-8 max-w-md w-full text-center">
          <AlertTriangle className="w-16 h-16 text-amber-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-[#1A2E40] mb-2">Review Link Expired</h2>
          <p className="text-gray-600">{data.message}</p>
          <p className="text-sm text-gray-400 mt-2">Reference: <strong>{data.reference_id}</strong></p>
          <button onClick={() => navigate("/consular")} className="mt-6 bg-[#E06F2C] text-white px-6 py-2.5 rounded-lg font-semibold hover:bg-[#c45a1a] transition">
            Back to Chat
          </button>
        </div>
      </div>
    );
  }

  if (confirmed) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-orange-50 to-blue-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-xl p-8 max-w-md w-full text-center">
          <CheckCircle className="w-20 h-20 text-green-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-[#1A2E40] mb-2">Application Confirmed!</h2>
          <p className="text-gray-600 mb-4">Your <strong>{data?.service_name}</strong> application has been confirmed.</p>
          <p className="text-sm text-[#E06F2C] font-mono font-semibold">{data?.reference_id}</p>
          <p className="text-sm text-gray-500 mt-3">A confirmation email with your PDF has been sent to your registered email address.</p>
          <button onClick={() => navigate("/consular")} className="mt-6 bg-[#E06F2C] text-white px-6 py-2.5 rounded-lg font-semibold hover:bg-[#c45a1a] transition">
            Back to Chat
          </button>
        </div>
      </div>
    );
  }

  const fields = data?.fields || [];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50 p-4">
      <div className="max-w-2xl mx-auto">
        {/* Header — tenant-neutral. Operators who want brand colours can
            override via Tailwind theme tokens later. */}
        <div className="bg-[#1A2E40] rounded-t-2xl px-6 py-4 text-center">
          <h1 className="text-white font-bold text-lg">Review Your Application</h1>
          {data?.brand && <p className="text-white/80 text-sm mt-0.5">{data.brand}</p>}
        </div>

        <div className="bg-white rounded-b-2xl shadow-xl p-6">
          <div className="flex items-start justify-between mb-4">
            <div>
              <p className="text-xs text-gray-500">Service</p>
              <p className="font-bold text-[#1A2E40]">{data?.service_name}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-gray-500">Reference ID</p>
              <p className="font-mono font-semibold text-[#E06F2C]">{data?.reference_id}</p>
            </div>
          </div>

          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5 mb-5 text-sm text-amber-800">
            <strong>Review Notice:</strong> Please check all fields carefully. You can edit them before confirming.
          </div>

          {/* Editable form */}
          <div className="space-y-4">
            {fields.length > 0 ? fields.map(f => (
              <div key={f.key}>
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1">{f.label}</label>
                <input
                  type="text"
                  value={editedData[f.key] || ""}
                  onChange={e => setEditedData(prev => ({ ...prev, [f.key]: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#E06F2C]"
                />
              </div>
            )) : Object.entries(editedData).map(([k, v]) => (
              <div key={k}>
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide block mb-1">{k.replace(/_/g, " ")}</label>
                <input
                  type="text"
                  value={editedData[k] || ""}
                  onChange={e => setEditedData(prev => ({ ...prev, [k]: e.target.value }))}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#E06F2C]"
                />
              </div>
            ))}
          </div>

          {/* Documents */}
          {(data?.documents || []).length > 0 && (
            <div className="mt-6">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Uploaded Documents</p>
              {data.documents.map((d, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-[#1A2E40] py-1">
                  <FileText className="w-4 h-4 text-[#E06F2C]" />
                  <span>{d.name || d.filename}</span>
                  <span className="ml-auto text-xs text-green-600 font-medium">✓ Uploaded</span>
                </div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 mt-8">
            <button
              onClick={handleSave}
              disabled={saving || confirming}
              className="flex-1 border-2 border-[#1A2E40] text-[#1A2E40] rounded-xl py-3 font-semibold text-sm hover:bg-[#1A2E40] hover:text-white transition disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save Changes"}
            </button>
            <button
              onClick={handleConfirm}
              disabled={saving || confirming}
              className="flex-1 bg-[#E06F2C] text-white rounded-xl py-3 font-semibold text-sm hover:bg-[#c45a1a] transition disabled:opacity-50"
            >
              {confirming ? "Confirming…" : "✅ Confirm & Submit"}
            </button>
          </div>
          <p className="text-xs text-gray-400 text-center mt-3">Confirming will lock this application and send your PDF by email.</p>
        </div>
      </div>
    </div>
  );
}
