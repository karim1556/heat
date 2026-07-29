"""Live NASA POWER fetch over ONE state's ANCHOR bbox, for DISPLAY-time
inference at dates OUTSIDE the static training window.

WHY THIS EXISTS (read the scope boundary before editing): every state's
trained STGCN, mu-TEVI, copula, contract and premium were fit on the static
data/processed/<state>/weather.parquet, whose date range is that state's
original training fetch window (~2014-2023). That parquet is the TRAINING
record and is NEVER modified, extended or re-fetched by this module -- doing
so would silently change what the priced artifacts were calibrated on.

What this module does instead is the INFERENCE-time counterpart: when the map
asks for a date the static parquet doesn't cover (since v2.8 the date picker
defaults to today minus NASA POWER's real ~3-day lag, which is far outside
every training window), it fetches that date's REAL weather over the SAME
anchor bbox and hands it back for a forward pass through the SAME trained
stgcn.pt with the SAME normalization stats. Dates INSIDE the training window
never reach this module -- they keep reading the static parquet, unchanged and
with no added latency.

This is the same live-fetch pattern v2.7/v2.8 established for whole-state
coverage (backend/state_heatmap.py), applied to the anchor grid. It is
factored out as an importable function rather than inlined in the /heatmap
route so later callers reuse it instead of duplicating fetch logic a third
time.

TILING MUST MATCH TRAINING: fetch_daily is called at its DEFAULT tile_deg --
the same value the training pipeline used -- so the returned grid covers the
node set the checkpoint was trained on. A larger tile would be ~4x faster
(one request pair instead of four) but returns a DIFFERENT, smaller node set
for some states (measured: IN-Goa 12 nodes at tile_deg=5 vs 15 at the 2deg
default), which would leave trained nodes unfetched. Callers must still
select the checkpoint's own node order out of the result: the v2.9 tile
padding means the live set can be a strict SUPERSET of the trained one (Goa
again: 15 live vs 12 trained). Overlapping cells were verified identical
between the two tilings (max abs diff 0.0 on both T2M and RH2M).

FETCH FAILURE IS HONEST, NEVER FABRICATED (Golden Rule 5): MODE A raises
SystemExit out of backend.data.recovery and MODE B fills gaps with nearest
REAL observations only. Neither is caught here -- the caller degrades
honestly rather than substituting stale or synthetic data.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from backend.data.weather import WeatherLoader
from backend.state_context import get_context

# On-demand display cache, kept OUT of data/raw/ itself so it never pollutes
# the committed training-data provenance sidecars there (data/raw/* is
# gitignored except *.meta.json). Mirrors v2.7's data/raw/state_cache.
ANCHOR_CACHE_DIR = "data/raw/anchor_cache"
# Days of real history fetched before the target so the STGCN's t_in window
# (12) is real and gap-free, with margin for MODE B. Matches the whole-state
# path's HISTORY_DAYS.
ANCHOR_HISTORY_DAYS = 30

TARGET_COL = "wbgt_c"  # matches models.stgcn.train.to_node_time_matrix


def fetch_anchor_weather_live(
    state_key: str,
    target_date,
    history_days: int = ANCHOR_HISTORY_DAYS,
    bbox: dict | None = None,
) -> pd.DataFrame:
    """Real NASA POWER weather over state_key's anchor bbox, ending at
    target_date, with wbgt_c computed -- the same schema the static training
    parquet has, so callers can treat the two interchangeably.

    `bbox` overrides the state's configured anchor bbox. Needed because one
    state's committed training grid was fetched with a bbox that later config
    edits moved (IN-Gujarat: 3 of its 15 trained nodes now sit outside
    ctx.bbox), so a caller that must reproduce the TRAINED node set passes a
    box derived from those nodes instead. Defaults to ctx.bbox, leaving the
    heat-map path's behaviour unchanged.

    Raises SystemExit on a MODE A hard-stop (unreachable source); the caller
    is responsible for degrading honestly rather than serving stale data.
    """
    ctx = get_context(state_key)
    bbox = bbox if bbox is not None else ctx.bbox
    target = pd.Timestamp(target_date)
    start = (target - timedelta(days=history_days)).strftime("%Y%m%d")
    end = target.strftime("%Y%m%d")

    loader = WeatherLoader(bbox=bbox, cache_dir=ANCHOR_CACHE_DIR)
    # DEFAULT tile_deg on purpose -- see the module docstring's tiling note.
    raw = loader.fetch_daily(start=start, end=end)
    if raw.empty:
        # NASA POWER has no data at all for this window (e.g. a date past the
        # real observation lag). Hand back the empty frame untouched -- gap
        # filling an empty series would invent every value in it.
        return raw
    filled, _proxies = loader.fill_gaps(raw)
    return filled.assign(**{TARGET_COL: loader.to_wbgt_approx(filled)})
