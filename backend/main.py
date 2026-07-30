"""FastAPI backend exposing the per-state pipeline as a service (v2 state-wise
rewrite -- replaces the v1 single-city Ahmedabad API; /forecast and
/flag-anomaly still serve the legacy single-city artifacts, out of scope here).

PRODUCT FRAMING (carried from Prompt 6b, now PER-STATE, never assumed): each
state's frame -- "income_smoothing" (chronic, high-frequency peril) or
"catastrophe_insurance" (rare, extreme peril) -- is read from that state's own
`models/artifacts/<state_key>/contract.json`, discovered from its real climate
regime by backend/backtest/contract_design.py's sweep. Never hardcode a frame
here; a temperate state and an extreme-heat state can legitimately differ.

STATE NAMESPACING: every route resolves a `state_key` (either given directly
or detected from lat/lon via backend/data/geo_states.resolve_state, offline
Natural Earth polygons -- no geocoding API) and then loads that state's own
context via backend/state_context.get_context: its wage schedule + currency
(config/wages_by_state.yaml), its anchor-metro weather grid
(config/state_anchors.yaml), and its own trained artifacts
(models/artifacts/<state_key>/). CURRENCY IS NEVER CONVERTED.

THREE COVERAGE MODES, always distinguished honestly (never a fabricated
price): "configured" (in the 78 priced states), "excluded" (a real state that
failed the coverage bar -- e.g. Alaska, too few heat-exposure days --
reason read from its excluded.json marker), "out_of_coverage" (outside
India/US, or a real admin-1 region not in the 79 configured states).

LAZY MODEL LOADING: no *.pt / copula.json / mu_tevi.parquet is read at import
time -- only inside request handlers, cached per state_key -- so this module
(and CI) can import `app` with zero trained artifacts on disk. A missing
artifact returns 503 rather than crashing.

PRIVACY: lat/lon travel ONLY in POST bodies (never a query string), are used
transiently to resolve a state, and are never logged or persisted -- only the
resolved state_key is retained (in the in-memory policy cache and responses).
"""

import json
import logging
import os
import uuid
from datetime import date
from typing import Any, Optional, List, Dict

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.responses import JSONResponse
import backend.auth as auth
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.data.geo_states import GEOJSON_PATH, resolve_state
from backend.state_context import all_state_keys, get_context, state_exists
from backend.anchor_weather import fetch_anchor_weather_live
from backend.mu_tevi_extend import extend_mu_tevi
from backend.window_contracts import (
    SELECTABLE_WINDOW_DAYS,
    SweepTableUnavailable,
    contract_for_window,
)
from backend.state_heatmap import build_state_heatmap
from models.pricing.lsmc_pricer import LSMCPricer
import backend.parametric as parametric

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Pricing the Heat", version="2.0.0")

@app.on_event("startup")
def startup_event():
    parametric.init_db()

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )

@app.exception_handler(Exception)
async def custom_unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )

