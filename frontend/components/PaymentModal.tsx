"use client";

import React, { useState } from "react";
import { 
  ShieldCheck, 
  CreditCard, 
  CheckCircle2, 
  Lock, 
  Sparkles, 
  ArrowRight, 
  X,
  Building2,
  QrCode,
  DollarSign
} from "lucide-react";
import { useAuth } from "./AuthProvider";

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

interface Cohort {
  id: string;
  name: string;
  worker_count?: number;
}

interface PaymentModalProps {
  template: PolicyTemplate;
  cohort: Cohort;
  onClose: () => void;
  onSuccess: (activePolicy: any) => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function PaymentModal({ template, cohort, onClose, onSuccess }: PaymentModalProps) {
  const { getAuthHeaders } = useAuth();
  const workerCount = Math.max(1, cohort.worker_count || 1);
  const basePremiumTotal = template.premium_monthly_inr * workerCount;
  const gstTax = Math.round(basePremiumTotal * 0.18); // 18% GST
  const grandTotal = basePremiumTotal + gstTax;

  const [paymentMethod, setPaymentMethod] = useState<"upi" | "card" | "netbanking">("upi");
  const [upiId, setUpiId] = useState("manager@okicici");
  const [cardNumber, setCardNumber] = useState("4532 •••• •••• 8892");
  const [cardExpiry, setCardExpiry] = useState("11/28");
  const [cardCvv, setCardCvv] = useState("734");

  const [processing, setProcessing] = useState(false);
  const [paid, setPaid] = useState(false);
  const [txId, setTxId] = useState("");

  const handlePay = async (e: React.FormEvent) => {
    e.preventDefault();
    setProcessing(true);

    try {
      // Simulate Payment Gateway API Processing
      await new Promise((resolve) => setTimeout(resolve, 1200));

      const generatedTx = `PAY-HEAT-${Math.floor(100000 + Math.random() * 900000)}`;
      setTxId(generatedTx);

      // Save policy in backend database
      const res = await fetch(`${API_BASE}/api/parametric/buy-policy`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          ...getAuthHeaders()
        },
        body: JSON.stringify({
          cohort_id: cohort.id,
          policy_template_id: template.id
        })
      });

      if (res.ok) {
        const activePolicy = await res.json();
        setPaid(true);
        setProcessing(false);
        setTimeout(() => {
          onSuccess(activePolicy);
        }, 1500);
      } else {
        alert("Payment verification failed at backend. Check authorization.");
        setProcessing(false);
      }
    } catch (err) {
      console.error(err);
      alert("Error executing payment gateway transaction");
      setProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 backdrop-blur-xs p-4">
      <div className="bg-white rounded-3xl max-w-lg w-full shadow-2xl border border-slate-200 overflow-hidden animate-scale-up">
        {/* Modal Top Bar */}
        <div className="bg-slate-900 text-white p-6 relative">
          <button
            onClick={onClose}
            className="absolute top-5 right-5 p-1.5 rounded-full bg-white/10 hover:bg-white/20 text-slate-300 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>

          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/20 border border-amber-500/30 text-amber-300 text-[10px] font-bold uppercase tracking-wider mb-2">
            <Lock className="w-3 h-3" /> Secure Checkout Gateway
          </div>

          <h2 className="text-xl font-bold">{template.title}</h2>
          <p className="text-xs text-slate-300">Underwritten by {template.provider_name}</p>
        </div>

        {paid ? (
          <div className="p-8 text-center space-y-4 animate-scale-up">
            <div className="w-14 h-14 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto shadow-inner">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <h3 className="text-xl font-bold text-slate-900">Payment Successful!</h3>
            <p className="text-xs text-slate-600">
              Parametric policy activated for <strong>{cohort.name}</strong> covering {workerCount} workers.
            </p>
            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200 text-xs font-mono text-left space-y-1">
              <div>Transaction ID: <strong className="text-slate-900">{txId}</strong></div>
              <div>Amount Paid: <strong className="text-emerald-700">₹{grandTotal.toLocaleString("en-IN")}</strong></div>
              <div>Status: <strong className="text-emerald-600">COMPLETED & ACTIVE</strong></div>
            </div>
          </div>
        ) : (
          <form onSubmit={handlePay} className="p-6 sm:p-8 space-y-6 text-xs">
            {/* Order Summary Box */}
            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200 space-y-2">
              <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">
                Order Summary
              </div>
              <div className="flex justify-between font-semibold text-slate-700">
                <span>Cohort Covered:</span>
                <span className="text-slate-900 font-bold">{cohort.name} ({workerCount} workers)</span>
              </div>
              <div className="flex justify-between text-slate-600">
                <span>Monthly Premium ({workerCount} × ₹{template.premium_monthly_inr}):</span>
                <span>₹{basePremiumTotal.toLocaleString("en-IN")}</span>
              </div>
              <div className="flex justify-between text-slate-600">
                <span>GST (18%):</span>
                <span>₹{gstTax.toLocaleString("en-IN")}</span>
              </div>
              <div className="flex justify-between pt-2 border-t border-slate-200 font-extrabold text-sm text-slate-900">
                <span>Total Due:</span>
                <span className="text-amber-600">₹{grandTotal.toLocaleString("en-IN")}</span>
              </div>
            </div>

            {/* Payment Method Selector */}
            <div className="space-y-2">
              <label className="block font-semibold text-slate-700">Select Payment Method:</label>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => setPaymentMethod("upi")}
                  className={`py-2.5 px-3 rounded-xl border text-center font-bold transition-all ${
                    paymentMethod === "upi"
                      ? "bg-amber-500 text-slate-950 border-amber-500 shadow-xs"
                      : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  UPI / GPay
                </button>

                <button
                  type="button"
                  onClick={() => setPaymentMethod("card")}
                  className={`py-2.5 px-3 rounded-xl border text-center font-bold transition-all ${
                    paymentMethod === "card"
                      ? "bg-amber-500 text-slate-950 border-amber-500 shadow-xs"
                      : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  Credit Card
                </button>

                <button
                  type="button"
                  onClick={() => setPaymentMethod("netbanking")}
                  className={`py-2.5 px-3 rounded-xl border text-center font-bold transition-all ${
                    paymentMethod === "netbanking"
                      ? "bg-amber-500 text-slate-950 border-amber-500 shadow-xs"
                      : "bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100"
                  }`}
                >
                  Netbanking
                </button>
              </div>
            </div>

            {/* Input Details based on Method */}
            {paymentMethod === "upi" && (
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Enter VPA / UPI ID</label>
                <input
                  type="text"
                  required
                  value={upiId}
                  onChange={(e) => setUpiId(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 font-mono"
                />
              </div>
            )}

            {paymentMethod === "card" && (
              <div className="space-y-3">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">Card Number</label>
                  <input
                    type="text"
                    required
                    value={cardNumber}
                    onChange={(e) => setCardNumber(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 font-mono"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">Expiry</label>
                    <input
                      type="text"
                      required
                      value={cardExpiry}
                      onChange={(e) => setCardExpiry(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">CVV</label>
                    <input
                      type="password"
                      required
                      maxLength={4}
                      value={cardCvv}
                      onChange={(e) => setCardCvv(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500 font-mono"
                    />
                  </div>
                </div>
              </div>
            )}

            {paymentMethod === "netbanking" && (
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Select Bank</label>
                <select className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-500">
                  <option value="icici">ICICI Bank Corporate Netbanking</option>
                  <option value="hdfc">HDFC Bank Corporate Netbanking</option>
                  <option value="sbi">State Bank of India</option>
                  <option value="axis">Axis Bank</option>
                </select>
              </div>
            )}

            <button
              type="submit"
              disabled={processing}
              className="w-full py-4 rounded-2xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-600 hover:to-orange-600 text-slate-950 font-bold shadow-lg shadow-orange-500/25 active:scale-98 transition-all flex items-center justify-center gap-2 text-xs"
            >
              {processing ? (
                <span>Processing Secure Payment...</span>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4" />
                  <span>PAY ₹{grandTotal.toLocaleString("en-IN")} & ACTIVATE POLICY</span>
                </>
              )}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
