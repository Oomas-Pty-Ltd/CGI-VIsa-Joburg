import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, MessageSquare, Settings as SettingsIcon, TrendingUp, Upload, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LocalAdminDashboard() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState({});
  const [documents, setDocuments] = useState([]);
  const [chatLogs, setChatLogs] = useState([]);
  const [features, setFeatures] = useState({ voice: true, camera: true });
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token || localStorage.getItem("user_type") !== "local_admin") {
      navigate("/admin/login");
      return;
    }
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const token = localStorage.getItem("token");
      const config = { headers: { Authorization: `Bearer ${token}` } };

      const [dashRes, docsRes, logsRes] = await Promise.all([
        axios.get(`${API}/local-admin/dashboard`, config),
        axios.get(`${API}/local-admin/documents`, config),
        axios.get(`${API}/local-admin/chat-logs?limit=50`, config)
      ]);

      setDashboard(dashRes.data);
      setDocuments(docsRes.data);
      setChatLogs(logsRes.data);
      
      if (dashRes.data.company?.features) {
        setFeatures(dashRes.data.company.features);
      }
    } catch (error) {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e) => {
    e.preventDefault();
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("category", "knowledge_base");

    try {
      const token = localStorage.getItem("token");
      await axios.post(`${API}/local-admin/documents/upload`, formData, {
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "multipart/form-data"
        }
      });

      toast.success("Document uploaded successfully!");
      setFile(null);
      fetchData();
    } catch (error) {
      toast.error("Upload failed");
    }
  };

  const handleFeatureToggle = async () => {
    try {
      const token = localStorage.getItem("token");
      await axios.put(`${API}/local-admin/feature-toggles`, features, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Features updated!");
    } catch (error) {
      toast.error("Failed to update features");
    }
  };

  const handleLogout = () => {
    localStorage.clear();
    navigate("/");
  };

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="admin-sidebar fixed left-0 top-0 h-full w-64 text-white p-6">
        <div className="flex items-center gap-3 mb-12">
          <SettingsIcon className="w-8 h-8" />
          <h2 className="text-xl font-bold">Local Admin</h2>
        </div>
        <div className="mb-8">
          <p className="text-sm text-gray-300">Company</p>
          <p className="font-semibold">{dashboard.company?.name}</p>
        </div>
        <Button
          variant="ghost"
          className="w-full justify-start text-white hover:bg-white/10"
          onClick={handleLogout}
          data-testid="logout-btn"
        >
          <LogOut className="w-5 h-5 mr-3" />
          Logout
        </Button>
      </div>

      <div className="ml-64 p-8">
        <h1 className="text-4xl font-bold text-[#1A2E40] mb-8">Dashboard</h1>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <div className="bg-white rounded-xl p-6 shadow-md" data-testid="stat-sessions-today">
            <h3 className="text-gray-600 text-sm mb-2">Sessions Today</h3>
            <p className="text-4xl font-bold text-[#E06F2C]">{dashboard.sessions_today || 0}</p>
          </div>
          <div className="bg-white rounded-xl p-6 shadow-md" data-testid="stat-total-documents">
            <h3 className="text-gray-600 text-sm mb-2">Total Documents</h3>
            <p className="text-4xl font-bold text-[#2E8B57]">{dashboard.total_documents || 0}</p>
          </div>
        </div>

        <Tabs defaultValue="documents" className="space-y-6">
          <TabsList>
            <TabsTrigger value="documents" data-testid="tab-documents">
              <FileText className="w-4 h-4 mr-2" />
              Documents
            </TabsTrigger>
            <TabsTrigger value="chat-logs" data-testid="tab-chat-logs">
              <MessageSquare className="w-4 h-4 mr-2" />
              Chat Logs
            </TabsTrigger>
            <TabsTrigger value="settings" data-testid="tab-settings">
              <SettingsIcon className="w-4 h-4 mr-2" />
              Settings
            </TabsTrigger>
          </TabsList>

          <TabsContent value="documents">
            <div className="bg-white rounded-xl shadow-md p-6">
              <h2 className="text-2xl font-bold text-[#1A2E40] mb-6">Upload Documents</h2>
              <form onSubmit={handleFileUpload} className="space-y-4">
                <div>
                  <Label htmlFor="file">Select File (PDF, DOCX, TXT)</Label>
                  <Input
                    id="file"
                    type="file"
                    onChange={(e) => setFile(e.target.files[0])}
                    accept=".pdf,.docx,.txt"
                    data-testid="file-upload-input"
                  />
                </div>
                <Button
                  type="submit"
                  className="bg-[#E06F2C] hover:bg-[#C55D20]"
                  disabled={!file}
                  data-testid="upload-submit-btn"
                >
                  <Upload className="w-4 h-4 mr-2" />
                  Upload
                </Button>
              </form>

              <div className="mt-8">
                <h3 className="text-lg font-semibold mb-4">Uploaded Documents ({documents.length})</h3>
                <div className="space-y-2">
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="border border-gray-200 rounded-lg p-3 hover:border-[#E06F2C] transition-colors"
                      data-testid={`document-${doc.id}`}
                    >
                      <p className="font-medium text-[#1A2E40]">{doc.filename}</p>
                      <p className="text-sm text-gray-500">{new Date(doc.uploaded_at).toLocaleDateString()}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="chat-logs">
            <div className="bg-white rounded-xl shadow-md p-6">
              <h2 className="text-2xl font-bold text-[#1A2E40] mb-6">Chat Logs (PII Masked)</h2>
              <div className="space-y-3 max-h-[600px] overflow-y-auto">
                {chatLogs.map((log) => (
                  <div
                    key={log.id}
                    className="border border-gray-200 rounded-lg p-4"
                    data-testid={`chat-log-${log.id}`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <span className="text-sm font-medium text-gray-600">User: {log.user_id}</span>
                      <span className="text-xs text-gray-400">{new Date(log.timestamp).toLocaleString()}</span>
                    </div>
                    <p className="text-[#1A2E40]">{log.masked_message}</p>
                  </div>
                ))}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="settings">
            <div className="bg-white rounded-xl shadow-md p-6">
              <h2 className="text-2xl font-bold text-[#1A2E40] mb-6">Feature Toggles</h2>
              <div className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <Label htmlFor="voice" className="text-base">Voice Input</Label>
                    <p className="text-sm text-gray-500">Enable voice recognition for users</p>
                  </div>
                  <Switch
                    id="voice"
                    checked={features.voice}
                    onCheckedChange={(checked) => setFeatures({ ...features, voice: checked })}
                    data-testid="toggle-voice"
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <Label htmlFor="camera" className="text-base">Camera/Document Scanner</Label>
                    <p className="text-sm text-gray-500">Enable camera for document scanning</p>
                  </div>
                  <Switch
                    id="camera"
                    checked={features.camera}
                    onCheckedChange={(checked) => setFeatures({ ...features, camera: checked })}
                    data-testid="toggle-camera"
                  />
                </div>

                <Button
                  onClick={handleFeatureToggle}
                  className="bg-[#E06F2C] hover:bg-[#C55D20]"
                  data-testid="save-features-btn"
                >
                  Save Changes
                </Button>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}