# FRONTEND_ORIGIN lets the deployed frontend (pricing-heat-web on Render, per
# render.yaml) call this cross-origin backend; defaults to "*" for easy first
# deploy, tightened later by setting FRONTEND_ORIGIN to the frontend's exact
# URL. allow_credentials is False because this app has no cookie/session auth
# -- that also keeps "*" a valid origin value (browsers reject
# allow_origins=["*"] combined with allow_credentials=True).
frontend_origin_env = os.environ.get("FRONTEND_ORIGIN", "*")
origins = ["*"] if frontend_origin_env == "*" or not frontend_origin_env else [
    o.strip().rstrip("/") for o in frontend_origin_env.split(",") if o.strip()
]
if "*" not in origins:
    origins.append("*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


FORECASTER_PATH = "models/artifacts/forecaster.pt"
ANOMALY_PATH = "models/artifacts/anomaly.pkl"

MODEL_NOT_TRAINED_DETAIL = "model artifact not trained yet — run make train / make train-all-states"

# In-memory cache: policy_id -> everything /explain needs to reconstruct the
# pricer and re-derive an explanation. No DB required (Prompt 7's rule).
_policy_cache: dict[str, dict[str, Any]] = {}

# Lazy STGCN handles, one per state_key, populated on first /heatmap call for
# that state.
_stgcn_cache: dict[str, dict[str, Any]] = {}

# Lazy GRU forecaster handle (legacy single-city artifact), populated on first
# /forecast call only.
_forecaster_cache: dict[str, Any] = {}

# Lazy anomaly-detector handle (legacy single-city artifact), populated on
# first /flag-anomaly call only.
_anomaly_cache: dict[str, Any] = {}

# Lazy map: state_key -> that state's raw GeoJSON boundary Feature, parsed once
# from the SAME Natural Earth admin-1 file resolve_state uses (never a new/
# derived boundary source). Populated on the first /state-boundary call.
_boundary_cache: dict[str, dict] = {}


def _load_boundaries() -> dict[str, dict]:
    """Parse the admin-1 GeoJSON once, keyed by state_key. Each value is the
    raw GeoJSON Feature verbatim -- Polygon OR MultiPolygon, whichever the
    source data is (22 of the 87 admin-1 features are MultiPolygon, e.g.
    coastal/island states) -- never coerced to a single assumed type.
    """
    if not _boundary_cache:
        data = json.loads(GEOJSON_PATH.read_text())
        for feat in data["features"]:
            _boundary_cache[feat["properties"]["state_key"]] = feat
    return _boundary_cache


def _load_stgcn(state_key: str, ctx) -> tuple[Any, Any]:
    """Lazily loads state_key's trained STGCN checkpoint. (None, None) if untrained."""
    cached = _stgcn_cache.get(state_key)
    if cached is not None:
        return cached["model"], cached["ckpt"]

    stgcn_path = ctx.artifact("stgcn.pt")
    if not stgcn_path.exists():
        return None, None

    import torch

    from models.stgcn.model import STGCN

    # stgcn_path is derived only from a validated state_key (checked against
    # state_exists before this is ever called), never from arbitrary request
    # text, so this never deserializes attacker-controlled input;
    # weights_only=False is required because the checkpoint carries
    # non-tensor config/graph data alongside the state_dict (see
    # models/stgcn/train.py). See SECURITY.md.
    ckpt = torch.load(stgcn_path, map_location="cpu", weights_only=False)  # nosec B614
    cfg = ckpt["config"]
    model = STGCN(in_channels=cfg["in_channels"], hidden=cfg["hidden"], horizon=cfg["horizon"],
                  t_in=cfg["t_in"], k_order=cfg["k_order"], kernel_size=cfg["kernel_size"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    _stgcn_cache[state_key] = {"model": model, "ckpt": ckpt}
    return model, ckpt


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Heat Parametric API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}



# --- /states ------------------------------------------------------------


class StateListEntry(BaseModel):
    state_key: str
    state: str
    country: str
    currency: str
    metro: str
    mode: str  # "configured" | "excluded" | "unpriced"
    # This state's OWN committed contract window length, so the UI defaults to
    # the state's real default instead of assuming one globally. None when the
    # state has no priced contract.
    window_days: Optional[int] = None


@app.get("/states", response_model=list[StateListEntry])
def list_states():
    """Every state in the real config (79 total: 78 priced + Alaska excluded),
    with its real currency/metro/mode -- the single source of truth the
    frontend's state selectors read from, never hand-duplicated in the UI.
    Only checks file EXISTENCE (contract.json / excluded.json), never loads
    model weights, so this stays cheap and eager.
    """
    out = []
    for key in all_state_keys():
        ctx = get_context(key)
        window_days = None
        if ctx.artifact("excluded.json").exists():
            mode = "excluded"
        elif ctx.artifact("contract.json").exists():
            mode = "configured"
            # contract.json is a few hundred bytes; reading it keeps this
            # endpoint the single source of truth for each state's own default
            # window without loading any model weights.
            window_days = int(json.loads(ctx.artifact("contract.json").read_text())["window_days"])
        else:
            mode = "unpriced"
        out.append(StateListEntry(
            state_key=key, state=ctx.wage.get("state", key), country=ctx.country,
            currency=ctx.currency, metro=ctx.metro, mode=mode, window_days=window_days,
        ))
    return out


@app.get("/window-options")
def window_options():
    """The coverage-window lengths a policy may actually be priced at.

    Exactly the WINDOW_GRID the real historical contract sweep scored, so the
    UI can never offer a length with no evaluated contract behind it.
    """
    return {
        "selectable_window_days": list(SELECTABLE_WINDOW_DAYS),
        "note": "Only these lengths were evaluated against real history. Each state's "
                "contract for a given length is the one that length's own sweep selected.",
    }


# --- /resolve-location ----------------------------------------------------


class ResolveLocationRequest(BaseModel):
    lat: float
    lon: float


class ResolveLocationResponse(BaseModel):
    country: Optional[str] = None
    state: Optional[str] = None
    state_key: Optional[str] = None
    currency: Optional[str] = None
    mode: str  # "configured" | "excluded" | "out_of_coverage"
    message: Optional[str] = None


def _resolve_and_classify(lat: float, lon: float) -> dict:
    """Resolve (lat, lon) to a real state, then classify it into one of the
    three honest coverage modes. Never fabricates a price/state for a point
    outside real coverage -- see module docstring.
    """
    geo = resolve_state(lat, lon)
    if geo["mode"] == "out_of_coverage":
        return {"mode": "out_of_coverage", "message": geo["message"]}

    state_key = geo["state_key"]
    if not state_exists(state_key):
        return {
            "mode": "out_of_coverage",
            "message": f"{geo['state']}, {geo['country']} was detected but is not in the "
                       f"currently priced 79-state set.",
        }

    ctx = get_context(state_key)
    if ctx.artifact("excluded.json").exists():
        reason = json.loads(ctx.artifact("excluded.json").read_text())["reason"]
        return {"mode": "excluded", "state_key": state_key, "state": geo["state"],
                "country": geo["country"], "currency": ctx.currency, "message": reason}
    if not ctx.artifact("contract.json").exists():
        return {"mode": "out_of_coverage", "state_key": state_key, "state": geo["state"],
                "country": geo["country"],
                "message": f"{geo['state']}, {geo['country']} is in the configured set but its "
                           f"pricing pipeline has not finished training yet."}

    return {"mode": "configured", "state_key": state_key, "state": geo["state"],
            "country": geo["country"], "currency": ctx.currency}


@app.post("/resolve-location", response_model=ResolveLocationResponse)
def resolve_location(req: ResolveLocationRequest):
    """Resolve a real GPS coordinate to its real state (offline Natural Earth
    point-in-polygon -- no geocoding API, no key). lat/lon travel ONLY in this
    POST body (never a query string) and are used transiently -- never logged
    or persisted. An out-of-coverage or excluded point gets an honest message;
    nothing is ever fabricated for it.
    """
    result = _resolve_and_classify(req.lat, req.lon)
    return ResolveLocationResponse(**result)


# --- /simulate-policy -------------------------------------------------------


class DateRange(BaseModel):
    start: date
    end: date


class SimulatePolicyRequest(BaseModel):
    state_key: Optional[str] = None
    occupation: str = "vendor"
    date_range: DateRange
    lat: Optional[float] = None
    lon: Optional[float] = None
    # Coverage-window length. Omit for the state's own committed contract.
    # Only the lengths the real historical sweep scored are accepted; each
    # non-default length is priced with THAT length's own already-selected
    # strike/frame (see backend/window_contracts.py).
    window_days: Optional[int] = None


class BasisRiskBlock(BaseModel):
    basis_risk_rmse: float
    shortfall_rate: float
    overpay_rate: float
    correlation: float


class WageProvenanceBlock(BaseModel):
    state: str
    occupation: str
    value: float
    currency: str
    source_url: Optional[str] = None
    confidence: Optional[str] = None
    note: Optional[str] = None


class SimulatePolicyResponse(BaseModel):
    policy_id: str
    coverage_mode: str  # "configured" | "excluded" | "out_of_coverage"
    country: Optional[str] = None
    state: Optional[str] = None
    state_key: Optional[str] = None
    currency: Optional[str] = None
    frame: Optional[str] = None  # "income_smoothing" | "catastrophe_insurance"
    strike: Optional[float] = None
    window_days: Optional[int] = None
    occupation: Optional[str] = None
    premium_lsmc: Optional[float] = None
    premium_wang: Optional[float] = None
    payout_schedule: Optional[dict] = None
    mu_tevi_series: Optional[List[dict]] = None
    basis_risk: Optional[BasisRiskBlock] = None
    wage_provenance: Optional[WageProvenanceBlock] = None
    message: Optional[str] = None
    # How many days of the priced window came from live-fetched real weather
    # run through the ALREADY-FITTED models, rather than from the static
    # calibrated mu-TEVI series. 0 => entirely within the calibration period.
    extended_days: Optional[int] = None
    calibrated_through: Optional[str] = None
    # True when the priced (strike, window) pairing came from this state's
    # real historical design sweep rather than being carried over from a
    # different window length.
    window_independently_evaluated: Optional[bool] = None
    committed_window_days: Optional[int] = None
    committed_strike: Optional[float] = None
    note: str


@app.post("/simulate-policy", response_model=SimulatePolicyResponse)
@limiter.limit("30/minute")
def simulate_policy(req: SimulatePolicyRequest, request: Request):
    """Price this state's own contract (frame/strike/window from its real
    contract.json) for a resolved state + occupation + real coverage window.

    Surfaces basis_risk as a first-class HONESTY feature (Prompt 6b, carried
    constraint D): the gap between the index-triggered payout and the
    worker's modeled loss, not hidden inside a single headline number.
    """
    policy_id = str(uuid.uuid4())

    if req.state_key:
        if not state_exists(req.state_key):
            raise HTTPException(status_code=400, detail=f"unknown state_key {req.state_key!r}")
        state_key = req.state_key
    elif req.lat is not None and req.lon is not None:
        geo = _resolve_and_classify(req.lat, req.lon)
        if geo["mode"] != "configured":
            _policy_cache[policy_id] = {"window_days": None}
            note = (
                "No pricing computed: this state is excluded from pricing (insufficient "
                "heat-exposure signal). No data was fabricated."
                if geo["mode"] == "excluded" else
                "No pricing computed: location is outside the priced coverage set. "
                "No data was fabricated for this point."
            )
            return SimulatePolicyResponse(
                policy_id=policy_id, coverage_mode=geo["mode"],
                country=geo.get("country"), state=geo.get("state"), state_key=geo.get("state_key"),
                currency=geo.get("currency"), message=geo.get("message"), note=note,
            )
        state_key = geo["state_key"]
    else:
        raise HTTPException(status_code=400, detail="must supply either state_key or lat/lon")

    ctx = get_context(state_key)

    if ctx.artifact("excluded.json").exists():
        reason = json.loads(ctx.artifact("excluded.json").read_text())["reason"]
        _policy_cache[policy_id] = {"window_days": None}
        return SimulatePolicyResponse(
            policy_id=policy_id, coverage_mode="excluded", state_key=state_key,
            state=ctx.wage.get("state", state_key), country=ctx.country, currency=ctx.currency,
            message=reason,
            note="No pricing computed: this state is excluded from pricing (insufficient "
                 "heat-exposure signal). No data was fabricated.",
        )

    contract_path = ctx.artifact("contract.json")
    copula_path = ctx.artifact("copula.json")
    if not contract_path.exists() or not copula_path.exists():
        raise HTTPException(status_code=503, detail=MODEL_NOT_TRAINED_DETAIL)
    contract = json.loads(contract_path.read_text())

    wages = ctx.daily_wages()
    if req.occupation not in wages:
        raise HTTPException(
            status_code=400,
            detail=f"unknown occupation '{req.occupation}'; have {sorted(wages)}",
        )

    # Window length is selectable among the lengths the real historical sweep
    # actually scored. Omitting it reproduces the committed contract exactly.
    # A non-default length uses THAT length's own already-evaluated best
    # strike/frame, looked up from the state's persisted sweep table -- every
    # state has at least one length whose best strike differs from its 14-day
    # one, so carrying the 14-day strike over would misprice it. Nothing is
    # refitted; see backend/window_contracts.py.
    if req.window_days is None:
        window_days = int(contract["window_days"])
        strike = float(contract["strike"])
        cap = float(contract["cap"])
        frame = contract["frame"]
        window_independently_evaluated = True
        window_is_committed_default = True
    else:
        try:
            selected = contract_for_window(state_key, int(req.window_days))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except SweepTableUnavailable as exc:
            # NOT "untrained" -- the model is fine, this deployment just can't
            # price a non-default length. Reported as itself.
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail=MODEL_NOT_TRAINED_DETAIL) from None
        window_days = selected["window_days"]
        strike = selected["strike"]
        cap = selected["cap"]
        frame = selected["frame"]
        window_independently_evaluated = selected["independently_evaluated"]
        window_is_committed_default = selected["is_committed_default"]

    if req.date_range.end < req.date_range.start:
        raise HTTPException(status_code=400, detail="date_range.end must be >= date_range.start")

    mu_tevi_path = ctx.processed("mu_tevi.parquet")
    if not mu_tevi_path.exists():
        raise HTTPException(status_code=503, detail=MODEL_NOT_TRAINED_DETAIL)
    state_index = pd.read_parquet(mu_tevi_path).sort_values("ts").reset_index(drop=True)
    last_calibrated_ts = pd.Timestamp(state_index["ts"].max())
    start_ts = pd.Timestamp(req.date_range.start)
    window_df = state_index[state_index["ts"] >= start_ts].head(window_days)

    # The static mu_tevi.parquet stops at the end of this state's calibration
    # period. For a window running past it, extend with real CURRENT data by
    # FORWARD-APPLYING the already-fitted models (calibration.json's
    # kappa/gamma, copula.json's theta/GEV/hurdle) to real observed weather --
    # nothing is refitted, and mu_tevi.parquet itself is never written. See
    # backend/mu_tevi_extend.py.
    extended_days = 0
    if len(window_df) < window_days:
        window_end_ts = start_ts + pd.Timedelta(days=window_days - 1)
        try:
            extra = extend_mu_tevi(state_key, start_ts, window_end_ts)
        except SystemExit:
            raise HTTPException(
                status_code=503,
                detail=f"real weather needed to price {req.date_range.start} could not be "
                       f"fetched from NASA POWER (source unreachable); no substitute was used",
            ) from None
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        except FileNotFoundError as exc:
            # A frozen-model input this deployment doesn't ship (e.g. per-state
            # calibration.json, absent from the runtime bundle before v2.13).
            # Surfaced as a real 503 rather than an unhandled 500.
            missing_name = os.path.basename(exc.filename) if exc.filename else str(exc)
            raise HTTPException(
                status_code=503,
                detail=f"cannot extend pricing past the calibrated period here: a required "
                       f"model artifact is missing from this deployment ({missing_name}). "
                       f"No value was substituted.",
            ) from None
        if not extra.empty:
            combined = (pd.concat([state_index, extra], ignore_index=True)
                        .drop_duplicates(subset="ts", keep="last")
                        .sort_values("ts").reset_index(drop=True))
            window_df = combined[combined["ts"] >= start_ts].head(window_days)
            extended_days = int((window_df["ts"] > last_calibrated_ts).sum())

    if len(window_df) < window_days:
        raise HTTPException(
            status_code=404,
            detail=f"real mu-TEVI data does not cover a full {window_days}-day window "
                   f"starting {req.date_range.start} for {state_key}; no data was fabricated to fill it",
        )

    pricer = LSMCPricer.from_copula_json(path=copula_path, strike=strike, cap=cap)
    wage_value = float(wages[req.occupation])
    window_values = window_df["mu_tevi"].to_numpy()
    result = pricer.price_window(window_values, req.occupation, wage=wage_value)

    prov = ctx.wage_provenance()
    wage_provenance = WageProvenanceBlock(
        state=prov["state"], occupation=req.occupation, value=wage_value, currency=prov["currency"],
        source_url=prov.get("source_url"), confidence=prov.get("confidence"), note=prov.get("note"),
    )

    _policy_cache[policy_id] = {
        "state_key": state_key,
        "occupation": req.occupation,
        "window_days": window_days,
        "strike": pricer.strike,
        "cap": pricer.cap,
        # Cached verbatim so /explain's surrogate is grounded on the SAME
        # contract this response returned, not a re-derived one.
        "premium_lsmc": result["premium_lsmc"],
        "premium_wang": result["premium_wang"],
        "payout_schedule": result["payout_schedule"],
        "basis_risk": result["basis_risk"],
    }

    return SimulatePolicyResponse(
        policy_id=policy_id,
        coverage_mode="configured",
        country=ctx.country,
        state=prov["state"],
        state_key=state_key,
        currency=ctx.currency,
        frame=frame,
        strike=strike,
        window_days=window_days,
        window_independently_evaluated=window_independently_evaluated,
        committed_window_days=int(contract["window_days"]),
        committed_strike=float(contract["strike"]),
        occupation=req.occupation,
        premium_lsmc=result["premium_lsmc"],
        premium_wang=result["premium_wang"],
        payout_schedule=result["payout_schedule"],
        mu_tevi_series=[
            {"ts": row["ts"].date().isoformat(), "mu_tevi": float(row["mu_tevi"])}
            for _, row in window_df.iterrows()
        ],
        basis_risk=BasisRiskBlock(**result["basis_risk"]),
        wage_provenance=wage_provenance,
        extended_days=extended_days,
        calibrated_through=str(last_calibrated_ts.date()),
        note=(
            f"Priced as {frame.replace('_', ' ')} -- this state's frame is "
            f"discovered from its own real climate regime, never assumed globally: a "
            f"{window_days}-day coverage window at strike {strike:.2f} mu-TEVI, "
            f"starting {req.date_range.start}. basis_risk reports how often the index "
            f"under/over-pays the worker's own modeled loss -- inherent to any parametric "
            f"product, surfaced honestly rather than hidden."
            + (
                f" This {window_days}-day length is not this state's committed default "
                f"({contract['window_days']} days at strike {float(contract['strike']):.2f}); "
                f"its strike and frame are the ones this length's own real historical sweep "
                f"already selected, looked up rather than refitted."
                if not window_is_committed_default else ""
            )
            + (
                f" {extended_days} of these {window_days} days fall after this state's "
                f"calibration period (which ends {last_calibrated_ts.date()}): their mu-TEVI "
                f"comes from live-fetched real NASA POWER weather run through the SAME "
                f"already-fitted models and priced with the SAME committed contract -- "
                f"nothing was refitted for them."
                if extended_days else ""
            )
        ),
    )


# --- /explain/{policy_id} ---------------------------------------------------


def _explain_contract(pricer: LSMCPricer, window_days: int, n_paths: int = 1000,
                      seed: int = 42) -> dict:
    """Feature-contribution surrogate for the priced contract.

    price_window's premium is a Bermudan (one-shot optimal-stopping) LSMC
    value with no native SHAP-compatible model, so this fits a small
    transparent linear surrogate -- regressing each simulated path's
    discounted payoff on three summary features of that path's mu-TEVI window
    -- and explains THAT surrogate. Uses shap.LinearExplainer if shap installs
    cleanly; otherwise falls back to sklearn permutation importance on the
    same regression. Either way this never blocks on SHAP being available.
    """
    rng = np.random.default_rng(seed)
    mutevi_paths, _loss_paths = pricer.simulate_paths(window_days, n_paths, rng)
    priced = pricer.price_paths(mutevi_paths, _loss_paths)
    y = priced["discounted_payoffs"]

    feature_names = ["max_index_in_window", "mean_index_in_window", "fraction_days_above_strike"]
    x = np.column_stack([
        mutevi_paths.max(axis=1),
        mutevi_paths.mean(axis=1),
        (mutevi_paths >= pricer.strike).mean(axis=1),
    ])

    from sklearn.linear_model import LinearRegression
    model = LinearRegression().fit(x, y)

    try:
        import importlib
        shap = importlib.import_module("shap")

        explainer = shap.LinearExplainer(model, x)
        shap_values = explainer.shap_values(x)
        contributions = {name: float(np.abs(shap_values[:, i]).mean())
                         for i, name in enumerate(feature_names)}
        method = "shap"
    except ImportError:
        from sklearn.inspection import permutation_importance

        r = permutation_importance(model, x, y, n_repeats=10, random_state=seed)
        contributions = {name: float(max(r.importances_mean[i], 0.0))
                         for i, name in enumerate(feature_names)}
        method = "permutation_importance"

    total = sum(contributions.values()) or 1.0
    return {
        "method": method,
        "feature_contributions": contributions,
        "feature_contributions_normalized": {k: v / total for k, v in contributions.items()},
        "note": "Surrogate explanation of the LSMC premium's sensitivity to the priced "
                "window's heat-index summary -- not a decomposition of the exact Bermudan "
                "value, which has no closed-form attribution.",
    }


@app.get("/explain/{policy_id}")
def explain(policy_id: str):
    cached = _policy_cache.get(policy_id)
    if cached is None:
        raise HTTPException(status_code=404, detail=f"unknown policy_id {policy_id!r}")
    if cached.get("window_days") is None:
        raise HTTPException(
            status_code=404,
            detail="policy has no priced contract to explain (out-of-coverage / excluded)",
        )

    ctx = get_context(cached["state_key"])
    try:
        pricer = LSMCPricer.from_copula_json(
            path=ctx.artifact("copula.json"), strike=cached["strike"], cap=cached["cap"])
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail=MODEL_NOT_TRAINED_DETAIL)

    explanation = _explain_contract(pricer, cached["window_days"])
    return {"policy_id": policy_id, **explanation}


