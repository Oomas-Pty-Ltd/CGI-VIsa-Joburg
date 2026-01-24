import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, Plus, Settings, TrendingUp, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function SuperAdminDashboard() {
  const navigate = useNavigate();
  const [companies, setCompanies] = useState([]);
  const [analytics, setAnalytics] = useState({});
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newCompany, setNewCompany] = useState({
    name: "",
    email: "",
    admin_password: "",
    llm_model: "gpt-5.2"
  });

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (!token) {
      navigate("/super-admin/login");
      return;
    }
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const token = localStorage.getItem("token");
      const config = { headers: { Authorization: `Bearer ${token}` } };

      const [companiesRes, analyticsRes] = await Promise.all([
        axios.get(`${API}/super-admin/companies`, config),
        axios.get(`${API}/super-admin/analytics/overview`, config)
      ]);

      setCompanies(companiesRes.data);
      setAnalytics(analyticsRes.data);
    } catch (error) {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateCompany = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem("token");
      await axios.post(`${API}/super-admin/companies`, newCompany, {
        headers: { Authorization: `Bearer ${token}` }
      });

      toast.success("Company created successfully!");
      setShowCreateDialog(false);
      setNewCompany({ name: "", email: "", admin_password: "", llm_model: "gpt-5.2" });
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to create company");
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
          <Building2 className="w-8 h-8" />
          <h2 className="text-xl font-bold">Super Admin</h2>
        </div>
        <nav className="space-y-4">
          <Button variant="ghost" className="w-full justify-start text-white hover:bg-white/10" data-testid="nav-dashboard">
            <TrendingUp className="w-5 h-5 mr-3" />
            Dashboard
          </Button>
          <Button variant="ghost" className="w-full justify-start text-white hover:bg-white/10" data-testid="nav-settings">
            <Settings className="w-5 h-5 mr-3" />
            Settings
          </Button>
          <Button
            variant="ghost"
            className="w-full justify-start text-white hover:bg-white/10 mt-auto"
            onClick={handleLogout}
            data-testid="logout-btn"
          >
            <LogOut className="w-5 h-5 mr-3" />
            Logout
          </Button>
        </nav>
      </div>

      <div className="ml-64 p-8">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-4xl font-bold text-[#1A2E40]">Dashboard</h1>
          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button className="bg-[#E06F2C] hover:bg-[#C55D20] text-white" data-testid="create-company-btn">
                <Plus className="w-5 h-5 mr-2" />
                Create Company
              </Button>
            </DialogTrigger>
            <DialogContent data-testid="create-company-dialog">
              <DialogHeader>
                <DialogTitle>Create New Company</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreateCompany} className="space-y-4">
                <div>
                  <Label htmlFor="name">Company Name</Label>
                  <Input
                    id="name"
                    value={newCompany.name}
                    onChange={(e) => setNewCompany({ ...newCompany, name: e.target.value })}
                    required
                    data-testid="company-name-input"
                  />
                </div>
                <div>
                  <Label htmlFor="email">Admin Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={newCompany.email}
                    onChange={(e) => setNewCompany({ ...newCompany, email: e.target.value })}
                    required
                    data-testid="company-email-input"
                  />
                </div>
                <div>
                  <Label htmlFor="password">Admin Password</Label>
                  <Input
                    id="password"
                    type="password"
                    value={newCompany.admin_password}
                    onChange={(e) => setNewCompany({ ...newCompany, admin_password: e.target.value })}
                    required
                    data-testid="company-password-input"
                  />
                </div>
                <div>
                  <Label htmlFor="model">LLM Model</Label>
                  <Select
                    value={newCompany.llm_model}
                    onValueChange={(value) => setNewCompany({ ...newCompany, llm_model: value })}
                  >
                    <SelectTrigger data-testid="llm-model-select">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="gpt-5.2">GPT-5.2 (OpenAI)</SelectItem>
                      <SelectItem value="gpt-5.1">GPT-5.1 (OpenAI)</SelectItem>
                      <SelectItem value="claude-sonnet-4-5-20250929">Claude Sonnet 4.5</SelectItem>
                      <SelectItem value="gemini-2.5-pro">Gemini 2.5 Pro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button type="submit" className="w-full bg-[#E06F2C] hover:bg-[#C55D20]" data-testid="submit-create-company">
                  Create Company
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-xl p-6 shadow-md" data-testid="stats-companies">
            <h3 className="text-gray-600 text-sm mb-2">Total Companies</h3>
            <p className="text-4xl font-bold text-[#E06F2C]">{analytics.total_companies || 0}</p>
          </div>
          <div className="bg-white rounded-xl p-6 shadow-md" data-testid="stats-sessions">
            <h3 className="text-gray-600 text-sm mb-2">Total Sessions</h3>
            <p className="text-4xl font-bold text-[#2E8B57]">{analytics.total_sessions || 0}</p>
          </div>
          <div className="bg-white rounded-xl p-6 shadow-md" data-testid="stats-documents">
            <h3 className="text-gray-600 text-sm mb-2">Total Documents</h3>
            <p className="text-4xl font-bold text-[#1A2E40]">{analytics.total_documents || 0}</p>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-md p-6">
          <h2 className="text-2xl font-bold text-[#1A2E40] mb-6">Companies</h2>
          <div className="space-y-4">
            {companies.map((company) => (
              <div
                key={company.id}
                className="border border-gray-200 rounded-lg p-4 hover:border-[#E06F2C] transition-colors"
                data-testid={`company-card-${company.id}`}
              >
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="text-lg font-semibold text-[#1A2E40]">{company.name}</h3>
                    <p className="text-gray-600 text-sm">{company.email}</p>
                  </div>
                  <div className="text-right">
                    <span className="text-sm text-gray-500">Model: {company.llm_model}</span>
                    <div className="mt-1">
                      <span className={`px-3 py-1 rounded-full text-xs ${
                        company.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                      }`}>
                        {company.status}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}