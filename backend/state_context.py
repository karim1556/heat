"""Per-state context: the single source of truth for a state's namespaced
artifact/data paths, its anchor-metro heat grid, and its state-level wage
schedule + currency.

WHY THIS EXISTS: the v1 pipeline hardcoded one city's paths
(models/artifacts/stgcn.pt, data/processed/weather.parquet, ...) and read
config["default_city"]. v2 trains ONE fully-real pipeline per state, so every
stage must namespace its I/O by state_key and source that state's own anchor
weather + own legislated wage. Centralizing that here keeps the 8 training
stages, the resumable batch runner, and the currency-aware API from each
re-deriving (and drifting on) the layout.

CURRENCY IS NEVER CONVERTED: INR for IN states, USD for US states, carried as a
label through every path. No FX anywhere (see wages_by_state.yaml).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "config"
WAGES_PATH = CONFIG_DIR / "wages_by_state.yaml"
ANCHORS_PATH = CONFIG_DIR / "state_anchors.yaml"

ARTIFACTS_ROOT = REPO_ROOT / "models" / "artifacts"
PROCESSED_ROOT = REPO_ROOT / "data" / "processed"

# Artifacts that must all exist (and be non-empty) for a state to count as
# "already trained" -- the resumability check the batch runner keys off.
# ppo_policy.pt is REQUIRED: it is a leaf artifact (nothing downstream reads it,
# so its presence is not implied transitively by copula/anomaly), and a missing
# or smoke-run policy must NOT let a state count as "trained" and be skipped on
# resume. The others are terminal artifacts whose stages' predecessors are
# implied transitively (copula.json => tevi ran => calibration+evaluate_spatial
# ran; anomaly.pkl => report ran => contract designed).
REQUIRED_ARTIFACTS = ("stgcn.pt", "ppo_policy.pt", "copula.json", "forecaster.pt", "anomaly.pkl")
REQUIRED_PROCESSED = ("weather.parquet", "mu_tevi.parquet")


@lru_cache(maxsize=1)
def _wages() -> dict:
    return yaml.safe_load(WAGES_PATH.read_text())["states"]


@lru_cache(maxsize=1)
def _anchors() -> dict:
    return yaml.safe_load(ANCHORS_PATH.read_text())["anchors"]


def all_state_keys() -> list[str]:
    """Every priced state, sorted -- the set the batch runner iterates."""
    return sorted(_wages().keys())


def state_exists(state_key: str) -> bool:
    return state_key in _wages() and state_key in _anchors()


class StateContext:
    """Resolved I/O + config for one state. Cheap to build; holds no data."""

    def __init__(self, state_key: str):
        if state_key not in _wages():
            raise KeyError(f"{state_key!r} is not in wages_by_state.yaml")
        if state_key not in _anchors():
            raise KeyError(f"{state_key!r} is not in state_anchors.yaml")
        self.state_key = state_key
        self.wage = _wages()[state_key]
        self.anchor = _anchors()[state_key]

    # -- identity ----------------------------------------------------------
    @property
    def country(self) -> str:
        return self.wage["country"]

    @property
    def currency(self) -> str:
        return self.wage["currency"]  # "INR" | "USD" -- never converted

    @property
    def metro(self) -> str:
        return self.anchor["metro"]

    @property
    def bbox(self) -> dict:
        return self.anchor["bbox"]

    def daily_wages(self) -> dict[str, float]:
        """{occupation: daily_wage} in this state's own currency."""
        return dict(self.wage["wages_daily"])

    def wage_provenance(self) -> dict:
        """Everything the /methodology table + provenance affordance need."""
        return {
            "state": self.wage.get("state", self.state_key),
            "country": self.country,
            "currency": self.currency,
            "wages_daily": self.daily_wages(),
            "confidence": self.wage.get("confidence"),
            "source_url": self.wage.get("source_url"),
            "note": self.wage.get("note"),
            "verified": self.wage.get("verified", False),
        }

    # -- namespaced I/O ----------------------------------------------------
    @property
    def artifacts_dir(self) -> Path:
        return ARTIFACTS_ROOT / self.state_key

    @property
    def processed_dir(self) -> Path:
        return PROCESSED_ROOT / self.state_key

    def artifact(self, name: str) -> Path:
        return self.artifacts_dir / name

    def processed(self, name: str) -> Path:
        return self.processed_dir / name

    def ensure_dirs(self) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    # -- resumability ------------------------------------------------------
    def is_trained(self) -> bool:
        """True iff every required artifact/data file exists and is non-empty.

        This is what `make train-all-states` uses to SKIP an already-done
        state on a resumed run -- so an interrupted overnight batch continues
        instead of restarting, and never loses completed states.
        """
        for name in REQUIRED_ARTIFACTS:
            p = self.artifact(name)
            if not p.exists() or p.stat().st_size == 0:
                return False
        for name in REQUIRED_PROCESSED:
            p = self.processed(name)
            if not p.exists() or p.stat().st_size == 0:
                return False
        return True


def get_context(state_key: str) -> StateContext:
    return StateContext(state_key)
