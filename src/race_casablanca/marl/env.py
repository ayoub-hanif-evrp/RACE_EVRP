"""Multi-agent adapter over OnlineSimulator for CTDE MAPPO (Stage 8.1).

Factorized actions: each agent may claim/defer/charge AND independently
send/suppress a task bid in the same decision epoch.

Messages update information only; they do not create unbounded extra physical
decision opportunities. Agents never receive privileged peer truth.
"""

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.policy_api import ActionInterface, RestrictedObservation, build_restricted_observation
from race_casablanca.sim.types import EventType, RequestStatus


K_TASKS = 5
# Operational: claim 0..K-1 | defer | charge
N_OP = K_TASKS + 2
OP_DEFER = K_TASKS
OP_CHARGE = K_TASKS + 1
# Communication: send bid for task 0..K-1 | suppress
N_COMM = K_TASKS + 1
COMM_SUPPRESS = K_TASKS

# Per-task feature width (own insertion + delivered peer-bid summary)
TASK_FEAT = 14
BASE_FEAT = 16

ABLATION_A = "A_no_comm"
ABLATION_B = "B_full_comm"
ABLATION_C = "C_random_matched"
ABLATION_D = "D_selective"
ABLATION_E = "E_selective_no_energy"
ABLATION_F = "F_race_marl"

MSG_COST = 0.001
COMM_COOLDOWN_S = 30.0
MAX_SENDS_PER_TASK = 2


@dataclass
class AgentStep:
    obs: np.ndarray
    op_mask: np.ndarray
    comm_mask: np.ndarray
    reward: float
    done: bool
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def mask(self) -> np.ndarray:
        """Legacy alias → operational mask."""
        return self.op_mask


