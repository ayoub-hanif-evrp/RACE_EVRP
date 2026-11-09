"""Shared actor-critic networks for parameter-shared MAPPO."""

from __future__ import annotations

import torch
import torch.nn as nn


class Actor(nn.Module):
    def __init__(self, obs_dim: int, n_actions: int, hidden: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
            nn.Linear(hidden, n_actions),
        )

    def forward(self, obs: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        logits = self.net(obs)
        # Mask invalid actions with large negative logits
        neg = torch.finfo(logits.dtype).min / 2
        logits = torch.where(mask > 0.5, logits, torch.full_like(logits, neg))
        return logits


class Critic(nn.Module):
    """Centralized critic: concatenates all agents' observations (training only)."""

    def __init__(self, global_obs_dim: int, hidden: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(global_obs_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
            nn.Linear(hidden, 1),
        )

    def forward(self, global_obs: torch.Tensor) -> torch.Tensor:
        return self.net(global_obs).squeeze(-1)
