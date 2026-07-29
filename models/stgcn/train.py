"""Train the STGCN street-level heat map on REAL NASA POWER weather.

Target: shade-WBGT (degC) at every real POWER grid node, `HORIZON` days ahead
from a `T_IN`-day history window.

Protocol (this is the part that has to be right, not merely runnable):

  * SPATIAL split, strictly inductive. 20% of nodes are held out BY LOCATION.
    The training graph is REBUILT over the remaining nodes only, so the held-out
    locations are absent from the Laplacian during training -- not merely masked
    out of the loss. Chebyshev theta is (K, C_in, C_out), independent of node
    count, so the same weights are then evaluated on the full graph. Splitting by
    timestep instead would leak: every node's neighbours would already be fitted.

  * GLOBAL normalization from train-nodes x train-time ONLY. Per-node statistics
    would both leak held-out nodes' moments into training and be undefined for a
    location the model has never seen -- which is exactly the case at inference.

  * Early stopping watches train-NODES x val-TIME. Watching the held-out nodes
    would leak the test set into model selection.

  * Headline held-out MAE is scored on held-out-NODES x val-TIME: unseen places
    AND unseen days. The baseline is scored on the identical cells.

Determinism: seed=42 for random/numpy/torch (CLAUDE.md Golden Rule 3), logged
below. CPU-only (Golden Rule 2). Data is real or it stops (Golden Rule 5): the
weather comes through backend.data.recovery, which fatal_aborts on MODE A and
fills MODE B gaps with nearest real observations only.
"""

from __future__ import annotations

import argparse
import copy
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
import torch
import yaml
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from backend.data.build_wage_loss import CITIES_YAML_PATH
from backend.data.weather import WeatherLoader, default_end_date
from models.stgcn.city_graph import CityGraphBuilder
from models.stgcn.model import STGCN

SEED = 42

# Per-state namespacing (v2 state-wise pipelines): when STATE_KEY is set -- the
# batch runner sets it per-state in a subprocess -- every I/O path is namespaced
# under that state's dirs and the heat grid is its anchor-metro bbox. When
# UNSET, behaviour is exactly the legacy single-city path, so `make reproduce`
# and the existing tests are unchanged. (CLAUDE.md Golden Rule 9 -- explicit
# paths, never inferred; here the state_key makes them explicit per state.)
STATE_KEY = os.environ.get("STATE_KEY")
if STATE_KEY:
    from backend.state_context import get_context

    _CTX = get_context(STATE_KEY)
    WEATHER_PARQUET = _CTX.processed("weather.parquet")
    MODEL_PATH = _CTX.artifact("stgcn.pt")
    PLOT_PATH = _CTX.artifact("stgcn_mae.png")
else:
    _CTX = None
    WEATHER_PARQUET = Path("data/processed/weather.parquet")
    MODEL_PATH = Path("models/artifacts/stgcn.pt")
    PLOT_PATH = Path("notebooks/artifacts/stgcn_mae.png")

# Laptop-scoped hyperparameters (Golden Rule 4).
T_IN = 12
HORIZON = 3
HIDDEN = 16
K_ORDER = 3
KERNEL_T = 3
KNN_K = 4
MAX_EPOCHS = 30
PATIENCE = 5
BATCH_SIZE = 32
LR = 1e-3
TEST_NODE_FRAC = 0.20
TIME_TRAIN_FRAC = 0.80

TARGET_COL = "wbgt_c"


