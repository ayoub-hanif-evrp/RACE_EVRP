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
            elif self.enable_charge and env._charge_action_legal(obs):
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


class _LoggingActionInterface(ActionInterface):
    """Record claim/charge/bid side-effects while applying them (oracle execute path)."""

    def __init__(self, sim, *, actor_vehicle_id: str):
        super().__init__(sim, actor_vehicle_id=actor_vehicle_id)
        self.claimed_rid: str | None = None
        self.charged: bool = False
        self.sent_rid: str | None = None

    def claim_task(self, vehicle_id: str, request_id: str, *, force_position: int | None = None) -> bool:
        ok = super().claim_task(vehicle_id, request_id, force_position=force_position)
        if ok:
            self.claimed_rid = request_id
        return ok

    def request_return_depot(self, vehicle_id: str, *, charge: bool | None = None, target_soc: float | None = None) -> None:
        self.charged = True
        return super().request_return_depot(vehicle_id, charge=charge, target_soc=target_soc)

    def broadcast_task_bid(self, vehicle_id: str, payload: dict) -> int:
        self.sent_rid = str(payload.get("request_id", "")) or self.sent_rid
        return super().broadcast_task_bid(vehicle_id, payload)


class _IntentOnlyInterface(ActionInterface):
    """Record native intent without mutating the simulator (factorized BC / env.step path)."""

    def __init__(self, sim, *, actor_vehicle_id: str):
        super().__init__(sim, actor_vehicle_id=actor_vehicle_id)
        self.claimed_rid: str | None = None
        self.charged: bool = False
        self.sent_rid: str | None = None

    def claim_task(self, vehicle_id: str, request_id: str, *, force_position: int | None = None) -> bool:
        chk = self.check_insertion(vehicle_id, request_id)
        if not chk.feasible:
            return False
        self.claimed_rid = request_id
        return True

    def request_return_depot(self, vehicle_id: str, *, charge: bool | None = None, target_soc: float | None = None) -> None:
        self.charged = True

    def broadcast_task_bid(self, vehicle_id: str, payload: dict) -> int:
        self.sent_rid = str(payload.get("request_id", "")) or self.sent_rid
        raw = str(payload)
        return max(1, len(raw.encode("utf-8")))

    def reject_request(self, request_id: str) -> None:
        # Intent-only: do not expire requests during labeling.
        return


class NativeBridgeTeacher:
    """Map real ``RaceCooperativePolicy`` decisions onto factorized MARL actions.

    Modes:
    - ``intent`` (default): non-mutating labels from the shared pending state; apply via
      ``env.step`` so BC train/eval share the batched claim protocol.
    - ``execute``: sequential mutating native calls (oracle upper bound; do not re-step).
    """

    def __init__(self, *, comm_mode: str = "selective", rng_seed: int = 7, mode: str = "intent"):
        from race_casablanca.policies import RaceCooperativePolicy

        self.comm_mode = comm_mode
        self.rng_seed = rng_seed
        self.mode = mode
        self.policy = RaceCooperativePolicy(
            comm_mode=comm_mode, enable_readiness_charge=True, rng_seed=rng_seed
        )

    def reset(self) -> None:
        from race_casablanca.policies import RaceCooperativePolicy

        self.policy = RaceCooperativePolicy(
            comm_mode=self.comm_mode, enable_readiness_charge=True, rng_seed=self.rng_seed
        )

    def actions(self, env: RaceMultiAgentEnv) -> dict[str, tuple[int, int]]:
        from dataclasses import replace

        from race_casablanca.sim.policy_api import build_restricted_observation

        assert env.sim is not None
        reason = getattr(env, "_last_decision_reason", "epoch") or "epoch"
        # Readiness charge in RaceCooperativePolicy is reason-gated and omits
        # service_end / vehicle_idle. MARL event-parity returns on those events;
        # map them to epoch so bridge charge matches native release/idle practice.
        charge_reason = reason
        if self.mode == "intent" and reason in ("service_end", "vehicle_idle", "pickup_missed"):
            charge_reason = "epoch"
        out: dict[str, tuple[int, int]] = {}
        # Snapshot task lists / obs before any optional execute mutations
        task_lists = {
            vid: sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
            for vid, obs in env._pending_obs.items()
        }
        pending_obs = dict(env._pending_obs)
        soft_claimed: set[str] = set()
        for vid in sorted(env._agent_ids):
            tasks = task_lists[vid]
            if self.mode == "execute":
                obs = build_restricted_observation(env.sim, vid)
                logger: ActionInterface = _LoggingActionInterface(env.sim, actor_vehicle_id=vid)
                self.policy.on_decision(obs, logger, reason)
            else:
                base = pending_obs[vid]
                # Sequential soft-assign: hide tasks already intended by earlier vehicles
                # so factorized labels approximate native within-epoch ordering.
                if soft_claimed:
                    filtered = [t for t in base.announced if t.request_id not in soft_claimed]
                    obs = replace(base, announced=filtered)
                else:
                    obs = base
                logger = _IntentOnlyInterface(env.sim, actor_vehicle_id=vid)
                self.policy.on_decision(obs, logger, charge_reason)
            op = OP_DEFER
            if logger.claimed_rid is not None:
                for i, t in enumerate(tasks):
                    if t.request_id == logger.claimed_rid:
                        op = i
                        break
                else:
                    op = OP_DEFER  # claimed outside top-K truncation
                if self.mode == "intent" and op != OP_DEFER:
                    soft_claimed.add(logger.claimed_rid)
            elif logger.charged:
                op = OP_CHARGE
            elif self.mode == "intent" and env._charge_action_legal(pending_obs[vid]):
                # Fallback when native reason-gating left a legal charge unused.
                if not pending_obs[vid].announced or all(
                    t.request_id in soft_claimed for t in pending_obs[vid].announced
                ):
                    op = OP_CHARGE
            comm = COMM_SUPPRESS
            if logger.sent_rid and env.comm_enabled:
                for i, t in enumerate(tasks):
                    if t.request_id == logger.sent_rid:
                        comm = i
                        break
            out[vid] = (op, comm)
        if self.mode == "execute":
            for vid in env._agent_ids:
                env._pending_obs[vid] = build_restricted_observation(env.sim, vid)
        return out


