"use client";

import React, { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth, UserRole } from "@/components/AuthProvider";
import { 
  Users, 
  Landmark, 
  Lock, 
  Mail, 
  ArrowRight, 
  Flame, 
  KeyRound,
  XCircle,
} from "lucide-react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requiredRole = searchParams.get("role") as UserRole | null;

  const { login, signUp } = useAuth();

  const [mode, setMode] = useState<"login" | "signup">("login");
  const [selectedRole, setSelectedRole] = useState<UserRole>(
    requiredRole || "group_manager"
  );

  // Form Fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [sector, setSector] = useState("delivery");
  const [partnerKey, setPartnerKey] = useState("ICICI-LOMBARD-PARAMETRIC");

  const [authError, setAuthError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const VALID_PARTNER_KEYS = [
    "ICICI-LOMBARD-PARAMETRIC",
    "HDFC-PARTNER-2026",
    "TATA-AIG-CLIMATE",
    "BAJAJ-ALLIANZ-2026"
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setAuthError(null);

    // Validate insurance partner key on signup
    if (mode === "signup" && selectedRole === "insurance_provider") {
      if (!VALID_PARTNER_KEYS.includes(partnerKey.trim())) {
        setAuthError("Invalid Enterprise Partner Key. Please contact your account manager.");
        setLoading(false);
        return;
      }
    }

    try {
      if (mode === "signup") {
        const displayName = fullName || email.split("@")[0];
        const result = await signUp(selectedRole, email, password, displayName, orgName, sector);
        if (result.success) {
          router.push(selectedRole === "group_manager" ? "/admin" : "/insurance");
        }
      } else {
        const result = await login(selectedRole, email, password, email.split("@")[0], orgName);
        if (result.success) {
          router.push(selectedRole === "group_manager" ? "/admin" : "/insurance");
        } else {
          setAuthError(result.message || "Login failed. Please check your credentials.");
        }
      }
    } catch (err: any) {
      console.error("Auth error", err);
      setAuthError(err.message || "Authentication failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  const handleDemoLogin = (role: UserRole) => {
    setLoading(true);
    setTimeout(async () => {
      try {
        if (role === "group_manager") {
          await login("group_manager", "rajesh.kumar@quicklogistics.in", "demo", "Rajesh Kumar");
          router.push("/admin");
        } else {
          await login("insurance_provider", "underwriter@icicilombard.com", "demo", "ICICI Lombard");
          router.push("/insurance");
        }
      } finally {
        setLoading(false);
      }
    }, 300);
  };

  return (
    <div className="bg-white rounded-3xl p-8 sm:p-10 max-w-md w-full shadow-2xl border border-slate-200 space-y-6 relative overflow-hidden">
      <div className="absolute top-0 right-0 w-64 h-64 bg-amber-500/10 rounded-full blur-3xl -mr-16 -mt-16 pointer-events-none" />

      {/* Header */}
      <div className="text-center space-y-2 relative z-10">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-amber-500 to-orange-500 text-white flex items-center justify-center mx-auto shadow-md shadow-orange-500/20">
          <Flame className="w-6 h-6 fill-white/20" />
        </div>
        <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
          {mode === "login" ? "Sign In to Pricing the Heat" : "Register New Account"}
        </h1>
        <p className="text-xs text-slate-500">
          {mode === "login"
            ? "Access your Parametric Micro-Insurance Dashboard & Autopay Console"
            : "Self-register as a Group Manager or enter your Insurer Enterprise Partner Key"}
        </p>
      </div>

      {/* Error Alert */}
      {authError && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-2xl text-xs flex items-start gap-2">
          <XCircle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold">Error: </span>{authError}
          </div>
        </div>
      )}

      {/* Mode Switcher */}
      <div className="flex border-b border-slate-200 text-xs font-bold text-center">
        <button
          type="button"
          onClick={() => { setMode("login"); setAuthError(null); }}
          className={`flex-1 pb-2.5 transition-all ${
            mode === "login"
              ? "text-slate-900 border-b-2 border-slate-900"
              : "text-slate-400 hover:text-slate-600"
          }`}
        >
          SIGN IN
        </button>
        <button
          type="button"
          onClick={() => { setMode("signup"); setAuthError(null); }}
          className={`flex-1 pb-2.5 transition-all ${
            mode === "signup"
              ? "text-slate-900 border-b-2 border-slate-900"
              : "text-slate-400 hover:text-slate-600"
          }`}
        >
          SIGN UP / REGISTER
        </button>
      </div>

      {/* Role Selector */}
      <div className="grid grid-cols-2 p-1.5 bg-slate-100 rounded-2xl border border-slate-200">
        <button
          type="button"
          onClick={() => setSelectedRole("group_manager")}
          className={`flex items-center justify-center gap-2 py-2 rounded-xl font-bold text-xs transition-all ${
            selectedRole === "group_manager"
              ? "bg-amber-500 text-slate-950 shadow-md"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Users className="w-3.5 h-3.5" />
          <span>Group Manager</span>
        </button>

        <button
          type="button"
          onClick={() => setSelectedRole("insurance_provider")}
          className={`flex items-center justify-center gap-2 py-2 rounded-xl font-bold text-xs transition-all ${
            selectedRole === "insurance_provider"
              ? "bg-sky-500 text-white shadow-md"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Landmark className="w-3.5 h-3.5" />
          <span>Insurance Provider</span>
        </button>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-4 text-xs">
        {mode === "signup" && (
          <div>
            <label className="block font-semibold text-slate-700 mb-1">Full Name</label>
            <input
              type="text"
              required
              placeholder="e.g. Vikram Sharma"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>
        )}

        {mode === "signup" && selectedRole === "group_manager" && (
          <>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Organization / Fleet Name</label>
              <input
                type="text"
                required
                placeholder="e.g. Swiggy Bandra Delivery Hub"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
              />
            </div>
            <div>
              <label className="block font-semibold text-slate-700 mb-1">Work Sector</label>
              <select
                value={sector}
                onChange={(e) => setSector(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
              >
                <option value="delivery">QuickCommerce & Food Delivery</option>
                <option value="construction">Construction & Site Works</option>
                <option value="street_vendor">Street Vendors & Artisans</option>
              </select>
            </div>
          </>
        )}

        {mode === "signup" && selectedRole === "insurance_provider" && (
          <div>
            <label className="block font-semibold text-slate-700 mb-1">Enterprise Partner Access Key</label>
            <div className="relative">
              <KeyRound className="w-4 h-4 text-sky-500 absolute left-3.5 top-3" />
              <input
                type="text"
                required
                value={partnerKey}
                onChange={(e) => setPartnerKey(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-10 pr-3.5 py-2.5 font-mono font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>
            <p className="text-[10px] text-slate-400 mt-1">Verified keys: ICICI-LOMBARD-PARAMETRIC, HDFC-PARTNER-2026</p>
          </div>
        )}

        <div>
          <label className="block font-semibold text-slate-700 mb-1">Email Address</label>
          <div className="relative">
            <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
            <input
              type="email"
              required
              placeholder={selectedRole === "group_manager" ? "manager@company.in" : "underwriter@insurer.com"}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-10 pr-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>
        </div>

        <div>
          <label className="block font-semibold text-slate-700 mb-1">Password</label>
          <div className="relative">
            <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
            <input
              type="password"
              required
              minLength={6}
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-10 pr-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>
          {mode === "signup" && (
            <p className="text-[10px] text-slate-400 mt-1">Minimum 6 characters</p>
          )}
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full py-3.5 rounded-2xl bg-slate-900 hover:bg-slate-800 text-white font-bold shadow-lg shadow-slate-900/20 transition-all flex items-center justify-center gap-2 text-xs disabled:opacity-60"
        >
          {loading ? (
            <span>Processing...</span>
          ) : (
            <>
              <span>{mode === "login" ? "SIGN IN TO DASHBOARD" : "CREATE ACCOUNT & ACCESS"}</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>

      {/* Quick Demo Access */}
      <div className="pt-4 border-t border-slate-100 space-y-2">
        <div className="text-[11px] font-semibold text-slate-400 text-center uppercase tracking-wider">
          ⚡ Quick Demo 1-Click Access
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => handleDemoLogin("group_manager")}
            disabled={loading}
            className="px-3 py-2.5 rounded-xl bg-amber-50 text-amber-900 hover:bg-amber-100 border border-amber-200 text-[11px] font-bold transition-all text-left flex items-center gap-2 disabled:opacity-50"
          >
            <Users className="w-4 h-4 text-amber-600 shrink-0" />
            <div>
              <div className="leading-tight">Site Head Demo</div>
              <div className="text-[9px] text-amber-700 font-normal">Manager Console</div>
            </div>
          </button>

          <button
            onClick={() => handleDemoLogin("insurance_provider")}
            disabled={loading}
            className="px-3 py-2.5 rounded-xl bg-sky-50 text-sky-900 hover:bg-sky-100 border border-sky-200 text-[11px] font-bold transition-all text-left flex items-center gap-2 disabled:opacity-50"
          >
            <Landmark className="w-4 h-4 text-sky-600 shrink-0" />
            <div>
              <div className="leading-tight">Insurer Demo</div>
              <div className="text-[9px] text-sky-700 font-normal">Underwriting Desk</div>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-[85vh] flex items-center justify-center p-4">
      <Suspense fallback={
        <div className="flex items-center gap-3 text-slate-500 text-sm font-medium">
          <Flame className="w-5 h-5 text-amber-500 animate-spin" />
          <span>Loading Sign In...</span>
        </div>
      }>
        <LoginForm />
      </Suspense>
    </div>
  );
}
