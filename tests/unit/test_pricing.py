"""Property-based tests for the pricing engine (Hypothesis + unit).

The premium formula IS the product, so these target the invariants a wrong-but-
runnable premium would violate: non-negativity, monotonicity in heat severity,
the Wang risk load's sign, the hurdle atom surviving simulation, and the
basis-risk / degeneracy contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from models.fusion.marginals import HurdleMarginal
from models.pricing.basis_functions import LaguerreBasis
from models.pricing.basis_risk import (
    COMONOTONE_SPEARMAN,
    DegenerateBasisRiskError,
    basis_risk_empirical,
    basis_risk_simulated,
)
from models.pricing.baseline_flat_rate import FlatRatePricer
from models.pricing.lsmc_pricer import LSMCPricer, payout_fraction
from models.pricing.wang_transform import g_lambda, wang_premium

COPULA_PATH = Path("models/artifacts/copula.json")

pytestmark = pytest.mark.skipif(
    not COPULA_PATH.exists(),
    reason="copula.json absent; run `python -m models.fusion.tevi` first",
)

# A fixed pricer for the property tests; each test re-seeds its own simulation.
_PRICER: LSMCPricer | None = None


def pricer() -> LSMCPricer:
    global _PRICER
    if _PRICER is None:
        _PRICER = LSMCPricer.from_copula_json()
    return _PRICER


def _hurdle() -> HurdleMarginal:
    return HurdleMarginal.from_dict(json.loads(COPULA_PATH.read_text())["hurdle"])


# --- premium non-negativity ----------------------------------------------


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(n_days=st.integers(min_value=5, max_value=40), seed=st.integers(0, 2**31 - 1))
def test_premium_is_non_negative_for_any_valid_path_set(n_days, seed):
    """An insurance premium can never be negative, on any simulated climate."""
    p = pricer()
    rng = np.random.default_rng(seed)
    mutevi, loss = p.simulate_paths(n_days, 400, rng)
    result = p.price_paths(mutevi, loss, wage=368.0, market_price_of_risk=0.3)
    assert result["premium_lsmc"] >= 0.0
    assert result["premium_wang"] >= 0.0
    assert result["premium_lsmc_fraction"] >= 0.0


# --- monotonicity in heat severity ---------------------------------------


@settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    n_days=st.integers(min_value=8, max_value=30),
    shift=st.floats(min_value=3.0, max_value=25.0),
    seed=st.integers(0, 2**31 - 1),
)
def test_premium_non_decreasing_in_heat_severity(n_days, shift, seed):
    """Two path sets on the SAME draws, one uniformly hotter (index shifted up):
    the hotter one's premium must not be lower.

    Uses the same simulated paths + a deterministic upward shift, so B
    stochastically dominates A in the index. The payout is monotone in the
    index, so the optimal-stopping value cannot fall. The shift is kept well
    above MC/regression noise; a tiny negative tolerance absorbs the residual.
    """
    p = pricer()
    rng = np.random.default_rng(seed)
    mutevi, loss = p.simulate_paths(n_days, 800, rng)

    hotter = np.clip(mutevi + shift, 0.0, 100.0)
    prem_base = p.price_paths(mutevi, loss)["premium_lsmc_fraction"]
    prem_hot = p.price_paths(hotter, loss)["premium_lsmc_fraction"]
    assert prem_hot >= prem_base - 1e-9


def test_premium_strictly_responds_to_a_large_heat_shift():
    """Sanity that the monotonicity test is not vacuously passing on flat zeros."""
    p = pricer()
    rng = np.random.default_rng(0)
    mutevi, loss = p.simulate_paths(30, 2000, rng)
    cold = np.clip(mutevi - 30.0, 0.0, 100.0)
    hot = np.clip(mutevi + 20.0, 0.0, 100.0)
    assert p.price_paths(hot, loss)["premium_lsmc_fraction"] > \
        p.price_paths(cold, loss)["premium_lsmc_fraction"]


# --- Wang risk load -------------------------------------------------------


@settings(max_examples=30, deadline=None)
@given(
    lambda_w=st.floats(min_value=0.01, max_value=1.0),
    payoffs=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=5, max_size=200),
)
def test_wang_premium_at_least_lsmc_when_lambda_positive(lambda_w, payoffs):
    """lambda_w > 0 loads risk: the distorted mean must be >= the plain mean."""
    payoffs = np.asarray(payoffs)
    plain = float(payoffs.mean())
    distorted = wang_premium(payoffs, lambda_w)
    assert distorted >= plain - 1e-9


def test_wang_premium_equals_mean_at_zero_lambda():
    """lambda_w = 0 is the identity distortion -> exactly the sample mean."""
    rng = np.random.default_rng(0)
    payoffs = rng.uniform(0, 1, 500)
    assert wang_premium(payoffs, 0.0) == pytest.approx(payoffs.mean(), abs=1e-9)


def test_g_lambda_exceeds_identity_for_positive_lambda():
    """g_lambda(u) > u on (0,1) for lambda_w > 0; fixes the endpoints."""
    u = np.linspace(0.01, 0.99, 50)
    assert np.all(g_lambda(u, 0.5) > u)
    assert g_lambda(0.0, 0.5) == pytest.approx(0.0)
    assert g_lambda(1.0, 0.5) == pytest.approx(1.0)
    # Monotone increasing.
    g = g_lambda(np.linspace(0, 1, 200), 0.4)
    assert np.all(np.diff(g) >= -1e-12)


def test_wang_lambda_is_not_the_copula_lambda_u():
    """Guard against the naming confusion: the Wang load and the copula tail
    dependence are different quantities. At the copula's lambda_U=0.835 used as a
    Wang lambda_w, the load is large and unrelated to any tail-dependence value."""
    d = json.loads(COPULA_PATH.read_text())
    lambda_u = d["upper_tail_dependence"]
    payoffs = np.linspace(0, 1, 100)
    # Using lambda_u as lambda_w is a *mistake*; it still computes, which is
    # exactly why the code must never alias them. Assert they give different
    # premiums so the two are demonstrably distinct knobs.
    assert wang_premium(payoffs, lambda_u) != pytest.approx(wang_premium(payoffs, 0.3))


# --- hurdle atom survives simulation -------------------------------------


@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(n_days=st.integers(min_value=10, max_value=40), seed=st.integers(0, 2**31 - 1))
def test_simulated_paths_reproduce_the_zero_atom(n_days, seed):
    """HURDLE GUARD: the realized zero-fraction must match p0 within tolerance --
    the atom must survive sampling rather than being smeared away."""
    p = pricer()
    hurdle = _hurdle()
    _, loss = p.simulate_paths(n_days, 1000, np.random.default_rng(seed))
    zero_fraction = float(np.mean(loss == 0.0))
    assert abs(zero_fraction - hurdle.p0) < 0.05


def test_simulate_paths_asserts_when_the_atom_is_smeared_away():
    """The guard's real target: sampling a CONTINUOUS law (the Prompt-3 smearing
    bug) instead of the hurdle. Then the realized zero-fraction is ~0 while p0 is
    ~0.33, so simulate_paths must REFUSE rather than price a smeared marginal.

    (Merely changing p0 cannot trigger it: HurdleMarginal.ppf uses its own p0 as
    the zero threshold, so the zero-fraction self-consistently tracks whatever p0
    the object holds. The failure that matters is a sampler with NO atom.)
    """
    p = pricer()

    class _SmearedContinuousLoss:
        """A continuous positive loss with NO atom -- exactly the smearing bug."""
        p0 = 0.3348
        positive_dist = "beta"

        def ppf(self, v):
            return 0.01 + 0.2 * np.asarray(v, dtype=float)  # strictly positive, no zeros

    p_broken = LSMCPricer(p.copula.theta, p.gev_params, _SmearedContinuousLoss(),
                          strike=p.strike)
    with pytest.raises(AssertionError, match="atom did NOT survive"):
        p_broken.simulate_paths(30, 1000, np.random.default_rng(0))


# --- basis-risk sanity ----------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(
    payout=st.lists(st.floats(min_value=0.0, max_value=1.0), min_size=10, max_size=300),
    data=st.data(),
)
def test_basis_risk_rates_are_probabilities(payout, data):
    """shortfall_rate and overpay_rate are probabilities in [0,1]."""
    payout = np.asarray(payout)
    loss = np.asarray(data.draw(st.lists(
        st.floats(min_value=0.0, max_value=1.0),
        min_size=len(payout), max_size=len(payout))))
    br = basis_risk_empirical(payout, loss, guard=False)
    assert 0.0 <= br["shortfall_rate"] <= 1.0
    assert 0.0 <= br["overpay_rate"] <= 1.0
    assert br["basis_risk_rmse"] >= 0.0
    assert -1.0 - 1e-9 <= br["correlation"] <= 1.0 + 1e-9


def test_perfect_payout_has_zero_basis_risk_rmse():
    """payout == actual_loss -> rmse 0, no shortfall, no overpay (degenerate check)."""
    rng = np.random.default_rng(0)
    loss = rng.uniform(0, 0.3, 500)
    # guard=False: identical series are trivially comonotone, which is the whole
    # point of THIS check; the guard is exercised separately below.
    br = basis_risk_empirical(loss.copy(), loss.copy(), guard=False)
    assert br["basis_risk_rmse"] == pytest.approx(0.0)
    assert br["shortfall_rate"] == 0.0
    assert br["overpay_rate"] == 0.0


def test_shortfall_and_overpay_are_directional():
    payout = np.array([0.0, 0.0, 0.0, 0.0])
    loss = np.array([0.1, 0.2, 0.3, 0.4])  # always under-compensated
    br = basis_risk_empirical(payout, loss, guard=False)
    assert br["shortfall_rate"] == 1.0
    assert br["overpay_rate"] == 0.0


def test_degeneracy_guard_refuses_comonotone_pairing():
    """The core guard: a payout that is a monotone transform of the loss (no ties)
    is comonotone -> refused, because it fakes zero basis risk."""
    rng = np.random.default_rng(0)
    loss = rng.uniform(0.01, 0.3, 1000)
    payout = 2.0 * loss + 0.05  # strictly increasing in loss -> Spearman 1.0
    with pytest.raises(DegenerateBasisRiskError, match="comonotone"):
        basis_risk_simulated(payout, loss)
    with pytest.raises(DegenerateBasisRiskError):
        basis_risk_empirical(payout, loss)


def test_degeneracy_guard_allows_the_real_basis_risk_pairing():
    """The correct index-vs-own-loss pairing (Spearman ~0.8) must pass the guard."""
    p = pricer()
    mutevi, loss = p.simulate_paths(30, 2000, np.random.default_rng(0))
    payout = payout_fraction(mutevi, p.strike, p.cap)
    br = basis_risk_simulated(payout, loss)  # must not raise
    from scipy.stats import spearmanr
    rho = spearmanr(payout.reshape(-1), loss.reshape(-1)).statistic
    assert rho < COMONOTONE_SPEARMAN
    assert br["correlation"] > 0.0  # positively but not perfectly related


# --- end-to-end price_window ---------------------------------------------


def test_price_window_returns_the_required_contract():
    """price_window's return shape is the API Prompt 6 and Prompt 7 depend on."""
    p = pricer()
    window = np.full(30, 60.0)
    result = p.price_window(window, "vendor", n_paths=500)
    assert set(result) >= {"premium_lsmc", "premium_wang", "payout_schedule", "basis_risk"}
    assert result["premium_lsmc"] > 0.0
    assert result["premium_wang"] >= result["premium_lsmc"] - 1e-9  # lambda_w>0 default
    br = result["basis_risk"]
    assert {"basis_risk_rmse", "shortfall_rate", "overpay_rate", "correlation"} == set(br)
    assert result["payout_schedule"]["strike"] == p.strike


