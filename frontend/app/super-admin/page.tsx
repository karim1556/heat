"use client";

import React, { useState, useEffect } from "react";
import { 
  ShieldCheck, 
  KeyRound, 
  Users, 
  Landmark, 
  Plus, 
  Lock, 
  Mail, 
  Sparkles, 
  CheckCircle2, 
  XCircle, 
  TrendingUp, 
  Activity,
  ArrowRight,
  Flame,
  Search,
  RefreshCw
} from "lucide-react";

interface EnterpriseKey {
  id: string;
  partner_name: string;
  key_code: string;
  tier: string;
  status: "active" | "revoked";
  created_at: string;
}

const MASTER_EMAIL = "admin@pricingtheheat.com";
const MASTER_PASSWORD = "SuperAdmin#2026!";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SuperAdminPage() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [emailInput, setEmailInput] = useState("");
  const [passwordInput, setPasswordInput] = useState("");
  const [authError, setAuthError] = useState("");

  const [activeTab, setActiveTab] = useState<"keys" | "roles" | "audit">("keys");

  // Enterprise Partner Keys State
  const [keys, setKeys] = useState<EnterpriseKey[]>([
    { id: "key-01", partner_name: "ICICI Lombard Climate Risk Desk", key_code: "ICICI-LOMBARD-PARAMETRIC", tier: "Tier 1 Enterprise", status: "active", created_at: "2026-07-28" },
    { id: "key-02", partner_name: "HDFC ERGO Micro-Protect Unit", key_code: "HDFC-PARTNER-2026", tier: "Tier 1 Enterprise", status: "active", created_at: "2026-07-28" },
    { id: "key-03", partner_name: "Tata AIG Parametric Underwriting", key_code: "TATA-AIG-CLIMATE", tier: "Enterprise Partner", status: "active", created_at: "2026-07-28" },
    { id: "key-04", partner_name: "Bajaj Allianz Weather Risk", key_code: "BAJAJ-ALLIANZ-2026", tier: "Standard Partner", status: "active", created_at: "2026-07-28" },
  ]);

  const [showAddKeyModal, setShowAddKeyModal] = useState(false);
  const [newPartnerName, setNewPartnerName] = useState("");
  const [newKeyPrefix, setNewKeyPrefix] = useState("");
  const [newTier, setNewTier] = useState("Tier 1 Enterprise");

  const [notification, setNotification] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 4000);
  };

  const handleMasterLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (emailInput === MASTER_EMAIL && passwordInput === MASTER_PASSWORD) {
      setIsAuthenticated(true);
      setAuthError("");
    } else {
      setAuthError("Invalid Master Super Admin credentials.");
    }
  };

  const handleGenerateKey = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPartnerName) return;

    const generatedCode = newKeyPrefix 
      ? `${newKeyPrefix.toUpperCase()}-PARAMETRIC-2026`
      : `${newPartnerName.substring(0, 4).toUpperCase()}-PARAMETRIC-${Math.floor(1000 + Math.random() * 9000)}`;

    const newKeyObj: EnterpriseKey = {
      id: `key-${Date.now()}`,
      partner_name: newPartnerName,
      key_code: generatedCode,
      tier: newTier,
      status: "active",
      created_at: new Date().toISOString().split("T")[0]
    };

    setKeys([newKeyObj, ...keys]);
    setShowAddKeyModal(false);
    setNewPartnerName("");
    setNewKeyPrefix("");
    showToast(`🎉 Generated Enterprise Key: ${generatedCode}`);
  };

  const toggleKeyStatus = (id: string) => {
    setKeys(keys.map((k) => k.id === id ? { ...k, status: k.status === "active" ? "revoked" : "active" } : k));
    showToast("Updated Partner Key status.");
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-[85vh] flex items-center justify-center p-4">
        <div className="bg-slate-900 text-white rounded-3xl p-8 sm:p-10 max-w-md w-full shadow-2xl border border-slate-800 space-y-6 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-red-500/10 rounded-full blur-3xl -mr-16 -mt-16 pointer-events-none" />

          <div className="text-center space-y-2 relative z-10">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-red-600 to-amber-500 text-white flex items-center justify-center mx-auto shadow-md">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <h1 className="text-2xl font-extrabold tracking-tight">Secret Super Admin Console</h1>
            <p className="text-xs text-slate-400">
              Platform Master Key & Enterprise Security Access
            </p>
          </div>

          {authError && (
            <div className="bg-red-500/20 border border-red-500/30 text-red-300 px-4 py-2.5 rounded-xl text-xs font-semibold text-center">
              {authError}
            </div>
          )}

          <form onSubmit={handleMasterLogin} className="space-y-4 text-xs">
            <div>
              <label className="block font-semibold text-slate-300 mb-1">Master Admin Email</label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-500 absolute left-3.5 top-3" />
                <input
                  type="email"
                  required
                  placeholder="admin@pricingtheheat.com"
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                  className="w-full bg-slate-800/80 border border-slate-700 rounded-xl pl-10 pr-3.5 py-2.5 font-medium text-white focus:outline-none focus:ring-2 focus:ring-red-500"
                />
              </div>
            </div>

            <div>
              <label className="block font-semibold text-slate-300 mb-1">Master Password</label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-500 absolute left-3.5 top-3" />
                <input
                  type="password"
                  required
                  placeholder="••••••••••••"
                  value={passwordInput}
                  onChange={(e) => setPasswordInput(e.target.value)}
                  className="w-full bg-slate-800/80 border border-slate-700 rounded-xl pl-10 pr-3.5 py-2.5 font-medium text-white focus:outline-none focus:ring-2 focus:ring-red-500"
                />
              </div>
            </div>

            <button
              type="submit"
              className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-red-600 to-amber-600 hover:from-red-500 hover:to-amber-500 text-white font-bold shadow-lg shadow-red-900/40 active:scale-98 transition-all flex items-center justify-center gap-2 text-xs"
            >
              <span>ACCESS SUPER ADMIN DASHBOARD</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>

          <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-800 text-[11px] text-slate-400 font-mono">
            <div>Default Seeded Master:</div>
            <div className="text-amber-400 font-bold">ID: admin@pricingtheheat.com</div>
            <div className="text-amber-400 font-bold">Pass: SuperAdmin#2026!</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      {notification && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 bg-slate-900 text-white px-5 py-3.5 rounded-2xl shadow-2xl border border-slate-700 animate-slide-up">
          <Sparkles className="w-5 h-5 text-amber-400 animate-pulse" />
          <span className="text-sm font-medium">{notification}</span>
        </div>
      )}

      {/* Header Banner */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 p-6 sm:p-8 text-white shadow-2xl mb-8 border border-slate-800">
        <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-500/20 border border-red-500/30 text-red-300 text-xs font-semibold uppercase tracking-wider mb-3">
              <ShieldCheck className="w-3.5 h-3.5" /> Hidden Master Console
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
              Platform Super Admin Dashboard
            </h1>
            <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-xl">
              Generate enterprise partner keys for insurance tie-ups, audit system security, and manage user role privileges.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowAddKeyModal(true)}
              className="px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold text-xs shadow-md transition-all flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              <span>Generate Enterprise Key</span>
            </button>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex gap-2 mb-6 border-b border-slate-200 pb-2">
        <button
          onClick={() => setActiveTab("keys")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all ${
            activeTab === "keys"
              ? "bg-slate-900 text-white shadow-md"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          <KeyRound className="w-4 h-4 text-amber-400" />
          <span>Enterprise Partner Keys</span>
        </button>

        <button
          onClick={() => setActiveTab("roles")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all ${
            activeTab === "roles"
              ? "bg-slate-900 text-white shadow-md"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          <Users className="w-4 h-4 text-sky-400" />
          <span>User Role Privileges</span>
        </button>
      </div>

      {/* Tab: Enterprise Keys */}
      {activeTab === "keys" && (
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200 shadow-md space-y-6">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Registered Enterprise Keys</h2>
              <p className="text-xs text-slate-500">Keys used by official insurance partners to sign up on the platform</p>
            </div>
            <span className="px-3 py-1 bg-amber-100 text-amber-900 text-xs font-bold rounded-full">
              {keys.filter(k => k.status === "active").length} Active Keys
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 text-slate-400 font-bold uppercase text-[10px]">
                  <th className="py-3 px-4">Insurance Partner Name</th>
                  <th className="py-3 px-4">Key Code</th>
                  <th className="py-3 px-4">Access Tier</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {keys.map((k) => (
                  <tr key={k.id} className="hover:bg-slate-50">
                    <td className="py-3.5 px-4 font-bold text-slate-900 flex items-center gap-2">
                      <Landmark className="w-4 h-4 text-sky-600" />
                      <span>{k.partner_name}</span>
                    </td>
                    <td className="py-3.5 px-4 font-mono font-bold text-amber-700 bg-amber-50/50 rounded-lg">
                      {k.key_code}
                    </td>
                    <td className="py-3.5 px-4 text-slate-600">{k.tier}</td>
                    <td className="py-3.5 px-4">
                      {k.status === "active" ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-bold">
                          <CheckCircle2 className="w-3 h-3" /> ACTIVE
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-red-100 text-red-800 text-[10px] font-bold">
                          <XCircle className="w-3 h-3" /> REVOKED
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <button
                        onClick={() => toggleKeyStatus(k.id)}
                        className={`px-3 py-1.5 rounded-xl font-bold text-[11px] transition-colors ${
                          k.status === "active"
                            ? "bg-red-50 text-red-700 hover:bg-red-100 border border-red-200"
                            : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200"
                        }`}
                      >
                        {k.status === "active" ? "Revoke Key" : "Re-Activate"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: User Role Privileges */}
      {activeTab === "roles" && (
        <div className="bg-white rounded-3xl p-6 sm:p-8 border border-slate-200 shadow-md space-y-4">
          <h2 className="text-lg font-bold text-slate-900">User Role Control Center</h2>
          <p className="text-xs text-slate-500">Platform user directory and assigned RBAC roles</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4">
            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
              <div className="flex justify-between items-center">
                <span className="font-bold text-slate-900 text-xs">Rajesh Kumar</span>
                <span className="px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-900 text-[10px] font-bold uppercase">
                  Group Manager
                </span>
              </div>
              <p className="text-xs text-slate-600">rajesh.kumar@quicklogistics.in • Bandra QuickCommerce Fleet</p>
            </div>

            <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-2">
              <div className="flex justify-between items-center">
                <span className="font-bold text-slate-900 text-xs">ICICI Lombard Desk</span>
                <span className="px-2.5 py-0.5 rounded-full bg-sky-100 text-sky-900 text-[10px] font-bold uppercase">
                  Insurance Provider
                </span>
              </div>
              <p className="text-xs text-slate-600">underwriter@icicilombard.com • ICICI Lombard Climate Unit</p>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: GENERATE ENTERPRISE KEY */}
      {showAddKeyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-md w-full shadow-2xl border border-slate-200 space-y-5 animate-scale-up">
            <h3 className="text-lg font-bold text-slate-900">Generate Enterprise Partner Key</h3>
            <form onSubmit={handleGenerateKey} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Insurance Company / Partner Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. SBI General Climate Cover"
                  value={newPartnerName}
                  onChange={(e) => setNewPartnerName(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Custom Key Prefix (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. SBIGEN"
                  value={newKeyPrefix}
                  onChange={(e) => setNewKeyPrefix(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 font-mono"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddKeyModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-100 text-slate-700 font-bold hover:bg-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold shadow-md"
                >
                  Generate Key
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
