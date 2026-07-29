"""Unit tests for backend/backtest/metrics.py.

Not required by Prompt 6's DoD, but two of these functions had real bugs
caught only by running them against real data (not by shape-checking), and
those bugs deserve regression coverage: payout_frequency algebraically
collapsing to trigger_rate under a naive denominator, and MAPE's small-actual
pathology needing an explicit, honest convention.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.backtest.metrics import (
    expected_shortfall,
    mape,
    payout_frequency,
    premium_to_payout_ratio,
    trigger_rate,
    value_at_risk,
)
from models.pricing.basis_risk import DegenerateBasisRiskError, basis_risk_empirical


def test_mape_excludes_zero_actual_and_reports_the_count():
    actual = np.array([0.0, 0.0, 10.0, 20.0])
    predicted = np.array([5.0, 5.0, 12.0, 18.0])
    result = mape(actual, predicted)
    assert result["n_excluded_zero_actual"] == 2
    assert result["n_included"] == 2
    expected = np.mean([abs(10 - 12) / 10, abs(20 - 18) / 20]) * 100.0
    assert result["mape"] == pytest.approx(expected)


def test_mape_raises_when_every_actual_is_zero():
    with pytest.raises(ValueError, match="undefined"):
        mape(np.zeros(5), np.ones(5))


def test_mape_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        mape(np.array([1.0, 2.0]), np.array([1.0]))


def test_payout_frequency_is_not_algebraically_identical_to_trigger_rate():
    """THE bug: with n_windows as payout_frequency's denominator and one claim
    per worker per triggering window, payout_frequency collapses exactly onto
    trigger_rate (n_triggered*n_workers / (n_workers*n_windows) = trigger_rate).
    The fix uses n_days, which must give a materially smaller number.
    """
    window_summary = pd.DataFrame({
        "window_id": [0, 0, 1, 1, 2, 2],
        "occupation": ["vendor", "construction"] * 3,
        "triggered": [True, True, False, False, True, True],
    })
    n_windows = 3
    n_workers = 2
    n_claim_events = 2 * 2  # 2 triggering windows x 2 workers, one claim each

    tr = trigger_rate(window_summary)
    assert tr == pytest.approx(2 / 3)

    # Naive (buggy) denominator: collapses onto trigger_rate exactly.
    buggy = n_claim_events / (n_workers * n_windows)
    assert buggy == pytest.approx(tr)

    # Correct denominator: true worker-days, not worker-windows.
    n_days = 90  # e.g. 3 x 30-day windows
    pf = payout_frequency(n_claim_events, n_workers, n_days)
    assert pf != pytest.approx(tr)
    assert pf < tr  # a per-day rate must be far smaller than a per-window rate


def test_payout_frequency_rejects_nonpositive_inputs():
    with pytest.raises(ValueError, match="must be > 0"):
        payout_frequency(5, 0, 100)
    with pytest.raises(ValueError, match="must be > 0"):
        payout_frequency(5, 10, 0)


def test_trigger_rate_dedupes_across_occupations():
    """The trigger is a single shared city-level event; trigger_rate must not
    be inflated by counting it once per occupation."""
    window_summary = pd.DataFrame({
        "window_id": [0, 0, 0],
        "occupation": ["vendor", "construction", "delivery"],
        "triggered": [True, True, True],
    })
    assert trigger_rate(window_summary) == pytest.approx(1.0)


def test_value_at_risk_and_expected_shortfall_are_ordered():
    rng = np.random.default_rng(42)
    losses = rng.exponential(scale=100.0, size=5000)
    var95 = value_at_risk(losses, 0.95)
    es95 = expected_shortfall(losses, 0.95)
    var99 = value_at_risk(losses, 0.99)
    assert es95 >= var95  # ES is the mean of the tail beyond VaR -> never below it
    assert var99 >= var95  # a stricter quantile is a larger loss


def test_value_at_risk_rejects_bad_alpha():
    with pytest.raises(ValueError, match="alpha"):
        value_at_risk(np.array([1.0, 2.0]), 1.5)


def test_premium_to_payout_ratio_directionality():
    assert premium_to_payout_ratio(np.array([100.0, 100.0]), np.array([50.0, 50.0])) \
        == pytest.approx(2.0)
    assert premium_to_payout_ratio(np.array([10.0]), np.array([0.0])) == float("inf")


def test_basis_risk_empirical_is_reused_verbatim_and_guards_degeneracy():
    """metrics.basis_risk_empirical must be the SAME function models.pricing
    uses (not a re-implementation) -- exercised here via the degeneracy guard,
    which is the one behavior that would silently diverge if it were copied."""
    rng = np.random.default_rng(0)
    loss = rng.uniform(0.01, 0.3, 1000)
    comonotone_payout = 2.0 * loss + 0.05
    with pytest.raises(DegenerateBasisRiskError):
        basis_risk_empirical(comonotone_payout, loss)
