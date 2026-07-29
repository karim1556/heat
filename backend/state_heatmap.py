"""Whole-state heat surface: real fetched NASA POWER weather over a state's
FULL border bbox, run through that state's EXISTING trained STGCN inductively.

WHY THIS IS A DISPLAY-ONLY PATH (read the scope boundary before editing): every
state's mu-TEVI, copula, contract, backtest and premium were trained and
calibrated on the ~2deg anchor-metro grid (config/state_anchors.yaml). That
2deg box was a COMPUTE scoping choice for the training batch, not a data limit
-- NASA POWER is global and keyless, so real weather for the whole state is
fetchable. This module renders the whole-state real forecast for the MAP ONLY;
it never recomputes or touches any pricing artifact. The priced index stays the
anchor-metro one it was calibrated on.

HONEST TRANSFER LABEL: the STGCN was TRAINED on the anchor-metro grid and is
applied here INDUCTIVELY to a wider real grid. Its Chebyshev weights are shape
(K, C_in, C_out) with no node dimension (verified in the checkpoint), so a
forward pass over a larger graph is valid without retraining -- the same
node-count-agnostic property the spatial hold-out already exercised. This is a
legitimate, standard use of an inductive graph model, but it IS a transfer, and
the API response records it as one (metadata.inductive_transfer).

ON DEMAND, NOT PRECOMPUTED: measured, full-range whole-state weather for all 79
states would be ~246MB (vs the current 69MB deploy_artifacts), a 4.6x image
bloat, so it is fetched per (state, date) through the existing NASA POWER disk
cache instead. tile_deg=5 keeps this cheap: ~2-9 tiles/state, seconds cold,
instant once cached.

FETCH FAILURE IS HONEST, NEVER FABRICATED (Golden Rule 5): if the real fetch
fails for any reason -- including a MODE A abort, which raises SystemExit -- this
returns None and the caller falls back to the state's real ANCHOR coverage with
an honest caption. The uncovered area is never filled by extrapolation.
"""

from __future__ import annotations

import json
from datetime import timedelta

import numpy as np
import pandas as pd
from shapely.geometry import Point, shape

from backend.data.weather import WeatherLoader
from backend.state_context import StateContext
from models.stgcn.city_graph import CityGraphBuilder

# 5deg x 5deg tile = ~80 NASA POWER grid points, safely under the regional API's
# 100-point-per-call cap and above its 2deg minimum span. Bigger tiles => far
# fewer requests for a large state (Texas: 9 tiles, not 42).
WHOLE_STATE_TILE_DEG = 5.0
# Days of history fetched before the target so the STGCN's t_in window is real
# and gap-free (t_in is 12; 30 gives comfortable margin).
HISTORY_DAYS = 30
# The whole-state display cache is on-demand and regenerable -- kept in its own
# subdir so it stays gitignored (data/raw/* ignores it) and never pollutes the
# committed training-data provenance sidecars in data/raw/ itself.
STATE_CACHE_DIR = "data/raw/state_cache"
# Need at least this many in-polygon grid nodes to build a graph and serve a
# genuine whole-state surface. A state smaller than a few 0.5deg cells (e.g. DC,
# which contains ZERO grid points) can't -- it honestly keeps anchor coverage.
MIN_INSIDE_NODES = 5

TARGET_COL = "wbgt_c"  # matches models.stgcn.train.to_node_time_matrix


def _bbox_of(boundary_feat: dict) -> dict:
    xmin, ymin, xmax, ymax = shape(boundary_feat["geometry"]).bounds
    return {"lat_min": ymin, "lat_max": ymax, "lon_min": xmin, "lon_max": xmax}


def build_state_heatmap(
    state_key: str,
    ctx: StateContext,
    model,
    ckpt: dict,
    target: pd.Timestamp,
    boundary_feat: dict,
) -> dict | None:
    """Return a whole-state /heatmap GeoJSON, or None to signal the caller to
    fall back to real anchor coverage (fetch failed, or the state is too small
    to contain grid nodes). Never fabricates for the uncovered area.
    """
    try:
        return _build(state_key, ctx, model, ckpt, target, boundary_feat)
    except SystemExit:
        # A MODE A abort inside the real fetch (fatal_abort -> sys.exit) must NOT
        # kill the API worker; degrade to anchor coverage honestly.
        return None
    except Exception:
        return None


