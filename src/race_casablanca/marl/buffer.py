"""Rollout buffer for multi-agent PPO."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import torch


@dataclass
class RolloutBuffer:
    obs: list = field(default_factory=list)
    global_obs: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    logprobs: list = field(default_factory=list)
    rewards: list = field(default_factory=list)
    dones: list = field(default_factory=list)
    values: list = field(default_factory=list)
    masks: list = field(default_factory=list)

    def add(self, obs, global_obs, action, logprob, reward, done, value, mask):
        self.obs.append(obs)
        self.global_obs.append(global_obs)
        self.actions.append(action)
        self.logprobs.append(logprob)
        self.rewards.append(reward)
        self.dones.append(done)
        self.values.append(value)
        self.masks.append(mask)

    def clear(self):
        self.__init__()

    def compute_gae(self, last_value: float, gamma: float = 0.99, lam: float = 0.95):
        rewards = np.asarray(self.rewards, dtype=np.float32)
        values = np.asarray(self.values + [last_value], dtype=np.float32)
        dones = np.asarray(self.dones, dtype=np.float32)
        adv = np.zeros_like(rewards)
        gae = 0.0
        for t in reversed(range(len(rewards))):
            delta = rewards[t] + gamma * values[t + 1] * (1.0 - dones[t]) - values[t]
            gae = delta + gamma * lam * (1.0 - dones[t]) * gae
            adv[t] = gae
        ret = adv + values[:-1]
        return adv, ret

    def as_tensors(self, adv, ret, device):
        return {
            "obs": torch.as_tensor(np.asarray(self.obs), dtype=torch.float32, device=device),
            "global_obs": torch.as_tensor(np.asarray(self.global_obs), dtype=torch.float32, device=device),
            "actions": torch.as_tensor(np.asarray(self.actions), dtype=torch.int64, device=device),
            "logprobs": torch.as_tensor(np.asarray(self.logprobs), dtype=torch.float32, device=device),
            "advantages": torch.as_tensor(adv, dtype=torch.float32, device=device),
            "returns": torch.as_tensor(ret, dtype=torch.float32, device=device),
            "masks": torch.as_tensor(np.asarray(self.masks), dtype=torch.float32, device=device),
        }
