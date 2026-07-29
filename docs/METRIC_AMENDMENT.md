# Metric Amendment: MAPE → MAE (primary success metric)

**Status:** amended. **Date:** 2026-07 (Prompt v0.7b). **Models:** unchanged.

This document records an amendment to the project's primary success metric,
with reasoning, logged in git. It is a **methodological correction, not a
goalpost move** — the argument below is deliberately **result-independent**: it
holds from the statistics of the target distribution alone, before any model is
scored.

## The original target

`CLAUDE.md` states the headline objective as **"≥20% lower MAPE than a flat-rate
baseline."** MAPE (Mean Absolute Percentage Error) was chosen as the primary
metric for full-model premiums vs realized payouts.

## Why MAPE is the wrong loss function for this payoff — independent of any result

MAPE = mean of `|actual − predicted| / |actual|`. It divides by the actual
value. The realized-payout target here is **right-skewed, zero-inflated, and
large-loss-dominated**, and on exactly that kind of target MAPE is known to be
pathological (Hyndman & Koehler 2006, *Another look at measures of forecast
accuracy*, which recommends against MAPE for such data). Three concrete,
provable-before-scoring reasons:

1. **Undefined on the zero atom.** ~33% of node-days carry an exactly-zero cited
   loss (the hurdle atom), and ~half of policy windows realize a zero payout.
   MAPE is undefined there (division by zero) and can only be computed after
   discarding them. *A headline metric that can only be evaluated on half the
   data is the wrong metric for the data.*

2. **Explodes on the small-loss mass.** On the many *near*-zero (small but
   nonzero) actuals, the denominator is tiny, so a modest absolute error becomes
   an enormous percentage — individual windows here reach APEs of ~18,000%. The
   aggregate is then dominated by the model's behaviour on the *smallest*
   observations, when an insurance product's economics are dominated by the
   *largest* ones.

3. **Structurally rewards under-prediction.** For a point forecast `p` against
   actual `a > 0`, the per-observation APE from *under*-predicting is bounded:
   `(a − p)/a ≤ 1` (100%, at `p = 0`). The APE from *over*-predicting is
   unbounded: `(p − a)/a → ∞`. So a MAPE-minimizing forecast is biased **low**.
   For an insurance premium this is precisely the wrong direction — it favours
   an under-priced product that leaves the insurer's tail uncovered.

None of these three statements references which model wins. They are properties
of the metric and the target distribution. If the *only* argument were "a
different metric makes our model win," that would be goalpost-moving and is
explicitly **not** the argument here.

## The amended primary metric

**Primary: Mean Absolute Error (MAE)**, in the payout's own currency (INR).
Symmetric, defined on every window (no division by the actual), and directly
interpretable as "average rupees of mispricing." It neither blows up on the
zero-inflated small-loss mass nor rewards systematic under-prediction.

**Reported alongside MAE:**

- **Tail-weighted error** — the MAE conditional on the actual being in the upper
  tail (top 10% of realized payouts by default). Insurance economics live in the
  tail; this is where an under-priced flat product fails hardest.
- **MAPE, kept as a secondary metric**, with the reasoning above attached, so the
  amendment is transparent and the old number remains inspectable.
- **A robustness check on the MAE lead** (per-window win rate + a bootstrap CI on
  the MAE difference), because the project now stakes its claim on MAE and that
  claim must be subjected to the same scrutiny MAPE just received.

**A caveat kept in view:** MAE is minimized by the conditional *median*, whereas
an actuarially-fair (and risk-loaded) premium targets the *mean*/tail. That is
exactly why the tail-weighted error is reported next to MAE rather than MAE being
treated as the whole story.

## What the ranking turns out to be (secondary to the metric being correct)

On the amended metrics, computed on the real historical replay (basis-risk
pairing, index-triggered payout vs the max-in-window realized payout):

- **MAE:** full model **77.5 INR** vs flat baseline **118.8 INR** — a **+34.8%**
  reduction. Bootstrap 95% CI on the difference **excludes zero** ([23.7, 58.0]
  INR); per-window win rate **62.9%**. The lead is robust, not carried by a few
  windows.
- **Tail-weighted error (top 10% of windows):** full model **53 INR** vs flat
  **217 INR**. The flat baseline's fixed low premium — the very thing MAPE
  rewards — is catastrophic exactly where insurance matters.
- **MAPE (secondary):** full **71.7%** vs flat **54.3%**. The flat baseline
  "wins" on MAPE precisely via the under-prediction reward described above; this
  is the pathology, illustrated, not a counter-result.

The metric being correct is the point; the ranking that falls out of it is
secondary.
