"""Offline API tests (v2 state-wise rewrite): must pass with NO trained
artifacts on disk (CI has neither per-state artifacts nor the legacy
single-city ones -- models/artifacts/* is gitignored, see .gitignore).

config/wages_by_state.yaml and config/state_anchors.yaml (the real 79-state
config) ARE tracked in git, so state detection / listing / honest-503 paths
are exercised against the REAL config directly. Only the full pricing path
(which needs a real copula.json fit) is monkeypatched via a stub pricer +
a synthetic state injected into backend.state_context, so the response
schema is asserted without requiring `make train-all-states` to have run.
Coordinates travel ONLY in POST bodies, never a query string
(location-privacy rule) -- verified explicitly below.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import backend.main as main_module
import backend.state_context as state_context
from backend.main import app

client = TestClient(app)

# Real, tracked config (see config/state_anchors.yaml) -- no artifacts required.
PHOENIX_LAT, PHOENIX_LON = 33.45, -112.07  # inside US-Arizona
# Far from any real state polygon (mid-Atlantic / mid-Pacific type point).
OUT_OF_COVERAGE_LAT, OUT_OF_COVERAGE_LON = 0.0, 0.0


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_states_lists_real_79_state_config():
    resp = client.get("/states")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 79
    by_key = {row["state_key"]: row for row in data}
    assert "US-Arizona" in by_key and "US-Alaska" in by_key
    assert by_key["US-Arizona"]["currency"] == "USD"
    assert by_key["US-Alaska"]["country"] == "US"
    for row in data:
        assert row["mode"] in {"configured", "excluded", "unpriced"}


def test_simulate_policy_malformed_body_returns_422():
    resp = client.post("/simulate-policy", json={"occupation": "vendor"})  # missing date_range
    assert resp.status_code == 422


def test_simulate_policy_requires_state_key_or_coords():
    resp = client.post("/simulate-policy", json={
        "occupation": "vendor",
        "date_range": {"start": "2020-01-01", "end": "2020-01-14"},
    })
    assert resp.status_code == 400


def test_simulate_policy_unknown_state_key_is_400():
    resp = client.post("/simulate-policy", json={
        "state_key": "XX-Nowhere",
        "occupation": "vendor",
        "date_range": {"start": "2020-01-01", "end": "2020-01-14"},
    })
    assert resp.status_code == 400


def test_heatmap_unknown_state_key_is_404():
    resp = client.get("/heatmap", params={"state_key": "XX-Nowhere"})
    assert resp.status_code == 404


def test_heatmap_without_trained_model_returns_503(monkeypatch, tmp_path):
    # US-Arizona is real, tracked config. Its artifacts are gitignored, so a
    # clean checkout has none -- but THIS machine may have real local
    # artifacts from a prior training run, so redirect ARTIFACTS_ROOT to an
    # empty tmp dir to make the 503 path deterministic either way.
    monkeypatch.setattr(state_context, "ARTIFACTS_ROOT", tmp_path)
    main_module._stgcn_cache.clear()
    resp = client.get("/heatmap", params={"state_key": "US-Arizona"})
    assert resp.status_code == 503
    assert "not trained" in resp.json()["detail"]


def _boundary_vertex_count(feat: dict) -> int:
    g = feat["geometry"]
    c = g["coordinates"]
    if g["type"] == "Polygon":
        return sum(len(ring) for ring in c)
    if g["type"] == "MultiPolygon":
        return sum(len(ring) for poly in c for ring in poly)
    return 0


def test_state_boundary_returns_real_polygon_gujarat():
    resp = client.get("/state-boundary", params={"state_key": "IN-Gujarat"})
    assert resp.status_code == 200
    feat = resp.json()
    assert feat["type"] == "Feature"
    assert feat["geometry"]["type"] in {"Polygon", "MultiPolygon"}
    assert feat["properties"]["state_key"] == "IN-Gujarat"
    # Non-degenerate: a real state border, not an empty/point shape.
    assert _boundary_vertex_count(feat) > 10


def test_state_boundary_returns_real_polygon_arizona():
    resp = client.get("/state-boundary", params={"state_key": "US-Arizona"})
    assert resp.status_code == 200
    feat = resp.json()
    assert feat["geometry"]["type"] in {"Polygon", "MultiPolygon"}
    assert _boundary_vertex_count(feat) > 10


def test_state_boundary_unknown_state_key_is_404():
    resp = client.get("/state-boundary", params={"state_key": "XX-Nowhere"})
    assert resp.status_code == 404


def test_resolve_location_happy_path_detects_real_state():
    resp = client.post("/resolve-location", json={"lat": PHOENIX_LAT, "lon": PHOENIX_LON})
    assert resp.status_code == 200
    data = resp.json()
    assert data["state_key"] == "US-Arizona"
    assert data["country"] == "US"
    assert data["currency"] == "USD"
    # Arizona's real pipeline artifacts are gitignored, so contract.json is
    # absent in a clean checkout -- this is the honest "not yet trained" leg,
    # never a fabricated "configured".
    assert data["mode"] in {"configured", "out_of_coverage"}


def test_resolve_location_out_of_coverage_is_honest():
    resp = client.post("/resolve-location", json={"lat": OUT_OF_COVERAGE_LAT, "lon": OUT_OF_COVERAGE_LON})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "out_of_coverage"
    assert data["message"] is not None
    assert data["state_key"] is None


def test_resolve_location_rejects_query_string_coords():
    """lat/lon MUST be POST body fields; supplying them only as a query string
    leaves the (required) body empty -> 422, never silently used."""
    resp = client.post(f"/resolve-location?lat={PHOENIX_LAT}&lon={PHOENIX_LON}")
    assert resp.status_code == 422


class _StubPricer:
    def __init__(self, strike: float = 75.0, cap: float = 0.9):
        self.strike = strike
        self.cap = cap

    @classmethod
    def from_copula_json(cls, path=None, strike: float = 75.0, cap: float = 0.9):
        return cls(strike=strike, cap=cap)

    def price_window(self, window_values, occupation, wage=None):
        return {
            "premium_lsmc": 42.0,
            "premium_wang": 55.0,
            "payout_schedule": {
                "form": "cap * (mu_tevi - strike)_+ / (100 - strike)",
                "strike": self.strike, "cap": self.cap, "trigger_frequency": 0.2,
            },
            "basis_risk": {
                "basis_risk_rmse": 12.3, "shortfall_rate": 0.25,
                "overpay_rate": 0.10, "correlation": 0.6,
            },
        }


@pytest.fixture
def stub_state(monkeypatch, tmp_path):
    """Injects a fully-synthetic, fully-trained 'TEST-State' into
    backend.state_context (patching its module-level config caches + roots),
    with a real-shaped contract.json + mu_tevi.parquet on disk and a stubbed
    LSMCPricer -- so /simulate-policy prices end-to-end without any real
    copula.json fit (CI has none)."""
    fake_wages = {
        "TEST-State": {
            "country": "US", "state": "Test State", "currency": "USD",
            "wages_daily": {"vendor": 100.0, "delivery": 100.0, "construction": 120.0},
            "confidence": "high", "verified": False,
            "source_url": "https://example.gov/wage", "note": "test fixture, not real",
        }
    }
    fake_anchors = {
        "TEST-State": {
            "metro": "Testville", "lat": 10.0, "lon": 20.0,
            "bbox": {"lat_min": 9.0, "lat_max": 11.0, "lon_min": 19.0, "lon_max": 21.0},
            "reason": "test fixture",
        }
    }
    monkeypatch.setattr(state_context, "_wages", lambda: fake_wages)
    monkeypatch.setattr(state_context, "_anchors", lambda: fake_anchors)
    monkeypatch.setattr(state_context, "ARTIFACTS_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(state_context, "PROCESSED_ROOT", tmp_path / "processed")
    monkeypatch.setattr(main_module, "LSMCPricer", _StubPricer)

    ctx = state_context.get_context("TEST-State")
    ctx.ensure_dirs()
    ctx.artifact("contract.json").write_text(json.dumps({
        "strike": 75.0, "window_days": 14, "frame": "income_smoothing", "cap": 0.9,
    }))
    ctx.artifact("copula.json").write_text("{}")  # unread: LSMCPricer is stubbed

    dates = pd.date_range("2020-01-01", periods=30, freq="D")
    pd.DataFrame({"ts": dates, "mu_tevi": [60.0 + i for i in range(30)]}).to_parquet(
        ctx.processed("mu_tevi.parquet"))
    return ctx


def test_simulate_policy_schema_by_state_key(stub_state):
    resp = client.post("/simulate-policy", json={
        "state_key": "TEST-State",
        "occupation": "vendor",
        "date_range": {"start": "2020-01-01", "end": "2020-01-14"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["coverage_mode"] == "configured"
    assert data["frame"] == "income_smoothing"
    assert data["currency"] == "USD"
    assert data["state_key"] == "TEST-State"
    assert data["premium_lsmc"] == 42.0
    assert data["premium_wang"] == 55.0
    br = data["basis_risk"]
    assert {"basis_risk_rmse", "shortfall_rate", "overpay_rate", "correlation"} == set(br)
    wp = data["wage_provenance"]
    assert wp["currency"] == "USD"
    assert wp["value"] == 100.0
    assert wp["source_url"] == "https://example.gov/wage"
    assert "effective_date" not in wp
    assert "policy_id" in data and data["policy_id"]


def test_simulate_policy_unknown_occupation_is_400(stub_state):
    resp = client.post("/simulate-policy", json={
        "state_key": "TEST-State",
        "occupation": "astronaut",
        "date_range": {"start": "2020-01-01", "end": "2020-01-14"},
    })
    assert resp.status_code == 400


def test_simulate_policy_excluded_state_is_honest_not_fabricated(monkeypatch, tmp_path):
    fake_wages = {"TEST-Excluded": {
        "country": "US", "state": "Excluded State", "currency": "USD",
        "wages_daily": {"vendor": 100.0}, "confidence": "high", "verified": False,
        "source_url": None, "note": None,
    }}
    fake_anchors = {"TEST-Excluded": {
        "metro": "Nowhereville", "lat": 0.0, "lon": 0.0,
        "bbox": {"lat_min": -1.0, "lat_max": 1.0, "lon_min": -1.0, "lon_max": 1.0}, "reason": "test",
    }}
    monkeypatch.setattr(state_context, "_wages", lambda: fake_wages)
    monkeypatch.setattr(state_context, "_anchors", lambda: fake_anchors)
    monkeypatch.setattr(state_context, "ARTIFACTS_ROOT", tmp_path / "artifacts")
    monkeypatch.setattr(state_context, "PROCESSED_ROOT", tmp_path / "processed")

    ctx = state_context.get_context("TEST-Excluded")
    ctx.ensure_dirs()
    ctx.artifact("excluded.json").write_text(json.dumps({
        "excluded": True, "state_key": "TEST-Excluded",
        "reason": "insufficient heat-exposure days: 5 < 30 minimum",
    }))

    resp = client.post("/simulate-policy", json={
        "state_key": "TEST-Excluded",
        "occupation": "vendor",
        "date_range": {"start": "2020-01-01", "end": "2020-01-14"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["coverage_mode"] == "excluded"
    assert data["premium_lsmc"] is None
    assert data["basis_risk"] is None
    assert "insufficient heat-exposure days" in data["message"]
    assert "not fabricated" in data["note"].lower() or "no data" in data["note"].lower()


def test_simulate_policy_out_of_coverage_via_coords_is_honest(stub_state):
    resp = client.post("/simulate-policy", json={
        "occupation": "vendor",
        "date_range": {"start": "2020-01-01", "end": "2020-01-14"},
        "lat": OUT_OF_COVERAGE_LAT, "lon": OUT_OF_COVERAGE_LON,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["coverage_mode"] == "out_of_coverage"
    assert data["premium_lsmc"] is None
    assert data["message"] is not None
    assert "not fabricated" in data["note"].lower() or "no data" in data["note"].lower()


def test_simulate_policy_ignores_lat_lon_in_query_string(stub_state):
    """Coordinates in the query string must be silently ignored -- only body
    fields are read at all, so a query-string lat/lon can't smuggle in an
    unvalidated location; the request must supply state_key or a body lat/lon."""
    resp = client.post(
        f"/simulate-policy?lat={OUT_OF_COVERAGE_LAT}&lon={OUT_OF_COVERAGE_LON}",
        json={"state_key": "TEST-State", "occupation": "vendor",
              "date_range": {"start": "2020-01-01", "end": "2020-01-14"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["coverage_mode"] == "configured"
    assert data["state_key"] == "TEST-State"


def test_explain_unknown_policy_id_returns_404():
    resp = client.get("/explain/does-not-exist")
    assert resp.status_code == 404


def test_forecast_without_trained_model_returns_503(monkeypatch):
    # /forecast still serves the legacy single-city artifact (out of scope
    # for the state-wise rewrite); this only covers the lazy-503 path.
    monkeypatch.setattr(main_module, "FORECASTER_PATH", "models/artifacts/__does_not_exist__.pt")
    main_module._forecaster_cache.clear()
    resp = client.get("/forecast")
    assert resp.status_code == 503
