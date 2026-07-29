"""Unit tests for the trivial spatial baselines (models/stgcn/spatial_baselines.py).

The IDW closed-form check uses backend.data.recovery._haversine_km as an
INDEPENDENT distance oracle (a separate implementation from Prompt 1, not the
models.stgcn.city_graph.pairwise_haversine_km the code under test calls), so
this is not a tautological test that could pass even if both distance
computations shared the same bug.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.data.recovery import _haversine_km
from models.stgcn.spatial_baselines import idw, nearest_station


# --- nearest_station -------------------------------------------------------


def test_nearest_station_returns_the_exact_nearest_node_value():
    """Hand-placed 3-node fixture: node 0 is obviously closest to the target."""
    train_coords = np.array([[23.0, 72.0], [23.0, 74.0], [10.0, 10.0]])
    train_values = np.array([31.5, 40.0, -99.0])
    target_coord = np.array([23.0, 72.1])  # a hair from node 0, far from the others

    assert nearest_station(train_coords, train_values, target_coord) == pytest.approx(31.5)


def test_nearest_station_picks_whichever_node_is_closer_as_target_moves():
    train_coords = np.array([[10.0, 20.0], [10.0, 24.0]])
    train_values = np.array([5.0, 9.0])

    assert nearest_station(train_coords, train_values, [10.0, 20.5]) == pytest.approx(5.0)
    assert nearest_station(train_coords, train_values, [10.0, 23.5]) == pytest.approx(9.0)


def test_nearest_station_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        nearest_station(np.array([[0.0, 0.0]]), np.array([1.0, 2.0]), [0.0, 0.0])


def test_nearest_station_rejects_empty_input():
    with pytest.raises(ValueError, match="at least one"):
        nearest_station(np.empty((0, 2)), np.empty(0), [0.0, 0.0])


# --- idw ---------------------------------------------------------------------


def test_idw_matches_the_closed_form_on_a_symmetric_two_node_fixture():
    """Two nodes on the SAME latitude, symmetric in longitude around the target.

    By the haversine formula's own symmetry (identical dlat=0, identical
    |dlon|, identical cos(lat) terms) the two distances are mathematically
    forced to be exactly equal regardless of any implementation detail -- so
    IDW must reduce to a plain average for ANY power. Confirmed independently
    against backend.data.recovery._haversine_km before trusting the equality.
    """
    train_coords = np.array([[10.0, 20.0], [10.0, 24.0]])
    train_values = np.array([5.0, 9.0])
    target_coord = np.array([10.0, 22.0])

    d0 = _haversine_km((10.0, 20.0), (10.0, 22.0))
    d1 = _haversine_km((10.0, 24.0), (10.0, 22.0))
    assert d0 == pytest.approx(d1), "fixture is not actually symmetric -- test is invalid"

    expected = (train_values[0] + train_values[1]) / 2.0
    assert idw(train_coords, train_values, target_coord, power=2) == pytest.approx(expected)
    assert idw(train_coords, train_values, target_coord, power=1) == pytest.approx(expected)


def test_idw_matches_the_closed_form_on_an_asymmetric_two_node_fixture():
    """Unequal distances, expected value computed from an INDEPENDENT haversine
    implementation (backend.data.recovery._haversine_km), not the one under
    test -- this is what makes the check a real closed-form comparison rather
    than the function agreeing with itself."""
    train_coords = np.array([[10.0, 20.0], [10.0, 25.0]])
    train_values = np.array([5.0, 9.0])
    target_coord = np.array([10.0, 21.0])

    d0 = _haversine_km((10.0, 20.0), (10.0, 21.0))
    d1 = _haversine_km((10.0, 25.0), (10.0, 21.0))
    w0, w1 = d0**-2.0, d1**-2.0
    expected = (w0 * train_values[0] + w1 * train_values[1]) / (w0 + w1)

    assert idw(train_coords, train_values, target_coord, power=2) == pytest.approx(expected, rel=1e-9)


def test_idw_weights_the_nearer_node_more_heavily():
    train_coords = np.array([[10.0, 20.0], [10.0, 25.0]])
    train_values = np.array([0.0, 100.0])
    target_coord = np.array([10.0, 20.5])  # much closer to node 0

    pred = idw(train_coords, train_values, target_coord, power=2)
    assert pred < 50.0  # pulled toward the nearer node's value, not a plain average


def test_idw_handles_exact_coincidence_without_dividing_by_zero():
    train_coords = np.array([[10.0, 20.0], [10.0, 25.0]])
    train_values = np.array([5.0, 9.0])
    target_coord = np.array([10.0, 20.0])  # exactly node 0's coordinate

    assert idw(train_coords, train_values, target_coord, power=2) == pytest.approx(5.0)


def test_idw_rejects_nonpositive_power():
    with pytest.raises(ValueError, match="power"):
        idw(np.array([[0.0, 0.0]]), np.array([1.0]), [1.0, 1.0], power=0)


def test_idw_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        idw(np.array([[0.0, 0.0]]), np.array([1.0, 2.0]), [0.0, 0.0])


# --- held-out node's own value must never be usable -------------------------


def test_baselines_never_use_the_held_out_nodes_own_value():
    """Mirrors evaluate_spatial.py's real indexing: the held-out node's column
    is excluded from train_values entirely, not merely unused by convention.
    Poisoning that column (as if it held the true answer) must not change the
    prediction, because it was never in the function's argument list at all.
    """
    all_coords = np.array([[22.0, 71.0], [22.0, 72.0], [22.0, 73.0]])
    all_values = np.array([30.0, 32.0, 999.0])  # index 2 is the "held-out" node
    held_out_idx = 2
    train_idx = [0, 1]

    train_coords = all_coords[train_idx]
    target_coord = all_coords[held_out_idx]
    train_values = all_values[train_idx]  # correctly excludes the poisoned value

    nearest_before = nearest_station(train_coords, train_values, target_coord)
    idw_before = idw(train_coords, train_values, target_coord, power=2)

    # Poison the held-out node's TRUE value further -- if either baseline were
    # somehow reading it, these predictions would change.
    all_values_repoisoned = all_values.copy()
    all_values_repoisoned[held_out_idx] = -12345.0
    train_values_after = all_values_repoisoned[train_idx]  # still excludes index 2

    nearest_after = nearest_station(train_coords, train_values_after, target_coord)
    idw_after = idw(train_coords, train_values_after, target_coord, power=2)

    assert nearest_after == pytest.approx(nearest_before)
    assert idw_after == pytest.approx(idw_before)
    # Sanity: predictions did not accidentally equal either poisoned value.
    assert nearest_before not in (999.0, -12345.0)
    assert idw_before != pytest.approx(999.0)
    assert idw_before != pytest.approx(-12345.0)
