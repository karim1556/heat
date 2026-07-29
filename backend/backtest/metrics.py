"""Backtest metrics: MAPE, premium-to-payout ratio, portfolio VaR/CVaR, and the
[NEW] diagnostics carried from Prompt 5 -- empirical basis risk, trigger/payout
frequency, and the real-data persistence-premium gap.

VaR/CVaR SUBJECT, stated explicitly per the prompt: these are computed on the
INSURER'S PAYOUT LIABILITY (aggregate daily payouts owed across the portfolio),
NOT on workers' wage losses. This is the "how much capital must the insurer
hold" question -- the loss variable IS the payout the insurer pays out.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from models.pricing.basis_risk import basis_risk_empirical  # re-exported, reused verbatim
from models.pricing.lsmc_pricer import LSMCPricer, persistence_premium_gap

__all__ = [
    "mae", "tail_weighted_error", "mae_win_rate", "bootstrap_mae_difference",
    "mape", "premium_to_payout_ratio", "value_at_risk", "expected_shortfall",
    "basis_risk_empirical", "trigger_rate", "payout_frequency",
    "real_persistence_premium_gap",
]


def _abs_errors(actual: np.ndarray, predicted: np.ndarray, nonzero_only: bool,
                min_actual: float) -> tuple[np.ndarray, np.ndarray]:
    """Absolute errors |actual - predicted|, and the boolean include-mask.

    Shared by every absolute-error metric below so they all score the SAME
    sample. `nonzero_only` scores only the windows where a payout actually
    occurred -- the windows on which pricing accuracy is testable, and the same
    sample MAPE is forced onto. This is deliberate, not incidental: including
    the zero-payout windows would compare each model's (fixed, positive) premium
    against a realized payout of 0, which REWARDS THE LOWER PREMIUM regardless of
    which model is better -- exactly the under-prediction bias that makes MAPE
    the wrong metric here. Aggregate calibration over the whole book (zeros
    included) is captured separately by premium_to_payout_ratio.
    """
    actual = np.asarray(actual, dtype=float).reshape(-1)
    predicted = np.asarray(predicted, dtype=float).reshape(-1)
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must be the same length")
    if len(actual) == 0:
        raise ValueError("need at least one observation")
    mask = (np.abs(actual) > min_actual) if nonzero_only else np.ones(len(actual), bool)
    return np.abs(actual - predicted), mask


def mae(actual: np.ndarray, predicted: np.ndarray, nonzero_only: bool = True,
       min_actual: float = 1e-9) -> dict:
    """Mean Absolute Error -- the PRIMARY headline metric (see docs/METRIC_AMENDMENT.md).

    Symmetric, in the payout's own currency units, and DEFINED on every window
    (no division by the actual value), so unlike MAPE it neither blows up on the
    zero-inflated small-loss mass nor structurally rewards under-prediction.
    Scored on the nonzero-actual sample by default -- see _abs_errors.
    """
    errors, mask = _abs_errors(actual, predicted, nonzero_only, min_actual)
    if mask.sum() == 0:
        raise ValueError("no observations in the scored sample")
    return {
        "mae": float(errors[mask].mean()),
        "n_included": int(mask.sum()),
        "n_excluded": int((~mask).sum()),
        "n_total": int(len(errors)),
    }


def tail_weighted_error(actual: np.ndarray, predicted: np.ndarray,
                        tail_quantile: float = 0.9, min_actual: float = 1e-9) -> dict:
    """Mean absolute error CONDITIONAL on the actual being in the upper tail --
    the error on the largest-loss windows, which is what insurance economics
    turn on.

    Defined as the mean of |actual - predicted| over the windows where
    actual >= quantile(actual, tail_quantile). A conditional / CVaR-style error:
    at tail_quantile = 0 the threshold is the sample minimum, every window
    qualifies, and this reduces EXACTLY to plain MAE (asserted in the tests).
    At 0.9 it is the MAE on the worst 10% of windows.

    Weighting the tail is the honest emphasis for a heat-payout product: the
    flat baseline's fixed low premium is catastrophically wrong on the big
    windows precisely because it is priced to minimize error against the many
    small ones -- the tail is where that trade-off is exposed.
    """
    if not 0.0 <= tail_quantile < 1.0:
        raise ValueError(f"tail_quantile must be in [0, 1), got {tail_quantile}")
    actual = np.asarray(actual, dtype=float).reshape(-1)
    predicted = np.asarray(predicted, dtype=float).reshape(-1)
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must be the same length")
    # Score over the nonzero-actual sample (the tail is large-actual by
    # construction; at tail_quantile=0 this still reduces to MAE of that sample).
    nonzero = np.abs(actual) > min_actual if tail_quantile > 0 else np.ones(len(actual), bool)
    a, p = actual[nonzero], predicted[nonzero]
    if len(a) == 0:
        raise ValueError("no observations in the scored sample")
    threshold = float(np.quantile(a, tail_quantile))
    tail = a >= threshold
    return {
        "tail_weighted_error": float(np.abs(a[tail] - p[tail]).mean()),
        "tail_quantile": tail_quantile,
        "tail_threshold": threshold,
        "n_tail": int(tail.sum()),
    }


def mae_win_rate(actual: np.ndarray, predicted_a: np.ndarray, predicted_b: np.ndarray,
                nonzero_only: bool = True, min_actual: float = 1e-9) -> float:
    """Fraction of windows on which model A has the strictly smaller absolute
    error than model B -- a per-window robustness check that the aggregate MAE
    lead is not carried by a few windows."""
    err_a, mask = _abs_errors(actual, predicted_a, nonzero_only, min_actual)
    err_b, _ = _abs_errors(actual, predicted_b, nonzero_only, min_actual)
    return float((err_a[mask] < err_b[mask]).mean())


def bootstrap_mae_difference(actual: np.ndarray, predicted_a: np.ndarray,
                             predicted_b: np.ndarray, n_boot: int = 10_000,
                             seed: int = 42, nonzero_only: bool = True,
                             min_actual: float = 1e-9) -> dict:
    """Bootstrap CI on MAE(B) - MAE(A) over the scored windows.

    A is the model under test (the full model), B the comparator (baseline), so
    a POSITIVE difference means A has the smaller error -- A is better. A 95% CI
    that excludes 0 means the lead is robust to resampling; a CI straddling 0
    means it is fragile, and the report must say so rather than present it as
    solid. Seed logged for reproducibility.
    """
    err_a, mask = _abs_errors(actual, predicted_a, nonzero_only, min_actual)
    err_b, _ = _abs_errors(actual, predicted_b, nonzero_only, min_actual)
    ea, eb = err_a[mask], err_b[mask]
    n = len(ea)
    if n == 0:
        raise ValueError("no observations in the scored sample")
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        diffs[i] = eb[idx].mean() - ea[idx].mean()
    point = float(eb.mean() - ea.mean())
    lo, hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
    return {
        "mae_difference": point,
        "ci_low": lo,
        "ci_high": hi,
        "ci_excludes_zero": bool(lo > 0.0),
        "improvement_pct": point / float(eb.mean()) * 100.0,
        "improvement_pct_ci": [lo / float(eb.mean()) * 100.0, hi / float(eb.mean()) * 100.0],
        "n_boot": n_boot,
        "seed": seed,
        "n_scored": n,
    }


def mape(actual: np.ndarray, predicted: np.ndarray, min_actual: float = 1e-9) -> dict:
    """Mean Absolute Percentage Error, with the zero-actual case handled honestly.

    A percentage error against an exactly-zero actual is undefined (division by
    zero), not "large" -- the standard convention (and the only one that does not
    silently distort the headline number) is to compute MAPE over the
    NON-ZERO-actual observations only, and report how many were excluded so the
    sample size is never hidden.
    """
    actual = np.asarray(actual, dtype=float).reshape(-1)
    predicted = np.asarray(predicted, dtype=float).reshape(-1)
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must be the same length")
    if len(actual) == 0:
        raise ValueError("need at least one observation")

    included = np.abs(actual) > min_actual
    n_excluded = int((~included).sum())
    if included.sum() == 0:
        raise ValueError("every actual value is ~0 -- MAPE is undefined for this sample")

    ape = np.abs((actual[included] - predicted[included]) / actual[included]) * 100.0
    return {
        "mape": float(ape.mean()),
        "n_included": int(included.sum()),
        "n_excluded_zero_actual": n_excluded,
        "n_total": int(len(actual)),
    }


def premium_to_payout_ratio(premiums: np.ndarray, payouts: np.ndarray) -> float:
    """sum(premiums collected) / sum(payouts paid). >1 = insurer collects more
    than it pays out (solvent on average); <1 = collects less (insolvent trend)."""
    premiums = np.asarray(premiums, dtype=float)
    payouts = np.asarray(payouts, dtype=float)
    total_payout = float(payouts.sum())
    if total_payout == 0.0:
        return float("inf") if premiums.sum() > 0 else float("nan")
    return float(premiums.sum() / total_payout)


def value_at_risk(losses: np.ndarray, alpha: float) -> float:
    """VaR_alpha: the alpha-quantile of the loss distribution (empirical).

    losses = the insurer's payout liability (see module docstring), NOT wage
    loss. VaR_95 = the payout level exceeded only 5% of the time.
    """
    losses = np.asarray(losses, dtype=float)
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0,1), got {alpha}")
    return float(np.quantile(losses, alpha))


def expected_shortfall(losses: np.ndarray, alpha: float) -> float:
    """ES_alpha (CVaR): mean loss in the tail beyond VaR_alpha."""
    losses = np.asarray(losses, dtype=float)
    var = value_at_risk(losses, alpha)
    tail = losses[losses >= var]
    if len(tail) == 0:
        return var
    return float(tail.mean())


def trigger_rate(window_summary: pd.DataFrame) -> float:
    """Fraction of WINDOWS (policy periods) in which the index trigger fired
    at least once. One row per window (dedupe across occupations, since the
    trigger is a single city-level event shared by every occupation)."""
    per_window = window_summary.drop_duplicates("window_id")
    return float(per_window["triggered"].mean())


def payout_frequency(n_claim_events: int, n_workers: int, n_days: int) -> float:
    """Fraction of WORKER-DAYS that actually received a payout.

    Denominator is n_workers x n_days -- the TRUE daily worker-day count, not
    n_workers x n_windows. This is a deliberate, load-bearing choice: under the
    one-shot contract each worker claims AT MOST ONCE per window (on their
    single best day), so using n_windows as the denominator would make
    n_claim_events/(n_workers*n_windows) ALGEBRAICALLY COLLAPSE to trigger_rate
    whenever every worker claims in every triggering window (n_claim_events =
    n_triggered_windows * n_workers exactly) -- caught by testing this: an
    earlier version used n_windows and the two "distinct" diagnostics came out
    numerically identical. With n_days, payout_frequency answers "on any given
    day, what is the chance THIS worker gets paid" -- a genuinely different,
    much smaller number than trigger_rate ("in any given policy period, does
    the shared trigger fire at all"), which is the contrast the diagnostic
    exists to show.
    """
    if n_workers <= 0 or n_days <= 0:
        raise ValueError("n_workers and n_days must be > 0")
    return float(n_claim_events / (n_workers * n_days))


def real_persistence_premium_gap(pricer: LSMCPricer, city_index: pd.DataFrame,
                                 window_days: int, n_paths: int,
                                 seed: int = 42) -> dict:
    """The real-data analogue of Prompt 5's simulated ~7% i.i.d.-vs-persistent
    gap, computed by REUSING models.pricing.lsmc_pricer.persistence_premium_gap
    (no new method invented) over every real, non-overlapping window.

    Only windows where the REAL ordered premium is nonzero are included (a
    window whose real values never reach the strike gives 0/0 -- undefined,
    not zero -- under EITHER ordering, since reordering cannot change the max
    of a fixed multiset of values).
    """
    from backend.backtest.historical_replay import windows  # local import: backtest -> pricing is
                                                              # the intended direction, not the reverse

    mutevi = city_index["mu_tevi"].to_numpy()
    win_bounds = windows(len(mutevi), window_days)
    rng = np.random.default_rng(seed)

    gaps = []
    n_undefined = 0
    for start, end in win_bounds:
        window = mutevi[start:end]
        gap = persistence_premium_gap(pricer, window, n_paths, rng)
        if np.isfinite(gap):
            gaps.append(gap)
        else:
            n_undefined += 1

    return {
        "mean_gap_pct": float(np.mean(gaps)) if gaps else float("nan"),
        "median_gap_pct": float(np.median(gaps)) if gaps else float("nan"),
        "n_windows_used": len(gaps),
        "n_windows_undefined": n_undefined,
        "n_windows_total": len(win_bounds),
    }
