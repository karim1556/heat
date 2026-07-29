"""Train the GRU mu-TEVI forecaster (Prompt 8) on the REAL fused city index.

CHRONOLOGICAL split, never shuffled across time: the model trains on earlier
years and validates on later years, matching a real deployment (you only ever
forecast forward). Shuffling windows across time would leak future days into
training for a multi-step sequence model.

Reports the GRU's validation MAE against a persistence baseline
(predicted(t+h) = value at t, "tomorrow = today") HONESTLY -- whichever wins.
If the GRU does not beat persistence, it is saved anyway and the result is
stated as-is; this script does not loop, retune, or cherry-pick a seed to
manufacture a win (the same discipline CLAUDE.md's data rules apply to
metrics: real or it stops, never massaged).
"""

from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from models.forecast.model import GRUForecaster

SEED = 42

# Per-state namespacing (v2): STATE_KEY set -> this state's mu-TEVI series +
# forecaster. Unset -> legacy single-city paths, unchanged.
STATE_KEY = os.environ.get("STATE_KEY")
if STATE_KEY:
    from backend.state_context import get_context

    _CTX = get_context(STATE_KEY)
    MU_TEVI_PATH = _CTX.processed("mu_tevi.parquet")
    MODEL_PATH = _CTX.artifact("forecaster.pt")
else:
    _CTX = None
    MU_TEVI_PATH = Path("data/processed/mu_tevi.parquet")
    MODEL_PATH = Path("models/artifacts/forecaster.pt")

T_IN = 14           # days of history fed to the GRU (matches the 14-day contract window).
HORIZON = 7         # forecast t+1 .. t+7.
HIDDEN = 64
PARAM_BUDGET = 50_000
MAX_EPOCHS = 20     # hard cap (Golden Rule 4: laptop-scoped, <5 min).
BATCH_SIZE = 32
LR = 1e-3
TRAIN_FRAC = 0.8    # chronological: first 80% of days train, last 20% validate.


