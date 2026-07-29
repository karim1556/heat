"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  explainPolicy,
  getStates,
  getWindowOptions,
  resolveLocation,
  simulatePolicy,
} from "@/lib/api";
import type {
  ExplainResponse,
  SimulatePolicyResponse,
  StateListEntry,
} from "@/lib/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { FeatureBars } from "@/components/FeatureBars";
import { PayoutChart } from "@/components/PayoutChart";
import { Sparkline } from "@/components/Sparkline";
import {
  ShoppingBag,
  Building2,
  Bike,
  MapPin,
  Calendar,
  Clock,
  ShieldCheck,
  Zap,
  TrendingUp,
  HelpCircle,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Info,
  CheckCircle2,
  Sparkles,
} from "lucide-react";

const OCCUPATION_ITEMS = [
  { id: "vendor", label: "Street Vendor", icon: ShoppingBag, desc: "Outdoor market stall & retail vendors" },
  { id: "construction", label: "Construction Worker", icon: Building2, desc: "Heavy physical outdoor site work" },
  { id: "delivery", label: "Delivery Rider", icon: Bike, desc: "Courier & last-mile transit riders" },
];

const WINDOW_DAYS_FALLBACK = 14;
const NASA_POWER_LAG_DAYS = 3;

function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function latestWindowStart(windowDays: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - NASA_POWER_LAG_DAYS - (windowDays - 1));
  return d.toISOString().slice(0, 10);
}

function groupByCountry(states: StateListEntry[]): Map<string, StateListEntry[]> {
  const groups = new Map<string, StateListEntry[]>();
  const sorted = [...states].sort((a, b) => a.state.localeCompare(b.state));
  for (const s of sorted) {
    const key = s.country === "IN" ? "India" : s.country === "US" ? "United States" : s.country;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(s);
  }
  return groups;
}

function cleanUrl(url: string): string {
  return url.trim().split(/\s+/)[0];
}

function sourceLabel(url: string | null): string {
  if (!url) return "source not on file";
  try {
    return new URL(cleanUrl(url)).hostname.replace(/^www\./, "");
  } catch {
    return cleanUrl(url);
  }
}

