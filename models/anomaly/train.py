"""Train the Isolation Forest claim-anomaly detector (Prompt 8) on REAL claim
feature vectors from the historical replay (data/processed/claims.parquet).

Flags the top 1% most anomalous claims (contamination=0.01, see
models/anomaly/detector.py). Saved to models/artifacts/anomaly.pkl.
"""

from __future__ import annotations

import os
import pickle
import sys
import time
from pathlib import Path

import pandas as pd

from models.anomaly.detector import ClaimAnomalyDetector

# Per-state namespacing (v2): STATE_KEY set -> this state's claims + anomaly
# model. Unset -> legacy single-city paths, unchanged.
STATE_KEY = os.environ.get("STATE_KEY")
if STATE_KEY:
    from backend.state_context import get_context

    _CTX = get_context(STATE_KEY)
    CLAIMS_PATH = _CTX.processed("claims.parquet")
    MODEL_PATH = _CTX.artifact("anomaly.pkl")
else:
    _CTX = None
    CLAIMS_PATH = Path("data/processed/claims.parquet")
    MODEL_PATH = Path("models/artifacts/anomaly.pkl")


def load_claims() -> pd.DataFrame:
    if not CLAIMS_PATH.exists():
        print(f"FATAL: {CLAIMS_PATH} missing. Run `python -m backend.backtest.report` first "
              f"(claims.parquet is written by the historical replay).")
        sys.exit(1)
    return pd.read_parquet(CLAIMS_PATH)


def main() -> int:
    started = time.time()
    print("=" * 72)
    print("ISOLATION FOREST -- claim anomaly detector")
    print("=" * 72)

    claims = load_claims()
    print(f"[DATA]     {len(claims)} real claim rows from {CLAIMS_PATH}")

    detector = ClaimAnomalyDetector()
    detector.fit(claims)
    flags = detector.predict(claims)
    n_flagged = int(flags.sum())
    print(f"[FIT]      contamination={detector.contamination} seed={detector.seed} "
          f"n_estimators=100")
    print(f"[FLAGGED]  {n_flagged}/{len(claims)} claims ({n_flagged / len(claims) * 100:.2f}%) "
          f"flagged as the top-anomaly tier")

    top = (
        claims.loc[flags, ["node_id", "occupation", "ts", "heat_index", "claimed_payout",
                           "days_since_last_claim"]]
        .sort_values("claimed_payout", ascending=False)
        .head(5)
    )
    print("[TOP-5 FLAGGED BY PAYOUT]")
    for _, row in top.iterrows():
        print(f"  {row['ts'].date()} {row['node_id']} {row['occupation']:12s} "
              f"payout={row['claimed_payout']:.1f} heat_index={row['heat_index']:.1f} "
              f"days_since_last={row['days_since_last_claim']}")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(detector, f)
    print(f"[ARTIFACT] {MODEL_PATH}")
    print(f"[TIME]     {time.time() - started:.1f}s total")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
