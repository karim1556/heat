"""Longstaff-Schwartz Monte-Carlo pricer for the parametric heat policy.

THE CONTRACT (stated precisely, because the premium formula IS the product):
a worker holds a one-shot, lump-sum heat-stress policy over an N-day coverage
window. On any day they may CLAIM ONCE; if they claim on day t they receive a
parametric payout that is a function of that day's mu-TEVI INDEX (not of their
assessed loss -- that is what makes it parametric):

    payout_frac(index) = CAP * (index - strike)_+ / (100 - strike),   CAP = 0.9

expressed as a fraction of the daily wage, so it lives on the SAME scale as the
worker's actual wage-loss fraction and basis risk is a like-for-like comparison.
The premium in absolute currency is wage * payout_frac.

WHY LONGSTAFF-SCHWARTZ AT ALL: the one-shot claim is an optimal-stopping problem
-- a Bermudan option. The worker should claim on the worst day, but cannot see
the future, so the fair premium is the value of the OPTIMAL EXERCISE POLICY, not
of claiming on a fixed day. LSMC estimates that policy by regressing the
continuation value on basis functions of the state, using simulated paths.
Without a stopping decision there would be nothing to regress and LSMC would be
decoration; here it is load-bearing.

TWO CARRIED CONSTRAINTS FROM PROMPT 4, both required:
  * HURDLE SAMPLING. Each simulated day's loss is drawn via the hurdle recipe
    (exact 0 w.p. p0, else Beta), NEVER a single continuous law -- see
    models/fusion/tevi.py. simulate_paths asserts the realized zero-fraction
    matches p0, so a regression to the smeared marginal cannot pass silently.
  * BASIS RISK. The payout keys off the mu-TEVI index; the worker's loss is a
    separate draw coupled only through the fitted Gumbel copula. That gap is the
    basis risk price_window reports (models/pricing/basis_risk.py).

MODELING SIMPLIFICATION, stated honestly (with the direction verified, not
guessed): the fitted copula is CROSS-SECTIONAL (heat vs loss on a given day), and
copula.json carries no temporal model, so simulated days are drawn i.i.d. in
time. Real heat is strongly persistent (mu-TEVI lag-1 autocorrelation ~0.99).
For a one-shot optimal-stopping payoff, independence gives MORE effectively-
independent chances to catch an extreme than positively-correlated days with the
SAME marginal, so i.i.d. OVER-states the premium. Measured on a same-marginal
time-reordering test: the premium falls ~7% going from i.i.d. to autocorr ~0.8.
So this is an UPPER bound relative to a persistence-aware price -- the
conservative direction for an insurer (it errs toward charging more), but a real
effect to flag. The premium is also CLIMATOLOGICAL (drawn from the unconditional
fitted law), not conditioned on the season of the passed window. Both are
limitations of the upstream fit, not of the pricer.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import yaml
from sklearn.linear_model import RidgeCV

from backend.config import load_contract_config
from backend.data.build_wage_loss import CITIES_YAML_PATH
from backend.data.elasticity import MAX_LOSS_FRACTION
from backend.data.wages import WageLoader
from models.fusion.gumbel_copula import GumbelSurvivalCopula
from models.fusion.marginals import HurdleMarginal
from models.pricing.basis_functions import LaguerreBasis
from models.pricing.basis_risk import basis_risk_simulated
from models.pricing.wang_transform import wang_premium

SEED = 42

# Per-state namespacing (v2): STATE_KEY set -> this state's copula + mu-TEVI and
# its OWN chosen contract (models/artifacts/<state>/contract.json, written by
# backend/backtest/contract_design.py's per-state sweep). Until that sweep has
# run for the state, the contract falls back to the shared cities.yaml one, so
# the sweep itself (which passes strike/window explicitly) is never blocked.
# STATE_KEY unset -> legacy single-city behaviour, unchanged.
_STATE_KEY = os.environ.get("STATE_KEY")
if _STATE_KEY:
    from backend.state_context import get_context

    _CTX = get_context(_STATE_KEY)
    COPULA_PATH = _CTX.artifact("copula.json")
    MU_TEVI_PATH = _CTX.processed("mu_tevi.parquet")
    _contract_path = _CTX.artifact("contract.json")
    _CONTRACT = json.loads(_contract_path.read_text()) if _contract_path.exists() \
        else load_contract_config()
else:
    _CTX = None
    COPULA_PATH = Path("models/artifacts/copula.json")
    MU_TEVI_PATH = Path("data/processed/mu_tevi.parquet")
    # Contract defaults -- sourced from backend/data/cities.yaml's `contract:`
    # section (the CHOSEN strike/window, Prompt 6b), NOT hardcoded here, so the
    # backtest and the API can never silently drift apart. See backend/config.py.
    _CONTRACT = load_contract_config()

DEFAULT_STRIKE = float(_CONTRACT["strike"])     # mu-TEVI trigger (index in [0,100]).
PAYOUT_CAP = MAX_LOSS_FRACTION   # 0.9; caps payout at the same ceiling as modeled loss.
DEFAULT_HORIZON = int(_CONTRACT["window_days"])  # days, if no window is supplied.

# Monte-Carlo / numerics.
DEFAULT_M = 2000
ANNUAL_RATE = 0.05
DAY_FRACTION = 1.0 / 365.0
RIDGE_ALPHAS = (0.1, 1.0, 10.0)  # DoD: Ridge(alpha=1.0) tuned by CV -> RidgeCV incl. 1.0.
ZERO_FRACTION_TOL = 0.03         # simulated loss zero-fraction must be within this of p0.


def payout_fraction(index: np.ndarray, strike: float = DEFAULT_STRIKE,
                    cap: float = PAYOUT_CAP) -> np.ndarray:
    """Parametric payout as a wage fraction: cap * (index - strike)_+ / (100 - strike)."""
    index = np.asarray(index, dtype=float)
    return cap * np.clip((index - strike) / (100.0 - strike), 0.0, 1.0)


class LSMCPricer:
    """Prices the parametric heat policy from the fitted joint distribution."""

    def __init__(self, theta: float, gev_params: tuple, hurdle: HurdleMarginal,
                 strike: float = DEFAULT_STRIKE, cap: float = PAYOUT_CAP,
                 annual_rate: float = ANNUAL_RATE, degree: int = 3):
        self.copula = GumbelSurvivalCopula(theta)
        self.gev_params = tuple(gev_params)
        self.hurdle = hurdle
        self.strike = float(strike)
        self.cap = float(cap)
        self.daily_discount = float(np.exp(-annual_rate * DAY_FRACTION))
        self.basis = LaguerreBasis(degree=degree)

    @classmethod
    def from_copula_json(cls, path: Path = COPULA_PATH, **kwargs) -> LSMCPricer:
        if not Path(path).exists():
            raise FileNotFoundError(
                f"{path} missing. Run `python -m models.fusion.tevi` first.")
        d = json.loads(Path(path).read_text())
        gev = d["gev_params"]
        return cls(theta=d["theta"],
                   gev_params=(gev["c"], gev["loc"], gev["scale"]),
                   hurdle=HurdleMarginal.from_dict(d["hurdle"]), **kwargs)

    # -- simulation --------------------------------------------------------

    def simulate_paths(self, n_days: int, n_paths: int,
                       rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
        """-> (mutevi_paths, loss_paths), each (n_paths, n_days).

        Follows the Prompt-4 hurdle recipe exactly: draw (u, v) from the Gumbel
        copula, map u through the GEV and v through the HURDLE marginal, and
        compute the published index from (u, v). Days are i.i.d. (see module
        docstring). Asserts the realized zero-fraction of the loss matches p0 --
        the guard that the atom survived sampling rather than being smeared.
        """
        if n_days < 1 or n_paths < 1:
            raise ValueError("n_days and n_paths must be >= 1")
        size = n_paths * n_days
        u, v = self.copula.sample(size, rng)

        # mu-TEVI = 100 * (1 - P(U>u, V>v)) = 100 * (u + v - C(u,v)).
        mutevi = 100.0 * (u + v - self.copula.cdf(u, v))
        # Loss via the hurdle: EXACTLY 0 when v <= p0, else Beta((v-p0)/(1-p0)).
        loss = self.hurdle.ppf(v)

        zero_fraction = float(np.mean(loss == 0.0))
        if abs(zero_fraction - self.hurdle.p0) > ZERO_FRACTION_TOL:
            raise AssertionError(
                f"simulated loss zero-fraction {zero_fraction:.4f} deviates from p0="
                f"{self.hurdle.p0:.4f} by more than {ZERO_FRACTION_TOL}: the hurdle atom "
                f"did NOT survive sampling. Refusing to price against a smeared marginal.")

        return (mutevi.reshape(n_paths, n_days), loss.reshape(n_paths, n_days))

    # -- LSMC core ---------------------------------------------------------

    def price_paths(self, mutevi_paths: np.ndarray, loss_paths: np.ndarray,
                    wage: float = 1.0, market_price_of_risk: float = 0.0) -> dict:
        """Price given simulated paths. `wage` scales the wage-fraction premium
        into currency. Kept separate from simulation so tests can feed
        constructed path sets (e.g. one stochastically dominating in heat).

        Returns per-path discounted payoffs plus premiums, so callers can apply
        the Wang distortion or aggregate however they need.
        """
        mutevi_paths = np.asarray(mutevi_paths, dtype=float)
        loss_paths = np.asarray(loss_paths, dtype=float)
        if mutevi_paths.shape != loss_paths.shape:
            raise ValueError("mutevi_paths and loss_paths must have the same shape")
        n_paths, n_days = mutevi_paths.shape

        payoff = payout_fraction(mutevi_paths, self.strike, self.cap)  # (M, N) wage fractions

        # Backward induction (Longstaff-Schwartz). `cashflow[i]` holds, for path
        # i, the value -- discounted to the current time t -- of the best
        # exercise decision found so far at times > t. Exercising earlier simply
        # overwrites it with the (smaller-t, less-discounted) immediate payoff, so
        # no separate exercise-time bookkeeping is needed. Start at maturity:
        # exercise iff in the money.
        cashflow = payoff[:, -1].copy()

        for t in range(n_days - 2, -1, -1):
            # Discount the currently-held future cashflow back one day, to time t.
            cashflow *= self.daily_discount

            immediate = payoff[:, t]
            itm = immediate > 0.0  # regress on IN-THE-MONEY paths only (LS 2001).
            if itm.sum() >= self.basis.n_features + 1:
                design = self.basis.transform(mutevi_paths[itm, t])
                # RidgeCV: alpha tuned by leave-one-out CV over a grid incl. 1.0.
                # fit_intercept=False because L_0 is already a constant column.
                model = RidgeCV(alphas=RIDGE_ALPHAS, fit_intercept=False)
                model.fit(design, cashflow[itm])
                continuation = model.predict(design)
                exercise_now = immediate[itm] >= continuation
            else:
                # Too few ITM paths to regress: exercise any ITM path (its
                # continuation estimate would be pure noise).
                exercise_now = np.ones(int(itm.sum()), dtype=bool)

            take = np.where(itm)[0][exercise_now]
            cashflow[take] = immediate[take]

        # cashflow is now the discounted value AT t=0 of the optimal policy.
        premium_lsmc = float(cashflow.mean())
        premium_wang = wang_premium(cashflow, market_price_of_risk) \
            if market_price_of_risk != 0.0 else premium_lsmc

        return {
            "premium_lsmc_fraction": premium_lsmc,
            "premium_wang_fraction": premium_wang,
            "premium_lsmc": premium_lsmc * wage,
            "premium_wang": premium_wang * wage,
            "discounted_payoffs": cashflow,
            "payoff_matrix": payoff,
        }

    # -- public entry point ------------------------------------------------

    def price_window(self, mu_tevi_window: np.ndarray, occupation: str,
                     n_paths: int = DEFAULT_M, market_price_of_risk: float = 0.30,
                     seed: int = SEED, wage: float | None = None) -> dict:
        """THE single pricing entry point (Prompt 6 backtest and Prompt 7 API).

        The window sets the coverage horizon N = len(window). Simulates n_paths
        forward paths of length N from the fitted joint law, runs LSMC, applies
        the Wang load, and reports this policy's SIMULATION-BASED basis risk (A)
        over its own MC paths. price_window never sees the own-node pairing, so
        the degeneracy guard does not fire here -- but basis_risk_simulated still
        runs it as defence in depth.
        """
        window = np.asarray(mu_tevi_window, dtype=float).reshape(-1)
        n_days = max(1, len(window))
        if wage is None:
            wage = self._occupation_wage(occupation)

        rng = np.random.default_rng(seed)
        mutevi_paths, loss_paths = self.simulate_paths(n_days, n_paths, rng)
        priced = self.price_paths(mutevi_paths, loss_paths, wage=wage,
                                  market_price_of_risk=market_price_of_risk)

        # (A) Simulation-based basis risk: payout schedule vs actual loss over
        # every (path, day). Payout keys off the index, loss is the coupled draw.
        payout_grid = priced["payoff_matrix"]
        basis = basis_risk_simulated(payout_grid, loss_paths)

        payout_schedule = {
            "form": "cap * (mu_tevi - strike)_+ / (100 - strike)",
            "strike": self.strike,
            "cap": self.cap,
            "trigger_frequency": float(np.mean(mutevi_paths >= self.strike)),
            "sample_points": {
                str(idx): float(payout_fraction(idx, self.strike, self.cap))
                for idx in (self.strike, 85.0, 95.0, 100.0)
            },
        }

        return {
            "premium_lsmc": priced["premium_lsmc"],
            "premium_wang": priced["premium_wang"],
            "premium_lsmc_fraction": priced["premium_lsmc_fraction"],
            "premium_wang_fraction": priced["premium_wang_fraction"],
            "payout_schedule": payout_schedule,
            "basis_risk": basis,
            "occupation": occupation,
            "wage": wage,
            "horizon_days": n_days,
            "n_paths": n_paths,
            "market_price_of_risk": market_price_of_risk,
        }

    @staticmethod
    def _occupation_wage(occupation: str) -> float:
        # Per-state (v2): when STATE_KEY is set the wage MUST come from THIS
        # state's own legislated schedule, in its own currency (INR for IN, USD
        # for US) -- never cities.yaml's default_city. Reading default_city here
        # was a real bug: every state silently priced in Ahmedabad's INR wage
        # regardless of which state was detected. STATE_KEY unset -> legacy
        # single-city path, unchanged.
        if _CTX is not None:
            wages = _CTX.daily_wages()
        else:
            with open(CITIES_YAML_PATH) as f:
                config = yaml.safe_load(f)
            key = config["default_city"]
            wages = WageLoader(
                country_iso3=config["cities"][key]["country_iso3"]
            ).occupation_baseline_wages(city_key=key)
        if occupation not in wages:
            raise ValueError(f"unknown occupation {occupation!r}; have {sorted(wages)}")
        return float(wages[occupation])


def persistence_premium_gap(pricer: LSMCPricer, window: np.ndarray, n_paths: int,
                            rng: np.random.Generator) -> float:
    """The same-marginal time-reordering test referenced in this module's
    docstring, formalized as reusable code (it previously existed only as an
    ad-hoc investigation script, not shipped code -- this is that method,
    extracted verbatim in spirit so Prompt 6's real-data number is directly
    comparable to the ~7% measured here on simulated data).

    Holds the MARGINAL exactly fixed -- both variants use precisely the same N
    values, `window`'s own -- and varies only the TIME ORDER:

      (a) i.i.d.-shuffled: each of the n_paths simulated paths gets an
          INDEPENDENT random permutation of `window`'s values (destroys
          autocorrelation, keeps the marginal).
      (b) real ordered: every path replays `window` in its EXACT real order
          (autocorrelation intact). All paths are then identical, so this
          collapses the LSMC regression to the single-path optimal-stopping
          value of that one real trajectory -- which is exactly the quantity
          wanted for comparison.

    Returns (premium_a - premium_b) / premium_b * 100, a percentage. The payoff
    is a pure function of the mu-TEVI index (see price_paths), so loss_paths is
    passed as zeros here -- irrelevant to the premium, never read for it.
    """
    n_days = len(window)
    if n_days < 2:
        raise ValueError("need >= 2 days to compare orderings")
    dummy_loss = np.zeros((n_paths, n_days))

    shuffled = np.array([rng.permutation(window) for _ in range(n_paths)])
    premium_a = pricer.price_paths(shuffled, dummy_loss)["premium_lsmc_fraction"]

    ordered = np.tile(window, (n_paths, 1))
    premium_b = pricer.price_paths(ordered, dummy_loss)["premium_lsmc_fraction"]

    if premium_b == 0.0:
        return float("nan")
    return (premium_a - premium_b) / premium_b * 100.0


def main() -> int:
    rng_window = np.random.default_rng(SEED)
    print("=" * 74)
    print("LSMC PARAMETRIC HEAT PRICER -- premium, Wang load, and basis risk")
    print("=" * 74)

    pricer = LSMCPricer.from_copula_json()
    print(f"[MODEL]    theta={pricer.copula.theta:.4f} "
          f"(lambda_U={pricer.copula.upper_tail_dependence():.4f}, copula tail dependence)")
    print(f"[CONTRACT] one-shot Bermudan claim | strike={pricer.strike:g} mu-TEVI | "
          f"payout=cap*(index-strike)+/(100-strike), cap={pricer.cap:.2f} wage")
    print(f"[HURDLE]   F_L p0={pricer.hurdle.p0:.4f} ({pricer.hurdle.positive_dist}); "
          f"simulated zero-fraction is asserted within {ZERO_FRACTION_TOL} of p0")

    # Price a representative 30-day window off the real mu-TEVI series if present.
    if MU_TEVI_PATH.exists():
        import pandas as pd
        series = pd.read_parquet(MU_TEVI_PATH)["mu_tevi"].to_numpy()
        window = series[:DEFAULT_HORIZON]
        window_src = f"first {DEFAULT_HORIZON} days of {MU_TEVI_PATH}"
    else:
        window = 50.0 + 10.0 * rng_window.standard_normal(DEFAULT_HORIZON)
        window_src = f"synthetic {DEFAULT_HORIZON}-day placeholder (mu_tevi.parquet absent)"

    print(f"[WINDOW]   {window_src}: N={len(window)} days")
    print()

    lam_w = 0.30  # Wang market price of risk (NOT lambda_U; see wang_transform.py).
    ccy = _CTX.currency if _CTX is not None else "INR"  # this state's own currency, never assumed
    for occupation in ("vendor", "construction", "delivery"):
        result = pricer.price_window(window, occupation, market_price_of_risk=lam_w)
        br = result["basis_risk"]
        print(f"[{occupation.upper()}]  wage={result['wage']:.1f} {ccy}/day | "
              f"trigger freq={result['payout_schedule']['trigger_frequency']:.3f}")
        print(f"           premium LSMC = {result['premium_lsmc']:8.3f} {ccy} "
              f"({result['premium_lsmc_fraction']:.4f} wage-frac)")
        print(f"           premium Wang = {result['premium_wang']:8.3f} {ccy} "
              f"({result['premium_wang_fraction']:.4f} wage-frac)  "
              f"[lambda_w={lam_w}, load {result['premium_wang'] / result['premium_lsmc'] - 1:+.1%}]")
        print(f"           basis risk : rmse={br['basis_risk_rmse']:.4f}  "
              f"shortfall={br['shortfall_rate']:.3f}  overpay={br['overpay_rate']:.3f}  "
              f"corr={br['correlation']:.3f}")

    print("=" * 74)
    print("NOTE: premium is climatological (unconditional fitted law) and assumes days")
    print("i.i.d. in time. Real heat is persistent (autocorr ~0.99); for this")
    print("optimal-stopping payoff i.i.d. OVER-states the premium (~7% on a same-marginal")
    print("test) -> an UPPER bound, conservative for an insurer. See module docstring.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
