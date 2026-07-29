"""Small POMDP: an informal outdoor worker choosing work/rest under heat.

Gymnasium-style API (reset/step, 5-tuple), duck-typed rather than subclassing
gymnasium.Env -- gymnasium is not a dependency of this project and the env is
small enough that the interface is the only thing PPO needs.

State      : (cash_buffer, heat_exposure, occupation)
Action     : 0 = rest, 1 = work
Reward     : R(s,a) = wage_o * a - kappa * exp(gamma * exposure) * a
Episode    : 30 steps (one month of daily work decisions)
Heat       : REAL NASA POWER shade-WBGT, sampled as a contiguous 30-day window
             at a real grid node (CLAUDE.md Golden Rule 5 -- never synthetic).

WHY THIS IS A POMDP, not an MDP: the reward is driven by the TRUE WBGT, but the
worker only perceives heat by feel, not with a WBGT meter. The observation
therefore carries `true_wbgt + N(0, perception_noise_c)` while the reward uses
the true value. That gap is the whole premise of parametric insurance: the
trigger is measured objectively, but behaviour responds to perceived heat.

NOTE ON cash_buffer: per the reward above -- which is the specified reward -- the
cash buffer does NOT enter R. It is carried as observable state (and evolves with
wages earned minus subsistence) for downstream use, but because R depends only on
(action, exposure) the induced optimal policy is MYOPIC: a per-step threshold on
heat. That is a property of the specified reward, not an oversight, and it is
exactly what makes the closed-form calibration in calibration.py legitimate
instead of requiring PPO to be retrained inside the optimizer.
"""

from __future__ import annotations

import numpy as np

# Cited daily wages come from cities.yaml (see backend/data/wages.py); the env
# takes them as arguments so no wage level is hardcoded here.
OCCUPATIONS = ("vendor", "construction", "delivery")

ACTION_REST = 0
ACTION_WORK = 1
N_ACTIONS = 2

EPISODE_LEN = 30

# A worker misjudges WBGT by roughly half a degree by feel. Small, but it is
# what makes the problem partially observed.
DEFAULT_PERCEPTION_NOISE_C = 0.5

# Default reward parameters, used ONLY until calibration.py fits them. They place
# the work/rest indifference point at 30 C WBGT with a moderate heat-cost curve:
#   kappa = wage * exp(-gamma * h_star)  =>  wage - kappa*exp(gamma*h_star) = 0.
DEFAULT_GAMMA = 0.1
DEFAULT_INDIFFERENCE_WBGT_C = 30.0


def default_kappa(wage: float, gamma: float = DEFAULT_GAMMA,
                  h_star: float = DEFAULT_INDIFFERENCE_WBGT_C) -> float:
    """kappa placing the work/rest indifference threshold at `h_star`."""
    return float(wage * np.exp(-gamma * h_star))


def heat_cost(exposure: float | np.ndarray, kappa: float, gamma: float):
    """kappa * exp(gamma * exposure) -- the disutility of working in heat."""
    return kappa * np.exp(gamma * np.asarray(exposure, dtype=float))


def reward(action: int, exposure: float, wage: float, kappa: float, gamma: float) -> float:
    """R(s,a) = wage*a - kappa*exp(gamma*exposure)*a. Resting always yields 0."""
    return float(action) * (wage - float(heat_cost(exposure, kappa, gamma)))