def set_seeds(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_weather(start: str = "20140101", end: str | None = None) -> pd.DataFrame:
    """Real NASA POWER weather with WBGT, cached at WEATHER_PARQUET.

    On a cache miss this rebuilds from the raw NASA POWER responses already in
    data/raw/ via WeatherLoader (no network call when the raw cache is warm),
    so `make reproduce` is deterministic. MODE A / MODE B are enforced inside
    backend.data.recovery; nothing is fabricated here.

    `end` defaults to `default_end_date()` (today minus NASA POWER's real
    processing lag) so a FUTURE training run naturally fetches up to real
    current data; existing cached WEATHER_PARQUET files are returned as-is
    below and never re-fetched by this change.
    """
    if WEATHER_PARQUET.exists():
        return pd.read_parquet(WEATHER_PARQUET)
    end = end or default_end_date()

    if _CTX is not None:
        bbox = _CTX.bbox            # this state's anchor-metro grid
    else:
        with open(CITIES_YAML_PATH) as f:
            config = yaml.safe_load(f)
        bbox = config["cities"][config["default_city"]]["bbox"]

    loader = WeatherLoader(bbox=bbox)
    raw = loader.fetch_daily(start=start, end=end)
    filled, proxies = loader.fill_gaps(raw)
    filled = filled.assign(**{TARGET_COL: loader.to_wbgt_approx(filled)})

    total_cells = len(filled) * 2  # T2M, RH2M
    rate = (len(proxies) / total_cells * 100.0) if total_cells else 0.0
    print(f"[MODE B]   Gap-filled cells: {len(proxies)}/{total_cells} ({rate:.3f}% proxy rate)")

    WEATHER_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    filled.to_parquet(WEATHER_PARQUET, index=False)
    return filled


def to_node_time_matrix(df: pd.DataFrame) -> tuple[np.ndarray, list[str], pd.DataFrame]:
    """-> (T, N) WBGT matrix, node_ids in column order, matching coords."""
    pivot = df.pivot(index="date", columns="node_id", values=TARGET_COL).sort_index()
    node_ids = [str(c) for c in pivot.columns]

    if pivot.isna().to_numpy().any():
        # A real gap survived MODE B. Never fill it here -- that would fabricate.
        n_missing = int(pivot.isna().to_numpy().sum())
        print(
            f"FATAL: {n_missing} WBGT cells are still missing after MODE B gap-fill.\n"
            f"No fabricated or synthetic data is permitted. Aborting."
        )
        sys.exit(1)

    coords = (
        df.drop_duplicates("node_id").set_index("node_id").loc[node_ids, ["lat", "lon"]]
        .reset_index()
    )
    return pivot.to_numpy(dtype=np.float32), node_ids, coords


def split_nodes(n_nodes: int, frac: float, seed: int = SEED) -> tuple[np.ndarray, np.ndarray]:
    """Hold out `frac` of nodes BY LOCATION (never by timestep)."""
    n_test = max(1, int(round(frac * n_nodes)))
    if n_test >= n_nodes:
        raise ValueError(f"cannot hold out {n_test} of {n_nodes} nodes")
    perm = np.random.default_rng(seed).permutation(n_nodes)
    return np.sort(perm[n_test:]), np.sort(perm[:n_test])


def window_starts(n_steps: int, t_in: int, horizon: int) -> np.ndarray:
    return np.arange(0, n_steps - t_in - horizon + 1)


def build_xy(arr: np.ndarray, starts: np.ndarray, node_cols: np.ndarray,
             t_in: int, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    """-> X (S, t_in, n, 1), Y (S, n, horizon) over the given nodes/windows."""
    sub = arr[:, node_cols]
    x_idx = starts[:, None] + np.arange(t_in)[None, :]
    y_idx = starts[:, None] + t_in + np.arange(horizon)[None, :]
    x = sub[x_idx][..., None].astype(np.float32)
    y = np.transpose(sub[y_idx], (0, 2, 1)).astype(np.float32)
    return x, y


@torch.no_grad()
def predict(model: STGCN, x: torch.Tensor, basis: torch.Tensor,
            batch_size: int = 256) -> torch.Tensor:
    model.eval()
    return torch.cat([model(x[i:i + batch_size], basis) for i in range(0, len(x), batch_size)])


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the STGCN heat map on real NASA POWER data")
    parser.add_argument("--epochs", type=int, default=MAX_EPOCHS)
    parser.add_argument("--start", default="20140101")
    parser.add_argument("--end", default=None, help="YYYYMMDD; defaults to today minus NASA POWER's real processing lag")
    args = parser.parse_args()

    started = time.time()
    set_seeds(SEED)
    torch.set_num_threads(1)  # deterministic CPU reduction order
    print("=" * 72)
    print("STGCN TRAINING -- street-level heat map (shade-WBGT, degC)")
    print("=" * 72)
    print(f"[SEED]     seed={SEED} (random, numpy, torch) | device=cpu")

    # --- Real data -------------------------------------------------------
    weather = load_weather(start=args.start, end=args.end)
    arr, node_ids, coords = to_node_time_matrix(weather)
    n_steps, n_nodes = arr.shape
    print(f"[REAL API] NASA POWER shade-WBGT: nodes={n_nodes} days={n_steps} "
          f"(node count read from data, never hardcoded)")

    # --- Spatial split, then graphs -------------------------------------
    train_nodes, test_nodes = split_nodes(n_nodes, TEST_NODE_FRAC, SEED)
    builder = CityGraphBuilder(coords, k=KNN_K)
    full_graph = builder.build(k_order=K_ORDER)
    train_graph = builder.subgraph(train_nodes, k_order=K_ORDER)
    print(f"[SPLIT]    spatial (by location): train={len(train_nodes)} nodes, "
          f"held-out={len(test_nodes)} nodes -> {[node_ids[i] for i in test_nodes]}")
    print(f"[GRAPH]    kNN k={builder.k} | full: N={full_graph.n_nodes} "
          f"lambda_max={full_graph.lambda_max:.4f} | train subgraph: N={train_graph.n_nodes} "
          f"lambda_max={train_graph.lambda_max:.4f} | Chebyshev K={K_ORDER} rescaled to [-1,1]")

    full_basis = torch.from_numpy(full_graph.cheb_basis).float()
    train_basis = torch.from_numpy(train_graph.cheb_basis).float()

    # --- Time split (early-stopping signal + honest eval window) ----------
    split_t = int(TIME_TRAIN_FRAC * n_steps)
    starts = window_starts(n_steps, T_IN, HORIZON)
    # Strict: a training window's TARGET must end before the val period, and a
    # val window's INPUT must start at/after it. Straddling windows are dropped.
    train_starts = starts[starts + T_IN + HORIZON <= split_t]
    val_starts = starts[starts >= split_t]
    print(f"[SPLIT]    time: train windows={len(train_starts)} (<= day {split_t}), "
          f"val windows={len(val_starts)} (>= day {split_t}), "
          f"{len(starts) - len(train_starts) - len(val_starts)} straddling dropped")

    # --- Normalization: train nodes x train time ONLY ---------------------
    fit_block = arr[:split_t][:, train_nodes]
    mu, sigma = float(fit_block.mean()), float(fit_block.std())
    if sigma <= 0.0:
        print("FATAL: zero variance in the training block. Aborting.")
        sys.exit(1)
    print(f"[NORM]     global z-score from train-nodes x train-time only: "
          f"mu={mu:.4f} sigma={sigma:.4f} degC")

    norm = (arr - mu) / sigma

    # Training/validation tensors live on the TRAIN SUBGRAPH (12 nodes).
    x_tr, y_tr = build_xy(norm, train_starts, train_nodes, T_IN, HORIZON)
    x_va, y_va = build_xy(norm, val_starts, train_nodes, T_IN, HORIZON)
    x_tr_t = torch.from_numpy(x_tr)
    y_tr_t = torch.from_numpy(y_tr)
    x_va_t = torch.from_numpy(x_va)
    y_va_t = torch.from_numpy(y_va)

    loader = DataLoader(
        TensorDataset(x_tr_t, y_tr_t), batch_size=BATCH_SIZE, shuffle=True,
        generator=torch.Generator().manual_seed(SEED),
    )

    # --- Model -----------------------------------------------------------
    model = STGCN(in_channels=1, hidden=HIDDEN, horizon=HORIZON, t_in=T_IN,
                  k_order=K_ORDER, kernel_size=KERNEL_T)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[MODEL]    STGCN 2 ST-blocks hidden={HIDDEN} K={K_ORDER} t_in={T_IN} "
          f"horizon={HORIZON}d | params={n_params} (node-count agnostic)")

    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    # MSE for training (STGCN standard); MAE is the reported metric. The squared
    # penalty keeps weight on heat extremes, which are what a heatwave contract
    # actually pays out on.
    criterion = nn.MSELoss()

    history: list[dict] = []
    best_val = float("inf")
    best_state = copy.deepcopy(model.state_dict())
    best_epoch = 0
    no_improve = 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        total, seen = 0.0, 0
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = criterion(model(xb, train_basis), yb)
            loss.backward()
            optimizer.step()
            total += loss.item() * len(xb)
            seen += len(xb)
        train_loss = total / max(seen, 1)

        # Validation: train NODES, val TIME. No held-out node is involved.
        val_mae = float(
            (predict(model, x_va_t, train_basis) - y_va_t).abs().mean().item() * sigma
        )
        history.append({"epoch": epoch, "train_loss": train_loss, "val_mae_c": val_mae})

        if val_mae < best_val - 1e-6:
            best_val, best_epoch, no_improve = val_mae, epoch, 0
            best_state = copy.deepcopy(model.state_dict())
        else:
            no_improve += 1

        print(f"  epoch {epoch:2d}/{args.epochs}  train_mse={train_loss:.5f}  "
              f"val_mae={val_mae:.4f} degC{'  *' if best_epoch == epoch else ''}")

        if no_improve >= PATIENCE:
            print(f"[EARLY]    stopped at epoch {epoch}: no val improvement in {PATIENCE} epochs")
            break

    model.load_state_dict(best_state)
    print(f"[BEST]     epoch {best_epoch}, val_mae={best_val:.4f} degC (weights restored)")

    # --- Held-out evaluation: unseen NODES x unseen TIME, FULL graph ------
    x_ev, y_ev = build_xy(norm, val_starts, np.arange(n_nodes), T_IN, HORIZON)
    pred_norm = predict(model, torch.from_numpy(x_ev), full_basis).numpy()
    pred_c = pred_norm * sigma + mu
    true_c = y_ev * sigma + mu

    model_mae = float(np.abs(pred_c[:, test_nodes, :] - true_c[:, test_nodes, :]).mean())

    # Baseline: each node's own historical mean, computed on the TRAIN TIME
    # window only, so it does not peek at the evaluation days either.
    node_hist_mean = arr[:split_t].mean(axis=0)
    base_pred = node_hist_mean[None, :, None]
    baseline_mae = float(
        np.abs(base_pred[:, test_nodes, :] - true_c[:, test_nodes, :]).mean()
    )

    # Extra diagnostic (NOT the acceptance gate): persistence -- carry the last
    # observed value forward. A reviewer will ask whether a static climatology
    # is a straw man, so report the harder baseline honestly alongside it.
    last_obs = (x_ev[:, -1, :, 0] * sigma + mu)[:, :, None]
    persistence_mae = float(
        np.abs(last_obs[:, test_nodes, :] - true_c[:, test_nodes, :]).mean()
    )

    beat = model_mae < baseline_mae
    improvement = (baseline_mae - model_mae) / baseline_mae * 100.0

    print("=" * 72)
    print("HELD-OUT EVALUATION -- unseen NODES x unseen TIME (full graph)")
    print("=" * 72)
    print(f"  held-out nodes      : {[node_ids[i] for i in test_nodes]}")
    print(f"  cells scored        : {len(val_starts) * len(test_nodes) * HORIZON}")
    print(f"  STGCN MAE           : {model_mae:.4f} degC")
    print(f"  baseline MAE        : {baseline_mae:.4f} degC  (each node's own historical mean)")
    print(f"  -> improvement      : {improvement:+.2f}% vs baseline")
    print(f"  [diagnostic] persistence MAE : {persistence_mae:.4f} degC (not the gate)")
    if beat:
        print("  ACCEPTANCE: PASS -- held-out MAE is below the historical-mean baseline.")
    else:
        print(f"  ACCEPTANCE: NOT MET in {len(history)} epochs. Model saved anyway; "
              f"held-out MAE did NOT beat the historical-mean baseline. Not looping further.")
    print("=" * 72)

    # --- Persist artifacts ------------------------------------------------
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "config": {
                "in_channels": 1, "hidden": HIDDEN, "horizon": HORIZON, "t_in": T_IN,
                "k_order": K_ORDER, "kernel_size": KERNEL_T, "knn_k": builder.k,
                "target": TARGET_COL, "units": "degC", "seed": SEED,
            },
            "graph": {
                "node_ids": node_ids,
                "coords": full_graph.coords,
                "cheb_basis": full_graph.cheb_basis,
                "lambda_max": full_graph.lambda_max,
            },
            "norm": {"mu": mu, "sigma": sigma, "scope": "train_nodes x train_time"},
            "split": {
                "train_nodes": train_nodes.tolist(),
                "test_nodes": test_nodes.tolist(),
                "split_t": split_t,
                "kind": "inductive_spatial",
            },
            "metrics": {
                "heldout_mae_c": model_mae,
                "baseline_mae_c": baseline_mae,
                "persistence_mae_c": persistence_mae,
                "improvement_pct": improvement,
                "beats_baseline": bool(beat),
                "best_epoch": best_epoch,
                "best_val_mae_c": best_val,
            },
            "history": history,
        },
        MODEL_PATH,
    )
    print(f"[ARTIFACT] {MODEL_PATH}")

    # --- Plot -------------------------------------------------------------
    epochs = [h["epoch"] for h in history]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    ax1.plot(epochs, [h["val_mae_c"] for h in history], marker="o", ms=3,
             color="#c1121f", label="val MAE (train nodes, val time)")
    ax1.axvline(best_epoch, ls=":", c="grey", lw=1, label=f"best epoch ({best_epoch})")
    ax1.set_xlabel("epoch")
    ax1.set_ylabel("MAE (degC WBGT)")
    ax1.set_title("Learning curve")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    names = ["STGCN", "Historical\nmean", "Persistence\n(diagnostic)"]
    values = [model_mae, baseline_mae, persistence_mae]
    bars = ax2.bar(names, values, color=["#2a9d8f", "#adb5bd", "#dee2e6"])
    for bar, val in zip(bars, values):
        ax2.text(bar.get_x() + bar.get_width() / 2, val, f"{val:.3f}",
                 ha="center", va="bottom", fontsize=9)
    ax2.set_ylabel("MAE (degC WBGT)")
    ax2.set_title(f"Held-out: {len(test_nodes)} unseen nodes x unseen time\n"
                  f"{improvement:+.1f}% vs historical-mean baseline")
    ax2.grid(alpha=0.3, axis="y")

    fig.suptitle(f"STGCN heat map -- {n_nodes} real NASA POWER nodes, seed={SEED}", fontsize=11)
    fig.tight_layout()
    PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOT_PATH, dpi=130)
    plt.close(fig)
    print(f"[ARTIFACT] {PLOT_PATH}")
    print(f"[TIME]     {time.time() - started:.1f}s total")

    return 0


if __name__ == "__main__":
    sys.exit(main())
