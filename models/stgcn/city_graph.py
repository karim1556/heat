"""City graph construction from REAL NASA POWER node coordinates.

Pipeline: real node coords -> geographic k-nearest-neighbour adjacency ->
symmetric normalized Laplacian -> Chebyshev rescaling of the spectrum to
[-1, 1] -> dense Chebyshev basis {T_0..T_{K-1}}.

Node count is ALWAYS read from the data (len of the supplied coords); it is
never hardcoded anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

EARTH_RADIUS_KM = 6371.0


def pairwise_haversine_km(coords: np.ndarray) -> np.ndarray:
    """Great-circle distance between every pair of (lat, lon) degree rows.

    coords: (N, 2) -> (N, N) km. Uses haversine (not Euclidean degrees) so the
    graph is geographic: a degree of longitude is shorter than a degree of
    latitude at 23N, and the adjacency must respect that.
    """
    lat = np.radians(coords[:, 0])[:, None]
    lon = np.radians(coords[:, 1])[:, None]
    dlat = lat - lat.T
    dlon = lon - lon.T
    h = np.sin(dlat / 2.0) ** 2 + np.cos(lat) * np.cos(lat.T) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


def knn_adjacency(dist_km: np.ndarray, k: int) -> np.ndarray:
    """Symmetric k-nearest-neighbour adjacency with a Gaussian kernel.

    W_ij = exp(-d_ij^2 / sigma^2) if j is among i's k nearest, else 0, then
    symmetrized via W = max(W, W^T). sigma is the mean kNN distance, so the
    kernel width is data-driven rather than a magic constant (Yu et al. 2018
    use the same thresholded-Gaussian form).
    """
    n = dist_km.shape[0]
    if not 1 <= k < n:
        raise ValueError(f"k must satisfy 1 <= k < n_nodes ({n}), got {k}")

    d = dist_km.copy()
    np.fill_diagonal(d, np.inf)
    nearest = np.argsort(d, axis=1, kind="stable")[:, :k]
    sigma = float(np.take_along_axis(d, nearest, axis=1).mean())
    if sigma <= 0.0:
        raise ValueError("degenerate graph: all nodes are co-located")

    w = np.zeros((n, n), dtype=np.float64)
    rows = np.repeat(np.arange(n), k)
    cols = nearest.reshape(-1)
    w[rows, cols] = np.exp(-(d[rows, cols] ** 2) / (sigma**2))
    w = np.maximum(w, w.T)
    np.fill_diagonal(w, 0.0)
    return w


def normalized_laplacian(w: np.ndarray) -> np.ndarray:
    """L = I - D^{-1/2} W D^{-1/2}. Symmetric, spectrum in [0, 2]."""
    deg = w.sum(axis=1)
    if np.any(deg <= 0.0):
        raise ValueError("isolated node: D^{-1/2} undefined (zero degree)")
    dinv = 1.0 / np.sqrt(deg)
    return np.eye(len(w)) - (w * dinv[:, None] * dinv[None, :])


def rescale_laplacian(lap: np.ndarray, lambda_max: float | None = None) -> tuple[np.ndarray, float]:
    """L_tilde = (2/lambda_max) L - I, mapping the spectrum onto [-1, 1].

    lambda_max is computed EXACTLY via eigvalsh rather than using the common
    lambda_max ~= 2 approximation. The graph is small (tens of nodes), the
    eigendecomposition is free, and an exact rescaling is what guarantees the
    Chebyshev basis is evaluated on its domain of orthogonality [-1, 1].
    """
    if lambda_max is None:
        lambda_max = float(np.linalg.eigvalsh(lap)[-1])
    if lambda_max <= 1e-8:
        raise ValueError(f"lambda_max={lambda_max} is degenerate (empty graph?)")
    return (2.0 / lambda_max) * lap - np.eye(len(lap)), lambda_max


def chebyshev_basis(l_tilde: np.ndarray, k_order: int) -> np.ndarray:
    """Dense Chebyshev basis via the recursion, stacked as (K, N, N).

        T_0 = I
        T_1 = L_tilde
        T_k = 2 L_tilde T_{k-1} - T_{k-2}
    """
    if k_order < 1:
        raise ValueError(f"k_order must be >= 1, got {k_order}")
    n = l_tilde.shape[0]
    terms = [np.eye(n)]
    if k_order > 1:
        terms.append(l_tilde.copy())
    for _ in range(2, k_order):
        terms.append(2.0 * l_tilde @ terms[-1] - terms[-2])
    return np.stack(terms[:k_order])


@dataclass(frozen=True)
class CityGraph:
    node_ids: list[str]
    coords: np.ndarray
    adjacency: np.ndarray
    laplacian: np.ndarray
    l_tilde: np.ndarray
    lambda_max: float
    cheb_basis: np.ndarray

    @property
    def n_nodes(self) -> int:
        return len(self.node_ids)


class CityGraphBuilder:
    """Builds a CityGraph from real POWER grid nodes.

    The node set is whatever the data contains -- `n_nodes` is derived from the
    supplied coordinates and is never assumed.
    """

    def __init__(self, coords: pd.DataFrame, k: int = 4):
        for col in ("node_id", "lat", "lon"):
            if col not in coords.columns:
                raise ValueError(f"coords is missing required column {col!r}")
        self.node_ids = [str(v) for v in coords["node_id"].tolist()]
        self.coords = coords[["lat", "lon"]].to_numpy(dtype=np.float64)
        self.n_nodes = len(self.node_ids)
        if self.n_nodes < 2:
            raise ValueError(f"need >= 2 real nodes to build a graph, got {self.n_nodes}")
        self.k = min(k, self.n_nodes - 1)

    @classmethod
    def from_node_ids(cls, node_ids: list[str], k: int = 4) -> CityGraphBuilder:
        """Parse coords out of POWER node_ids of the form '<lat>_<lon>'.

        Matches backend.data.weather._node_id, which is the single source of
        truth for both lat and lon.
        """
        rows = []
        for node_id in node_ids:
            lat_str, lon_str = str(node_id).split("_")
            rows.append({"node_id": str(node_id), "lat": float(lat_str), "lon": float(lon_str)})
        return cls(pd.DataFrame(rows), k=k)

    def build(self, k_order: int = 3) -> CityGraph:
        dist = pairwise_haversine_km(self.coords)
        adjacency = knn_adjacency(dist, self.k)
        lap = normalized_laplacian(adjacency)
        l_tilde, lambda_max = rescale_laplacian(lap)
        return CityGraph(
            node_ids=list(self.node_ids),
            coords=self.coords.copy(),
            adjacency=adjacency,
            laplacian=lap,
            l_tilde=l_tilde,
            lambda_max=lambda_max,
            cheb_basis=chebyshev_basis(l_tilde, k_order),
        )

    def subgraph(self, node_positions: np.ndarray, k_order: int = 3) -> CityGraph:
        """Rebuild the graph over a SUBSET of nodes (kNN recomputed within it).

        Used for the strict inductive spatial split: the model is trained on a
        graph that does not contain the held-out locations at all.
        """
        sub = pd.DataFrame({
            "node_id": [self.node_ids[i] for i in node_positions],
            "lat": self.coords[node_positions, 0],
            "lon": self.coords[node_positions, 1],
        })
        return CityGraphBuilder(sub, k=self.k).build(k_order=k_order)
