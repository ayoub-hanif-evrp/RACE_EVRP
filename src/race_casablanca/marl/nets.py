"""Shared actor-critic networks for parameter-shared factorized MAPPO."""

from __future__ import annotations

import torch
import torch.nn as nn


def _mask_logits(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    neg = torch.finfo(logits.dtype).min / 2
    return torch.where(mask > 0.5, logits, torch.full_like(logits, neg))


class FactorizedActor(nn.Module):
    """Shared encoder with independent operational and communication heads."""

    def __init__(self, obs_dim: int, n_op: int, n_comm: int, hidden: int = 128):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(obs_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
        )
        self.op_head = nn.Linear(hidden, n_op)
        self.comm_head = nn.Linear(hidden, n_comm)

    def forward(
        self, obs: torch.Tensor, op_mask: torch.Tensor, comm_mask: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.encoder(obs)
        return _mask_logits(self.op_head(h), op_mask), _mask_logits(self.comm_head(h), comm_mask)


# Backward-compatible alias used by older smoke tests / scripts.
class Actor(FactorizedActor):
    def __init__(self, obs_dim: int, n_actions: int, hidden: int = 128, n_comm: int | None = None):
        # Legacy single-head callers pass n_actions; treat as operational only and add dummy comm.
        if n_comm is None:
            n_comm = 2
        super().__init__(obs_dim, n_actions, n_comm, hidden=hidden)

    def forward(self, obs: torch.Tensor, mask: torch.Tensor, comm_mask: torch.Tensor | None = None):
        if comm_mask is None:
            # Legacy: return only operational logits
            h = self.encoder(obs)
            return _mask_logits(self.op_head(h), mask)
        return FactorizedActor.forward(self, obs, mask, comm_mask)


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
