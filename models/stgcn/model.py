"""STGCN: 2 spatio-temporal blocks, hidden 16 (Yu, Yin & Zhu 2018, arXiv:1709.04875).

Each ST block is temporal -> spatial (Chebyshev) -> temporal ("sandwich"), so
the graph convolution is bracketed by gated temporal convolutions.

The model carries NO node-count-dependent parameters: the Chebyshev basis is an
argument to forward(). Train it on a 12-node subgraph and evaluate it on the
full 15-node graph with the same weights.
"""

from __future__ import annotations

import torch
from torch import nn

from models.stgcn.layers import ChebConvBlock, TemporalGatedConv


class STConvBlock(nn.Module):
    """temporal -> ChebConv -> ReLU -> temporal -> LayerNorm(channels).

    Shortens the time axis by 2*(kernel_size - 1).
    """

    def __init__(self, c_in: int, c_hidden: int, c_out: int, k_order: int = 3,
                 kernel_size: int = 3):
        super().__init__()
        self.temporal_in = TemporalGatedConv(c_in, c_hidden, kernel_size)
        self.cheb = ChebConvBlock(c_hidden, c_hidden, k_order)
        self.temporal_out = TemporalGatedConv(c_hidden, c_out, kernel_size)
        # Normalizes over channels only -> independent of the node count.
        self.norm = nn.LayerNorm(c_out)

    def forward(self, x: torch.Tensor, cheb_basis: torch.Tensor) -> torch.Tensor:
        h = self.temporal_in(x)
        h = torch.relu(self.cheb(h, cheb_basis))
        h = self.temporal_out(h)
        return self.norm(h)


class STGCN(nn.Module):
    """(B, T_in, N, C_in) -> (B, N, horizon).

    Time budget with kernel_size=3: each ST block costs 2*(3-1)=4 steps, two
    blocks cost 8, leaving t_rem = t_in - 8, which the head collapses to 1.
    """

    def __init__(self, in_channels: int = 1, hidden: int = 16, horizon: int = 3,
                 t_in: int = 12, k_order: int = 3, kernel_size: int = 3):
        super().__init__()
        self.t_in = t_in
        self.horizon = horizon
        self.k_order = k_order

        self.block1 = STConvBlock(in_channels, hidden, hidden, k_order, kernel_size)
        self.block2 = STConvBlock(hidden, hidden, hidden, k_order, kernel_size)

        t_rem = t_in - 4 * (kernel_size - 1)
        if t_rem < 1:
            raise ValueError(
                f"t_in={t_in} is too short for 2 ST blocks with kernel {kernel_size}: "
                f"needs t_in >= {4 * (kernel_size - 1) + 1}"
            )
        self.t_rem = t_rem
        # Collapse the surviving time steps to one, then map channels -> horizon.
        self.head_temporal = TemporalGatedConv(hidden, hidden, t_rem)
        self.head = nn.Linear(hidden, horizon)

    def forward(self, x: torch.Tensor, cheb_basis: torch.Tensor) -> torch.Tensor:
        if x.shape[1] != self.t_in:
            raise ValueError(f"expected t_in={self.t_in} timesteps, got {x.shape[1]}")
        h = self.block1(x, cheb_basis)
        h = self.block2(h, cheb_basis)
        h = self.head_temporal(h)  # (B, 1, N, hidden)
        h = h.squeeze(1)           # (B, N, hidden)
        return self.head(h)        # (B, N, horizon)
