"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import { apiService } from "@/services/api";
import { Shield, Sparkles, ArrowRight, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Alert } from "@/components/ui/Alert";
import Link from "next/link";

export default function AdminRegister() {
  const router = useRouter();
  const { login, isAuthenticated, role, initialize } = useAuthStore();
  
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [securityKey, setSecurityKey] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    initialize();
  }, [initialize]);

  useEffect(() => {
    if (isAuthenticated && (role === "admin" || role === "super_admin")) {
      router.push("/admin");
    }
  }, [isAuthenticated, role, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      // 1. Sign up as admin
      await apiService.signup({
        email,
        password,
        full_name: fullName,
        role: "admin",
        security_key: securityKey
      });
      
      // 2. Log in immediately
      const params = new URLSearchParams();
      params.append("username", email);
      params.append("password", password);
      
      const tokenData = await apiService.login(params);
      login(tokenData.access_token, tokenData.role, tokenData.full_name, tokenData.email);
      
      router.push("/admin");
    } catch (err: any) {
      setError(err.message || "An error occurred during administrative signup.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen h-screen overflow-hidden bg-background text-foreground flex justify-center items-center relative font-sans">
      {/* Decorative Blur Backgrounds */}
      <div className="absolute top-[-10%] right-[-10%] w-1/2 h-1/2 bg-purple-600/10 rounded-full blur-120 pointer-events-none z-0" />
      <div className="absolute bottom-[-10%] left-[-10%] w-1/2 h-1/2 bg-indigo-600/10 rounded-full blur-120 pointer-events-none z-0" />

      {/* Grid Pattern */}
      <div className="absolute inset-0 digital-grid-bg opacity-30 pointer-events-none z-0" />

      {/* Registration Card */}
      <div className="w-full max-w-md bg-app-card border border-app-border backdrop-blur-xl p-8 rounded-2xl relative z-10 shadow-2xl flex flex-col gap-6">
        
        {/* Brand Header */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-lg border border-indigo-400/20">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L2 7L12 12L22 7L12 2Z" fill="white" opacity="0.95"/>
              <path d="M2 17L12 22L22 17" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M2 12L12 17L22 12" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </div>
          <div>
            <div className="flex items-baseline gap-0.5">
              <span className="text-app-text font-extrabold text-lg tracking-tight leading-none">Vidyamarg</span>
              <span className="text-blue-500 font-extrabold text-lg tracking-tight leading-none italic">AI</span>
            </div>
            <span className="block text-[8px] text-indigo-400 font-bold tracking-widest uppercase mt-0.5">Admin Management</span>
          </div>
        </div>

        <div>
          <h2 className="text-xl font-extrabold tracking-tight flex items-center gap-2">
            <span>Register Admin Profile</span>
            <Shield size={16} className="text-purple-400" />
          </h2>
          <p className="text-xs text-slate-400 mt-1 leading-relaxed">
            Create a recruiting admin account. You will need your organization's administrative key to complete setup.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
          {error && (
            <Alert variant="error">
              {error}
            </Alert>
          )}

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Full Name</label>
            <Input
              type="text"
              required
              placeholder="e.g. Sebastian Ramirez"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="bg-app-surface border-app-border text-app-text focus:border-purple-500"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Admin Email</label>
            <Input
              type="email"
              required
              placeholder="admin@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="bg-app-surface border-app-border text-app-text focus:border-purple-500"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Security Password</label>
            <div className="relative">
              <Input
                type={showPassword ? "text" : "password"}
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-app-surface border-app-border text-app-text focus:border-purple-500 pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-app-text-muted hover:text-app-text transition-colors p-1 cursor-pointer"
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Administrative Key</label>
            <Input
              type="password"
              required
              placeholder="Enter the administrator key supplied by your organization"
              value={securityKey}
              onChange={(e) => setSecurityKey(e.target.value)}
              className="bg-app-surface border-app-border text-app-text focus:border-purple-500 font-mono text-center tracking-widest"
            />
          </div>

          <Button
            type="submit"
            loading={loading}
            className="w-full bg-purple-600 hover:bg-purple-700 text-white mt-2"
          >
            <span>Register Admin & Enter Dashboard</span>
            {!loading && <ArrowRight size={16} />}
          </Button>
        </form>

        <div className="text-center border-t border-app-border pt-4 flex flex-col gap-2">
          <Link 
            href="/admin-login" 
            className="text-xs text-purple-400 hover:underline font-bold"
          >
            Already have an Admin profile? Login here
          </Link>
          <Link 
            href="/" 
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            Return to Candidate login
          </Link>
        </div>

      </div>
    </main>
  );
}
