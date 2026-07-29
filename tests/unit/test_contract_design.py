"""Unit tests for the contract design pass and the amended metrics.

Covers the DoD-required checks: the "behaves like insurance" criteria on
hand-constructed cases, a deterministic/reproducible sweep + selection, and
tail_weighted_error reducing to plain MAE at tail_quantile=0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.backtest import contract_design as cd
from backend.backtest.metrics import mae, tail_weighted_error

COPULA_PATH = "models/artifacts/copula.json"
MU_TEVI_PATH = "data/processed/mu_tevi.parquet"

_needs_artifacts = pytest.mark.skipif(
    not (pd.io.common.file_exists(COPULA_PATH) and pd.io.common.file_exists(MU_TEVI_PATH)),
    reason="copula.json / mu_tevi.parquet absent; run the pipeline first",
)


# --- criteria function ----------------------------------------------------


def test_near_always_paying_contract_fails_insurance_criteria():
    """A contract that triggers almost every window is NOT catastrophe insurance."""
    row = {"trigger_rate": 0.90, "premium_to_cap": 0.85, "shortfall_rate": 0.20}
    assert cd.behaves_like_insurance(row) is False


def test_rare_trigger_meaningful_premium_contract_passes():
    """Rare trigger + cheap premium + good coverage = catastrophe insurance."""
    row = {"trigger_rate": 0.10, "premium_to_cap": 0.20, "shortfall_rate": 0.20}
    assert cd.behaves_like_insurance(row) is True


def test_each_criterion_is_necessary():
    """Violating ANY single criterion flips the verdict to False."""
    ok = {"trigger_rate": 0.10, "premium_to_cap": 0.20, "shortfall_rate": 0.20}
    assert cd.behaves_like_insurance(ok)
    assert not cd.behaves_like_insurance({**ok, "trigger_rate": 0.50})     # too frequent
    assert not cd.behaves_like_insurance({**ok, "premium_to_cap": 0.80})   # prepaid-ish
    assert not cd.behaves_like_insurance({**ok, "shortfall_rate": 0.60})   # gutted coverage


def test_criteria_are_at_the_documented_boundaries():
    """Boundary values (<=) pass; a hair over fails."""
    at_bound = {"trigger_rate": cd.CAT_MAX_TRIGGER_RATE,
                "premium_to_cap": cd.CAT_MAX_PREMIUM_TO_CAP,
                "shortfall_rate": cd.CAT_MAX_SHORTFALL_RATE}
    assert cd.behaves_like_insurance(at_bound)
    assert not cd.behaves_like_insurance({**at_bound,
                                          "trigger_rate": cd.CAT_MAX_TRIGGER_RATE + 1e-6})


# --- selection on a hand-built sweep --------------------------------------


def test_select_contract_reframes_when_no_point_is_insurance():
    """If nothing passes the catastrophe criteria, the frame must be income
    smoothing and the chosen strike must minimize the shortfall/overpay
    asymmetry (the unbiased-index objective)."""
    sweep = pd.DataFrame([
        # strike, window, trigger, payout_freq, prem/cap, shortfall, overpay, rmse, maes...
        dict(strike=60, window=30, trigger_rate=0.6, payout_frequency=0.02,
             premium_to_cap=0.90, shortfall_rate=0.20, overpay_rate=0.47,
             basis_risk_rmse=110.0, mae_full=80, mae_flat=110, mae_improvement_pct=27),
        dict(strike=75, window=30, trigger_rate=0.5, payout_frequency=0.02,
             premium_to_cap=0.70, shortfall_rate=0.34, overpay_rate=0.32,
             basis_risk_rmse=82.0, mae_full=85, mae_flat=116, mae_improvement_pct=27),
        dict(strike=95, window=30, trigger_rate=0.2, payout_frequency=0.01,
             premium_to_cap=0.50, shortfall_rate=0.64, overpay_rate=0.03,
             basis_risk_rmse=48.0, mae_full=70, mae_flat=173, mae_improvement_pct=60),
    ])
    chosen = cd.select_contract(sweep)
    assert chosen["frame"] == "income_smoothing"
    assert chosen["is_catastrophe_insurance"] is False
    assert chosen["n_catastrophe_passing"] == 0
    # strike 75 is the most unbiased (|0.34-0.32| = 0.02, the minimum).
    assert chosen["strike"] == 75


def test_select_contract_prefers_catastrophe_insurance_if_one_exists():
    """If a point DOES qualify as catastrophe insurance, it must be chosen over
    an income-smoothing reframe."""
    sweep = pd.DataFrame([
        dict(strike=75, window=30, trigger_rate=0.5, payout_frequency=0.02,
             premium_to_cap=0.70, shortfall_rate=0.34, overpay_rate=0.32,
             basis_risk_rmse=82.0, mae_full=85, mae_flat=116, mae_improvement_pct=27),
        dict(strike=98, window=14, trigger_rate=0.10, payout_frequency=0.01,
             premium_to_cap=0.25, shortfall_rate=0.25, overpay_rate=0.05,
             basis_risk_rmse=40.0, mae_full=70, mae_flat=175, mae_improvement_pct=60),
    ])
    chosen = cd.select_contract(sweep)
    assert chosen["frame"] == "catastrophe_insurance"
    assert chosen["is_catastrophe_insurance"] is True
    assert chosen["strike"] == 98


def test_income_smoothing_window_tiebreak_maximizes_risk_transfer():
    """Among strikes tied on unbiasedness, the lower premium/cap window wins
    (more genuine risk transfer), not an arbitrary choice."""
    sweep = pd.DataFrame([
        dict(strike=75, window=14, trigger_rate=0.48, payout_frequency=0.03,
             premium_to_cap=0.70, shortfall_rate=0.34, overpay_rate=0.32,
             basis_risk_rmse=82.0, mae_full=84, mae_flat=116, mae_improvement_pct=27),
        dict(strike=75, window=30, trigger_rate=0.51, payout_frequency=0.02,
             premium_to_cap=0.83, shortfall_rate=0.34, overpay_rate=0.32,
             basis_risk_rmse=82.0, mae_full=78, mae_flat=119, mae_improvement_pct=35),
    ])
    chosen = cd.select_contract(sweep)
    assert chosen["strike"] == 75
    assert chosen["window"] == 14  # lower premium/cap, despite the WORSE MAE gap


# --- reproducibility of the real sweep ------------------------------------


@_needs_artifacts
def test_real_sweep_and_selection_are_reproducible():
    """DoD: the sweep is deterministic (seed logged) and the chosen point is
    reproducible across reruns."""
    a = cd.run_design_pass(persist_table=False)
    b = cd.run_design_pass(persist_table=False)
    assert a["chosen"]["strike"] == b["chosen"]["strike"]
    assert a["chosen"]["window"] == b["chosen"]["window"]
    assert a["chosen"]["frame"] == b["chosen"]["frame"]
    # The full sweep table must be numerically identical, not just the winner.
    pd.testing.assert_frame_equal(a["sweep"], b["sweep"])


@_needs_artifacts
def test_real_honesty_gate_fires_on_this_data():
    """On the real Ahmedabad data the peril is chronic, so NO grid point should
    behave like catastrophe insurance -- the honesty gate must fire and the
    product must be reframed as income smoothing."""
    chosen = cd.run_design_pass(persist_table=False)["chosen"]
    assert chosen["n_catastrophe_passing"] == 0
    assert chosen["frame"] == "income_smoothing"


# --- tail_weighted_error reduces to MAE -----------------------------------


def test_tail_weighted_error_reduces_to_mae_at_quantile_zero():
    """Sanity: at tail_quantile=0 every window is in the 'tail', so the
    tail-weighted error is exactly plain MAE."""
    rng = np.random.default_rng(0)
    actual = rng.uniform(1.0, 300.0, 500)  # all nonzero so samples coincide
    predicted = actual + rng.normal(0, 30, 500)
    twe = tail_weighted_error(actual, predicted, tail_quantile=0.0)
    plain = mae(actual, predicted, nonzero_only=False)
    assert twe["tail_weighted_error"] == pytest.approx(plain["mae"])
    assert twe["n_tail"] == len(actual)


def test_tail_weighted_error_focuses_on_large_actuals():
    """At a high quantile it must score only the large-actual windows."""
    actual = np.array([1.0, 2.0, 3.0, 100.0, 200.0])
    predicted = np.zeros_like(actual)
    twe = tail_weighted_error(actual, predicted, tail_quantile=0.8)
    # top 20% -> just the 200.0 window -> error 200.
    assert twe["n_tail"] == 1
    assert twe["tail_weighted_error"] == pytest.approx(200.0)


def test_tail_weighted_error_rejects_out_of_range_quantile():
    with pytest.raises(ValueError, match="tail_quantile"):
        tail_weighted_error(np.array([1.0, 2.0]), np.array([1.0, 2.0]), tail_quantile=1.0)
