"""Parameter-shared MAPPO trainer with time-indexed GAE (Yu et al. 2022 CTDE).

Stage 8.2: store *executed* communication actions. For B/C (external comm),
comm_learnable=0 so PPO does not apply likelihood ratios / entropy to
unexecuted sampled communication actions.
"""

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
        freeze_comm: bool = False,
        freeze_op: bool = False,
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
        self.freeze_comm = bool(freeze_comm)
        self.freeze_op = bool(freeze_op)
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
        buf = FleetRolloutBuffer()
        steps = self.env.reset(seed=self.env.seed)
        agent_ids = list(steps.keys())
        ep_seed = int(self.env.seed)
        last_done = False
        for _ in range(n_steps):
            op_actions = []
            proposed_comm = []
            op_logps = []
            proposed_comm_logps = []
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
                proposed_comm.append(comm_a)
                op_logps.append(olp)
                proposed_comm_logps.append(clp)
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
            if done and not list(next_steps.values())[0].info.get("truncated_budget", False):
                trunc = False
            team_reward = float(list(next_steps.values())[0].reward)
            elapsed = float(list(next_steps.values())[0].info.get("elapsed_s", 1.0))

            # Use *executed* communication actions; zero logprob if not learnable.
            exec_comm = []
            exec_comm_logps = []
            learnable = []
            for i, vid in enumerate(agent_ids):
                info = next_steps[vid].info
                ec = int(info.get("executed_comm", proposed_comm[i]))
                learn = bool(info.get("comm_learnable", not self.env.comm_externally_controlled))
                exec_comm.append(ec)
                if learn and ec == proposed_comm[i]:
                    exec_comm_logps.append(proposed_comm_logps[i])
                elif learn:
                    # Recompute logprob for executed action under the same policy.
                    o = torch.as_tensor(obs_rows[i], dtype=torch.float32, device=self.device).unsqueeze(0)
                    om = torch.as_tensor(op_masks[i], dtype=torch.float32, device=self.device).unsqueeze(0)
                    cm = torch.as_tensor(comm_masks[i], dtype=torch.float32, device=self.device).unsqueeze(0)
                    _, clog = self.actor(o, om, cm)
                    dist = Categorical(logits=clog)
                    exec_comm_logps.append(float(dist.log_prob(torch.tensor(ec, device=self.device)).item()))
                else:
                    exec_comm_logps.append(0.0)
                learnable.append(1.0 if learn else 0.0)

            # Natural terminal → dones=1 (cuts GAE). Budget cut → truncs=1.
            # Mid-buffer episode end + reset is covered by dones=1 so the next
            # episode's values cannot propagate backward.
            buf.add(
                obs_arr,
                gobs,
                np.asarray(op_actions),
                np.asarray(exec_comm),
                np.asarray(op_logps),
                np.asarray(exec_comm_logps),
                team_reward,
                float(done and not trunc),
                float(trunc),
                v,
                np.stack(op_masks, axis=0),
                np.stack(comm_masks, axis=0),
                elapsed=elapsed,
                comm_learnable=np.asarray(learnable, dtype=np.float32),
            )
            steps = next_steps
            last_done = done
            if done:
                ep_seed += 1
                steps = self.env.reset(seed=ep_seed)
                agent_ids = list(steps.keys())
        self.env.seed = ep_seed
        if last_done and buf.dones[-1] > 0.5:
            bootstrap = 0.0
        elif last_done and buf.truncs[-1] > 0.5:
            bootstrap = 0.0  # drained episode after budget cut
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
            learn = data["comm_learnable"]
            if self.freeze_comm:
                learn = torch.zeros_like(learn)
            if self.freeze_op:
                op_w = torch.zeros_like(learn)
            else:
                op_w = torch.ones_like(learn)

            # Likelihood uses only executed, learnable actions.
            old_logp = op_w * data["op_logprobs"] + learn * data["comm_logprobs"]
            new_logp = op_w * new_op_logp + learn * new_comm_logp
            ratio = torch.exp(new_logp - old_logp)
            surr1 = ratio * data["advantages"]
            surr2 = torch.clamp(ratio, 1.0 - self.clip, 1.0 + self.clip) * data["advantages"]
            policy_loss = -torch.min(surr1, surr2).mean()

            ent = op_w * op_dist.entropy() + learn * comm_dist.entropy()
            # Avoid div0 when all frozen — mean over agents still defined.
            entropy = ent.mean()

            values = self.critic(gobs_time)
            value_loss = F.mse_loss(values, returns_time)
            loss = policy_loss + self.value_coef * value_loss - self.entropy_coef * entropy
            self.opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                list(self.actor.parameters()) + list(self.critic.parameters()), 0.5
            )
            self.opt.step()
            # Diagnostic: mean |grad| on comm head when learnable fraction is 0
            comm_grad_norm = 0.0
            for name, p in self.actor.named_parameters():
                if "comm" in name and p.grad is not None:
                    comm_grad_norm += float(p.grad.detach().norm().item())
            metrics = {
                "loss": float(loss.item()),
                "policy_loss": float(policy_loss.item()),
                "value_loss": float(value_loss.item()),
                "entropy": float(entropy.item()),
                "comm_learnable_frac": float(learn.mean().item()),
                "comm_grad_norm": comm_grad_norm,
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