export default function SimulatePage() {
  const [states, setStates] = useState<StateListEntry[] | null>(null);
  const [statesError, setStatesError] = useState<string | null>(null);
  const [manualStateKey, setManualStateKey] = useState<string>("");

  const [occupation, setOccupation] = useState("vendor");
  const [windowOptions, setWindowOptions] = useState<number[]>([WINDOW_DAYS_FALLBACK]);
  const [windowDays, setWindowDays] = useState<number>(WINDOW_DAYS_FALLBACK);
  const [startDate, setStartDate] = useState(() => latestWindowStart(WINDOW_DAYS_FALLBACK));
  const [dateTouched, setDateTouched] = useState(false);

  const [result, setResult] = useState<SimulatePolicyResponse | null>(null);
  const [explainResult, setExplainResult] = useState<ExplainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [explainError, setExplainError] = useState<string | null>(null);
  const [locationNotice, setLocationNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [explainLoading, setExplainLoading] = useState(false);
  const [provenanceOpen, setProvenanceOpen] = useState(false);

  useEffect(() => {
    getStates()
      .then((rows) => {
        setStates(rows);
        setManualStateKey((prev) => prev || rows[0]?.state_key || "");
      })
      .catch((err: unknown) => {
        setStatesError(err instanceof ApiError ? err.message : "Failed to load state list.");
      });

    getWindowOptions()
      .then((opts) => {
        if (opts.selectable_window_days?.length) setWindowOptions(opts.selectable_window_days);
      })
      .catch(() => undefined);
  }, []);

  const grouped = useMemo(
    () => (states ? groupByCountry(states) : new Map<string, StateListEntry[]>()),
    [states],
  );

  const selectedStateDefaultWindow = useMemo(
    () => states?.find((s) => s.state_key === manualStateKey)?.window_days ?? null,
    [states, manualStateKey],
  );

  const [windowTouched, setWindowTouched] = useState(false);
  useEffect(() => {
    if (!windowTouched && selectedStateDefaultWindow) setWindowDays(selectedStateDefaultWindow);
  }, [selectedStateDefaultWindow, windowTouched]);

  const maxStart = latestWindowStart(windowDays);

  useEffect(() => {
    setStartDate((prev) => {
      if (!dateTouched) return maxStart;
      return prev > maxStart ? maxStart : prev;
    });
  }, [maxStart, dateTouched]);

  const endDate = addDays(startDate, windowDays - 1);

  async function priceStateKey(stateKey: string) {
    setLoading(true);
    setError(null);
    setResult(null);
    setExplainResult(null);
    setExplainError(null);
    try {
      const stateDefault = states?.find((s) => s.state_key === stateKey)?.window_days ?? null;
      const resp = await simulatePolicy({
        state_key: stateKey,
        occupation,
        date_range: { start: startDate, end: endDate },
        ...(stateDefault && windowDays === stateDefault ? {} : { window_days: windowDays }),
      });
      setResult(resp);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the pricing server.");
    } finally {
      setLoading(false);
    }
  }

  function useMyLocation() {
    setLocationNotice(null);
    setError(null);
    setResult(null);
    if (!("geolocation" in navigator)) {
      setLocationNotice("Geolocation isn't supported by this browser. Pick state manually.");
      return;
    }
    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude: lat, longitude: lon } = position.coords;
        resolveLocation({ lat, lon })
          .then(async (geo) => {
            if (geo.mode === "out_of_coverage") {
              setLocationNotice(geo.message ?? "Location not covered yet. Pick state manually.");
              setLoading(false);
              return;
            }
            setLocationNotice(`Detected: ${geo.state}, ${geo.country}`);
            await priceStateKey(geo.state_key!);
          })
          .catch((err: unknown) => {
            setError(err instanceof ApiError ? err.message : "Couldn't resolve your location.");
            setLoading(false);
          });
      },
      () => {
        setLocationNotice("Location permission denied. Pick your state manually below.");
        setLoading(false);
      },
    );
  }

  async function runExplain() {
    if (!result) return;
    setExplainLoading(true);
    setExplainError(null);
    try {
      setExplainResult(await explainPolicy(result.policy_id));
    } catch (err) {
      setExplainError(err instanceof ApiError ? err.message : "Couldn't fetch policy explanation.");
    } finally {
      setExplainLoading(false);
    }
  }

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 py-10 space-y-8">
      {/* Header Banner */}
      <div className="space-y-2">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-50 border border-amber-200 text-xs font-bold uppercase tracking-wider text-amber-800">
          <Zap className="w-3.5 h-3.5 text-amber-500" />
          <span>Interactive Parametric Pricer</span>
        </div>
        <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Simulate a Policy</h1>
        <p className="text-sm text-slate-600 max-w-2xl">
          Price real heat-wage insurance policies for outdoor workers. Frame options (income smoothing vs catastrophe insurance) and local minimum wage scales are automatically determined per state.
        </p>
      </div>

      {statesError && <ErrorBanner message={statesError} />}

      {/* Main 2-Column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        
        {/* Left Column: Config Panel */}
        <div className="lg:col-span-5 space-y-6">
          <div className="glass-card p-6 rounded-2xl space-y-6 border border-slate-200/80 shadow-md">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <span>01. Configure Coverage Parameters</span>
            </h2>

            {/* Occupation Visual Cards */}
            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-500">
                Occupation Type
              </label>
              <div className="grid grid-cols-1 gap-2.5">
                {OCCUPATION_ITEMS.map((occ) => {
                  const Icon = occ.icon;
                  const selected = occupation === occ.id;
                  return (
                    <button
                      key={occ.id}
                      type="button"
                      onClick={() => setOccupation(occ.id)}
                      className={`flex items-start gap-3 p-3 rounded-xl text-left border transition-all ${
                        selected
                          ? "bg-amber-50/80 border-amber-400 ring-2 ring-amber-400/20 shadow-xs"
                          : "bg-white border-slate-200/80 hover:border-slate-300 hover:bg-slate-50/50"
                      }`}
                    >
                      <div className={`p-2 rounded-lg ${selected ? "bg-amber-500 text-white" : "bg-slate-100 text-slate-500"}`}>
                        <Icon className="w-4 h-4" />
                      </div>
                      <div className="flex-1">
                        <div className="flex justify-between items-center">
                          <span className="text-xs font-bold text-slate-900">{occ.label}</span>
                          {selected && <CheckCircle2 className="w-4 h-4 text-amber-600" />}
                        </div>
                        <p className="text-[11px] text-slate-500">{occ.desc}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Window Duration Selector */}
            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 flex justify-between">
                <span>Coverage Window Length</span>
                {selectedStateDefaultWindow && (
                  <span className="text-[11px] font-mono font-normal text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
                    Default: {selectedStateDefaultWindow}d
                  </span>
                )}
              </label>
              <div className="grid grid-cols-3 gap-2">
                {windowOptions.map((w) => {
                  const selected = windowDays === w;
                  const isDefault = selectedStateDefaultWindow === w;
                  return (
                    <button
                      key={w}
                      type="button"
                      onClick={() => {
                        setWindowTouched(true);
                        setWindowDays(w);
                      }}
                      className={`py-2 px-3 rounded-xl text-xs font-mono font-bold border transition-all ${
                        selected
                          ? "bg-orange-500 text-white border-orange-500 shadow-sm"
                          : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      {w} Days
                      {isDefault && <span className="block text-[9px] font-sans font-normal opacity-90">State Default</span>}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Coverage Window Start Date */}
            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 flex justify-between items-center">
                <span>Window Start Date</span>
                <span className="text-[11px] font-mono text-amber-700 font-semibold bg-amber-50 px-2 py-0.5 rounded border border-amber-200/60">
                  Policy Ends: {endDate}
                </span>
              </label>
              <div className="relative">
                <input
                  type="date"
                  value={startDate}
                  min="2014-01-01"
                  max={maxStart}
                  onChange={(e) => {
                    setDateTouched(true);
                    setStartDate(e.target.value);
                  }}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-xs font-mono font-semibold text-slate-800 focus:ring-2 focus:ring-amber-500 focus:bg-white transition-all outline-none"
                />
              </div>

              {/* Data Horizon Guidance Banner */}
              <div className="bg-slate-100/90 border border-slate-200 rounded-xl p-2.5 text-[11px] text-slate-600 space-y-1">
                <div className="flex items-center justify-between font-semibold text-slate-700">
                  <span className="flex items-center gap-1 text-amber-700">
                    <Sparkles className="w-3 h-3 text-amber-500 shrink-0" />
                    Latest Available Weather:
                  </span>
                  <span className="font-mono text-slate-900">{addDays(maxStart, windowDays - 1)}</span>
                </div>
                <p className="text-[10.5px] leading-tight text-slate-500">
                  Dates after <strong className="font-mono text-slate-700">{maxStart}</strong> are locked for a {windowDays}-day window because 4-day NASA POWER satellite latency requires full observation data up to {addDays(maxStart, windowDays - 1)}.
                </p>
              </div>
            </div>

            {/* Geolocation Button */}
            <div className="pt-2">
              <button
                type="button"
                onClick={useMyLocation}
                disabled={loading}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-slate-100 hover:bg-slate-200/80 text-slate-800 px-4 py-2.5 text-xs font-bold transition-all disabled:opacity-50"
              >
                <MapPin className="w-4 h-4 text-orange-500" />
                <span>Auto-Detect My Location</span>
              </button>
              {locationNotice && (
                <p className="text-xs text-amber-700 mt-2 text-center font-medium bg-amber-50 p-2 rounded-lg border border-amber-200/60">
                  {locationNotice}
                </p>
              )}
            </div>

            {/* Manual State Selector & Primary Price CTA */}
            <div className="pt-4 border-t border-slate-200/80 space-y-3">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-500">
                Or Select State Manually
              </label>
              <select
                value={manualStateKey}
                onChange={(e) => setManualStateKey(e.target.value)}
                disabled={!states}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-xs font-semibold text-slate-800 focus:ring-2 focus:ring-amber-500 focus:bg-white transition-all outline-none"
              >
                {states === null && <option>Loading states...</option>}
                {[...grouped.entries()].map(([country, rows]) => (
                  <optgroup key={country} label={country}>
                    {rows.map((s) => (
                      <option key={s.state_key} value={s.state_key}>
                        {s.state} {s.mode === "excluded" ? "(Excluded)" : s.mode === "unpriced" ? "(Unpriced)" : ""}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>

              <button
                type="button"
                onClick={() => void priceStateKey(manualStateKey)}
                disabled={loading || !manualStateKey}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-amber-500 via-orange-500 to-red-500 text-white font-bold px-5 py-3.5 text-xs shadow-md shadow-orange-500/20 hover:shadow-lg hover:shadow-orange-500/30 hover:scale-[1.01] active:scale-95 transition-all duration-200 disabled:opacity-50"
              >
                {loading ? (
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    <span>Pricing Policy via LSMC...</span>
                  </div>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>Price Policy For Selected Region</span>
                  </>
                )}
              </button>
            </div>

          </div>
        </div>

        {/* Right Column: Pricing Dashboard */}
        <div className="lg:col-span-7 space-y-6">
          
          {error && <ErrorBanner message={error} />}

          {!result && !loading && (
            <div className="glass-card p-10 rounded-2xl text-center space-y-4 border border-slate-200/80">
              <div className="w-12 h-12 rounded-2xl bg-amber-50 border border-amber-200/80 flex items-center justify-center mx-auto text-amber-500">
                <Zap className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-bold text-slate-900 text-base">Ready to Price Policy</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
                  Choose your occupation and target state on the left to generate real-time actuarial pricing quotes.
                </p>
              </div>
            </div>
          )}

          {/* Excluded state message */}
          {result && (result.coverage_mode === "out_of_coverage" || result.coverage_mode === "excluded") && (
            <div className="glass-card p-6 rounded-2xl border-l-4 border-l-amber-500 bg-amber-50/50 space-y-2">
              <div className="flex items-center gap-2 font-bold text-amber-900 text-sm">
                <Info className="w-4 h-4 text-amber-600" />
                <span>{result.coverage_mode === "excluded" ? "Region Excluded from Pricing" : "Out of Coverage Range"}</span>
              </div>
              <p className="text-xs text-amber-800 leading-relaxed">{result.message}</p>
              <p className="text-[11px] text-amber-700/80 font-mono mt-2">{result.note}</p>
            </div>
          )}

          {/* Configured pricing result */}
          {result && result.coverage_mode === "configured" && (
            <div className="glass-card p-6 rounded-2xl space-y-6 border border-slate-200/90 shadow-lg">
              
              {/* Region Header */}
              <div className="flex justify-between items-start border-b border-slate-200/80 pb-4">
                <div>
                  <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Priced Policy Quote</div>
                  <h2 className="text-xl font-bold text-slate-900">
                    {result.state}, {result.country}
                  </h2>
                  <div className="text-xs font-medium text-slate-600 mt-0.5 capitalize">
                    Occupation: <span className="font-semibold text-slate-900">{result.occupation}</span>
                  </div>
                </div>

                {result.frame && (
                  <div className="text-right">
                    <span className="inline-block px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-orange-100 text-orange-800 border border-orange-200">
                      {result.frame.replace(/_/g, " ")}
                    </span>
                  </div>
                )}
              </div>

              {/* Dual Premium Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="bg-slate-50/80 p-4 rounded-xl border border-slate-200/80">
                  <div className="text-xs font-semibold text-slate-500">Fair Actuarial Price (LSMC)</div>
                  <div className="font-mono text-3xl font-extrabold text-slate-900 mt-1">
                    {result.currency} {result.premium_lsmc?.toFixed(2)}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1">Pure actuarial loss cost</div>
                </div>

                <div className="bg-gradient-to-br from-amber-50 to-orange-50 p-4 rounded-xl border border-orange-200/80">
                  <div className="text-xs font-bold text-orange-900">Insurer Price (with Wang Risk Load)</div>
                  <div className="font-mono text-3xl font-extrabold text-orange-600 mt-1">
                    {result.currency} {result.premium_wang?.toFixed(2)}
                  </div>
                  <div className="text-[11px] text-orange-700/80 mt-1">Loaded with capital risk margin</div>
                </div>
              </div>

              {/* Payout Schedule Section */}
              {result.payout_schedule && (
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-xs font-bold text-slate-700">
                    <span>Parametric Payout Schedule</span>
                    <span className="font-mono text-slate-500">Strike: {result.payout_schedule.strike}</span>
                  </div>
                  <PayoutChart
                    strike={result.payout_schedule.strike}
                    cap={result.payout_schedule.cap}
                    samplePoints={result.payout_schedule.sample_points}
                  />
                </div>
              )}

              {/* mu-TEVI Index Sparkline */}
              {result.mu_tevi_series && result.mu_tevi_series.length > 0 && (
                <div className="space-y-2">
                  <div className="flex justify-between items-center text-xs font-bold text-slate-700">
                    <span>mu-TEVI Index History (Coverage Window)</span>
                    <span className="font-mono text-amber-600">{result.mu_tevi_series.length} data points</span>
                  </div>
                  <Sparkline points={result.mu_tevi_series} />
                </div>
              )}

              {/* Basis Risk Section */}
              {result.basis_risk && (
                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-3">
                  <div className="flex items-center gap-2 text-xs font-bold text-slate-800">
                    <ShieldCheck className="w-4 h-4 text-emerald-600" />
                    <span>Basis Risk Transparency Disclosure</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center text-xs">
                    <div className="bg-white p-2 rounded-lg border border-slate-200/60">
                      <div className="text-[10px] text-slate-500">Shortfall Rate</div>
                      <div className="font-mono font-bold text-slate-900">
                        {(result.basis_risk.shortfall_rate * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div className="bg-white p-2 rounded-lg border border-slate-200/60">
                      <div className="text-[10px] text-slate-500">Overpay Rate</div>
                      <div className="font-mono font-bold text-slate-900">
                        {(result.basis_risk.overpay_rate * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div className="bg-white p-2 rounded-lg border border-slate-200/60">
                      <div className="text-[10px] text-slate-500 font-bold">Correlation</div>
                      <div className="font-mono font-bold text-emerald-600">
                        {result.basis_risk.correlation.toFixed(2)}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Explain Premium Drawer */}
              <div className="border-t border-slate-200/80 pt-4 space-y-3">
                <button
                  type="button"
                  onClick={() => void runExplain()}
                  disabled={explainLoading}
                  className="w-full flex items-center justify-center gap-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white px-4 py-2.5 text-xs font-bold transition-all disabled:opacity-50"
                >
                  <TrendingUp className="w-4 h-4 text-amber-400" />
                  <span>{explainLoading ? "Computing SHAP Contributions..." : "Explain Premium Contributions"}</span>
                </button>

                {explainError && <ErrorBanner message={explainError} />}

                {explainResult && (
                  <div className="bg-amber-50/40 p-4 rounded-xl border border-amber-200/60 space-y-3">
                    <div className="text-xs font-bold text-slate-800">
                      SHAP Feature Contributions ({explainResult.method.replace(/_/g, " ")})
                    </div>
                    <FeatureBars contributions={explainResult.feature_contributions_normalized} />
                  </div>
                )}
              </div>

              {/* Wage Basis Provenance Accordion */}
              {result.wage_provenance && (
                <div className="border-t border-slate-200/80 pt-4">
                  <button
                    type="button"
                    onClick={() => setProvenanceOpen(!provenanceOpen)}
                    className="w-full flex justify-between items-center text-xs font-bold text-slate-700 py-1"
                  >
                    <span>Wage Basis & Legal Minimum Wage Provenance</span>
                    {provenanceOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>

                  {provenanceOpen && (
                    <div className="mt-3 p-3 bg-slate-50 rounded-xl text-xs space-y-2 font-mono text-slate-600 border border-slate-200/80">
                      <div>
                        Region Baseline: <span className="font-bold text-slate-900">{result.wage_provenance.state}</span>
                      </div>
                      <div>
                        Wage Rate:{" "}
                        <span className="font-bold text-emerald-600">
                          {result.wage_provenance.value} {result.wage_provenance.currency}/day
                        </span>
                      </div>
                      {result.wage_provenance.source_url && (
                        <div className="truncate">
                          Source:{" "}
                          <a
                            href={cleanUrl(result.wage_provenance.source_url)}
                            target="_blank"
                            rel="noreferrer"
                            className="underline text-orange-600 inline-flex items-center gap-1 font-sans"
                          >
                            <span>{sourceLabel(result.wage_provenance.source_url)}</span>
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        </div>
                      )}
                      {result.wage_provenance.note && <div className="text-[11px] text-slate-500 font-sans">{result.wage_provenance.note}</div>}
                    </div>
                  )}
                </div>
              )}

            </div>
          )}

        </div>

      </div>
    </main>
  );
}
