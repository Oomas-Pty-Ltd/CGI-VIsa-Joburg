import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";

import Landing from "@/pages/Landing";
import SuperAdminLogin from "@/pages/SuperAdminLogin";
import SuperAdminDashboard from "@/pages/SuperAdminDashboard";
import LocalAdminLogin from "@/pages/LocalAdminLogin";
import LocalAdminDashboard from "@/pages/LocalAdminDashboard";
import ConsularBot from "@/pages/ConsularBot";
import FormReview from "@/pages/FormReview";
import ChatWidget from "@/components/ChatWidget";
import AdminDashboardPage from "@/pages/AdminDashboardPage";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/super-admin/login" element={<SuperAdminLogin />} />
          <Route path="/super-admin/dashboard" element={<SuperAdminDashboard />} />
          <Route path="/super-admin/admin-panel" element={<AdminDashboardPage />} />
          <Route path="/admin/login" element={<LocalAdminLogin />} />
          <Route path="/admin/dashboard" element={<LocalAdminDashboard />} />
          <Route path="/consular" element={<ConsularBot />} />
          <Route path="/consular/review" element={<FormReview />} />
          <Route path="/widget" element={<ChatWidget />} />
          <Route path="/widget-demo" element={<WidgetDemo />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" />
    </div>
  );
}

// Demo page showing the widget on a sample website
function WidgetDemo() {
  return (
    <div className="min-h-screen bg-gray-100">
      {/* Sample website content */}
      <header className="bg-white shadow-sm p-4">
        <div className="container mx-auto flex justify-between items-center">
          <h1 className="text-xl font-bold">Your Website</h1>
          <nav className="space-x-4">
            <a href="#" className="text-gray-600 hover:text-gray-900">Home</a>
            <a href="#" className="text-gray-600 hover:text-gray-900">Services</a>
            <a href="#" className="text-gray-600 hover:text-gray-900">Contact</a>
          </nav>
        </div>
      </header>
      
      <main className="container mx-auto py-12 px-4">
        <div className="max-w-3xl mx-auto">
          <h2 className="text-3xl font-bold mb-6">Welcome to Our Website</h2>
          <p className="text-gray-600 mb-4">
            This is a demo page showing how the Seva Setu Bot widget appears on your website.
            The chat widget is in the bottom-right corner.
          </p>
          <p className="text-gray-600 mb-4">
            Click the orange chat button to start a conversation with the bot.
          </p>
          
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mt-8">
            <h3 className="font-semibold text-yellow-800 mb-2">Test the Widget:</h3>
            <ul className="text-sm text-yellow-700 space-y-1">
              <li>• Ask: "What is OCI?"</li>
              <li>• Ask: "How to renew passport?"</li>
              <li>• Ask: "Office timings?"</li>
              <li>• Ask in Hindi: "पासपोर्ट कैसे बनवाएं?"</li>
            </ul>
          </div>
        </div>
      </main>
      
      {/* The Widget */}
      <ChatWidget />
    </div>
  );
}

export default App;