def test_price_window_scales_with_wage_but_fraction_is_invariant():
    """Occupation enters as a wage scale; the wage-fraction premium is identical."""
    p = pricer()
    window = np.full(30, 65.0)
    vendor = p.price_window(window, "vendor", n_paths=800)
    construction = p.price_window(window, "construction", n_paths=800)
    assert vendor["premium_lsmc_fraction"] == pytest.approx(
        construction["premium_lsmc_fraction"])
    # Absolute premium tracks the wage ratio.
    ratio = construction["premium_lsmc"] / vendor["premium_lsmc"]
    assert ratio == pytest.approx(construction["wage"] / vendor["wage"], rel=1e-6)


# --- baseline & basis functions ------------------------------------------


def test_flat_rate_is_constant_across_policies():
    flat = FlatRatePricer.calibrate(np.array([0.1, 0.2, 0.3, 0.0, 0.5]))
    assert flat.price_window(np.full(30, 90.0), "vendor") == \
        flat.price_window(np.full(30, 40.0), "construction")
    assert flat.flat_premium == pytest.approx(np.mean([0.1, 0.2, 0.3, 0.0, 0.5]) * 1.1)


def test_laguerre_basis_matches_the_closed_forms():
    basis = LaguerreBasis(degree=3)
    design = basis.transform(np.array([0.0, 50.0, 100.0]))
    assert design.shape == (3, 4)
    # At scaled x = index/100: rows for x = 0.0, 0.5, 1.0.
    x = np.array([0.0, 0.5, 1.0])
    np.testing.assert_allclose(design[:, 0], 1.0)
    np.testing.assert_allclose(design[:, 1], 1.0 - x)
    np.testing.assert_allclose(design[:, 2], 1.0 - 2 * x + x**2 / 2)
    np.testing.assert_allclose(design[:, 3], 1.0 - 3 * x + 3 * x**2 / 2 - x**3 / 6)


def test_payout_fraction_is_zero_below_strike_and_capped_above():
    assert payout_fraction(50.0, strike=75.0, cap=0.9) == 0.0
    assert payout_fraction(75.0, strike=75.0, cap=0.9) == 0.0
    assert payout_fraction(100.0, strike=75.0, cap=0.9) == pytest.approx(0.9)
    assert 0.0 < payout_fraction(85.0, strike=75.0, cap=0.9) < 0.9
