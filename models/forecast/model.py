"""Small GRU forecaster for the mu-TEVI city index (Prompt 8).

<50k params by construction: a single-layer GRU (hidden=64, input=1) followed
by a linear head mapping the final hidden state directly to a HORIZON-length
vector of future mu-TEVI values (days t+1 .. t+HORIZON). No node dimension
here -- mu_tevi.parquet is already the city-AGGREGATED daily index (see
models.fusion.tevi), so this is a plain univariate sequence model.
"""

from __future__ import annotations

import torch
from torch import nn


class GRUForecaster(nn.Module):
    """(B, T_in, input_size) -> (B, horizon)."""

    def __init__(self, input_size: int = 1, hidden: int = 64, horizon: int = 7,
                 num_layers: int = 1):
        super().__init__()
        self.horizon = horizon
        self.gru = nn.GRU(input_size=input_size, hidden_size=hidden,
                          num_layers=num_layers, batch_first=True)
        self.head = nn.Linear(hidden, horizon)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, h_n = self.gru(x)
        h_last = h_n[-1]  # (B, hidden) -- final layer's last hidden state.
        return self.head(h_last)