class WorkerEnv:
    """One worker, 30 daily work/rest decisions, real heat.

    Each episode samples an occupation and a real (node, 30-day window) so the
    single policy sees all three occupations and the full real heat distribution.
    """

    def __init__(
        self,
        heat_matrix: np.ndarray,
        wages: dict[str, float],
        params: dict[str, dict[str, float]] | None = None,
        episode_len: int = EPISODE_LEN,
        perception_noise_c: float = DEFAULT_PERCEPTION_NOISE_C,
        initial_cash_days: float = 7.0,
        subsistence_frac: float = 0.5,
        seed: int = 42,
    ):
        if heat_matrix.ndim != 2:
            raise ValueError(f"heat_matrix must be (T, N), got shape {heat_matrix.shape}")
        n_steps = heat_matrix.shape[0]
        if n_steps <= episode_len:
            raise ValueError(f"need > {episode_len} real days of heat, got {n_steps}")

        self.heat = np.asarray(heat_matrix, dtype=np.float64)
        self.occupations = tuple(o for o in OCCUPATIONS if o in wages)
        if not self.occupations:
            raise ValueError(f"wages must cover at least one of {OCCUPATIONS}")
        self.wages = dict(wages)
        self.episode_len = episode_len
        self.perception_noise_c = float(perception_noise_c)
        self.initial_cash_days = float(initial_cash_days)
        self.subsistence_frac = float(subsistence_frac)

        # Reward parameters per occupation; defaults until calibration fits them.
        self.params = {
            occ: {"kappa": default_kappa(self.wages[occ]), "gamma": DEFAULT_GAMMA}
            for occ in self.occupations
        }
        if params:
            for occ, p in params.items():
                if occ in self.params:
                    self.params[occ] = {"kappa": float(p["kappa"]), "gamma": float(p["gamma"])}

        # Observation normalization constants are read from the REAL heat data.
        self.heat_mu = float(self.heat.mean())
        self.heat_sigma = float(self.heat.std()) or 1.0

        self.observation_dim = 2 + len(self.occupations)  # cash, heat, occ one-hot
        self.action_dim = N_ACTIONS
        self.rng = np.random.default_rng(seed)

        self._episode_heat: np.ndarray | None = None
        self._occupation: str | None = None
        self._t = 0
        self._cash = 0.0

    # -- internals --------------------------------------------------------

    def _observe(self) -> np.ndarray:
        """Partial observation: heat is perceived with noise; reward uses truth."""
        true_heat = self._episode_heat[self._t]
        perceived = true_heat + self.rng.normal(0.0, self.perception_noise_c)
        occ_onehot = np.zeros(len(self.occupations))
        occ_onehot[self.occupations.index(self._occupation)] = 1.0
        cash_norm = self._cash / (self.initial_cash_days * self.wages[self._occupation])
        return np.concatenate([
            [cash_norm, (perceived - self.heat_mu) / self.heat_sigma],
            occ_onehot,
        ]).astype(np.float32)

    # -- Gymnasium-style API ----------------------------------------------

    def reset(self, seed: int | None = None, occupation: str | None = None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)

        self._occupation = occupation or self.occupations[
            int(self.rng.integers(len(self.occupations)))
        ]
        # A real contiguous 30-day window at a real node.
        node = int(self.rng.integers(self.heat.shape[1]))
        start = int(self.rng.integers(self.heat.shape[0] - self.episode_len))
        self._episode_heat = self.heat[start:start + self.episode_len, node]
        self._t = 0
        self._cash = self.initial_cash_days * self.wages[self._occupation]
        return self._observe(), {"occupation": self._occupation, "node": node, "start": start}

    def step(self, action: int):
        if self._episode_heat is None:
            raise RuntimeError("step() called before reset()")
        if action not in (ACTION_REST, ACTION_WORK):
            raise ValueError(f"action must be 0 (rest) or 1 (work), got {action!r}")

        p = self.params[self._occupation]
        wage = self.wages[self._occupation]
        true_heat = float(self._episode_heat[self._t])
        r = reward(action, true_heat, wage, p["kappa"], p["gamma"])

        # Cash evolves but does not enter R (see module docstring).
        self._cash += wage * action - self.subsistence_frac * wage

        self._t += 1
        truncated = self._t >= self.episode_len  # time limit, not a failure state
        terminated = False
        obs = self._observe() if not truncated else np.zeros(self.observation_dim, np.float32)
        info = {"true_wbgt_c": true_heat, "cash": self._cash, "occupation": self._occupation,
                "worked": int(action)}
        return obs, r, terminated, truncated, info

    # -- behavioural reference policy -------------------------------------

    def softmax_work_prob(self, exposure, occupation: str, tau: float):
        """P(work | exposure) under a logit (random-utility) choice rule.

        P(work) = exp(R_work/tau) / (exp(R_work/tau) + exp(R_rest/tau)), and
        R_rest = 0, so this reduces to sigmoid(R_work / tau). `tau` is the
        choice-noise scale; see calibration.py for why it is fixed rather than
        fitted. This is the POPULATION behaviour model, distinct from the
        reward-maximising PPO policy.
        """
        p = self.params[occupation]
        r_work = self.wages[occupation] - heat_cost(exposure, p["kappa"], p["gamma"])
        # Logistic written via tanh to stay numerically stable in both tails.
        return 0.5 * (1.0 + np.tanh(0.5 * r_work / tau))
