"""Minimal PPO (Schulman et al. 2017, arXiv:1707.06347) for the worker POMDP.

From scratch in plain torch: no RLlib, no stable-baselines. RLlib is optional
and off the critical path (see ppo_rllib.py).

The comments here explain WHY each term is written the way it is, because every
one of them is a place where a wrong implementation still runs, still produces
falling loss curves, and is still silently invalid.

CPU-only, seed=42, <5 min on a laptop (CLAUDE.md Golden Rules 2-4).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import torch
import yaml
from torch import nn

from backend.data.build_wage_loss import CITIES_YAML_PATH
from backend.data.wages import WageLoader
from models.behavioral_agent.worker_env import EPISODE_LEN, WorkerEnv, heat_cost
from models.stgcn.train import load_weather

SEED = 42

# Per-state namespacing (v2): STATE_KEY set -> this state's policy/plot and its
# OWN wage schedule + currency (the POMDP reward is wage vs heat-cost, so the
# wages MUST be this state's, never Ahmedabad's). Unset -> legacy paths, {CCY}.
STATE_KEY = os.environ.get("STATE_KEY")
if STATE_KEY:
    from backend.state_context import get_context

    _CTX = get_context(STATE_KEY)
    POLICY_PATH = _CTX.artifact("ppo_policy.pt")
    PLOT_PATH = _CTX.artifact("ppo_reward.png")
    CCY = _CTX.currency
else:
    _CTX = None
    POLICY_PATH = Path("models/artifacts/ppo_policy.pt")
    PLOT_PATH = Path("notebooks/artifacts/ppo_reward.png")
    CCY = "INR"

HIDDEN = 32
MAX_ITERS = 200
PLATEAU_PATIENCE = 20
EPISODES_PER_ITER = 8
EVAL_EPISODES = 32
EVAL_SEED_BASE = 10_000
UPDATE_EPOCHS = 4
MINIBATCH = 64
LR = 3e-4
GAMMA_DISCOUNT = 0.99
GAE_LAMBDA = 0.95
CLIP_EPS = 0.2
VALUE_COEF = 0.5
ENTROPY_COEF = 0.01
MAX_GRAD_NORM = 0.5


def set_seeds(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


class ActorCritic(nn.Module):
    """Separate policy and value heads, tiny MLP (hidden 32).

    Separate trunks rather than a shared one: with a 5-dim observation there is
    nothing to gain from sharing features, and a shared trunk would make the
    value loss coefficient tug on the policy's representation -- one more knob
    that can silently distort the policy gradient.
    """

    def __init__(self, obs_dim: int, n_actions: int, hidden: int = HIDDEN):
        super().__init__()
        self.pi = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, n_actions),
        )
        self.v = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, 1),
        )
        self.apply(self._init)
        # Small final-layer gain on the policy head so the initial policy is
        # near-uniform: a confident random policy would collapse exploration
        # before the value function is worth trusting.
        nn.init.orthogonal_(self.pi[-1].weight, gain=0.01)
        nn.init.orthogonal_(self.v[-1].weight, gain=1.0)

    @staticmethod
    def _init(m: nn.Module) -> None:
        if isinstance(m, nn.Linear):
            nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
            nn.init.zeros_(m.bias)

    def forward(self, obs: torch.Tensor):
        return self.pi(obs), self.v(obs).squeeze(-1)

    def act(self, obs: torch.Tensor):
        logits = self.pi(obs)
        dist = torch.distributions.Categorical(logits=logits)
        action = dist.sample()
        return action, dist.log_prob(action), self.v(obs).squeeze(-1)


def compute_gae(rewards: np.ndarray, values: np.ndarray, dones: np.ndarray,
                last_value: float, gamma: float = GAMMA_DISCOUNT,
                lam: float = GAE_LAMBDA) -> tuple[np.ndarray, np.ndarray]:
    """Generalized Advantage Estimation (Schulman et al. 2015).

        delta_t = r_t + gamma * V(s_{t+1}) * (1 - done_t) - V(s_t)
        A_t     = delta_t + gamma * lam * (1 - done_t) * A_{t+1}

    The (1 - done_t) factors are the whole game. Dropping either one bootstraps
    across an episode boundary -- the agent gets credit for reward earned in the
    NEXT episode, the advantages stay finite and plausible, the loss still falls,
    and the learned policy is wrong. `dones` must mark the last step of each
    episode.

    Returns (advantages, returns) with returns = advantages + values, which is
    the standard GAE-consistent value target (a lambda-return).
    """
    n = len(rewards)
    if not (len(values) == len(dones) == n):
        raise ValueError("rewards, values and dones must be the same length")
    adv = np.zeros(n, dtype=np.float64)
    running = 0.0
    for t in reversed(range(n)):
        next_value = last_value if t == n - 1 else values[t + 1]
        non_terminal = 1.0 - float(dones[t])
        delta = rewards[t] + gamma * next_value * non_terminal - values[t]
        running = delta + gamma * lam * non_terminal * running
        adv[t] = running
    return adv, adv + values


def ppo_policy_loss(new_logp: torch.Tensor, old_logp: torch.Tensor,
                    advantages: torch.Tensor, clip_eps: float = CLIP_EPS) -> torch.Tensor:
    """Clipped surrogate objective, returned as a LOSS (negated objective).

        ratio = exp(log pi_new - log pi_old)
        L = -E[ min( ratio * A, clip(ratio, 1-eps, 1+eps) * A ) ]

    Subtracting log-probs before exponentiating (rather than dividing the
    probabilities) keeps the ratio stable when either probability is tiny.

    `advantages` MUST be detached: they are treated as constants of the current
    update. If a gradient flowed through them the objective would no longer be
    the policy gradient at all.

    The min() is what makes the clip pessimistic: it takes the LOWER of the
    clipped and unclipped objectives, so clipping only ever removes incentive to
    move further, never adds it. Using clip() alone would leave the objective
    unbounded on the side where clipping does not bind.
    """
    if advantages.requires_grad:
        raise ValueError("advantages must be detached before entering the PPO loss")
    ratio = torch.exp(new_logp - old_logp)
    unclipped = ratio * advantages
    clipped = torch.clamp(ratio, 1.0 - clip_eps, 1.0 + clip_eps) * advantages
    return -torch.min(unclipped, clipped).mean()


def value_loss(new_values: torch.Tensor, returns: torch.Tensor) -> torch.Tensor:
    """Plain MSE value regression against the lambda-returns."""
    return 0.5 * ((new_values - returns) ** 2).mean()


def collect_rollout(env: WorkerEnv, model: ActorCritic, n_episodes: int, reward_scale: float):
    """Run whole episodes so every `done` is a real episode boundary."""
    obs_buf, act_buf, logp_buf, val_buf, rew_buf, done_buf = [], [], [], [], [], []
    episode_returns, work_rate = [], []

    for _ in range(n_episodes):
        obs, _ = env.reset()
        ep_return, ep_worked, steps = 0.0, 0, 0
        while True:
            obs_t = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
            with torch.no_grad():
                action, logp, value = model.act(obs_t)
            next_obs, reward, terminated, truncated, info = env.step(int(action.item()))
            done = terminated or truncated

            obs_buf.append(obs)
            act_buf.append(int(action.item()))
            logp_buf.append(float(logp.item()))
            val_buf.append(float(value.item()))
            rew_buf.append(reward * reward_scale)
            done_buf.append(float(done))

            ep_return += reward
            ep_worked += info["worked"]
            steps += 1
            obs = next_obs
            if done:
                break
        episode_returns.append(ep_return)
        work_rate.append(ep_worked / steps)

    # Episodes always end at the 30-step time limit, and the final `done` cuts
    # bootstrapping there, so the trailing bootstrap value is never used.
    return (
        np.array(obs_buf, dtype=np.float32), np.array(act_buf), np.array(logp_buf),
        np.array(val_buf), np.array(rew_buf), np.array(done_buf),
        float(np.mean(episode_returns)), float(np.mean(work_rate)),
    )


def rollout_fixed(env: WorkerEnv, policy_fn, n_episodes: int, base_seed: int):
    """Run a policy over a FIXED set of episodes -> (mean return {CCY}, work rate).

    WHY THIS EXISTS: the training return is measured on freshly sampled 30-day
    windows, so it swings by thousands of rupees between iterations purely
    because one month happened to be cooler than another. Selecting the "best"
    checkpoint on that signal selects the LUCKIEST ROLLOUT, not the best policy.
    Re-seeding the env per episode pins the occupation, node and window, so every
    iteration is scored on identical weather and the comparison is real.
    """
    returns, work = [], []
    for i in range(n_episodes):
        obs, _ = env.reset(seed=base_seed + i)
        total, worked, steps = 0.0, 0, 0
        while True:
            obs, r, terminated, truncated, info = env.step(policy_fn(obs, env))
            total += r
            worked += info["worked"]
            steps += 1
            if terminated or truncated:
                break
        returns.append(total)
        work.append(worked / steps)
    return float(np.mean(returns)), float(np.mean(work))


def greedy_policy(model: ActorCritic):
    """Deterministic (argmax) evaluation of the stochastic policy."""
    def act(obs, _env):
        with torch.no_grad():
            logits = model.pi(torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0))
        return int(logits.argmax(-1).item())
    return act


def oracle_policy(obs, env: WorkerEnv) -> int:
    """Myopic optimum computed on the TRUE heat: work iff the reward is positive.

    Because R depends only on (action, exposure), this threshold rule is exactly
    optimal -- it is the ceiling PPO is chasing. The agent cannot reach it: it
    only sees heat through perceptual noise, so the ORACLE-MINUS-PPO gap is a
    direct measurement of the cost of partial observability, not a training bug.
    """
    p = env.params[env._occupation]
    true_heat = env._episode_heat[env._t]
    return int(env.wages[env._occupation] > heat_cost(true_heat, p["kappa"], p["gamma"]))


def always_work_policy(_obs, _env) -> int:
    """Naive baseline: a worker with no option to rest."""
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Train PPO on the worker heat POMDP")
    parser.add_argument("--iters", type=int, default=MAX_ITERS)
    parser.add_argument("--calibration", default=None,
                        help="optional calibration.json; default = documented defaults, "
                             "so a fresh run is reproducible without it")
    args = parser.parse_args()

    started = time.time()
    set_seeds(SEED)
    torch.set_num_threads(1)
    print("=" * 72)
    print("PPO (from scratch) -- worker work/rest POMDP under real heat")
    print("=" * 72)
    print(f"[SEED]     seed={SEED} (random, numpy, torch) | device=cpu")

    # --- Real data --------------------------------------------------------
    weather = load_weather()
    heat_matrix = (
        weather.pivot(index="date", columns="node_id", values="wbgt_c").sort_index().to_numpy()
    )
    if _CTX is not None:
        wages = _CTX.daily_wages()   # this state's own schedule, in its own currency
    else:
        with open(CITIES_YAML_PATH) as f:
            config = yaml.safe_load(f)
        city_key = config["default_city"]
        wages = WageLoader(country_iso3=config["cities"][city_key]["country_iso3"]) \
            .occupation_baseline_wages(city_key=city_key)
    print(f"[REAL API] NASA POWER shade-WBGT: {heat_matrix.shape[0]} days x "
          f"{heat_matrix.shape[1]} nodes | episodes draw real 30-day windows")
    print(f"[CITED]    baseline daily wages ({CCY}): "
          f"{ {k: round(v, 1) for k, v in wages.items()} }")

    params = None
    if args.calibration and Path(args.calibration).exists():
        params = json.loads(Path(args.calibration).read_text())
        print(f"[PARAMS]   kappa/gamma from {args.calibration}")
    else:
        print("[PARAMS]   kappa/gamma = documented defaults (indifference at 30C WBGT); "
              "calibration.py fits them afterwards")
    env = WorkerEnv(heat_matrix, wages, params=params, seed=SEED)
    # A separate env instance for evaluation: reset(seed=...) re-seeds the env
    # RNG, which would otherwise reach into the training stream and destroy
    # reproducibility of the rollouts.
    eval_env = WorkerEnv(heat_matrix, wages, params=params, seed=SEED + 1)
    for occ in env.occupations:
        p = env.params[occ]
        print(f"           {occ:13s} wage={wages[occ]:6.1f} kappa={p['kappa']:.4g} "
              f"gamma={p['gamma']:.4g}")

    # Rewards are hundreds of rupees; a value head regressing on that scale
    # starts with a huge error and swamps the policy gradient. Dividing by the
    # mean wage expresses returns in units of one daily wage. This is a positive
    # affine rescaling of R, so it CANNOT change the optimal policy -- only the
    # conditioning of the value regression.
    reward_scale = 1.0 / float(np.mean(list(wages.values())))
    print(f"[SCALE]    reward scaled by 1/mean_wage = {reward_scale:.5f} "
          f"(returns in units of one daily wage; optimal policy unchanged)")

    model = ActorCritic(env.observation_dim, env.action_dim, HIDDEN)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, eps=1e-5)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[MODEL]    ActorCritic hidden={HIDDEN} params={n_params} | "
          f"obs_dim={env.observation_dim} actions={env.action_dim}")
    print(f"[PPO]      clip={CLIP_EPS} gamma={GAMMA_DISCOUNT} lambda={GAE_LAMBDA} "
          f"epochs={UPDATE_EPOCHS} minibatch={MINIBATCH} lr={LR}")

    # Reference points on the SAME fixed episodes the policy is scored on.
    oracle_return, oracle_work = rollout_fixed(
        eval_env, oracle_policy, EVAL_EPISODES, EVAL_SEED_BASE)
    naive_return, naive_work = rollout_fixed(
        eval_env, always_work_policy, EVAL_EPISODES, EVAL_SEED_BASE)
    print(f"[EVAL]     {EVAL_EPISODES} fixed episodes (identical weather every iteration)")
    print(f"           oracle (true-heat threshold, myopic optimum): "
          f"{oracle_return:8.2f} {CCY}  work_rate={oracle_work:.3f}")
    print(f"           naive  (always work)                        : "
          f"{naive_return:8.2f} {CCY}  work_rate={naive_work:.3f}")

    history: list[dict] = []
    best_return, best_iter, no_improve = -np.inf, 0, 0
    best_state = {k: v.clone() for k, v in model.state_dict().items()}

    for iteration in range(1, args.iters + 1):
        obs, actions, old_logp, values, rewards, dones, mean_return, work_rate = \
            collect_rollout(env, model, EPISODES_PER_ITER, reward_scale)

        advantages, returns = compute_gae(rewards, values, dones, last_value=0.0)

        obs_t = torch.as_tensor(obs)
        act_t = torch.as_tensor(actions, dtype=torch.long)
        # Detached by construction: these are the fixed reference point of this
        # update, not differentiable quantities.
        old_logp_t = torch.as_tensor(old_logp, dtype=torch.float32)
        adv_t = torch.as_tensor(advantages, dtype=torch.float32)
        ret_t = torch.as_tensor(returns, dtype=torch.float32)

        # Advantage normalization: a variance-reduction trick on the gradient
        # SCALE, applied per-batch. It leaves the sign of every advantage intact,
        # so the direction of the policy gradient is unchanged.
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

        idx = np.arange(len(obs))
        last_losses = {}
        for _ in range(UPDATE_EPOCHS):
            np.random.shuffle(idx)
            for start in range(0, len(idx), MINIBATCH):
                mb = idx[start:start + MINIBATCH]
                logits, v_pred = model(obs_t[mb])
                dist = torch.distributions.Categorical(logits=logits)
                new_logp = dist.log_prob(act_t[mb])

                pi_loss = ppo_policy_loss(new_logp, old_logp_t[mb], adv_t[mb], CLIP_EPS)
                v_loss = value_loss(v_pred, ret_t[mb])
                # Entropy BONUS -> subtracted from the loss. Sign errors here are
                # invisible: the run still trains, just straight into a collapsed
                # deterministic policy.
                entropy = dist.entropy().mean()
                loss = pi_loss + VALUE_COEF * v_loss - ENTROPY_COEF * entropy

                optimizer.zero_grad()
                loss.backward()
                # Clip the global norm, not per-parameter: preserves the gradient
                # DIRECTION and only bounds its length.
                nn.utils.clip_grad_norm_(model.parameters(), MAX_GRAD_NORM)
                optimizer.step()
                last_losses = {"pi": float(pi_loss.item()), "v": float(v_loss.item()),
                               "entropy": float(entropy.item())}

        # Model selection and early stopping use the FIXED eval set, never the
        # noisy training return (see rollout_fixed).
        eval_return, eval_work = rollout_fixed(
            eval_env, greedy_policy(model), EVAL_EPISODES, EVAL_SEED_BASE)
        history.append({"iter": iteration, "train_return": mean_return,
                        "train_work_rate": work_rate, "eval_return": eval_return,
                        "eval_work_rate": eval_work, **last_losses})

        if eval_return > best_return + 1e-9:
            best_return, best_iter, no_improve = eval_return, iteration, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            no_improve += 1

        if iteration % 10 == 0 or iteration == 1:
            print(f"  iter {iteration:3d}/{args.iters}  eval={eval_return:8.2f} {CCY} "
                  f"({eval_return / oracle_return * 100:5.1f}% of oracle)  "
                  f"work={eval_work:.3f}  train={mean_return:8.2f}  "
                  f"pi={last_losses['pi']:+.4f} v={last_losses['v']:.4f} "
                  f"H={last_losses['entropy']:.3f}")

        if no_improve >= PLATEAU_PATIENCE:
            print(f"[EARLY]    plateau: no improvement in {PLATEAU_PATIENCE} iters "
                  f"(stopped at {iteration})")
            break

    model.load_state_dict(best_state)
    print("=" * 72)
    print(f"[BEST]     iter {best_iter}: eval return={best_return:.2f} {CCY} over "
          f"{EPISODE_LEN} days (weights restored)")
    print(f"           oracle (myopic optimum, sees TRUE heat) : {oracle_return:8.2f} {CCY}")
    print(f"           PPO    (sees heat through POMDP noise)  : {best_return:8.2f} {CCY} "
          f"({best_return / oracle_return * 100:.1f}% of oracle)")
    print(f"           naive  (always work)                    : {naive_return:8.2f} {CCY}")
    print(f"           oracle - PPO = {oracle_return - best_return:.2f} {CCY}: "
          f"the price of partial observability")
    if best_return <= naive_return:
        print("           WARNING: PPO did not beat the always-work baseline.")
    print("=" * 72)

    POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "state_dict": model.state_dict(),
        "config": {"hidden": HIDDEN, "obs_dim": env.observation_dim,
                   "n_actions": env.action_dim, "seed": SEED,
                   "reward_scale": reward_scale, "episode_len": EPISODE_LEN},
        "env_params": {"occupations": list(env.occupations), "wages": wages,
                       "params": env.params,
                       "perception_noise_c": env.perception_noise_c},
        "metrics": {"best_eval_return_inr": best_return, "best_iter": best_iter,
                    "oracle_return_inr": oracle_return,
                    "naive_return_inr": naive_return,
                    "pct_of_oracle": best_return / oracle_return * 100.0,
                    "iters_run": len(history)},
        "history": history,
    }, POLICY_PATH)
    print(f"[ARTIFACT] {POLICY_PATH}")

    _plot(history, best_iter, best_return, oracle_return, oracle_work, naive_return)
    print(f"[ARTIFACT] {PLOT_PATH}")
    print(f"[TIME]     {time.time() - started:.1f}s total")
    return 0


def _plot(history, best_iter, best_return, oracle_return, oracle_work, naive_return) -> None:
    it = [h["iter"] for h in history]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    for key, color, lw, label in (
        ("train_return", "#dee2e6", 1.0, "train (fresh windows -- noisy)"),
        ("eval_return", "#c1121f", 1.4, "eval (fixed windows)"),
    ):
        ax1.plot(it, [h[key] for h in history], color=color, lw=lw, label=label)
    for y, color, label in ((oracle_return, "#2a9d8f", f"oracle ({oracle_return:.0f})"),
                            (naive_return, "#adb5bd", f"always work ({naive_return:.0f})")):
        ax1.axhline(y, ls="--", c=color, lw=1.2, label=label)
    ax1.axvline(best_iter, ls=":", c="grey", lw=1, label=f"best iter ({best_iter})")
    ax1.set(xlabel="PPO iteration", ylabel=f"mean episode return ({CCY} / {EPISODE_LEN}d)",
            title=f"Learning curve -- {best_return / oracle_return * 100:.1f}% of oracle")

    ax2.plot(it, [h["eval_work_rate"] for h in history], color="#2a9d8f", lw=1.4,
             label="PPO (greedy)")
    ax2.axhline(oracle_work, ls="--", c="#264653", lw=1.2, label=f"oracle ({oracle_work:.3f})")
    ax2.set(xlabel="PPO iteration", ylabel="fraction of days worked", ylim=(-0.02, 1.02),
            title="Behaviour: work rate under real heat")

    for ax in (ax1, ax2):
        ax.legend(fontsize=7)
        ax.grid(alpha=0.3)
    fig.suptitle(f"PPO from scratch -- worker heat POMDP, seed={SEED}", fontsize=11)
    fig.tight_layout()
    PLOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PLOT_PATH, dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    sys.exit(main())
