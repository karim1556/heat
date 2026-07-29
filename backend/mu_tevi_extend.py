"""Forward application of a state's ALREADY-FITTED models to real weather that
postdates its static mu_tevi.parquet -- so a contract can be priced on real
current dates without refitting anything.

WHAT THIS IS, PRECISELY (read before editing -- this is the highest-risk
boundary in the project):

  FORWARD APPLICATION ONLY. Every parameter used here is READ from an existing
  committed artifact and applied unchanged:
    * kappa, gamma   <- models/artifacts/<state>/calibration.json
    * tau            <- the FIXED convention tau = 0.10 * wage
                        (calibration.TAU_WAGE_FRACTION; recorded in
                        copula.json as tau_convention so downstream cannot
                        forget kappa/gamma are conditional on it)
    * theta          <- copula.json
    * GEV params     <- copula.json
    * hurdle marginal<- copula.json (p0, positive_dist, positive_params)
  NOTHING here fits, refits, re-estimates or re-selects any of them. There is
  no optimizer, no .fit() call, and no contract sweep in this module. The
  contract (strike/window/frame) is likewise applied by the caller exactly as
  committed.

WHY IT USES OBSERVED WEATHER, NOT THE STGCN FORECAST: the mu-TEVI chain is
built on REAL OBSERVED shade-WBGT, not on STGCN output. Verified in source --
models/behavioral_agent/calibration.py and models/fusion/tevi.py both take
their heat from models.stgcn.train.load_weather(), i.e. the observed NASA
POWER parquet. The STGCN drives the heat MAP; it is not an input to mu-TEVI.
Substituting a forecast here would feed the calibrated marginals a different
quantity than the one they were fitted on, so this module applies the same
functions to the same kind of input: observed WBGT from the same anchor bbox.

FAITHFULNESS IS PROVEN, NOT ASSUMED: recomputing the full historical series
with this exact chain reproduces the committed mu_tevi.parquet bit-identically
(max abs diff 0.0 over all 3652 rows, verified for IN-Gujarat, US-Texas and
US-District of Columbia). That equality is what licenses applying it forward.

THE STATIC ARTIFACT IS NEVER TOUCHED: extended values go to a separate,
gitignored, on-demand cache (mu_tevi_extended_cache.parquet). The original
mu_tevi.parquet's byte-identity is the proof this module changed nothing.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from backend.anchor_weather import fetch_anchor_weather_live
from backend.state_context import get_context

# The three occupations pooled equal-weight into the node-day portfolio,
# matching models/fusion/tevi.py's node_day aggregation.
OCCUPATIONS = ("vendor", "construction", "delivery")

EXTENDED_CACHE_NAME = "mu_tevi_extended_cache.parquet"


def _load_frozen_models(ctx):
    """Rebuild the fitted objects from committed JSON -- the same
    reconstruction LSMCPricer.from_copula_json already relies on."""
    from models.fusion.gumbel_copula import GumbelSurvivalCopula
    from models.fusion.marginals import HurdleMarginal
    from models.fusion.tevi import TEVICalculator

    cop = json.loads(ctx.artifact("copula.json").read_text())
    gev = cop["gev_params"]
    calc = TEVICalculator(
        (gev["c"], gev["loc"], gev["scale"]),
        HurdleMarginal.from_dict(cop["hurdle"]),
        GumbelSurvivalCopula(cop["theta"]),
    )
    calibration = json.loads(ctx.artifact("calibration.json").read_text())
    return calc, calibration


def mu_tevi_from_weather(state_key: str, weather: pd.DataFrame) -> pd.DataFrame:
    """(node_id, ts, wbgt_c) of REAL observed weather -> daily (ts, mu_tevi).

    This is models/fusion/tevi.py's node_day pipeline applied with frozen
    parameters: cited-zero atom restored at the cited threshold, three
    occupations equal-weighted per node-day, the trigger taken as the CITY
    daily max (a spatial block maximum, not the node's own heat), and the
    daily index as the mean over nodes.
    """
    from models.behavioral_agent.calibration import TAU_WAGE_FRACTION, simulated_loss
    from models.fusion.marginals import CITED_ZERO_THRESHOLD_C

    ctx = get_context(state_key)
    calc, calibration = _load_frozen_models(ctx)
    wages = ctx.daily_wages()

    frames = []
    for occupation in OCCUPATIONS:
        params = calibration[occupation]
        wage = float(wages[occupation])
        # APPLY the calibrated (kappa, gamma) at the fixed tau convention.
        fraction = simulated_loss(
            weather["wbgt_c"].to_numpy(), params["kappa"], params["gamma"],
            wage, TAU_WAGE_FRACTION * wage,
        )
        frames.append(pd.DataFrame({
            "node_id": weather["node_id"].to_numpy(),
            "ts": weather["ts"].to_numpy(),
            "wbgt_c": weather["wbgt_c"].to_numpy(),
            "wage_loss_fraction": fraction,
        }))
    merged = pd.concat(frames, ignore_index=True)

    # Structural correction 1: restore the cited-zero atom the logit smeared.
    merged["loss_hurdle"] = np.where(
        merged["wbgt_c"] <= CITED_ZERO_THRESHOLD_C, 0.0, merged["wage_loss_fraction"])
    node_day = merged.groupby(["node_id", "ts"], as_index=False).agg(
        loss_hurdle=("loss_hurdle", "mean"))

    # Structural correction 2: the trigger is the CITY daily max, not own-node heat.
    city_index = weather.groupby("ts", as_index=False).wbgt_c.max().rename(
        columns={"wbgt_c": "heat_index"})
    node_day = node_day.merge(city_index, on="ts", how="left")

    node_day["mu_tevi"] = calc.node_day_index(
        node_day["heat_index"].to_numpy(), node_day["loss_hurdle"].to_numpy())
    return (node_day.groupby("ts", as_index=False)["mu_tevi"].mean()
            .sort_values("ts").reset_index(drop=True))


def extend_mu_tevi(state_key: str, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> pd.DataFrame:
    """Real (ts, mu_tevi) for [start_ts, end_ts] BEYOND the static parquet.

    Returns only dates strictly after the static artifact's last real day.
    Raises SystemExit on a MODE A hard-stop inside the real fetch; returns
    fewer rows than requested if NASA POWER genuinely has no data yet --
    never pads, interpolates or reuses a neighbouring day's value.
    """
    ctx = get_context(state_key)
    static = pd.read_parquet(ctx.processed("mu_tevi.parquet"))
    last_static = pd.Timestamp(static["ts"].max())

    gap_start = max(pd.Timestamp(start_ts), last_static + pd.Timedelta(days=1))
    gap_end = pd.Timestamp(end_ts)
    if gap_end < gap_start:
        return pd.DataFrame(columns=["ts", "mu_tevi"])

    cache_path = ctx.processed(EXTENDED_CACHE_NAME)
    cached = pd.read_parquet(cache_path) if cache_path.exists() else None
    if cached is not None:
        have = cached[(cached["ts"] >= gap_start) & (cached["ts"] <= gap_end)]
        if len(have) == (gap_end - gap_start).days + 1:
            return have.sort_values("ts").reset_index(drop=True)

    # Fetch over a box derived from the TRAINED node coordinates, not
    # ctx.bbox: the calibrated index is a max/mean over exactly those grid
    # points, and for IN-Gujarat later config edits moved ctx.bbox off 3 of
    # its 15 trained nodes. Padding half a grid step guarantees the boundary
    # centres are returned; any extra nodes are filtered out below.
    trained = pd.read_parquet(ctx.processed("weather.parquet")).drop_duplicates("node_id")
    trained_nodes = set(trained["node_id"].unique())
    pad = 0.25
    trained_bbox = {
        "lat_min": float(trained["lat"].min()) - pad,
        "lat_max": float(trained["lat"].max()) + pad,
        "lon_min": float(trained["lon"].min()) - pad,
        "lon_max": float(trained["lon"].max()) + pad,
    }

    # Real fetch of OBSERVED weather, reusing v2.10's loader (MODE A/B
    # enforced inside it, unchanged).
    history_days = max(int((gap_end - gap_start).days), 1)
    weather = fetch_anchor_weather_live(
        state_key, gap_end, history_days=history_days, bbox=trained_bbox)
    if weather.empty:
        return pd.DataFrame(columns=["ts", "mu_tevi"])

    weather = weather.rename(columns={"date": "ts"})[["node_id", "ts", "wbgt_c"]]

    # The calibrated marginals were fitted over the TRAINING node set, and the
    # trigger is a max over exactly those nodes. The live grid can be a strict
    # superset (v2.9 tile padding), so restrict to the trained nodes -- an
    # extra node would silently move the city max and the node-day mean.
    weather = weather[weather["node_id"].isin(trained_nodes)]
    missing = trained_nodes - set(weather["node_id"].unique())
    if missing:
        raise ValueError(
            f"{state_key}: real weather is missing {len(missing)} of "
            f"{len(trained_nodes)} trained grid nodes; refusing to compute a "
            f"mu-TEVI over a different node set than the one calibrated")

    daily = mu_tevi_from_weather(state_key, weather)
    fresh = daily[(daily["ts"] >= gap_start) & (daily["ts"] <= gap_end)].reset_index(drop=True)

    # Persist to the SEPARATE on-demand cache. mu_tevi.parquet is never
    # written here -- that file is the calibrated artifact.
    if not fresh.empty:
        combined = fresh if cached is None else pd.concat([cached, fresh], ignore_index=True)
        combined = (combined.drop_duplicates(subset="ts", keep="last")
                    .sort_values("ts").reset_index(drop=True))
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(cache_path, index=False)
    return fresh
