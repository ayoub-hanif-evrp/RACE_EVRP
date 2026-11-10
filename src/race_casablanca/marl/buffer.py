"""Time-indexed multi-agent rollout buffer for MAPPO (Yu et al. 2022 style).

Fleet transitions are stored as synchronized time steps. GAE runs along TIME only;
the shared team advantage is broadcast to simultaneous agent decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import torch


def compute_gae_time(
    rewards: np.ndarray,
    values: np.ndarray,
    dones: np.ndarray,
    truncs: np.ndarray,
    last_value: float,
    *,
    gamma: float = 0.99,
    lam: float = 0.95,
    elapsed: np.ndarray | None = None,
    dt_ref: float = 60.0,
) -> tuple[np.ndarray, np.ndarray]:
    """GAE along the time axis only.

    Parameters
    ----------
    rewards, values, dones, truncs : shape (T,)
        ``dones[t]=1`` means the episode ended after step t (no bootstrap).
        ``truncs[t]=1`` means the rollout was cut while the episode continues;
        bootstrap with ``last_value`` / next value is still valid when not done.
    last_value : bootstrap value after the final stored step (0 if episode ended).
    elapsed : optional wall-clock seconds per transition for time-aware discount.
    """

    rewards = np.asarray(rewards, dtype=np.float32)
    values = np.asarray(values, dtype=np.float32)
    dones = np.asarray(dones, dtype=np.float32)
    truncs = np.asarray(truncs, dtype=np.float32)
    T = len(rewards)
    adv = np.zeros(T, dtype=np.float32)
    gae = 0.0
    for t in reversed(range(T)):
        if t == T - 1:
            next_v = float(last_value)
        else:
            next_v = float(values[t + 1])
        # Episode termination: do not bootstrap. Truncation: bootstrap is allowed.
        cont = 1.0 - float(dones[t])
        if elapsed is not None:
            dt = max(float(elapsed[t]), 0.0)
            gamma_t = float(gamma) ** (dt / float(dt_ref))
        else:
            gamma_t = float(gamma)
        delta = float(rewards[t]) + gamma_t * next_v * cont - float(values[t])
        gae = delta + gamma_t * float(lam) * cont * gae
        adv[t] = gae
    ret = adv + values
    return adv, ret


@dataclass
class FleetRolloutBuffer:
    """Stores synchronized fleet transitions: one row per decision time."""

    obs: list = field(default_factory=list)  # [T] of (n_agents, obs_dim)
    global_obs: list = field(default_factory=list)  # [T] of (n_agents*obs_dim,)
    op_actions: list = field(default_factory=list)  # [T] of (n_agents,)
    comm_actions: list = field(default_factory=list)
    op_logprobs: list = field(default_factory=list)
    comm_logprobs: list = field(default_factory=list)
    rewards: list = field(default_factory=list)  # [T] team reward
    dones: list = field(default_factory=list)
    truncs: list = field(default_factory=list)
    values: list = field(default_factory=list)  # [T] team value
    op_masks: list = field(default_factory=list)
    comm_masks: list = field(default_factory=list)
    elapsed: list = field(default_factory=list)

    def add(
        self,
        obs,
        global_obs,
        op_actions,
        comm_actions,
        op_logprobs,
        comm_logprobs,
        reward,
        done,
        trunc,
        value,
        op_masks,
        comm_masks,
        elapsed: float = 1.0,
    ):
        self.obs.append(np.asarray(obs, dtype=np.float32))
        self.global_obs.append(np.asarray(global_obs, dtype=np.float32))
        self.op_actions.append(np.asarray(op_actions, dtype=np.int64))
        self.comm_actions.append(np.asarray(comm_actions, dtype=np.int64))
        self.op_logprobs.append(np.asarray(op_logprobs, dtype=np.float32))
        self.comm_logprobs.append(np.asarray(comm_logprobs, dtype=np.float32))
        self.rewards.append(float(reward))
        self.dones.append(float(done))
        self.truncs.append(float(trunc))
        self.values.append(float(value))
        self.op_masks.append(np.asarray(op_masks, dtype=np.float32))
        self.comm_masks.append(np.asarray(comm_masks, dtype=np.float32))
        self.elapsed.append(float(elapsed))

    def clear(self):
        self.__init__()

    def __len__(self) -> int:
        return len(self.rewards)

    def compute_gae(
        self,
        last_value: float,
        gamma: float = 0.99,
        lam: float = 0.95,
        *,
        time_aware: bool = True,
        dt_ref: float = 60.0,
    ):
        adv_t, ret_t = compute_gae_time(
            np.asarray(self.rewards, dtype=np.float32),
            np.asarray(self.values, dtype=np.float32),
            np.asarray(self.dones, dtype=np.float32),
            np.asarray(self.truncs, dtype=np.float32),
            last_value,
            gamma=gamma,
            lam=lam,
            elapsed=np.asarray(self.elapsed, dtype=np.float32) if time_aware else None,
            dt_ref=dt_ref,
        )
        # Broadcast fleet advantage to each simultaneous agent decision.
        n_agents = int(self.obs[0].shape[0])
        adv = np.repeat(adv_t[:, None], n_agents, axis=1).reshape(-1)
        ret = np.repeat(ret_t[:, None], n_agents, axis=1).reshape(-1)
        return adv_t, ret_t, adv, ret

    def as_tensors(self, adv_flat, ret_flat, device):
        obs = np.concatenate(self.obs, axis=0)  # (T*n_agents, obs_dim)
        gobs = np.repeat(np.asarray(self.global_obs), repeats=[a.shape[0] for a in self.obs], axis=0)
        return {
            "obs": torch.as_tensor(obs, dtype=torch.float32, device=device),
            "global_obs": torch.as_tensor(gobs, dtype=torch.float32, device=device),
            "op_actions": torch.as_tensor(
                np.concatenate(self.op_actions), dtype=torch.int64, device=device
            ),
            "comm_actions": torch.as_tensor(
                np.concatenate(self.comm_actions), dtype=torch.int64, device=device
            ),
            "op_logprobs": torch.as_tensor(
                np.concatenate(self.op_logprobs), dtype=torch.float32, device=device
            ),
            "comm_logprobs": torch.as_tensor(
                np.concatenate(self.comm_logprobs), dtype=torch.float32, device=device
            ),
            "advantages": torch.as_tensor(adv_flat, dtype=torch.float32, device=device),
            "returns": torch.as_tensor(ret_flat, dtype=torch.float32, device=device),
            "op_masks": torch.as_tensor(
                np.concatenate(self.op_masks), dtype=torch.float32, device=device
            ),
            "comm_masks": torch.as_tensor(
                np.concatenate(self.comm_masks), dtype=torch.float32, device=device
            ),
        }


# Legacy alias for imports that still reference RolloutBuffer.
RolloutBuffer = FleetRolloutBuffer
