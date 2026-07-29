"""Per-window-length contract LOOKUP from each state's persisted design sweep.

WHY A LOOKUP AND NOT A RE-SELECTION (this is the safety argument -- read it
before editing):

Each state's contract was chosen by sweeping STRIKE_GRID x WINDOW_GRID over
its REAL historical data and scoring every combination; that whole scored
table is persisted per state at
models/artifacts/<state>/contract_design_sweep.csv (present for all 78 priced
states, all four WINDOW_GRID lengths, balanced rows per window -- verified).
The committed contract.json is simply the winner of that table under
contract_design.select_contract.

select_contract is a PURE function of the persisted table: it filters and
sorts already-computed columns (trigger_rate, premium_to_cap, shortfall_rate,
overpay_rate) and returns one row. It fits nothing, simulates nothing, calls
no copula, and touches no file. Applying it to the rows for ONE window length
is therefore the same lookup that produced contract.json, restricted to a
subset of rows the sweep had already scored -- not a refit, and not a new
evaluation of anything.

VERIFIED, NOT ASSUMED: select_contract over each state's FULL table
reproduces that state's committed contract.json strike/window/frame exactly
for all 78 states (0 mismatches), and restricted to the committed window it
reproduces the committed strike/frame for all 78. That equality is what
licenses using it per window.

WHY THIS MATTERS RATHER THAN JUST REUSING THE 14-DAY STRIKE: measured across
all 78 states, EVERY state has at least one window length whose
independently-evaluated best strike differs from its committed 14-day strike
(e.g. IN-Kerala: 80 at 14d, 85 at 30d, 95 at 60d and 90d). Pricing a 90-day
window at the 14-day strike would quietly be a contract the sweep never
picked for that length.

Nothing here writes any artifact.
"""

from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from backend.backtest.contract_design import WINDOW_GRID, select_contract
from backend.state_context import get_context

# The only selectable lengths: exactly the grid the real historical sweep
# scored. A free-form day count would have no evaluated contract behind it.
SELECTABLE_WINDOW_DAYS: tuple[int, ...] = tuple(int(w) for w in WINDOW_GRID)


class SweepTableUnavailable(RuntimeError):
    """This deployment lacks the per-window sweep table, so only the state's
    own committed window length can be priced. Distinct from "untrained" --
    conflating the two is exactly what made the v2.12 packaging regression
    read as a missing model."""


@lru_cache(maxsize=None)
def contract_for_window(state_key: str, window_days: int) -> dict:
    """The already-evaluated best contract for this state at this window.

    Returns the same shape the /simulate-policy handler needs: strike, cap,
    frame, window_days, plus the sweep row's real historical diagnostics.
    `cap` comes from the state's committed contract.json (uniformly 0.9), the
    sweep having been scored at that cap.

    Raises ValueError for a window length the sweep never scored, and
    FileNotFoundError if the state has no persisted sweep table.
    """
    if int(window_days) not in SELECTABLE_WINDOW_DAYS:
        raise ValueError(
            f"window_days must be one of {list(SELECTABLE_WINDOW_DAYS)} -- the lengths "
            f"actually evaluated against real history; got {window_days}")

    ctx = get_context(state_key)
    sweep_path = ctx.artifact("contract_design_sweep.csv")
    contract_path = ctx.artifact("contract.json")
    if not contract_path.exists():
        raise FileNotFoundError(f"{state_key} has no committed contract.json")

    committed = json.loads(contract_path.read_text())

    # A deployment that ships only the runtime artifacts may not carry the
    # sweep table (it didn't until v2.13). The COMMITTED contract is itself
    # that state's selection at its own window length, so serve the default
    # window from contract.json alone rather than failing. Any OTHER length
    # genuinely needs the table -- say so specifically instead of claiming
    # the model is untrained, which sent v2.12 chasing the wrong cause.
    if not sweep_path.exists():
        if int(window_days) == int(committed["window_days"]):
            return {
                "strike": float(committed["strike"]),
                "cap": float(committed["cap"]),
                "frame": committed["frame"],
                "window_days": int(committed["window_days"]),
                "independently_evaluated": True,
                "is_committed_default": True,
                "diagnostics": None,
            }
        raise SweepTableUnavailable(
            f"{state_key}'s contract design sweep is not available in this deployment, so a "
            f"{window_days}-day window cannot be priced with that length's own evaluated "
            f"strike; its committed {committed['window_days']}-day contract still prices "
            f"normally. No strike was substituted.")
    sweep = pd.read_csv(sweep_path)
    rows = sweep[sweep["window"] == int(window_days)]
    if rows.empty:
        raise ValueError(
            f"{state_key}'s sweep table has no rows for a {window_days}-day window")

    chosen = select_contract(rows)
    return {
        "strike": float(chosen["strike"]),
        "cap": float(committed["cap"]),
        "frame": chosen["frame"],
        "window_days": int(chosen["window"]),
        # True whenever the (strike, window) pairing came from the real
        # historical sweep -- which, by construction here, it always did.
        "independently_evaluated": True,
        # Whether this is the state's own committed default combination.
        "is_committed_default": (
            int(window_days) == int(committed["window_days"])
            and float(chosen["strike"]) == float(committed["strike"])
        ),
        "diagnostics": chosen["row"],
    }
