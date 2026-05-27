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
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shield, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import axios from "axios";
import { consumeExpiryFlash } from "@/lib/authInterceptor";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Module-level latch so React Strict Mode's double-invoke of the effect
// doesn't consume the flash twice and erase the banner on the second pass.
let expiryFlashConsumed = false;

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [loading, setLoading] = useState(false);
  // Inline banner instead of a toast: a toast fired immediately after a
  // full-page reload races the Sonner Toaster's useEffect subscriber and
  // can be silently dropped (Sonner queues toasts to subscribers at publish
  // time, not retroactively on subscribe). A persistent banner is also
  // better UX for a security-relevant message — the user can read it at
  // their pace instead of catching a fading toast.
  const [sessionExpired, setSessionExpired] = useState(false);
  // 2FA: after a correct password the backend returns otp_required; we show
  // an OTP screen and only get a token once the code is verified.
  const [otpStep, setOtpStep] = useState(false);
  const [otp, setOtp] = useState("");
  const [otpMessage, setOtpMessage] = useState("");

  useEffect(() => {
    if (expiryFlashConsumed) return;
    if (consumeExpiryFlash()) {
      expiryFlashConsumed = true;
      setSessionExpired(true);
      // Also fire the toast as a secondary cue. The Toaster has had time
      // to mount by the time the first form interaction happens, so this
      // is a no-op-or-extra-cue — not the primary feedback channel.
      setTimeout(() => {
        toast.error("Your session expired. Please sign in again.", { duration: 6000 });
      }, 200);
    }
  }, []);

  const errMsg = (error, fallback) => {
    const raw = error.response?.data?.detail;
    if (typeof raw === "string" && raw.trim()) return raw;
    if (Array.isArray(raw) && raw.length) return raw[0]?.msg || fallback;
    return fallback;
  };

  // Finish login once we hold a real token (post-OTP).
  const completeLogin = (data) => {
    localStorage.setItem("token", data.token);
    localStorage.setItem("user_type", data.user_type);
    localStorage.setItem("user_id", data.user_id);
    if (data.company_id) localStorage.setItem("company_id", data.company_id);
    else localStorage.removeItem("company_id");
    if (data.password_change_required) localStorage.setItem("password_change_required", "true");
    else localStorage.removeItem("password_change_required");

    toast.success("Login successful!");

    if (data.password_change_required) { navigate("/change-password"); return; }
    if (data.user_type === "super_admin") navigate("/super-admin/dashboard");
    else if (data.user_type === "local_admin" || data.user_type === "viewer") navigate("/admin/dashboard");
    else navigate("/");
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const body = { email, password };
      if (companyId.trim()) body.company_id = companyId.trim();

      const { data } = await axios.post(`${API}/auth/login`, body);

      if (data.otp_required) {
        // Password OK — move to the OTP verification screen.
        setOtpStep(true);
        setOtp("");
        setOtpMessage(data.message || "Enter the verification code to continue.");
        return;
      }
      // (Shouldn't happen with 2FA on, but handle a direct token just in case.)
      completeLogin(data);
    } catch (error) {
      toast.error(errMsg(error, "Login failed"));
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await axios.post(`${API}/auth/login/verify-otp`, {
        email: email.trim(), otp: otp.trim(),
      });
      completeLogin(data);
    } catch (error) {
      toast.error(errMsg(error, "Verification failed"));
    } finally {
      setLoading(false);
    }
  };

  const backToPassword = () => { setOtpStep(false); setOtp(""); setOtpMessage(""); };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <div className="bg-card border border-border rounded-xl shadow-sm p-8 w-full max-w-md" data-testid="login-form">
        <div className="flex justify-center mb-6">
          <div className="h-12 w-12 rounded-lg bg-primary flex items-center justify-center">
            <Shield className="w-6 h-6 text-primary-foreground" />
          </div>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-center text-foreground mb-1">
          {otpStep ? "Verify it's you" : "Sign in"}
        </h1>
        <p className="text-center text-sm text-muted-foreground mb-6">{(process.env.REACT_APP_SITE_NAME || 'Admin') + ' console'}</p>

        {sessionExpired && !otpStep && (
          <div
            role="alert"
            className="mb-5 flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            data-testid="session-expired-banner"
          >
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>Your session expired. Please sign in again.</span>
          </div>
        )}

        {otpStep ? (
          <form onSubmit={handleVerifyOtp} className="space-y-5" data-testid="login-otp-form">
            <div className="flex items-start gap-2 rounded-md border border-primary/20 bg-primary/5 px-3 py-2 text-sm text-foreground">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-primary" />
              <span>{otpMessage}</span>
            </div>
            <div>
              <Label htmlFor="otp">Verification code</Label>
              <Input
                id="otp"
                inputMode="numeric"
                autoComplete="one-time-code"
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/[^0-9]/g, ""))}
                required
                autoFocus
                maxLength={6}
                placeholder="6-digit code"
                className="mt-1 tracking-[0.4em] text-center text-lg font-mono"
                data-testid="login-otp-input"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading} data-testid="login-otp-submit">
              {loading ? "Verifying…" : "Verify & sign in"}
            </Button>
            <Button type="button" variant="link" onClick={backToPassword} className="w-full text-muted-foreground hover:text-foreground">
              ← Back
            </Button>
          </form>
        ) : (
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
        )}

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
