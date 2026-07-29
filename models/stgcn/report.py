"""Heat-model reporting section: STGCN vs temporal AND spatial baselines.

TODO(Prompt 7 / backtest): this module is currently just the heat-model section
of what should become a full backtest report (pricing performance, claims,
copula fit, etc.). When that report is built, import `heat_model_section()`
from here and slot its returned text in as the heat-model paragraph rather than
re-deriving these numbers -- it reads the single source of truth
(notebooks/artifacts/spatial_baseline_metrics.json) written by
models.stgcn.evaluate_spatial, so the report and the underlying evaluation
script can never silently disagree with each other.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

METRICS_PATH = Path("notebooks/artifacts/spatial_baseline_metrics.json")
COPULA_PATH = Path("models/artifacts/copula.json")


def heat_model_section(metrics_path: Path = METRICS_PATH) -> str:
    """The honest headline claim for the STGCN heat surface.

    States the STGCN's margin over BOTH the temporal baseline (persistence) and
    the spatial baselines (nearest_station, IDW) -- the spatial number is the
    one that actually defends "the model does useful spatial interpolation,"
    since the temporal margin alone (historical-mean / persistence) says
    nothing about generalization to an unseen location.
    """
    if not metrics_path.exists():
        raise FileNotFoundError(
            f"{metrics_path} does not exist. Run `python -m models.stgcn.evaluate_spatial` first."
        )
    data = json.loads(metrics_path.read_text())
    m = data["metrics"]
    gate = data["honesty_gate"]
    protocol = data["protocol"]

    lines = [
        "Heat model (STGCN) -- held-out evaluation",
        f"  {protocol['n_cells']} cells, {len(protocol['held_out_nodes'])} unseen "
        f"locations x {protocol['n_val_windows']} unseen time windows x "
        f"{protocol['horizon']}-day horizon.",
        f"  STGCN MAE            : {m['stgcn']['mae_c']:.4f} degC",
        f"  vs persistence (temporal): {m['persistence']['margin_vs_stgcn_pct']:+.2f}%",
        f"  vs nearest_station (spatial): {m['nearest_station']['margin_vs_stgcn_pct']:+.2f}%",
        f"  vs IDW p={m['idw']['power']} (spatial)   : {m['idw']['margin_vs_stgcn_pct']:+.2f}%",
    ]
    if not gate["clears_threshold"]:
        lines.append(
            f"  HONEST CAVEAT: STGCN does not clearly beat trivial spatial "
            f"interpolation on this grid (margin vs IDW = "
            f"{gate['stgcn_vs_idw_margin_pct']:+.2f}%, threshold "
            f"{gate['threshold_pct']:.0f}%). See "
            f"notebooks/artifacts/spatial_baseline_metrics.json -> "
            f"metrics.idw_information_matched_diagnostic for why."
        )
    else:
        lines.append(
            f"  STGCN clears the spatial-baseline honesty threshold "
            f"({gate['stgcn_vs_idw_margin_pct']:+.2f}% >= {gate['threshold_pct']:.0f}%)."
        )
    return "\n".join(lines)


def fusion_section(copula_path: Path = COPULA_PATH) -> str:
    """The mu-TEVI fusion claim, with its caveats attached rather than dropped.

    Reads models/artifacts/copula.json (written by models.fusion.tevi) as the
    single source of truth, so the report cannot drift from the fit.
    """
    if not copula_path.exists():
        raise FileNotFoundError(
            f"{copula_path} does not exist. Run `python -m models.fusion.tevi` first.")
    d = json.loads(copula_path.read_text())
    hurdle = d["hurdle"]
    atten = d["atom_attenuation"]
    bites = d["where_the_smearing_bites"]

    return "\n".join([
        "mu-TEVI fusion (Gumbel copula over heat trigger x wage loss)",
        f"  What the copula models: {d['pairing']['models']}.",
        f"    trigger = {d['pairing']['trigger']}",
        f"    loss    = {d['pairing']['loss']}",
        f"    NOT the node's own heat: {d['pairing']['why_not_own_node_heat']}",
        f"  theta = {d['theta']:.4f} (tie convention: {d['tie_handling']}), "
        f"lambda_U = {d['upper_tail_dependence']:.4f}",
        f"  F_L hurdle: p0 = {hurdle['p0']:.4f} ({hurdle['n_zero_atom']} node-days at exactly "
        f"zero), positive part = {hurdle['positive_dist']} (by AIC)",
        f"  F_H: GEV, but KS={d['gev_fit_quality']['ks']:.4f} vs 5% critical "
        f"{d['gev_fit_quality']['ks_critical_5pct']:.4f} -> "
        f"{'REJECTED' if d['gev_fit_quality']['ks_rejects_at_5pct'] else 'not rejected'}. "
        f"{d['gev_fit_quality']['caveat']}",
        f"  HONEST CAVEAT (theta delta): the raw naive-vs-hurdle delta "
        f"({d['theta_naive_vs_hurdle_delta']:+.4f}) is mostly the atom-induced attenuation "
        f"(factor {atten['factor']:.4f}), not the smearing. Net of it the smearing moves theta "
        f"by only {atten['theta_naive_vs_hurdle_delta_attenuation_adjusted']:+.4f}.",
        f"  WHERE THE SMEARING ACTUALLY COSTS: the marginal. P(zero-loss day) = "
        f"{bites['p_zero_loss_hurdle']:.4f} under the hurdle vs {bites['p_zero_loss_naive']:.4f} "
        f"under Prompt 3's single-piece fit -- that drives payout probability on a third of the "
        f"calendar.",
        f"  SPATIAL HONESTY: {d['spatial_honesty']}",
        f"  tau convention: kappa/gamma are conditional on tau = {d['tau_convention']}; "
        f"they are not free-standing constants.",
    ])


def main() -> int:
    print(heat_model_section())
    print()
    try:
        print(fusion_section())
    except FileNotFoundError as exc:
        print(f"mu-TEVI fusion section unavailable: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
