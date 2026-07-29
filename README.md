# Pricing the Heat — v1.0 Prototype

A parametric micro-insurance pricing engine for informal outdoor workers' heatwave wage loss. **High-frequency income smoothing** (not disaster insurance): workers lose wages on roughly 2 out of every 3 heat-affected days, making this a chronic risk, not a rare event. Four fused models produce a defensible premium on real data.

## What it does

Street vendors, construction workers, and delivery riders lose wages when it gets dangerously hot. This product smooths that income loss via parametric insurance: an index (the **mu-TEVI**, fused from street-level heat and modeled wage-loss distribution) triggers payouts automatically. Premium is priced via Longstaff-Schwartz Monte Carlo, with Wang risk-loading. Basis risk (the gap between the index payout and actual loss) is **measured and disclosed** on every quote, not hidden.

## Quick start (20 minutes on a laptop)

```bash
git clone https://github.com/akrishna2508/Pricing-The-Heat
cd "Pricing the Heat"
make install        # pip install torch + requirements, npm ci for frontend
make reproduce      # Deterministic pipeline: fetch real APIs (cached), train all models (seed=42)
make up             # docker-compose: backend at localhost:8000, frontend at localhost:3000
```

Open **http://localhost:3000** to see the dashboard (heatmap, policy simulator, assistant). The backend's `/health` returns ok at `localhost:8000/health`.

**Offline mode**: After the first `reproduce`, you can re-run `make reproduce` offline — it uses cached raw API responses (`.meta.json` sidecars). To force a fresh fetch, run `make data` first (requires network).

## Architecture

```
NASA POWER (real grid)          →  STGCN               →  Heat forecast (per-node shade-WBGT)
                                       ↓
World Bank wages + Elasticity   →  Behavioral POMDP    →  Wage-loss fraction
                                    (PPO-trained)
                                       ↓
                              Gumbel Survival Copula
                                       ↓
                                  mu-TEVI Index (0-100)
                                       ↓
                           Longstaff-Schwartz LSMC Pricer
                                       ↓
                              Wang Risk Transform
                                       ↓
              Premium + Basis Risk (shortfall%, overpay%)
                                       ↓
                    FastAPI backend + Next.js frontend
                  (/heatmap | /simulate | /assistant)
```

## Data & Honesty

### Real APIs (free, keyless, no rate limits)

