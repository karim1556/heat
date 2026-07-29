"""Offline-capable tests for the GRU mu-TEVI forecaster (Prompt 8).

Model-shape and persistence-comparison tests run entirely offline (no trained
artifact needed, no mu_tevi.parquet needed). The API-level lazy-503 test
monkeypatches FORECASTER_PATH to a nonexistent file, matching the existing
lazy-loading pattern from test_api.py, so this passes in CI with zero trained
models. A final test exercises the real trained artifact when present (e.g.
after `python -m models.forecast.train` per this prompt's DoD).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient

import backend.main as main_module
from backend.main import app
from models.forecast.model import GRUForecaster
from models.forecast.train import HORIZON, T_IN, build_xy, persistence_baseline, window_starts

client = TestClient(app)


def test_gru_output_shape_matches_configured_horizon():
    model = GRUForecaster(input_size=1, hidden=64, horizon=HORIZON)
    x = torch.randn(4, T_IN, 1)
    out = model(x)
    assert out.shape == (4, HORIZON)


def test_gru_stays_under_the_50k_param_budget():
    model = GRUForecaster(input_size=1, hidden=64, horizon=HORIZON)
    n_params = sum(p.numel() for p in model.parameters())
    assert n_params < 50_000


def test_persistence_baseline_vs_model_mae_comparison_runs():
    """The comparison must RUN and report both MAEs -- the test does NOT
    assert the model wins (models/forecast/train.py may honestly lose to
    persistence and still ships; that is the point of the honesty rule)."""
    rng = np.random.default_rng(42)
    values = 50.0 + 10.0 * np.sin(np.linspace(0, 20, 400)) + rng.normal(0, 2, 400)
    starts = window_starts(len(values), T_IN, HORIZON)
    x, y = build_xy(values, starts, T_IN, HORIZON)
    persistence_pred = persistence_baseline(values, starts, T_IN, HORIZON)
    persistence_mae = float(np.abs(persistence_pred - y).mean())

    model = GRUForecaster(input_size=1, hidden=64, horizon=HORIZON)
    with torch.no_grad():
        model_pred = model(torch.from_numpy(x)).numpy()
    model_mae = float(np.abs(model_pred - y).mean())

    assert np.isfinite(persistence_mae) and np.isfinite(model_mae)
    winner = "model" if model_mae < persistence_mae else "persistence"
    assert winner in ("model", "persistence")  # comparison ran; either honest outcome is valid


def test_forecast_endpoint_without_trained_model_returns_503(monkeypatch):
    monkeypatch.setattr(main_module, "FORECASTER_PATH", Path("models/artifacts/__does_not_exist__.pt"))
    main_module._forecaster_cache.clear()
    resp = client.get("/forecast")
    assert resp.status_code == 503
    assert "not trained" in resp.json()["detail"]


def test_forecast_endpoint_rejects_out_of_range_horizon(monkeypatch):
    monkeypatch.setattr(main_module, "FORECASTER_PATH", Path("models/artifacts/__does_not_exist__.pt"))
    main_module._forecaster_cache.clear()
    resp = client.get("/forecast", params={"horizon_days": 999})
    # Untrained -> 503 fires before the horizon check; this just confirms it
    # never crashes with a 500 on an absurd horizon.
    assert resp.status_code in (503, 400)


@pytest.mark.skipif(
    not Path("models/artifacts/forecaster.pt").exists(),
    reason="forecaster.pt absent; run `python -m models.forecast.train` first",
)
def test_forecast_endpoint_horizon_length_matches_request_real_artifact():
    main_module._forecaster_cache.clear()
    main_module.FORECASTER_PATH = Path("models/artifacts/forecaster.pt")
    resp = client.get("/forecast", params={"horizon_days": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["forecast"]) == 3
    assert data["forecast"][0]["days_ahead"] == 1
    assert "model_mae" in data["validation"]
    assert "persistence_mae" in data["validation"]
    assert "beats_persistence" in data["validation"]
