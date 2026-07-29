"""Gumbel copula and its survival function, for fusing heat and wage loss.

NAMING, stated up front because this is a classic silent error: this class fits
a GUMBEL copula and exposes its SURVIVAL FUNCTION

    survival_cdf(u,v) = P(U > u, V > v) = 1 - u - v + C(u,v)

which is the joint-exceedance probability the mu-TEVI index is built from. It is
NOT the "survival copula" in the rotated sense, Chat(u,v) = u+v-1+C(1-u,1-v).
The distinction matters and is not cosmetic: the Gumbel copula has UPPER tail
dependence lambda_U = 2 - 2^(1/theta) and zero lower tail dependence, whereas
the ROTATED survival copula has those swapped (lower dependence 2 - 2^(1/theta),
upper zero). Upper tail dependence is what we want here -- it asks "given the
heat trigger is extreme, is the wage loss extreme too", which is exactly the
basis-risk question a parametric contract lives or dies on. Getting these
backwards would invert the tail behaviour while every shape test still passed.

    C(u,v)   = exp( -[ (-ln u)^theta + (-ln v)^theta ]^(1/theta) ),  theta >= 1
    tau      = 1 - 1/theta
    lambda_U = 2 - 2^(1/theta)

theta = 1 is independence; theta -> infinity is comonotonicity.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp

# theta must be >= 1 for the Gumbel to be a valid copula. The upper bound is a
# numerical guard: beyond this the copula is comonotone for all practical
# purposes and the MLE surface is flat, so a fit that lands on the bound is
# reported as such rather than passed off as an estimate.
THETA_MIN = 1.0
THETA_MAX = 50.0

_EPS = 1e-10


def _clip_uv(u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    u = np.clip(np.asarray(u, dtype=float), _EPS, 1.0 - _EPS)
    v = np.clip(np.asarray(v, dtype=float), _EPS, 1.0 - _EPS)
    return u, v


class GumbelSurvivalCopula:
    """Gumbel copula with MLE fitting and a joint-survival function."""

    def __init__(self, theta: float):
        if theta < THETA_MIN:
            raise ValueError(f"theta must be >= {THETA_MIN}, got {theta}")
        self.theta = float(theta)
        self.fit_hit_bound = False

    def __repr__(self) -> str:
        return f"GumbelSurvivalCopula(theta={self.theta:.4f}, lambda_U={self.upper_tail_dependence():.4f})"

    # -- core ------------------------------------------------------------

    def cdf(self, u, v) -> np.ndarray:
        """C(u,v) = exp(-[(-ln u)^theta + (-ln v)^theta]^(1/theta))."""
        u, v = _clip_uv(u, v)
        x, y = -np.log(u), -np.log(v)
        # logsumexp keeps x^theta + y^theta from overflowing at large theta.
        log_w = logsumexp(np.stack([self.theta * np.log(x), self.theta * np.log(y)]),
                          axis=0) / self.theta
        out = np.exp(-np.exp(log_w))
        return out if out.ndim else float(out)

    def survival_cdf(self, u, v) -> np.ndarray:
        """P(U > u, V > v) = 1 - u - v + C(u,v). Joint EXCEEDANCE probability."""
        u, v = _clip_uv(u, v)
        out = 1.0 - u - v + self.cdf(u, v)
        return out if out.ndim else float(out)

    def upper_tail_dependence(self) -> float:
        """lambda_U = 2 - 2^(1/theta) = lim P(V > q | U > q) as q -> 1."""
        return float(2.0 - 2.0 ** (1.0 / self.theta))

    def kendall_tau(self) -> float:
        """tau = 1 - 1/theta (closed form for the Gumbel)."""
        return float(1.0 - 1.0 / self.theta)

    # -- likelihood ------------------------------------------------------

    @staticmethod
    def _log_density(u: np.ndarray, v: np.ndarray, theta: float) -> np.ndarray:
        """log c(u,v), the copula density.

        Derived by differentiating C twice (verified against the standard form
        in Nelsen 4.2.2 and, in the tests, against a numerical mixed partial):

            c = exp(-w) * (x y)^(theta-1) * w^(1-2 theta) * (w + theta - 1) / (u v)

        with x = -ln u, y = -ln v, w = (x^theta + y^theta)^(1/theta). Since
        -ln u - ln v = x + y, the log form below adds (x + y) rather than
        subtracting logs. At theta = 1 this collapses to log c = 0
        (independence), which the tests check explicitly.
        """
        u, v = _clip_uv(u, v)
        x, y = -np.log(u), -np.log(v)
        log_x, log_y = np.log(x), np.log(y)
        log_w = logsumexp(np.stack([theta * log_x, theta * log_y]), axis=0) / theta
        w = np.exp(log_w)
        return (
            -w
            + (theta - 1.0) * (log_x + log_y)
            + (1.0 - 2.0 * theta) * log_w
            + np.log(w + theta - 1.0)
            + x
            + y
        )

    def log_likelihood(self, u, v) -> float:
        return float(np.sum(self._log_density(u, v, self.theta)))

    @classmethod
    def fit(cls, u, v, bounds: tuple[float, float] = (THETA_MIN, THETA_MAX)) -> GumbelSurvivalCopula:
        """MLE for theta via bounded scalar minimization of the negative log-likelihood."""
        u, v = _clip_uv(u, v)
        if len(u) != len(v):
            raise ValueError("u and v must be the same length")

        def nll(theta: float) -> float:
            value = -np.sum(cls._log_density(u, v, theta))
            return value if np.isfinite(value) else np.inf

        result = minimize_scalar(nll, bounds=bounds, method="bounded",
                                 options={"xatol": 1e-8})
        copula = cls(float(result.x))
        # A fit pinned to the upper bound means the data are effectively
        # comonotone and theta is NOT identified -- flagged, never silently
        # reported as a point estimate.
        copula.fit_hit_bound = bool(np.isclose(result.x, bounds[1], rtol=1e-3))
        return copula

    # -- sampling --------------------------------------------------------

    @staticmethod
    def _positive_stable(alpha: float, size: int, rng: np.random.Generator) -> np.ndarray:
        """Positive alpha-stable variates with Laplace transform E[e^{-tS}] = e^{-t^alpha}.

        Kanter (1975) / Chambers-Mallows-Stuck representation. This exact
        Laplace transform is what makes the Marshall-Olkin construction below
        produce a Gumbel copula, so the tests verify the LT numerically rather
        than trusting the formula.
        """
        if not 0 < alpha < 1:
            raise ValueError(f"alpha must be in (0,1), got {alpha}")
        theta_u = rng.uniform(0.0, np.pi, size)
        w = rng.exponential(1.0, size)
        term1 = np.sin(alpha * theta_u) / np.sin(theta_u) ** (1.0 / alpha)
        term2 = (np.sin((1.0 - alpha) * theta_u) / w) ** ((1.0 - alpha) / alpha)
        return term1 * term2

    def sample(self, size: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        """Draw (U,V) ~ Gumbel copula via the Marshall-Olkin frailty construction.

        The Gumbel generator's inverse psi(t) = exp(-t^(1/theta)) is the Laplace
        transform of a positive (1/theta)-stable variate V, so with E_j ~ Exp(1)
        independent, U_j = psi(E_j / V) has the Gumbel copula as its joint law.
        """
        if self.theta == 1.0:
            return rng.random(size), rng.random(size)
        alpha = 1.0 / self.theta
        frailty = self._positive_stable(alpha, size, rng)
        e1 = rng.exponential(1.0, size)
        e2 = rng.exponential(1.0, size)
        return (np.exp(-((e1 / frailty) ** alpha)),
                np.exp(-((e2 / frailty) ** alpha)))


def distributional_transform(x: np.ndarray, cdf, cdf_left_limit,
                             rng: np.random.Generator) -> np.ndarray:
    """Pseudo-observations for a marginal WITH AN ATOM (Rueschendorf 2009).

        V = F(x-) + U * (F(x) - F(x-)),   U ~ Uniform(0,1) independent

    WHY NOT MID-RANKS: a hurdle marginal puts ~33% of observations at exactly
    one value, so F(x) pins every one of them to the identical pseudo-value.
    That is a point mass in the pseudo-observations, which are then NOT uniform,
    and a copula MLE fitted on non-uniform margins is biased -- silently, since
    it still converges and returns a plausible theta. The distributional
    transform spreads the atom uniformly across the CDF interval it occupies
    ([0, p0] for the zero atom), restoring exact uniformity.

    The randomization is honest about what the data contain: within the atom all
    losses are exactly equal, so their relative ORDER carries no information, and
    the transform declines to invent any.
    """
    x = np.asarray(x, dtype=float)
    upper = np.asarray(cdf(x), dtype=float)
    lower = np.asarray(cdf_left_limit(x), dtype=float)
    return lower + rng.random(len(x)) * (upper - lower)


def mid_rank_transform(x: np.ndarray, cdf, cdf_left_limit) -> np.ndarray:
    """Mid-rank pseudo-observations: V = (F(x-) + F(x)) / 2.

    Deterministic alternative to the distributional transform, kept ONLY as a
    robustness check so the reported theta can be shown not to hinge on which
    tie convention was chosen.
    """
    x = np.asarray(x, dtype=float)
    return 0.5 * (np.asarray(cdf_left_limit(x), dtype=float)
                  + np.asarray(cdf(x), dtype=float))


def empirical_pseudo_obs(x: np.ndarray) -> np.ndarray:
    """Rank-based pseudo-observations r_i/(n+1), average ranks for ties.

    Used as a robustness check: these depend on the data only through its ranks,
    so a theta fitted on them is immune to marginal misspecification (which
    matters here because the GEV fit for F_H is imperfect).
    """
    from scipy.stats import rankdata

    x = np.asarray(x, dtype=float)
    return rankdata(x, method="average") / (len(x) + 1.0)
