"use client";

import React, { useState, useEffect } from "react";
import { getAuthHeaders, getActiveRole, setActiveRole } from "@/components/RoleSwitcher";
import { 
  Landmark, 
  ShieldAlert, 
  Flame, 
  Plus, 
  CheckCircle2, 
  TrendingUp, 
  Building2, 
  Truck, 
  Store, 
  FileText, 
  Sparkles,
  DollarSign
} from "lucide-react";

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
  cohort_name: string;
  manager_name: string;
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
  cohort_name: string;
  policy_title: string;
  provider_name: string;
  trigger_temperature_c: number;
  trigger_date: string;
  total_amount_inr: number;
  per_worker_amount_inr: number;
  worker_count: number;
  status: string;
  approved_at?: string;
  approved_by?: string;
}

import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import { ArrowRight } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function InsuranceDashboard() {
  const { user, getAuthHeaders } = useAuth();
  const [stats, setStats] = useState({
    total_cohorts: 0,
    total_workers: 0,
    total_active_policies: 0,
    total_disbursed_inr: 0,
    pending_approvals: 0
  });

  const [policyTemplates, setPolicyTemplates] = useState<PolicyTemplate[]>([]);
  const [activePolicies, setActivePolicies] = useState<ActivePolicy[]>([]);
  const [payoutEvents, setPayoutEvents] = useState<PayoutEvent[]>([]);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [notification, setNotification] = useState<string | null>(null);

  const [newTemplate, setNewTemplate] = useState({
    title: "",
    sector: "delivery",
    temperature_threshold_c: 43.5,
    duration_days: 2,
    payout_amount_inr: 800,
    premium_monthly_inr: 95,
    provider_name: "HDFC ERGO Micro-Protect",
    description: ""
  });

  const showToast = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 4000);
  };

  const fetchData = async () => {
    try {
      const [resStats, resTemplates, resActivePols, resEvents] = await Promise.all([
        fetch(`${API_BASE}/api/parametric/stats`).then((r) => r.json()),
        fetch(`${API_BASE}/api/parametric/policy-templates`).then((r) => r.json()),
        fetch(`${API_BASE}/api/parametric/active-policies`).then((r) => r.json()),
        fetch(`${API_BASE}/api/parametric/payout-events`).then((r) => r.json())
      ]);

      setStats(resStats);
      setPolicyTemplates(resTemplates);
      setActivePolicies(resActivePols);
      setPayoutEvents(resEvents);
    } catch (err) {
      console.error("Failed to fetch insurance data:", err);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleCreateTemplate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/api/parametric/policy-templates`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify(newTemplate)
      });
      if (res.ok) {
        showToast(`Policy template "${newTemplate.title}" published!`);
        setShowCreateModal(false);
        setNewTemplate({
          title: "",
          sector: "delivery",
          temperature_threshold_c: 43.5,
          duration_days: 2,
          payout_amount_inr: 800,
          premium_monthly_inr: 95,
          provider_name: "HDFC ERGO Micro-Protect",
          description: ""
        });
        fetchData();
      } else {
        const errData = await res.json();
        showToast(`Access Denied: ${errData.detail || "Insurance Provider role required"}`);
      }
    } catch (err) {
      showToast("Error publishing policy template");
    }
  };

  const totalExposureINR = activePolicies.reduce(
    (sum, p) => sum + p.payout_amount_inr * (p.covered_workers_count || 1),
    0
  );

  if (!user || user.role !== "insurance_provider") {
    return (
      <div className="min-h-[75vh] flex items-center justify-center p-4">
        <div className="bg-white p-8 rounded-3xl max-w-md w-full text-center border border-slate-200 shadow-xl space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-sky-50 text-sky-600 border border-sky-200 flex items-center justify-center mx-auto">
            <Landmark className="w-6 h-6" />
          </div>
          <h2 className="text-xl font-bold text-slate-900">Insurance Provider Authentication Required</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            The Underwriting Console is restricted to verified Insurance Companies and Risk Actuaries. Please sign in to create policy packages and view risk exposure logs.
          </p>
          <Link
            href="/login?role=insurance_provider&redirect=/insurance"
            className="inline-flex items-center justify-center gap-2 w-full py-3.5 rounded-2xl bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs shadow-lg shadow-sky-500/20 transition-all"
          >
            <span>SIGN IN AS INSURANCE PROVIDER</span>
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
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-sky-950 to-slate-900 p-6 sm:p-8 text-white shadow-2xl mb-8 border border-slate-800">
        <div className="absolute top-0 right-0 w-96 h-96 bg-sky-500/10 rounded-full blur-3xl -mr-20 -mt-20 pointer-events-none" />

        <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-sky-500/20 border border-sky-500/30 text-sky-300 text-xs font-semibold uppercase tracking-wider mb-3">
              <Landmark className="w-3.5 h-3.5" /> Insurance Provider Underwriting Desk
            </div>
            <h1 className="text-2xl sm:text-4xl font-bold tracking-tight text-white">
              Parametric Risk & Underwriting Console
            </h1>
            <p className="text-slate-300 text-sm mt-1 max-w-2xl">
              Design heatwave micro-insurance templates, set temperature trigger parameters, and audit real-time parametric claim payouts.
            </p>
          </div>

          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-5 py-3 rounded-2xl bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-600 hover:to-blue-700 text-white font-bold shadow-lg shadow-sky-500/25 active:scale-95 transition-all text-xs"
          >
            <Plus className="w-4 h-4" />
            <span>Create New Policy Package</span>
          </button>
        </div>

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-8 pt-6 border-t border-white/10">
          <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
            <div className="text-xs text-slate-400 font-medium">Underwritten Packages</div>
            <div className="text-2xl font-bold text-white mt-1">{policyTemplates.length}</div>
          </div>
          <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
            <div className="text-xs text-slate-400 font-medium">Active Policy Subscriptions</div>
            <div className="text-2xl font-bold text-sky-400 mt-1">{activePolicies.length}</div>
          </div>
          <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
            <div className="text-xs text-slate-400 font-medium">Total Maximum Exposure</div>
            <div className="text-2xl font-bold text-amber-300 mt-1">₹{totalExposureINR.toLocaleString("en-IN")}</div>
          </div>
          <div className="bg-white/5 rounded-2xl p-4 border border-white/10">
            <div className="text-xs text-slate-400 font-medium">Claims Paid Out</div>
            <div className="text-2xl font-bold text-emerald-400 mt-1">₹{stats.total_disbursed_inr.toLocaleString("en-IN")}</div>
          </div>
        </div>
      </div>

      {/* Main Grid: Policy Templates & Active Policies */}
      <div className="grid lg:grid-cols-2 gap-8 mb-8">
        {/* Left Column: Published Policy Templates */}
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Published Parametric Packages</h2>
              <p className="text-xs text-slate-500">Templates available for group managers to purchase.</p>
            </div>
          </div>

          <div className="space-y-4">
            {policyTemplates.map((t) => (
              <div key={t.id} className="bg-white rounded-3xl p-5 border border-slate-200 shadow-xs hover:border-slate-300 transition-all space-y-3">
                <div className="flex justify-between items-start">
                  <div>
                    <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold uppercase tracking-wider">
                      {t.provider_name}
                    </span>
                    <h3 className="text-base font-bold text-slate-900 mt-1">{t.title}</h3>
                  </div>
                  <span className="flex items-center gap-1 text-xs font-bold text-red-600 bg-red-50 px-2.5 py-1 rounded-xl border border-red-100">
                    <Flame className="w-3.5 h-3.5 fill-red-500 text-red-500" />
                    &ge; {t.temperature_threshold_c}°C
                  </span>
                </div>

                <p className="text-xs text-slate-600">{t.description}</p>

                <div className="grid grid-cols-3 gap-2 bg-slate-50 p-3 rounded-2xl text-[11px]">
                  <div>
                    <div className="text-slate-400">Target Sector</div>
                    <div className="font-bold text-slate-800 uppercase">{t.sector.replace("_", " ")}</div>
                  </div>
                  <div>
                    <div className="text-slate-400">Worker Payout</div>
                    <div className="font-bold text-slate-900">₹{t.payout_amount_inr}</div>
                  </div>
                  <div>
                    <div className="text-slate-400">Monthly Premium</div>
                    <div className="font-bold text-amber-700">₹{t.premium_monthly_inr} / worker</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: Active Policy Subscriptions */}
        <div className="space-y-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Active Cohort Coverages</h2>
            <p className="text-xs text-slate-500">Live insurance contracts bound to worker cohorts.</p>
          </div>

          <div className="bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-xs">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                  <tr>
                    <th className="p-3.5 pl-5">Cohort & Manager</th>
                    <th className="p-3.5">Policy</th>
                    <th className="p-3.5">Threshold</th>
                    <th className="p-3.5">Workers</th>
                    <th className="p-3.5 pr-5 text-right">Max Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium text-slate-800">
                  {activePolicies.map((ap) => (
                    <tr key={ap.id}>
                      <td className="p-3.5 pl-5">
                        <div className="font-bold text-slate-900">{ap.cohort_name}</div>
                        <div className="text-[10px] text-slate-400">{ap.manager_name}</div>
                      </td>
                      <td className="p-3.5 text-slate-700 font-semibold">{ap.title}</td>
                      <td className="p-3.5 text-amber-600 font-bold">&ge; {ap.temperature_threshold_c}°C</td>
                      <td className="p-3.5 font-bold">{ap.covered_workers_count}</td>
                      <td className="p-3.5 pr-5 text-right font-bold text-slate-900">
                        ₹{(ap.payout_amount_inr * (ap.covered_workers_count || 1)).toLocaleString("en-IN")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Section: Parametric Payout Audit Log */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-slate-900">Parametric Claims Audit Trail</h2>
        <div className="bg-white rounded-3xl border border-slate-200 overflow-hidden shadow-xs">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
              <tr>
                <th className="p-3.5 pl-5">Event ID</th>
                <th className="p-3.5">Cohort</th>
                <th className="p-3.5">Trigger Temp</th>
                <th className="p-3.5">Total Amount</th>
                <th className="p-3.5">Status</th>
                <th className="p-3.5 pr-5 text-right">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-medium text-slate-800">
              {payoutEvents.map((evt) => (
                <tr key={evt.id}>
                  <td className="p-3.5 pl-5 font-mono text-slate-400">{evt.id}</td>
                  <td className="p-3.5 font-bold text-slate-900">{evt.cohort_name}</td>
                  <td className="p-3.5 font-bold text-red-600">{evt.trigger_temperature_c}°C</td>
                  <td className="p-3.5 font-extrabold text-slate-900">₹{evt.total_amount_inr.toLocaleString("en-IN")}</td>
                  <td className="p-3.5">
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                        evt.status === "disbursed"
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-amber-100 text-amber-800"
                      }`}
                    >
                      {evt.status}
                    </span>
                  </td>
                  <td className="p-3.5 pr-5 text-right text-slate-400 text-[11px]">
                    {new Date(evt.trigger_date).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* MODAL: CREATE POLICY PACKAGE */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-md w-full shadow-2xl border border-slate-200 animate-scale-up space-y-4">
            <h3 className="text-lg font-bold text-slate-900">Design Parametric Policy Template</h3>
            
            <form onSubmit={handleCreateTemplate} className="space-y-3 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Insurance Provider Name</label>
                <input
                  type="text"
                  required
                  value={newTemplate.provider_name}
                  onChange={(e) => setNewTemplate({ ...newTemplate, provider_name: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Policy Title</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Gig Rider Heatwave Shield"
                  value={newTemplate.title}
                  onChange={(e) => setNewTemplate({ ...newTemplate, title: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Target Sector</label>
                <select
                  value={newTemplate.sector}
                  onChange={(e) => setNewTemplate({ ...newTemplate, sector: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  <option value="delivery">Delivery Riders / Gig Economy</option>
                  <option value="construction">Construction & Infrastructure Labor</option>
                  <option value="street_vendor">Street Vendors & Local Artisans</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Trigger Temp (°C)</label>
                  <input
                    type="number"
                    step="0.5"
                    required
                    value={newTemplate.temperature_threshold_c}
                    onChange={(e) => setNewTemplate({ ...newTemplate, temperature_threshold_c: parseFloat(e.target.value) })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Duration (Days)</label>
                  <input
                    type="number"
                    required
                    value={newTemplate.duration_days}
                    onChange={(e) => setNewTemplate({ ...newTemplate, duration_days: parseInt(e.target.value) })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Worker Payout (₹)</label>
                  <input
                    type="number"
                    required
                    value={newTemplate.payout_amount_inr}
                    onChange={(e) => setNewTemplate({ ...newTemplate, payout_amount_inr: parseFloat(e.target.value) })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Monthly Premium (₹)</label>
                  <input
                    type="number"
                    required
                    value={newTemplate.premium_monthly_inr}
                    onChange={(e) => setNewTemplate({ ...newTemplate, premium_monthly_inr: parseFloat(e.target.value) })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
                  />
                </div>
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Description</label>
                <textarea
                  required
                  rows={2}
                  value={newTemplate.description}
                  onChange={(e) => setNewTemplate({ ...newTemplate, description: e.target.value })}
                  placeholder="Details regarding parametric conditions..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-100 text-slate-600 font-semibold hover:bg-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 rounded-xl bg-sky-600 text-white font-bold hover:bg-sky-700 shadow-xs"
                >
                  Publish Package
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
