"""Optional swap seam: primary field-survey elasticity override.

If data/raw/survey_real.csv exists, its MEASURED per-occupation elasticity
overrides the cited literature constants in elasticity.py, and that
occupation's provenance flips to "primary field data". This is a manual
drop-in (never an automated fetch) -- see README for PLFS microdata, which is
real but gated behind microdata.gov.in registration.

Expected CSV columns: occupation, per_deg, wbgt_threshold_c
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DEFAULT_SURVEY_PATH = Path("data/raw/survey_real.csv")


class SurveyDataLoader:
    def __init__(self, survey_path: str | Path = DEFAULT_SURVEY_PATH):
        self.survey_path = Path(survey_path)

    def available(self) -> bool:
        return self.survey_path.exists()

    def load_overrides(self) -> dict[str, dict]:
        """Return {occupation: {per_deg, wbgt_threshold_c, source}} from the
        real survey CSV, or {} if no survey file is present.
        """
        if not self.available():
            return {}

        df = pd.read_csv(self.survey_path)
        overrides = {}
        for _, row in df.iterrows():
            overrides[row["occupation"]] = {
                "per_deg": float(row["per_deg"]),
                "wbgt_threshold_c": float(row["wbgt_threshold_c"]),
                "source": "primary field data",
            }
        return overrides
