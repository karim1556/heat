"""Unit tests for the behavioral agent: PPO internals, env, and CPT transforms.

The PPO tests target the places where a wrong implementation still RUNS: the
policy-gradient direction, the GAE done-masking, and the clip branch. Shape
tests would pass on all three while the science was silently invalid.
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from models.behavioral_agent.behavioral_layers import (
    prospect_value,
    probability_weight,
    quasi_hyperbolic_discount,
)
from models.behavioral_agent.ppo_from_scratch import (
    ActorCritic,
    compute_gae,
    ppo_policy_loss,
)
from models.behavioral_agent.worker_env import (
    ACTION_REST,
    ACTION_WORK,
    EPISODE_LEN,
    WorkerEnv,
    default_kappa,
    reward as env_reward,
)

# --- toy 2-state MDP -----------------------------------------------------
#
# One step, then the episode ends. 2 states, 2 actions, known reward table and
# known start-state distribution, so the true expected return
#     J(theta) = sum_s p(s) sum_a pi_theta(a|s) R(s,a)
# is computable in closed form and differentiable by finite differences.
#
# float64 THROUGHOUT, deliberately: a central difference with eps=1e-5 forms a
# numerator of order 1e-5, and float32 carries only ~7 significant digits, so the
# cancellation alone produces ~5% error and would mask (or fake) a real gradient
# bug. In float64 the same check agrees to ~1e-11.
TOY_DTYPE = torch.float64
TOY_REWARDS = torch.tensor([[1.0, -2.0], [0.5, 3.0]], dtype=TOY_DTYPE)  # R[state, action]
TOY_START = torch.tensor([0.6, 0.4], dtype=TOY_DTYPE)                    # p(state)


def toy_expected_return(logits: torch.Tensor) -> torch.Tensor:
    """J(theta) for the toy MDP -- exact, no sampling."""
    probs = torch.softmax(logits, dim=-1)
    return (TOY_START.unsqueeze(-1) * probs * TOY_REWARDS).sum()


def test_ppo_policy_gradient_matches_finite_differences_on_toy_mdp():
    """The PPO surrogate's gradient must point along the TRUE performance gradient.

    Constructed to be EXACT rather than Monte-Carlo: every (s, a) pair appears
    once, and each pair's probability mass p(s)*pi(a|s) is folded into its
    (detached) advantage. Because advantages are constants of the update, this
    turns the batch mean into the exact expectation:

        mean_i[ratio_i * A_i] = sum_{s,a} p(s) pi_old(a|s) ratio(s,a) R(s,a)
                              = sum_{s,a} p(s) pi_theta(a|s) R(s,a) = J(theta)

    so -d(loss)/d(theta) must equal dJ/d(theta) with no sampling error at all.
    At theta = theta_old the ratio is exactly 1, which is inside the clip range,
    and both branches of the min() carry the same gradient -- so tie-breaking in
    torch.min cannot affect the result.
    """
    logits = torch.tensor([[0.3, -0.7], [-0.2, 0.9]], dtype=TOY_DTYPE, requires_grad=True)

    states = torch.tensor([0, 0, 1, 1])
    actions = torch.tensor([0, 1, 0, 1])
    n_pairs = len(states)

    log_probs = torch.log_softmax(logits, dim=-1)[states, actions]
    old_logp = log_probs.detach()

    weights = TOY_START[states] * log_probs.detach().exp()
    advantages = (TOY_REWARDS[states, actions] * weights * n_pairs).detach()

    loss = ppo_policy_loss(log_probs, old_logp, advantages, clip_eps=0.2)
    loss.backward()
    analytic = -logits.grad.detach().clone()  # loss = -J  =>  -dloss = dJ

    # Central finite differences on the exact J.
    eps = 1e-5
    numeric = torch.zeros_like(analytic)
    base = logits.detach().clone()
    for i in range(base.shape[0]):
        for j in range(base.shape[1]):
            plus, minus = base.clone(), base.clone()
            plus[i, j] += eps
            minus[i, j] -= eps
            numeric[i, j] = (toy_expected_return(plus) - toy_expected_return(minus)) / (2 * eps)

    torch.testing.assert_close(analytic, numeric, rtol=1e-8, atol=1e-10)

    # Direction, stated separately from magnitude.
    cosine = torch.dot(analytic.flatten(), numeric.flatten()) / (
        analytic.norm() * numeric.norm()
    )
    assert cosine > 1.0 - 1e-12


def test_ppo_ascends_expected_return_on_toy_mdp():
    """One gradient step along the surrogate must INCREASE the true J."""
    logits = torch.tensor([[0.3, -0.7], [-0.2, 0.9]], dtype=TOY_DTYPE, requires_grad=True)
    states = torch.tensor([0, 0, 1, 1])
    actions = torch.tensor([0, 1, 0, 1])

    j_before = toy_expected_return(logits).item()
    log_probs = torch.log_softmax(logits, dim=-1)[states, actions]
    weights = TOY_START[states] * log_probs.detach().exp()
    advantages = (TOY_REWARDS[states, actions] * weights * len(states)).detach()

    loss = ppo_policy_loss(log_probs, log_probs.detach(), advantages, clip_eps=0.2)
    loss.backward()
    with torch.no_grad():
        stepped = logits - 0.01 * logits.grad  # descend the loss == ascend J
    assert toy_expected_return(stepped).item() > j_before


def test_ppo_loss_rejects_attached_advantages():
    """Advantages carrying a gradient would silently stop being the policy gradient."""
    logp = torch.zeros(3, requires_grad=True)
    with pytest.raises(ValueError, match="detached"):
        ppo_policy_loss(logp, logp.detach(), torch.ones(3, requires_grad=True))


def test_ppo_clip_binds_only_on_the_pessimistic_side():
    """min() must take the LOWER of clipped/unclipped, so clipping never rewards."""
    old_logp = torch.zeros(2)
    # ratio = e^0.5 ~ 1.649, well outside [0.8, 1.2].
    new_logp = torch.full((2,), 0.5)
    eps = 0.2

    # Positive advantage: the objective must be capped at (1+eps)*A.
    pos = ppo_policy_loss(new_logp, old_logp, torch.tensor([1.0, 1.0]), eps)
    assert pos.item() == pytest.approx(-(1.0 + eps))

    # Negative advantage: unclipped ratio*A is LOWER than clipped, so min() picks
    # the unclipped branch and the loss is NOT capped -- the gradient keeps
    # pushing back toward the trust region.
    neg = ppo_policy_loss(new_logp, old_logp, torch.tensor([-1.0, -1.0]), eps)
    assert neg.item() == pytest.approx(float(np.exp(0.5)))


# --- GAE -----------------------------------------------------------------


def test_gae_matches_the_explicit_discounted_sum():
    """A_t = sum_l (gamma*lam)^l delta_{t+l}, checked against the recursion."""
    rng = np.random.default_rng(42)
    n = 6
    rewards = rng.normal(size=n)
    values = rng.normal(size=n)
    dones = np.zeros(n)
    last_value, gamma, lam = 0.7, 0.99, 0.95

    adv, returns = compute_gae(rewards, values, dones, last_value, gamma, lam)

    deltas = np.zeros(n)
    for t in range(n):
        next_v = last_value if t == n - 1 else values[t + 1]
        deltas[t] = rewards[t] + gamma * next_v - values[t]
    expected = np.array([
        sum((gamma * lam) ** k * deltas[t + k] for k in range(n - t)) for t in range(n)
    ])
    np.testing.assert_allclose(adv, expected, rtol=1e-10)
    np.testing.assert_allclose(returns, expected + values, rtol=1e-10)


def test_gae_does_not_bootstrap_across_an_episode_boundary():
    """THE silent bug: without (1-done), episode 1 gets credit for episode 2.

    Advantages before the boundary must be completely unaffected by what happens
    after it.
    """
    gamma, lam = 0.99, 0.95
    values = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    dones = np.array([0.0, 0.0, 1.0, 0.0, 0.0, 1.0])  # episode ends at index 2
    rewards_a = np.array([1.0, 1.0, 1.0, 5.0, 5.0, 5.0])
    rewards_b = np.array([1.0, 1.0, 1.0, -99.0, -99.0, -99.0])  # only ep 2 differs

    adv_a, _ = compute_gae(rewards_a, values, dones, 0.0, gamma, lam)
    adv_b, _ = compute_gae(rewards_b, values, dones, 0.0, gamma, lam)

    np.testing.assert_allclose(adv_a[:3], adv_b[:3], rtol=1e-12)
    assert not np.allclose(adv_a[3:], adv_b[3:])


def test_gae_terminal_step_has_no_bootstrap_term():
    rewards = np.array([2.0])
    values = np.array([0.5])
    adv, _ = compute_gae(rewards, values, np.array([1.0]), last_value=99.0,
                         gamma=0.99, lam=0.95)
    assert adv[0] == pytest.approx(2.0 - 0.5)  # done => the 99.0 must be ignored


def test_gae_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        compute_gae(np.zeros(3), np.zeros(2), np.zeros(3), 0.0)


# --- behavioral layers ---------------------------------------------------


def test_prospect_value_is_loss_averse():
    """The required property: a loss of 10 hurts more than a gain of 10 pleases."""
    assert prospect_value(-10) < -prospect_value(10)


def test_prospect_value_matches_the_closed_form():
    assert prospect_value(10) == pytest.approx(10**0.88)
    assert prospect_value(-10) == pytest.approx(-2.25 * 10**0.88)
    assert prospect_value(0) == pytest.approx(0.0)


def test_prospect_value_loss_aversion_ratio_is_lambda():
    """v(-x) / -v(x) must be exactly lambda when alpha == beta."""
    for x in (0.5, 1.0, 25.0, 400.0):
        assert prospect_value(-x) / -prospect_value(x) == pytest.approx(2.25)


def test_prospect_value_is_concave_in_gains_and_convex_in_losses():
    # EQUALLY spaced x: a second difference only tracks the second derivative on
    # a uniform grid. On a geometric grid this test would fail on a correct
    # implementation.
    x = np.linspace(1.0, 16.0, 31)
    gains = prospect_value(x)
    assert np.all(np.diff(gains, 2) < 0)          # concave in gains
    losses = prospect_value(-x)
    assert np.all(np.diff(losses, 2) > 0)         # convex in losses


def test_prospect_value_handles_arrays_without_nan():
    out = prospect_value(np.array([-100.0, -1.0, 0.0, 1.0, 100.0]))
    assert np.all(np.isfinite(out))
    assert np.all(np.diff(out) > 0)               # strictly increasing


def test_probability_weight_is_not_the_identity():
    """The required property: w(0.5) != 0.5 at gamma = 0.61."""
    assert probability_weight(0.5) != pytest.approx(0.5)
    assert probability_weight(0.5) == pytest.approx(0.4206, abs=1e-3)


def test_probability_weight_fixes_the_endpoints():
    assert probability_weight(0.0) == pytest.approx(0.0)
    assert probability_weight(1.0) == pytest.approx(1.0)


def test_probability_weight_overweights_rare_events():
    """Inverse-S: small p over-weighted, large p under-weighted."""
    assert probability_weight(0.01) > 0.01        # a rare heatwave feels likelier
    assert probability_weight(0.99) < 0.99


def test_probability_weight_is_the_identity_at_gamma_one():
    for p in (0.1, 0.5, 0.9):
        assert probability_weight(p, gamma=1.0) == pytest.approx(p)


def test_probability_weight_is_monotone_increasing():
    p = np.linspace(0.0, 1.0, 101)
    assert np.all(np.diff(probability_weight(p)) > 0)


def test_probability_weight_rejects_out_of_range_p():
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        probability_weight(1.5)


def test_quasi_hyperbolic_leaves_the_present_period_undiscounted():
    """PV = r_0 + beta * sum_{t>=1} delta^t r_t -- r_0 takes no beta haircut."""
    rewards = [10.0, 10.0, 10.0]
    beta, delta = 0.7, 0.9
    expected = 10.0 + beta * (delta * 10.0 + delta**2 * 10.0)
    assert quasi_hyperbolic_discount(rewards, beta, delta) == pytest.approx(expected)


def test_quasi_hyperbolic_reduces_to_exponential_at_beta_one():
    rewards = [5.0, 4.0, 3.0, 2.0]
    delta = 0.9
    expected = sum(delta**t * r for t, r in enumerate(rewards))
    assert quasi_hyperbolic_discount(rewards, 1.0, delta) == pytest.approx(expected)


def test_quasi_hyperbolic_present_bias_creates_a_preference_reversal():
    """The behavioral signature: beta-delta reverses a choice that delta alone does not.

    Sooner-smaller (10 now) vs later-larger (13 in two periods). Present bias
    picks the sooner reward; exponential discounting with the same delta does not.
    """
    beta, delta = 0.6, 0.95
    sooner = [10.0, 0.0, 0.0]
    later = [0.0, 0.0, 13.0]
    assert quasi_hyperbolic_discount(sooner, beta, delta) > \
        quasi_hyperbolic_discount(later, beta, delta)
    assert quasi_hyperbolic_discount(sooner, 1.0, delta) < \
        quasi_hyperbolic_discount(later, 1.0, delta)


def test_quasi_hyperbolic_applies_along_the_requested_axis():
    rewards = np.array([[10.0, 10.0], [0.0, 20.0]])
    out = quasi_hyperbolic_discount(rewards, 0.5, 0.9, axis=-1)
    assert out.shape == (2,)
    assert out[0] == pytest.approx(10.0 + 0.5 * 0.9 * 10.0)
    assert out[1] == pytest.approx(0.0 + 0.5 * 0.9 * 20.0)


def test_behavioral_layers_reject_invalid_parameters():
    with pytest.raises(ValueError, match="lam"):
        prospect_value(1.0, lam=-1.0)
    with pytest.raises(ValueError, match="gamma"):
        probability_weight(0.5, gamma=0.0)
    with pytest.raises(ValueError, match="beta"):
        quasi_hyperbolic_discount([1.0], beta=0.0, delta=0.9)


# --- environment ---------------------------------------------------------


@pytest.fixture()
def env() -> WorkerEnv:
    rng = np.random.default_rng(0)
    # Real-shaped heat matrix (days x nodes); values here only need to be plausible
    # WBGT for the interface tests -- the real matrix is loaded in training.
    heat = 24.0 + 6.0 * rng.standard_normal((400, 4))
    wages = {"vendor": 368.0, "construction": 406.0, "delivery": 387.0}
    return WorkerEnv(heat, wages, seed=42)


def test_env_step_returns_correctly_shaped_obs_reward_done(env):
    obs, info = env.reset()
    assert obs.shape == (env.observation_dim,)
    assert obs.dtype == np.float32

    obs, reward, terminated, truncated, info = env.step(ACTION_WORK)
    assert obs.shape == (env.observation_dim,)
    assert obs.dtype == np.float32
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert {"true_wbgt_c", "cash", "occupation", "worked"} <= set(info)


def test_env_episode_is_exactly_thirty_steps(env):
    env.reset()
    for step in range(1, EPISODE_LEN + 1):
        _, _, terminated, truncated, _ = env.step(ACTION_WORK)
        done = terminated or truncated
        assert done == (step == EPISODE_LEN), f"episode ended at step {step}"
    assert step == EPISODE_LEN == 30


def test_env_resting_always_yields_zero_reward(env):
    env.reset()
    for _ in range(5):
        _, reward, _, _, _ = env.step(ACTION_REST)
        assert reward == 0.0


def test_env_reward_matches_the_specified_formula(env):
    _, info = env.reset(occupation="vendor")
    p = env.params["vendor"]
    wage = env.wages["vendor"]
    heat = env._episode_heat[0]
    _, reward, _, _, _ = env.step(ACTION_WORK)
    expected = wage - p["kappa"] * np.exp(p["gamma"] * heat)
    assert reward == pytest.approx(expected)
    assert reward == pytest.approx(env_reward(1, heat, wage, p["kappa"], p["gamma"]))


def test_env_is_partially_observed(env):
    """Observed heat must differ from true heat -- that is what makes it a POMDP."""
    env.reset(occupation="vendor")
    true_heat = env._episode_heat[env._t]
    observed = [env._observe()[1] * env.heat_sigma + env.heat_mu for _ in range(20)]
    assert not np.allclose(observed, true_heat), "observation is not noisy: not a POMDP"
    # Unbiased: the perceptual noise has zero mean.
    assert np.mean(observed) == pytest.approx(true_heat, abs=0.5)


def test_env_is_deterministic_given_a_seed(env):
    env.reset(seed=7)
    first = [env.step(ACTION_WORK)[1] for _ in range(10)]
    env.reset(seed=7)
    second = [env.step(ACTION_WORK)[1] for _ in range(10)]
    assert first == second


def test_env_rejects_invalid_actions(env):
    env.reset()
    with pytest.raises(ValueError, match="action"):
        env.step(2)


def test_env_requires_reset_before_step(env):
    fresh = WorkerEnv(env.heat, env.wages, seed=1)
    with pytest.raises(RuntimeError, match="reset"):
        fresh.step(ACTION_WORK)


def test_default_kappa_places_indifference_at_thirty_degrees():
    """wage - kappa*exp(gamma*30) must be exactly 0 at the documented default."""
    wage, gamma = 368.0, 0.1
    kappa = default_kappa(wage, gamma, h_star=30.0)
    assert wage - kappa * np.exp(gamma * 30.0) == pytest.approx(0.0, abs=1e-9)


def test_softmax_work_prob_falls_monotonically_with_heat(env):
    heats = np.linspace(15.0, 45.0, 40)
    probs = env.softmax_work_prob(heats, "vendor", tau=36.8)
    assert np.all(np.diff(probs) < 0)
    assert np.all((probs >= 0) & (probs <= 1))


def test_actor_critic_shapes_and_stochasticity(env):
    torch.manual_seed(42)
    model = ActorCritic(env.observation_dim, env.action_dim, hidden=32)
    obs = torch.randn(7, env.observation_dim)
    logits, values = model(obs)
    assert logits.shape == (7, env.action_dim)
    assert values.shape == (7,)

    action, logp, value = model.act(obs)
    assert action.shape == (7,)
    assert logp.shape == (7,)
    assert value.shape == (7,)
    assert torch.all((action >= 0) & (action < env.action_dim))
