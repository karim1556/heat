"""Offline tests for city resolution (backend/data/location.py).

Never fabricates weather/wage data for a raw GPS point: a configured hit
resolves to a real configured city; an out-of-coverage point returns an
honest message naming the nearest configured city, never invented numbers.
"""

from __future__ import annotations

from backend.data.location import THRESHOLD_KM, resolve_city

TEST_CITIES_CFG = {
    "cities": {
        "testcity": {"name": "Test City", "lat": 23.0, "lon": 72.5},
    }
}


def test_resolve_city_configured_hit():
    result = resolve_city(23.01, 72.51, TEST_CITIES_CFG)
    assert result["mode"] == "configured"
    assert result["city_key"] == "testcity"
    assert result["city"] == "Test City"
    assert result["distance_km"] < THRESHOLD_KM


def test_resolve_city_out_of_coverage():
    # (0, 0) is ~8000km from (23.0, 72.5) -- clearly out of coverage.
    result = resolve_city(0.0, 0.0, TEST_CITIES_CFG)
    assert result["mode"] == "out_of_coverage"
    assert result["city_key"] == "testcity"
    assert result["distance_km"] > THRESHOLD_KM
    assert "Test City" in result["message"]
    assert str(round(result["distance_km"], 1)) in result["message"] or "km" in result["message"]
    # never a fabricated wage/heat value for the raw point
    assert "wage" not in result
    assert "heat" not in result
    assert "wbgt" not in result


def test_resolve_city_picks_nearest_of_multiple():
    cfg = {
        "cities": {
            "near": {"name": "Near City", "lat": 23.0, "lon": 72.5},
            "far": {"name": "Far City", "lat": 40.0, "lon": 100.0},
        }
    }
    result = resolve_city(23.02, 72.52, cfg)
    assert result["city_key"] == "near"
    assert result["mode"] == "configured"
