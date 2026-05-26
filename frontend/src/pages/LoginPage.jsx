/**
 * Unified console login (Sprint 7).
 *
 * Replaces SuperAdminLogin.jsx and LocalAdminLogin.jsx — one form for
 * both roles. Email + password is enough for most sign-ins (emails are
 * globally unique across admin tables); the optional Company ID field
 * is only needed to disambiguate when an email happens to exist as
 * both a super-admin AND a local-admin row (rare).
 *
 * The backend `/api/auth/login` returns `user_type` so the redirect
 * destination is decided server-side, not by which page the user
 * landed on.
 */
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const body = { email, password };
      if (companyId.trim()) body.company_id = companyId.trim();

      const { data } = await axios.post(`${API}/auth/login`, body);

      localStorage.setItem("token", data.token);
      localStorage.setItem("user_type", data.user_type);
      localStorage.setItem("user_id", data.user_id);
      if (data.company_id) {
        localStorage.setItem("company_id", data.company_id);
      } else {
        localStorage.removeItem("company_id");
      }
      if (data.password_change_required) {
        localStorage.setItem("password_change_required", "true");
      } else {
        localStorage.removeItem("password_change_required");
      }

      toast.success("Login successful!");

      // Sprint 10: if the account still has the bootstrap password, force
      // a password change before letting the user reach the dashboard.
      if (data.password_change_required) {
        navigate("/change-password");
        return;
      }

      // Redirect by role — decided server-side, not by the URL the user opened.
      if (data.user_type === "super_admin") {
        navigate("/super-admin/dashboard");
      } else if (data.user_type === "local_admin") {
        navigate("/admin/dashboard");
      } else {
        // Future viewer / other roles fall back to landing for now.
        navigate("/");
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="bg-card border border-border rounded-xl shadow-sm p-8 w-full max-w-md" data-testid="login-form">
        <div className="flex justify-center mb-6">
          <div className="h-12 w-12 rounded-lg bg-primary flex items-center justify-center">
            <Shield className="w-6 h-6 text-primary-foreground" />
          </div>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-center text-foreground mb-1">Sign in</h1>
        <p className="text-center text-sm text-muted-foreground mb-8">{(process.env.REACT_APP_SITE_NAME || 'Admin') + ' console'}</p>

        <form onSubmit={handleLogin} className="space-y-5">
          <div>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              className="mt-1"
              data-testid="login-email-input"
            />
          </div>

          <div>
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="mt-1"
              data-testid="login-password-input"
            />
          </div>

          <div>
            <Label htmlFor="company_id">
              Company ID
              <span className="text-xs text-muted-foreground ml-1">(optional — leave blank if super-admin)</span>
            </Label>
            <Input
              id="company_id"
              type="text"
              value={companyId}
              onChange={(e) => setCompanyId(e.target.value)}
              placeholder="d3b578ed-…"
              className="mt-1 font-mono text-xs"
              data-testid="login-company-id-input"
            />
            <p className="text-xs text-muted-foreground mt-1">
              Local admins can usually leave this blank — only fill it in if your email is shared between multiple tenants.
            </p>
          </div>

          <Button
            type="submit"
            className="w-full"
            disabled={loading}
            data-testid="login-submit"
          >
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <div className="mt-6 text-center">
          <Button
            variant="link"
            onClick={() => navigate("/")}
            className="text-muted-foreground hover:text-foreground"
            data-testid="back-to-home-btn"
          >
            Back to Home
          </Button>
        </div>
      </div>
    </div>
  );
}
