import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { 
  LayoutDashboard, 
  AlertCircle, 
  BookOpen, 
  BarChart3, 
  LogOut,
  RefreshCw,
  Eye,
  CheckCircle,
  Clock,
  AlertTriangle,
  Users,
  MessageSquare,
  DollarSign,
  Shield,
  Plus,
  Edit,
  History,
  Search
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Tab definitions
const TABS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "escalations", label: "Escalations", icon: AlertCircle },
  { id: "knowledge", label: "Knowledge Base", icon: BookOpen },
  { id: "observability", label: "AI Observability", icon: BarChart3 }
];

const PRIORITY_COLORS = {
  urgent: "bg-red-100 text-red-800 border-red-200",
  high: "bg-orange-100 text-orange-800 border-orange-200",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-200",
  low: "bg-green-100 text-green-800 border-green-200"
};

const STATUS_COLORS = {
  open: "bg-blue-100 text-blue-800",
  in_progress: "bg-yellow-100 text-yellow-800",
  resolved: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-800"
};

export default function AdminDashboardPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("dashboard");
  const [loading, setLoading] = useState(true);
  const [dashboardData, setDashboardData] = useState(null);
  const [escalations, setEscalations] = useState([]);
  const [knowledgeEntries, setKnowledgeEntries] = useState([]);
  const [observabilityData, setObservabilityData] = useState(null);
  const [selectedEscalation, setSelectedEscalation] = useState(null);
  const [selectedKnowledge, setSelectedKnowledge] = useState(null);
  const [showAddKnowledge, setShowAddKnowledge] = useState(false);
  const [knowledgeHistory, setKnowledgeHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  const token = localStorage.getItem("token");

  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json"
  };

  useEffect(() => {
    const userType = localStorage.getItem("user_type");
    if (!token || userType !== "super_admin") {
      navigate("/super-admin/login");
      return;
    }
    loadData();
  }, [token, navigate]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [dashboard, escalationsRes, knowledgeRes, observability] = await Promise.all([
        axios.get(`${API}/admin/dashboard`, { headers }),
        axios.get(`${API}/admin/escalations`, { headers }),
        axios.get(`${API}/admin/knowledge`, { headers }),
        axios.get(`${API}/admin/observability`, { headers })
      ]);

      setDashboardData(dashboard.data);
      setEscalations(escalationsRes.data.escalations || []);
      setKnowledgeEntries(knowledgeRes.data.entries || []);
      setObservabilityData(observability.data);
    } catch (error) {
      console.error("Failed to load data:", error);
      if (error.response?.status === 401) {
        localStorage.removeItem("superAdminToken");
        navigate("/super-admin-login");
      } else {
        toast.error("Failed to load dashboard data");
      }
    } finally {
      setLoading(false);
    }
  }, [headers, navigate]);

  const handleLogout = () => {
    localStorage.removeItem("superAdminToken");
    navigate("/super-admin-login");
  };

  const updateEscalation = async (id, updates) => {
    try {
      await axios.put(`${API}/admin/escalations/${id}`, updates, { headers });
      toast.success("Escalation updated");
      loadData();
      setSelectedEscalation(null);
    } catch (error) {
      toast.error("Failed to update escalation");
    }
  };

  const loadKnowledgeHistory = async (entryId) => {
    try {
      const response = await axios.get(`${API}/admin/knowledge/${entryId}/history`, { headers });
      setKnowledgeHistory(response.data.history || []);
      setShowHistory(true);
    } catch (error) {
      toast.error("Failed to load history");
    }
  };

  const createKnowledgeEntry = async (data) => {
    try {
      await axios.post(`${API}/admin/knowledge`, data, { headers });
      toast.success("Knowledge entry created");
      loadData();
      setShowAddKnowledge(false);
    } catch (error) {
      toast.error("Failed to create entry");
    }
  };

  const updateKnowledgeEntry = async (id, updates) => {
    try {
      await axios.put(`${API}/admin/knowledge/${id}`, updates, { headers });
      toast.success("Knowledge entry updated");
      loadData();
      setSelectedKnowledge(null);
    } catch (error) {
      toast.error("Failed to update entry");
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-[#E06F2C] mx-auto" />
          <p className="mt-2 text-gray-600">Loading admin dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 py-3 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <Shield className="w-8 h-8 text-[#E06F2C]" />
            <div>
              <h1 className="text-xl font-bold text-[#1A2E40]">Seva Setu Admin</h1>
              <p className="text-xs text-gray-500">AI Observability & Management</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={loadData}>
              <RefreshCw className="w-4 h-4 mr-1" /> Refresh
            </Button>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              <LogOut className="w-4 h-4 mr-1" /> Logout
            </Button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Tab Navigation */}
        <div className="flex gap-2 mb-6 bg-white p-2 rounded-lg shadow-sm">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors ${
                activeTab === tab.id
                  ? "bg-[#E06F2C] text-white"
                  : "hover:bg-gray-100 text-gray-700"
              }`}
              data-testid={`tab-${tab.id}`}
            >
              <tab.icon className="w-4 h-4" />
              <span className="font-medium">{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === "dashboard" && dashboardData && (
          <DashboardTab data={dashboardData} />
        )}

        {activeTab === "escalations" && (
          <EscalationsTab 
            escalations={escalations} 
            onSelect={setSelectedEscalation}
            onUpdate={updateEscalation}
          />
        )}

        {activeTab === "knowledge" && (
          <KnowledgeTab 
            entries={knowledgeEntries}
            onSelect={setSelectedKnowledge}
            onAdd={() => setShowAddKnowledge(true)}
            onHistory={loadKnowledgeHistory}
          />
        )}

        {activeTab === "observability" && observabilityData && (
          <ObservabilityTab data={observabilityData} />
        )}
      </div>

      {/* Escalation Detail Dialog */}
      <EscalationDialog
        escalation={selectedEscalation}
        onClose={() => setSelectedEscalation(null)}
        onUpdate={updateEscalation}
      />

      {/* Knowledge Entry Dialog */}
      <KnowledgeDialog
        entry={selectedKnowledge}
        onClose={() => setSelectedKnowledge(null)}
        onSave={updateKnowledgeEntry}
      />

      {/* Add Knowledge Dialog */}
      <AddKnowledgeDialog
        open={showAddKnowledge}
        onClose={() => setShowAddKnowledge(false)}
        onSave={createKnowledgeEntry}
      />

      {/* History Dialog */}
      <HistoryDialog
        open={showHistory}
        history={knowledgeHistory}
        onClose={() => setShowHistory(false)}
      />
    </div>
  );
}

// =====================================================================
// DASHBOARD TAB
// =====================================================================
function DashboardTab({ data }) {
  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={MessageSquare}
          label="Total Sessions"
          value={data.overview.total_sessions}
          subtext={`${data.overview.today_sessions} today`}
          color="blue"
        />
        <StatCard
          icon={Users}
          label="Companies"
          value={data.overview.total_companies}
          subtext={`${data.overview.total_users} users`}
          color="green"
        />
        <StatCard
          icon={AlertCircle}
          label="Open Escalations"
          value={data.escalations.open}
          subtext={`${data.escalations.urgent} urgent`}
          color="orange"
        />
        <StatCard
          icon={DollarSign}
          label="Today's Cost"
          value={`$${data.costs.today_usd.toFixed(2)}`}
          subtext={`${data.costs.budget_used_pct}% of budget`}
          color="purple"
        />
      </div>

      {/* Health Status */}
      <div className="bg-white rounded-lg p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-[#1A2E40] mb-4">System Health</h3>
        <div className="flex gap-4">
          <div className={`flex items-center gap-2 px-4 py-2 rounded-full ${
            data.health.status === 'healthy' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
          }`}>
            <CheckCircle className="w-5 h-5" />
            <span className="font-medium capitalize">{data.health.status}</span>
          </div>
          <div className={`flex items-center gap-2 px-4 py-2 rounded-full ${
            data.health.llm_available ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
          }`}>
            <span>LLM: {data.health.llm_available ? 'Connected' : 'Disconnected'}</span>
          </div>
          <div className={`flex items-center gap-2 px-4 py-2 rounded-full ${
            data.health.db_connected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
          }`}>
            <span>DB: {data.health.db_connected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// ESCALATIONS TAB
// =====================================================================
function EscalationsTab({ escalations, onSelect, onUpdate }) {
  const [filter, setFilter] = useState("all");

  const filtered = filter === "all" 
    ? escalations 
    : escalations.filter(e => e.status === filter);

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold text-[#1A2E40]">Escalations</h2>
        <div className="flex gap-2">
          {["all", "open", "in_progress", "resolved"].map(status => (
            <button
              key={status}
              onClick={() => setFilter(status)}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                filter === status
                  ? "bg-[#E06F2C] text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200"
              }`}
            >
              {status === "all" ? "All" : status.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-sm overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Channel</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Priority</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Reason</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                  No escalations found
                </td>
              </tr>
            ) : (
              filtered.map(esc => (
                <tr key={esc.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm font-mono">{esc.id.slice(0, 8)}</td>
                  <td className="px-4 py-3 text-sm capitalize">{esc.channel}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${PRIORITY_COLORS[esc.priority]}`}>
                      {esc.priority}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${STATUS_COLORS[esc.status]}`}>
                      {esc.status.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm">{esc.reason.replace("_", " ")}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">
                    {new Date(esc.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <Button size="sm" variant="ghost" onClick={() => onSelect(esc)}>
                      <Eye className="w-4 h-4" />
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// =====================================================================
// KNOWLEDGE TAB
// =====================================================================
function KnowledgeTab({ entries, onSelect, onAdd, onHistory }) {
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");

  const categories = [...new Set(entries.map(e => e.category))];
  
  const filtered = entries.filter(e => {
    const matchesSearch = search === "" || 
      e.title.toLowerCase().includes(search.toLowerCase()) ||
      e.question.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = categoryFilter === "all" || e.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-bold text-[#1A2E40]">Knowledge Base</h2>
        <Button onClick={onAdd} className="bg-[#E06F2C] hover:bg-[#C55D20]">
          <Plus className="w-4 h-4 mr-1" /> Add Entry
        </Button>
      </div>

      <div className="flex gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search knowledge base..."
            className="pl-10"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-4 py-2 border rounded-md"
        >
          <option value="all">All Categories</option>
          {categories.map(cat => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>
      </div>

      <div className="grid gap-4">
        {filtered.map(entry => (
          <div key={entry.id} className="bg-white rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs font-medium">
                    {entry.category}
                  </span>
                  <span className="text-xs text-gray-500">v{entry.version}</span>
                  {entry.source_verified && (
                    <span className="px-2 py-1 bg-green-100 text-green-800 rounded text-xs">
                      ✓ Verified
                    </span>
                  )}
                </div>
                <h3 className="font-semibold text-[#1A2E40]">{entry.title}</h3>
                <p className="text-sm text-gray-600 mt-1">{entry.question}</p>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => onHistory(entry.id)}>
                  <History className="w-4 h-4" />
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onSelect(entry)}>
                  <Edit className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// =====================================================================
// OBSERVABILITY TAB
// =====================================================================
function ObservabilityTab({ data }) {
  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-[#1A2E40]">AI Observability</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Intent Classification */}
        <div className="bg-white rounded-lg p-6 shadow-sm">
          <h3 className="font-semibold text-[#1A2E40] mb-4">Intent Classification</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-600">Total Classifications</span>
              <span className="font-semibold">{data.intent_classification.total_classifications}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">LLM Fallbacks</span>
              <span className="font-semibold">{data.intent_classification.llm_fallbacks}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Rule-Based Rate</span>
              <span className="font-semibold text-green-600">{data.intent_classification.rule_based_rate}%</span>
            </div>
            <div className="mt-4 p-3 bg-green-50 rounded-lg">
              <p className="text-sm text-green-800">{data.intent_classification.efficiency}</p>
            </div>
          </div>
        </div>

        {/* Cost Tracking */}
        <div className="bg-white rounded-lg p-6 shadow-sm">
          <h3 className="font-semibold text-[#1A2E40] mb-4">Cost Tracking</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-600">Daily Cost</span>
              <span className="font-semibold">${data.cost_tracking.daily_cost.toFixed(2)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Tokens Used</span>
              <span className="font-semibold">{data.cost_tracking.daily_tokens.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Budget Remaining</span>
              <span className="font-semibold">${data.cost_tracking.budget_remaining.toFixed(2)}</span>
            </div>
            <div className="mt-2">
              <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-[#E06F2C] transition-all"
                  style={{ width: `${data.cost_tracking.budget_used_pct}%` }}
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">{data.cost_tracking.budget_used_pct}% of daily budget</p>
            </div>
          </div>
        </div>

        {/* Guardrails */}
        <div className="bg-white rounded-lg p-6 shadow-sm">
          <h3 className="font-semibold text-[#1A2E40] mb-4">Guardrails</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-600">PII Detections</span>
              <span className="font-semibold">{data.guardrails.pii_detections}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Unsafe Outputs Blocked</span>
              <span className="font-semibold">{data.guardrails.unsafe_outputs_blocked}</span>
            </div>
          </div>
        </div>

        {/* Rate Limiting */}
        <div className="bg-white rounded-lg p-6 shadow-sm">
          <h3 className="font-semibold text-[#1A2E40] mb-4">Rate Limiting</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-600">Total Requests</span>
              <span className="font-semibold">{data.rate_limiting.total_requests}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Blocked Requests</span>
              <span className="font-semibold text-red-600">{data.rate_limiting.blocked_requests}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Block Rate</span>
              <span className="font-semibold">{data.rate_limiting.block_rate}%</span>
            </div>
          </div>
        </div>

        {/* Escalations */}
        <div className="bg-white rounded-lg p-6 shadow-sm">
          <h3 className="font-semibold text-[#1A2E40] mb-4">Escalations</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-600">Open</span>
              <span className="font-semibold">{data.escalations.open}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">In Progress</span>
              <span className="font-semibold">{data.escalations.in_progress}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Urgent</span>
              <span className="font-semibold text-red-600">{data.escalations.urgent}</span>
            </div>
          </div>
        </div>

        {/* Knowledge Base */}
        <div className="bg-white rounded-lg p-6 shadow-sm">
          <h3 className="font-semibold text-[#1A2E40] mb-4">Knowledge Base</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-gray-600">Total Entries</span>
              <span className="font-semibold">{data.knowledge_base.total_entries}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Verified</span>
              <span className="font-semibold text-green-600">{data.knowledge_base.verified_entries}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Verification Rate</span>
              <span className="font-semibold">{data.knowledge_base.verification_rate}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// HELPER COMPONENTS
// =====================================================================
function StatCard({ icon: Icon, label, value, subtext, color }) {
  const colorClasses = {
    blue: "bg-blue-50 text-blue-600",
    green: "bg-green-50 text-green-600",
    orange: "bg-orange-50 text-orange-600",
    purple: "bg-purple-50 text-purple-600"
  };

  return (
    <div className="bg-white rounded-lg p-6 shadow-sm">
      <div className="flex items-center gap-4">
        <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
          <Icon className="w-6 h-6" />
        </div>
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className="text-2xl font-bold text-[#1A2E40]">{value}</p>
          <p className="text-xs text-gray-400">{subtext}</p>
        </div>
      </div>
    </div>
  );
}

function EscalationDialog({ escalation, onClose, onUpdate }) {
  const [status, setStatus] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (escalation) {
      setStatus(escalation.status);
      setNotes(escalation.resolution_notes || "");
    }
  }, [escalation]);

  if (!escalation) return null;

  return (
    <Dialog open={!!escalation} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Escalation Details</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-gray-500">ID</p>
              <p className="font-mono">{escalation.id}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Channel</p>
              <p className="capitalize">{escalation.channel}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Priority</p>
              <span className={`px-2 py-1 rounded text-sm ${PRIORITY_COLORS[escalation.priority]}`}>
                {escalation.priority}
              </span>
            </div>
            <div>
              <p className="text-sm text-gray-500">Reason</p>
              <p className="capitalize">{escalation.reason.replace("_", " ")}</p>
            </div>
          </div>

          <div>
            <p className="text-sm text-gray-500 mb-1">Description</p>
            <p className="bg-gray-50 p-3 rounded">{escalation.description}</p>
          </div>

          <div>
            <p className="text-sm text-gray-500 mb-1">Conversation Summary</p>
            <pre className="bg-gray-50 p-3 rounded text-sm whitespace-pre-wrap">
              {escalation.conversation_summary}
            </pre>
          </div>

          <div>
            <label className="text-sm text-gray-500 mb-1 block">Status</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full px-3 py-2 border rounded"
            >
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
              <option value="closed">Closed</option>
            </select>
          </div>

          <div>
            <label className="text-sm text-gray-500 mb-1 block">Resolution Notes</label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add notes about the resolution..."
              rows={3}
            />
          </div>

          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button 
              onClick={() => onUpdate(escalation.id, { esc_status: status, resolution_notes: notes })}
              className="bg-[#E06F2C] hover:bg-[#C55D20]"
            >
              Update
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function KnowledgeDialog({ entry, onClose, onSave }) {
  const [title, setTitle] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [source, setSource] = useState("");
  const [verified, setVerified] = useState(false);

  useEffect(() => {
    if (entry) {
      setTitle(entry.title);
      setQuestion(entry.question);
      setAnswer(entry.answer);
      setSource(entry.source || "");
      setVerified(entry.source_verified || false);
    }
  }, [entry]);

  if (!entry) return null;

  return (
    <Dialog open={!!entry} onOpenChange={() => onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Knowledge Entry</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-500 mb-1 block">Title</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label className="text-sm text-gray-500 mb-1 block">Question (FAQ)</label>
            <Input value={question} onChange={(e) => setQuestion(e.target.value)} />
          </div>
          <div>
            <label className="text-sm text-gray-500 mb-1 block">Answer</label>
            <Textarea 
              value={answer} 
              onChange={(e) => setAnswer(e.target.value)} 
              rows={8}
            />
          </div>
          <div>
            <label className="text-sm text-gray-500 mb-1 block">Source URL</label>
            <Input value={source} onChange={(e) => setSource(e.target.value)} />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={verified}
              onChange={(e) => setVerified(e.target.checked)}
              id="verified"
            />
            <label htmlFor="verified" className="text-sm">Source Verified</label>
          </div>

          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button 
              onClick={() => onSave(entry.id, { title, question, answer, source, source_verified: verified })}
              className="bg-[#E06F2C] hover:bg-[#C55D20]"
            >
              Save Changes
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function AddKnowledgeDialog({ open, onClose, onSave }) {
  const [category, setCategory] = useState("general");
  const [title, setTitle] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [keywords, setKeywords] = useState("");
  const [source, setSource] = useState("");

  const handleSave = () => {
    onSave({
      category,
      title,
      question,
      answer,
      keywords: keywords.split(",").map(k => k.trim()).filter(k => k),
      source
    });
    // Reset form
    setTitle("");
    setQuestion("");
    setAnswer("");
    setKeywords("");
    setSource("");
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add Knowledge Entry</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-500 mb-1 block">Category</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full px-3 py-2 border rounded"
            >
              <option value="passport">Passport</option>
              <option value="visa">Visa</option>
              <option value="oci">OCI</option>
              <option value="consular">Consular</option>
              <option value="fees">Fees</option>
              <option value="emergency">Emergency</option>
              <option value="office">Office</option>
              <option value="general">General</option>
            </select>
          </div>
          <div>
            <label className="text-sm text-gray-500 mb-1 block">Title</label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Entry title" />
          </div>
          <div>
            <label className="text-sm text-gray-500 mb-1 block">Question (FAQ)</label>
            <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="What question does this answer?" />
          </div>
          <div>
            <label className="text-sm text-gray-500 mb-1 block">Answer</label>
            <Textarea 
              value={answer} 
              onChange={(e) => setAnswer(e.target.value)} 
              rows={8}
              placeholder="Full answer (supports Markdown)"
            />
          </div>
          <div>
            <label className="text-sm text-gray-500 mb-1 block">Keywords (comma-separated)</label>
            <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="keyword1, keyword2, keyword3" />
          </div>
          <div>
            <label className="text-sm text-gray-500 mb-1 block">Source URL</label>
            <Input value={source} onChange={(e) => setSource(e.target.value)} placeholder="https://..." />
          </div>

          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button 
              onClick={handleSave}
              className="bg-[#E06F2C] hover:bg-[#C55D20]"
              disabled={!title || !question || !answer}
            >
              Create Entry
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function HistoryDialog({ open, history, onClose }) {
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Version History</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {history.length === 0 ? (
            <p className="text-gray-500 text-center py-4">No history available</p>
          ) : (
            history.map((item, index) => (
              <div key={index} className="border rounded-lg p-4">
                <div className="flex justify-between items-center mb-2">
                  <span className="font-semibold">Version {item.version}</span>
                  <span className="text-sm text-gray-500">
                    {new Date(item.archived_at).toLocaleString()}
                  </span>
                </div>
                <p className="text-sm text-gray-600">{item.data?.title}</p>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
