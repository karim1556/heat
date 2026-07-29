"""Basis risk: the gap between an INDEX-triggered payout and the worker's ACTUAL
loss. This is the core risk of ANY parametric product -- the payout keys off an
objective index, not an assessment of the individual's loss, so the two can
diverge. Quantifying it honestly is what separates a real product from a demo.

TWO DISTINCT COMPUTATIONS, deliberately kept separate (do not conflate):

  (A) basis_risk_simulated  -- per policy, over the M simulated MC paths inside
      price_window. "For THIS policy, how well does the index payout track the
      modeled loss, in expectation over the simulated climate?" Returned in
      price_window's `basis_risk` field.

  (B) basis_risk_empirical  -- portfolio level, over the real historical replay
      (Prompt 6), across all worker-days. A standalone function the backtest
      calls; price_window never touches it.

Both report the SAME four quantities, via one shared kernel so they cannot drift:
    basis_risk_rmse : RMSE(payout - actual_loss)
    shortfall_rate  : P(actual_loss > payout)   -- worker UNDER-compensated
    overpay_rate    : P(payout > actual_loss)   -- insurer OVER-pays
    correlation     : corr(payout, actual_loss)

DEGENERACY GUARD lives HERE, where the payout-vs-loss pairing is actually
assembled -- NOT in price_window, which only ever sees the correct
index-vs-own-loss pairing and so cannot commit the error. If payout and
actual_loss are effectively comonotone (Spearman >= 0.999) the pairing has no
basis risk at all and would massively overstate product performance; that is the
degenerate own-node case Prompt 4 warned about (loss a deterministic monotone
function of the worker's own heat), and it is refused outright.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import spearmanr

COMONOTONE_SPEARMAN = 0.999


class DegenerateBasisRiskError(ValueError):
    """Raised when payout and actual_loss are effectively comonotone."""


def _check_not_comonotone(payout: np.ndarray, actual_loss: np.ndarray) -> None:
    # Spearman is undefined if either series is constant; a constant payout or
    # loss is not the comonotone degeneracy this guard targets, so allow it.
    if np.ptp(payout) == 0.0 or np.ptp(actual_loss) == 0.0:
        return
    rho = spearmanr(payout, actual_loss).statistic
    if np.isfinite(rho) and rho >= COMONOTONE_SPEARMAN:
        raise DegenerateBasisRiskError(
            f"payout and actual_loss are effectively comonotone (Spearman={rho:.5f} "
            f">= {COMONOTONE_SPEARMAN}). This pairing has NO basis risk and would "
            f"overstate product performance. You are almost certainly pricing the "
            f"degenerate own-node case (Prompt 3 makes loss a deterministic monotone "
            f"function of the worker's own heat). Pricing MUST use the city-index "
            f"trigger vs own-loss pairing that Prompt 4 fit theta on."
        )


def _basis_risk_kernel(payout: np.ndarray, actual_loss: np.ndarray) -> dict:
    """The shared four-quantity computation. No guard here -- callers guard."""
    payout = np.asarray(payout, dtype=float).reshape(-1)
    actual_loss = np.asarray(actual_loss, dtype=float).reshape(-1)
    if len(payout) != len(actual_loss):
        raise ValueError("payout and actual_loss must be the same length")
    if len(payout) == 0:
        raise ValueError("need at least one observation")

    gap = payout - actual_loss
    rmse = float(np.sqrt(np.mean(gap**2)))
    shortfall_rate = float(np.mean(actual_loss > payout))
    overpay_rate = float(np.mean(payout > actual_loss))

    # Pearson correlation; undefined (reported as 0.0) if either side is constant,
    # e.g. an all-zero payout window -- that is "no linear co-movement", not an error.
    if np.ptp(payout) == 0.0 or np.ptp(actual_loss) == 0.0:
        correlation = 0.0
    else:
        correlation = float(np.corrcoef(payout, actual_loss)[0, 1])

    return {
        "basis_risk_rmse": rmse,
        "shortfall_rate": shortfall_rate,
        "overpay_rate": overpay_rate,
        "correlation": correlation,
    }


def basis_risk_simulated(payout: np.ndarray, actual_loss: np.ndarray,
                         guard: bool = True) -> dict:
    """(A) Per-policy basis risk over simulated MC paths (used by price_window).

    payout / actual_loss are flattened over all (path, day) pairs of one policy.
    """
    payout = np.asarray(payout, dtype=float).reshape(-1)
    actual_loss = np.asarray(actual_loss, dtype=float).reshape(-1)
    if guard:
        _check_not_comonotone(payout, actual_loss)
    return _basis_risk_kernel(payout, actual_loss)


def basis_risk_empirical(payouts: np.ndarray, actual_losses: np.ndarray,
                         guard: bool = True) -> dict:
    """(B) Portfolio-level basis risk over the real historical replay (Prompt 6).

    payouts / actual_losses are one value per worker-day across the whole
    backtest. Standalone -- price_window does not call this.
    """
    payouts = np.asarray(payouts, dtype=float).reshape(-1)
    actual_losses = np.asarray(actual_losses, dtype=float).reshape(-1)
    if guard:
        _check_not_comonotone(payouts, actual_losses)
    return _basis_risk_kernel(payouts, actual_losses)
