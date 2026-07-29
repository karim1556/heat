"use client";

import React, { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { 
  ShieldCheck, 
  UserCheck, 
  Phone, 
  CreditCard, 
  MapPin, 
  CheckCircle2, 
  Flame, 
  Sparkles,
  Users
} from "lucide-react";

interface Cohort {
  id: string;
  name: string;
  manager_name: string;
  manager_email: string;
  sector: string;
  location_name: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function WorkerJoinPage() {
  const params = useParams();
  const cohortId = params.cohortId as string;

  const [cohort, setCohort] = useState<Cohort | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitted, setSubmitted] = useState(false);

  const [form, setForm] = useState({
    name: "",
    phone: "",
    payment_upi: ""
  });

  useEffect(() => {
    if (cohortId) {
      fetch(`${API_BASE}/api/parametric/cohorts/${cohortId}`)
        .then((r) => r.json())
        .then((data) => {
          setCohort(data);
          setLoading(false);
        })
        .catch((err) => {
          console.error(err);
          setLoading(false);
        });
    }
  }, [cohortId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/api/parametric/workers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cohort_id: cohortId,
          name: form.name,
          phone: form.phone,
          payment_upi: form.payment_upi
        })
      });
      if (res.ok) {
        setSubmitted(true);
      }
    } catch (err) {
      alert("Registration failed. Please try again.");
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="flex items-center gap-3 text-slate-500 font-medium text-sm">
          <Flame className="w-6 h-6 text-amber-500 animate-spin" />
          <span>Loading Cohort Information...</span>
        </div>
      </div>
    );
  }

  if (!cohort) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="bg-white p-8 rounded-3xl max-w-sm w-full text-center border border-slate-200 shadow-sm space-y-3">
          <h2 className="text-lg font-bold text-slate-900">Cohort Not Found</h2>
          <p className="text-xs text-slate-500">The QR Code or onboarding link may have expired or is invalid.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
      <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-md w-full shadow-xl border border-slate-200 space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="w-12 h-12 rounded-2xl bg-amber-500 text-white flex items-center justify-center mx-auto shadow-md shadow-amber-500/30">
            <ShieldCheck className="w-7 h-7" />
          </div>

          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-50 text-amber-800 text-[10px] font-bold uppercase tracking-wider border border-amber-200">
            <Flame className="w-3 h-3 text-amber-600 fill-amber-500" /> Parametric Heat Micro-Insurance
          </div>

          <h1 className="text-xl font-bold text-slate-900">{cohort.name}</h1>
          
          <div className="flex justify-center items-center gap-3 text-xs text-slate-500 font-medium">
            <span className="flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5 text-slate-400" />
              {cohort.location_name}
            </span>
            <span>•</span>
            <span>Manager: {cohort.manager_name}</span>
          </div>
        </div>

        {submitted ? (
          <div className="bg-emerald-50 rounded-2xl p-6 text-center border border-emerald-200 space-y-3 animate-scale-up">
            <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto" />
            <h2 className="text-base font-bold text-emerald-900">Coverage Activated!</h2>
            <p className="text-xs text-emerald-700 leading-relaxed">
              Welcome, <strong>{form.name}</strong>! You are now enrolled in the heat micro-insurance protection for <strong>{cohort.name}</strong>.
            </p>
            <div className="bg-white/80 p-3 rounded-xl text-left text-xs font-mono text-emerald-900 border border-emerald-200 space-y-1">
              <div>Phone: <strong>{form.phone}</strong></div>
              <div>Payout UPI: <strong>{form.payment_upi}</strong></div>
            </div>
            <p className="text-[11px] text-emerald-600 italic">
              During heatwave alerts, your relief payouts will automatically deposit into this UPI ID upon manager approval.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 text-xs">
            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100 space-y-1">
              <div className="font-bold text-slate-800 text-xs flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                No Forms or Fees Required
              </div>
              <p className="text-[11px] text-slate-500">
                Your group manager covers your monthly premium. Enter your phone and UPI details to receive automatic heatwave relief payouts.
              </p>
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Your Full Name</label>
              <div className="relative">
                <UserCheck className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="text"
                  required
                  placeholder="e.g. Rahul Sharma"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
              </div>
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">Mobile Phone Number</label>
              <div className="relative">
                <Phone className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                <input
                  type="tel"
                  required
                  placeholder="+91 98765 43210"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 font-mono"
                />
              </div>
            </div>

            <div>
              <label className="block font-semibold text-slate-700 mb-1">UPI ID for Direct Payouts</label>
              <div className="relative">
                <CreditCard className="w-4 h-4 text-amber-500 absolute left-3 top-3" />
                <input
                  type="text"
                  required
                  placeholder="e.g. rahul@paytm"
                  value={form.payment_upi}
                  onChange={(e) => setForm({ ...form, payment_upi: e.target.value })}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 font-mono"
                />
              </div>
            </div>

            <button
              type="submit"
              className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-white font-bold shadow-lg shadow-orange-500/25 active:scale-98 transition-all text-sm flex items-center justify-center gap-2"
            >
              <ShieldCheck className="w-5 h-5" />
              <span>JOIN COHORT & ACTIVATE COVERAGE</span>
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
