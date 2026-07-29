"""Offline state detection from a real GPS coordinate -- no geocoding API, no
key, no rate limit (Golden Rule 7 / project keyless-source discipline).

Point-in-polygon against REAL Natural Earth admin-1 boundaries (public domain)
for India + the United States, filtered to data/raw/geo/admin1_in_us.geojson
and committed. Bounding boxes are deliberately NOT used: states are not
rectangles, and a bbox misassigns anyone near a border. The polygon is the
legally-correct unit because minimum wages are legislated per state.

resolve_state only answers "which state is this point in"; it never picks a
wage schedule by distance (that is purely the detected state) and never
fabricates anything for a point outside the two supported countries.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from shapely.geometry import shape
from shapely.geometry import Point
from shapely.prepared import prep

GEOJSON_PATH = Path(__file__).parent.parent.parent / "data" / "raw" / "geo" / "admin1_in_us.geojson"

SUPPORTED_COUNTRIES = ("India", "the United States")


@lru_cache(maxsize=1)
def _load_polygons() -> list[dict]:
    """Load and prepare the admin-1 polygons once (cached for the process).

    Returns a list of {country, state, state_key, geom, prepared} dicts.
    """
    data = json.loads(GEOJSON_PATH.read_text())
    polygons = []
    for feat in data["features"]:
        props = feat["properties"]
        geom = shape(feat["geometry"])
        polygons.append({
            "country": props["country"],
            "state": props["state"],
            "state_key": props["state_key"],
            "geom": geom,
            "prepared": prep(geom),   # fast repeated point-in-polygon
        })
    return polygons


def resolve_state(lat: float, lon: float) -> dict:
    """Resolve (lat, lon) to the India/US state whose real boundary contains it.

    Returns {country, state, state_key, mode="detected"} on a hit, or
    {mode="out_of_coverage", message} when the point is outside both supported
    countries. lat/lon are used only for this containment test -- never
    persisted, logged, or used to synthesize data for the raw point.

    Coverage against the priced set (config/wages_by_state.yaml) is a SEPARATE
    concern handled by the caller: a point can land in a real IN/US state that
    is not in the wage config (e.g. an Indian union territory), which is still
    an honest "detected but not priced", never fabricated pricing.
    """
    point = Point(lon, lat)  # shapely is (x=lon, y=lat)
    for poly in _load_polygons():
        if poly["prepared"].contains(point):
            return {
                "country": poly["country"],
                "state": poly["state"],
                "state_key": poly["state_key"],
                "mode": "detected",
            }
    return {
        "mode": "out_of_coverage",
        "message": (
            f"This location is outside the supported countries. Only "
            f"{SUPPORTED_COUNTRIES[0]} and {SUPPORTED_COUNTRIES[1]} are "
            f"currently covered."
        ),
    }
