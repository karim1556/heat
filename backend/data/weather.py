"""NASA POWER weather loader (keyless, no fixed rate limit).

Host: power.larc.nasa.gov ONLY. NEVER api.nasa.gov (that host requires a key
and is capped at 1000 req/hr). All network access is routed through
backend.data.recovery so Golden Rule 5 (MODE A / MODE B) is enforced in one
place.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from backend.data.recovery import fetch_json_cached, fill_gaps_nearest

POWER_HOST = "power.larc.nasa.gov"
REGIONAL_URL = f"https://{POWER_HOST}/api/temporal/daily/regional"

# NASA POWER regional API hard limits (verified against the live API):
# a single call must span < 366 days and >= 2 degrees in both lat and lon.
MAX_DAYS_PER_CALL = 366
MIN_DEGREES_PER_TILE = 2.0
# Every individual tile actually sent to NASA POWER must clear this floor, not
# the bare 2.0 minimum: padding to EXACTLY 2.0 still underflows after
# double-precision arithmetic -- IN-Kerala's anchor bbox once measured
# 1.9999999999999991deg at nominal-2.0 padding and got a real HTTP 422 (fixed
# in config/state_anchors.yaml, commit 31311dc, by widening to +/-1.005deg).
# The same class of failure applies to any tile computed at request time (a
# small state's real border bbox, e.g. Massachusetts at 1.63deg latitude
# span -- confirmed live, v2.8 session), so the margin is enforced once here,
# at the shared tiling point, rather than re-padded per caller.
NASA_POWER_MIN_TILE_DEG = MIN_DEGREES_PER_TILE + 0.01

# NASA POWER's daily processing lag, live-verified 2026-07-24 against the real
# point API (Ahmedabad): T2M/RH2M were real through today-3d and -999
# (no-data) for the 3 most recent days. Used only as the DEFAULT `end` for
# callers that don't pass one explicitly -- a request for a date that turns
# out not to be real yet still goes through MODE B (nearest-real fill) or
# MODE A (hard-stop) exactly as any other gap would, so this is a sane
# default, not a promise the API can't keep.
NASA_POWER_LAG_DAYS = 3

PARAMETERS = ("T2M", "RH2M")


def default_end_date() -> str:
    """Most recent date NASA POWER will realistically have real data for."""
    return (date.today() - timedelta(days=NASA_POWER_LAG_DAYS)).strftime("%Y%m%d")


def _date_chunks(start: str, end: str, max_days: int = MAX_DAYS_PER_CALL) -> list[tuple[str, str]]:
    start_dt = pd.to_datetime(start, format="%Y%m%d")
    end_dt = pd.to_datetime(end, format="%Y%m%d")
    chunks = []
    cur = start_dt
    while cur <= end_dt:
        chunk_end = min(cur + pd.Timedelta(days=max_days - 1), end_dt)
        chunks.append((cur.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
        cur = chunk_end + pd.Timedelta(days=1)
    return chunks


def _pad_to_min_span(vmin: float, vmax: float, floor: float = NASA_POWER_MIN_TILE_DEG) -> tuple[float, float]:
    """Widen [vmin, vmax] symmetrically about its own center up to `floor`.

    A no-op whenever the span already clears the floor, so this can be applied
    unconditionally to every tile without changing any tile that was already
    valid.
    """
    span = vmax - vmin
    if span >= floor:
        return vmin, vmax
    pad = (floor - span) / 2.0
    return vmin - pad, vmax + pad


def _spatial_tiles(bbox: dict, tile_deg: float = MIN_DEGREES_PER_TILE) -> list[dict]:
    lat_min, lat_max = bbox["lat_min"], bbox["lat_max"]
    lon_min, lon_max = bbox["lon_min"], bbox["lon_max"]

    if (lat_max - lat_min) <= tile_deg and (lon_max - lon_min) <= tile_deg:
        lat_min, lat_max = _pad_to_min_span(lat_min, lat_max)
        lon_min, lon_max = _pad_to_min_span(lon_min, lon_max)
        return [dict(lat_min=lat_min, lat_max=lat_max, lon_min=lon_min, lon_max=lon_max)]

    tiles = []
    lat = lat_min
    while lat < lat_max:
        lat_top = min(lat + tile_deg, lat_max)
        if lat_top - lat < tile_deg:
            lat = max(lat_max - tile_deg, lat_min)
            lat_top = lat_max
        lon = lon_min
        while lon < lon_max:
            lon_right = min(lon + tile_deg, lon_max)
            if lon_right - lon < tile_deg:
                lon = max(lon_max - tile_deg, lon_min)
                lon_right = lon_max
            tile_lat_min, tile_lat_max = _pad_to_min_span(lat, lat_top)
            tile_lon_min, tile_lon_max = _pad_to_min_span(lon, lon_right)
            tiles.append(dict(lat_min=tile_lat_min, lat_max=tile_lat_max,
                               lon_min=tile_lon_min, lon_max=tile_lon_max))
            if lon_right >= lon_max:
                break
            lon = lon_right
        if lat_top >= lat_max:
            break
        lat = lat_top
    return tiles


def _node_id(lat: float, lon: float) -> str:
    return f"{lat:.4f}_{lon:.4f}"


def parse_regional_response(data: dict, parameter: str) -> list[dict]:
    """Reshape one NASA POWER regional JSON response into node/day rows."""
    rows = []
    for feature in data.get("features", []):
        lon, lat = feature["geometry"]["coordinates"][:2]
        series = feature.get("properties", {}).get("parameter", {}).get(parameter, {})
        for date_str, value in series.items():
            rows.append({
                "node_id": _node_id(lat, lon),
                "lat": lat,
                "lon": lon,
                "date": date_str,
                parameter: value,
            })
    return rows


class WeatherLoader:
    def __init__(self, bbox: dict, cache_dir: str | Path = "data/raw"):
        self.bbox = bbox
        self.cache_dir = Path(cache_dir)

    def fetch_daily(
        self, start: str = "20140101", end: str | None = None,
        tile_deg: float = MIN_DEGREES_PER_TILE,
    ) -> pd.DataFrame:
        """Fetch T2M and RH2M separately (regional = one parameter/call),
        tiling over both time (<366-day chunks) and space (tiles of `tile_deg`),
        merged on (node_id, date). -999 cells are left as MODE B gaps for
        fill_gaps() to resolve.

        `tile_deg` is the spatial tile size. It defaults to the 2deg regional-API
        MINIMUM span (used by the training pipeline's single-anchor fetches). The
        whole-state display path (backend/state_heatmap.py) passes a LARGER tile
        (5deg -> ~80 grid points, safely under the API's 100-point-per-call cap
        and above the 2deg floor) so a big state needs far fewer requests -- same
        regional endpoint and tiling function, just a different valid tile size,
        not new fetch semantics.

        `end` defaults to `default_end_date()` (today minus the live-verified
        NASA POWER processing lag) rather than a fixed date, so every caller
        that doesn't pass its own `end` naturally tracks real current data.
        """
        end = end or default_end_date()
        tiles = _spatial_tiles(self.bbox, tile_deg)
        chunks = _date_chunks(start, end)

        param_frames: dict[str, pd.DataFrame] = {}
        for parameter in PARAMETERS:
            rows: list[dict] = []
            for tile in tiles:
                for chunk_start, chunk_end in chunks:
                    cache_name = (
                        f"nasa_power_{parameter}_"
                        f"{tile['lat_min']:.2f}_{tile['lat_max']:.2f}_"
                        f"{tile['lon_min']:.2f}_{tile['lon_max']:.2f}_"
                        f"{chunk_start}_{chunk_end}.json"
                    )
                    cache_path = self.cache_dir / cache_name
                    params = {
                        "parameters": parameter,
                        "community": "AG",
                        "longitude-min": tile["lon_min"],
                        "longitude-max": tile["lon_max"],
                        "latitude-min": tile["lat_min"],
                        "latitude-max": tile["lat_max"],
                        "start": chunk_start,
                        "end": chunk_end,
                        "format": "json",
                    }
                    data = fetch_json_cached(
                        REGIONAL_URL, cache_path, params=params,
                        name=f"NASA POWER regional ({parameter})",
                    )
                    rows.extend(parse_regional_response(data, parameter))
            df = pd.DataFrame(rows)
            if not df.empty:
                df = df.drop_duplicates(subset=["node_id", "date"])
            param_frames[parameter] = df

        # NASA POWER answers 200 with ZERO features for a window it has no data
        # for at all (e.g. entirely in the future) -- distinct from a MODE B
        # -999 cell inside a window it does cover. Report that as an empty
        # frame; the caller decides how to degrade honestly. (Left unguarded
        # this raised a bare KeyError on the merge below -- unreachable from the
        # training path, which only ever fetches real past windows, but
        # reachable from the display path's live fetch.)
        if any(frame.empty for frame in param_frames.values()):
            return pd.DataFrame(columns=["node_id", "lat", "lon", "date", *PARAMETERS])

        merged = param_frames[PARAMETERS[0]]
        for parameter in PARAMETERS[1:]:
            merged = merged.merge(
                param_frames[parameter][["node_id", "date", parameter]],
                on=["node_id", "date"], how="outer",
            )
        # lat/lon may be missing on rows only present via the outer-merged
        # parameter frame; node_id itself is the source of truth for both.
        missing_coords = merged["lat"].isna() | merged["lon"].isna()
        if missing_coords.any():
            parsed = merged.loc[missing_coords, "node_id"].str.split("_", expand=True)
            merged.loc[missing_coords, "lat"] = parsed[0].astype(float)
            merged.loc[missing_coords, "lon"] = parsed[1].astype(float)
        merged["date"] = pd.to_datetime(merged["date"], format="%Y%m%d")
        return merged.sort_values(["node_id", "date"]).reset_index(drop=True)

    def fill_gaps(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
        coords = {
            row["node_id"]: (row["lat"], row["lon"])
            for _, row in df.drop_duplicates("node_id").iterrows()
        }
        return fill_gaps_nearest(
            df,
            value_cols=list(PARAMETERS),
            node_key="node_id",
            time_key="date",
            coords=coords,
            max_temporal_gap=7,
        )

    @staticmethod
    def to_heat_index(df: pd.DataFrame) -> pd.Series:
        """NOAA/NWS Rothfusz regression heat index, in Fahrenheit.

        Reference: https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
        """
        t_f = df["T2M"] * 9.0 / 5.0 + 32.0
        rh = df["RH2M"]

        hi_simple = 0.5 * (t_f + 61.0 + ((t_f - 68.0) * 1.2) + (rh * 0.094))
        avg = (hi_simple + t_f) / 2.0

        hi_full = (
            -42.379 + 2.04901523 * t_f + 10.14333127 * rh
            - 0.22475541 * t_f * rh - 6.83783e-3 * t_f**2
            - 5.481717e-2 * rh**2 + 1.22874e-3 * t_f**2 * rh
            + 8.5282e-4 * t_f * rh**2 - 1.99648e-6 * t_f**2 * rh**2
        )

        low_rh_mask = (rh < 13) & (t_f >= 80) & (t_f <= 112)
        low_rh_adj = ((13 - rh) / 4.0) * ((17 - (t_f - 95).abs()) / 17.0).clip(lower=0) ** 0.5
        hi_full = hi_full.where(~low_rh_mask, hi_full - low_rh_adj)

        high_rh_mask = (rh > 85) & (t_f >= 80) & (t_f <= 87)
        high_rh_adj = ((rh - 85.0) / 10.0) * ((87.0 - t_f) / 5.0)
        hi_full = hi_full.where(~high_rh_mask, hi_full + high_rh_adj)

        return hi_simple.where(avg < 80.0, hi_full)

    @staticmethod
    def to_wbgt_approx(df: pd.DataFrame) -> pd.Series:
        """Shade-WBGT approximation (Australian Bureau of Meteorology method).

        WBGT_shade = 0.567*Ta + 0.393*e + 3.94, where e is water-vapor
        pressure (hPa) from Ta (C) and relative humidity.

        LABEL: this OMITS the solar/globe-temperature term, so it approximates
        outdoor WBGT in shade only, not full-sun WBGT. Upgrade path: add
        ALLSKY_SFC_SW_DWN from the same NASA POWER API to compute full WBGT
        with a solar-globe term.
        Reference: http://www.bom.gov.au/info/thermal_stress/
        """
        t_c = df["T2M"]
        rh = df["RH2M"]
        e = (rh / 100.0) * 6.105 * np.exp(17.27 * t_c / (237.7 + t_c))
        return 0.567 * t_c + 0.393 * e + 3.94
