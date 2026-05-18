import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shield } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function SuperAdminLogin() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const response = await axios.post(`${API}/auth/super-admin/login`, {
        email,
        password
      });

      localStorage.setItem("token", response.data.token);
      localStorage.setItem("user_type", response.data.user_type);
      localStorage.setItem("user_id", response.data.user_id);

      toast.success("Login successful!");
      navigate("/super-admin/dashboard");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center p-6">
      <div className="bg-white rounded-xl shadow-2xl p-8 w-full max-w-md" data-testid="super-admin-login-form">
        <div className="flex justify-center mb-6">
          <Shield className="w-16 h-16 text-[#E06F2C]" />
        </div>
        <h1 className="text-3xl font-bold text-center text-[#1A2E40] mb-2">Super Admin</h1>
        <p className="text-center text-gray-600 mb-8">Seva Setu Bot</p>

        <form onSubmit={handleLogin} className="space-y-6">
          <div>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="mt-1"
              data-testid="super-admin-email-input"
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
              data-testid="super-admin-password-input"
            />
          </div>

          <Button
            type="submit"
            className="w-full bg-[#E06F2C] hover:bg-[#C55D20] text-white"
            disabled={loading}
            data-testid="super-admin-login-submit"
          >
            {loading ? "Logging in..." : "Login"}
          </Button>
        </form>

        <div className="mt-6 text-center">
          <Button
            variant="link"
            onClick={() => navigate("/")}
            className="text-[#1A2E40]"
            data-testid="back-to-home-btn"
          >
            Back to Home
          </Button>
        </div>
      </div>
    </div>
  );
}