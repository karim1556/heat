# CLAUDE.md — Pricing the Heat

## What this project is
A parametric micro-insurance pricing engine for informal outdoor workers'
heatwave wage loss. Four fused models: an STGCN street-level heat map; a
behavioral multi-agent POMDP wage-loss simulation; a Gumbel survival copula
fusing them into a mu-TEVI index; and a Longstaff-Schwartz + Wang-Transform
pricing engine. Primary metric: >=20% lower MAPE than a flat-rate baseline.
Target: ISEF. The result must be scientifically DEFENSIBLE in a live interview,
not merely runnable.

## Golden Rules (apply to EVERY prompt, always)
1. Execution-only. Never ask clarifying questions. If ambiguous, pick the most
   standard option and proceed.
2. CPU-ONLY. Never install CUDA wheels. Always the CPU build of torch.
3. Deterministic. Every script with randomness sets seed=42 (random, numpy,
   torch) and logs it.
4. Small by default. Every model/data size runs on a laptop in <5 min. Never
   scale up "for quality."
5. DATA IS REAL OR IT STOPS (non-negotiable). No synthetic or assumed data
   anywhere. Two failure modes, handled oppositely:
   - MODE A — API unreachable (no HTTP 200 / unparseable after 3 retries w/
     backoff): call fatal_abort -> print the FATAL banner -> sys.exit(1).
     Never fabricate, never substitute.
   - MODE B — API returns 200 but a cell is null/-999: fill with the NEAREST
     REAL OBSERVED value (same node nearest day within 7d; else same day
     nearest node; else escalate to MODE A). Never a random/mean/synthetic/
     interpolated value. Log every proxy (source cell + distance) to the
     .meta.json sidecar; report the proxy rate.
6. After each prompt, RUN its Definition-of-done. Only proceed/commit if it
   exits 0. If it fails, fix code from THIS prompt only and re-run.
7. No secrets in the repo. Keys come from env vars (.env, gitignored) only.
   Never enter passwords/tokens or create accounts (prohibited actions).
8. PACKAGE STRUCTURE: every imported dir under models/ and backend/ has an
   empty __init__.py; run from repo root with PYTHONPATH=. so `python -m ...`
   resolves.
9. DATA HANDOFF IS EXPLICIT — never infer paths. Canonical artifacts:
     data/raw/*.meta.json               (provenance sidecar, every fetch)
     data/processed/wage_loss.parquet   (Prompt 3 -> 4)
     data/processed/mu_tevi.parquet     (Prompt 4 -> 5,6,8)
     data/processed/claims.parquet      (Prompt 6 -> 8, anomaly input)
     models/artifacts/stgcn.pt          (Prompt 2 -> 7)
     models/artifacts/ppo_policy.pt     (Prompt 3)
     models/artifacts/calibration.json  (Prompt 3 -> 4,5)
     models/artifacts/copula.json       (Prompt 4 -> 5)
     models/artifacts/forecaster.pt     (Prompt 8)
     models/artifacts/anomaly.pkl       (Prompt 8)
10. VERSION EVERYTHING. After every prompt, commit + push with the prompt's
    COMMIT TAG. Never leave work uncommitted. Trained weights (*.pt/*.pkl) and
    processed parquet are gitignored (large/regenerable), so rollback restores
    CODE+CONFIG, not weights; that's safe because the pipeline is deterministic
    (seed=42) and `make reproduce` regenerates identical artifacts from cached
    raw responses. Optional git-lfs on models/artifacts/ for binary-exact
    weight rollback (README documents it; not required).

## Verified data sources (free, keyless, NOT rate-capped)
- Heat: NASA POWER — https://power.larc.nasa.gov/api/temporal/daily/{regional,point}
  No key, no fixed rate limit. DO NOT use api.nasa.gov (needs a key, capped at
  1000/hr). Regional calls = ONE parameter each. -999 = no-data (a MODE B gap).
- Wages (labor structure): World Bank Indicators API v2 —
  https://api.worldbank.org/v2/country/{ISO3}/indicator/{CODE}?format=json
  No key, no rate limit for normal use. MUST use /v2/ and &format=json. Body is
  [metadata, data]; parse element [1]. Verified code: SL.EMP.WORK.ZS. Data lags
  1-2 yrs (recent nulls = MODE B).
- Baseline wage LEVEL: NOT from an API (WB gives shares, not currency). Read
  from cities.yaml, sourced from a NAMED cited public wage schedule (with URL +
  date). Labeled as a cited value, like the elasticity.
- Heat->wage-loss elasticity: cited literature (~2.6%/C above WBGT 24C;
  construction ~0.57%/C). The ONE labeled modeling assumption. ILOSTAT SDMX is
  OPTIONAL enrichment only, never on the required path, always try/except-guarded.

## Git Discipline (END of every prompt)
- FIRST run the prompt's Definition-of-done. COMMIT ONLY IF IT EXITS 0 — a tag
  must always point at a known-good state.
- Ensure branch is main: `git branch -M main` once after `git init`.
- git add -A
- git commit -m "<type>: <summary>"  (conventional: feat/fix/chore/test/docs)
- git tag <COMMIT TAG from the banner>
- git push origin main --tags
- If push fails for no remote: the human sets it once (Prompt A prints how); do
  not create repos or credentials yourself.

## Model discipline
Obey the ">> RUN AS" banner. Most prompts: cheapest model, blind mode, no
thinking. Only the four scientific-core prompts (STGCN, PPO, copula, pricing)
use extended thinking. Do not think on the others; it wastes tokens.
