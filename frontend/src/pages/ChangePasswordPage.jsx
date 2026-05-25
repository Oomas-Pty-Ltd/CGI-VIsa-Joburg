/**
 * Forced first-login password change (Sprint 10).
 *
 * The unified login response carries `password_change_required: true`
 * when a super-admin created the account with a typed-in initial
 * password. The frontend stores the flag in localStorage and redirects
 * here instead of the dashboard. Once the new password is set, the
 * server clears the flag, the frontend mirrors that, and the user
 * lands on their dashboard.
 *
 * Also usable for voluntary password changes (admin profile menu — to
 * be added in a later sprint).
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

export default function ChangePasswordPage() {
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);

  const token        = localStorage.getItem("token");
  const userType     = localStorage.getItem("user_type");
  const forced       = localStorage.getItem("password_change_required") === "true";

  // Guard: must be logged in as an admin
  React.useEffect(() => {
    if (!token || !["super_admin", "local_admin"].includes(userType)) {
      navigate("/login");
    }
  }, [token, userType, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (next.length < 8) {
      toast.error("New password must be at least 8 characters");
      return;
    }
    if (next !== confirm) {
      toast.error("New password and confirmation do not match");
      return;
    }
    if (next === current) {
      toast.error("New password must differ from the current one");
      return;
    }

    setLoading(true);
    try {
      await axios.post(
        `${API}/auth/change-password`,
        { current_password: current, new_password: next },
        { headers: { Authorization: `Bearer ${token}` } },
      );

      // Server cleared the flag — mirror locally so the user lands on the
      // dashboard next time (and doesn't get bounced back here).
      localStorage.removeItem("password_change_required");
      toast.success("Password updated");

      if (userType === "super_admin") navigate("/super-admin/dashboard");
      else if (userType === "local_admin") navigate("/admin/dashboard");
      else navigate("/");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Password change failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center p-6">
      <div className="bg-white rounded-xl shadow-2xl p-8 w-full max-w-md" data-testid="change-password-form">
        <div className="flex justify-center mb-6">
          <Shield className="w-16 h-16 text-[#E06F2C]" />
        </div>
        <h1 className="text-3xl font-bold text-center text-[#1A2E40] mb-2">
          {forced ? "Set your password" : "Change password"}
        </h1>
        <p className="text-center text-gray-600 mb-6 text-sm">
          {forced
            ? "Your account was provisioned with a temporary password. Choose a new one before continuing."
            : "Pick a new password for your account."}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="current">{forced ? "Temporary password" : "Current password"}</Label>
            <Input
              id="current"
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
              autoFocus
              className="mt-1"
              data-testid="current-password-input"
            />
          </div>

          <div>
            <Label htmlFor="next">New password</Label>
            <Input
              id="next"
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
              minLength={8}
              className="mt-1"
              data-testid="new-password-input"
            />
            <p className="text-xs text-gray-400 mt-1">Minimum 8 characters.</p>
          </div>

          <div>
            <Label htmlFor="confirm">Confirm new password</Label>
            <Input
              id="confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              minLength={8}
              className="mt-1"
              data-testid="confirm-password-input"
            />
          </div>

          <Button
            type="submit"
            className="w-full bg-[#E06F2C] hover:bg-[#C55D20] text-white"
            disabled={loading}
            data-testid="change-password-submit"
          >
            {loading ? "Saving…" : "Set password"}
          </Button>
        </form>

        {!forced && (
          <div className="mt-4 text-center">
            <Button
              variant="link"
              onClick={() => navigate(userType === "super_admin" ? "/super-admin/dashboard" : "/admin/dashboard")}
              className="text-[#1A2E40]"
            >
              Cancel
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