def set_seeds(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_series() -> pd.DataFrame:
    if not MU_TEVI_PATH.exists():
        print(f"FATAL: {MU_TEVI_PATH} missing. Run `python -m models.fusion.tevi` first.")
        sys.exit(1)
    return pd.read_parquet(MU_TEVI_PATH).sort_values("ts").reset_index(drop=True)


def window_starts(n_steps: int, t_in: int, horizon: int) -> np.ndarray:
    return np.arange(0, n_steps - t_in - horizon + 1)


def build_xy(values: np.ndarray, starts: np.ndarray, t_in: int,
             horizon: int) -> tuple[np.ndarray, np.ndarray]:
    """-> X (S, t_in, 1), Y (S, horizon), on a plain 1-D series."""
    x_idx = starts[:, None] + np.arange(t_in)[None, :]
    y_idx = starts[:, None] + t_in + np.arange(horizon)[None, :]
    x = values[x_idx][..., None].astype(np.float32)
    y = values[y_idx].astype(np.float32)
    return x, y


def persistence_baseline(values: np.ndarray, starts: np.ndarray, t_in: int,
                         horizon: int) -> np.ndarray:
    """predicted(t+h) = value at the last input day (today), for every h.

    The genuinely naive "tomorrow = today" forecast: today's value carried
    forward unchanged across the whole horizon.
    """
    today_idx = starts + t_in - 1
    today = values[today_idx]
    return np.tile(today[:, None], (1, horizon))


@torch.no_grad()
def predict(model: GRUForecaster, x: torch.Tensor, batch_size: int = 256) -> torch.Tensor:
    model.eval()
    return torch.cat([model(x[i:i + batch_size]) for i in range(0, len(x), batch_size)])


def main() -> int:
    started = time.time()
    set_seeds(SEED)
    torch.set_num_threads(1)  # deterministic CPU reduction order
    print("=" * 72)
    print("GRU mu-TEVI FORECASTER -- 3-7 day-ahead city index")
    print("=" * 72)
    print(f"[SEED]     seed={SEED} (random, numpy, torch) | device=cpu")

    df = load_series()
    values = df["mu_tevi"].to_numpy(dtype=np.float64)
    n_steps = len(values)
    print(f"[DATA]     {n_steps} real days from {MU_TEVI_PATH}")

    split_t = int(TRAIN_FRAC * n_steps)
    starts = window_starts(n_steps, T_IN, HORIZON)
    # Strict: a training window's TARGET must end before the val period, and a
    # val window's INPUT must start at/after it (straddling windows dropped).
    train_starts = starts[starts + T_IN + HORIZON <= split_t]
    val_starts = starts[starts >= split_t]
    print(f"[SPLIT]    CHRONOLOGICAL (never shuffled across time): train windows="
          f"{len(train_starts)} (<= day {split_t}), val windows={len(val_starts)} "
          f"(>= day {split_t}), {len(starts) - len(train_starts) - len(val_starts)} straddling dropped")

    # Normalize using the TRAIN portion only -- no leakage from validation years.
    mu, sigma = float(values[:split_t].mean()), float(values[:split_t].std())
    if sigma <= 0.0:
        print("FATAL: zero variance in the training block. Aborting.")
        return 1
    norm = (values - mu) / sigma
    print(f"[NORM]     train-time-only z-score: mu={mu:.4f} sigma={sigma:.4f}")

    x_tr, y_tr = build_xy(norm, train_starts, T_IN, HORIZON)
    x_va, y_va = build_xy(norm, val_starts, T_IN, HORIZON)
    x_tr_t, y_tr_t = torch.from_numpy(x_tr), torch.from_numpy(y_tr)
    x_va_t, y_va_t = torch.from_numpy(x_va), torch.from_numpy(y_va)

    loader = DataLoader(
        TensorDataset(x_tr_t, y_tr_t), batch_size=BATCH_SIZE, shuffle=True,
        generator=torch.Generator().manual_seed(SEED),
    )

    model = GRUForecaster(input_size=1, hidden=HIDDEN, horizon=HORIZON)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[MODEL]    GRU hidden={HIDDEN} t_in={T_IN} horizon={HORIZON} | "
          f"params={n_params} (budget {PARAM_BUDGET})")
    if n_params >= PARAM_BUDGET:
        print(f"FATAL: forecaster has {n_params} params, exceeds the {PARAM_BUDGET} budget.")
        return 1

    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    criterion = nn.MSELoss()

    history: list[dict] = []
    best_val = float("inf")
    best_state = None
    for epoch in range(1, MAX_EPOCHS + 1):
        model.train()
        total, seen = 0.0, 0
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            total += loss.item() * len(xb)
            seen += len(xb)
        train_loss = total / max(seen, 1)

        val_mae = float((predict(model, x_va_t) - y_va_t).abs().mean().item()) * sigma
        history.append({"epoch": epoch, "train_mse": train_loss, "val_mae": val_mae})
        print(f"  epoch {epoch:2d}/{MAX_EPOCHS}  train_mse={train_loss:.5f}  "
              f"val_mae={val_mae:.4f}{'  *' if val_mae < best_val - 1e-6 else ''}")

        if val_mae < best_val - 1e-6:
            best_val = val_mae
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    print(f"[BEST]     val_mae={best_val:.4f} (weights restored)")

    # --- Persistence baseline, on the SAME validation windows ----------------
    persistence_pred_norm = persistence_baseline(norm, val_starts, T_IN, HORIZON)
    persistence_mae = float(np.abs(persistence_pred_norm - y_va).mean()) * sigma

    model_mae = best_val
    beats_persistence = model_mae < persistence_mae
    improvement_pct = ((persistence_mae - model_mae) / persistence_mae * 100.0
                       if persistence_mae else float("nan"))

    print("=" * 72)
    print("VALIDATION (chronological hold-out, later years)")
    print(f"  GRU forecaster MAE   : {model_mae:.4f} (mu-TEVI index points)")
    print(f"  Persistence baseline : {persistence_mae:.4f} (tomorrow = today)")
    print(f"  -> {'GRU BEATS' if beats_persistence else 'GRU DOES NOT BEAT'} persistence "
          f"({improvement_pct:+.2f}%) -- reported honestly, not retuned to force a win.")
    print("=" * 72)

    # Per-horizon breakdown (diagnostic, never the acceptance gate).
    pred_va_norm = predict(model, x_va_t).numpy()
    per_horizon = []
    for h in range(HORIZON):
        m_mae = float(np.abs(pred_va_norm[:, h] - y_va[:, h]).mean()) * sigma
        p_mae = float(np.abs(persistence_pred_norm[:, h] - y_va[:, h]).mean()) * sigma
        per_horizon.append({"days_ahead": h + 1, "model_mae": m_mae, "persistence_mae": p_mae})
        print(f"  [h={h + 1}d] model={m_mae:.4f}  persistence={p_mae:.4f}")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": model.state_dict(),
        "config": {"input_size": 1, "hidden": HIDDEN, "t_in": T_IN, "horizon": HORIZON, "seed": SEED},
        "norm": {"mu": mu, "sigma": sigma, "scope": "train_time_only"},
        "last_window": values[-T_IN:].tolist(),
        "last_date": str(df["ts"].iloc[-1].date()),
        "metrics": {
            "model_mae": model_mae, "persistence_mae": persistence_mae,
            "beats_persistence": bool(beats_persistence), "improvement_pct": improvement_pct,
            "per_horizon": per_horizon, "n_params": n_params, "best_epoch_val_mae": best_val,
        },
        "history": history,
    }, MODEL_PATH)
    print(f"[ARTIFACT] {MODEL_PATH}")
    print(f"[TIME]     {time.time() - started:.1f}s total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
