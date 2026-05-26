import React from "react";
import { Building2, Shield, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useNavigate } from "react-router-dom";

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background text-foreground">
      <nav className="container mx-auto px-6 py-5 flex justify-between items-center">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-md bg-primary flex items-center justify-center">
            <Shield className="w-4 h-4 text-primary-foreground" />
          </div>
          <h1 className="text-base font-semibold tracking-tight">
            {process.env.REACT_APP_SITE_NAME || "Bot Console"}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            onClick={() => navigate("/login")}
            data-testid="login-btn"
          >
            Sign in
          </Button>
        </div>
      </nav>

      <main className="container mx-auto px-6 pt-16 pb-20">
        <div className="max-w-3xl mx-auto text-center space-y-6">
          <h1 className="text-4xl md:text-5xl font-semibold tracking-tight" data-testid="landing-heading">
            Multi-tenant service automation
          </h1>
          <p className="text-lg text-muted-foreground leading-relaxed max-w-2xl mx-auto">
            Your AI assistant for service applications. Save time, get instant
            help, and complete applications with ease — 24/7, in the languages
            your operator configures.
          </p>

          <div className="flex gap-3 justify-center pt-4">
            <Button
              size="lg"
              onClick={() => navigate("/consular")}
              data-testid="start-consular-bot-btn"
            >
              Start application
            </Button>
            <Button
              size="lg"
              variant="outline"
              onClick={() => navigate("/login")}
            >
              Sign in
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-20 max-w-5xl mx-auto">
          <FeatureCard
            icon={Building2}
            title="Multi-tenant"
            body="Isolated company accounts with dedicated admin portals."
            testId="feature-card-multi-tenant"
          />
          <FeatureCard
            icon={Shield}
            title="Secure"
            body="Data scoped to each tenant; per-request validation on every endpoint."
            testId="feature-card-secure"
          />
          <FeatureCard
            icon={Globe}
            title="Multilingual"
            body="Speech, text, and PDFs in the languages your tenants configure."
            testId="feature-card-multilingual"
          />
        </div>
      </main>
    </div>
  );
}

function FeatureCard({ icon: Icon, title, body, testId }) {
  return (
    <div
      className="rounded-lg border border-border bg-card p-6 hover:border-foreground/20 transition-colors"
      data-testid={testId}
    >
      <Icon className="w-5 h-5 text-foreground mb-3" />
      <h3 className="text-sm font-semibold mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed">{body}</p>
    </div>
  );
}
