"""STGCN layers in plain torch (no torch-geometric).

Tensor convention throughout: x is (B, T, N, C) -- batch, timestep, node,
channel. N never appears in any parameter shape, which is what makes the model
inductive: the same weights run on a graph of a different size.
"""

from __future__ import annotations

import math

import torch
from torch import nn


class ChebConvBlock(nn.Module):
    """Chebyshev spectral graph convolution, order K, computed directly.

        conv(x) = sum_{k=0}^{K-1} T_k @ x @ theta_k + b

    where {T_k} is the dense Chebyshev basis of the rescaled Laplacian. The
    basis is passed to forward() rather than baked in as a buffer, so one set
    of weights can be trained on a subgraph and evaluated on the full graph
    (the strict inductive spatial split). theta has shape (K, C_in, C_out) --
    no dependence on the node count.
    """

    def __init__(self, c_in: int, c_out: int, k_order: int = 3):
        super().__init__()
        if k_order < 1:
            raise ValueError(f"k_order must be >= 1, got {k_order}")
        self.c_in = c_in
        self.c_out = c_out
        self.k_order = k_order
        self.theta = nn.Parameter(torch.empty(k_order, c_in, c_out))
        self.bias = nn.Parameter(torch.zeros(c_out))
        self.reset_parameters()

    def reset_parameters(self) -> None:
        # Glorot with the Chebyshev fan-in: each output channel sums over K
        # basis terms x C_in input channels.
        fan_in = self.k_order * self.c_in
        bound = math.sqrt(6.0 / (fan_in + self.c_out))
        nn.init.uniform_(self.theta, -bound, bound)
        nn.init.zeros_(self.bias)

    def forward(self, x: torch.Tensor, cheb_basis: torch.Tensor) -> torch.Tensor:
        """x: (B, T, N, C_in), cheb_basis: (K, N, N) -> (B, T, N, C_out)."""
        if cheb_basis.shape[0] != self.k_order:
            raise ValueError(
                f"basis has K={cheb_basis.shape[0]} but layer was built for K={self.k_order}"
            )
        if x.shape[2] != cheb_basis.shape[1]:
            raise ValueError(
                f"node-count mismatch: x has N={x.shape[2]}, basis has N={cheb_basis.shape[1]}"
            )
        # Literal transcription of sum_k T_k @ x @ theta_k.
        out = torch.einsum("kij,btjc,kco->btio", cheb_basis, x, self.theta)
        return out + self.bias


class TemporalGatedConv(nn.Module):
    """Gated 1-D causal-width temporal convolution (GLU).

    Conv1d maps C_in -> 2*C_out along time; the halves are split into P and Q
    and combined as P * sigmoid(Q). No padding, so each layer shortens the time
    axis by (kernel_size - 1) -- the caller must budget for that.
    """

    def __init__(self, c_in: int, c_out: int, kernel_size: int = 3):
        super().__init__()
        self.c_out = c_out
        self.kernel_size = kernel_size
        self.conv = nn.Conv1d(c_in, 2 * c_out, kernel_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, T, N, C_in) -> (B, T - kernel_size + 1, N, C_out)."""
        b, t, n, _ = x.shape
        if t < self.kernel_size:
            raise ValueError(f"time dim {t} is shorter than kernel {self.kernel_size}")
        # (B,T,N,C) -> (B,N,C,T) -> fold nodes into the batch so Conv1d slides
        # over time only, independently per node.
        h = x.permute(0, 2, 3, 1).reshape(b * n, -1, t)
        h = self.conv(h)
        p, q = torch.split(h, self.c_out, dim=1)
        h = p * torch.sigmoid(q)
        t_out = h.shape[-1]
        return h.view(b, n, self.c_out, t_out).permute(0, 3, 1, 2)
