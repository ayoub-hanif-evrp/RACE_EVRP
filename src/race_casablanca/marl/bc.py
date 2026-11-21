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
    - ``execute``: mutating native calls; advance with ``_advance_without_reexec``.
    - ``intent_matched`` (preferred step path): same as execute, then mark
      ``env._comm_preflight_done`` / ``_ops_preflight_done`` so ``env.step`` only
      advances time (no re-send / re-claim). Closes teacher-through-step gap safely.
    - ``intent``: legacy soft labels for diagnostics only (known OT gap).

    On ``request_release``, mirrors native two-phase ``bid_exchange`` → flush →
    ``bid_assign`` (Stage 8.3 / top-tier Phase 1 slice 2).
    """

    def __init__(self, *, comm_mode: str = "selective", rng_seed: int = 7, mode: str = "intent_matched"):
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

    @staticmethod
    def _map_op_comm(
        *,
        tasks: list,
        claimed_rid: str | None,
        charged: bool,
        sent_rid: str | None,
        comm_enabled: bool,
    ) -> tuple[int, int]:
        op = OP_DEFER
        if claimed_rid is not None:
            for i, t in enumerate(tasks):
                if t.request_id == claimed_rid:
                    op = i
                    break
        elif charged:
            op = OP_CHARGE
        comm = COMM_SUPPRESS
        if sent_rid and comm_enabled:
            for i, t in enumerate(tasks):
                if t.request_id == sent_rid:
                    comm = i
                    break
        return op, comm

    def _actions_execute(self, env: RaceMultiAgentEnv) -> dict[str, tuple[int, int]]:
        from race_casablanca.sim.policy_api import build_restricted_observation

        assert env.sim is not None
        reason = getattr(env, "_last_decision_reason", "epoch") or "epoch"
        task_lists = {
            vid: sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
            for vid, obs in env._pending_obs.items()
        }
        out: dict[str, tuple[int, int]] = {vid: (OP_DEFER, COMM_SUPPRESS) for vid in env._agent_ids}
        sent: dict[str, str | None] = {vid: None for vid in env._agent_ids}

        def _run(vid: str, phase: str) -> _LoggingActionInterface:
            obs = build_restricted_observation(env.sim, vid)
            logger = _LoggingActionInterface(env.sim, actor_vehicle_id=vid)
            self.policy.on_decision(obs, logger, phase)
            return logger

        # Native OnlineSimulator two-phase on release (not a single request_release call).
        if reason == "request_release":
            for vid in list(env.sim.vehicles.keys()):
                lg = _run(vid, "bid_exchange")
                if lg.sent_rid:
                    sent[vid] = lg.sent_rid
            flush = getattr(env.sim, "_flush_zero_delay_task_bids", None)
            if callable(flush):
                flush()
            for vid in list(env.sim.vehicles.keys()):
                lg = _run(vid, "bid_assign")
                op, comm = self._map_op_comm(
                    tasks=task_lists.get(vid, []),
                    claimed_rid=lg.claimed_rid,
                    charged=lg.charged,
                    sent_rid=lg.sent_rid or sent.get(vid),
                    comm_enabled=env.comm_enabled,
                )
                out[vid] = (op, comm)
        else:
            for vid in list(env.sim.vehicles.keys()):
                lg = _run(vid, reason)
                op, comm = self._map_op_comm(
                    tasks=task_lists.get(vid, []),
                    claimed_rid=lg.claimed_rid,
                    charged=lg.charged,
                    sent_rid=lg.sent_rid,
                    comm_enabled=env.comm_enabled,
                )
                out[vid] = (op, comm)

        for vid in env._agent_ids:
            env._pending_obs[vid] = build_restricted_observation(env.sim, vid)
        return out

    def _actions_intent(self, env: RaceMultiAgentEnv) -> dict[str, tuple[int, int]]:
        from dataclasses import replace

        assert env.sim is not None
        reason = getattr(env, "_last_decision_reason", "epoch") or "epoch"
        # Map MARL idle/service epochs to a charge-eligible native reason.
        charge_reason = reason
        if reason in ("service_end", "vehicle_idle", "pickup_missed"):
            charge_reason = "epoch"

        task_lists = {
            vid: sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
            for vid, obs in env._pending_obs.items()
        }
        pending_obs = dict(env._pending_obs)
        out: dict[str, tuple[int, int]] = {
            vid: (OP_DEFER, COMM_SUPPRESS) for vid in env._agent_ids
        }
        soft_claimed: set[str] = set()
        sent: dict[str, str | None] = {vid: None for vid in env._agent_ids}

        if reason == "request_release":
            from race_casablanca.sim.policy_api import build_restricted_observation

            # Phase A: REAL bid_exchange (same bus state as native/execute).
            for vid in list(env.sim.vehicles.keys()):
                obs = build_restricted_observation(env.sim, vid)
                lg = _LoggingActionInterface(env.sim, actor_vehicle_id=vid)
                self.policy.on_decision(obs, lg, "bid_exchange")
                if lg.sent_rid:
                    sent[vid] = lg.sent_rid
            flush = getattr(env.sim, "_flush_zero_delay_task_bids", None)
            if callable(flush):
                flush()

            # Phase B: non-mutating bid_assign on refreshed obs + soft ownership.
            for vid in list(env.sim.vehicles.keys()):
                tasks = task_lists.get(vid, [])
                base = build_restricted_observation(env.sim, vid)
                if soft_claimed:
                    filtered = [t for t in base.announced if t.request_id not in soft_claimed]
                    obs = replace(base, announced=filtered)
                else:
                    obs = base
                logger = _IntentOnlyInterface(env.sim, actor_vehicle_id=vid)
                self.policy.on_decision(obs, logger, "bid_assign")
                op, _ = self._map_op_comm(
                    tasks=tasks,
                    claimed_rid=logger.claimed_rid,
                    charged=logger.charged,
                    sent_rid=None,
                    comm_enabled=False,
                )
                if op != OP_DEFER and logger.claimed_rid is not None:
                    soft_claimed.add(logger.claimed_rid)
                elif op == OP_DEFER and env._charge_action_legal(base):
                    if not base.announced or all(
                        t.request_id in soft_claimed for t in base.announced
                    ):
                        op = OP_CHARGE
                _, comm = self._map_op_comm(
                    tasks=tasks,
                    claimed_rid=None,
                    charged=False,
                    sent_rid=sent.get(vid),
                    comm_enabled=env.comm_enabled,
                )
                out[vid] = (op, comm)
                env._pending_obs[vid] = base
            # env.step must not re-send; claims only.
            env._comm_preflight_done = True
            return out

        for vid in list(env.sim.vehicles.keys()):
            tasks = task_lists.get(vid, [])
            base = pending_obs[vid]
            if soft_claimed:
                filtered = [t for t in base.announced if t.request_id not in soft_claimed]
                obs = replace(base, announced=filtered)
            else:
                obs = base
            logger = _IntentOnlyInterface(env.sim, actor_vehicle_id=vid)
            self.policy.on_decision(obs, logger, charge_reason)
            op, comm = self._map_op_comm(
                tasks=tasks,
                claimed_rid=logger.claimed_rid,
                charged=logger.charged,
                sent_rid=logger.sent_rid,
                comm_enabled=env.comm_enabled,
            )
            if op != OP_DEFER and logger.claimed_rid is not None:
                soft_claimed.add(logger.claimed_rid)
            elif op == OP_DEFER and env._charge_action_legal(env._pending_obs[vid]):
                if not env._pending_obs[vid].announced or all(
                    t.request_id in soft_claimed for t in env._pending_obs[vid].announced
                ):
                    op = OP_CHARGE
            out[vid] = (op, comm)
        return out

    def actions(self, env: RaceMultiAgentEnv) -> dict[str, tuple[int, int]]:
        if self.mode in ("execute", "intent_matched"):
            out = self._actions_execute(env)
            if self.mode == "intent_matched":
                # Native already applied; env.step should only flush legs + advance.
                env._comm_preflight_done = True
                env._ops_preflight_done = True
            return out
        return self._actions_intent(env)


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
    teacher: str = "native_execute",
    teacher_comm_mode: str = "selective",
) -> dict[str, np.ndarray]:
    """Collect BC labels.

    Preferred ``teacher='native_execute'``: real RaceCooperativePolicy mutations at
    MARL epochs (two-phase on release), then time advance without re-stepping.
    ``native_bridge`` = intent labels applied through ``env.step``.
    ``teacher_comm_mode='full'`` warms F toward B-level send rate (G4).
    """
    steps = env.reset(seed=seed)
    obs_l, op_l, comm_l, opm_l, cmm_l = [], [], [], [], []
    ep_seed = seed
    coop = CooperativeTeacherAdapter() if teacher == "cooperative" else None
    native_mode = None
    if teacher == "native_bridge":
        native_mode = "intent_matched"
    elif teacher == "native_execute":
        native_mode = "execute"
    native = (
        NativeBridgeTeacher(mode=native_mode, comm_mode=str(teacher_comm_mode))
        if native_mode
        else None
    )
    if coop is not None:
        coop.reset()
    if native is not None:
        native.reset()
    for _ in range(n_steps):
        if teacher == "cooperative":
            labels = cooperative_teacher_actions(env, coop)
            already_executed = False
        elif teacher in ("native_bridge", "native_execute"):
            labels = native_bridge_teacher_actions(env, native)
            # execute: advance without step; intent_matched: step only advances.
            already_executed = teacher == "native_execute"
        else:
            labels = greedy_teacher_actions(env)
            already_executed = False
        for vid, st in steps.items():
            obs_l.append(st.obs)
            op_l.append(labels[vid][0])
            # F training: only imitate sends that need energy-cert / contest.
            comm_a = int(labels[vid][1])
            if getattr(env, "ablation", "") == "F_race_marl":
                from race_casablanca.marl.env import COMM_SUPPRESS, K_TASKS
                from race_casablanca.sim.policy_api import ActionInterface

                obs = env._pending_obs.get(vid)
                if obs is not None and 0 <= comm_a < K_TASKS:
                    tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
                    if comm_a < len(tasks):
                        t = tasks[comm_a]
                        chk = ActionInterface(env.sim, actor_vehicle_id=vid).check_insertion(
                            vid, t.request_id
                        )
                        if not env._task_needs_energy_cert(obs, t, chk):
                            comm_a = COMM_SUPPRESS
            comm_l.append(comm_a)
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
    send_boost: float = 2.0,
) -> list[float]:
    """Imitate teacher op/comm. ``send_boost`` upweights non-suppress comm classes (G4)."""
    device = torch.device(device)
    actor = actor.to(device)
    opt = torch.optim.Adam(actor.parameters(), lr=lr)
    obs = torch.as_tensor(batch["obs"], device=device)
    op = torch.as_tensor(batch["op"], device=device)
    comm = torch.as_tensor(batch["comm"], device=device)
    opm = torch.as_tensor(batch["op_mask"], device=device)
    cmm = torch.as_tensor(batch["comm_mask"], device=device)
    op_w = None
    comm_w = None
    if class_weight:
        n_op = int(getattr(getattr(actor, "op_head", None), "out_features", int(op.max().item()) + 1))
        counts = np.bincount(batch["op"], minlength=n_op).astype(np.float32)
        w = counts.sum() / (counts + 1.0)
        w = w / max(float(w.mean()), 1e-6)
        op_w = torch.as_tensor(w, device=device)
        n_comm = int(
            getattr(getattr(actor, "comm_head", None), "out_features", int(comm.max().item()) + 1)
        )
        c_counts = np.bincount(batch["comm"], minlength=n_comm).astype(np.float32)
        cw = c_counts.sum() / (c_counts + 1.0)
        cw = cw / max(float(cw.mean()), 1e-6)
        # Boost every non-suppress class (suppress is last index = n_comm-1).
        if send_boost and float(send_boost) != 1.0 and n_comm > 1:
            cw = np.asarray(cw, dtype=np.float32).copy()
            cw[:-1] *= float(send_boost)
            cw = cw / max(float(cw.mean()), 1e-6)
        comm_w = torch.as_tensor(cw, device=device)
    losses = []
    for _ in range(epochs):
        op_logits, comm_logits = actor(obs, opm, cmm)
        loss = F.cross_entropy(op_logits, op, weight=op_w) + F.cross_entropy(
            comm_logits, comm, weight=comm_w
        )
        opt.zero_grad()
        loss.backward()
        opt.step()
        v = float(loss.item())
        losses.append(v if v == v and abs(v) != float("inf") else float("nan"))
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
    teacher_comm_mode: str = "selective",
) -> dict[str, np.ndarray]:
    """Roll out student; label states with teacher (DAgger-style)."""
    device = torch.device(device)
    actor = actor.to(device)
    actor.eval()
    coop = CooperativeTeacherAdapter() if teacher == "cooperative" else None
    # DAgger: student env.step must apply student ops — use soft intent labels only
    # (intent_matched would pre-apply native claims and ignore the student).
    label_teacher = (
        NativeBridgeTeacher(mode="intent", comm_mode=str(teacher_comm_mode))
        if teacher in ("native_bridge", "native_execute")
        else None
    )
    steps = env.reset(seed=seed)
    obs_l, op_l, comm_l, opm_l, cmm_l = [], [], [], [], []
    ep_seed = seed
    for _ in range(n_steps):
        if label_teacher is not None:
            labels = native_bridge_teacher_actions(env, label_teacher)
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
            if label_teacher is not None:
                label_teacher.reset()
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
