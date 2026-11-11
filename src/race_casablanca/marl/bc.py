"""Behavior cloning teachers for Stage 8.2 recovery.

Two teachers are distinguished explicitly:

- ``greedy_teacher_actions``: local marginal-cost greedy (legacy Stage 8.1).
- ``cooperative_teacher_actions``: adapter over ``RaceCooperativePolicy`` using
  only restricted observations and the same action space / assignment window
  as the learner (no privileged simulator access beyond ActionInterface).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn.functional as F

from race_casablanca.coordination.selective_protocol import BidMemory, selective_should_send
from race_casablanca.coordination.task_bids import compute_self_bid, self_should_claim
from race_casablanca.marl.env import (
    ABLATION_A,
    ABLATION_B,
    ABLATION_F,
    COMM_SUPPRESS,
    K_TASKS,
    OP_CHARGE,
    OP_DEFER,
    RaceMultiAgentEnv,
)
from race_casablanca.marl.nets import FactorizedActor
from race_casablanca.sim.policy_api import ActionInterface


def greedy_teacher_actions(env: RaceMultiAgentEnv) -> dict[str, tuple[int, int]]:
    """Local teacher: claim feasible task with least travel; charge if SoC low."""
    assert env.sim is not None
    out = {}
    for vid, obs in env._pending_obs.items():
        act = ActionInterface(env.sim, actor_vehicle_id=vid)
        tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
        best_i = None
        best_travel = float("inf")
        for i, t in enumerate(tasks):
            chk = act.check_insertion(vid, t.request_id)
            if chk.feasible:
                travel = float(chk.marginal_travel_s or 0.0)
                if travel < best_travel:
                    best_travel = travel
                    best_i = i
        soc = float(obs.self_state.battery_kwh) / 40.0
        if best_i is not None:
            op = best_i
        elif soc < 0.25:
            op = OP_CHARGE
        else:
            op = OP_DEFER
        if env.comm_enabled and best_i is not None and env.ablation != ABLATION_A:
            chk = act.check_insertion(vid, tasks[best_i].request_id)
            flex = float(chk.energy_flex_kwh or 0.0)
            if env.ablation == ABLATION_B or flex < 8.0:
                comm = best_i
            else:
                comm = COMM_SUPPRESS
        else:
            comm = COMM_SUPPRESS
        out[vid] = (op, comm)
    return out


class CooperativeTeacherAdapter:
    """Map RaceCooperativePolicy logic onto factorized (op, comm) indices.

    Maintains per-vehicle bid memory across decision epochs (training only).
    Does not expose privileged global state to the student.
    """

    def __init__(self, *, bid_ttl_s: float = 120.0, enable_charge: bool = True):
        self.bid_ttl_s = float(bid_ttl_s)
        self.enable_charge = bool(enable_charge)
        self._seq = 0
        self._sent: dict[tuple[str, str], BidMemory] = {}
        self._commit_version: dict[str, int] = {}

    def reset(self) -> None:
        self._seq = 0
        self._sent.clear()
        self._commit_version.clear()

    def actions(self, env: RaceMultiAgentEnv) -> dict[str, tuple[int, int]]:
        assert env.sim is not None
        out: dict[str, tuple[int, int]] = {}
        for vid, obs in env._pending_obs.items():
            act = ActionInterface(env.sim, actor_vehicle_id=vid)
            tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
            cv = self._commit_version.get(vid, 0)
            own_bids = {}
            for t in tasks:
                self._seq += 1
                own_bids[t.request_id] = compute_self_bid(
                    obs, act, t, ttl_s=self.bid_ttl_s, seq=self._seq, commitment_version=cv
                )

            # Operational: first task where self_should_claim, else charge/defer.
            op = OP_DEFER
            claim_i = None
            for i, t in enumerate(tasks):
                own = own_bids[t.request_id]
                if not own.feasible:
                    continue
                peers = []
                for sid, payload in (obs.peer_bids.get(t.request_id) or {}).items():
                    if sid == vid:
                        continue
                    try:
                        from race_casablanca.coordination.task_bids import TaskBid

                        peers.append(TaskBid.from_payload(payload))
                    except (KeyError, TypeError, ValueError):
                        continue
                if self_should_claim(own, peers, now_s=float(obs.now_s)):
                    claim_i = i
                    break
            if claim_i is not None:
                op = claim_i
            elif self.enable_charge and float(obs.self_state.battery_kwh) / 40.0 < 0.30:
                op = OP_CHARGE

            # Communication: selective_should_send mapped to task index.
            comm = COMM_SUPPRESS
            if env.comm_enabled and env.ablation != ABLATION_A and tasks:
                if env.ablation == ABLATION_B:
                    for i, t in enumerate(tasks):
                        if own_bids[t.request_id].feasible:
                            comm = i
                            break
                else:
                    for i, t in enumerate(tasks):
                        own = own_bids[t.request_id]
                        if not own.feasible:
                            continue
                        peers = []
                        for sid, payload in (obs.peer_bids.get(t.request_id) or {}).items():
                            if sid == vid:
                                continue
                            try:
                                from race_casablanca.coordination.task_bids import TaskBid

                                peers.append(TaskBid.from_payload(payload))
                            except (KeyError, TypeError, ValueError):
                                continue
                        key = (vid, t.request_id)
                        mem = self._sent.get(key)
                        if env.ablation == ABLATION_F:
                            # Contest / energy-cert gate matches env F mask.
                            from race_casablanca.marl.env import CONTEST_DEADLINE_SLACK_S

                            needs = bool(peers) or float(own.energy_flex_kwh) < env.energy_cert_threshold_kwh
                            needs = needs or float(own.deadline_slack_s) < CONTEST_DEADLINE_SLACK_S
                            if not needs:
                                continue
                        send, _kind = selective_should_send(own, peers, mem, now_s=float(obs.now_s))
                        if send:
                            comm = i
                            self._sent[key] = BidMemory(bid=own, send_s=float(obs.now_s))
                            break
            if claim_i is not None:
                self._commit_version[vid] = cv + 1
            out[vid] = (op, comm)
        return out


def cooperative_teacher_actions(
    env: RaceMultiAgentEnv, adapter: CooperativeTeacherAdapter | None = None
) -> dict[str, tuple[int, int]]:
    if adapter is None:
        adapter = CooperativeTeacherAdapter()
    return adapter.actions(env)


def collect_bc_batch(
    env: RaceMultiAgentEnv,
    *,
    n_steps: int = 128,
    seed: int = 0,
    teacher: str = "cooperative",
) -> dict[str, np.ndarray]:
    steps = env.reset(seed=seed)
    obs_l, op_l, comm_l, opm_l, cmm_l = [], [], [], [], []
    ep_seed = seed
    coop = CooperativeTeacherAdapter() if teacher == "cooperative" else None
    if coop is not None:
        coop.reset()
    for _ in range(n_steps):
        if teacher == "cooperative":
            labels = cooperative_teacher_actions(env, coop)
        else:
            labels = greedy_teacher_actions(env)
        for vid, st in steps.items():
            obs_l.append(st.obs)
            op_l.append(labels[vid][0])
            comm_l.append(labels[vid][1])
            opm_l.append(st.op_mask)
            cmm_l.append(st.comm_mask)
        steps = env.step(labels)
        if list(steps.values())[0].done:
            ep_seed += 1
            steps = env.reset(seed=ep_seed)
            if coop is not None:
                coop.reset()
    return {
        "obs": np.asarray(obs_l, dtype=np.float32),
        "op": np.asarray(op_l, dtype=np.int64),
        "comm": np.asarray(comm_l, dtype=np.int64),
        "op_mask": np.asarray(opm_l, dtype=np.float32),
        "comm_mask": np.asarray(cmm_l, dtype=np.float32),
        "teacher": teacher,
    }


def behavior_clone(
    actor: FactorizedActor,
    batch: dict[str, np.ndarray],
    *,
    epochs: int = 20,
    lr: float = 1e-3,
    device: str | torch.device = "cpu",
) -> list[float]:
    device = torch.device(device)
    actor = actor.to(device)
    opt = torch.optim.Adam(actor.parameters(), lr=lr)
    obs = torch.as_tensor(batch["obs"], device=device)
    op = torch.as_tensor(batch["op"], device=device)
    comm = torch.as_tensor(batch["comm"], device=device)
    opm = torch.as_tensor(batch["op_mask"], device=device)
    cmm = torch.as_tensor(batch["comm_mask"], device=device)
    losses = []
    for _ in range(epochs):
        op_logits, comm_logits = actor(obs, opm, cmm)
        loss = F.cross_entropy(op_logits, op) + F.cross_entropy(comm_logits, comm)
        opt.zero_grad()
        loss.backward()
        opt.step()
        losses.append(float(loss.item()))
    return losses


def evaluate_bc_accuracy(
    actor: FactorizedActor,
    batch: dict[str, np.ndarray],
    *,
    device: str | torch.device = "cpu",
) -> dict[str, float]:
    device = torch.device(device)
    actor = actor.to(device)
    actor.eval()
    with torch.no_grad():
        obs = torch.as_tensor(batch["obs"], device=device)
        op = torch.as_tensor(batch["op"], device=device)
        comm = torch.as_tensor(batch["comm"], device=device)
        opm = torch.as_tensor(batch["op_mask"], device=device)
        cmm = torch.as_tensor(batch["comm_mask"], device=device)
        op_logits, comm_logits = actor(obs, opm, cmm)
        op_pred = op_logits.argmax(dim=-1)
        comm_pred = comm_logits.argmax(dim=-1)
        op_acc = float((op_pred == op).float().mean().item())
        comm_acc = float((comm_pred == comm).float().mean().item())
        charge_mask = op == OP_CHARGE
        if charge_mask.any():
            charge_acc = float((op_pred[charge_mask] == op[charge_mask]).float().mean().item())
        else:
            charge_acc = float("nan")
    return {
        "op_accuracy": op_acc,
        "comm_accuracy": comm_acc,
        "charge_accuracy": charge_acc,
        "n": float(len(batch["op"])),
        "teacher": str(batch.get("teacher", "")),
    }


def dagger_aggregate(
    env: RaceMultiAgentEnv,
    actor: FactorizedActor,
    *,
    n_steps: int = 64,
    seed: int = 0,
    device: str | torch.device = "cpu",
    prior_batch: dict[str, np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    """Roll out student; label states with cooperative teacher (DAgger-style)."""
    device = torch.device(device)
    actor = actor.to(device)
    actor.eval()
    coop = CooperativeTeacherAdapter()
    steps = env.reset(seed=seed)
    obs_l, op_l, comm_l, opm_l, cmm_l = [], [], [], [], []
    ep_seed = seed
    for _ in range(n_steps):
        labels = cooperative_teacher_actions(env, coop)
        student_actions: dict[str, tuple[int, int]] = {}
        for vid, st in steps.items():
            obs_l.append(st.obs)
            op_l.append(labels[vid][0])
            comm_l.append(labels[vid][1])
            opm_l.append(st.op_mask)
            cmm_l.append(st.comm_mask)
            with torch.no_grad():
                o = torch.as_tensor(st.obs, device=device).unsqueeze(0)
                om = torch.as_tensor(st.op_mask, device=device).unsqueeze(0)
                cm = torch.as_tensor(st.comm_mask, device=device).unsqueeze(0)
                op_logits, comm_logits = actor(o, om, cm)
                student_actions[vid] = (
                    int(op_logits.argmax(-1).item()),
                    int(comm_logits.argmax(-1).item()),
                )
        steps = env.step(student_actions)
        if list(steps.values())[0].done:
            ep_seed += 1
            steps = env.reset(seed=ep_seed)
            coop.reset()
    new = {
        "obs": np.asarray(obs_l, dtype=np.float32),
        "op": np.asarray(op_l, dtype=np.int64),
        "comm": np.asarray(comm_l, dtype=np.int64),
        "op_mask": np.asarray(opm_l, dtype=np.float32),
        "comm_mask": np.asarray(cmm_l, dtype=np.float32),
        "teacher": "cooperative_dagger",
    }
    if prior_batch is None:
        return new
    return {
        "obs": np.concatenate([prior_batch["obs"], new["obs"]], axis=0),
        "op": np.concatenate([prior_batch["op"], new["op"]], axis=0),
        "comm": np.concatenate([prior_batch["comm"], new["comm"]], axis=0),
        "op_mask": np.concatenate([prior_batch["op_mask"], new["op_mask"]], axis=0),
        "comm_mask": np.concatenate([prior_batch["comm_mask"], new["comm_mask"]], axis=0),
        "teacher": "cooperative_dagger",
    }