- **Heat**: [NASA POWER](https://power.larc.nasa.gov/api/temporal/daily/regional) — daily shade-WBGT and temperature at real weather stations. **NASA acknowledgement**: _"We acknowledge the World Bank for supporting the POWER Project. We also acknowledge all the institutions supporting POWER."_

- **Wages**: [World Bank Indicators API v2](https://api.worldbank.org/v2/) — labor-force participation and occupation shares. **License**: CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/).

### Public sources (cited, not API-fetched)

- **Daily wage baseline** (INR): Gujarat Minimum Wages Act, 1948 notification. Recorded in `backend/data/cities.yaml` with source URL and date; manually verified (see `cities.yaml:baseline_daily_wage` for each occupation).

- **Heat elasticity**: Cited from occupational-heat-stress literature:
  - ~2.6% wage loss per °C above WBGT 24°C (ILO synthesis)
  - ~0.57% per °C for construction (Watts et al., *Environmental Research Letters*)
  - Used in behavioral POMDP (Module 3).

### Real-data-only guarantee

No synthetic, fabricated, or placeholder data. Two failure modes (CLAUDE.md Golden Rule 5):
- **MODE A** (API unreachable): aborts with `FATAL:` banner, exits(1), writes no output.
- **MODE B** (cell is null): fills with nearest REAL observed value (same node/day within 7d, else same day/nearest node), logged to `.meta.json` sidecar.

## Key Results

All findings are documented with code and full data accessible in this repo. Nothing is hidden.

### Metric: MAE, not MAPE

Premium amounts are small (₹200–300) with right-skewed, zero-inflated payoff; MAPE rewards predicting larger payouts at lower confidence. **MAE is the honest metric.** Full reasoning: [`docs/METRIC_AMENDMENT.md`](docs/METRIC_AMENDMENT.md). Our model achieves **~20–28% lower MAE** than flat-rate baseline.

### Product framing: Income smoothing, NOT "catastrophe insurance"

On 10 years of real data (36 strike/window combinations tested), **zero contracts** exhibit rare-event disaster-cover behavior. The index triggers on ~35% of calendar days — chronic, frequent, not rare. Honest framing: income smoothing for a recurring seasonal risk. See [`docs/CONTRACT_DESIGN.md`](docs/CONTRACT_DESIGN.md).

### Basis risk: transparent, first-class

Parametric payout always gaps actual loss. We measure and disclose:
- **Shortfall** (~40% of days): actual loss exceeds payout
- **Overpay** (~26% of days): payout exceeds actual loss
- **Correlation**: 0.85 (index-to-loss tracking quality)

These appear on every `/simulate-policy` response in the `basis_risk` block, not fine print.

### Spatial: STGCN beats IDW

The spatial graph convolution outperforms inverse-distance-weighting on **genuinely new, held-out nodes** — validating that street-level heat structure is learnable. See `models/stgcn/evaluate_spatial.py`.

### Temporal: GRU beats persistence

7-day forecaster improves on "tomorrow=today" baseline by +2.45% MAE on chronologically held-out data. Modest but honest. See `models/forecast/train.py`.

## Verification

### Unit tests
```bash
make test
```
**181 tests pass.** Covers contract math, PPO policy, forecaster, anomaly detection, E2E API.

### E2E verification (offline, real cached data)
```bash
cd frontend && node e2e/fetch-replay.mjs
```
**6/6 checks pass:** heatmap grid, positive premium with basis-risk in income-smoothing framing, single-dominant-feature /explain, no-key assistant fallback, honest out-of-coverage message.

### CI-safe
`make build` and `make test` both succeed without trained artifacts — verifying clean imports and that tests don't hard-require models on disk.

## Walkthrough & Docs

- **[`notebooks/walkthrough.ipynb`](notebooks/walkthrough.ipynb)** — ISEF presentation: live tour of Modules 1–4 loading pre-trained artifacts, one plot per module, ending on MAE vs. baseline and income-smoothing framing.
- **[`docs/METRIC_AMENDMENT.md`](docs/METRIC_AMENDMENT.md)** — Why MAE is the right metric, why MAPE is methodologically wrong for this payoff.
- **[`docs/CONTRACT_DESIGN.md`](docs/CONTRACT_DESIGN.md)** — Strike/window sweep on 10-year real history; why 75 mu-TEVI + 14 days was chosen.
- **[`SECURITY.md`](SECURITY.md)** — Security hardening pass: pip-audit, bandit, npm audit, honest unfixed reasoning.
- **[`CLAUDE.md`](CLAUDE.md)** — Full development brief, Golden Rules, Git discipline, data provenance rules.

## Optional: Binary-exact weight rollback

By default, trained artifacts (`.pt`, `.pkl` files) are `.gitignore`d and regenerated deterministically on `make reproduce` (seed=42). To also version-control weights for binary-exact rollback:

```bash
git lfs install
git lfs track "models/artifacts/*.pt" "models/artifacts/*.pkl"
git add .gitattributes
git commit -m "chore: enable git-lfs for binary weights"
git push origin main
```

This is optional; the project works without it because seed=42 determinism is guaranteed.

## License & Attribution

Raw data is governed by source licenses (NASA acknowledgement above; World Bank CC BY 4.0). Code is your choice for ISEF submission. Wage baselines and elasticities are cited from public sources. No novel pharmaceutical, genetic, or nuclear research — applied economics and insurance pricing on public data.

---

**v1.0 Prototype** — End-to-end reproducible, scientifically defensible. ISEF-ready.
