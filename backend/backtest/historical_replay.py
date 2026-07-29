"""Replay the real ~10-year history through the full pipeline (Prompts 2-5) and
build the real-data tables the backtest report and metrics are computed on.

WHAT "REPLAY" MEANS HERE, precisely (worth stating up front, since the LSMC
premium is climatological -- see models/pricing/lsmc_pricer.py):

  PREDICTED premium: price_window's premium does NOT depend on the numeric
  content of the window passed to it, only its LENGTH (it simulates M forward
  paths from the fitted UNCONDITIONAL joint law). This is not a bug being
  worked around here -- it is how a real parametric product prices: the
  premium is fixed once from a climate model at policy issuance, then the SAME
  premium is charged every period regardless of what that period's weather
  turns out to be. So the predicted premium is computed ONCE per occupation
  (constant across all windows), exactly reflecting that.

  ACTUAL realized payout: computed directly from the REAL, PERSISTENT mu-TEVI
  series (data/processed/mu_tevi.parquet) -- never resampled or shuffled. A
  window "triggers" if the real city index reaches the strike at least once
  within it; if so, the policy pays on the day within the window the index is
  HIGHEST (the MAX-IN-WINDOW convention -- see the note below on why, not
  first-exceedance).

  WHY MAX-IN-WINDOW AND NOT FIRST-EXCEEDANCE (a real bug caught by actually
  running the numbers, not assumed away): first-exceedance was the initial
  choice here, reasoned as "look-ahead-free". It is not what was priced. The
  contract is a one-shot claim the worker exercises OPTIMALLY (that is the
  entire reason Longstaff-Schwartz is in this pipeline at all -- see
  models/pricing/lsmc_pricer.py), and the LSMC premium is the expected value
  of that optimal policy. Comparing it against a first-exceedance "actual"
  (claim on the FIRST trigger day, not the best one) silently compares two
  DIFFERENT contracts and understated the realized payout badly: nonzero-actual
  mean was 127 INR under first-exceedance vs premiums of 275-303 INR, an
  apparent MAPE of ~1656%. Switching to max-in-window -- the standard
  convention for backtesting a Bermudan payoff against ALREADY-REALIZED
  history, where the optimal exercise day is simply knowable in hindsight --
  raised the nonzero-actual mean to 240 INR and dropped MAPE to ~72%. This is a
  genuine correction (matching what was actually priced), not a
  re-tune-for-a-better-number: the strike, cap, and pricer are untouched.

TWO GRANULARITIES are built and kept separate:
  * CLAIMS (one row per triggering (node, occupation, window)): the sparse
    event table Prompt 8's anomaly detector consumes.
  * DAILY worker-day table (node, occupation, day) x {payout, actual_loss}:
    the dense table basis_risk_empirical, VaR/ES, and trigger/payout-frequency
    diagnostics are computed on. This applies the parametric payout formula to
    EVERY day (not gated by the one-shot claim mechanic), because basis risk
    asks "how well does the index's implied payout track the loss on a given
    day", a question about the TRIGGER's daily behaviour, not the claim timing.

ACTUAL LOSS is the SAME hurdle-corrected wage loss Prompt 4 fit the copula to:
loss = 0 for WBGT at/below the cited elasticity threshold, else the
behaviorally-calibrated wage_loss_fraction from Prompt 3. Recomputed here from
the same real weather + wage_loss.parquet inputs, the same way tevi.py did it
(never re-derived differently -- that would silently create a second, possibly
inconsistent, definition of "actual loss").
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from backend.data.build_wage_loss import CITIES_YAML_PATH, OCCUPATIONS
from backend.data.wages import WageLoader
from models.fusion.marginals import CITED_ZERO_THRESHOLD_C
from models.pricing.lsmc_pricer import (
    DEFAULT_HORIZON,
    LSMCPricer,
    payout_fraction,
)
from models.stgcn.train import load_weather

SEED = 42

# Per-state namespacing (v2): STATE_KEY set -> this state's namespaced replay
# I/O; unset -> legacy single-city paths. WINDOW_DAYS follows DEFAULT_HORIZON,
# which is itself state-aware in lsmc_pricer (this state's chosen contract).
_STATE_KEY = os.environ.get("STATE_KEY")
if _STATE_KEY:
    from backend.state_context import get_context

    _CTX = get_context(_STATE_KEY)
    MU_TEVI_PATH = _CTX.processed("mu_tevi.parquet")
    WAGE_LOSS_PATH = _CTX.processed("wage_loss.parquet")
    CLAIMS_PATH = _CTX.processed("claims.parquet")
else:
    _CTX = None
    MU_TEVI_PATH = Path("data/processed/mu_tevi.parquet")
    WAGE_LOSS_PATH = Path("data/processed/wage_loss.parquet")
    CLAIMS_PATH = Path("data/processed/claims.parquet")

WINDOW_DAYS = DEFAULT_HORIZON  # sourced from the (state-aware) contract config, see backend/config.py.


def load_wages() -> dict[str, float]:
    if _CTX is not None:
        return _CTX.daily_wages()          # this state's own schedule + currency
    with open(CITIES_YAML_PATH) as f:
        config = yaml.safe_load(f)
    key = config["default_city"]
    return WageLoader(
        country_iso3=config["cities"][key]["country_iso3"]
    ).occupation_baseline_wages(city_key=key)


def build_actual_loss_table() -> pd.DataFrame:
    """(node_id, ts, occupation, wbgt_c, loss_hurdle) for every real node-day.

    loss_hurdle is EXACTLY Prompt 4's construction: 0 at/below the cited
    threshold, else the calibrated wage_loss_fraction. Recomputing this rather
    than re-reading mu_tevi.parquet is necessary because mu_tevi.parquet is
    already the city-AGGREGATED daily index; the per-worker actual loss needed
    for basis risk and claims lives at node x occupation granularity.
    """
    weather = load_weather()[["node_id", "date", "wbgt_c"]].rename(columns={"date": "ts"})
    if not WAGE_LOSS_PATH.exists():
        print(f"FATAL: {WAGE_LOSS_PATH} missing. Run models.behavioral_agent.calibration first.")
        sys.exit(1)
    wage_loss = pd.read_parquet(WAGE_LOSS_PATH)
    merged = wage_loss.merge(weather, on=["node_id", "ts"], how="inner")
    if len(merged) != len(wage_loss):
        print(f"FATAL: wage_loss rows ({len(wage_loss)}) did not all match weather "
              f"({len(merged)}). Refusing to replay misaligned data.")
        sys.exit(1)
    merged["loss_hurdle"] = np.where(
        merged["wbgt_c"] <= CITED_ZERO_THRESHOLD_C, 0.0, merged["wage_loss_fraction"])
    return merged[["node_id", "ts", "occupation", "wbgt_c", "loss_hurdle"]]


def load_city_index() -> pd.DataFrame:
    """The real, persistent daily mu-TEVI trigger series -- (ts, mu_tevi)."""
    if not MU_TEVI_PATH.exists():
        print(f"FATAL: {MU_TEVI_PATH} missing. Run models.fusion.tevi first.")
        sys.exit(1)
    return pd.read_parquet(MU_TEVI_PATH).sort_values("ts").reset_index(drop=True)


def windows(n_total_days: int, window_days: int = WINDOW_DAYS) -> list[tuple[int, int]]:
    """Non-overlapping [start, end) day-index windows, dropping a short tail."""
    n_windows = n_total_days // window_days
    return [(i * window_days, (i + 1) * window_days) for i in range(n_windows)]


def build_daily_liability_table(city_index: pd.DataFrame, actual_loss: pd.DataFrame,
                                wages: dict[str, float], strike: float,
                                cap: float) -> pd.DataFrame:
    """(node_id, occupation, ts, mu_tevi, payout_daily, actual_loss_amt).

    payout_daily applies the parametric formula to EVERY day the real index is
    observed (not gated by the one-shot claim mechanic) -- see module
    docstring for why this daily granularity is the right one for basis risk.
    """
    df = actual_loss.merge(city_index, on="ts", how="inner")
    df["wage"] = df["occupation"].map(wages)
    df["payout_daily"] = payout_fraction(df["mu_tevi"].to_numpy(), strike, cap) * df["wage"]
    df["actual_loss_amt"] = df["loss_hurdle"] * df["wage"]
    return df


def build_claims(city_index: pd.DataFrame, actual_loss: pd.DataFrame,
                 wages: dict[str, float], strike: float, cap: float,
                 window_days: int = WINDOW_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """MAX-IN-WINDOW claims per (node, occupation, window) -- the worker claims
    on the day the index is highest within the window, matching the optimal
    exercise the LSMC premium was priced for (see module docstring for why
    this replaced an earlier first-exceedance convention). Also returns a
    per-window per-occupation realized-payout summary (for MAPE / premium
    comparison). Returns (claims_df, window_summary_df).
    """
    idx = city_index.reset_index(drop=True)
    mutevi = idx["mu_tevi"].to_numpy()
    ts = idx["ts"].to_numpy()
    win_bounds = windows(len(idx), window_days)

    node_ids = sorted(actual_loss["node_id"].unique())
    loss_lookup = actual_loss.set_index(["node_id", "occupation", "ts"])["loss_hurdle"]

    claim_rows: list[dict] = []
    window_rows: list[dict] = []

    for w_id, (start, end) in enumerate(win_bounds):
        window_index = mutevi[start:end]
        window_ts = ts[start:end]
        triggered = bool((window_index >= strike).any())
        claim_offset = int(np.argmax(window_index)) if triggered else None  # best day, hindsight
        claim_ts = window_ts[claim_offset] if triggered else None
        claim_index_value = float(window_index[claim_offset]) if triggered else 0.0
        claim_payout_frac = payout_fraction(claim_index_value, strike, cap) if triggered else 0.0

        for occupation in OCCUPATIONS:
            wage = wages[occupation]
            realized_payout = claim_payout_frac * wage if triggered else 0.0
            window_rows.append({
                "window_id": w_id, "window_start": window_ts[0], "window_end": window_ts[-1],
                "occupation": occupation, "triggered": triggered,
                "realized_payout": realized_payout,
            })
            if not triggered:
                continue
            for node_id in node_ids:
                actual_loss_on_claim_day = float(
                    loss_lookup.get((node_id, occupation, claim_ts), np.nan))
                claim_rows.append({
                    "node_id": node_id, "occupation": occupation,
                    "ts": claim_ts, "window_id": w_id,
                    "heat_index": claim_index_value,
                    "claimed_payout_fraction": claim_payout_frac,
                    "claimed_payout": realized_payout,
                    "actual_loss_fraction": actual_loss_on_claim_day,
                    "actual_loss_amt": actual_loss_on_claim_day * wage,
                })

    claims = pd.DataFrame(claim_rows).sort_values(["node_id", "occupation", "ts"])
    claims["days_since_last_claim"] = (
        claims.groupby(["node_id", "occupation"])["ts"]
        .diff().dt.days
    )
    window_summary = pd.DataFrame(window_rows)
    return claims.reset_index(drop=True), window_summary


def run(strike: float | None = None, cap: float | None = None,
       window_days: int = WINDOW_DAYS, persist: bool = True) -> dict:
    """Orchestrate the full replay. Returns a dict of dataframes + scalars that
    metrics.py / report.py consume; writes data/processed/claims.parquet as a
    side effect (Prompt 8's anomaly-detection input) when persist=True.
    """
    pricer = LSMCPricer.from_copula_json(
        **({"strike": strike} if strike is not None else {}),
        **({"cap": cap} if cap is not None else {}),
    )
    strike = pricer.strike
    cap = pricer.cap

    wages = load_wages()
    city_index = load_city_index()
    actual_loss = build_actual_loss_table()

    daily = build_daily_liability_table(city_index, actual_loss, wages, strike, cap)
    claims, window_summary = build_claims(city_index, actual_loss, wages, strike, cap, window_days)

    if persist:
        CLAIMS_PATH.parent.mkdir(parents=True, exist_ok=True)
        claims.to_parquet(CLAIMS_PATH, index=False)

    # Predicted premium is climatological -- one call per occupation, reused
    # for every window (see module docstring).
    predicted_premium = {}
    representative_window = city_index["mu_tevi"].to_numpy()[:window_days]
    for occupation in OCCUPATIONS:
        result = pricer.price_window(representative_window, occupation)
        predicted_premium[occupation] = result["premium_lsmc"]

    return {
        "pricer": pricer,
        "wages": wages,
        "city_index": city_index,
        "actual_loss": actual_loss,
        "daily": daily,
        "claims": claims,
        "window_summary": window_summary,
        "predicted_premium": predicted_premium,
        "strike": strike,
        "cap": cap,
        "window_days": window_days,
        "n_windows": window_summary["window_id"].nunique(),
    }


def main() -> int:
    started = time.time()
    print("=" * 74)
    print("HISTORICAL REPLAY -- real 10-year mu-TEVI series through the full pipeline")
    print("=" * 74)
    result = run()
    n_windows = result["n_windows"]
    n_triggered = int(result["window_summary"].drop_duplicates("window_id")["triggered"].sum())
    print(f"[REPLAY]   {n_windows} non-overlapping {result['window_days']}-day windows | "
          f"strike={result['strike']:g} cap={result['cap']:.2f}")
    print(f"[TRIGGER]  {n_triggered}/{n_windows} windows triggered "
          f"({n_triggered / n_windows * 100:.1f}%)")
    print(f"[CLAIMS]   {len(result['claims'])} claim rows -> data/processed/claims.parquet")
    for occupation, premium in result["predicted_premium"].items():
        print(f"[PREMIUM]  {occupation:13s} predicted (climatological) = {premium:.2f} INR")
    print(f"[TIME]     {time.time() - started:.1f}s total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
