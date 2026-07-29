"""Unit tests for the Gumbel copula and the hurdle marginal.

These target the places where a wrong implementation still runs and still
returns a plausible number: the copula density (a hand-derived mixed partial),
the tail-dependence direction, atom handling in the marginal, and tie handling
in the pseudo-observations.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats
from scipy.stats import kendalltau

from models.fusion.gumbel_copula import (
    THETA_MAX,
    GumbelSurvivalCopula,
    distributional_transform,
    empirical_pseudo_obs,
    mid_rank_transform,
)
from models.fusion.marginals import HurdleMarginal, NaiveMarginal, fit_gev

SEED = 42


# --- copula self-consistency ---------------------------------------------


def test_sampler_recovers_the_generating_theta_within_five_percent():
    """SELF-CONSISTENCY: sample at a known theta=2.5, refit, recover it."""
    rng = np.random.default_rng(SEED)
    true_theta = 2.5
    u, v = GumbelSurvivalCopula(true_theta).sample(40_000, rng)
    refit = GumbelSurvivalCopula.fit(u, v)
    assert abs(refit.theta - true_theta) / true_theta < 0.05, \
        f"recovered theta={refit.theta:.4f} from true {true_theta}"


@pytest.mark.parametrize("true_theta", [1.5, 2.5, 4.0, 6.5])
def test_theta_recovery_holds_across_the_dependence_range(true_theta):
    rng = np.random.default_rng(SEED)
    u, v = GumbelSurvivalCopula(true_theta).sample(40_000, rng)
    refit = GumbelSurvivalCopula.fit(u, v)
    assert abs(refit.theta - true_theta) / true_theta < 0.05


def test_upper_tail_dependence_matches_the_closed_form():
    for theta in (1.0, 1.5, 2.5, 6.5, 20.0):
        copula = GumbelSurvivalCopula(theta)
        assert copula.upper_tail_dependence() == pytest.approx(2.0 - 2.0 ** (1.0 / theta))
    # theta=1 is independence -> no tail dependence at all.
    assert GumbelSurvivalCopula(1.0).upper_tail_dependence() == pytest.approx(0.0)
    # Tail dependence increases toward comonotonicity.
    assert GumbelSurvivalCopula(20.0).upper_tail_dependence() > \
        GumbelSurvivalCopula(2.0).upper_tail_dependence()


def test_sampled_kendall_tau_matches_the_closed_form():
    """tau = 1 - 1/theta. Validates the Marshall-Olkin sampler independently
    of the MLE -- if both were wrong in the same way, theta recovery alone
    could still pass."""
    rng = np.random.default_rng(SEED)
    for theta in (1.5, 2.5, 6.5):
        u, v = GumbelSurvivalCopula(theta).sample(60_000, rng)
        assert kendalltau(u, v).statistic == pytest.approx(1.0 - 1.0 / theta, abs=0.01)


def test_positive_stable_has_the_required_laplace_transform():
    """E[exp(-tS)] = exp(-t^alpha) is what makes the frailty construction a Gumbel."""
    rng = np.random.default_rng(SEED)
    for alpha in (0.4, 0.667):
        s = GumbelSurvivalCopula._positive_stable(alpha, 300_000, rng)
        for t in (0.5, 1.0, 2.0):
            assert np.mean(np.exp(-t * s)) == pytest.approx(np.exp(-(t**alpha)), abs=5e-3)


# --- copula correctness ---------------------------------------------------


def test_density_is_the_numerical_mixed_partial_of_the_cdf():
    """log_density must be d2C/dudv. Checked numerically, because an algebra slip
    in the hand-derived density still yields a smooth, convergent MLE."""
    theta = 2.5
    copula = GumbelSurvivalCopula(theta)
    h = 1e-5
    for u0, v0 in ((0.3, 0.4), (0.5, 0.5), (0.7, 0.2), (0.85, 0.9)):
        numeric = (
            copula.cdf(u0 + h, v0 + h) - copula.cdf(u0 + h, v0 - h)
            - copula.cdf(u0 - h, v0 + h) + copula.cdf(u0 - h, v0 - h)
        ) / (4 * h * h)
        analytic = float(np.exp(copula._log_density(
            np.array([u0]), np.array([v0]), theta))[0])
        assert analytic == pytest.approx(numeric, rel=1e-4)


def test_theta_one_is_the_independence_copula():
    copula = GumbelSurvivalCopula(1.0)
    u = np.array([0.2, 0.5, 0.8])
    v = np.array([0.3, 0.5, 0.9])
    np.testing.assert_allclose(copula.cdf(u, v), u * v, rtol=1e-8)
    # log density of the independence copula is exactly 0 (c = 1).
    np.testing.assert_allclose(copula._log_density(u, v, 1.0), 0.0, atol=1e-8)


def test_cdf_respects_the_frechet_bounds_and_is_a_valid_copula():
    rng = np.random.default_rng(SEED)
    u = rng.uniform(0.01, 0.99, 500)
    v = rng.uniform(0.01, 0.99, 500)
    for theta in (1.0, 2.5, 10.0):
        c = GumbelSurvivalCopula(theta).cdf(u, v)
        assert np.all(c <= np.minimum(u, v) + 1e-9)              # upper Frechet
        assert np.all(c >= np.maximum(u + v - 1.0, 0.0) - 1e-9)  # lower Frechet
        assert np.all((c >= 0) & (c <= 1))


def test_cdf_has_uniform_margins():
    """C(u,1) = u and C(1,v) = v."""
    copula = GumbelSurvivalCopula(2.5)
    for x in (0.1, 0.5, 0.9):
        assert copula.cdf(x, 1.0) == pytest.approx(x, abs=1e-6)
        assert copula.cdf(1.0, x) == pytest.approx(x, abs=1e-6)


def test_survival_cdf_is_the_joint_exceedance_probability():
    """survival_cdf(u,v) must equal P(U>u, V>v), verified against a sample."""
    rng = np.random.default_rng(SEED)
    theta = 2.5
    copula = GumbelSurvivalCopula(theta)
    us, vs = copula.sample(200_000, rng)
    for u0, v0 in ((0.3, 0.3), (0.5, 0.7), (0.8, 0.8)):
        empirical = float(np.mean((us > u0) & (vs > v0)))
        assert copula.survival_cdf(u0, v0) == pytest.approx(empirical, abs=5e-3)


def test_survival_cdf_identity():
    copula = GumbelSurvivalCopula(3.0)
    u, v = 0.4, 0.6
    assert copula.survival_cdf(u, v) == pytest.approx(1 - u - v + copula.cdf(u, v))


def test_gumbel_has_upper_not_lower_tail_dependence():
    """The direction is the whole point: joint EXTREMES must co-occur.

    If the rotated survival copula had been implemented by mistake, this test
    fails while every shape test still passes.
    """
    rng = np.random.default_rng(SEED)
    u, v = GumbelSurvivalCopula(4.0).sample(200_000, rng)
    q = 0.98
    upper = float(np.mean(v[u > q] > q))   # P(V>q | U>q)
    lower = float(np.mean(v[u < 1 - q] < 1 - q))  # P(V<1-q | U<1-q)
    assert upper > lower, "Gumbel must be upper-tail dependent, not lower"
    assert upper == pytest.approx(GumbelSurvivalCopula(4.0).upper_tail_dependence(), abs=0.06)


def test_fit_rejects_theta_below_one_and_mismatched_lengths():
    with pytest.raises(ValueError, match="theta must be"):
        GumbelSurvivalCopula(0.5)
    with pytest.raises(ValueError, match="same length"):
        GumbelSurvivalCopula.fit(np.array([0.1, 0.2]), np.array([0.3]))


def test_comonotone_data_pins_theta_to_the_bound_and_is_flagged():
    """Perfectly comonotone data (exactly what Prompt 3's deterministic loss
    produces if paired with its own node's heat) must be FLAGGED, not silently
    reported as an estimate."""
    u = np.linspace(0.001, 0.999, 3000)
    copula = GumbelSurvivalCopula.fit(u, u.copy())
    assert copula.fit_hit_bound
    assert copula.theta == pytest.approx(THETA_MAX, rel=1e-2)


# --- hurdle marginal ------------------------------------------------------


def _synthetic_hurdle(n=20_000, p0=0.30, seed=SEED):
    rng = np.random.default_rng(seed)
    in_zero = rng.random(n) < p0
    losses = np.where(in_zero, 0.0, stats.beta.rvs(2.0, 5.0, size=n, random_state=rng))
    return losses, in_zero


# The jitter RNG must NEVER share a seed with _synthetic_hurdle's. `in_zero` is
# defined as {i : stream[i] < p0}, so an identically-seeded jitter draw is < p0
# at exactly the atom rows -- the "random" jitter lands perfectly correlated with
# the atom mask, and the transform's output silently stops being uniform (KS 0.21
# instead of 0.002). Real runs cannot hit this (the data come from NASA POWER, not
# from an RNG), but the trap is easy to walk into in a test.
JITTER_SEED = 1234


def test_hurdle_recovers_a_known_zero_atom():
    """HURDLE CORRECTNESS: known 30% atom -> fitted p0 within 2 percentage points."""
    losses, in_zero = _synthetic_hurdle(p0=0.30)
    hurdle = HurdleMarginal.fit(losses, in_zero)
    assert abs(hurdle.p0 - 0.30) < 0.02, f"fitted p0={hurdle.p0:.4f}"
    assert hurdle.n_zero + hurdle.n_positive == len(losses)


def test_hurdle_cdf_at_zero_equals_p0_the_atom_is_not_smeared():
    """F_L(0) == p0 exactly: the point mass is represented, not averaged away."""
    losses, in_zero = _synthetic_hurdle(p0=0.30)
    hurdle = HurdleMarginal.fit(losses, in_zero)
    assert float(hurdle.cdf(0.0)) == pytest.approx(hurdle.p0)
    assert float(hurdle.cdf(-1.0)) == pytest.approx(hurdle.p0)
    # The left limit at the atom is 0 -- the atom spans the whole [0, p0] interval.
    assert float(hurdle.cdf_left_limit(0.0)) == pytest.approx(0.0)


def test_hurdle_cdf_is_the_stated_mixture_and_is_a_valid_cdf():
    losses, in_zero = _synthetic_hurdle()
    hurdle = HurdleMarginal.fit(losses, in_zero)
    grid = np.linspace(1e-6, float(losses.max()), 300)
    values = hurdle.cdf(grid)
    assert np.all(np.diff(values) >= -1e-12)              # non-decreasing
    assert np.all((values >= hurdle.p0 - 1e-9) & (values <= 1.0 + 1e-9))
    # Matches p0 + (1-p0)*G(x) exactly on the positive part.
    g = stats.beta.cdf(grid, *hurdle.positive_params) if hurdle.positive_dist == "beta" \
        else stats.gamma.cdf(grid, *hurdle.positive_params)
    np.testing.assert_allclose(values, hurdle.p0 + (1 - hurdle.p0) * g, rtol=1e-9)


def test_hurdle_ppf_inverts_the_cdf_and_returns_exact_zeros_in_the_atom():
    losses, in_zero = _synthetic_hurdle()
    hurdle = HurdleMarginal.fit(losses, in_zero)
    assert float(hurdle.ppf(hurdle.p0 * 0.5)) == 0.0   # inside the atom -> exact zero
    assert float(hurdle.ppf(hurdle.p0)) == 0.0
    for q in (0.5, 0.75, 0.95):
        assert float(hurdle.cdf(hurdle.ppf(q))) == pytest.approx(q, abs=1e-6)


def test_hurdle_rvs_reproduces_p0_this_is_the_prompt5_sampling_recipe():
    """Prompt 5's LSMC depends on this: exact zeros with probability p0."""
    losses, in_zero = _synthetic_hurdle(p0=0.30)
    hurdle = HurdleMarginal.fit(losses, in_zero)
    draws = hurdle.rvs(50_000, np.random.default_rng(SEED))
    assert float((draws == 0.0).mean()) == pytest.approx(hurdle.p0, abs=0.01)
    assert np.all(draws >= 0.0)


def test_naive_marginal_has_no_atom_which_is_the_defect_being_measured():
    """The naive single-piece fit assigns ~0 probability to an exact zero --
    the smearing whose cost the theta delta quantifies."""
    rng = np.random.default_rng(SEED)
    smeared = stats.beta.rvs(2.0, 5.0, size=5000, random_state=rng) + 0.024
    naive = NaiveMarginal.fit(smeared)
    assert float(naive.cdf(0.0)) < 0.01


def test_hurdle_rejects_malformed_input():
    with pytest.raises(ValueError, match="same length"):
        HurdleMarginal.fit(np.zeros(5), np.ones(3, dtype=bool))
    with pytest.raises(ValueError, match="insufficient heat-exposure days"):
        HurdleMarginal.fit(np.array([0.0, 0.1]), np.array([True, False]))


# --- tie handling ---------------------------------------------------------


def test_copula_fit_survives_an_atom_heavy_sample_and_recovers_theta():
    """TIE HANDLING: with ~30% of observations sharing the atom value, the fit
    must run AND still recover the generating theta within tolerance.

    Construction: draw (u,v) from a known Gumbel, push v through a hurdle
    quantile function so a 30% block collapses to exactly 0, then rebuild
    pseudo-observations with the distributional transform. Recovering theta
    proves the transform undoes the tie damage rather than merely not crashing.

    WHY THE TOLERANCE IS 10% HERE AND 5% FOR CLEAN DATA: an atom genuinely
    destroys information. Every observation in it has the identical loss, so
    their relative order carries no signal, and the distributional transform
    correctly refuses to invent one -- it inserts independent noise across the
    atom's CDF interval. Theta is therefore ATTENUATED toward independence, and
    the copula is not uniquely identified from data with ties at all (Genest &
    Neslehova 2007). Measured attenuation at theta=2.5 is about -1% at a 10%
    atom, -7% at 30%, and -8% at 33.5%. That is a property of the estimand, not
    a defect in this code, and test_atom_attenuation_is_systematic pins it down.
    """
    rng = np.random.default_rng(SEED)
    true_theta = 2.5
    u, v = GumbelSurvivalCopula(true_theta).sample(60_000, rng)

    losses, in_zero = _synthetic_hurdle(n=60_000, p0=0.30)
    hurdle = HurdleMarginal.fit(losses, in_zero)
    # v -> loss with a real atom; ~30% become exactly 0 (a huge tie block).
    v_losses = hurdle.ppf(v)
    assert float((v_losses == 0.0).mean()) == pytest.approx(0.30, abs=0.02)

    v_pseudo = distributional_transform(v_losses, hurdle.cdf, hurdle.cdf_left_limit,
                                        np.random.default_rng(JITTER_SEED))
    refit = GumbelSurvivalCopula.fit(u, v_pseudo)
    assert abs(refit.theta - true_theta) / true_theta < 0.10, \
        f"atom-heavy refit theta={refit.theta:.4f} vs true {true_theta}"
    # Attenuation is toward INDEPENDENCE (downward), never upward.
    assert refit.theta < true_theta


def test_atom_attenuation_is_systematic_and_toward_independence():
    """Pins the attenuation the hurdle fit is subject to, so the naive-vs-hurdle
    theta delta reported in copula.json can be corrected for it rather than
    being mistaken entirely for 'the cost of Prompt 3's smearing'.

    Attenuation must grow monotonically with the atom size and always pull
    theta DOWN toward independence.
    """
    true_theta = 2.5
    measured = {}
    for p0 in (0.0, 0.10, 0.30):
        rng = np.random.default_rng(7)
        u, v = GumbelSurvivalCopula(true_theta).sample(40_000, rng)
        if p0 == 0.0:
            v_pseudo = v
        else:
            hurdle = HurdleMarginal(p0=p0, positive_dist="beta",
                                    positive_params=(2.0, 5.0, 0.0, 1.0),
                                    n_zero=0, n_positive=0, positive_aic={})
            v_pseudo = distributional_transform(
                hurdle.ppf(v), hurdle.cdf, hurdle.cdf_left_limit,
                np.random.default_rng(JITTER_SEED))
        measured[p0] = GumbelSurvivalCopula.fit(u, v_pseudo).theta

    assert measured[0.0] == pytest.approx(true_theta, rel=0.03)  # no atom -> no bias
    assert measured[0.30] < measured[0.10] < measured[0.0]       # monotone attenuation
    assert measured[0.30] < true_theta


def test_distributional_transform_yields_uniform_pseudo_observations():
    """The reason mid-ranks are rejected: only the transform keeps V uniform."""
    losses, in_zero = _synthetic_hurdle(n=40_000, p0=0.30)
    hurdle = HurdleMarginal.fit(losses, in_zero)

    v_dt = distributional_transform(losses, hurdle.cdf, hurdle.cdf_left_limit,
                                    np.random.default_rng(JITTER_SEED))
    assert stats.kstest(v_dt, "uniform").statistic < 0.02
    assert np.all((v_dt >= 0) & (v_dt <= 1))
    # The atom must be spread across the WHOLE interval [0, p0] it occupies.
    assert v_dt[in_zero].max() == pytest.approx(hurdle.p0, rel=0.02)

    # Mid-ranks pin the entire atom to one value -> a visible point mass.
    v_mid = mid_rank_transform(losses, hurdle.cdf, hurdle.cdf_left_limit)
    assert float(np.mean(np.isclose(v_mid, hurdle.p0 / 2))) > 0.25
    assert stats.kstest(v_mid, "uniform").statistic > 0.1


def test_empirical_pseudo_obs_are_uniform_and_rank_based():
    rng = np.random.default_rng(SEED)
    x = rng.normal(size=5000)
    p = empirical_pseudo_obs(x)
    assert np.all((p > 0) & (p < 1))
    assert stats.kstest(p, "uniform").statistic < 0.02


# --- F_H ------------------------------------------------------------------


def test_fit_gev_recovers_known_gev_parameters():
    rng = np.random.default_rng(SEED)
    sample = stats.genextreme.rvs(0.2, loc=30.0, scale=3.0, size=20_000, random_state=rng)
    gev = fit_gev(sample)
    assert gev["params"]["c"] == pytest.approx(0.2, abs=0.05)
    assert gev["params"]["loc"] == pytest.approx(30.0, abs=0.2)
    assert gev["params"]["scale"] == pytest.approx(3.0, abs=0.2)
    assert gev["gev_is_best_by_aic"]
    assert not gev["ks_rejects_at_5pct"], "GEV must fit data that IS GEV"


def test_fit_gev_reports_rejection_on_data_that_is_not_gev():
    """The KS gate must actually bite -- otherwise the honest caveat is worthless."""
    rng = np.random.default_rng(SEED)
    bimodal = np.concatenate([rng.normal(20, 1, 3000), rng.normal(32, 1, 3000)])
    gev = fit_gev(bimodal)
    assert gev["ks_rejects_at_5pct"]


def test_fit_gev_rejects_tiny_samples():
    with pytest.raises(ValueError, match=">=30"):
        fit_gev(np.arange(10.0))
