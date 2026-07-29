"""Resolve a user's real GPS coordinate to a configured city -- never
fabricate data for an arbitrary point.

Wages and the weather grid both come from a REAL configured city (its NASA
POWER bbox, its cited wage schedule). A raw lat/lon is only ever used to find
the nearest configured city; if no configured city is close enough, we say so
honestly (mode="out_of_coverage") instead of inventing anything.
"""

from __future__ import annotations

import math

THRESHOLD_KM = 150.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def resolve_city(lat: float, lon: float, cities_cfg: dict, threshold_km: float = THRESHOLD_KM) -> dict:
    """Return the nearest configured city to (lat, lon).

    {city, city_key, distance_km, mode} where mode is "configured" if
    distance_km <= threshold_km, else "out_of_coverage". lat/lon are used
    transiently for this distance computation only -- never persisted, never
    logged, never used to synthesize weather/wage data for the raw point.
    """
    cities = cities_cfg["cities"]

    best_key = None
    best_dist = math.inf
    for city_key, city in cities.items():
        dist = _haversine_km(lat, lon, city["lat"], city["lon"])
        if dist < best_dist:
            best_dist = dist
            best_key = city_key

    best_city = cities[best_key]
    mode = "configured" if best_dist <= threshold_km else "out_of_coverage"

    result = {
        "city_key": best_key,
        "city": best_city["name"],
        "distance_km": round(best_dist, 2),
        "mode": mode,
    }

    if mode == "out_of_coverage":
        result["message"] = (
            f"This location is not yet covered. Nearest configured city is "
            f"{best_city['name']}, {round(best_dist, 1)} km away."
        )

    return result
