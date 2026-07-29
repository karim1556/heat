"use client";

import React, { useState, useEffect } from "react";
import { getAuthHeaders, getActiveRole, setActiveRole } from "@/components/RoleSwitcher";
import QrCodeGenerator from "@/components/QrCodeGenerator";
import PaymentModal from "@/components/PaymentModal";
import { 
  Users, 
  ShieldCheck, 
  Zap, 
  Plus, 
  QrCode, 
  CheckCircle2, 
  AlertTriangle, 
  TrendingUp, 
  MapPin, 
  Phone, 
  CreditCard, 
  Flame, 
  Building2, 
  Truck, 
  Store, 
  Sparkles,
  ArrowRight,
  ExternalLink,
  X
} from "lucide-react";

interface Cohort {
  id: string;
  name: string;
  manager_name: string;
  manager_email: string;
  sector: string;
  location_name: string;
  lat: number;
  lon: number;
  created_at: string;
  worker_count?: number;
  active_policy_count?: number;
}

interface Worker {
  id: string;
  cohort_id: string;
  name: string;
  phone: string;
  payment_upi: string;
  payment_method: string;
  status: string;
  registered_at: string;
}

interface PolicyTemplate {
  id: string;
  title: string;
  sector: string;
  temperature_threshold_c: number;
  duration_days: number;
  payout_amount_inr: number;
  premium_monthly_inr: number;
  provider_name: string;
  description: string;
}

interface ActivePolicy {
  id: string;
  cohort_id: string;
  cohort_name?: string;
  policy_template_id: string;
  title: string;
  sector: string;
  temperature_threshold_c: number;
  payout_amount_inr: number;
  provider_name: string;
  covered_workers_count: number;
  status: string;
  start_date: string;
}

interface PayoutEvent {
  id: string;
  active_policy_id: string;
  cohort_id: string;
  cohort_name: string;
  manager_name: string;
  sector: string;
  policy_title: string;
  provider_name: string;
  trigger_temperature_c: number;
  trigger_date: string;
  total_amount_inr: number;
  per_worker_amount_inr: number;
  worker_count: number;
  status: 'pending_approval' | 'disbursed' | 'cancelled';
  approved_at?: string;
  approved_by?: string;
}

