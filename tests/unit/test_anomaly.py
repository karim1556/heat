"""Offline-capable tests for the Isolation Forest claim-anomaly detector
(Prompt 8).

Fits on a small SYNTHETIC-BUT-STRUCTURED claim table generated in-process --
this is test-fixture data for the sklearn wrapper's unit tests, not the
product's pricing pipeline (CLAUDE.md Golden Rule 5 governs real data on the
PRICING path; it does not forbid synthetic fixtures for testing a generic ML
wrapper class). This keeps the test independent of data/processed/claims.parquet,
which is gitignored and absent in CI.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

import backend.main as main_module
from backend.main import app
from models.anomaly.detector import ClaimAnomalyDetector

client = TestClient(app)


def _synthetic_claims(n: int = 400, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    occupations = rng.choice(["vendor", "construction", "delivery"], size=n)
    heat_index = rng.uniform(75.0, 92.0, n)       # typical triggering range
    claimed_payout = rng.uniform(50.0, 250.0, n)   # typical payout range (INR)
    days_since_last_claim = rng.uniform(10.0, 40.0, n)
    return pd.DataFrame({
        "occupation": occupations, "heat_index": heat_index,
        "claimed_payout": claimed_payout, "days_since_last_claim": days_since_last_claim,
    })


def test_extreme_outlier_claim_is_flagged_normal_claim_is_not():
    claims = _synthetic_claims()
    outlier = pd.DataFrame([{
        "occupation": "vendor", "heat_index": 100.0,
        "claimed_payout": 5000.0,       # ~20x the typical range
        "days_since_last_claim": 0.5,   # implausibly rapid re-claim
    }])
    normal = pd.DataFrame([{
        "occupation": "vendor", "heat_index": float(np.median(claims["heat_index"])),
        "claimed_payout": float(np.median(claims["claimed_payout"])),
        "days_since_last_claim": float(np.median(claims["days_since_last_claim"])),
    }])

    fit_df = pd.concat([claims, outlier], ignore_index=True)
    detector = ClaimAnomalyDetector().fit(fit_df)

    assert bool(detector.predict(outlier)[0]) is True
    assert bool(detector.predict(normal)[0]) is False
    # The outlier's score must be markedly more anomalous (lower) than the normal claim's.
    assert detector.score(outlier)[0] < detector.score(normal)[0]


def test_first_claim_nan_days_since_is_imputed_not_crashing():
    """A worker's first-ever claim has NaN days_since_last_claim (see
    backend/backtest/historical_replay.py's build_claims); the detector must
    impute it (median), not crash or propagate NaN into the model."""
    claims = _synthetic_claims()
    claims.loc[0, "days_since_last_claim"] = np.nan
    detector = ClaimAnomalyDetector().fit(claims)
    flags = detector.predict(claims)
    assert flags.shape == (len(claims),)
    assert flags.dtype == bool


def test_flag_anomaly_endpoint_without_trained_model_returns_503(monkeypatch):
    monkeypatch.setattr(main_module, "ANOMALY_PATH", Path("models/artifacts/__does_not_exist__.pkl"))
    main_module._anomaly_cache.clear()
    resp = client.post("/flag-anomaly", json={
        "heat_index": 80.0, "occupation": "vendor",
        "claimed_payout": 100.0, "days_since_last_claim": 20.0,
    })
    assert resp.status_code == 503


def test_flag_anomaly_endpoint_with_stubbed_detector_flags_extreme_claim(monkeypatch, tmp_path):
    """End-to-end through the API using a real ClaimAnomalyDetector fit on
    synthetic data and pickled to a temp path -- no dependency on the real
    claims.parquet or a pre-trained anomaly.pkl."""
    import pickle

    claims = _synthetic_claims()
    detector = ClaimAnomalyDetector().fit(claims)
    pkl_path = tmp_path / "anomaly.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(detector, f)

    monkeypatch.setattr(main_module, "ANOMALY_PATH", pkl_path)
    main_module._anomaly_cache.clear()

    resp = client.post("/flag-anomaly", json={
        "heat_index": 100.0, "occupation": "vendor",
        "claimed_payout": 5000.0, "days_since_last_claim": 0.5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_anomalous"] is True
    assert isinstance(data["anomaly_score"], float)
