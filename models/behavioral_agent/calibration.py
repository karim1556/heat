"""Calibrate the reward parameters (kappa, gamma) per occupation.

WHAT IS BEING MATCHED
  Simulated wage-loss-vs-heat  <->  the cited literature elasticity curve
  (backend/data/elasticity.py -- the ONE labeled modeling assumption), evaluated
  over the REAL observed WBGT distribution at real NASA POWER nodes, so the fit
  is weighted by the heat that actually occurs in Ahmedabad rather than over a
  made-up uniform grid.

THE CHOICE MODEL
  In the env, resting yields 0 and working yields wage - kappa*exp(gamma*h). A
  worker's wage loss on a given day is therefore the probability they rest:

      L(h) = P(rest | h) = sigmoid( (kappa*exp(gamma*h) - wage) / tau )

  This is a logit / random-utility (McFadden) choice rule. tau is NOT
  irrationality: it is the scale of unobserved heterogeneity in heat tolerance
  ACROSS workers. It has to be there -- a population of identical rational
  agents would produce a step function at a single threshold, whereas the cited
  elasticity is a gradual ~2.6%/C ramp, which only a dispersed population can
  produce.

WHY tau IS FIXED AND NOT FITTED  (this is the crux, and it is a real constraint)
  The curve has exactly two identifiable features: WHERE it turns over
  (h* = ln(wage/kappa)/gamma) and HOW STEEP it is there (slope = gamma*wage/(4 tau)).
  Three parameters (kappa, gamma, tau) cannot be recovered from two features:
  gamma and tau enter the slope only through the ratio gamma/tau, so they are
  jointly NON-IDENTIFIED. Fixing tau makes (kappa, gamma) identified -- the SSE
  Hessian at the optimum is positive definite (asserted below). The consequence,
  stated plainly: the fitted kappa and gamma are conditional on tau, and a
  different tau yields a different (kappa, gamma) describing the SAME curve.

WHY A CLOSED FORM INSTEAD OF ROLLING OUT PPO
  The specified reward R(s,a) = wage*a - kappa*exp(gamma*h)*a depends only on
  the current action and current heat -- cash_buffer does not enter it -- so the
  decision is myopic and P(rest|h) has the closed form above. No policy needs to
  be retrained inside the optimizer. That claim is not taken on faith: it is
  verified below by Monte-Carlo rollout of the actual WorkerEnv, and the maximum
  discrepancy is reported.

Deterministic: seed=42 (CLAUDE.md Golden Rule 3). Real data or it stops (Rule 5).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from scipy.optimize import minimize

from backend.data import elasticity
from backend.data.build_wage_loss import CITIES_YAML_PATH, OCCUPATIONS, _effective_elasticity
from backend.data.survey import SurveyDataLoader
from backend.data.wages import WageLoader
from models.behavioral_agent.worker_env import WorkerEnv, heat_cost
from models.stgcn.train import load_weather

SEED = 42

# Per-state namespacing (v2): STATE_KEY set -> this state's namespaced I/O and
# its OWN legislated wage schedule (USD for US states, INR for IN states, never
# converted). Unset -> legacy single-city path unchanged. See backend/state_context.
STATE_KEY = os.environ.get("STATE_KEY")
if STATE_KEY:
    from backend.state_context import get_context

    _CTX = get_context(STATE_KEY)
    CALIBRATION_PATH = _CTX.artifact("calibration.json")
    WAGE_LOSS_PATH = _CTX.processed("wage_loss.parquet")
    PLOT_PATH = _CTX.artifact("calibration_residuals.png")
else:
    _CTX = None
    CALIBRATION_PATH = Path("models/artifacts/calibration.json")
    WAGE_LOSS_PATH = Path("data/processed/wage_loss.parquet")
    PLOT_PATH = Path("notebooks/artifacts/calibration_residuals.png")

# Logit choice-noise scale, as a fraction of one daily wage. FIXED, not fitted --
# see the module docstring on identifiability. 0.10 is chosen because it keeps
# the SSE Hessian best-conditioned across occupations while leaving the model's
# low-heat floor, sigmoid(-wage/tau) = sigmoid(-10) ~ 5e-5, negligible against a
# target that is exactly 0 below the threshold.
TAU_WAGE_FRACTION = 0.10

# Deterministic multi-start grid in log-space (log kappa, log gamma). Nelder-Mead
# is local; a fixed grid of starts makes the reported optimum reproducible rather
# than dependent on where the search happened to begin.
START_GRID = [(lk, lg) for lk in (-6.0, -2.0, 2.0, 5.0) for lg in (-6.0, -4.0, -2.0)]

MC_EPISODES_PER_CHECK = 400


def sigmoid(z: np.ndarray) -> np.ndarray:
    """Logistic via tanh -- stable in both tails, unlike 1/(1+exp(-z))."""
    return 0.5 * (1.0 + np.tanh(0.5 * np.asarray(z, dtype=float)))


def simulated_loss(h: np.ndarray, kappa: float, gamma: float, wage: float,
                   tau: float) -> np.ndarray:
    """L(h) = P(rest | h) under the logit choice rule."""
    return sigmoid((heat_cost(h, kappa, gamma) - wage) / tau)


def target_loss(h: np.ndarray, occupation: str, overrides: dict) -> np.ndarray:
    """The cited elasticity ramp: clip((h - threshold) * per_deg, 0, cap)."""
    params = _effective_elasticity(occupation, overrides)
    return np.clip(
        (np.asarray(h, dtype=float) - params["wbgt_threshold_c"]) * params["per_deg"],
        0.0, elasticity.MAX_LOSS_FRACTION,
    )


def fit_occupation(h: np.ndarray, occupation: str, wage: float, overrides: dict) -> dict:
    """Fit (kappa, gamma) by least squares over the REAL heat distribution.

    Optimized in log-space so kappa, gamma > 0 is enforced by construction
    rather than by bounds the simplex would have to bounce off.
    """
    tau = TAU_WAGE_FRACTION * wage
    y = target_loss(h, occupation, overrides)

    def sse(p: np.ndarray) -> float:
        kappa, gamma = np.exp(p[0]), np.exp(p[1])
        return float(np.mean((simulated_loss(h, kappa, gamma, wage, tau) - y) ** 2))

    best = None
    for start in START_GRID:
        res = minimize(sse, np.array(start), method="Nelder-Mead",
                       options=dict(maxiter=6000, fatol=1e-15, xatol=1e-12))
        if best is None or res.fun < best.fun:
            best = res

    kappa, gamma = float(np.exp(best.x[0])), float(np.exp(best.x[1]))
    pred = simulated_loss(h, kappa, gamma, wage, tau)
    resid = pred - y
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float((resid**2).sum()) / ss_tot if ss_tot > 0 else float("nan")

    # Identifiability check: a positive-definite SSE Hessian at the optimum means
    # (kappa, gamma) are locally identified GIVEN tau. If this is singular the fit
    # is a ridge and the reported numbers are arbitrary along it.
    eps = 1e-4
    hess = np.zeros((2, 2))
    for i in range(2):
        for j in range(2):
            acc = 0.0
            for si, sj, sign in ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)):
                p = best.x.copy()
                p[i] += si * eps
                p[j] += sj * eps
                acc += sign * sse(p)
            hess[i, j] = acc / (4 * eps * eps)
    eigs = np.linalg.eigvalsh(hess)

    return {
        "kappa": kappa,
        "gamma": gamma,
        "tau": tau,
        "indifference_wbgt_c": float(np.log(wage / kappa) / gamma),
        "rmse": float(np.sqrt(best.fun)),
        "r2": r2,
        "hessian_eigs": eigs.tolist(),
        "identified": bool(np.all(eigs > 0)),
        "condition_number": float(abs(eigs).max() / max(abs(eigs).min(), 1e-300)),
        "residuals": resid,
        "pred": pred,
        "target": y,
    }


def verify_against_env(env: WorkerEnv, occupation: str, tau: float,
                       rng: np.random.Generator) -> float:
    """Monte-Carlo check that the closed form IS the env's behaviour.

    Rolls the real env forward under the logit policy (acting on the PERCEIVED
    heat, i.e. through the POMDP's observation noise) and compares the realised
    rest rate, bucketed by true WBGT, against the closed form. Returns the max
    absolute discrepancy over buckets with enough samples.
    """
    true_heat, rested = [], []
    for _ in range(MC_EPISODES_PER_CHECK):
        env.reset(occupation=occupation)
        while True:
            # The worker decides on perceived heat; the closed form is stated in
            # true heat. Any gap between them shows up in this check.
            perceived = env._episode_heat[env._t] + rng.normal(0.0, env.perception_noise_c)
            p_work = float(env.softmax_work_prob(perceived, occupation, tau))
            action = int(rng.random() < p_work)
            _, _, terminated, truncated, info = env.step(action)
            true_heat.append(info["true_wbgt_c"])
            rested.append(1 - info["worked"])
            if terminated or truncated:
                break

    true_heat, rested = np.array(true_heat), np.array(rested)
    edges = np.arange(np.floor(true_heat.min()), np.ceil(true_heat.max()) + 1, 1.0)
    worst = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (true_heat >= lo) & (true_heat < hi)
        if mask.sum() < 200:
            continue
        mid = 0.5 * (lo + hi)
        p = env.params[occupation]
        closed = float(
            simulated_loss(np.array([mid]), p["kappa"], p["gamma"], env.wages[occupation], tau)[0]
        )
        worst = max(worst, abs(rested[mask].mean() - closed))
    return worst


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate kappa/gamma to the cited elasticity")
    parser.add_argument("--output", default=str(CALIBRATION_PATH))
    args = parser.parse_args()

    started = time.time()
    random.seed(SEED)
    np.random.seed(SEED)
    rng = np.random.default_rng(SEED)

    print("=" * 72)
    print("BEHAVIORAL CALIBRATION -- fitting kappa, gamma per occupation")
    print("=" * 72)
    print(f"[SEED]     seed={SEED}")

    weather = load_weather()
    pivot = weather.pivot(index="date", columns="node_id", values="wbgt_c").sort_index()
    heat_matrix = pivot.to_numpy()
    h_flat = heat_matrix.reshape(-1)

    if _CTX is not None:
        wages = _CTX.daily_wages()          # this state's own wage schedule + currency
        wage_currency = _CTX.currency
    else:
        with open(CITIES_YAML_PATH) as f:
            config = yaml.safe_load(f)
        city_key = config["default_city"]
        loader = WageLoader(country_iso3=config["cities"][city_key]["country_iso3"])
        wages = loader.occupation_baseline_wages(city_key=city_key)
        wage_currency = "INR"
    overrides = SurveyDataLoader().load_overrides()
    print(f"[WAGE]     baseline daily wages ({wage_currency}): {wages}")

    print(f"[REAL API] NASA POWER shade-WBGT: {len(h_flat)} real node-days, "
          f"mean={h_flat.mean():.2f}C sd={h_flat.std():.2f}C "
          f"[{h_flat.min():.1f}, {h_flat.max():.1f}]")
    print("[CITED]    target = elasticity ramp per occupation "
          "(the ONE labeled modeling assumption)")
    print(f"[MODEL]    logit P(rest|h) = sigmoid((kappa*exp(gamma*h) - wage)/tau), "
          f"tau = {TAU_WAGE_FRACTION} * wage (FIXED -- see module docstring)")
    print()

    results, calibration = {}, {}
    for occupation in OCCUPATIONS:
        fit = fit_occupation(h_flat, occupation, wages[occupation], overrides)
        results[occupation] = fit
        calibration[occupation] = {"kappa": fit["kappa"], "gamma": fit["gamma"]}
        src = "primary field data" if occupation in overrides else \
            _effective_elasticity(occupation, overrides)["source"]
        print(f"  {occupation:13s} kappa={fit['kappa']:10.4f}  gamma={fit['gamma']:.6f}  "
              f"tau={fit['tau']:6.2f}")
        print(f"                RMSE={fit['rmse']:.5f}  R2={fit['r2']:.4f}  "
              f"h*={fit['indifference_wbgt_c']:.2f}C")
        print(f"                identified={fit['identified']} (Hessian PD, "
              f"cond={fit['condition_number']:.3g})  target: {src}")

    # Verify the closed form against the real simulator, at the fitted params.
    print()
    print("[VERIFY]   closed-form P(rest|h) vs Monte-Carlo rollout of WorkerEnv")
    env = WorkerEnv(heat_matrix, wages, params=calibration, seed=SEED)
    for occupation in OCCUPATIONS:
        worst = verify_against_env(env, occupation, results[occupation]["tau"], rng)
        status = "OK" if worst < 0.05 else "MISMATCH"
        print(f"           {occupation:13s} max |MC - closed form| = {worst:.4f}  [{status}]")
        results[occupation]["mc_max_abs_error"] = worst

    for occupation, fit in results.items():
        if not fit["identified"]:
            print(f"FATAL: (kappa, gamma) not identified for {occupation}: "
                  f"SSE Hessian is not positive definite. Aborting rather than "
                  f"reporting arbitrary parameters along a ridge.")
            return 1

    # --- calibration.json -------------------------------------------------
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(calibration, indent=2) + "\n")
    print(f"\n[ARTIFACT] {out_path}")

    # --- wage_loss.parquet (F_L input for Prompt 4) -----------------------
    # Overwrites the literature-based version from Prompt 1 with the
    # behaviorally-calibrated one, keeping the identical schema.
    long = (
        pivot.reset_index()
        .melt(id_vars="date", var_name="node_id", value_name="wbgt_c")
        .rename(columns={"date": "ts"})
    )
    frames = []
    for occupation in OCCUPATIONS:
        fit = results[occupation]
        fraction = simulated_loss(
            long["wbgt_c"].to_numpy(), fit["kappa"], fit["gamma"],
            wages[occupation], fit["tau"],
        )
        frames.append(pd.DataFrame({
            "node_id": long["node_id"],
            "ts": long["ts"],
            "occupation": occupation,
            "wage_loss_fraction": fraction,
            "wage_loss_abs": fraction * wages[occupation],
        }))
    wage_loss = pd.concat(frames, ignore_index=True).sort_values(
        ["node_id", "ts", "occupation"]
    ).reset_index(drop=True)

    WAGE_LOSS_PATH.parent.mkdir(parents=True, exist_ok=True)
    wage_loss.to_parquet(WAGE_LOSS_PATH, index=False)
    print(f"[ARTIFACT] {WAGE_LOSS_PATH}  rows={len(wage_loss)} "
          f"cols={list(wage_loss.columns)}")
    print("           behaviorally-calibrated F_L (overwrote the Prompt-1 "
          "literature version, same schema)")

    # --- residual plot ----------------------------------------------------
    fig, axes = plt.subplots(2, len(OCCUPATIONS), figsize=(4.1 * len(OCCUPATIONS), 7.2))
    order = np.argsort(h_flat)
    h_sorted = h_flat[order]
    for col, occupation in enumerate(OCCUPATIONS):
        fit = results[occupation]
        ax = axes[0, col]
        ax.plot(h_sorted, fit["target"][order], lw=2.4, color="#adb5bd",
                label="cited elasticity")
        ax.plot(h_sorted, fit["pred"][order], lw=1.4, color="#c1121f",
                label="calibrated logit")
        ax.set_title(f"{occupation}\nR2={fit['r2']:.4f}  RMSE={fit['rmse']:.4f}")
        ax.set_xlabel("shade-WBGT (degC)")
        ax.set_ylabel("wage-loss fraction")
        ax.legend(fontsize=7)
        ax.grid(alpha=0.3)

        ax = axes[1, col]
        ax.scatter(h_sorted, fit["residuals"][order], s=1, alpha=0.25, color="#2a9d8f")
        ax.axhline(0, color="k", lw=0.8)
        params = _effective_elasticity(occupation, overrides)
        ax.axvline(params["wbgt_threshold_c"], ls=":", color="grey", lw=1,
                   label=f"cited threshold ({params['wbgt_threshold_c']:.0f}C)")
        ax.set_xlabel("shade-WBGT (degC)")
        ax.set_ylabel("residual (fit - cited)")
        ax.set_title("Residuals")
        ax.legend(fontsize=7)
        ax.grid(alpha=0.3)

    fig.suptitle(
        f"Behavioral calibration over {len(h_flat)} real node-days  |  "
        f"tau = {TAU_WAGE_FRACTION}*wage (fixed)  |  seed={SEED}", fontsize=11)
    fig.tight_layout()
    PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOT_PATH, dpi=130)
    plt.close(fig)
    print(f"[ARTIFACT] {PLOT_PATH}")
    print(f"[TIME]     {time.time() - started:.1f}s total")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
