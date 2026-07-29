"""Wang transform: a distortion risk measure for loading the actuarial premium.

The LSMC premium is a plain expectation of the discounted payoff -- the pure
risk-neutral / actuarially-fair price. A real insurer charges more, to be
compensated for bearing risk. The Wang (2000) transform loads that risk by
distorting the payoff's SURVIVAL function toward its tail:

    g_lambda(u) = Phi( Phi^{-1}(u) + lambda_w )

where u is a survival probability, Phi the standard-normal CDF, and lambda_w the
MARKET PRICE OF RISK. For lambda_w > 0, g_lambda(u) > u for all u in (0,1): every
exceedance probability is inflated, so the distorted expectation puts more weight
on large losses and the premium rises.

NAMING GUARD (a real, easy error): lambda_w here -- the Wang market price of
risk -- is a COMPLETELY DIFFERENT quantity from the copula's lambda_U, the
upper-tail dependence 2 - 2^(1/theta) = 0.835 from Prompt 4. They share only a
Greek letter. This module names it `market_price_of_risk` / `lambda_w` and never
writes a bare `lambda_U`; the two must never be interchanged.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm


def g_lambda(u, lambda_w: float):
    """Wang distortion g_lambda(u) = Phi(Phi^{-1}(u) + lambda_w).

    Monotone increasing, maps [0,1] onto [0,1], fixes 0 and 1. For lambda_w > 0
    it lies strictly above the identity on (0,1) (proven in the tests), which is
    exactly the risk loading.
    """
    u = np.asarray(u, dtype=float)
    out = norm.cdf(norm.ppf(u) + lambda_w)
    # Pin the fixed points: Phi^{-1}(0)=-inf, Phi^{-1}(1)=+inf give NaN otherwise.
    out = np.where(u <= 0.0, 0.0, out)
    out = np.where(u >= 1.0, 1.0, out)
    return out if out.ndim else float(out)


def wang_premium(payoffs: np.ndarray, lambda_w: float) -> float:
    """Distorted expectation of a sample of (discounted) payoffs.

        E_g[X] = integral_0^inf g_lambda(S(x)) dx   (X >= 0 here: payoffs are
                 non-negative insurance payouts)

    Computed on the empirical distribution: sort the payoffs ascending, and
    weight each by the DROP in the distorted survival function across its step,

        E_g[X] = sum_i x_(i) * [ g(S(x_(i-1))) - g(S(x_(i))) ]

    with S the empirical survival function (S(x_(k)) = (n-k)/n after sorting).
    For lambda_w = 0 this collapses to the plain sample mean (g = identity),
    and for lambda_w > 0 it is >= the mean (verified in the tests). This is the
    standard distortion-risk-measure estimator; no distributional assumption on
    the payoff is made.
    """
    x = np.sort(np.asarray(payoffs, dtype=float))
    n = len(x)
    if n == 0:
        raise ValueError("need at least one payoff")
    if np.any(x < 0):
        raise ValueError("wang_premium assumes non-negative payoffs (insurance payouts)")

    # Distorted survival at each step boundary: S(x_(k)) = (n - k)/n, k=0..n.
    survival = (n - np.arange(0, n + 1)) / n
    distorted = g_lambda(survival, lambda_w)
    # Weight of the i-th order statistic = g(S_{i-1}) - g(S_i).
    weights = distorted[:-1] - distorted[1:]
    return float(np.dot(x, weights))