def native_bridge_teacher_actions(
    env: RaceMultiAgentEnv, teacher: NativeBridgeTeacher | None = None
) -> dict[str, tuple[int, int]]:
    if teacher is None:
        teacher = NativeBridgeTeacher()
    return teacher.actions(env)


def _advance_without_reexec(env: RaceMultiAgentEnv) -> dict:
    """After a teacher that already mutated the sim, only flush legs and advance time."""
    env._n_decisions += 1
    env._flush_autoleg()
    done = env._advance_to_decision()
    truncated = False
    if env._n_decisions >= env.max_decisions:
        done = True
        truncated = True
    if done:
        while env.sim._eq:
            env._flush_autoleg()
            if env._advance_to_decision():
                break
        env._flush_autoleg()
    out = env._observe_all(reward=0.0, done=done)
    for st in out.values():
        st.info["truncated_budget"] = truncated
    return out


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
    # Intent mode: labels must be applied via env.step (batched protocol).
    native = NativeBridgeTeacher(mode="intent") if teacher == "native_bridge" else None
    if coop is not None:
        coop.reset()
    if native is not None:
        native.reset()
    for _ in range(n_steps):
        if teacher == "cooperative":
            labels = cooperative_teacher_actions(env, coop)
            already_executed = False
        elif teacher == "native_bridge":
            labels = native_bridge_teacher_actions(env, native)
            already_executed = False
        else:
            labels = greedy_teacher_actions(env)
            already_executed = False
        for vid, st in steps.items():
            obs_l.append(st.obs)
            op_l.append(labels[vid][0])
            comm_l.append(labels[vid][1])
            opm_l.append(st.op_mask)
            cmm_l.append(st.comm_mask)
        if already_executed:
            steps = _advance_without_reexec(env)
        else:
            steps = env.step(labels)
        if list(steps.values())[0].done:
            ep_seed += 1
            steps = env.reset(seed=ep_seed)
            if coop is not None:
                coop.reset()
            if native is not None:
                native.reset()
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
    class_weight: bool = True,
) -> list[float]:
    device = torch.device(device)
    actor = actor.to(device)
    opt = torch.optim.Adam(actor.parameters(), lr=lr)
    obs = torch.as_tensor(batch["obs"], device=device)
    op = torch.as_tensor(batch["op"], device=device)
    comm = torch.as_tensor(batch["comm"], device=device)
    opm = torch.as_tensor(batch["op_mask"], device=device)
    cmm = torch.as_tensor(batch["comm_mask"], device=device)
    op_w = None
    if class_weight:
        n_op = int(getattr(getattr(actor, "op_head", None), "out_features", int(op.max().item()) + 1))
        counts = np.bincount(batch["op"], minlength=n_op).astype(np.float32)
        w = counts.sum() / (counts + 1.0)
        w = w / max(float(w.mean()), 1e-6)
        op_w = torch.as_tensor(w, device=device)
    losses = []
    for _ in range(epochs):
        op_logits, comm_logits = actor(obs, opm, cmm)
        loss = F.cross_entropy(op_logits, op, weight=op_w) + F.cross_entropy(comm_logits, comm)
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
    teacher: str = "cooperative",
) -> dict[str, np.ndarray]:
    """Roll out student; label states with teacher (DAgger-style)."""
    device = torch.device(device)
    actor = actor.to(device)
    actor.eval()
    coop = CooperativeTeacherAdapter() if teacher == "cooperative" else None
    native = NativeBridgeTeacher(mode="intent") if teacher == "native_bridge" else None
    steps = env.reset(seed=seed)
    obs_l, op_l, comm_l, opm_l, cmm_l = [], [], [], [], []
    ep_seed = seed
    for _ in range(n_steps):
        if native is not None:
            labels = native_bridge_teacher_actions(env, native)
        else:
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
            if coop is not None:
                coop.reset()
            if native is not None:
                native.reset()
    tag = f"{teacher}_dagger"
    new = {
        "obs": np.asarray(obs_l, dtype=np.float32),
        "op": np.asarray(op_l, dtype=np.int64),
        "comm": np.asarray(comm_l, dtype=np.int64),
        "op_mask": np.asarray(opm_l, dtype=np.float32),
        "comm_mask": np.asarray(cmm_l, dtype=np.float32),
        "teacher": tag,
    }
    if prior_batch is None:
        return new
    return {
        "obs": np.concatenate([prior_batch["obs"], new["obs"]], axis=0),
        "op": np.concatenate([prior_batch["op"], new["op"]], axis=0),
        "comm": np.concatenate([prior_batch["comm"], new["comm"]], axis=0),
        "op_mask": np.concatenate([prior_batch["op_mask"], new["op_mask"]], axis=0),
        "comm_mask": np.concatenate([prior_batch["comm_mask"], new["comm_mask"]], axis=0),
        "teacher": tag,
    }