class RaceMultiAgentEnv:
    """Semi-Markov multi-agent wrapper with factorized op/comm actions."""

    def __init__(
        self,
        *,
        scenario_factory,
        n_vehicles: int = 3,
        initial_soc: float = 0.35,
        message_delay_s: float = 0.0,
        packet_loss_p: float = 0.0,
        comm_enabled: bool = True,
        ablation: str = ABLATION_F,
        seed: int = 0,
        max_decisions: int = 500,
        random_send_p: float = 0.5,
        msg_cost: float = MSG_COST,
        dt_ref_s: float = 60.0,
        message_triggers_decision: bool = False,
    ):
        self.scenario_factory = scenario_factory
        self.n_vehicles = int(n_vehicles)
        self.initial_soc = float(initial_soc)
        self.message_delay_s = float(message_delay_s)
        self.packet_loss_p = float(packet_loss_p)
        self.ablation = str(ablation)
        self.comm_enabled = bool(comm_enabled) and self.ablation != ABLATION_A
        self.seed = int(seed)
        self.max_decisions = int(max_decisions)
        self.random_send_p = float(random_send_p)
        self.msg_cost = float(msg_cost)
        self.dt_ref_s = float(dt_ref_s)
        # Stage 8.1 default: delivered messages update info only.
        self.message_triggers_decision = bool(message_triggers_decision)
        self.sim: OnlineSimulator | None = None
        self._agent_ids: list[str] = []
        self._last_served = 0
        self._last_on_time = 0
        self._last_bid_msgs = 0
        self._n_decisions = 0
        self._pending_obs: dict[str, RestrictedObservation] = {}
        self._rng = random.Random(self.seed)
        self._n_send_actions = 0
        self._n_op_claims = 0
        self._n_op_charge = 0
        self._n_op_defer = 0
        self._n_comm_suppress = 0
        self._n_comm_opportunities = 0
        self._send_cooldown: dict[tuple[str, str], float] = {}
        self._send_counts: dict[tuple[str, str], int] = {}
        self._decision_t0 = 0.0
        self.obs_dim = BASE_FEAT + K_TASKS * TASK_FEAT
        self.n_op = N_OP
        self.n_comm = N_COMM
        self.n_actions = N_OP  # legacy

    def reset(self, seed: int | None = None) -> dict[str, AgentStep]:
        if seed is not None:
            self.seed = int(seed)
        self._rng = random.Random(self.seed)
        sc = self.scenario_factory(seed=self.seed, n_vehicles=self.n_vehicles)
        self.sim = OnlineSimulator(
            scenario_id=sc["scenario_id"],
            graph=sc["graph"],
            model=sc["model"],
            requests=sc["requests"],
            fleet={**sc["fleet"], "n_vehicles": self.n_vehicles},
            depot_node=sc["depot_node"],
            shift_start_s=sc["shift_start_s"],
            shift_end_s=sc["shift_end_s"],
            config=SimConfig(
                info_mode="restricted",
                seed=self.seed,
                initial_soc=self.initial_soc,
                n_vehicles=self.n_vehicles,
                message_delay_s=self.message_delay_s,
                packet_loss_p=self.packet_loss_p,
                packet_loss_seed=self.seed + 17,
                periodic_state_broadcast=False,
                decision_on_release=True,
                day=str(sc.get("day", "Monday")),
            ),
            policy=None,
        )
        self._agent_ids = list(self.sim.vehicles.keys())
        self._last_served = 0
        self._last_on_time = 0
        self._last_bid_msgs = 0
        self._n_decisions = 0
        self._n_send_actions = 0
        self._n_op_claims = 0
        self._n_op_charge = 0
        self._n_op_defer = 0
        self._n_comm_suppress = 0
        self._n_comm_opportunities = 0
        self._send_cooldown = {}
        self._send_counts = {}
        self._advance_to_decision()
        self._decision_t0 = float(self.sim.now_s)
        return self._observe_all(reward=0.0, done=False)

    def _advance_to_decision(self) -> bool:
        """Pop events until a physical decision point or episode end."""
        assert self.sim is not None
        sim = self.sim
        while sim._eq:
            ev = heapq.heappop(sim._eq)
            if ev.time_s + 1e-12 < sim.now_s:
                raise RuntimeError("event causality violated")
            sim.now_s = ev.time_s
            if ev.type == EventType.REQUEST_RELEASE:
                rid = ev.payload["request_id"]
                req = sim.requests[rid]
                if req.status == RequestStatus.UNRELEASED:
                    req.status = RequestStatus.AVAILABLE
                    return False
            elif ev.type == EventType.VEHICLE_ARRIVAL:
                sim._on_arrival(ev.payload["vehicle_id"])
            elif ev.type == EventType.SERVICE_END:
                sim._on_service_end(ev.payload["vehicle_id"], ev.payload["request_id"])
            elif ev.type == EventType.CHARGE_END:
                sim._on_charge_end(
                    ev.payload["vehicle_id"],
                    ev.payload["target_kwh"],
                    energy_delivered=float(ev.payload.get("energy_to_deliver_kwh", 0.0)),
                    duration_s=float(ev.payload.get("duration_s", 0.0)),
                )
                return False
            elif ev.type == EventType.MESSAGE_DELIVER:
                msg = next(m for m in sim.bus.history if m.msg_id == ev.payload["msg_id"])
                sim.bus.deliver(msg)
                if msg.kind == "task_bid":
                    sim._ingest_task_bid(msg.recipient, dict(msg.payload), sender=msg.sender)
                elif msg.kind == "state_update":
                    peer = msg.payload["vehicle_id"]
                    sim.local_views.setdefault(msg.recipient, {})[peer] = dict(msg.payload)
                # Default Stage 8.1: information update only (no extra decision).
                if self.message_triggers_decision:
                    return False
            elif ev.type == EventType.BID_ASSIGN_WINDOW:
                return False
            elif ev.type == EventType.SHIFT_END:
                sim._expire_open_requests()
            elif ev.type == EventType.EPISODE_END:
                return True
        return True

    def _peer_task_feats(self, obs: RestrictedObservation, request_id: str, now_s: float) -> list[float]:
        """Compact delivered peer-bid summary for one task (legal local info only)."""
        senders = (obs.peer_bids or {}).get(request_id, {}) or {}
        best_travel = 0.0
        best_energy = 0.0
        best_slack = 0.0
        best_age = 0.0
        any_valid = 0.0
        n_fresh = 0
        for payload in senders.values():
            if not payload:
                continue
            withdrawn = bool(payload.get("withdrawn", False))
            expires = float(payload.get("expires_s", -1.0))
            feasible = bool(payload.get("feasible", False))
            if withdrawn or (expires >= 0 and now_s > expires + 1e-9):
                continue
            n_fresh += 1
            if not feasible:
                continue
            travel = float(payload.get("marginal_travel_s", 0.0))
            energy = float(payload.get("energy_flex_kwh", 0.0))
            slack = float(payload.get("deadline_slack_s", 0.0))
            as_of = float(payload.get("as_of_s", now_s))
            age = max(0.0, now_s - as_of)
            if any_valid < 0.5 or travel < best_travel:
                best_travel = travel
                best_energy = energy
                best_slack = slack
                best_age = age
                any_valid = 1.0
        pending = 0.0
        if self.sim is not None and request_id in getattr(self.sim, "_pending_assign_requests", set()):
            pending = 1.0
        return [
            best_travel / 3600.0,
            best_energy / 40.0,
            best_slack / 3600.0,
            best_age / 120.0,
            any_valid,
            float(n_fresh) / 5.0,
            pending,
        ]

    def _encode(self, obs: RestrictedObservation) -> tuple[np.ndarray, np.ndarray, np.ndarray, list]:
        assert self.sim is not None
        v = obs.self_state
        shift_left = max(0.0, float(self.sim.shift_end_s - obs.now_s) / 28800.0)
        feats = [
            float(v.battery_kwh) / 40.0,
            float(v.load_kg) / 600.0,
            1.0 if v.busy else 0.0,
            float(len(v.committed)) / 10.0,
            float(obs.now_s) / 28800.0,
            shift_left,
            float(len(obs.announced)) / 40.0,
            float(len(obs.peer_bids)) / 40.0,
            1.0 if self.comm_enabled else 0.0,
            float(self.message_delay_s) / 120.0,
            float(self.packet_loss_p),
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ]
        if self.ablation == ABLATION_E:
            feats[0] = 0.0
        tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
        op_mask = np.zeros(N_OP, dtype=np.float32)
        comm_mask = np.zeros(N_COMM, dtype=np.float32)
        op_mask[OP_DEFER] = 1.0
        op_mask[OP_CHARGE] = 1.0
        comm_mask[COMM_SUPPRESS] = 1.0
        task_feats: list[float] = []
        actions = ActionInterface(self.sim, actor_vehicle_id=obs.vehicle_id)
        for i in range(K_TASKS):
            if i < len(tasks):
                t = tasks[i]
                chk = actions.check_insertion(obs.vehicle_id, t.request_id)
                own = [
                    1.0,
                    float(chk.feasible),
                    float(chk.marginal_travel_s or 0.0) / 3600.0,
                    float(chk.energy_flex_kwh or 0.0) / 40.0,
                    float(chk.min_deadline_slack_s or 0.0) / 3600.0,
                    (float(t.tw_end_s) - float(obs.now_s)) / 3600.0,
                ]
                peer = self._peer_task_feats(obs, t.request_id, float(obs.now_s))
                # own_vs_best travel delta (positive ⇒ peer cheaper)
                own_travel = float(chk.marginal_travel_s or 0.0) / 3600.0
                peer_travel = peer[0]
                delta = (own_travel - peer_travel) if peer[4] > 0.5 else 0.0
                row = own + peer + [delta]
                assert len(row) == TASK_FEAT
                if self.ablation == ABLATION_E:
                    row[3] = 0.0
                    row[7] = 0.0
                task_feats.extend(row)
                if chk.feasible:
                    op_mask[i] = 1.0
                if self.comm_enabled and chk.feasible:
                    key = (obs.vehicle_id, t.request_id)
                    cool_ok = float(obs.now_s) >= self._send_cooldown.get(key, -1e18)
                    count_ok = self._send_counts.get(key, 0) < MAX_SENDS_PER_TASK
                    if cool_ok and count_ok:
                        if self.ablation == ABLATION_B:
                            comm_mask[i] = 1.0
                            # Full-comm: suppress remains available but policy can be forced.
                        else:
                            comm_mask[i] = 1.0
            else:
                task_feats.extend([0.0] * TASK_FEAT)
        if not self.comm_enabled:
            comm_mask[:] = 0.0
            comm_mask[COMM_SUPPRESS] = 1.0
        vec = np.asarray(feats + task_feats, dtype=np.float32)
        assert vec.shape[0] == self.obs_dim
        return vec, op_mask, comm_mask, tasks

    def _observe_all(self, reward: float, done: bool) -> dict[str, AgentStep]:
        assert self.sim is not None
        out = {}
        self._pending_obs = {}
        for vid in self._agent_ids:
            obs = build_restricted_observation(self.sim, vid)
            self._pending_obs[vid] = obs
            vec, op_m, comm_m, _ = self._encode(obs)
            out[vid] = AgentStep(obs=vec, op_mask=op_m, comm_mask=comm_m, reward=reward, done=done, info={})
        return out

    def _can_send(self, vid: str, request_id: str, now_s: float) -> bool:
        key = (vid, request_id)
        if self._send_counts.get(key, 0) >= MAX_SENDS_PER_TASK:
            return False
        if now_s < self._send_cooldown.get(key, -1e18):
            return False
        return True

    def _send_bid(self, vid: str, obs: RestrictedObservation, task) -> bool:
        if not self.comm_enabled:
            return False
        from race_casablanca.coordination.task_bids import compute_self_bid

        if not self._can_send(vid, task.request_id, float(obs.now_s)):
            return False
        act = ActionInterface(self.sim, actor_vehicle_id=vid)
        bid = compute_self_bid(obs, act, task)
        if not bid.feasible:
            return False
        payload = bid.to_payload()
        if self.ablation == ABLATION_E:
            for k in ("energy_flex_kwh", "energy_cost_kwh", "residual_energy_kwh", "charge_burden_s"):
                if k in payload:
                    payload[k] = 0.0
        act.broadcast_task_bid(vid, payload)
        key = (vid, task.request_id)
        self._send_counts[key] = self._send_counts.get(key, 0) + 1
        self._send_cooldown[key] = float(obs.now_s) + COMM_COOLDOWN_S
        self._n_send_actions += 1
        return True

    def step(self, actions: dict[str, tuple[int, int] | int]) -> dict[str, AgentStep]:
        """Execute factorized (op, comm) actions for each agent.

        Legacy callers may pass a single int (operational only → suppress).
        """
        assert self.sim is not None
        self._n_decisions += 1
        t_before = float(self.sim.now_s)

        for vid, raw in actions.items():
            if isinstance(raw, tuple):
                op_a, comm_a = int(raw[0]), int(raw[1])
            else:
                op_a, comm_a = int(raw), COMM_SUPPRESS
            obs = self._pending_obs[vid]
            act = ActionInterface(self.sim, actor_vehicle_id=vid)
            tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]

            # --- Operational head ---
            if op_a < K_TASKS and op_a < len(tasks):
                rid = tasks[op_a].request_id
                chk = act.check_insertion(vid, rid)
                if chk.feasible:
                    act.claim_task(vid, rid)
                    self._n_op_claims += 1
            elif op_a == OP_CHARGE:
                act.request_return_depot(vid, charge=True, target_soc=0.70)
                self._n_op_charge += 1
            else:
                self._n_op_defer += 1

            # --- Communication head (independent of operational choice) ---
            if self.comm_enabled and tasks:
                self._n_comm_opportunities += 1
                do_send = False
                send_idx = 0
                if self.ablation == ABLATION_B:
                    # Full communication: always send best feasible top task bid.
                    do_send = True
                    send_idx = 0
                elif self.ablation == ABLATION_C:
                    do_send = self._rng.random() < self.random_send_p
                    send_idx = 0
                elif 0 <= comm_a < K_TASKS:
                    do_send = True
                    send_idx = comm_a
                else:
                    self._n_comm_suppress += 1
                if do_send and send_idx < len(tasks):
                    self._send_bid(vid, obs, tasks[send_idx])

        # Advance physics / messages, THEN account incremental reward.
        done = self._advance_to_decision()
        truncated_budget = False
        if self._n_decisions >= self.max_decisions:
            done = True
            truncated_budget = True

        if done:
            # Drain remaining events without further agent control.
            while self.sim._eq:
                if self._advance_to_decision():
                    break

        served = sum(1 for r in self.sim.requests.values() if r.status == RequestStatus.COMPLETED)
        on_time = sum(
            1
            for r in self.sim.requests.values()
            if r.status == RequestStatus.COMPLETED and r.on_time
        )
        bid_msgs = int(self.sim.n_bid_messages)
        delta_ot = float(on_time - self._last_on_time)
        delta_served = float(served - self._last_served)
        delta_msgs = float(bid_msgs - self._last_bid_msgs)
        # Primary: on-time completions; secondary: any completion; tiny incremental msg cost.
        team_r = 1.0 * delta_ot + 0.1 * max(0.0, delta_served - delta_ot) - self.msg_cost * delta_msgs
        self._last_served = served
        self._last_on_time = on_time
        self._last_bid_msgs = bid_msgs

        elapsed = max(0.0, float(self.sim.now_s) - t_before)
        out = self._observe_all(reward=team_r, done=done)
        for st in out.values():
            st.info["elapsed_s"] = elapsed
            st.info["truncated_budget"] = truncated_budget
            st.info["delta_on_time"] = delta_ot
            st.info["delta_messages"] = delta_msgs
        if not done:
            self._decision_t0 = float(self.sim.now_s)
        return out

    def final_metrics(self) -> dict[str, Any]:
        assert self.sim is not None
        m = self.sim._metrics().to_dict()
        m["n_send_actions"] = self._n_send_actions
        m["n_op_claims"] = self._n_op_claims
        m["n_op_charge"] = self._n_op_charge
        m["n_op_defer"] = self._n_op_defer
        m["n_comm_suppress"] = self._n_comm_suppress
        m["n_comm_opportunities"] = self._n_comm_opportunities
        m["n_decisions"] = self._n_decisions
        m["ablation"] = self.ablation
        m["obs_dim"] = self.obs_dim
        m["task_feat"] = TASK_FEAT
        m["message_triggers_decision"] = self.message_triggers_decision
        return m
