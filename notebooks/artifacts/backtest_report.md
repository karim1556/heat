# Backtest Report -- Pricing the Heat

_Generated 2026-07-18T03:36:38.204222+00:00_

## Provenance

- **Heat**: NASA POWER regional API (`power.larc.nasa.gov`), real fetch recorded in `data/raw/*.meta.json` sidecars.
- **Wages (labor structure)**: World Bank Indicators v2 (`api.worldbank.org`), indicator SL.EMP.WORK.ZS.
- **Baseline daily wages (cited, not API)**:
  - vendor: INR 368.0 -- Minimum Wages Act, 1948 notification (unskilled, Zone I) -- Labour & Employment Department, Government of Gujarat (https://labour.gujarat.gov.in, 2023-10) [**UNVERIFIED -- human confirmation required**]
  - construction: INR 406.0 -- Minimum Wages Act, 1948 notification (Building & Construction scheduled employment, semi-skilled) -- Labour & Employment Department, Government of Gujarat (https://labour.gujarat.gov.in, 2023-10) [**UNVERIFIED -- human confirmation required**]
  - delivery: INR 387.0 -- Minimum Wages Act, 1948 notification (semi-skilled, Zone I) -- Labour & Employment Department, Government of Gujarat (https://labour.gujarat.gov.in, 2023-10) [**UNVERIFIED -- human confirmation required**]
- **Elasticity (the one labeled modeling assumption)**:
  - vendor, delivery: 0.026/degC above 24.0C -- Foster/Kjellstrom meta-analysis, ~2.6%/C wage-loss above 24C WBGT
  - construction: 0.0057/degC above 24.0C -- Construction-sector WBGT productivity study, ~0.57%/C above 24C WBGT

## Data Completeness

- 100.000% directly observed, 0.000% nearest-real proxied (max reach: 0d / 0.0km), 0 fabricated.

## Modeling Assumptions

> **Elasticity**: ~2.6%/C wage loss above 24C WBGT (default), ~0.57%/C for construction (Foster/Kjellstrom meta-analysis; construction-sector WBGT productivity study).
>
> **tau convention**: kappa/gamma (Prompt 3's behavioral calibration) are CONDITIONAL on the fixed logit choice-noise scale tau = 0.1*wage. (kappa, gamma, tau) are jointly non-identified from a single choice curve; a different tau describes the same curve with different kappa/gamma. They are not free-standing physical constants.

## Headline: MAE (full model vs flat-rate baseline) — PRIMARY metric

Primary metric is **MAE**, not MAPE (see `docs/METRIC_AMENDMENT.md` for the result-independent reasoning: MAPE is undefined on the ~33% zero atom, explodes on the small-loss mass, and structurally rewards under-prediction -- properties of this right-skewed, zero-inflated, tail-dominated payoff, provable before any model is scored). Computed on the **basis-risk pairing** (index-triggered payout vs MAX-IN-WINDOW realized payout, matching the optimal-exercise contract the LSMC premium was priced for), on the 375 nonzero-payout windows.

| metric | Full model (LSMC) | Flat-rate baseline | full vs flat |
|---|---|---|---|
| **MAE (INR)** — primary | **84.16** | 116.30 | **+27.6%** |
| Tail-weighted error (top 10%) | 96.54 | 234.61 | +58.8% |
| MAPE (%) — secondary | 243.35 | 128.53 | -89.3% |

**On the tail** (the top 38 largest-loss windows, where insurance economics live), the full model's error is 97 INR vs the flat baseline's 235 INR. The flat baseline's fixed low premium -- the very thing MAPE rewards -- is catastrophic exactly where it matters most.

### Robustness of the MAE lead

The project now stakes its claim on MAE, so the lead gets the same scrutiny MAPE did:
- **Per-window win rate**: the full model has the smaller absolute error on **64.5%** of windows (not carried by a few).
- **Bootstrap 95% CI** on MAE(flat) - MAE(full) (10,000 resamples, seed 42): [21.0, 43.0] INR, which **EXCLUDES zero** -- the lead is robust. Improvement 95% CI: [18.0%, 37.0%].

_MAPE secondary result (-89.3%): the flat baseline "wins" on MAPE precisely via the under-prediction reward described in the amendment doc -- the pathology illustrated, not a counter-result._

## Contract Design (strike/window selected on the real replay)

This is **contract calibration** (choosing strike + coverage window), distinct from model retuning -- the pricing, heat, and behavioral models are frozen. The strike and window were selected by an explicit sweep (`backend/backtest/contract_design.py`, 36 grid points, seed 42), not assumed.

**Honesty gate**: a contract 'behaves like catastrophe insurance' iff trigger_rate <= 0.15, premium/cap <= 0.3, and shortfall_rate <= 0.3 all hold. **0 of 36** grid points qualify.

**NO strike/window is catastrophe insurance without gutting coverage.** This is not a tuning failure -- it is forced by the peril: outdoor workers lose wages on **~66% of worker-days**, a chronic seasonal condition, not a rare catastrophe. The trade-off is monotonic and unavoidable (see `contract_design_sweep.png`): a rarer trigger (higher strike) drives the worker's shortfall_rate from ~20% up to ~64%, and any contract with good coverage necessarily has premium/cap > 0.8 -- the mathematical signature of income smoothing, not tail insurance.

**The product is therefore honestly reframed as high-frequency INCOME SMOOTHING**, and the contract is selected for that objective: an UNBIASED index (minimize |shortfall - overpay|, fixing the strike), then the window that MAXIMIZES genuine risk transfer (lowest premium/cap). The contract is chosen on product quality, never on the model-vs-baseline metric -- picking the window that flatters the MAE gap would be goalpost-gaming and is explicitly not done (the chosen 14-day window in fact has a SMALLER MAE gap than a 30-day window would).

**Chosen contract: strike 75 mu-TEVI, 14-day window** (income smoothing). On the real replay: trigger_rate 0.481, premium/cap 0.698, shortfall 0.345, overpay 0.320 (|bias| 0.025 -- the most unbiased point on the grid).

**Trade-off surface (never just the winner)** -- a slice at the 14-day window:

| strike | trigger | premium/cap | shortfall | overpay | rmse | MAE impr |
|---|---|---|---|---|---|---|
| 55 | 0.596 | 0.814 | 0.165 | 0.501 | 119.6 | +29.4% |
| 60 | 0.577 | 0.793 | 0.197 | 0.468 | 111.5 | +28.6% |
| 65 | 0.546 | 0.769 | 0.234 | 0.432 | 102.5 | +29.7% |
| 70 | 0.519 | 0.739 | 0.278 | 0.387 | 92.5 | +28.0% |
| 75 **<-chosen** | 0.481 | 0.698 | 0.345 | 0.320 | 81.8 | +27.2% |
| 80 | 0.423 | 0.650 | 0.422 | 0.243 | 71.1 | +27.7% |
| 85 | 0.354 | 0.586 | 0.503 | 0.162 | 61.0 | +26.4% |
| 90 | 0.246 | 0.485 | 0.580 | 0.085 | 53.0 | +31.5% |
| 95 | 0.138 | 0.322 | 0.638 | 0.027 | 47.9 | +37.3% |

Note the trap this avoids: `basis_risk_rmse` *improves* (falls) as the strike rises, at the very same time shortfall_rate *worsens* -- selecting on RMSE alone would quietly gut coverage. Full grid: `notebooks/artifacts/contract_design_sweep.csv`.

## Contract Health

- **trigger_rate**: 48.1% of 260 14-day windows had the index reach the strike at least once.
- **payout_frequency**: 3.423% of 164,340 worker-days actually received a payout.
- **premium-to-cap ratio** (priced premium / max possible payout):
  - vendor: 0.692
  - construction: 0.692
  - delivery: 0.692

trigger_rate (48.1%) is below the 60% pathological threshold, but a ~48% chance of triggering per 14-day window is frequent for anything framed as catastrophe-style cover -- consistent with the Contract Design section's finding that this product is high-frequency income smoothing, not tail insurance.

## Persistence

Real-data analogue of Prompt 5's simulated ~7% i.i.d.-vs-persistent gap, computed with the SAME reordering utility (`models.pricing.lsmc_pricer.persistence_premium_gap`) applied to every real non-overlapping window: (a) an i.i.d.-shuffled version of the window's own 14 values vs (b) the real ordered window (autocorrelation ~0.99 intact).

- mean gap: **-2.89%** (median -2.55%), over 125 triggering windows (135 windows never reach the strike under either ordering -- gap is 0/0, undefined, and excluded).

**Methodological note (why the sign differs from Prompt 5's simulated figure)**: Prompt 5's test varied AR(1) persistence across M INDEPENDENT simulated realizations sharing one marginal, preserving genuine stopping-under-uncertainty in both cases. Here, "the real ordered window" is the ONE real historical realization, replicated identically across paths for the LSMC call; with zero cross-sectional variance the regression collapses toward the near-perfect-foresight value of that one history, which is mechanically >= the genuine stopping-under-uncertainty value of the shuffled case -- hence a NEGATIVE gap here versus the positive ~7% on simulated data. Both are honestly reported; they are not the same experiment, just the same reordering principle applied to what data was actually available.

## Basis Risk (empirical, real replay)

Computed on 164,340 real worker-days (45 workers x 3652 days), pairing the index-triggered daily payout against each worker's own hurdle-model wage loss.

| basis_risk_rmse | shortfall_rate | overpay_rate | correlation |
|---|---|---|---|
| 81.82 INR | 34.5% | 32.0% | 0.665 |

shortfall_rate = 34.5% of worker-days the index UNDER-pays the worker's actual modeled loss; overpay_rate = 32.0% the insurer pays MORE than the actual loss. This is the honest measure of how often the index fails the worker, structurally inherent to any parametric product.

**HONEST CAVEAT**: shortfall_rate exceeds 30% -- workers are frequently under-compensated relative to their modeled loss. This is a design finding (strike/cap/basis choice), not something to bury.

## Sensitivity Sweep

theta moves the premium (it directly parameterizes the copula the mu-TEVI index is built from); the loss-marginal shape (traceable to Prompt 3's kappa/gamma) does NOT -- verified live, not assumed: the payout is a pure function of the index, independent of the loss draw.

| theta multiplier | theta | premium (wage-frac) |
|---|---|---|
| 0.7x | 3.176 | 0.7585 |
| 1.0x | 4.537 | 0.7473 |
| 1.3x | 5.898 | 0.7407 |

| loss-marginal (kappa/gamma proxy) multiplier | premium (wage-frac) | mean simulated loss |
|---|---|---|
| 0.7x | 0.7473 | 0.0656 |
| 1.0x | 0.7473 | 0.0785 |
| 1.3x | 0.7473 | 0.0891 |

## Value at Risk / Expected Shortfall

Computed on the **insurer's aggregate daily payout liability** (summed across the 45-worker portfolio, one value per real day, 3652 days -- itself aggregating 164,340 worker-days, comfortably exceeding the >=1000 worker-day threshold). This is a capital-adequacy question ('how much must the insurer hold'), NOT a statement about workers' wage losses.

| alpha | VaR (INR/day) | Expected Shortfall (INR/day) |
|---|---|---|
| 95% | 12213.73 | 13522.76 |
| 99% | 14317.75 | 14955.89 |

**premium_to_payout_ratio** (total premium collected / total realized payout, over the replay): 2.454

## Figures

- `data/exports/poster_figures/heat_map_snapshot.png` -- Heat-map snapshot (peak real day)
- `data/exports/poster_figures/mu_tevi_series.png` -- Real mu-TEVI series, 2014-2023
- `data/exports/poster_figures/premium_vs_heat.png` -- Premium-vs-heat (payout schedule) curve
- `data/exports/poster_figures/mape_comparison.png` -- MAPE / MAE comparison: full model vs flat baseline
- `data/exports/poster_figures/trigger_rate_calendar.png` -- [NEW] Trigger-rate over the calendar (contract health)

