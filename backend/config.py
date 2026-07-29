"""Single source of truth for the CHOSEN contract (strike + coverage window).

Prompt 6b selected strike=75, window=14 days on the real historical replay via
backend/backtest/contract_design.py's honesty-gated sweep (0/36 grid points
behaved like catastrophe insurance -- the peril is chronic/high-frequency, so
the product is framed as INCOME SMOOTHING, not catastrophe insurance -- see
backend/data/cities.yaml's `contract:` section for the full citation).

Both the backtest (models/pricing/lsmc_pricer.py's DEFAULT_STRIKE/
DEFAULT_HORIZON, which backend/backtest/historical_replay.py's WINDOW_DAYS
derives from) and the API (backend/main.py) must read the contract from HERE
-- never hardcode a strike/window independently in either place, or the two
can silently drift.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CITIES_YAML_PATH = Path(__file__).parent / "data" / "cities.yaml"


def load_contract_config(path: Path = CITIES_YAML_PATH) -> dict:
    """Returns {"strike": ..., "window_days": ..., "product_type": ...}."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    contract = cfg.get("contract")
    if not contract:
        raise KeyError(f"{path} has no top-level `contract:` section")
    return contract
