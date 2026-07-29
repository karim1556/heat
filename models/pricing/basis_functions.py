"""Laguerre basis functions for the LSMC continuation-value regression.

Longstaff & Schwartz (2001) regress the continuation value on a small set of
basis functions of the state variable. Laguerre polynomials are their canonical
choice: they are orthogonal on [0, inf) under the weight e^{-x}, which suits a
non-negative state (here the mu-TEVI index).

The state is rescaled to [0, 1] (index / 100) BEFORE the polynomials are
applied. This matters and is not cosmetic: L_3(x) = 1 - 3x + 1.5x^2 - x^3/6, so
on a raw index of 0..100 the cubic term reaches ~-1.7e5 and the design matrix
becomes catastrophically ill-conditioned, swamping the Ridge fit. On [0, 1] all
terms stay O(1).
"""

from __future__ import annotations

import numpy as np

STATE_SCALE = 100.0  # mu-TEVI lives in [0, 100]; map to [0, 1] before the basis.


class LaguerreBasis:
    """Laguerre polynomials L_0..L_degree as an LSMC regression design matrix.

    Explicit closed forms (rather than a recurrence) up to degree 3, which is
    all Longstaff-Schwartz uses and all the DoD requires:

        L_0(x) = 1
        L_1(x) = 1 - x
        L_2(x) = 1 - 2x + x^2/2
        L_3(x) = 1 - 3x + 3x^2/2 - x^3/6
    """

    def __init__(self, degree: int = 3):
        if not 0 <= degree <= 3:
            raise ValueError(f"degree must be in 0..3 (explicit forms only), got {degree}")
        self.degree = degree

    @property
    def n_features(self) -> int:
        return self.degree + 1

    def transform(self, state: np.ndarray) -> np.ndarray:
        """state: (n,) mu-TEVI values in [0, 100] -> (n, degree+1) design matrix.

        L_0 (the constant column) is INCLUDED, so a downstream regressor should
        be fit WITHOUT its own intercept to avoid a rank-deficient duplicate.
        """
        x = np.asarray(state, dtype=float).reshape(-1) / STATE_SCALE
        columns = [np.ones_like(x)]
        if self.degree >= 1:
            columns.append(1.0 - x)
        if self.degree >= 2:
            columns.append(1.0 - 2.0 * x + x**2 / 2.0)
        if self.degree >= 3:
            columns.append(1.0 - 3.0 * x + 3.0 * x**2 / 2.0 - x**3 / 6.0)
        return np.column_stack(columns)
