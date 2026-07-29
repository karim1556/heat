"""Trivial spatial baselines for the STGCN's actual job: interpolating heat to
an unseen LOCATION, using only other nodes at the SAME timestep -- no temporal
information at all.

This exists because the STGCN's headline number so far (models/stgcn/train.py)
is benchmarked against TEMPORAL baselines (historical mean, persistence), which
say nothing about whether the graph convolution is doing useful spatial work.
A model that just memorizes each node's climatology can beat a historical-mean
baseline while still losing badly to a naive geographic interpolation at a
truly new location. These two baselines are that honest comparison.

Both use the exact haversine metric already used to build the STGCN's kNN graph
(models.stgcn.city_graph.pairwise_haversine_km) rather than a re-derived
distance formula, so "nearest" here means the same thing it means to the graph.
"""

from __future__ import annotations

import numpy as np

from models.stgcn.city_graph import pairwise_haversine_km


def _distances_to_target(train_coords: np.ndarray, target_coord: np.ndarray) -> np.ndarray:
    """Haversine distance (km) from `target_coord` to each row of `train_coords`.

    Implemented by appending the target as one extra row and reusing the exact
    same pairwise haversine matrix the graph builder uses, rather than a
    separately written point-to-many formula that could silently drift from it.
    """
    train_coords = np.asarray(train_coords, dtype=np.float64)
    target_coord = np.asarray(target_coord, dtype=np.float64).reshape(1, 2)
    combined = np.vstack([train_coords, target_coord])
    dist_matrix = pairwise_haversine_km(combined)
    return dist_matrix[-1, :-1]


def nearest_station(train_coords: np.ndarray, train_values: np.ndarray,
                    target_coord: np.ndarray) -> float:
    """Copy the geographically nearest training node's reading.

    Uses ONLY `train_coords`/`train_values` (never anything about the target's
    own true value -- the function has no argument through which that could
    even be passed) and ONLY the current timestep's readings, matching the
    inductive spatial-split protocol.
    """
    train_values = np.asarray(train_values, dtype=np.float64)
    if len(train_coords) != len(train_values):
        raise ValueError("train_coords and train_values must be the same length")
    if len(train_values) == 0:
        raise ValueError("need at least one training node")
    dists = _distances_to_target(train_coords, target_coord)
    return float(train_values[int(np.argmin(dists))])


def idw(train_coords: np.ndarray, train_values: np.ndarray, target_coord: np.ndarray,
       power: float = 2) -> float:
    """Inverse-distance-weighted average of the training nodes' readings.

        w_i = d_i^{-power} / sum_j d_j^{-power}
        pred = sum_i w_i * value_i

    If the target coincides exactly with a training coordinate (distance 0,
    only possible in a degenerate/test fixture -- real held-out nodes are never
    at a training node's exact location), that node's own value is returned
    directly rather than dividing by zero.
    """
    train_values = np.asarray(train_values, dtype=np.float64)
    if len(train_coords) != len(train_values):
        raise ValueError("train_coords and train_values must be the same length")
    if len(train_values) == 0:
        raise ValueError("need at least one training node")
    if power <= 0:
        raise ValueError(f"power must be > 0, got {power}")

    dists = _distances_to_target(train_coords, target_coord)
    zero = dists == 0.0
    if np.any(zero):
        return float(train_values[int(np.argmax(zero))])

    weights = dists ** (-power)
    weights = weights / weights.sum()
    return float(np.dot(weights, train_values))
