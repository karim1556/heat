"""Genuinely naive flat-rate premium -- the baseline the LSMC pricer must beat.

A flat-rate product charges every worker the same premium regardless of heat
exposure, occupation, or location: premium = (average historical payout per
window) with a small expense/solvency loading. This is what an unsophisticated
insurer, or a government scheme with no climate model, actually does.

IT IS NOT A STRAWMAN. It is calibrated to the SAME realized payouts the LSMC
pricer is scored against, so it is the fair-average premium -- the honest thing
to beat. The point of the whole project (CLAUDE.md: >=20% lower MAPE than a
flat-rate baseline) is that a flat rate misprices INDIVIDUAL policies badly even
when it is right ON AVERAGE, because it ignores who is actually exposed.

NOTE for Prompt 6: the MAPE comparison must be made on the BASIS-RISK reality
(index trigger vs actual loss), NOT the degenerate own-node case, or the >=20%
claim is measured against a strawman.
"""

from __future__ import annotations

import numpy as np

# A modest expense + solvency loading on top of the pure average payout. Flat
# social-insurance schemes commonly run near cost; 10% is deliberately small so
# the baseline is not handicapped.
DEFAULT_LOADING = 0.10


class FlatRatePricer:
    """One premium for everyone, calibrated to the average historical payout."""

    def __init__(self, flat_premium: float, loading: float = DEFAULT_LOADING):
        self.flat_premium = float(flat_premium)
        self.loading = float(loading)

    @classmethod
    def calibrate(cls, historical_window_payouts: np.ndarray,
                  loading: float = DEFAULT_LOADING) -> FlatRatePricer:
        """flat premium = mean realized payout per window * (1 + loading).

        `historical_window_payouts` is one total payout per historical policy
        window (whatever the contract paid over that window), so the flat rate
        is genuinely the break-even average plus a small load.
        """
        payouts = np.asarray(historical_window_payouts, dtype=float)
        if payouts.ndim != 1 or len(payouts) == 0:
            raise ValueError("need a 1-D non-empty array of per-window payouts")
        if np.any(payouts < 0):
            raise ValueError("payouts must be non-negative")
        return cls(float(payouts.mean()) * (1.0 + loading), loading)

    def price(self, n_policies: int = 1) -> np.ndarray:
        """The identical premium, repeated -- it does not depend on the policy."""
        return np.full(int(n_policies), self.flat_premium, dtype=float)

    def price_window(self, *_args, **_kwargs) -> float:
        """Same flat premium regardless of the window -- that is the whole point."""
        return self.flat_premium
