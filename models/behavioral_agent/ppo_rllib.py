"""OPTIONAL RLlib cross-check. Never on the critical path.

If ray[rllib] is installed this trains PPO on the same WorkerEnv and prints its
mean episode return next to the from-scratch run, as an independent check that
the from-scratch implementation lands in the same place. If ray is absent this
prints a skip line and exits 0 -- a missing optional dependency must NEVER fail
the build (CLAUDE.md: ILOSTAT/RLlib-style enrichment is always try/except-guarded).
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        import ray  # noqa: F401
        from ray.rllib.algorithms.ppo import PPOConfig
    except Exception:
        # Deliberately broad: a partial/incompatible ray install raises all sorts
        # of things at import time, and none of them may break the build.
        print("RLlib not installed, skipping optional comparison")
        return 0

    import numpy as np
    import yaml

    from backend.data.build_wage_loss import CITIES_YAML_PATH
    from backend.data.wages import WageLoader
    from models.behavioral_agent.worker_env import WorkerEnv
    from models.stgcn.train import load_weather

    try:
        import gymnasium as gym
    except Exception:
        print("RLlib present but gymnasium is not, skipping optional comparison")
        return 0

    weather = load_weather()
    heat_matrix = (
        weather.pivot(index="date", columns="node_id", values="wbgt_c").sort_index().to_numpy()
    )
    with open(CITIES_YAML_PATH) as f:
        config = yaml.safe_load(f)
    city_key = config["default_city"]
    wages = WageLoader(country_iso3=config["cities"][city_key]["country_iso3"]) \
        .occupation_baseline_wages(city_key=city_key)

    class GymWorkerEnv(gym.Env):
        """Thin gymnasium adapter over the duck-typed WorkerEnv."""

        def __init__(self, cfg=None):
            self.inner = WorkerEnv(heat_matrix, wages, seed=42)
            self.observation_space = gym.spaces.Box(
                low=-np.inf, high=np.inf, shape=(self.inner.observation_dim,), dtype=np.float32)
            self.action_space = gym.spaces.Discrete(self.inner.action_dim)

        def reset(self, *, seed=None, options=None):
            return self.inner.reset(seed=seed)

        def step(self, action):
            return self.inner.step(int(action))

    try:
        ray.init(ignore_reinit_error=True, log_to_driver=False, include_dashboard=False)
        algo = (
            PPOConfig()
            .environment(GymWorkerEnv)
            .framework("torch")
            .env_runners(num_env_runners=0)
            .training(train_batch_size=960, gamma=0.99, lambda_=0.95, clip_param=0.2)
            .build()
        )
        for i in range(5):
            result = algo.train()
            mean = result.get("env_runners", {}).get("episode_return_mean",
                                                     result.get("episode_reward_mean"))
            print(f"  [rllib] iter {i + 1}/5 mean episode return = {mean}")
        algo.stop()
    except Exception as exc:
        print(f"RLlib comparison failed ({type(exc).__name__}: {exc}); "
              f"skipping -- optional path, build unaffected")
        return 0
    finally:
        try:
            ray.shutdown()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
