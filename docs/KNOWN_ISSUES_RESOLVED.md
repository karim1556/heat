# Known Issues Found & Resolved

A running record of substantive bugs caught and corrected **before** publication.
Kept here (not in the auto-generated `STATEWISE_RESULTS.md`, which is overwritten
on every regeneration) so the integrity history is permanent and findable.

---

## 2026-07-23 — Strike-desync + grid-censoring in contract pricing (33 states)

**Bug.** `select_contract` stored the chosen strike with `int()`, truncating it
(e.g. 99.7 → 99) and desyncing the *reported* strike from the *chosen row's*
economics. Compounding it, `STRIKE_GRID` stopped at integer strike 99, so
heat-concentrated states — whose mu-TEVI exceedance mass sits above 99 — had
their true optimum censored at the grid edge and were priced on the wrong
contract.

**Blast radius.** 33 of 78 designed states sat at the old ceiling (not 2, as first
believed from the CA/CO symptoms). Fixed as one root cause: strike stored as
`float`; grid extended with fractional strikes to 99.99; and `sweep()` now
self-prunes grid points that never trigger for a state (strike above its own
mu-TEVI max) instead of crashing on an all-zero sample.

**Before → after (the three that mattered).** All three negative-MAE results were
pure censoring artifacts and flipped positive; none survived as genuine negatives:

| State | Before | After | Corrected strike |
|---|---|---|---|
| Washington | −117.5% | +3.0% | 99.9 |
| Oregon | −21.8% | +2.6% | 99.9 |
| Colorado | −6.1% | +8.9% | 99.7 |

The remaining 30 flagged states were already positive; ~7 improved at their true
interior optimum and ~23 were genuinely optimal at strike 99 all along (the flag
was conservative). After the fix: **0 of 78 chosen strikes land on the grid
ceiling** — every state is priced on a proven-interior optimum. Contracts are
selected on product quality (lowest shortfall), never on the MAE headline, so a
few states' MAE ticked down slightly when their strike moved to the genuinely
better-covering point — reported, not hidden.

Fix + all 33 corrected states: commit tag `v2.1-desync-bug-fixed-33states`.
Unrelated genuine negatives (interior, not censored) — IN-Tamil Nadu, Telangana,
Andhra Pradesh, Goa — were left untouched as legitimate findings.
