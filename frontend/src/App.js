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

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/super-admin/login" element={<SuperAdminLogin />} />
          <Route path="/super-admin/dashboard" element={<SuperAdminDashboard />} />
          <Route path="/admin/login" element={<LocalAdminLogin />} />
          <Route path="/admin/dashboard" element={<LocalAdminDashboard />} />
          <Route path="/consular" element={<ConsularBot />} />
          <Route path="/consular/review" element={<FormReview />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" />
    </div>
  );
}

export default App;