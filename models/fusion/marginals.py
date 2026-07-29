"""Marginal distributions for the mu-TEVI fusion: F_H (heat) and F_L (wage loss).

F_H -- GEV fitted to the city-level daily heat index (the spatial maximum of
shade-WBGT across the real NASA POWER nodes). The spatial max is a BLOCK
MAXIMUM, which is the classically correct object for a GEV; POT exceedances
would instead call for a GPD. Honest caveat, reported by fit_gev() and not
buried: the block here is only 15 strongly-correlated nodes, so the GEV
asymptotic argument is approximate, and the unconditional daily series is
strongly SEASONAL -- a mixture across seasons rather than one GEV. The fit is
therefore justified empirically (best AIC among candidates, QQ plot) with its
KS statistic reported, and the copula fit is separately re-run on empirical
ranks so that any F_H misspecification cannot silently move theta.

F_L -- a TWO-PART (HURDLE) marginal, which is required rather than cosmetic.
Prompt 3's behavioral calibration used a logit choice model, and a logit is
strictly positive everywhere: it SMEARED the cited-zero region into a ~2.4%
wage-loss floor on the 33.5% of node-days that sit at or below the elasticity
threshold, where the cited literature says the loss is exactly 0. That
destroyed the atom at zero. The hurdle marginal restores it:

    F_L(0) = p0                          (point mass at exactly zero)
    F_L(x) = p0 + (1 - p0) * G(x)        for x > 0

with p0 the empirical fraction of node-days in the cited-zero region and G the
CDF of a continuous distribution fitted to the STRICTLY POSITIVE losses only.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

# The cited elasticity threshold: at or below this WBGT the literature says the
# wage loss is exactly zero. Imported rather than hardcoded so this cannot drift
# from backend/data/elasticity.py.
from backend.data.elasticity import ELASTICITY

CITED_ZERO_THRESHOLD_C = ELASTICITY["default"]["wbgt_threshold_c"]

# Candidate families for the strictly-positive part of F_L. Beta is bounded and
# Gamma is not; the choice is made by AIC and reported, never assumed.
POSITIVE_CANDIDATES = {"beta": stats.beta, "gamma": stats.gamma}

# Minimum strictly-positive loss-days required to fit a defensible positive-loss
# distribution. This is a DELIBERATE COVERAGE BOUNDARY, not an arbitrary crash:
# a state with fewer than this many days above the heat-exposure elasticity
# threshold has too little heat-exposure signal to fit F_L's positive part, so
# it is EXCLUDED from pricing (and recorded as such in docs/STATEWISE_RESULTS.md)
# rather than fitted on noise. Typically trips for cold-climate / high-latitude
# / high-altitude states (e.g. US-Alaska: 22 < 30 heat-exposure days).
MIN_POSITIVE_LOSS_DAYS = 30

# Candidate families for F_H. genextreme is the theoretically motivated one for
# block maxima; the others are here so "GEV fits best" is a measured claim.
HEAT_CANDIDATES = {"genextreme": stats.genextreme, "gumbel_r": stats.gumbel_r,
                   "norm": stats.norm}


def _aic(dist, x: np.ndarray, params: tuple) -> tuple[float, float]:
    log_lik = float(np.sum(dist.logpdf(x, *params)))
    return 2 * len(params) - 2 * log_lik, log_lik


def fit_gev(heat_index: np.ndarray) -> dict:
    """Fit a GEV to the city heat index, with an honest goodness-of-fit record.

    Returns the GEV fit plus the AIC of every candidate family and the KS
    statistic, so a reader can see BOTH that GEV is the best available choice
    and how well it actually fits in absolute terms.
    """
    heat_index = np.asarray(heat_index, dtype=float)
    if heat_index.ndim != 1 or len(heat_index) < 30:
        raise ValueError(f"need a 1-D heat index with >=30 obs, got {heat_index.shape}")

    candidates = {}
    for name, dist in HEAT_CANDIDATES.items():
        params = dist.fit(heat_index)
        aic, log_lik = _aic(dist, heat_index, params)
        candidates[name] = {
            "params": [float(p) for p in params],
            "aic": aic,
            "log_lik": log_lik,
            "ks": float(stats.kstest(heat_index, dist.name, args=params).statistic),
        }

    best = min(candidates, key=lambda k: candidates[k]["aic"])
    gev = candidates["genextreme"]
    c, loc, scale = gev["params"]

    # The KS null is rejected at 5% above roughly 1.36/sqrt(n) -- stated so the
    # fit's inadequacy is a number in the record, not a matter of opinion.
    ks_crit = 1.36 / np.sqrt(len(heat_index))

    return {
        "dist": "genextreme",
        "params": {"c": c, "loc": loc, "scale": scale},
        "params_tuple": (c, loc, scale),
        "aic": gev["aic"],
        "ks": gev["ks"],
        "ks_critical_5pct": float(ks_crit),
        "ks_rejects_at_5pct": bool(gev["ks"] > ks_crit),
        "best_by_aic": best,
        "gev_is_best_by_aic": best == "genextreme",
        "candidates": candidates,
        "n": int(len(heat_index)),
    }


def gev_cdf(x, params: tuple) -> np.ndarray:
    return stats.genextreme.cdf(x, *params)


@dataclass
class HurdleMarginal:
    """Two-part marginal: a point mass at exactly 0, plus a continuous positive part.

        F_L(0) = p0,   F_L(x) = p0 + (1 - p0) * G(x)  for x > 0

    SAMPLING RECIPE (this is what Prompt 5's LSMC must follow -- see also the
    note in models/fusion/tevi.py): draw an exact zero with probability p0,
    otherwise draw from the positive-loss distribution. Do NOT sample a single
    continuous distribution over [0, max]: that reintroduces exactly the
    smearing this class exists to remove. `rvs()` and `ppf()` below implement
    the correct recipe.
    """

    p0: float
    positive_dist: str
    positive_params: tuple
    n_zero: int
    n_positive: int
    positive_aic: dict

    @property
    def _dist(self):
        return POSITIVE_CANDIDATES[self.positive_dist]

    @classmethod
    def fit(cls, losses: np.ndarray, in_zero_region: np.ndarray) -> HurdleMarginal:
        """Fit the hurdle marginal.

        `in_zero_region` is a boolean mask marking the CITED-zero observations
        (node-days at or below the elasticity threshold). p0 is estimated from
        that mask -- i.e. from the cited physical region -- rather than from a
        count of exact zeros in the smeared data, which would be 0 because the
        logit never returns exactly zero.
        """
        losses = np.asarray(losses, dtype=float)
        in_zero_region = np.asarray(in_zero_region, dtype=bool)
        if len(losses) != len(in_zero_region):
            raise ValueError("losses and in_zero_region must be the same length")

        p0 = float(in_zero_region.mean())
        positive = losses[~in_zero_region]
        if len(positive) < MIN_POSITIVE_LOSS_DAYS:
            raise ValueError(
                f"insufficient heat-exposure days: {len(positive)} < "
                f"{MIN_POSITIVE_LOSS_DAYS} minimum strictly-positive loss-days "
                f"-- state EXCLUDED from pricing (deliberate coverage boundary, "
                f"not a fittable state)")
        if np.any(positive <= 0):
            raise ValueError("positive part contains non-positive values")

        aics = {}
        for name, dist in POSITIVE_CANDIDATES.items():
            params = dist.fit(positive)
            aic, log_lik = _aic(dist, positive, params)
            aics[name] = {"aic": aic, "log_lik": log_lik,
                          "params": [float(p) for p in params], "k": len(params)}
        best = min(aics, key=lambda k: aics[k]["aic"])

        return cls(
            p0=p0,
            positive_dist=best,
            positive_params=tuple(aics[best]["params"]),
            n_zero=int(in_zero_region.sum()),
            n_positive=int((~in_zero_region).sum()),
            positive_aic=aics,
        )

    def cdf(self, x) -> np.ndarray:
        """F_L(x). Exactly p0 at x <= 0; p0 + (1-p0)*G(x) above."""
        x = np.asarray(x, dtype=float)
        g = self._dist.cdf(x, *self.positive_params)
        out = np.where(x <= 0.0, self.p0, self.p0 + (1.0 - self.p0) * g)
        return out if out.ndim else float(out)

    def cdf_left_limit(self, x) -> np.ndarray:
        """F_L(x-). Differs from cdf() ONLY at the atom, where it is 0.

        Needed for the distributional transform: the atom occupies the CDF
        interval [F(0-), F(0)] = [0, p0], and a pseudo-observation must be drawn
        uniformly across that interval rather than pinned to a single value.
        """
        x = np.asarray(x, dtype=float)
        g = self._dist.cdf(x, *self.positive_params)
        out = np.where(x <= 0.0, 0.0, self.p0 + (1.0 - self.p0) * g)
        return out if out.ndim else float(out)

    def ppf(self, q) -> np.ndarray:
        """Inverse CDF. q <= p0 maps to an exact zero -- the atom."""
        q = np.asarray(q, dtype=float)
        scaled = np.clip((q - self.p0) / (1.0 - self.p0), 0.0, 1.0)
        out = np.where(q <= self.p0, 0.0, self._dist.ppf(scaled, *self.positive_params))
        return out if out.ndim else float(out)

    def rvs(self, size: int, rng: np.random.Generator) -> np.ndarray:
        """Sample the hurdle correctly: exact zero w.p. p0, else the positive part."""
        out = np.zeros(size, dtype=float)
        positive_mask = rng.random(size) >= self.p0
        n_pos = int(positive_mask.sum())
        if n_pos:
            out[positive_mask] = self._dist.rvs(
                *self.positive_params, size=n_pos, random_state=rng)
        return out

    def to_dict(self) -> dict:
        return {
            "p0": self.p0,
            "positive_dist": self.positive_dist,
            "positive_params": [float(p) for p in self.positive_params],
            "n_zero_atom": self.n_zero,
            "n_positive": self.n_positive,
            "positive_dist_selected_by": "lower AIC",
            "positive_aic": {k: v["aic"] for k, v in self.positive_aic.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> HurdleMarginal:
        """Reconstruct from a to_dict() payload (e.g. copula.json's 'hurdle' block).

        This is the ONLY sanctioned way for the pricer to rebuild F_L from
        copula.json -- it guarantees the exact fitted p0/dist/params are used,
        so the Prompt-5 sampler cannot silently drift from the Prompt-4 fit.
        """
        if d["positive_dist"] not in POSITIVE_CANDIDATES:
            raise ValueError(f"unknown positive_dist {d['positive_dist']!r}")
        return cls(
            p0=float(d["p0"]),
            positive_dist=d["positive_dist"],
            positive_params=tuple(float(p) for p in d["positive_params"]),
            n_zero=int(d.get("n_zero_atom", 0)),
            n_positive=int(d.get("n_positive", 0)),
            positive_aic={},
        )


@dataclass
class NaiveMarginal:
    """Single-piece F_L, i.e. the marginal EXACTLY as Prompt 3 left it.

    Diagnostic only. This is what you get if you take wage_loss.parquet at face
    value and fit one continuous distribution to all of it, smeared floor
    included. Its only purpose is to measure how far the copula's theta moves
    between this and the hurdle -- that delta is the concrete, quantified cost
    of Prompt 3's smearing.
    """

    dist_name: str
    params: tuple
    aic: dict

    @property
    def _dist(self):
        return POSITIVE_CANDIDATES[self.dist_name]

    @classmethod
    def fit(cls, losses: np.ndarray) -> NaiveMarginal:
        losses = np.asarray(losses, dtype=float)
        aics = {}
        for name, dist in POSITIVE_CANDIDATES.items():
            params = dist.fit(losses)
            aic, log_lik = _aic(dist, losses, params)
            aics[name] = {"aic": aic, "params": [float(p) for p in params]}
        best = min(aics, key=lambda k: aics[k]["aic"])
        return cls(dist_name=best, params=tuple(aics[best]["params"]), aic=aics)

    def cdf(self, x) -> np.ndarray:
        return self._dist.cdf(np.asarray(x, dtype=float), *self.params)