# --- /heatmap ---------------------------------------------------------------


@app.get("/heatmap")
def heatmap(state_key: str, date: Optional[str] = None, coverage: str = "anchor"):
    """GeoJSON of state_key's real STGCN heat forecast, per node.

    coverage="anchor" (default, pricing-adjacent, UNCHANGED): the trained
    anchor-metro grid on disk -- the exact grid every mu-TEVI/copula/contract
    was calibrated on. coverage="state": the real full-state forecast, fetched
    on demand from NASA POWER over the state's full border and run through the
    SAME trained stgcn.pt inductively (see backend/state_heatmap.py). The
    whole-state path is DISPLAY-ONLY and never touches pricing; on any fetch
    failure it falls back to real anchor coverage (never fabricated fill).

    Each cell also carries the requested date's ANCHOR-metro STATE-LEVEL mu_tevi
    (the fused priced index -- the SAME value across every cell). Viewable for
    ANY real state in the config, including an excluded one (e.g. Alaska).
    """
    if not state_exists(state_key):
        raise HTTPException(status_code=404, detail=f"unknown state_key {state_key!r}")
    ctx = get_context(state_key)

    model, ckpt = _load_stgcn(state_key, ctx)
    if model is None:
        raise HTTPException(status_code=503, detail=MODEL_NOT_TRAINED_DETAIL)

    # Whole-state display path: attempt the real full-state fetch + inductive
    # forward. If it can't (fetch failure, or a state too small to hold grid
    # nodes like DC), fall through to the real anchor grid below -- honestly,
    # never with extrapolated fill.
    state_fetch_attempted = False
    if coverage == "state" and date is not None:
        boundary_feat = _load_boundaries().get(state_key)
        if boundary_feat is not None:
            state_fetch_attempted = True
            try:
                state_result = build_state_heatmap(
                    state_key, ctx, model, ckpt, pd.Timestamp(date), boundary_feat)
                if state_result is not None:
                    return state_result
            except BaseException as err:
                logger.warning(f"build_state_heatmap failed for {state_key}: {err}")

    weather_path = ctx.processed("weather.parquet")
    if not weather_path.exists():
        raise HTTPException(status_code=503, detail=MODEL_NOT_TRAINED_DETAIL)

    import torch

    from models.stgcn.train import to_node_time_matrix

    weather = pd.read_parquet(weather_path)
    dates_sorted = sorted(weather["date"].unique())

    # Dates INSIDE the static training window are served from it unchanged --
    # no network, no added latency, byte-identical to before. A date outside
    # it (since v2.8 the picker defaults to today minus NASA POWER's real lag,
    # which every training window predates) is fetched LIVE over the same
    # anchor bbox and run through the same trained weights. The training
    # parquet itself is never modified or extended -- see
    # backend/anchor_weather.py's scope boundary.
    anchor_live_fetched = False
    if date is None:
        target = dates_sorted[-1]
    else:
        target = pd.Timestamp(date)
        if target not in dates_sorted:
            try:
                weather = fetch_anchor_weather_live(state_key, target)
            except SystemExit:
                # MODE A hard-stop inside the real fetch (fatal_abort ->
                # sys.exit) must not kill the API worker, and must never be
                # papered over with stale training data.
                raise HTTPException(
                    status_code=503,
                    detail=f"real weather for {date} could not be fetched from NASA POWER "
                           f"(source unreachable); no substitute data is served",
                ) from None
            anchor_live_fetched = True
            if weather.empty:
                raise HTTPException(
                    status_code=404,
                    detail=f"NASA POWER has no real observations for {date} yet "
                           f"(it publishes with a few days' lag); no data is invented to fill it",
                )
            dates_sorted = sorted(weather["date"].unique())
            if target not in dates_sorted:
                raise HTTPException(
                    status_code=404,
                    detail=f"date {date} is not covered by {state_key}'s real weather data",
                )

    node_order = ckpt["graph"]["node_ids"]
    try:
        # to_node_time_matrix hard-stops (sys.exit) if a real gap survived
        # MODE B rather than fabricating a fill -- honest, but it must not
        # take the worker down on the live path.
        arr, node_ids_current, _coords = to_node_time_matrix(weather)
    except SystemExit:
        raise HTTPException(
            status_code=503,
            detail=f"real weather for {date} has gaps NASA POWER could not fill with "
                   f"observed values; no fabricated fill is served",
        ) from None
    col_index = {nid: i for i, nid in enumerate(node_ids_current)}
    # The live grid can be a strict SUPERSET of the trained node set (v2.9 tile
    # padding), so selecting the checkpoint's own order both drops the extras
    # and keeps the Chebyshev basis aligned. A trained node genuinely absent
    # from the real response is a coverage failure, reported, never guessed.
    if not set(node_order).issubset(col_index):
        raise HTTPException(
            status_code=503,
            detail=f"real weather for {date} is missing "
                   f"{len(set(node_order) - set(col_index))} of {state_key}'s "
                   f"{len(node_order)} trained grid nodes; no interpolated fill is served",
        )
    reorder = [col_index[nid] for nid in node_order]
    arr = arr[:, reorder]

    t_in = ckpt["config"]["t_in"]
    idx = dates_sorted.index(target)
    if idx < t_in:
        raise HTTPException(
            status_code=400,
            detail=f"insufficient real history before {target.date()} "
                   f"(need {t_in} prior days on disk)",
        )

    mu, sigma = ckpt["norm"]["mu"], ckpt["norm"]["sigma"]
    window = arr[idx - t_in:idx]
    x = torch.from_numpy(((window - mu) / sigma)[None, :, :, None].astype(np.float32))
    basis = torch.from_numpy(ckpt["graph"]["cheb_basis"]).float()
    with torch.no_grad():
        pred = model(x, basis).numpy()[0]  # (N, horizon)
    heat_index = pred[:, 0] * sigma + mu    # first horizon day == `target`

    mu_tevi_value = None
    mu_tevi_path = ctx.processed("mu_tevi.parquet")
    if mu_tevi_path.exists():
        state_index = pd.read_parquet(mu_tevi_path)
        row = state_index[state_index["ts"] == target]
        if not row.empty:
            mu_tevi_value = float(row["mu_tevi"].iloc[0])

    frame = None
    contract_path = ctx.artifact("contract.json")
    if contract_path.exists():
        frame = json.loads(contract_path.read_text())["frame"]

    target_weather = weather[weather["date"] == target].set_index("node_id") if "date" in weather.columns else pd.DataFrame()
    t2m_dict = target_weather["T2M"].to_dict() if "T2M" in target_weather.columns else {}
    rh2m_dict = target_weather["RH2M"].to_dict() if "RH2M" in target_weather.columns else {}

    coords = ckpt["graph"]["coords"]
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(coords[i][1]), float(coords[i][0])]},
            "properties": {
                "node_id": nid,
                "heat_index": float(heat_index[i]),
                "temperature": float(t2m_dict[nid]) if nid in t2m_dict and pd.notna(t2m_dict[nid]) else None,
                "humidity": float(rh2m_dict[nid]) if nid in rh2m_dict and pd.notna(rh2m_dict[nid]) else None,
                "mu_tevi": mu_tevi_value,
            },
        }
        for i, nid in enumerate(node_order)
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "state_key": state_key,
            "state": ctx.wage.get("state", state_key),
            "date": str(target.date()),
            "frame": frame,
            # "anchor" = the trained anchor-metro grid. If a whole-state fetch was
            # requested but couldn't be served (fetch failure, or a state too
            # small to contain grid nodes), this is the honest real-anchor
            # fallback -- flagged so the UI says so, never silently extrapolated.
            "coverage": "anchor",
            "whole_state_available": not state_fetch_attempted,
            # True when this date fell outside the static TRAINING window and
            # its weather was fetched live from NASA POWER for display (the
            # training parquet is unchanged either way).
            "anchor_live_fetched": anchor_live_fetched,
            "note": "heat_index is the per-node STGCN street-level heat forecast (shade-WBGT, "
                    "degC), one real value per grid cell -- it VARIES by node. mu_tevi is this "
                    "state's single state-level fused index for this date and is intentionally "
                    "IDENTICAL across every cell -- there is one contract trigger for the whole "
                    "state, not a per-node one.",
        },
    }


