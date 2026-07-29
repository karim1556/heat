"""Shared data-recovery module implementing CLAUDE.md Golden Rule 5.

This is the ONLY place network calls are made from the data pipeline, and the
ONLY place gap-filling logic lives. Two failure modes:

  MODE A - source unreachable / unparseable after retries -> fatal_abort()
           (never fabricate, never substitute; sys.exit(1)).
  MODE B - a returned cell is null/-999 -> fill_gaps_nearest() fills it with
           the NEAREST REAL OBSERVED value (never mean/random/interpolated).
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, NoReturn

import pandas as pd
import requests

GAP_SENTINEL = -999


def fatal_abort(name: str, url: str, reason: str) -> NoReturn:
    """MODE A: print the FATAL banner verbatim and exit nonzero."""
    message = (
        f"FATAL: real data source {name} unreachable at {url} ({reason}).\n"
        f"No fabricated or synthetic data is permitted. Aborting."
    )
    print(message)
    sys.exit(1)


def fetch_json(
    url: str,
    headers: dict | None = None,
    params: dict | None = None,
    retries: int = 3,
    backoff: float = 1.5,
    name: str | None = None,
) -> dict:
    """The ONLY place network calls happen.

    200 + parseable JSON -> return it. Otherwise, after `retries` attempts
    with exponential backoff, escalate to MODE A via fatal_abort (never
    returns).
    """
    label = name or url
    delay = 1.0
    last_reason = "unknown error"

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException as exc:
            last_reason = f"request error: {exc}"
        else:
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError as exc:
                    last_reason = f"unparseable JSON: {exc}"
            else:
                last_reason = f"HTTP {resp.status_code}"

        if attempt < retries:
            time.sleep(delay)
            delay *= backoff

    fatal_abort(label, url, last_reason)


def fetch_json_cached(
    url: str,
    cache_path: str | Path,
    headers: dict | None = None,
    params: dict | None = None,
    retries: int = 3,
    backoff: float = 1.5,
    name: str | None = None,
) -> dict:
    """Cache-through wrapper around fetch_json.

    If `cache_path` already exists on disk, the cached raw response is
    returned with NO network call (this is what makes `make reproduce`
    deterministic from cached raw responses per CLAUDE.md Golden Rule 10).
    Otherwise a real network call is made via fetch_json, the raw JSON is
    written to `cache_path`, and a `<stem>.meta.json` sidecar is written
    alongside it recording source_url, fetched_at_utc, and query_params.
    """
    cache_path = Path(cache_path)

    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)

    data = fetch_json(
        url, headers=headers, params=params, retries=retries, backoff=backoff,
        name=name or str(cache_path),
    )

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(data, f)

    meta_path = cache_path.parent / f"{cache_path.stem}.meta.json"
    meta = {
        "source_url": url,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "query_params": params or {},
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return data


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def fill_gaps_nearest(
    df: pd.DataFrame,
    value_cols: list[str],
    node_key: str,
    time_key: str,
    coords: dict | None = None,
    max_temporal_gap: int = 7,
    max_spatial_km: float | None = None,
    on_unfillable: Callable = fatal_abort,
) -> tuple[pd.DataFrame, list[dict]]:
    """MODE B: fill null/-999 cells with the nearest REAL observed value.

    Order of preference per gap cell:
      1. Same node, nearest time within `max_temporal_gap` days.
      2. Same time, nearest node within `max_spatial_km` (requires `coords`).
      3. Escalate to `on_unfillable(name, url, reason)` (MODE A by default).

    Never writes a value that was not itself a real observation somewhere in
    `df` (no mean/random/interpolation). Returns (filled_df, proxy_records).
    """
    df = df.copy()
    df[time_key] = pd.to_datetime(df[time_key])
    proxies: list[dict] = []

    for col in value_cols:
        is_gap = df[col].isna() | (df[col] == GAP_SENTINEL)
        valid_mask = ~is_gap
        gap_indices = df.index[is_gap].tolist()

        for idx in gap_indices:
            row = df.loc[idx]
            node = row[node_key]
            t = row[time_key]
            filled = False

            # Step 1: same node, nearest time within max_temporal_gap
            same_node = df[(df[node_key] == node) & valid_mask]
            if not same_node.empty:
                deltas = (same_node[time_key] - t).abs()
                best_pos = deltas.values.argmin()
                best_delta_days = deltas.iloc[best_pos].days
                if best_delta_days <= max_temporal_gap:
                    best_row = same_node.iloc[best_pos]
                    df.at[idx, col] = best_row[col]
                    proxies.append({
                        "column": col,
                        "target_node": node,
                        "target_time": t.isoformat(),
                        "method": "same_node_nearest_time",
                        "source_node": node,
                        "source_time": best_row[time_key].isoformat(),
                        "distance_days": int(best_delta_days),
                        "distance_km": 0.0,
                    })
                    filled = True

            # Step 2: same time, nearest node within max_spatial_km
            if not filled and coords is not None and max_spatial_km is not None:
                same_time = df[(df[time_key] == t) & valid_mask]
                if not same_time.empty and node in coords:
                    best_dist = math.inf
                    best_row = None
                    for _, cand in same_time.iterrows():
                        cand_node = cand[node_key]
                        if cand_node not in coords:
                            continue
                        dist = _haversine_km(coords[node], coords[cand_node])
                        if dist < best_dist:
                            best_dist = dist
                            best_row = cand
                    if best_row is not None and best_dist <= max_spatial_km:
                        df.at[idx, col] = best_row[col]
                        proxies.append({
                            "column": col,
                            "target_node": node,
                            "target_time": t.isoformat(),
                            "method": "same_time_nearest_node",
                            "source_node": best_row[node_key],
                            "source_time": t.isoformat(),
                            "distance_days": 0,
                            "distance_km": round(best_dist, 3),
                        })
                        filled = True

            # Step 3: escalate to MODE A
            if not filled:
                on_unfillable(
                    f"gap-fill:{col}",
                    "",
                    f"no real observation within range for node={node} time={t}",
                )

    return df, proxies
