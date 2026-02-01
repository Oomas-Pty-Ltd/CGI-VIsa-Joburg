import React from "react";
import { Building2, Shield, Globe, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 via-white to-blue-50">
      <nav className="container mx-auto px-6 py-6 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <Shield className="w-8 h-8 text-[#E06F2C]" />
          <h1 className="text-2xl font-bold text-[#1A2E40]">Seva Setu Bot</h1>
        </div>
        <div className="flex gap-4">
          <Button
            variant="outline"
            className="border-[#1A2E40] text-[#1A2E40] hover:bg-[#1A2E40] hover:text-white"
            onClick={() => navigate("/super-admin/login")}
            data-testid="super-admin-login-btn"
          >
            Super Admin
          </Button>
          <Button
            variant="outline"
            className="border-[#1A2E40] text-[#1A2E40] hover:bg-[#1A2E40] hover:text-white"
            onClick={() => navigate("/admin/login")}
            data-testid="local-admin-login-btn"
          >
            Local Admin
          </Button>
        </div>
      </nav>

      <main className="container mx-auto px-6 py-20">
        <div className="max-w-4xl mx-auto text-center space-y-8">
          <h1 className="text-5xl md:text-6xl font-bold text-[#1A2E40] tracking-tight" data-testid="landing-heading">
            Multi-Tenant Consular Automation Platform
          </h1>
          <p className="text-xl text-gray-700 leading-relaxed max-w-2xl mx-auto">
            GDPR & POPIA compliant AI-powered consular services for Indian and South African citizens.
            Secure, multilingual, and built for scale.
          </p>

          <div className="flex gap-4 justify-center pt-8">
            <Button
              className="bg-[#E06F2C] hover:bg-[#C55D20] text-white px-8 py-6 text-lg rounded-md shadow-lg hover:shadow-xl transition-all"
              onClick={() => navigate("/consular")}
              data-testid="start-consular-bot-btn"
            >
              Start Consular Application
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 pt-16">
            <div className="bg-white rounded-xl p-8 shadow-md hover:shadow-lg transition-all" data-testid="feature-card-multi-tenant">
              <Building2 className="w-12 h-12 text-[#E06F2C] mb-4 mx-auto" />
              <h3 className="text-xl font-semibold text-[#1A2E40] mb-2">Multi-Tenant</h3>
              <p className="text-gray-600">Isolated company accounts with dedicated admin portals</p>
            </div>

            <div className="bg-white rounded-xl p-8 shadow-md hover:shadow-lg transition-all" data-testid="feature-card-secure">
              <Shield className="w-12 h-12 text-[#2E8B57] mb-4 mx-auto" />
              <h3 className="text-xl font-semibold text-[#1A2E40] mb-2">Secure & Compliant</h3>
              <p className="text-gray-600">Microsoft Presidio PII masking, GDPR & POPIA ready</p>
            </div>

            <div className="bg-white rounded-xl p-8 shadow-md hover:shadow-lg transition-all" data-testid="feature-card-multilingual">
              <Globe className="w-12 h-12 text-[#E06F2C] mb-4 mx-auto" />
              <h3 className="text-xl font-semibold text-[#1A2E40] mb-2">50+ Languages</h3>
              <p className="text-gray-600">Hindi, Zulu, Afrikaans, and more supported</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}