# --- /state-boundary --------------------------------------------------------


@app.get("/state-boundary")
def state_boundary(state_key: str):
    """Return state_key's REAL admin-1 boundary as a raw GeoJSON Feature
    (Polygon or MultiPolygon, whichever the Natural Earth source is).

    Reuses the exact same committed boundary file resolve_state reads
    (data/raw/geo/admin1_in_us.geojson) -- no new or derived boundary source.
    The frontend uses this only to CLIP and OUTLINE the heat overlay to the
    state's true irregular shape; it is a cartographic boundary, never an
    input to pricing.
    """
    feat = _load_boundaries().get(state_key)
    if feat is None:
        raise HTTPException(
            status_code=404,
            detail=f"no boundary polygon on file for state_key {state_key!r}",
        )
    return feat


# --- /forecast (Prompt 8, legacy single-city artifact) ----------------------


def _load_forecaster():
    """Lazily loads the trained GRU forecaster checkpoint. (None, None) if untrained."""
    if "model" in _forecaster_cache:
        return _forecaster_cache["model"], _forecaster_cache["ckpt"]
    if not os.path.exists(FORECASTER_PATH):
        return None, None

    import torch

    from models.forecast.model import GRUForecaster

    # FORECASTER_PATH is a fixed, server-authored constant (never derived
    # from any request parameter); see the identical rationale on the
    # STGCN torch.load above, and SECURITY.md.
    ckpt = torch.load(FORECASTER_PATH, map_location="cpu", weights_only=False)  # nosec B614
    cfg = ckpt["config"]
    model = GRUForecaster(input_size=cfg["input_size"], hidden=cfg["hidden"], horizon=cfg["horizon"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    _forecaster_cache["model"] = model
    _forecaster_cache["ckpt"] = ckpt
    return model, ckpt


@app.get("/forecast")
def forecast(horizon_days: int = 7):
    """GRU forecast of the (legacy single-city) mu-TEVI index, `horizon_days`
    ahead of the most recent real day on disk. Surfaces the training-time
    validation comparison against a persistence baseline (Prompt 8's honesty
    requirement) on every call, not just at training time.
    """
    model, ckpt = _load_forecaster()
    if model is None:
        raise HTTPException(status_code=503, detail=MODEL_NOT_TRAINED_DETAIL)

    max_horizon = ckpt["config"]["horizon"]
    if not 1 <= horizon_days <= max_horizon:
        raise HTTPException(
            status_code=400,
            detail=f"horizon_days must be in [1, {max_horizon}] (forecaster trained to {max_horizon}d)",
        )

    import torch

    mu, sigma = ckpt["norm"]["mu"], ckpt["norm"]["sigma"]
    last_window = np.asarray(ckpt["last_window"], dtype=np.float32)
    x = torch.from_numpy(((last_window - mu) / sigma)[None, :, None].astype(np.float32))
    with torch.no_grad():
        pred_norm = model(x).numpy()[0]  # (horizon,)
    pred = pred_norm * sigma + mu

    last_date = pd.Timestamp(ckpt["last_date"])
    metrics = ckpt["metrics"]
    return {
        "as_of": last_date.date().isoformat(),
        "horizon_days": horizon_days,
        "forecast": [
            {
                "days_ahead": h + 1,
                "ts": (last_date + pd.Timedelta(days=h + 1)).date().isoformat(),
                "mu_tevi": float(pred[h]),
            }
            for h in range(horizon_days)
        ],
        "validation": {
            "model_mae": metrics["model_mae"],
            "persistence_mae": metrics["persistence_mae"],
            "beats_persistence": metrics["beats_persistence"],
            "note": "GRU forecaster's chronological hold-out MAE vs a persistence "
                    "(tomorrow=today) baseline, reported honestly whichever wins -- "
                    "see models/forecast/train.py.",
        },
    }


# --- /flag-anomaly (Prompt 8, legacy single-city artifact) ------------------


def _load_anomaly_detector():
    """Lazily loads the trained IsolationForest claim-anomaly detector. None if untrained."""
    if "detector" in _anomaly_cache:
        return _anomaly_cache["detector"]
    if not os.path.exists(ANOMALY_PATH):
        return None

    import pickle

    # ANOMALY_PATH is a fixed, server-authored constant (never derived from
    # any request parameter), so this never deserializes attacker-controlled
    # input. See SECURITY.md.
    with open(ANOMALY_PATH, "rb") as f:
        detector = pickle.load(f)  # nosec B301
    _anomaly_cache["detector"] = detector
    return detector


class FlagAnomalyRequest(BaseModel):
    heat_index: float
    occupation: str
    claimed_payout: float
    days_since_last_claim: Optional[float] = None


class FlagAnomalyResponse(BaseModel):
    is_anomalous: bool
    anomaly_score: float


@app.post("/flag-anomaly", response_model=FlagAnomalyResponse)
def flag_anomaly(req: FlagAnomalyRequest):
    """Score a single claim's feature vector against the trained Isolation
    Forest (top 1% most anomalous flagged, see models/anomaly/detector.py).
    """
    detector = _load_anomaly_detector()
    if detector is None:
        raise HTTPException(status_code=503, detail=MODEL_NOT_TRAINED_DETAIL)

    row = pd.DataFrame([{
        "heat_index": req.heat_index,
        "occupation": req.occupation,
        "claimed_payout": req.claimed_payout,
        "days_since_last_claim": (
            req.days_since_last_claim if req.days_since_last_claim is not None else float("nan")
        ),
    }])
    is_anomalous = bool(detector.predict(row)[0])
    anomaly_score = float(detector.score(row)[0])
    return FlagAnomalyResponse(is_anomalous=is_anomalous, anomaly_score=anomaly_score)


# -----------------------------------------------------------------------------
# PARAMETRIC INSURANCE & AUTOPAY API ENDPOINTS
# -----------------------------------------------------------------------------

@app.get("/api/parametric/stats")
def get_parametric_stats(
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
    x_role: Optional[str] = Header(None, alias="X-Role")
):
    email_filter = x_user_email if x_role == "group_manager" else None
    return parametric.get_overall_stats(email_filter)

@app.get("/api/parametric/cohorts")
def list_cohorts(
    x_user_email: Optional[str] = Header(None),
    x_role: Optional[str] = Header(None)
):
    print(f"DEBUG: x_user_email={x_user_email}, x_role={x_role}")
    email_filter = x_user_email
    return parametric.get_all_cohorts(email_filter)

@app.get("/api/parametric/cohorts/{cohort_id}")
def get_cohort(cohort_id: str):
    cohort = parametric.get_cohort_by_id(cohort_id)
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    return cohort

@app.post("/api/parametric/cohorts", dependencies=[Depends(auth.require_role(["group_manager"]))])
def create_cohort(data: parametric.CohortCreate):
    return parametric.create_cohort(data)

@app.get("/api/parametric/cohorts/{cohort_id}/workers")
def list_workers(cohort_id: str):
    return parametric.get_workers_by_cohort(cohort_id)

@app.post("/api/parametric/workers")
def register_worker(data: parametric.WorkerCreate):
    return parametric.register_worker(data)

@app.get("/api/parametric/policy-templates")
def list_policy_templates():
    return parametric.get_policy_templates()

@app.post("/api/parametric/policy-templates", dependencies=[Depends(auth.require_role(["insurance_provider"]))])
def create_policy_template(data: parametric.PolicyTemplateCreate):
    return parametric.create_policy_template(data)

@app.post("/api/parametric/buy-policy", dependencies=[Depends(auth.require_role(["group_manager"]))])
def buy_policy(data: parametric.BuyPolicyRequest):
    return parametric.buy_policy(data)

@app.get("/api/parametric/cohorts/{cohort_id}/active-policies")
def list_cohort_active_policies(cohort_id: str):
    return parametric.get_active_policies_for_cohort(cohort_id)

@app.get("/api/parametric/active-policies")
def list_all_active_policies(
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
    x_role: Optional[str] = Header(None, alias="X-Role")
):
    email_filter = x_user_email if x_role == "group_manager" else None
    return parametric.get_all_active_policies(email_filter)

@app.post("/api/parametric/trigger-simulation")
def trigger_simulation(data: parametric.TriggerSimulateRequest):
    return parametric.trigger_payout_simulation(data)

@app.get("/api/parametric/payout-events")
def list_payout_events(
    cohort_id: Optional[str] = None,
    x_user_email: Optional[str] = Header(None, alias="X-User-Email"),
    x_role: Optional[str] = Header(None, alias="X-Role")
):
    email_filter = x_user_email if x_role == "group_manager" else None
    return parametric.get_payout_events(cohort_id, email_filter)

@app.post("/api/parametric/payout-events/{event_id}/approve", dependencies=[Depends(auth.require_role(["group_manager"]))])
def approve_payout(event_id: str, req: parametric.ApprovePayoutRequest):
    try:
        return parametric.approve_payout_event(event_id, req.approved_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    # Render (and most free-tier PaaS hosts) assign the listen port at
    # runtime via $PORT and reject a hardcoded one -- default 8000 keeps
    # `python -m backend.main` and local Docker runs unchanged.
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