def _build(
    state_key: str,
    ctx: StateContext,
    model,
    ckpt: dict,
    target: pd.Timestamp,
    boundary_feat: dict,
) -> dict | None:
    import torch

    from models.stgcn.train import to_node_time_matrix

    poly = shape(boundary_feat["geometry"])
    bbox = _bbox_of(boundary_feat)

    # Real fetch over the FULL state bbox, reusing WeatherLoader's tiling / retry
    # / MODE A hard-stop / MODE B nearest-real gap-fill exactly as the training
    # pipeline does -- only the tile size differs (5deg, valid for the API).
    start = (target - timedelta(days=HISTORY_DAYS)).strftime("%Y%m%d")
    end = target.strftime("%Y%m%d")
    loader = WeatherLoader(bbox=bbox, cache_dir=STATE_CACHE_DIR)
    raw = loader.fetch_daily(start=start, end=end, tile_deg=WHOLE_STATE_TILE_DEG)
    filled, _proxies = loader.fill_gaps(raw)
    filled = filled.assign(**{TARGET_COL: loader.to_wbgt_approx(filled)})

    # Drop grid nodes OUTSIDE the real border BEFORE building anything, so the
    # served node set is genuinely the state's own (Part 2.4).
    node_coords = filled.drop_duplicates("node_id")[["node_id", "lat", "lon"]]
    inside_ids = {
        row.node_id
        for row in node_coords.itertuples(index=False)
        if poly.contains(Point(row.lon, row.lat))
    }
    if len(inside_ids) < MIN_INSIDE_NODES:
        return None  # too small for a whole-state grid -> caller uses anchor
    filled = filled[filled["node_id"].isin(inside_ids)].reset_index(drop=True)

    arr, node_ids, coords = to_node_time_matrix(filled)
    dates_sorted = sorted(filled["date"].unique())
    if pd.Timestamp(target) not in dates_sorted:
        return None
    idx = dates_sorted.index(pd.Timestamp(target))
    t_in = int(ckpt["config"]["t_in"])
    if idx < t_in:
        return None

    # Whole-state graph: SAME CityGraphBuilder (geographic kNN, normalized
    # Laplacian, Chebyshev basis) as training, just over more nodes. The basis is
    # (K, N', N') for this graph; the model's learned weights are node-count
    # agnostic, so the forward pass is valid.
    graph = CityGraphBuilder(coords, k=int(ckpt["config"]["knn_k"])).build(
        k_order=int(ckpt["config"]["k_order"])
    )

    # Reuse the checkpoint's stored normalization (anchor train-time mu/sigma) --
    # do NOT refit on the wider area; refitting would be a different model.
    mu, sigma = ckpt["norm"]["mu"], ckpt["norm"]["sigma"]
    window = arr[idx - t_in:idx]
    x = torch.from_numpy(((window - mu) / sigma)[None, :, :, None].astype(np.float32))
    basis = torch.from_numpy(graph.cheb_basis).float()
    with torch.no_grad():
        pred = model(x, basis).numpy()[0]  # (N', horizon)
    heat_index = pred[:, 0] * sigma + mu   # first horizon day == target

    # mu_tevi and frame come from the ANCHOR-calibrated artifacts, unchanged --
    # the priced index covers the anchor extent, deliberately different from the
    # whole-state heat surface (the UI says so).
    mu_tevi_value = None
    mu_tevi_path = ctx.processed("mu_tevi.parquet")
    if mu_tevi_path.exists():
        state_index = pd.read_parquet(mu_tevi_path)
        row = state_index[state_index["ts"] == pd.Timestamp(target)]
        if not row.empty:
            mu_tevi_value = float(row["mu_tevi"].iloc[0])

    frame = None
    contract_path = ctx.artifact("contract.json")
    if contract_path.exists():
        frame = json.loads(contract_path.read_text())["frame"]

    target_df = filled[filled["date"] == pd.Timestamp(target)].set_index("node_id")
    t2m_dict = target_df["T2M"].to_dict() if "T2M" in target_df.columns else {}
    rh2m_dict = target_df["RH2M"].to_dict() if "RH2M" in target_df.columns else {}

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(coords.iloc[i]["lon"]),
                                                          float(coords.iloc[i]["lat"])]},
            "properties": {
                "node_id": nid,
                "heat_index": float(heat_index[i]),
                "temperature": float(t2m_dict[nid]) if nid in t2m_dict and pd.notna(t2m_dict[nid]) else None,
                "humidity": float(rh2m_dict[nid]) if nid in rh2m_dict and pd.notna(rh2m_dict[nid]) else None,
                "mu_tevi": mu_tevi_value,
            },
        }
        for i, nid in enumerate(node_ids)
    ]
    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "state_key": state_key,
            "state": ctx.wage.get("state", state_key),
            "date": str(pd.Timestamp(target).date()),
            "frame": frame,
            "coverage": "state",
            "inductive_transfer": True,
            "n_nodes": len(node_ids),
            "note": "heat_index is the real full-state STGCN shade-WBGT forecast, one value per "
                    "NASA POWER grid node inside the state's real border. The STGCN was TRAINED on "
                    "the anchor-metro grid and applied INDUCTIVELY to this wider real grid (a "
                    "legitimate transfer, recorded as one). mu_tevi -- the priced index -- comes "
                    "from the anchor-metro grid the model was calibrated on, so it covers a "
                    "different, deliberately narrower extent than this map.",
        },
    }
