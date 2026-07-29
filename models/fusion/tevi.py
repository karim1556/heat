"""mu-TEVI: fuse the heat trigger (F_H) and wage loss (F_L) via a Gumbel copula.

WHAT THE COPULA ACTUALLY MODELS -- and why the obvious pairing is vacuous
-------------------------------------------------------------------------
Prompt 3's calibration makes wage loss a DETERMINISTIC, strictly increasing
function of WBGT: loss = sigmoid((kappa*exp(gamma*h) - wage)/tau). Measured on
the real data, spearman(WBGT, loss) = 1.0000000000 exactly, per occupation. So
pairing a node's own heat with that same node's own loss produces an EXACTLY
comonotone sample: theta diverges, lambda_U -> 1, and the copula is a
tautology dressed up as a model. (Pooling occupations appears to fix this --
spearman drops to 0.83 -- but that "dependence" is just cross-sectional
heterogeneity between occupations, not stochastic dependence. It would be a
fake number.)

A copula in a parametric pricer can only meaningfully model ONE thing: BASIS
RISK, the mismatch between the TRIGGER the contract pays on and the LOSS the
worker actually suffers. So the pairing here is:

    TRIGGER H_t  = city-level daily heat index = spatial MAX of shade-WBGT over
                   the real POWER nodes. One index for the whole city, which is
                   how these contracts actually work -- you cannot put a WBGT
                   sensor on every informal worker.
    LOSS  L_{i,t} = the hurdle-corrected wage loss at the worker's OWN node i.

The gap between the two is real and measurable: (city max - node WBGT) has mean
1.49 C and sd 1.18 C. That dispersion is the basis risk, and it makes the fit
non-degenerate (theta ~ 4.5 as fitted, ~5.8 once corrected for the atom-induced
attenuation described below) without inventing anything. lambda_U = 2 -
2^(1/theta) then answers the question the product turns on: given the index
triggers, how likely is the worker to actually be losing wages?

WHAT THE HURDLE ACTUALLY BUYS (measured, not assumed)
-----------------------------------------------------
Restoring the atom moves theta from 5.84 (naive) to 4.54 (hurdle), which looks
like a 22% correction -- but ~97% of that gap is a STATISTICAL ARTIFACT, not the
smearing. An atom destroys the ordering information inside it, so theta fitted on
hurdle pseudo-observations is attenuated toward independence (measured factor
0.78 at this p0). Net of that, the smearing's true effect on the dependence
parameter is only about -0.6%.

The smearing's real cost is in the MARGINAL, not the copula: the naive
single-piece F_L assigns ~0 probability to a zero-loss day, whereas 33.5% of real
node-days have exactly zero cited loss. That is what misprices the contract,
because it drives the payout probability on a third of the calendar -- which is
also why Prompt 5 must sample the hurdle rather than one continuous law.

SPATIAL HONESTY (carried from Prompt 2b, required in the output)
---------------------------------------------------------------
mu-TEVI's spatial term is NOT learned geography. On this compact ~2x2 degree
grid the STGCN is roughly on par with information-matched IDW (+4.6%) and
clearly LOSES to same-timestep IDW (-168.8%); nearest-neighbour correlation
among held-out nodes exceeds 0.998. The spatial component is a mild refinement
over trivial interpolation, not a strong independent signal, and it is weighted
and described accordingly below.

HURDLE SAMPLING RECIPE FOR PROMPT 5 (read this before writing the LSMC)
----------------------------------------------------------------------
copula.json's marginal schema is a HURDLE, not a single beta. To simulate a
mu-TEVI path you must sample the joint distribution as:

    1. Draw (u, v) ~ GumbelSurvivalCopula(theta).sample(n, rng)   # dependence
    2. Heat  : h = scipy.stats.genextreme.ppf(u, *gev_params)
    3. Loss  : l = HurdleMarginal.ppf(v)     -- i.e. EXACTLY 0 when v <= p0,
               otherwise beta.ppf((v - p0)/(1 - p0), *positive_params)
    4. mu-TEVI = 100 * (1 - survival_cdf(u, v)) = 100 * (u + v - C(u,v))

Step 3 is the one that is easy to get wrong. Do NOT fit or sample a single
continuous distribution over [0, max]: that silently reintroduces the ~2.4%
floor this whole module exists to remove, and it would misprice every contract
whose payout depends on the probability of a genuinely zero-loss day (about a
third of them). models.fusion.marginals.HurdleMarginal.ppf/.rvs implement the
correct recipe -- call them rather than reimplementing.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import kendalltau

from models.fusion.gumbel_copula import (
    GumbelSurvivalCopula,
    distributional_transform,
    empirical_pseudo_obs,
    mid_rank_transform,
)
from models.fusion.marginals import (
    CITED_ZERO_THRESHOLD_C,
    MIN_POSITIVE_LOSS_DAYS,
    HurdleMarginal,
    NaiveMarginal,
    fit_gev,
    gev_cdf,
)
from models.stgcn.train import load_weather

SEED = 42

# Per-state namespacing (v2): STATE_KEY set -> this state's namespaced I/O
# (its wage_loss in, its copula/mu-TEVI out, its spatial-metrics honesty gate).
# Unset -> legacy single-city paths unchanged.
_STATE_KEY = os.environ.get("STATE_KEY")
if _STATE_KEY:
    from backend.state_context import get_context

    _CTX = get_context(_STATE_KEY)
    WAGE_LOSS_PATH = _CTX.processed("wage_loss.parquet")
    MU_TEVI_PATH = _CTX.processed("mu_tevi.parquet")
    COPULA_PATH = _CTX.artifact("copula.json")
    QQ_PLOT_PATH = _CTX.artifact("gev_qq.png")
    HURDLE_PLOT_PATH = _CTX.artifact("hurdle_marginal.png")
    SPATIAL_METRICS_PATH = _CTX.artifact("spatial_baseline_metrics.json")
    EXCLUDED_PATH = _CTX.artifact("excluded.json")
else:
    WAGE_LOSS_PATH = Path("data/processed/wage_loss.parquet")
    MU_TEVI_PATH = Path("data/processed/mu_tevi.parquet")
    COPULA_PATH = Path("models/artifacts/copula.json")
    QQ_PLOT_PATH = Path("notebooks/artifacts/gev_qq.png")
    HURDLE_PLOT_PATH = Path("notebooks/artifacts/hurdle_marginal.png")
    SPATIAL_METRICS_PATH = Path("notebooks/artifacts/spatial_baseline_metrics.json")
    EXCLUDED_PATH = Path("models/artifacts/excluded.json")

# Distinct exit code for a DELIBERATE out-of-coverage exclusion (a state with
# too few heat-exposure days to fit a defensible wage-loss distribution), as
# opposed to a genuine error. The pipeline still stops for this state -- there
# is nothing downstream to price -- but it drops an excluded.json marker so the
# state is recorded as EXCLUDED in docs/STATEWISE_RESULTS.md, never a silent gap.
EXCLUSION_EXIT_CODE = 3

# From Prompt 3: kappa/gamma are conditional on this fixed logit choice-noise
# scale. Recorded in copula.json so downstream pricing cannot forget that the
# calibrated reward parameters are not free-standing.
TAU_CONVENTION = "0.1*wage"


class TEVICalculator:
    """Builds the mu-TEVI series from the fitted marginals and copula."""

    def __init__(self, gev_params: tuple, hurdle: HurdleMarginal,
                 copula: GumbelSurvivalCopula):
        self.gev_params = gev_params
        self.hurdle = hurdle
        self.copula = copula

    def node_day_index(self, heat_index: np.ndarray, losses: np.ndarray) -> np.ndarray:
        """mu-TEVI in [0, 100] per node-day.

            mu-TEVI = 100 * (1 - P(H > h, L > l)) = 100 * (u + v - C(u,v))

        Reads as a joint-extremity percentile: mu-TEVI = 95 means only 5% of
        node-days exceed BOTH this heat and this loss. It is monotone
        non-decreasing in each of u and v (d/du = 1 - dC/du = 1 - P(V<=v|U=u) >= 0)
        and bounded in [0,100] by the Frechet bounds, so it needs no rescaling.

        Uses the DETERMINISTIC hurdle CDF (atom -> exactly p0), not the jittered
        pseudo-observations used for fitting: the published index must be
        reproducible, not randomized.
        """
        u = gev_cdf(heat_index, self.gev_params)
        v = self.hurdle.cdf(losses)
        return 100.0 * (1.0 - self.copula.survival_cdf(u, v))


def estimate_atom_attenuation(theta: float, p0: float, size: int,
                              reps: int = 3, seed: int = SEED) -> float:
    """Attenuation factor E[theta_hat]/theta induced by an atom of size p0.

    WHY THIS IS NEEDED, and why the naive-vs-hurdle delta is misleading without it:
    an atom destroys information. Every observation inside it has the identical
    loss, so their relative ORDER carries no signal, and the distributional
    transform correctly declines to invent one -- it spreads them independently
    across [0, p0]. The consequence is that theta fitted on hurdle
    pseudo-observations is biased DOWN toward independence (the copula is not
    even uniquely identified from data with ties -- Genest & Neslehova 2007).

    So theta_hurdle < theta_naive is NOT purely "the naive marginal overstates
    dependence". Part of the gap is this estimation artifact. This function
    measures the artifact by simulation at the fitted (theta, p0), so the
    reported delta can be decomposed into the real smearing effect and the
    attenuation, instead of crediting all of it to the former.
    """
    surrogate = HurdleMarginal(p0=p0, positive_dist="beta",
                               positive_params=(2.0, 5.0, 0.0, 1.0),
                               n_zero=0, n_positive=0, positive_aic={})
    estimates = []
    for rep in range(reps):
        rng = np.random.default_rng(seed + rep)
        u, v = GumbelSurvivalCopula(theta).sample(size, rng)
        v_pseudo = distributional_transform(
            surrogate.ppf(v), surrogate.cdf, surrogate.cdf_left_limit,
            # A jitter stream independent of the data stream: sharing a seed
            # would correlate the jitter with the atom mask.
            np.random.default_rng(seed + 5000 + rep))
        estimates.append(GumbelSurvivalCopula.fit(u, v_pseudo).theta)
    return float(np.mean(estimates) / theta)


def _load_spatial_caveat() -> str:
    """The Prompt-2b spatial finding, read from its artifact rather than retyped."""
    if not SPATIAL_METRICS_PATH.exists():
        return ("STGCN's spatial edge over trivial interpolation is unverified "
                "(run models.stgcn.evaluate_spatial); do not claim learned geography.")
    gate = json.loads(SPATIAL_METRICS_PATH.read_text())["honesty_gate"]
    return (
        f"STGCN vs same-timestep IDW: {gate['stgcn_vs_idw_margin_pct']:+.1f}%; "
        f"vs information-matched IDW: "
        f"{gate['stgcn_vs_information_matched_idw_margin_pct']:+.1f}%. The spatial "
        f"component is a mild refinement over trivial interpolation, NOT learned "
        f"geography, and is not weighted as an independent signal."
    )


def _record_exclusion(reason: str, positive_days: int) -> None:
    """Persist a durable out-of-coverage marker for this state and print a clear
    banner. Read by backend.backtest.report --aggregate so the state appears as
    EXCLUDED (with reason) in docs/STATEWISE_RESULTS.md rather than vanishing.
    """
    marker = {
        "excluded": True,
        "state_key": _STATE_KEY,
        "reason": reason,
        "positive_loss_days": positive_days,
        "min_positive_loss_days": MIN_POSITIVE_LOSS_DAYS,
        "stage": "models.fusion.tevi",
        "at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    EXCLUDED_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXCLUDED_PATH.write_text(json.dumps(marker, indent=2))
    print("=" * 78)
    print(f"EXCLUDED (out of coverage): {_STATE_KEY or '<single-city>'}")
    print(f"  {reason}")
    print(f"  This is a DELIBERATE coverage boundary, not an error: too little "
          f"heat-exposure\n  signal to fit a defensible wage-loss distribution. "
          f"Recorded to {EXCLUDED_PATH}.")
    print("=" * 78)


def main() -> int:
    started = time.time()
    rng = np.random.default_rng(SEED)
    print("=" * 78)
    print("mu-TEVI FUSION -- Gumbel copula over (heat trigger, wage loss)")
    print("=" * 78)
    print(f"[SEED]     seed={SEED}")

    # --- Real data --------------------------------------------------------
    weather = load_weather()[["node_id", "date", "wbgt_c"]].rename(columns={"date": "ts"})
    if not WAGE_LOSS_PATH.exists():
        print(f"FATAL: {WAGE_LOSS_PATH} missing. Run models.behavioral_agent.calibration first.")
        return 1
    wage_loss = pd.read_parquet(WAGE_LOSS_PATH)
    merged = wage_loss.merge(weather, on=["node_id", "ts"], how="inner")
    if len(merged) != len(wage_loss):
        print(f"FATAL: wage_loss rows ({len(wage_loss)}) did not all match weather "
              f"({len(merged)}). Refusing to fuse misaligned data.")
        return 1

    # --- The two structural corrections -----------------------------------
    # 1. Restore the cited-zero atom that Prompt 3's logit smeared away.
    merged["loss_hurdle"] = np.where(
        merged["wbgt_c"] <= CITED_ZERO_THRESHOLD_C, 0.0, merged["wage_loss_fraction"])

    # Node-day portfolio: equal-weight across the three occupations. The unit of
    # analysis is the node-day, which is where p0 is defined.
    node_day = merged.groupby(["node_id", "ts"], as_index=False).agg(
        loss_hurdle=("loss_hurdle", "mean"),
        loss_naive=("wage_loss_fraction", "mean"),
        node_wbgt=("wbgt_c", "first"),
    )
    # 2. The trigger is a CITY index, not the node's own heat (see module docstring).
    city_index = weather.groupby("ts", as_index=False).wbgt_c.max().rename(
        columns={"wbgt_c": "heat_index"})
    node_day = node_day.merge(city_index, on="ts", how="left").sort_values(
        ["ts", "node_id"]).reset_index(drop=True)

    in_zero_region = (node_day["node_wbgt"] <= CITED_ZERO_THRESHOLD_C).to_numpy()
    n_nodes = node_day["node_id"].nunique()
    print(f"[REAL]     {len(node_day)} node-days ({n_nodes} nodes x "
          f"{node_day['ts'].nunique()} days), 3 occupations pooled equal-weight")
    print(f"[TRIGGER]  city daily max shade-WBGT | basis gap (city - node): "
          f"mean={float((node_day.heat_index - node_day.node_wbgt).mean()):.3f}C "
          f"sd={float((node_day.heat_index - node_day.node_wbgt).std()):.3f}C")

    # --- F_H: GEV ---------------------------------------------------------
    gev = fit_gev(city_index["heat_index"].to_numpy())
    print()
    print(f"[F_H]      GEV(c={gev['params']['c']:.4f}, loc={gev['params']['loc']:.4f}, "
          f"scale={gev['params']['scale']:.4f}) on the city daily max (a spatial block maximum)")
    print(f"           best family by AIC: {gev['best_by_aic']} "
          f"({', '.join(f'{k}={v[chr(97)+chr(105)+chr(99)]:.0f}' for k, v in gev['candidates'].items())})")
    print(f"           HONEST FIT CAVEAT: KS={gev['ks']:.4f} vs 5% critical "
          f"{gev['ks_critical_5pct']:.4f} -> "
          f"{'REJECTED' if gev['ks_rejects_at_5pct'] else 'not rejected'}. The daily city max "
          f"is strongly SEASONAL, so its")
    print("           unconditional law is a seasonal mixture, not one GEV. GEV is the best "
          "available family here, not a good absolute fit; theta is re-fitted on")
    print("           empirical ranks below so this misspecification cannot silently move it.")

    # --- F_L: hurdle vs naive ---------------------------------------------
    try:
        hurdle = HurdleMarginal.fit(node_day["loss_hurdle"].to_numpy(), in_zero_region)
    except ValueError as e:
        if "insufficient heat-exposure days" in str(e):
            _record_exclusion(str(e), int((~in_zero_region).sum()))
            return EXCLUSION_EXIT_CODE
        raise
    naive = NaiveMarginal.fit(node_day["loss_naive"].to_numpy())
    smeared_floor = float(node_day.loc[in_zero_region, "loss_naive"].mean())

    print()
    print(f"[F_L]      HURDLE marginal: F_L(0) = p0 = {hurdle.p0:.4f}; "
          f"F_L(x) = p0 + (1-p0)*G(x) for x>0")
    print(f"           zero atom     : {hurdle.n_zero:6d} node-days "
          f"({hurdle.p0 * 100:.2f}%) at or below the cited {CITED_ZERO_THRESHOLD_C:.0f}C threshold")
    print(f"           positive part : {hurdle.n_positive:6d} node-days "
          f"({(1 - hurdle.p0) * 100:.2f}%)")
    print(f"           positive dist : {hurdle.positive_dist} (chosen by lower AIC: "
          f"{', '.join(f'{k}={v:.0f}' for k, v in hurdle.to_dict()['positive_aic'].items())})")
    print(f"           WHY THIS IS REQUIRED: Prompt 3's logit is strictly positive "
          f"everywhere, so it smeared those {hurdle.n_zero} cited-zero node-days into a")
    print(f"           mean {smeared_floor * 100:.2f}% wage-loss floor where the literature says "
          f"the loss is exactly 0. The hurdle restores the atom.")

    # --- Copula on the hurdle pseudo-observations -------------------------
    u = gev_cdf(node_day["heat_index"].to_numpy(), gev["params_tuple"])
    v_hurdle = distributional_transform(
        node_day["loss_hurdle"].to_numpy(), hurdle.cdf, hurdle.cdf_left_limit, rng)
    copula = GumbelSurvivalCopula.fit(u, v_hurdle)

    # Naive: single-piece marginal, no atom, hence no ties.
    v_naive = naive.cdf(node_day["loss_naive"].to_numpy())
    copula_naive = GumbelSurvivalCopula.fit(u, v_naive)
    theta_delta = copula.theta - copula_naive.theta

    print()
    print("[COPULA]   Gumbel, fitted by MLE on pseudo-observations (theta >= 1)")
    print(f"           TIE HANDLING: distributional transform (Rueschendorf) -- the "
          f"{hurdle.n_zero} atom observations are")
    print("           spread uniformly over the CDF interval [0, p0] they occupy. Mid-ranks "
          "would pin all of them to")
    print(f"           the single value {hurdle.p0 / 2:.4f}, leaving the pseudo-observations "
          f"non-uniform and the MLE biased.")
    print(f"           theta (hurdle) = {copula.theta:.4f}  "
          f"tau={copula.kendall_tau():.4f}  lambda_U={copula.upper_tail_dependence():.4f}")
    print(f"           theta (naive ) = {copula_naive.theta:.4f}  "
          f"tau={copula_naive.kendall_tau():.4f}  lambda_U={copula_naive.upper_tail_dependence():.4f}")
    print(f"           -> theta_naive_vs_hurdle_delta = {theta_delta:+.4f} "
          f"({theta_delta / copula_naive.theta * 100:+.2f}%)")
    print(f"              lambda_U moves {copula_naive.upper_tail_dependence():.4f} -> "
          f"{copula.upper_tail_dependence():.4f} "
          f"({copula.upper_tail_dependence() - copula_naive.upper_tail_dependence():+.4f}); "
          f"the naive marginal OVERSTATES tail dependence,")
    print("              i.e. understates basis risk, i.e. underprices the contract.")
    if copula.fit_hit_bound:
        print("           WARNING: theta hit the optimizer bound -- the data are effectively "
              "comonotone and theta is NOT identified.")

    # The delta above is NOT purely the smearing effect -- decompose it.
    attenuation = estimate_atom_attenuation(copula.theta, hurdle.p0, size=40_000)
    theta_latent = copula.theta / attenuation
    delta_adjusted = theta_latent - copula_naive.theta
    print()
    print("[DECOMPOSE] The raw delta CONFLATES two effects and must not be reported as one:")
    print("           (a) atom-induced ATTENUATION: an atom destroys the ordering information "
          "inside it, so theta fitted on")
    print(f"               hurdle pseudo-obs is biased toward independence. Measured by "
          f"simulation at (theta={copula.theta:.3f}, p0={hurdle.p0:.3f}):")
    print(f"               attenuation factor = {attenuation:.4f} "
          f"({(attenuation - 1) * 100:+.2f}%) -> attenuation-corrected theta_hurdle "
          f"= {theta_latent:.4f}")
    print("               This is an estimand property (Genest & Neslehova 2007 "
          "non-identifiability under ties), NOT a code defect.")
    print(f"           (b) the REAL smearing effect, net of (a): "
          f"{delta_adjusted:+.4f} ({delta_adjusted / copula_naive.theta * 100:+.2f}%)")
    if abs(delta_adjusted) < abs(theta_delta) * 0.5:
        print(f"           HONEST READING: most of the raw delta ({theta_delta:+.4f}) is the "
              f"statistical attenuation, not the smearing. The smearing's")
        print("           true effect on theta is the smaller adjusted figure. Do not quote "
              "the raw delta as 'the cost of Prompt 3's smearing'.")
    else:
        print("           HONEST READING: the smearing effect survives the attenuation "
              "correction, so the raw delta is mostly real.")

    # Where the smearing ACTUALLY costs: the marginal, not the dependence.
    naive_p_zero = float(naive.cdf(0.0))
    print()
    print("[WHERE THE SMEARING ACTUALLY BITES] Not the copula -- the MARGINAL:")
    print(f"           P(loss is exactly 0):  hurdle = {hurdle.p0:.4f}   "
          f"naive single-piece = {naive_p_zero:.4f}")
    print(f"           The naive marginal assigns ~zero probability to a zero-loss day, when "
          f"{hurdle.p0 * 100:.1f}% of real node-days have")
    print("           exactly zero cited loss. THAT is the expensive error: it drives the "
          "payout probability on roughly a third of all")
    print(f"           days. The dependence parameter barely moves ({delta_adjusted:+.4f} once "
          f"attenuation is netted out); the marginal moves")
    print(f"           by {hurdle.p0 - naive_p_zero:.4f} in probability. Prompt 5 must sample the "
          f"hurdle (see the recipe in this module's docstring),")
    print("           or it will price a third of the calendar as if a small loss were certain.")

    # Robustness: empirical ranks (immune to marginal misspecification) and mid-ranks.
    theta_ranks = GumbelSurvivalCopula.fit(
        empirical_pseudo_obs(node_day["heat_index"].to_numpy()),
        empirical_pseudo_obs(node_day["loss_hurdle"].to_numpy())).theta
    theta_midrank = GumbelSurvivalCopula.fit(
        u, mid_rank_transform(node_day["loss_hurdle"].to_numpy(),
                              hurdle.cdf, hurdle.cdf_left_limit)).theta
    tau_emp = float(kendalltau(node_day["heat_index"], node_day["loss_hurdle"]).statistic)
    print("           ROBUSTNESS -- what the spread does and does NOT show:")
    print(f"             MLE + distributional transform : {copula.theta:.4f}")
    print(f"             MLE on empirical ranks         : {theta_ranks:.4f}  (marginal-free)")
    print(f"             MLE + mid-rank ties            : {theta_midrank:.4f}")
    print(f"             moment 1/(1-tau_b)             : {1 / (1 - tau_emp):.4f}  "
          f"(tau_b={tau_emp:.4f}, computed on tied raw data)")
    print(f"           The first two agree to {abs(copula.theta - theta_ranks):.4f}, which is the "
          f"claim worth making: the imperfect GEV does NOT move theta,")
    print("           because rank-based pseudo-obs are immune to marginal misspecification. "
          "The last two DIVERGE, and that is expected, not")
    print("           reassuring: they handle the atom's ties differently, and under ties the "
          "copula is genuinely not identified. theta is")
    print("           conditional on the tie convention -- so it is reported with the "
          "convention named, never as a bare number.")
    print(f"           NOTE ON INDEPENDENCE: the {len(node_day)} node-days are NOT independent "
          f"({n_nodes} nodes share each day's trigger and are")
    print("           spatially correlated >0.998), so this is a composite pseudo-likelihood: "
          "theta is consistent but its standard error would be understated.")

    # --- mu-TEVI series ---------------------------------------------------
    calc = TEVICalculator(gev["params_tuple"], hurdle, copula)
    node_day["mu_tevi"] = calc.node_day_index(
        node_day["heat_index"].to_numpy(), node_day["loss_hurdle"].to_numpy())
    daily = node_day.groupby("ts", as_index=False)["mu_tevi"].mean().sort_values("ts")

    print()
    print(f"[mu-TEVI]  100*(1 - P(H>h, L>l)) per node-day, averaged over the {n_nodes} nodes "
          f"-> daily index")
    print(f"           range=[{daily.mu_tevi.min():.2f}, {daily.mu_tevi.max():.2f}]  "
          f"mean={daily.mu_tevi.mean():.2f}  median={daily.mu_tevi.median():.2f}")
    print(f"[SPATIAL HONESTY] {_load_spatial_caveat()}")

    MU_TEVI_PATH.parent.mkdir(parents=True, exist_ok=True)
    daily[["ts", "mu_tevi"]].to_parquet(MU_TEVI_PATH, index=False)
    print(f"[ARTIFACT] {MU_TEVI_PATH}  rows={len(daily)} cols=['ts', 'mu_tevi']")

    # --- copula.json ------------------------------------------------------
    payload = {
        "theta": copula.theta,
        "gev_params": gev["params"],
        "hurdle": hurdle.to_dict(),
        "tau_convention": TAU_CONVENTION,
        "theta_naive_vs_hurdle_delta": theta_delta,
        "theta_naive": copula_naive.theta,
        "atom_attenuation": {
            "factor": attenuation,
            "theta_hurdle_attenuation_corrected": theta_latent,
            "theta_naive_vs_hurdle_delta_attenuation_adjusted": delta_adjusted,
            "note": (
                "The raw theta_naive_vs_hurdle_delta conflates TWO effects: (a) the real "
                "correction from restoring the cited-zero atom, and (b) attenuation, because "
                "an atom destroys the ordering information inside it so theta fitted on hurdle "
                "pseudo-observations is biased toward independence (Genest & Neslehova 2007: "
                "the copula is not uniquely identified under ties). The factor here is measured "
                "by simulation at the fitted (theta, p0). Quote the attenuation-adjusted delta "
                "as 'the cost of Prompt 3's smearing', NOT the raw one."
            ),
        },
        "upper_tail_dependence": copula.upper_tail_dependence(),
        "upper_tail_dependence_naive": copula_naive.upper_tail_dependence(),
        "kendall_tau": copula.kendall_tau(),
        "tau_convention_note": (
            "kappa/gamma from Prompt 3's calibration are CONDITIONAL on the fixed logit "
            "choice-noise scale tau = 0.1*wage. (kappa, gamma, tau) are jointly "
            "non-identified from a single choice curve; a different tau describes the "
            "same curve with different kappa/gamma. Do not treat kappa/gamma as "
            "free-standing physical constants."
        ),
        "pairing": {
            "trigger": "city-level daily max shade-WBGT (spatial block maximum)",
            "loss": "hurdle-corrected wage loss at the worker's own node, occupations "
                    "equal-weighted",
            "models": "spatial basis risk between the parametric trigger and the "
                      "worker's actual loss",
            "why_not_own_node_heat": (
                "Prompt 3's calibration makes loss a deterministic monotone function of "
                "WBGT (measured spearman = 1.0000000000 exactly per occupation), so "
                "pairing a node's own heat with its own loss is exactly comonotone: "
                "theta diverges and the copula is vacuous."
            ),
        },
        "tie_handling": "distributional transform (Rueschendorf); mid-rank reported as robustness",
        "where_the_smearing_bites": {
            "p_zero_loss_hurdle": hurdle.p0,
            "p_zero_loss_naive": naive_p_zero,
            "note": (
                "The smearing's expensive error is in the MARGINAL, not the dependence. The "
                "naive single-piece F_L gives ~0 probability to a zero-loss day when 33.5% of "
                "real node-days have exactly zero cited loss; that drives payout probability on "
                "a third of the calendar. Net of attenuation, theta itself barely moves."
            ),
        },
        "robustness": {
            "theta_empirical_ranks": theta_ranks,
            "theta_mid_rank_ties": theta_midrank,
            "theta_from_empirical_tau_moment": float(1 / (1 - tau_emp)),
            "kendall_tau_empirical": tau_emp,
            "note": (
                "theta via distributional transform and via empirical ranks agree closely, which "
                "shows the imperfect GEV does NOT drive theta (rank-based pseudo-obs are immune "
                "to marginal misspecification). The mid-rank and tau_b figures DIVERGE, which is "
                "expected rather than reassuring: under ties the copula is not uniquely "
                "identified, so theta is conditional on the stated tie convention."
            ),
        },
        "gev_fit_quality": {
            "ks": gev["ks"],
            "ks_critical_5pct": gev["ks_critical_5pct"],
            "ks_rejects_at_5pct": gev["ks_rejects_at_5pct"],
            "best_by_aic": gev["best_by_aic"],
            "caveat": "The daily city max is strongly seasonal, so its unconditional law is a "
                      "seasonal mixture, not a single GEV. GEV is the best available family, "
                      "not a good absolute fit.",
        },
        "spatial_honesty": _load_spatial_caveat(),
        "hurdle_sampling_recipe_for_prompt5": (
            "Draw (u,v) from GumbelSurvivalCopula(theta).sample(); h = genextreme.ppf(u, "
            "*gev_params); l = HurdleMarginal.ppf(v) -> EXACTLY 0 when v <= p0, else "
            "beta.ppf((v-p0)/(1-p0), *positive_params). Never sample a single continuous "
            "distribution over [0, max]: that reintroduces the ~2.4% smeared floor and "
            "misprices every zero-loss day (~a third of them)."
        ),
        "seed": SEED,
        "n_node_days": int(len(node_day)),
        "independence_caveat": (
            f"The {len(node_day)} node-days are not independent ({n_nodes} nodes share each "
            f"day's trigger, spatial correlation >0.998); this is a composite "
            f"pseudo-likelihood. theta is consistent; its standard error is understated."
        ),
    }
    COPULA_PATH.parent.mkdir(parents=True, exist_ok=True)
    COPULA_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"[ARTIFACT] {COPULA_PATH}")

    _plot_gev_qq(city_index["heat_index"].to_numpy(), gev)
    _plot_hurdle(node_day, in_zero_region, hurdle, naive, smeared_floor)
    print(f"[ARTIFACT] {QQ_PLOT_PATH}")
    print(f"[ARTIFACT] {HURDLE_PLOT_PATH}")
    print(f"[TIME]     {time.time() - started:.1f}s total")
    print("=" * 78)
    return 0


def _plot_gev_qq(heat: np.ndarray, gev: dict) -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.4))
    n = len(heat)
    probs = (np.arange(1, n + 1) - 0.5) / n
    theoretical = stats.genextreme.ppf(probs, *gev["params_tuple"])
    empirical = np.sort(heat)
    ax1.scatter(theoretical, empirical, s=3, alpha=0.35, color="#2a9d8f")
    lims = [min(theoretical.min(), empirical.min()), max(theoretical.max(), empirical.max())]
    ax1.plot(lims, lims, ls="--", c="#c1121f", lw=1.2, label="y = x")
    ax1.set(xlabel="GEV theoretical quantile (degC)", ylabel="empirical quantile (degC)",
            title=f"F_H GEV QQ -- KS={gev['ks']:.4f} vs 5% crit {gev['ks_critical_5pct']:.4f}\n"
                  f"({'REJECTED' if gev['ks_rejects_at_5pct'] else 'not rejected'}: "
                  f"the series is seasonal, not one GEV)")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    ax2.hist(heat, bins=60, density=True, color="#dee2e6", label="city daily max WBGT")
    grid = np.linspace(heat.min(), heat.max(), 400)
    ax2.plot(grid, stats.genextreme.pdf(grid, *gev["params_tuple"]), color="#c1121f",
             lw=1.6, label="fitted GEV")
    ax2.set(xlabel="shade-WBGT (degC)", ylabel="density",
            title="Fitted GEV vs the real trigger distribution")
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    QQ_PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(QQ_PLOT_PATH, dpi=130)
    plt.close(fig)


def _plot_hurdle(node_day: pd.DataFrame, in_zero_region: np.ndarray,
                 hurdle: HurdleMarginal, naive: NaiveMarginal, smeared_floor: float) -> None:
    """Show the restored point mass against Prompt 3's smeared version."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.6))

    naive_losses = node_day["loss_naive"].to_numpy()
    hurdle_losses = node_day["loss_hurdle"].to_numpy()

    ax1.hist(naive_losses[in_zero_region], bins=40, color="#c1121f", alpha=0.75,
             label=f"Prompt 3 (smeared): {in_zero_region.sum()} cited-zero\n"
                   f"node-days spread over a ~{smeared_floor * 100:.1f}% floor")
    ax1.axvline(0.0, color="#2a9d8f", lw=3.0,
                label=f"hurdle: all {hurdle.n_zero} restored to EXACTLY 0")
    ax1.set(xlabel="wage-loss fraction", ylabel="node-days",
            title="The cited-zero region (WBGT <= "
                  f"{CITED_ZERO_THRESHOLD_C:.0f}C)\nsmeared vs restored")
    ax1.legend(fontsize=7)
    ax1.grid(alpha=0.3)

    grid = np.linspace(-0.02, float(hurdle_losses.max()) * 1.05, 600)
    ax2.plot(grid, hurdle.cdf(grid), color="#2a9d8f", lw=1.8,
             label=f"hurdle F_L (atom p0={hurdle.p0:.3f})")
    ax2.plot(grid, naive.cdf(grid), color="#c1121f", lw=1.4, ls="--",
             label=f"naive single-piece F_L ({naive.dist_name})")
    ax2.plot([0.0], [hurdle.p0], marker="o", ms=7, color="#2a9d8f")
    ax2.annotate(f"point mass p0={hurdle.p0:.3f}", xy=(0.0, hurdle.p0),
                 xytext=(0.06, hurdle.p0 - 0.16), fontsize=8,
                 arrowprops=dict(arrowstyle="->", lw=1.0))
    ax2.set(xlabel="wage-loss fraction", ylabel="F_L(x)",
            title="Marginal CDF: the hurdle has an atom at 0,\nthe naive fit does not")
    ax2.legend(fontsize=8, loc="lower right")
    ax2.grid(alpha=0.3)

    fig.suptitle("F_L hurdle marginal -- restoring the cited-zero atom Prompt 3 smeared away",
                 fontsize=11)
    fig.tight_layout()
    HURDLE_PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(HURDLE_PLOT_PATH, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
