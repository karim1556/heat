"""Cumulative-prospect-theory and hyperbolic-discounting transforms.

PURE POST-HOC FUNCTIONS. None of these is used inside the PPO training loop --
PPO maximises the objective reward, and these transforms are applied afterwards
to re-express the resulting outcome distribution the way a real worker weighs
it. Keeping them out of the loop matters: folding a non-linear value function
into the reward would change the fixed point being learned and would silently
invalidate any claim that the agent is optimising the stated reward.

All parameter defaults are the canonical published estimates, cited inline.
Every function is elementwise and accepts scalars or arrays.
"""

from __future__ import annotations

import numpy as np

# Tversky & Kahneman (1992), "Advances in Prospect Theory: Cumulative
# Representation of Uncertainty", J. Risk and Uncertainty 5:297-323.
#   value function : alpha = beta = 0.88, lambda = 2.25
#   weighting fn   : gamma = 0.61 (gains), 0.69 (losses)
PT_ALPHA = 0.88
PT_BETA = 0.88
PT_LAMBDA = 2.25
PW_GAMMA = 0.61


def prospect_value(x, alpha: float = PT_ALPHA, beta: float = PT_BETA,
                   lam: float = PT_LAMBDA):
    """Tversky-Kahneman (1992) value function, in deviations from a reference.

        v(x) =  x^alpha            for x >= 0
        v(x) = -lam * (-x)^beta    for x <  0

    Concave in gains, convex in losses, and steeper in losses (lam > 1) -- so a
    wage loss of X hurts more than a wage gain of X pleases. That asymmetry is
    the reason a worker buys insurance at a premium above expected loss.
    """
    if alpha <= 0 or beta <= 0:
        raise ValueError(f"alpha and beta must be > 0, got {alpha}, {beta}")
    if lam <= 0:
        raise ValueError(f"lam must be > 0, got {lam}")
    x = np.asarray(x, dtype=float)
    # Take |x| BEFORE the fractional power: a negative base with a fractional
    # exponent is NaN in IEEE arithmetic, and np.where would still evaluate it.
    magnitude = np.abs(x)
    gains = magnitude**alpha
    losses = -lam * magnitude**beta
    out = np.where(x >= 0, gains, losses)
    return out if out.ndim else out.item()


def probability_weight(p, gamma: float = PW_GAMMA):
    """Tversky-Kahneman (1992) cumulative probability weighting function.

        w(p) = p^gamma / (p^gamma + (1-p)^gamma)^(1/gamma)

    Inverse-S: small probabilities are OVER-weighted and large ones UNDER-
    weighted, with a fixed point near p ~ 1/3. This is why a rare, severe
    heatwave feels more likely than its base rate -- and why parametric cover
    against it is attractive at an actuarially loaded price.
    """
    if not 0 < gamma <= 1:
        raise ValueError(f"gamma must be in (0, 1], got {gamma}")
    p = np.asarray(p, dtype=float)
    if np.any((p < 0) | (p > 1)):
        raise ValueError("p must lie in [0, 1]")
    num = p**gamma
    denom = (p**gamma + (1.0 - p) ** gamma) ** (1.0 / gamma)
    # p = 0 and p = 1 give 0/1 and 1/1 exactly; no guard needed, but denom == 0
    # cannot occur for p in [0,1] since the two terms never vanish together.
    out = num / denom
    return out if out.ndim else out.item()


def quasi_hyperbolic_discount(rewards, beta: float, delta: float, axis: int = -1):
    """Laibson (1997) beta-delta present value of a reward stream.

        PV = r_0 + beta * sum_{t>=1} delta^t * r_t

    The PRESENT period is undiscounted; every future period takes an extra,
    uniform beta < 1 haircut. That single kink -- not the geometric delta -- is
    what produces present bias and preference reversal: a worker who would
    rather rest tomorrow works today anyway.

    beta = 1 collapses this to standard exponential discounting.
    """
    if not 0 < beta <= 1:
        raise ValueError(f"beta must be in (0, 1], got {beta}")
    if not 0 < delta <= 1:
        raise ValueError(f"delta must be in (0, 1], got {delta}")
    r = np.asarray(rewards, dtype=float)
    if r.ndim == 0:
        raise ValueError("rewards must be a sequence, not a scalar")

    horizon = r.shape[axis]
    t = np.arange(horizon)
    weights = np.where(t == 0, 1.0, beta * delta**t.astype(float))
    # Broadcast the weights along `axis` regardless of the array's rank.
    shape = [1] * r.ndim
    shape[axis] = horizon
    out = np.sum(r * weights.reshape(shape), axis=axis)
    return out if out.ndim else out.item()
