"""Parameter-shared MAPPO trainer (Yu et al. 2022 style CTDE)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np
import torch
import torch.nn.functional as F
from torch.distributions import Categorical

from race_casablanca.marl.buffer import RolloutBuffer
from race_casablanca.marl.env import RaceMultiAgentEnv
from race_casablanca.marl.nets import Actor, Critic


class MAPPOTrainer:
    def __init__(
        self,
        env: RaceMultiAgentEnv,
        *,
        lr: float = 3e-4,
        gamma: float = 0.99,
        lam: float = 0.95,
        clip: float = 0.2,
        entropy_coef: float = 0.01,
        value_coef: float = 0.5,
        epochs: int = 4,
        device: str | None = None,
    ):
        self.env = env
        self.gamma = gamma
        self.lam = lam
        self.clip = clip
        self.entropy_coef = entropy_coef
        self.value_coef = value_coef
        self.epochs = epochs
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        n_agents = env.n_vehicles
        self.actor = Actor(env.obs_dim, env.n_actions).to(self.device)
        self.critic = Critic(env.obs_dim * n_agents).to(self.device)
        self.opt = torch.optim.Adam(
            list(self.actor.parameters()) + list(self.critic.parameters()), lr=lr
        )
        self.n_updates = 0
        self.loss_history: list[dict] = []

    def _select(self, obs, mask):
        o = torch.as_tensor(obs, dtype=torch.float32, device=self.device).unsqueeze(0)
        m = torch.as_tensor(mask, dtype=torch.float32, device=self.device).unsqueeze(0)
        logits = self.actor(o, m)
        dist = Categorical(logits=logits)
        a = dist.sample()
        return int(a.item()), float(dist.log_prob(a).item())

    def collect(self, n_steps: int) -> RolloutBuffer:
        buf = RolloutBuffer()
        steps = self.env.reset(seed=self.env.seed)
        agent_ids = list(steps.keys())
        ep_seed = int(self.env.seed)
        for _ in range(n_steps):
            actions = {}
            logps = {}
            for vid in agent_ids:
                a, lp = self._select(steps[vid].obs, steps[vid].mask)
                actions[vid] = a
                logps[vid] = lp
            # Centralized value from concat obs (training only)
            gobs = np.concatenate([steps[vid].obs for vid in agent_ids], axis=0)
            with torch.no_grad():
                v = float(
                    self.critic(
                        torch.as_tensor(gobs, dtype=torch.float32, device=self.device).unsqueeze(0)
                    ).item()
                )
            next_steps = self.env.step(actions)
            done = any(s.done for s in next_steps.values())
            team_reward = list(next_steps.values())[0].reward
            for vid in agent_ids:
                buf.add(
                    steps[vid].obs,
                    gobs,
                    actions[vid],
                    logps[vid],
                    team_reward / max(1, len(agent_ids)),
                    float(done),
                    v,
                    steps[vid].mask,
                )
            steps = next_steps
            if done:
                ep_seed += 1
                steps = self.env.reset(seed=ep_seed)
                agent_ids = list(steps.keys())
        self.env.seed = ep_seed
        return buf

    def update(self, buf: RolloutBuffer) -> dict:
        with torch.no_grad():
            # bootstrap 0
            last_v = 0.0
        adv, ret = buf.compute_gae(last_v, gamma=self.gamma, lam=self.lam)
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        data = buf.as_tensors(adv, ret, self.device)
        metrics = {}
        for _ in range(self.epochs):
            logits = self.actor(data["obs"], data["masks"])
            dist = Categorical(logits=logits)
            new_logp = dist.log_prob(data["actions"])
            entropy = dist.entropy().mean()
            ratio = torch.exp(new_logp - data["logprobs"])
            surr1 = ratio * data["advantages"]
            surr2 = torch.clamp(ratio, 1.0 - self.clip, 1.0 + self.clip) * data["advantages"]
            policy_loss = -torch.min(surr1, surr2).mean()
            values = self.critic(data["global_obs"])
            value_loss = F.mse_loss(values, data["returns"])
            loss = policy_loss + self.value_coef * value_loss - self.entropy_coef * entropy
            self.opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                list(self.actor.parameters()) + list(self.critic.parameters()), 0.5
            )
            self.opt.step()
            metrics = {
                "loss": float(loss.item()),
                "policy_loss": float(policy_loss.item()),
                "value_loss": float(value_loss.item()),
                "entropy": float(entropy.item()),
            }
        self.n_updates += 1
        self.loss_history.append(metrics)
        return metrics

    def train(
        self,
        iterations: int,
        steps_per_iter: int = 64,
        *,
        eval_every: int = 0,
        eval_episodes: int = 2,
        on_eval=None,
    ) -> list[dict]:
        logs = []
        best_ot = -1.0
        for i in range(iterations):
            buf = self.collect(steps_per_iter)
            m = self.update(buf)
            m["iter"] = i
            if eval_every and (i + 1) % eval_every == 0:
                ev = self.evaluate_deterministic(n_episodes=eval_episodes)
                m["eval"] = ev
                if ev["mean_ot"] >= best_ot:
                    best_ot = float(ev["mean_ot"])
                    m["is_best"] = True
                if on_eval is not None:
                    on_eval(i, ev, m)
            logs.append(m)
        return logs

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "actor": self.actor.state_dict(),
                "critic": self.critic.state_dict(),
                "n_updates": self.n_updates,
                "loss_history": self.loss_history,
            },
            path,
        )

    def load(self, path: Path, *, require_critic: bool = False) -> None:
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        self.actor.load_state_dict(ckpt["actor"])
        try:
            self.critic.load_state_dict(ckpt["critic"])
        except RuntimeError as exc:
            # Critic input dim = n_vehicles * obs_dim; fleet-transfer eval only needs actor.
            if require_critic:
                raise
            print(f"WARN: critic not loaded ({exc}); actor-only transfer eval", flush=True)
        self.n_updates = int(ckpt.get("n_updates", 0))
        self.loss_history = list(ckpt.get("loss_history", []))

    @torch.no_grad()
    def evaluate_deterministic(self, n_episodes: int = 3) -> dict:
        returns = []
        ots = []
        for ep in range(n_episodes):
            steps = self.env.reset(seed=self.env.seed + 1000 + ep)
            done = False
            total_r = 0.0
            while not done:
                actions = {}
                for vid, st in steps.items():
                    o = torch.as_tensor(st.obs, dtype=torch.float32, device=self.device).unsqueeze(0)
                    m = torch.as_tensor(st.mask, dtype=torch.float32, device=self.device).unsqueeze(0)
                    logits = self.actor(o, m)
                    a = int(torch.argmax(logits, dim=-1).item())
                    actions[vid] = a
                steps = self.env.step(actions)
                total_r += list(steps.values())[0].reward
                done = list(steps.values())[0].done
            returns.append(total_r)
            ots.append(float(self.env.final_metrics().get("on_time_rate_all", 0.0)))
        return {"mean_return": float(np.mean(returns)), "mean_ot": float(np.mean(ots)), "n": n_episodes}
