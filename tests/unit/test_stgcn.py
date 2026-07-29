"""Unit tests for the STGCN heat map.

The Chebyshev tests use a separate 3-node toy graph whose basis is computable
by hand in closed form, so the recursion is checked against arithmetic rather
than against itself.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch

from models.stgcn.city_graph import (
    CityGraphBuilder,
    chebyshev_basis,
    normalized_laplacian,
    pairwise_haversine_km,
    rescale_laplacian,
)
from models.stgcn.layers import ChebConvBlock, TemporalGatedConv
from models.stgcn.model import STGCN
from models.stgcn.train import HORIZON, K_ORDER, T_IN, WEATHER_PARQUET

WAGE_LOSS_PARQUET = Path("data/processed/wage_loss.parquet")

# --- Toy fixture: 3-node path graph 0 -- 1 -- 2 --------------------------
#
# Hand computation (verified independently):
#   W    = [[0,1,0],[1,0,1],[0,1,0]],  D = diag(1,2,1)
#   L    = I - D^-1/2 W D^-1/2 = [[1,-r,0],[-r,1,-r],[0,-r,1]], r = 1/sqrt(2)
#   The path on 3 nodes is bipartite ({0,2} | {1}), so a connected bipartite
#   graph's normalized Laplacian has spectrum {0, 1, 2} and lambda_max = 2
#   EXACTLY. Hence L_tilde = (2/2)L - I = L - I.
#   T_0 = I
#   T_1 = L_tilde                     = [[0,-r,0],[-r,0,-r],[0,-r,0]]
#   T_2 = 2 L_tilde^2 - I
#         L_tilde^2 = [[.5,0,.5],[0,1,0],[.5,0,.5]]
#         => T_2     = [[0,0,1],[0,1,0],[1,0,0]]   (exact integers)
TOY_W = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
_R = 1.0 / math.sqrt(2.0)
EXPECTED_T0 = np.eye(3)
EXPECTED_T1 = np.array([[0.0, -_R, 0.0], [-_R, 0.0, -_R], [0.0, -_R, 0.0]])
EXPECTED_T2 = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]])


@pytest.fixture(scope="module")
def toy_basis() -> np.ndarray:
    lap = normalized_laplacian(TOY_W)
    l_tilde, lambda_max = rescale_laplacian(lap)
    assert lambda_max == pytest.approx(2.0), "path-on-3 is bipartite -> lambda_max is exactly 2"
    return chebyshev_basis(l_tilde, K_ORDER)


@pytest.fixture(scope="module")
def real_node_ids() -> list[str]:
    """Node ids read FROM THE DATA -- n is never hardcoded in these tests."""
    if WEATHER_PARQUET.exists():
        df = pd.read_parquet(WEATHER_PARQUET, columns=["node_id"])
    elif WAGE_LOSS_PARQUET.exists():
        df = pd.read_parquet(WAGE_LOSS_PARQUET, columns=["node_id"])
    else:
        pytest.skip(
            f"no real node data at {WEATHER_PARQUET} or {WAGE_LOSS_PARQUET}; "
            f"run `python -m models.stgcn.train` first"
        )
    return sorted({str(v) for v in df["node_id"]})


# --- Chebyshev recursion -------------------------------------------------


def test_toy_chebyshev_matches_hand_computed_values(toy_basis):
    assert toy_basis.shape == (K_ORDER, 3, 3)
    np.testing.assert_allclose(toy_basis[0], EXPECTED_T0, atol=1e-12)
    np.testing.assert_allclose(toy_basis[1], EXPECTED_T1, atol=1e-12)
    np.testing.assert_allclose(toy_basis[2], EXPECTED_T2, atol=1e-12)


def test_toy_chebyshev_satisfies_the_recursion(toy_basis):
    """T_k = 2 L_tilde T_{k-1} - T_{k-2}, checked term by term."""
    l_tilde = toy_basis[1]
    for k in range(2, K_ORDER):
        np.testing.assert_allclose(
            toy_basis[k], 2.0 * l_tilde @ toy_basis[k - 1] - toy_basis[k - 2], atol=1e-12
        )


def test_rescaled_laplacian_spectrum_is_within_unit_interval(toy_basis):
    eigs = np.linalg.eigvalsh(toy_basis[1])
    assert eigs.min() >= -1.0 - 1e-9
    assert eigs.max() <= 1.0 + 1e-9


def test_real_graph_spectrum_is_within_unit_interval(real_node_ids):
    graph = CityGraphBuilder.from_node_ids(real_node_ids).build(k_order=K_ORDER)
    eigs = np.linalg.eigvalsh(graph.l_tilde)
    assert eigs.min() >= -1.0 - 1e-9
    assert eigs.max() <= 1.0 + 1e-9
    np.testing.assert_allclose(graph.cheb_basis[0], np.eye(graph.n_nodes), atol=1e-12)


# --- Graph construction --------------------------------------------------


def test_adjacency_is_symmetric_with_zero_diagonal(real_node_ids):
    graph = CityGraphBuilder.from_node_ids(real_node_ids).build(k_order=K_ORDER)
    np.testing.assert_allclose(graph.adjacency, graph.adjacency.T, atol=1e-12)
    np.testing.assert_allclose(np.diag(graph.adjacency), 0.0, atol=1e-12)
    assert (graph.adjacency.sum(axis=1) > 0).all(), "every real node must have a neighbour"


def test_haversine_is_symmetric_and_zero_on_the_diagonal():
    coords = np.array([[23.0, 72.5], [22.0, 71.875], [24.0, 73.125]])
    dist = pairwise_haversine_km(coords)
    np.testing.assert_allclose(dist, dist.T, atol=1e-9)
    np.testing.assert_allclose(np.diag(dist), 0.0, atol=1e-9)
    # ~1 degree of latitude is ~111 km.
    assert 100.0 < dist[0, 1] < 200.0


def test_node_count_is_read_from_data_not_hardcoded(real_node_ids):
    builder = CityGraphBuilder.from_node_ids(real_node_ids)
    graph = builder.build(k_order=K_ORDER)
    assert graph.n_nodes == len(real_node_ids)
    assert graph.cheb_basis.shape == (K_ORDER, len(real_node_ids), len(real_node_ids))


def test_subgraph_excludes_held_out_nodes(real_node_ids):
    """The inductive split must physically remove held-out nodes from the graph."""
    builder = CityGraphBuilder.from_node_ids(real_node_ids)
    keep = np.arange(len(real_node_ids))[:-3]
    sub = builder.subgraph(keep, k_order=K_ORDER)
    assert sub.n_nodes == len(keep)
    assert set(sub.node_ids).isdisjoint({real_node_ids[i] for i in range(len(real_node_ids))[-3:]})


# --- Model ---------------------------------------------------------------


def test_forward_output_shape_is_n_real_nodes_by_horizon(real_node_ids):
    n_nodes = len(real_node_ids)
    graph = CityGraphBuilder.from_node_ids(real_node_ids).build(k_order=K_ORDER)
    basis = torch.from_numpy(graph.cheb_basis).float()

    model = STGCN(in_channels=1, hidden=16, horizon=HORIZON, t_in=T_IN, k_order=K_ORDER)
    out = model(torch.randn(1, T_IN, n_nodes, 1), basis)
    assert out.squeeze(0).shape == (n_nodes, HORIZON)

    batched = model(torch.randn(4, T_IN, n_nodes, 1), basis)
    assert batched.shape == (4, n_nodes, HORIZON)


def test_random_forward_pass_runs_under_five_seconds(real_node_ids):
    n_nodes = len(real_node_ids)
    graph = CityGraphBuilder.from_node_ids(real_node_ids).build(k_order=K_ORDER)
    basis = torch.from_numpy(graph.cheb_basis).float()
    model = STGCN(in_channels=1, hidden=16, horizon=HORIZON, t_in=T_IN, k_order=K_ORDER)
    x = torch.randn(32, T_IN, n_nodes, 1)

    started = time.perf_counter()
    with torch.no_grad():
        model(x, basis)
    assert time.perf_counter() - started < 5.0


def test_model_has_no_node_count_dependent_parameters(real_node_ids):
    """Weights trained on the subgraph must run on the full graph unchanged.

    This is what makes the strict inductive spatial split possible.
    """
    n_nodes = len(real_node_ids)
    builder = CityGraphBuilder.from_node_ids(real_node_ids)
    full = builder.build(k_order=K_ORDER)
    sub = builder.subgraph(np.arange(n_nodes)[:-3], k_order=K_ORDER)

    model = STGCN(in_channels=1, hidden=16, horizon=HORIZON, t_in=T_IN, k_order=K_ORDER)
    with torch.no_grad():
        out_sub = model(torch.randn(2, T_IN, sub.n_nodes, 1),
                        torch.from_numpy(sub.cheb_basis).float())
        out_full = model(torch.randn(2, T_IN, full.n_nodes, 1),
                         torch.from_numpy(full.cheb_basis).float())
    assert out_sub.shape == (2, sub.n_nodes, HORIZON)
    assert out_full.shape == (2, full.n_nodes, HORIZON)


# --- Layers --------------------------------------------------------------


def test_temporal_gated_conv_shortens_time_by_kernel_minus_one():
    conv = TemporalGatedConv(c_in=1, c_out=16, kernel_size=3)
    out = conv(torch.randn(2, T_IN, 5, 1))
    assert out.shape == (2, T_IN - 2, 5, 16)


def test_temporal_gated_conv_gate_is_a_sigmoid_product():
    """out = P * sigmoid(Q) on the split halves of the Conv1d output."""
    torch.manual_seed(42)
    conv = TemporalGatedConv(c_in=2, c_out=3, kernel_size=3)
    x = torch.randn(2, 8, 4, 2)

    b, t, n, c = x.shape
    raw = conv.conv(x.permute(0, 2, 3, 1).reshape(b * n, c, t))
    p, q = torch.split(raw, conv.c_out, dim=1)
    expected = (p * torch.sigmoid(q)).view(b, n, conv.c_out, -1).permute(0, 3, 1, 2)
    torch.testing.assert_close(conv(x), expected)


def test_cheb_conv_equals_the_explicit_sum_over_k(toy_basis):
    """conv = sum_k T_k @ x @ theta_k, checked against an explicit loop."""
    torch.manual_seed(42)
    layer = ChebConvBlock(c_in=2, c_out=3, k_order=K_ORDER)
    basis = torch.from_numpy(toy_basis).float()
    x = torch.randn(2, 4, 3, 2)  # (B, T, N=3, C_in)

    expected = torch.zeros(2, 4, 3, 3)
    for k in range(K_ORDER):
        expected = expected + torch.matmul(basis[k], x) @ layer.theta[k]
    expected = expected + layer.bias

    torch.testing.assert_close(layer(x, basis), expected)


def test_cheb_conv_with_identity_basis_is_a_pointwise_linear_map():
    """With K=1 the basis is just T_0 = I, so the graph conv must reduce to a
    per-node linear layer -- a clean sanity check that T_0 is really I."""
    torch.manual_seed(42)
    layer = ChebConvBlock(c_in=2, c_out=3, k_order=1)
    identity = torch.eye(3).unsqueeze(0)
    x = torch.randn(2, 4, 3, 2)
    torch.testing.assert_close(layer(x, identity), x @ layer.theta[0] + layer.bias)


def test_cheb_conv_rejects_a_basis_of_the_wrong_order(toy_basis):
    layer = ChebConvBlock(c_in=2, c_out=3, k_order=K_ORDER)
    with pytest.raises(ValueError, match="K="):
        layer(torch.randn(1, 4, 3, 2), torch.from_numpy(toy_basis[:2]).float())


# --- Guards --------------------------------------------------------------


def test_isolated_node_raises_rather_than_silently_filling():
    w = np.zeros((3, 3))
    w[0, 1] = w[1, 0] = 1.0  # node 2 is isolated -> zero degree
    with pytest.raises(ValueError, match="isolated node"):
        normalized_laplacian(w)


def test_too_short_history_is_rejected():
    with pytest.raises(ValueError, match="too short"):
        STGCN(t_in=8, k_order=K_ORDER, kernel_size=3)
