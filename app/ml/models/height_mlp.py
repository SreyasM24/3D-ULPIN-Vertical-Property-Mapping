"""
Compact Tabular Neural Network for Building Height Regression.
Maps geometric footprint morphology and terrain elevation to estimated height (m).
Uses BatchNorm, ReLU, Dropout, and Softplus for strictly positive metric outputs.
"""

import torch
import torch.nn as nn


class HeightRegressorMLP(nn.Module):
    """
    Lightweight Tabular Neural Network for Cadastral Height Intelligence.
    Parameters: ~5,200 float32 weights for sub-millisecond CPU inference.
    """

    def __init__(self, in_features: int = 7):
        super().__init__()
        self.in_features = in_features
        self.net = nn.Sequential(
            nn.Linear(in_features, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Softplus()  # Guarantees physically valid positive height > 0
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)