import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AdminDashboard() {
  const { user, getAuthHeaders } = useAuth();
  const [activeTab, setActiveTab] = useState<"autopay" | "cohorts" | "marketplace" | "simulator">("autopay");
  const [stats, setStats] = useState({
    total_cohorts: 0,
    total_workers: 0,
    total_active_policies: 0,
    total_disbursed_inr: 0,
    pending_approvals: 0
  });

  const [cohorts, setCohorts] = useState<Cohort[]>([]);
  const [selectedCohortId, setSelectedCohortId] = useState<string>("");
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [policyTemplates, setPolicyTemplates] = useState<PolicyTemplate[]>([]);
  const [activePolicies, setActivePolicies] = useState<ActivePolicy[]>([]);
  const [payoutEvents, setPayoutEvents] = useState<PayoutEvent[]>([]);

  // Modals & UI states
  const [showAddCohortModal, setShowAddCohortModal] = useState(false);
  const [showAddWorkerModal, setShowAddWorkerModal] = useState(false);
  const [showQrModal, setShowQrModal] = useState(false);
  const [qrCohort, setQrCohort] = useState<Cohort | null>(null);
  const [paymentTemplate, setPaymentTemplate] = useState<PolicyTemplate | null>(null);
  const [paymentCohort, setPaymentCohort] = useState<Cohort | null>(null);

  // Form states
  const [newCohort, setNewCohort] = useState({
    name: "",
    manager_name: user?.name || "Rajesh Kumar",
    manager_email: user?.email || "manager@heatshield.org",
    sector: "delivery",
    location_name: "Bandra West, Mumbai",
    lat: 19.0596,
    lon: 72.8295
  });

  const [newWorker, setNewWorker] = useState({
    name: "",
    phone: "",
    payment_upi: ""
  });

  const [simTemp, setSimTemp] = useState<number>(44.5);
  const [simCohortId, setSimCohortId] = useState<string>("");
  const [simMessage, setSimMessage] = useState<string | null>(null);

  const [notification, setNotification] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 4000);
  };

  const fetchData = async () => {
    try {
      const headers = getAuthHeaders();
      const [resStats, resCohorts, resTemplates, resActivePols, resEvents] = await Promise.all([
        fetch(`${API_BASE}/api/parametric/stats`, { headers }).then((r) => r.json()),
        fetch(`${API_BASE}/api/parametric/cohorts`, { headers }).then((r) => r.json()),
        fetch(`${API_BASE}/api/parametric/policy-templates`, { headers }).then((r) => r.json()),
        fetch(`${API_BASE}/api/parametric/active-policies`, { headers }).then((r) => r.json()),
        fetch(`${API_BASE}/api/parametric/payout-events`, { headers }).then((r) => r.json())
      ]);

      setStats(resStats);
      setCohorts(resCohorts);
      setPolicyTemplates(resTemplates);
      setActivePolicies(resActivePols);
      setPayoutEvents(resEvents);

      if (resCohorts.length > 0 && !selectedCohortId) {
        setSelectedCohortId(resCohorts[0].id);
        setSimCohortId(resCohorts[0].id);
      }
    } catch (err) {
      console.error("Failed to load parametric data:", err);
    }
  };

  useEffect(() => {
    fetchData();
  }, [user]);

  useEffect(() => {
    if (selectedCohortId) {
      fetch(`${API_BASE}/api/parametric/cohorts/${selectedCohortId}/workers`, { headers: getAuthHeaders() })
        .then((r) => r.json())
        .then((data) => setWorkers(data))
        .catch((err) => console.error(err));
    }
  }, [selectedCohortId, user]);

  const handleCreateCohort = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        ...newCohort,
        manager_name: newCohort.manager_name || user?.name || "Manager",
        manager_email: user?.email || newCohort.manager_email || "manager@heatshield.org"
      };
      const res = await fetch(`${API_BASE}/api/parametric/cohorts`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        showToast(`Cohort "${payload.name}" created successfully!`);
        setShowAddCohortModal(false);
        setNewCohort({
          name: "",
          manager_name: user?.name || "Rajesh Kumar",
          manager_email: user?.email || "manager@heatshield.org",
          sector: "delivery",
          location_name: "Bandra West, Mumbai",
          lat: 19.0596,
          lon: 72.8295
        });
        fetchData();
      } else {
        const errData = await res.json();
        showToast(`Access Error: ${errData.detail || "Unauthorized"}`);
      }
    } catch (err) {
      showToast("Error creating cohort");
    }
  };

  const handleCreateWorker = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCohortId) return;
    try {
      const res = await fetch(`${API_BASE}/api/parametric/workers`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({
          ...newWorker,
          cohort_id: selectedCohortId
        })
      });
      if (res.ok) {
        showToast(`Worker ${newWorker.name} added to cohort!`);
        setShowAddWorkerModal(false);
        setNewWorker({ name: "", phone: "", payment_upi: "" });
        // refresh workers
        fetch(`${API_BASE}/api/parametric/cohorts/${selectedCohortId}/workers`, { headers: getAuthHeaders() })
          .then((r) => r.json())
          .then((data) => setWorkers(data));
        fetchData();
      }
    } catch (err) {
      showToast("Error adding worker");
    }
  };

  const handleBuyPolicy = (template: PolicyTemplate, cohortId: string) => {
    const foundCohort = cohorts.find((c) => c.id === cohortId);
    if (!foundCohort) {
      showToast("Please select a valid cohort first");
      return;
    }
    setPaymentTemplate(template);
    setPaymentCohort(foundCohort);
  };

  const handleApprovePayout = async (eventId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/parametric/payout-events/${eventId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify({ approved_by: "Rajesh Kumar (Group Manager)" })
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`🎉 DISBURSED ₹${data.total_amount_inr.toLocaleString("en-IN")} across ${data.worker_count} workers instantly via Autopay!`);
        fetchData();
      } else {
        const errData = await res.json();
        showToast(`Access Denied: ${errData.detail || "Manager role required"}`);
      }
    } catch (err) {
      showToast("Error approving payout");
    }
  };

  const handleRunSimulation = async () => {
    if (!simCohortId) return;
    try {
      const res = await fetch(`${API_BASE}/api/parametric/trigger-simulation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cohort_id: simCohortId,
          simulated_temp_c: simTemp
        })
      });
      const data = await res.json();
      if (data.triggered) {
        setSimMessage(`🔥 THRESHOLD BREACHED! ${data.events.length} Payout Event(s) generated for ${simTemp}°C. Switch to One-Tap Autopay tab to approve!`);
        showToast(`Heat event triggered for ${simTemp}°C! Check Autopay Center.`);
        fetchData();
      } else {
        setSimMessage(`ℹ️ ${data.reason || `Temperature of ${simTemp}°C did not breach active policy thresholds.`}`);
      }
    } catch (err) {
      setSimMessage("Error triggering weather simulation");
    }
  };

  const getSectorIcon = (sector: string) => {
    switch (sector) {
      case "delivery":
        return <Truck className="w-4 h-4 text-sky-500" />;
      case "construction":
        return <Building2 className="w-4 h-4 text-amber-500" />;
      case "street_vendor":
        return <Store className="w-4 h-4 text-emerald-500" />;
      default:
        return <Users className="w-4 h-4 text-purple-500" />;
    }
  };

  if (!user || user.role !== "group_manager") {
    return (
      <div className="min-h-[75vh] flex items-center justify-center p-4">
        <div className="bg-white p-8 rounded-3xl max-w-md w-full text-center border border-slate-200 shadow-xl space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-amber-50 text-amber-600 border border-amber-200 flex items-center justify-center mx-auto">
            <Users className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold text-slate-900">Group Manager Authentication Required</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            The Manager Dashboard is restricted to authorized Site Heads, Fleet Managers, and Guild Coordinators. Please sign in to access your cohorts and one-tap autopay controls.
          </p>
          <Link
            href="/login?role=group_manager&redirect=/admin"
            className="inline-flex items-center justify-center gap-2 w-full py-3.5 rounded-2xl bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold text-xs shadow-lg shadow-amber-500/20 transition-all"
          >
            <span>SIGN IN AS GROUP MANAGER</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    );
  }

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      {/* Toast Notification */}
      {notification && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-3 bg-slate-900 text-white px-5 py-3.5 rounded-2xl shadow-2xl border border-slate-700 animate-slide-up">
          <Sparkles className="w-5 h-5 text-amber-400 animate-pulse" />
          <span className="text-sm font-medium">{notification}</span>
        </div>
      )}

      {/* Header Banner */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-slate-800 to-amber-950 p-6 sm:p-8 text-white shadow-2xl mb-8 border border-slate-800">
        <div className="absolute top-0 right-0 w-96 h-96 bg-amber-500/10 rounded-full blur-3xl -mr-20 -mt-20 pointer-events-none" />
        
        <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/20 border border-amber-500/30 text-amber-300 text-xs font-semibold uppercase tracking-wider mb-3">
              <ShieldCheck className="w-3.5 h-3.5" /> Group Manager Dashboard
            </div>
            <h1 className="text-2xl sm:text-4xl font-bold tracking-tight text-white">
              Parametric Heat Micro-Insurance
            </h1>
            <p className="text-slate-300 text-sm mt-1 max-w-2xl">
              Protect field workers, delivery riders, and vendors against heatwave wage losses.
              Automated weather triggers with one-tap instant payout approval.
            </p>
          </div>

          <div className="flex items-center gap-3 bg-white/10 backdrop-blur-md px-4 py-2.5 rounded-2xl border border-white/15">
            <div className="w-9 h-9 rounded-full bg-amber-500/20 flex items-center justify-center font-bold text-amber-300 uppercase">
              {user?.name ? user.name.substring(0, 2) : "MG"}
            </div>
            <div>
              <div className="text-xs font-semibold text-white">{user?.name || "Group Manager"}</div>
              <div className="text-[11px] text-amber-200">{user?.orgName || user?.email || "Site & Fleet Operations Lead"}</div>
            </div>
          </div>
        </div>

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mt-8 pt-6 border-t border-white/10">
          <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
            <div className="text-xs text-slate-400 font-medium">Active Cohorts</div>
            <div className="text-2xl font-bold text-white mt-1">{stats.total_cohorts}</div>
          </div>
          <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
            <div className="text-xs text-slate-400 font-medium">Covered Workers</div>
            <div className="text-2xl font-bold text-emerald-400 mt-1">{stats.total_workers}</div>
          </div>
          <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
            <div className="text-xs text-slate-400 font-medium">Active Policies</div>
            <div className="text-2xl font-bold text-sky-400 mt-1">{stats.total_active_policies}</div>
          </div>
          <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
            <div className="text-xs text-slate-400 font-medium">Pending Approvals</div>
            <div className="text-2xl font-bold text-amber-400 mt-1">{stats.pending_approvals}</div>
          </div>
          <div className="bg-white/5 rounded-2xl p-4 border border-white/10 col-span-2 sm:col-span-1">
            <div className="text-xs text-slate-400 font-medium">Total Disbursed</div>
            <div className="text-2xl font-bold text-amber-300 mt-1">₹{stats.total_disbursed_inr.toLocaleString("en-IN")}</div>
          </div>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex items-center gap-2 border-b border-slate-200 mb-8 overflow-x-auto pb-2">
        <button
          onClick={() => setActiveTab("autopay")}
          className={`flex items-center gap-2 px-5 py-3 rounded-2xl font-semibold text-sm transition-all whitespace-nowrap ${
            activeTab === "autopay"
              ? "bg-amber-500 text-white shadow-lg shadow-amber-500/20"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          <Zap className="w-4 h-4" />
          <span>One-Tap Autopay Center</span>
          {stats.pending_approvals > 0 && (
            <span className="bg-red-500 text-white text-[10px] font-bold px-2 py-0.5 rounded-full animate-bounce">
              {stats.pending_approvals}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab("cohorts")}
          className={`flex items-center gap-2 px-5 py-3 rounded-2xl font-semibold text-sm transition-all whitespace-nowrap ${
            activeTab === "cohorts"
              ? "bg-slate-900 text-white shadow-lg shadow-slate-900/20"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          <Users className="w-4 h-4" />
          <span>Cohorts & Workers ({cohorts.length})</span>
        </button>

        <button
          onClick={() => setActiveTab("marketplace")}
          className={`flex items-center gap-2 px-5 py-3 rounded-2xl font-semibold text-sm transition-all whitespace-nowrap ${
            activeTab === "marketplace"
              ? "bg-slate-900 text-white shadow-lg shadow-slate-900/20"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          <ShieldCheck className="w-4 h-4" />
          <span>Policy Marketplace & Coverage</span>
        </button>

        <button
          onClick={() => setActiveTab("simulator")}
          className={`flex items-center gap-2 px-5 py-3 rounded-2xl font-semibold text-sm transition-all whitespace-nowrap ${
            activeTab === "simulator"
              ? "bg-amber-600 text-white shadow-lg shadow-amber-600/20"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          <Flame className="w-4 h-4" />
          <span>Weather Trigger Simulator</span>
        </button>
      </div>

      {/* TAB 1: ONE-TAP AUTOPAY CENTER */}
      {activeTab === "autopay" && (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-xl font-bold text-slate-900">Autopay Payout Approvals</h2>
              <p className="text-xs text-slate-500">
                When environmental sensors/NASA POWER detect heatwave thresholds, parametric claim triggers arrive here.
              </p>
            </div>
          </div>

          {payoutEvents.length === 0 ? (
            <div className="bg-white rounded-3xl p-12 text-center border border-slate-200">
              <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-3" />
              <h3 className="text-lg font-bold text-slate-800">No Pending Payout Triggers</h3>
              <p className="text-sm text-slate-500 max-w-md mx-auto mt-1">
                All worker accounts are clear. You can test a simulated heatwave trigger from the Weather Trigger Simulator tab!
              </p>
            </div>
          ) : (
            <div className="grid gap-4">
              {payoutEvents.map((evt) => (
                <div
                  key={evt.id}
                  className={`bg-white rounded-3xl p-6 border shadow-sm transition-all ${
                    evt.status === "pending_approval"
                      ? "border-amber-400/80 bg-gradient-to-r from-amber-50/50 via-white to-white ring-2 ring-amber-400/20"
                      : "border-slate-200 opacity-80"
                  }`}
                >
                  <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
                    <div className="space-y-2">
                      <div className="flex items-center gap-3">
                        <span
                          className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                            evt.status === "pending_approval"
                              ? "bg-amber-500 text-white animate-pulse"
                              : "bg-emerald-100 text-emerald-800"
                          }`}
                        >
                          {evt.status === "pending_approval" ? "🚨 ACTION REQUIRED: Payout Triggered" : "✅ DISBURSED VIA AUTOPAY"}
                        </span>
                        <span className="text-xs text-slate-400 font-mono">{evt.id}</span>
                      </div>

                      <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                        {evt.cohort_name}
                        <span className="text-xs font-normal text-slate-500">({evt.policy_title})</span>
                      </h3>

                      <div className="flex flex-wrap items-center gap-4 text-xs text-slate-600">
                        <span className="flex items-center gap-1 font-semibold text-red-600">
                          <Flame className="w-4 h-4 fill-red-500 text-red-500" />
                          Recorded Temp: {evt.trigger_temperature_c}°C
                        </span>
                        <span>•</span>
                        <span>Covered Workers: <strong>{evt.worker_count}</strong></span>
                        <span>•</span>
                        <span>Per Worker: <strong>₹{evt.per_worker_amount_inr}</strong></span>
                        <span>•</span>
                        <span>Insurer: <strong>{evt.provider_name}</strong></span>
                      </div>
                    </div>

                    <div className="flex items-center gap-4 w-full lg:w-auto pt-4 lg:pt-0 border-t lg:border-0 border-slate-100">
                      <div className="text-right">
                        <div className="text-xs text-slate-400 uppercase font-semibold">Total Payout Pool</div>
                        <div className="text-2xl font-extrabold text-slate-900">
                          ₹{evt.total_amount_inr.toLocaleString("en-IN")}
                        </div>
                      </div>

                      {evt.status === "pending_approval" ? (
                        <button
                          onClick={() => handleApprovePayout(evt.id)}
                          className="flex-1 lg:flex-none flex items-center justify-center gap-2 px-6 py-4 rounded-2xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white font-bold shadow-lg shadow-orange-500/25 active:scale-95 transition-all text-sm"
                        >
                          <Zap className="w-5 h-5 fill-white" />
                          <span>ONE-TAP APPROVE & DISBURSE</span>
                        </button>
                      ) : (
                        <div className="px-4 py-2 rounded-xl bg-emerald-50 text-emerald-700 text-xs font-semibold flex items-center gap-2 border border-emerald-200">
                          <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                          Disbursed to {evt.worker_count} UPI accounts on {new Date(evt.approved_at || Date.now()).toLocaleTimeString()}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: COHORTS & WORKERS */}
      {activeTab === "cohorts" && (
        <div className="grid lg:grid-cols-3 gap-8">
          {/* Left Column: Cohorts List */}
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-bold text-slate-900">Registered Cohorts</h2>
              <button
                onClick={() => setShowAddCohortModal(true)}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 transition-colors shadow-xs"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>New Cohort</span>
              </button>
            </div>

            <div className="space-y-3">
              {cohorts.map((c) => (
                <div
                  key={c.id}
                  onClick={() => setSelectedCohortId(c.id)}
                  className={`p-4 rounded-2xl border transition-all cursor-pointer ${
                    selectedCohortId === c.id
                      ? "bg-slate-900 text-white border-slate-900 shadow-md"
                      : "bg-white text-slate-900 border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex items-center gap-2 font-bold text-sm">
                      {getSectorIcon(c.sector)}
                      <span>{c.name}</span>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setQrCohort(c);
                        setShowQrModal(true);
                      }}
                      className={`p-1.5 rounded-lg transition-colors ${
                        selectedCohortId === c.id ? "bg-white/10 text-white hover:bg-white/20" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      }`}
                      title="View Worker Self-Onboarding QR Code"
                    >
                      <QrCode className="w-4 h-4" />
                    </button>
                  </div>

                  <div className={`text-xs mt-2 space-y-1 ${selectedCohortId === c.id ? "text-slate-300" : "text-slate-500"}`}>
                    <div className="flex items-center gap-1">
                      <MapPin className="w-3 h-3" />
                      <span>{c.location_name}</span>
                    </div>
                    <div className="flex justify-between items-center pt-2 font-medium border-t border-current/10">
                      <span>Workers: <strong>{c.worker_count || 0}</strong></span>
                      <span className="capitalize px-2 py-0.5 rounded-md bg-white/10 text-[10px] uppercase font-bold tracking-wider">
                        {c.sector.replace("_", " ")}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right Column: Workers in Selected Cohort */}
          <div className="lg:col-span-2 space-y-4">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Workers List {selectedCohortId && `(${workers.length})`}
                </h2>
                <p className="text-xs text-slate-500">
                  Workers enrolled in this cohort automatically receive parametric heat payouts via UPI/Bank transfer.
                </p>
              </div>

              <div className="flex items-center gap-2">
                {selectedCohortId && (
                  <button
                    onClick={() => {
                      const current = cohorts.find(c => c.id === selectedCohortId);
                      if (current) {
                        setQrCohort(current);
                        setShowQrModal(true);
                      }
                    }}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-amber-50 text-amber-800 border border-amber-200 text-xs font-semibold hover:bg-amber-100 transition-colors"
                  >
                    <QrCode className="w-3.5 h-3.5" />
                    <span>Get QR Code</span>
                  </button>
                )}

                <button
                  onClick={() => setShowAddWorkerModal(true)}
                  disabled={!selectedCohortId}
                  className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold hover:bg-slate-800 disabled:opacity-50 transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Worker</span>
                </button>
              </div>
            </div>

            {workers.length === 0 ? (
              <div className="bg-white rounded-3xl p-8 text-center border border-slate-200">
                <Users className="w-10 h-10 text-slate-300 mx-auto mb-2" />
                <h3 className="text-sm font-bold text-slate-700">No Workers Registered Yet</h3>
                <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                  Click "Add Worker" or share the QR code link so workers can self-register from their phones.
                </p>
              </div>
            ) : (
              <div className="bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-xs">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                      <tr>
                        <th className="p-3.5 pl-5">Worker Name</th>
                        <th className="p-3.5">Phone Number</th>
                        <th className="p-3.5">UPI / Routing</th>
                        <th className="p-3.5">Status</th>
                        <th className="p-3.5 pr-5 text-right">Enrolled Date</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-medium text-slate-800">
                      {workers.map((w) => (
                        <tr key={w.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="p-3.5 pl-5 font-bold text-slate-900 flex items-center gap-2">
                            <div className="w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center font-bold text-slate-600 text-[10px]">
                              {w.name.charAt(0)}
                            </div>
                            {w.name}
                          </td>
                          <td className="p-3.5 text-slate-600 font-mono">
                            <span className="flex items-center gap-1">
                              <Phone className="w-3 h-3 text-slate-400" />
                              {w.phone}
                            </span>
                          </td>
                          <td className="p-3.5 text-slate-600 font-mono">
                            <span className="flex items-center gap-1">
                              <CreditCard className="w-3 h-3 text-amber-500" />
                              {w.payment_upi}
                            </span>
                          </td>
                          <td className="p-3.5">
                            <span className="px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-bold uppercase tracking-wider">
                              {w.status}
                            </span>
                          </td>
                          <td className="p-3.5 pr-5 text-right text-slate-400 text-[11px]">
                            {new Date(w.registered_at).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: POLICY MARKETPLACE & COVERAGE */}
      {activeTab === "marketplace" && (
        <div className="space-y-8">
          <div>
            <h2 className="text-xl font-bold text-slate-900">Parametric Policy Packages</h2>
            <p className="text-xs text-slate-500">
              Browse available heatwave policies created by verified Insurance Providers. Purchase coverage for your workers.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            {policyTemplates.map((tmpl) => (
              <div key={tmpl.id} className="bg-white rounded-3xl p-6 border border-slate-200 shadow-sm flex flex-col justify-between hover:border-amber-300 hover:shadow-md transition-all">
                <div className="space-y-3">
                  <div className="flex justify-between items-start">
                    <span className="px-2.5 py-1 rounded-lg bg-amber-50 text-amber-800 text-[10px] font-bold uppercase tracking-wider border border-amber-200">
                      {tmpl.provider_name}
                    </span>
                    <span className="text-xs font-semibold text-slate-500 flex items-center gap-1">
                      <Flame className="w-3.5 h-3.5 text-orange-500" />
                      &ge; {tmpl.temperature_threshold_c}°C
                    </span>
                  </div>

                  <h3 className="text-base font-bold text-slate-900">{tmpl.title}</h3>
                  <p className="text-xs text-slate-600 leading-relaxed">{tmpl.description}</p>

                  <div className="bg-slate-50 rounded-2xl p-3 border border-slate-100 text-xs space-y-1.5">
                    <div className="flex justify-between text-slate-600">
                      <span>Worker Payout:</span>
                      <strong className="text-slate-900">₹{tmpl.payout_amount_inr} / event</strong>
                    </div>
                    <div className="flex justify-between text-slate-600">
                      <span>Monthly Premium:</span>
                      <strong className="text-amber-700">₹{tmpl.premium_monthly_inr} / worker</strong>
                    </div>
                    <div className="flex justify-between text-slate-600">
                      <span>Trigger Rule:</span>
                      <strong className="text-slate-900">{tmpl.duration_days} consecutive days</strong>
                    </div>
                  </div>
                </div>

                <div className="pt-4 mt-4 border-t border-slate-100 space-y-2">
                  <label className="text-[11px] font-semibold text-slate-500">Select Cohort to Cover:</label>
                  {cohorts.length > 0 ? (
                    <div className="flex gap-2">
                      <select
                        id={`cohort-select-${tmpl.id}`}
                        className="flex-1 text-xs bg-slate-100 border border-slate-200 rounded-xl px-3 py-2 font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-amber-500"
                      >
                        {cohorts.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name} ({c.worker_count || 0} workers)
                          </option>
                        ))}
                      </select>

                      <button
                        onClick={() => {
                          const el = document.getElementById(`cohort-select-${tmpl.id}`) as HTMLSelectElement;
                          if (el && el.value) {
                            handleBuyPolicy(tmpl, el.value);
                          }
                        }}
                        className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition-colors shadow-xs"
                      >
                        Buy
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <select
                        disabled
                        className="w-full text-xs bg-slate-50 border border-slate-200 text-slate-400 rounded-xl px-3 py-2 font-medium cursor-not-allowed"
                      >
                        <option>-- No Cohorts Available --</option>
                      </select>
                      <button
                        onClick={() => {
                          setNewCohort({
                            name: `${user?.name || "Manager"}'s Delivery Fleet #1`,
                            manager_name: user?.name || "Site Lead",
                            manager_email: user?.email || "manager@quicklogistics.in",
                            sector: tmpl.sector || "delivery",
                            location_name: "Bandra West, Mumbai",
                            lat: 19.0596,
                            lon: 72.8295
                          });
                          setShowAddCohortModal(true);
                        }}
                        className="w-full py-2 px-3 rounded-xl bg-amber-50 text-amber-900 hover:bg-amber-100 border border-amber-200 text-xs font-bold transition-colors flex items-center justify-center gap-1.5"
                      >
                        <Plus className="w-3.5 h-3.5 text-amber-600" />
                        <span>+ Create Cohort to Buy</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Active Policies Table */}
          <div className="space-y-4 pt-4">
            <h3 className="text-base font-bold text-slate-900">Active Coverage Contracts</h3>
            <div className="bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-xs">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="p-3.5 pl-5">Cohort</th>
                    <th className="p-3.5">Policy Title</th>
                    <th className="p-3.5">Insurer</th>
                    <th className="p-3.5">Trigger Temp</th>
                    <th className="p-3.5">Covered Workers</th>
                    <th className="p-3.5 pr-5 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium text-slate-800">
                  {activePolicies.map((ap) => (
                    <tr key={ap.id}>
                      <td className="p-3.5 pl-5 font-bold text-slate-900">{ap.cohort_name}</td>
                      <td className="p-3.5 text-slate-700">{ap.title}</td>
                      <td className="p-3.5 text-slate-500">{ap.provider_name}</td>
                      <td className="p-3.5 font-bold text-amber-600">&ge; {ap.temperature_threshold_c}°C</td>
                      <td className="p-3.5">{ap.covered_workers_count} workers</td>
                      <td className="p-3.5 pr-5 text-right">
                        <span className="px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-bold uppercase tracking-wider">
                          {ap.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: WEATHER TRIGGER SIMULATOR */}
      {activeTab === "simulator" && (
        <div className="max-w-2xl mx-auto bg-white rounded-3xl p-8 border border-slate-200 shadow-sm space-y-6">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-2xl bg-amber-50 text-amber-600 border border-amber-200">
              <Flame className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900">Simulate Extreme Heatwave Event</h2>
              <p className="text-xs text-slate-500">
                Test the backend Parametric Engine by simulating a live temperature spike for a cohort.
              </p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">Select Target Cohort:</label>
              {cohorts.length > 0 ? (
                <select
                  value={simCohortId}
                  onChange={(e) => setSimCohortId(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-2xl px-4 py-3 text-sm font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                >
                  {cohorts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} — {c.location_name} ({c.sector})
                    </option>
                  ))}
                </select>
              ) : (
                <div className="p-3 bg-amber-50 border border-amber-200 rounded-2xl text-xs text-amber-900 flex items-center justify-between gap-3">
                  <span>No cohorts available to simulate. Create one first!</span>
                  <button
                    onClick={() => {
                      setNewCohort({
                        name: `${user?.name || "Manager"}'s Fleet`,
                        manager_name: user?.name || "Site Lead",
                        manager_email: user?.email || "manager@quicklogistics.in",
                        sector: "delivery",
                        location_name: "Bandra West, Mumbai",
                        lat: 19.0596,
                        lon: 72.8295
                      });
                      setShowAddCohortModal(true);
                    }}
                    className="px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold rounded-xl text-xs shrink-0 shadow-xs"
                  >
                    + Create Cohort
                  </button>
                </div>
              )}
            </div>

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="text-xs font-semibold text-slate-700">Simulated Heat Index (°C):</label>
                <span className="text-base font-extrabold text-amber-600 font-mono">{simTemp}°C</span>
              </div>
              <input
                type="range"
                min="38"
                max="50"
                step="0.5"
                value={simTemp}
                onChange={(e) => setSimTemp(parseFloat(e.target.value))}
                className="w-full accent-amber-500 cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-slate-400 font-mono mt-1">
                <span>38°C (Normal)</span>
                <span>43°C (Threshold)</span>
                <span>50°C (Extreme)</span>
              </div>
            </div>

            <button
              onClick={handleRunSimulation}
              className="w-full py-4 rounded-2xl bg-gradient-to-r from-amber-500 via-orange-500 to-red-500 hover:from-amber-600 hover:to-red-600 text-white font-bold shadow-lg shadow-orange-500/20 active:scale-98 transition-all flex items-center justify-center gap-2 text-sm"
            >
              <Zap className="w-5 h-5 fill-white" />
              <span>TRIGGER WEATHER ORACLE & RUN PARAMETRIC CHECK</span>
            </button>

            {simMessage && (
              <div className="p-4 rounded-2xl bg-slate-900 text-amber-300 text-xs font-mono leading-relaxed border border-slate-800">
                {simMessage}
              </div>
            )}
          </div>
        </div>
      )}

      {/* MODAL: ADD NEW COHORT */}
      {showAddCohortModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-md w-full shadow-2xl border border-slate-200 animate-scale-up space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-bold text-slate-900">Create New Worker Cohort</h3>
              <button
                type="button"
                onClick={() => {
                  setNewCohort({
                    name: `${user?.name || "Bandra"} Delivery Fleet #1`,
                    manager_name: user?.name || "Fleet Manager",
                    manager_email: user?.email || "manager@quicklogistics.in",
                    sector: "delivery",
                    location_name: "Bandra West, Mumbai",
                    lat: 19.0596,
                    lon: 72.8295
                  });
                }}
                className="text-[10px] bg-amber-50 text-amber-900 hover:bg-amber-100 border border-amber-200 px-2.5 py-1 rounded-lg font-bold"
              >
                ⚡ Auto-Fill Sample
              </button>
            </div>
            
            <form onSubmit={handleCreateCohort} className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Cohort Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. South Delhi Delivery Riders Hub #4"
                  value={newCohort.name}
                  onChange={(e) => setNewCohort({ ...newCohort, name: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Sector</label>
                <select
                  value={newCohort.sector}
                  onChange={(e) => setNewCohort({ ...newCohort, sector: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                >
                  <option value="delivery">Delivery Riders / Gig Economy</option>
                  <option value="construction">Construction & Infrastructure Labor</option>
                  <option value="street_vendor">Street Vendors & Local Artisans</option>
                </select>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Location Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Connaught Place, New Delhi"
                  value={newCohort.location_name}
                  onChange={(e) => setNewCohort({ ...newCohort, location_name: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Manager Name</label>
                  <input
                    type="text"
                    required
                    value={newCohort.manager_name}
                    onChange={(e) => setNewCohort({ ...newCohort, manager_name: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Manager Email</label>
                  <input
                    type="email"
                    required
                    value={newCohort.manager_email}
                    onChange={(e) => setNewCohort({ ...newCohort, manager_email: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowAddCohortModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-100 text-slate-600 font-semibold hover:bg-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-slate-900 text-white font-bold hover:bg-slate-800 shadow-xs"
                >
                  Save Cohort
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: ADD WORKER */}
      {showAddWorkerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-md w-full shadow-2xl border border-slate-200 animate-scale-up space-y-4">
            <h3 className="text-lg font-bold text-slate-900">Add Worker to Cohort</h3>
            
            <form onSubmit={handleCreateWorker} className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Worker Full Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Manoj Sharma"
                  value={newWorker.name}
                  onChange={(e) => setNewWorker({ ...newWorker, name: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Mobile Phone Number</label>
                <input
                  type="tel"
                  required
                  placeholder="+91 98765 43210"
                  value={newWorker.phone}
                  onChange={(e) => setNewWorker({ ...newWorker, phone: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 font-mono"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">UPI ID for Autopay Transfers</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. manoj@okicici"
                  value={newWorker.payment_upi}
                  onChange={(e) => setNewWorker({ ...newWorker, payment_upi: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 font-mono"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowAddWorkerModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-100 text-slate-600 font-semibold hover:bg-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-slate-900 text-white font-bold hover:bg-slate-800 shadow-xs"
                >
                  Enroll Worker
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: QR CODE FOR SELF-ONBOARDING */}
      {showQrModal && qrCohort && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-sm w-full shadow-2xl border border-slate-200 text-center animate-scale-up space-y-4">
            <div className="w-12 h-12 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center mx-auto border border-amber-200">
              <QrCode className="w-6 h-6" />
            </div>

            <div>
              <h3 className="text-lg font-bold text-slate-900">{qrCohort.name}</h3>
              <p className="text-xs text-slate-500 mt-0.5">Worker Self-Onboarding Link</p>
            </div>

            {/* Real Scannable SVG QR Code Generator */}
            <div className="flex justify-center my-2">
              <QrCodeGenerator 
                value={typeof window !== "undefined" ? `${window.location.origin}/join/${qrCohort.id}` : `https://pricingtheheat.app/join/${qrCohort.id}`} 
                size={180} 
              />
            </div>

            <div className="text-xs text-slate-600 bg-amber-50/80 p-3 rounded-xl border border-amber-200/60 font-mono break-all text-left">
              <span className="text-[10px] uppercase font-bold text-amber-800 block">Direct URL:</span>
              <a 
                href={`/join/${qrCohort.id}`} 
                target="_blank" 
                rel="noreferrer"
                className="text-amber-900 underline flex items-center gap-1 font-sans font-bold text-xs mt-1 hover:text-orange-600"
              >
                <span>/join/{qrCohort.id}</span>
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>

            <button
              onClick={() => setShowQrModal(false)}
              className="w-full py-2.5 rounded-xl bg-slate-900 text-white font-bold text-xs hover:bg-slate-800 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* MODAL: PAYMENT GATEWAY CHECKOUT FOR POLICY PURCHASING */}
      {paymentTemplate && paymentCohort && (
        <PaymentModal
          template={paymentTemplate}
          cohort={paymentCohort}
          onClose={() => {
            setPaymentTemplate(null);
            setPaymentCohort(null);
          }}
          onSuccess={(activePolicy) => {
            setPaymentTemplate(null);
            setPaymentCohort(null);
            showToast(`🎉 Payment Confirmed! Parametric Policy activated for ${paymentCohort.name}.`);
            fetchData();
          }}
        />
      )}
    </main>
  );
}
