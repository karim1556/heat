// Types mirroring backend/main.py's Pydantic response models exactly -- kept
// in one place so a backend schema change surfaces as a single TS diff here.

import type { Feature, MultiPolygon, Polygon } from "geojson";

// GET /state-boundary returns the raw admin-1 Feature verbatim -- Polygon OR
// MultiPolygon (22 of 87 states are MultiPolygon), never coerced to one type.
export type StateBoundary = Feature<Polygon | MultiPolygon>;

export type CoverageMode = "configured" | "excluded" | "out_of_coverage";
export type StateMode = "configured" | "excluded" | "unpriced";
export type Frame = "income_smoothing" | "catastrophe_insurance";

export type StateListEntry = {
  state_key: string;
  state: string;
  country: string;
  currency: string;
  metro: string;
  // This state's own committed contract window length (null if unpriced).
  window_days?: number | null;
  mode: StateMode;
};

export type ResolveLocationRequest = { lat?: number; lon?: number };

export type ResolveLocationResponse = {
  country: string | null;
  state: string | null;
  state_key: string | null;
  currency: string | null;
  mode: CoverageMode;
  message: string | null;
};

export type HeatmapFeature = {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    node_id: string;
    heat_index: number;
    temperature?: number | null;
    humidity?: number | null;
    mu_tevi: number | null;
  };
};

export type HeatmapResponse = {
  type: "FeatureCollection";
  features: HeatmapFeature[];
  metadata: {
    state_key: string;
    state: string;
    date: string;
    frame: Frame | null;
    // "state" = real full-state forecast (inductive STGCN over fetched NASA
    // POWER); "anchor" = the trained anchor-metro grid (also the honest
    // fallback when a whole-state fetch fails / the state is too small).
    coverage?: "state" | "anchor";
    inductive_transfer?: boolean;
    n_nodes?: number;
    // On an anchor response: false means a whole-state view was requested but
    // couldn't be served, so this is the honest anchor fallback.
    whole_state_available?: boolean;
    note: string;
  };
};

export type DateRange = { start: string; end: string };

export type SimulatePolicyRequest = {
  state_key?: string;
  occupation: string;
  date_range: DateRange;
  lat?: number;
  lon?: number;
  // Omit for the state's own committed contract window. Only the lengths the
  // real historical sweep scored are accepted by the backend.
  window_days?: number;
};

export type BasisRisk = {
  basis_risk_rmse: number;
  shortfall_rate: number;
  overpay_rate: number;
  correlation: number;
};

export type PayoutSchedule = {
  form: string;
  strike: number;
  cap: number;
  trigger_frequency: number;
  sample_points: Record<string, number>;
};

export type MuTeviPoint = { ts: string; mu_tevi: number };

export type WageProvenance = {
  state: string;
  occupation: string;
  value: number;
  currency: string;
  source_url: string | null;
  confidence: string | null;
  note: string | null;
};

export type SimulatePolicyResponse = {
  policy_id: string;
  coverage_mode: CoverageMode;
  country: string | null;
  state: string | null;
  state_key: string | null;
  currency: string | null;
  frame: Frame | null;
  strike: number | null;
  window_days: number | null;
  occupation: string | null;
  premium_lsmc: number | null;
  premium_wang: number | null;
  payout_schedule: PayoutSchedule | null;
  mu_tevi_series: MuTeviPoint[] | null;
  basis_risk: BasisRisk | null;
  wage_provenance: WageProvenance | null;
  message: string | null;
  // Days of the priced window that fall after the state's calibration period
  // and were computed by forward-applying the already-fitted models to
  // live-fetched real weather. 0 => entirely within the calibrated series.
  extended_days: number | null;
  calibrated_through: string | null;
  // True when the priced (strike, window) pairing came from this state's real
  // historical sweep rather than being carried over from another length.
  window_independently_evaluated?: boolean | null;
  committed_window_days?: number | null;
  committed_strike?: number | null;
  note: string;
};

export type ExplainResponse = {
  policy_id: string;
  method: string;
  feature_contributions: Record<string, number>;
  feature_contributions_normalized: Record<string, number>;
  note: string;
};
