import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { ErrorBoundary, ErrorProvider } from "@/components/ErrorSystem";

import Landing from "@/pages/Landing";
import LoginPage from "@/pages/LoginPage";
import ChangePasswordPage from "@/pages/ChangePasswordPage";
import SuperAdminDashboard from "@/pages/SuperAdminDashboard";
import LocalAdminDashboard from "@/pages/LocalAdminDashboard";
import ConsularBot from "@/pages/ConsularBot";
import ICSWhatsAppBot from "@/pages/ICSWhatsAppBot";
import SevaReview from "@/pages/SevaReview";
import ChatWidget from "@/components/ChatWidget";
import { setupWidget } from "@/lib/widgetConfig";

function App() {
  return (
    <ErrorBoundary>
      <ErrorProvider>
        <div className="App">
          <BrowserRouter>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/change-password" element={<ChangePasswordPage />} />
              <Route path="/super-admin/dashboard" element={<SuperAdminDashboard />} />
              <Route path="/admin/dashboard" element={<LocalAdminDashboard />} />
              <Route path="/consular" element={<ConsularBot />} />
              <Route path="/whatsapp" element={<ICSWhatsAppBot />} />
              <Route path="/review/:token" element={<SevaReview />} />
              <Route path="/widget" element={<ChatWidget />} />
              <Route path="/widget-demo" element={<WidgetDemo />} />
            </Routes>
          </BrowserRouter>
          <Toaster position="top-right" />
        </div>
      </ErrorProvider>
    </ErrorBoundary>
  );
}

// Demo page showing the widget on a sample website.
//
// Embed-snippet-equivalent for in-app preview: the actual widget bundle
// uses `data-company-id` on the <script> tag to scope every API call. Here
// in the React main app there is no script tag, so we read the company_id
// from the URL query string and prime `window.__SEVA_CONFIG__` *before*
// calling `setupWidget()` (which installs the axios+fetch interceptors that
// stamp X-Company-Id). Without this, backend routes fall back to env-var
// COMPANY_ID and the demo always renders the default tenant.
function WidgetDemo() {
  const [tenantId, setTenantId] = useState(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("company_id");
    if (q) {
      window.__SEVA_CONFIG__ = { ...(window.__SEVA_CONFIG__ || {}), companyId: q.trim() };
      setupWidget();
      setTenantId(q.trim());
    }
  }, []);

  if (!tenantId) {
    return (
      <div className="min-h-screen bg-gray-100 flex items-center justify-center p-6">
        <div className="bg-white rounded-xl shadow-md max-w-xl p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-2">Widget demo</h2>
          <p className="text-sm text-gray-600 mb-3">
            This page mounts the chat widget against a tenant of your choice. Append
            <code className="mx-1 px-1 py-0.5 bg-gray-100 rounded text-xs">?company_id=&lt;UUID&gt;</code>
            to the URL and reload to preview that tenant's bot.
          </p>
          <p className="text-xs text-gray-500">
            Example: <code className="font-mono">/widget-demo?company_id=00000000-1111-2222-3333-444444444444</code>
          </p>
        </div>
      </div>
    );
  }

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
            This is a demo page showing how the chat widget appears on your website.
            The chat widget is in the bottom-right corner.
          </p>
          <p className="text-gray-600 mb-4">
            Click the chat button to start a conversation. Previewing tenant
            <code className="ml-1 px-1.5 py-0.5 bg-gray-200 rounded text-xs font-mono">{tenantId}</code>.
          </p>
        </div>
      </main>

      {/* The Widget */}
      <ChatWidget />
    </div>
  );
}

export default App;