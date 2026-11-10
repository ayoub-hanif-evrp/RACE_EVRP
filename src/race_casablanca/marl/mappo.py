"""Parameter-shared MAPPO trainer with time-indexed GAE (Yu et al. 2022 CTDE)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.distributions import Categorical

from race_casablanca.marl.buffer import FleetRolloutBuffer
from race_casablanca.marl.env import COMM_SUPPRESS, RaceMultiAgentEnv
from race_casablanca.marl.nets import Critic, FactorizedActor


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
        time_aware: bool = True,
        dt_ref: float = 60.0,
    ):
        self.env = env
        self.gamma = gamma
        self.lam = lam
        self.clip = clip
        self.entropy_coef = entropy_coef
        self.value_coef = value_coef
        self.epochs = epochs
        self.time_aware = time_aware
        self.dt_ref = dt_ref
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        n_agents = env.n_vehicles
        self.actor = FactorizedActor(env.obs_dim, env.n_op, env.n_comm).to(self.device)
        self.critic = Critic(env.obs_dim * n_agents).to(self.device)
        self.opt = torch.optim.Adam(
            list(self.actor.parameters()) + list(self.critic.parameters()), lr=lr
        )
        self.n_updates = 0
        self.loss_history: list[dict] = []

    def _select(self, obs, op_mask, comm_mask):
        o = torch.as_tensor(obs, dtype=torch.float32, device=self.device).unsqueeze(0)
        om = torch.as_tensor(op_mask, dtype=torch.float32, device=self.device).unsqueeze(0)
        cm = torch.as_tensor(comm_mask, dtype=torch.float32, device=self.device).unsqueeze(0)
        op_logits, comm_logits = self.actor(o, om, cm)
        op_dist = Categorical(logits=op_logits)
        comm_dist = Categorical(logits=comm_logits)
        op_a = op_dist.sample()
        comm_a = comm_dist.sample()
        return (
            int(op_a.item()),
            int(comm_a.item()),
            float(op_dist.log_prob(op_a).item()),
            float(comm_dist.log_prob(comm_a).item()),
        )

    def collect(self, n_steps: int) -> tuple[FleetRolloutBuffer, float, bool]:
        """Collect n_steps synchronized fleet transitions.

        Returns buffer, bootstrap value for truncation, and whether last step ended an episode.
        """
        buf = FleetRolloutBuffer()
        steps = self.env.reset(seed=self.env.seed)
        agent_ids = list(steps.keys())
        ep_seed = int(self.env.seed)
        last_done = False
        for _ in range(n_steps):
            op_actions = []
            comm_actions = []
            op_logps = []
            comm_logps = []
            op_masks = []
            comm_masks = []
            obs_rows = []
            action_map = {}
            for vid in agent_ids:
                op_a, comm_a, olp, clp = self._select(
                    steps[vid].obs, steps[vid].op_mask, steps[vid].comm_mask
                )
                action_map[vid] = (op_a, comm_a)
                op_actions.append(op_a)
                comm_actions.append(comm_a)
                op_logps.append(olp)
                comm_logps.append(clp)
                op_masks.append(steps[vid].op_mask)
                comm_masks.append(steps[vid].comm_mask)
                obs_rows.append(steps[vid].obs)
            obs_arr = np.stack(obs_rows, axis=0)
            gobs = obs_arr.reshape(-1)
            with torch.no_grad():
                v = float(
                    self.critic(
                        torch.as_tensor(gobs, dtype=torch.float32, device=self.device).unsqueeze(0)
                    ).item()
                )
            next_steps = self.env.step(action_map)
            done = any(s.done for s in next_steps.values())
            trunc = bool(list(next_steps.values())[0].info.get("truncated_budget", False)) and done
            # If episode ended naturally (not budget), trunc=False, done=True.
            if done and not list(next_steps.values())[0].info.get("truncated_budget", False):
                trunc = False
            team_reward = float(list(next_steps.values())[0].reward)
            elapsed = float(list(next_steps.values())[0].info.get("elapsed_s", 1.0))
            buf.add(
                obs_arr,
                gobs,
                np.asarray(op_actions),
                np.asarray(comm_actions),
                np.asarray(op_logps),
                np.asarray(comm_logps),
                team_reward,
                float(done and not trunc),
                float(trunc),
                v,
                np.stack(op_masks, axis=0),
                np.stack(comm_masks, axis=0),
                elapsed=elapsed,
            )
            steps = next_steps
            last_done = done
            if done:
                ep_seed += 1
                steps = self.env.reset(seed=ep_seed)
                agent_ids = list(steps.keys())
        self.env.seed = ep_seed
        # Bootstrap: if last transition ended the episode, 0; if truncated mid-episode, critic value.
        if last_done and buf.dones[-1] > 0.5:
            bootstrap = 0.0
        elif last_done and buf.truncs[-1] > 0.5:
            # Budget truncation after drain — treat as terminal for service accounting.
            bootstrap = 0.0
        else:
            gobs = np.concatenate([steps[vid].obs for vid in agent_ids], axis=0)
            with torch.no_grad():
                bootstrap = float(
                    self.critic(
                        torch.as_tensor(gobs, dtype=torch.float32, device=self.device).unsqueeze(0)
                    ).item()
                )
        return buf, bootstrap, last_done

    def update(self, buf: FleetRolloutBuffer, last_value: float = 0.0) -> dict:
        adv_t, ret_t, adv_flat, ret_flat = buf.compute_gae(
            last_value,
            gamma=self.gamma,
            lam=self.lam,
            time_aware=self.time_aware,
            dt_ref=self.dt_ref,
        )
        adv_flat = (adv_flat - adv_flat.mean()) / (adv_flat.std() + 1e-8)
        data = buf.as_tensors(adv_flat, ret_flat, self.device)
        # Time-level returns for critic (one per fleet step)
        returns_time = torch.as_tensor(ret_t, dtype=torch.float32, device=self.device)
        gobs_time = torch.as_tensor(
            np.asarray(buf.global_obs), dtype=torch.float32, device=self.device
        )
        metrics = {}
        for _ in range(self.epochs):
            op_logits, comm_logits = self.actor(data["obs"], data["op_masks"], data["comm_masks"])
            op_dist = Categorical(logits=op_logits)
            comm_dist = Categorical(logits=comm_logits)
            new_op_logp = op_dist.log_prob(data["op_actions"])
            new_comm_logp = comm_dist.log_prob(data["comm_actions"])
            entropy = op_dist.entropy().mean() + comm_dist.entropy().mean()
            # Joint log-prob ratio (independent heads)
            old_logp = data["op_logprobs"] + data["comm_logprobs"]
            new_logp = new_op_logp + new_comm_logp
            ratio = torch.exp(new_logp - old_logp)
            surr1 = ratio * data["advantages"]
            surr2 = torch.clamp(ratio, 1.0 - self.clip, 1.0 + self.clip) * data["advantages"]
            policy_loss = -torch.min(surr1, surr2).mean()
            values = self.critic(gobs_time)
            value_loss = F.mse_loss(values, returns_time)
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
            buf, bootstrap, _ = self.collect(steps_per_iter)
            m = self.update(buf, last_value=bootstrap)
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
                "obs_dim": self.env.obs_dim,
                "n_op": self.env.n_op,
                "n_comm": self.env.n_comm,
                "n_vehicles": self.env.n_vehicles,
            },
            path,
        )

    def load(self, path: Path, *, require_critic: bool = False) -> None:
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        self.actor.load_state_dict(ckpt["actor"])
        try:
            self.critic.load_state_dict(ckpt["critic"])
        except RuntimeError as exc:
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
                    om = torch.as_tensor(st.op_mask, dtype=torch.float32, device=self.device).unsqueeze(0)
                    cm = torch.as_tensor(st.comm_mask, dtype=torch.float32, device=self.device).unsqueeze(0)
                    op_logits, comm_logits = self.actor(o, om, cm)
                    op_a = int(torch.argmax(op_logits, dim=-1).item())
                    comm_a = int(torch.argmax(comm_logits, dim=-1).item())
                    actions[vid] = (op_a, comm_a)
                steps = self.env.step(actions)
                total_r += list(steps.values())[0].reward
                done = list(steps.values())[0].done
            returns.append(total_r)
            ots.append(float(self.env.final_metrics().get("on_time_rate_all", 0.0)))
        return {"mean_return": float(np.mean(returns)), "mean_ot": float(np.mean(ots)), "n": n_episodes}
