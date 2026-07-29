"""Feature engineering + a thin wrapper around sklearn's IsolationForest for
flagging anomalous heat-payout claims (Prompt 8).

Features per claim: heat_index (the mu-TEVI value on the claimed day),
occupation (one-hot, FIXED category order so the encoding is stable
regardless of which occupations appear in a given batch -- required for the
single-row inference the API's /flag-anomaly does), claimed_payout (INR), and
days_since_last_claim (NaN for a worker's first-ever claim -- imputed with the
TRAINING set's median, not zero or a large sentinel, so a first claim is not
spuriously treated as extreme in either direction).
"""

from __future__ import annotations  # needed for the `-> ClaimAnomalyDetector` self-reference below

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

OCCUPATIONS = ("vendor", "construction", "delivery")
SEED = 42
CONTAMINATION = 0.01  # flag the top 1% most anomalous, per the prompt.


class ClaimAnomalyDetector:
    def __init__(self, contamination: float = CONTAMINATION, seed: int = SEED):
        self.contamination = contamination
        self.seed = seed
        self.model_: IsolationForest | None = None
        self.days_since_median_: float | None = None

    def _features(self, df: pd.DataFrame, fit_impute: bool = False) -> np.ndarray:
        occ = pd.Categorical(df["occupation"], categories=OCCUPATIONS)
        occ_onehot = pd.get_dummies(occ).to_numpy(dtype=np.float64)

        days = df["days_since_last_claim"].to_numpy(dtype=np.float64)
        if fit_impute:
            finite = days[~np.isnan(days)]
            self.days_since_median_ = float(np.median(finite)) if len(finite) else 0.0
        days_filled = np.where(np.isnan(days), self.days_since_median_, days)

        numeric = df[["heat_index", "claimed_payout"]].to_numpy(dtype=np.float64)
        return np.column_stack([numeric, days_filled[:, None], occ_onehot])

    def fit(self, df: pd.DataFrame) -> ClaimAnomalyDetector:
        x = self._features(df, fit_impute=True)
        self.model_ = IsolationForest(
            n_estimators=100, contamination=self.contamination, random_state=self.seed,
        )
        self.model_.fit(x)
        return self

    def score(self, df: pd.DataFrame) -> np.ndarray:
        """sklearn convention: higher = more normal. Use predict() for flags."""
        if self.model_ is None:
            raise RuntimeError("call fit() before score()")
        return self.model_.decision_function(self._features(df, fit_impute=False))

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """True = anomalous (flagged, top contamination-fraction), False = normal."""
        if self.model_ is None:
            raise RuntimeError("call fit() before predict()")
        return self.model_.predict(self._features(df, fit_impute=False)) == -1
