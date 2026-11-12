"""Multi-agent adapter over OnlineSimulator for CTDE MAPPO (Stage 8.2).

Decision epoch protocol (bid-before-commit):
  1. Agents propose operational + communication actions from current local obs.
  2. Communication (task bids) executes first; zero-delay deliveries ingest immediately.
  3. Contested claims are resolved in a batched, vehicle-order-invariant way.
  4. Fresh feasibility is checked at commitment; physics advances afterward.

F_race_marl vs D_selective:
  D — free learned selective send/suppress on any feasible announced task.
  F — energy-certified decision-relevant communication: send mask is enabled
      only for contested / energy-critical tasks; payloads always carry the
      conservative energy-feasibility certificate used by peers for ranking.

E_selective_no_energy keeps the EV's own battery observation; only peer
energy certificate fields are stripped from messages and peer features.

B/C externally control communication; the env records executed_comm and
comm_learnable=False so PPO does not credit unexecuted sampled comm actions.
"""

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from race_casablanca.coordination.task_bids import TaskBid, compute_self_bid, self_should_claim
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.policy_api import ActionInterface, RestrictedObservation, build_restricted_observation
from race_casablanca.sim.types import EventType, RequestStatus, VehicleMode


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
# F: energy certificate is decision-relevant below this residual flex (kWh)
ENERGY_CERT_THRESHOLD_KWH = 8.0
# F: tight deadline slack also counts as contested (seconds)
CONTEST_DEADLINE_SLACK_S = 300.0


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
        matched_send_p: float | None = None,
        msg_cost: float = MSG_COST,
        dt_ref_s: float = 60.0,
        message_triggers_decision: bool = False,
        energy_cert_threshold_kwh: float = ENERGY_CERT_THRESHOLD_KWH,
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
        # C: matched-budget random uses predeclared p (from selective calibration), not post-hoc.
        self.random_send_p = float(random_send_p if matched_send_p is None else matched_send_p)
        self.matched_send_p = float(self.random_send_p)
        self.msg_cost = float(msg_cost)
        self.dt_ref_s = float(dt_ref_s)
        self.message_triggers_decision = bool(message_triggers_decision)
        self.energy_cert_threshold_kwh = float(energy_cert_threshold_kwh)
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
        self._n_msgs_before_commit = 0
        self._n_batched_conflicts = 0
        self._n_claim_defers_to_peer = 0
        self._send_cooldown: dict[tuple[str, str], float] = {}
        self._send_counts: dict[tuple[str, str], int] = {}
        self._decision_t0 = 0.0
        self._last_executed_comm: dict[str, int] = {}
        self._last_comm_learnable: dict[str, bool] = {}
        self._pending_autoleg: set[str] = set()
        self._last_decision_reason: str = "reset"
        self._n_decision_service_end = 0
        self._n_decision_vehicle_idle = 0
        self._n_decision_charge_end = 0
        self._n_decision_release = 0
        self._n_second_choice_claims = 0
        self._n_idle_with_pending = 0
        self._n_missed_feasible_pickup = 0
        self._n_claim_attempts = 0
        self._n_duplicate_task_proposals = 0
        self.obs_dim = BASE_FEAT + K_TASKS * TASK_FEAT
        self.n_op = N_OP
        self.n_comm = N_COMM
        self.n_actions = N_OP  # legacy
        # Charge-to target matches non-learning readiness charge
        self.charge_target_soc = 0.70

    @property
    def comm_externally_controlled(self) -> bool:
        """True when communication is forced (B) or externally randomized (C)."""
        return self.ablation in (ABLATION_B, ABLATION_C)

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
        self._n_msgs_before_commit = 0
        self._n_batched_conflicts = 0
        self._n_claim_defers_to_peer = 0
        self._send_cooldown = {}
        self._send_counts = {}
        self._last_executed_comm = {}
        self._last_comm_learnable = {}
        self._pending_autoleg = set()
        self._last_decision_reason = "reset"
        self._n_decision_service_end = 0
        self._n_decision_vehicle_idle = 0
        self._n_decision_charge_end = 0
        self._n_decision_release = 0
        self._n_second_choice_claims = 0
        self._n_idle_with_pending = 0
        self._n_missed_feasible_pickup = 0
        self._n_claim_attempts = 0
        self._n_duplicate_task_proposals = 0
        self._advance_to_decision()
        self._decision_t0 = float(self.sim.now_s)
        return self._observe_all(reward=0.0, done=False)

    def _suppress_autoleg(self):
        """Context: run native event handlers without immediately starting next legs.

        Native sim calls ``_maybe_decide`` then ``_start_next_leg``. With policy=None
        the decide is a no-op; we still must defer ``_start_next_leg`` until after the
        MARL step so agents can claim/charge while idle — matching native timing.
        """
        assert self.sim is not None
        sim = self.sim
        orig = sim._start_next_leg

        def _noop(vehicle_id: str) -> None:
            self._pending_autoleg.add(vehicle_id)

        sim._start_next_leg = _noop  # type: ignore[method-assign]
        return orig

    def _restore_autoleg(self, orig) -> None:
        assert self.sim is not None
        self.sim._start_next_leg = orig  # type: ignore[method-assign]

    def _flush_autoleg(self) -> None:
        assert self.sim is not None
        pending = sorted(self._pending_autoleg)
        self._pending_autoleg.clear()
        for vid in pending:
            v = self.sim.vehicles[vid]
            if v.busy:
                continue
            self.sim._start_next_leg(vid)

    def _vehicle_idle_for_decision(self, vehicle_id: str) -> bool:
        assert self.sim is not None
        v = self.sim.vehicles[vehicle_id]
        from race_casablanca.sim.types import VehicleMode

        return (not v.busy) and v.mode == VehicleMode.IDLE

    def _advance_to_decision(self) -> bool:
        """Pop events until a physical decision point or episode end.

        Decision parity with native ``_maybe_decide`` triggers (except message-only
        info updates): request_release, service_end, vehicle_idle, charge_end,
        bid_assign, pickup_missed. Same-time events are processed until a trigger;
        agents then act; ``_flush_autoleg`` starts next legs afterward.
        """
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
                    self._last_decision_reason = "request_release"
                    self._n_decision_release += 1
                    return False
            elif ev.type == EventType.VEHICLE_ARRIVAL:
                vid = ev.payload["vehicle_id"]
                orig = self._suppress_autoleg()
                try:
                    sim._on_arrival(vid)
                finally:
                    self._restore_autoleg(orig)
                if self._vehicle_idle_for_decision(vid):
                    self._last_decision_reason = "vehicle_idle"
                    self._n_decision_vehicle_idle += 1
                    return False
            elif ev.type == EventType.SERVICE_END:
                vid = ev.payload["vehicle_id"]
                orig = self._suppress_autoleg()
                try:
                    sim._on_service_end(vid, ev.payload["request_id"])
                finally:
                    self._restore_autoleg(orig)
                if self._vehicle_idle_for_decision(vid):
                    self._last_decision_reason = "service_end"
                    self._n_decision_service_end += 1
                    return False
            elif ev.type == EventType.CHARGE_END:
                vid = ev.payload["vehicle_id"]
                orig = self._suppress_autoleg()
                try:
                    sim._on_charge_end(
                        vid,
                        ev.payload["target_kwh"],
                        energy_delivered=float(ev.payload.get("energy_to_deliver_kwh", 0.0)),
                        duration_s=float(ev.payload.get("duration_s", 0.0)),
                    )
                finally:
                    self._restore_autoleg(orig)
                self._last_decision_reason = "charge_end"
                self._n_decision_charge_end += 1
                return False
            elif ev.type == EventType.MESSAGE_DELIVER:
                msg = next(m for m in sim.bus.history if m.msg_id == ev.payload["msg_id"])
                sim.bus.deliver(msg)
                if msg.kind == "task_bid":
                    sim._ingest_task_bid(msg.recipient, dict(msg.payload), sender=msg.sender)
                elif msg.kind == "state_update":
                    peer = msg.payload["vehicle_id"]
                    sim.local_views.setdefault(msg.recipient, {})[peer] = dict(msg.payload)
                # Information only by default (parity with Stage 8.1 fairness).
                if self.message_triggers_decision:
                    self._last_decision_reason = "message"
                    return False
            elif ev.type == EventType.BID_ASSIGN_WINDOW:
                self._last_decision_reason = "bid_assign"
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
        # E keeps own battery; only peer energy certificate content is ablated.
        tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
        op_mask = np.zeros(N_OP, dtype=np.float32)
        comm_mask = np.zeros(N_COMM, dtype=np.float32)
        op_mask[OP_DEFER] = 1.0
        if self._charge_action_legal(obs):
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
                own_travel = float(chk.marginal_travel_s or 0.0) / 3600.0
                peer_travel = peer[0]
                delta = (own_travel - peer_travel) if peer[4] > 0.5 else 0.0
                row = own + peer + [delta]
                assert len(row) == TASK_FEAT
                if self.ablation == ABLATION_E:
                    row[7] = 0.0  # peer energy_flex only
                task_feats.extend(row)
                if chk.feasible:
                    op_mask[i] = 1.0
                if self.comm_enabled and chk.feasible:
                    key = (obs.vehicle_id, t.request_id)
                    cool_ok = float(obs.now_s) >= self._send_cooldown.get(key, -1e18)
                    count_ok = self._send_counts.get(key, 0) < MAX_SENDS_PER_TASK
                    if cool_ok and count_ok:
                        if self.ablation == ABLATION_F:
                            if self._task_needs_energy_cert(obs, t, chk):
                                comm_mask[i] = 1.0
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

    def _task_needs_energy_cert(self, obs: RestrictedObservation, task, chk) -> bool:
        peer_senders = (obs.peer_bids or {}).get(task.request_id, {}) or {}
        if peer_senders:
            return True
        flex = float(chk.energy_flex_kwh or 0.0)
        if flex < self.energy_cert_threshold_kwh:
            return True
        slack = float(chk.min_deadline_slack_s or 0.0)
        if slack < CONTEST_DEADLINE_SLACK_S:
            return True
        if self.sim is not None and task.request_id in getattr(self.sim, "_pending_assign_requests", set()):
            return True
        return False

    def _charge_action_legal(self, obs: RestrictedObservation) -> bool:
        """Charge only when idle, not already charging/en-route, and SOC needs it.

        Matches non-learning readiness charge spirit: do not offer charge when a
        feasible announced pickup exists, or when the vehicle is physically busy.
        Depot return preserves existing pickup commitments (simulator fix).
        """
        assert self.sim is not None
        from race_casablanca.sim.types import VehicleMode

        v = self.sim.vehicles[obs.vehicle_id]
        if v.busy or v.mode in (VehicleMode.SERVING, VehicleMode.CHARGING, VehicleMode.EN_ROUTE):
            return False
        if v.mode == VehicleMode.EMERGENCY_STRANDED:
            return False
        bat = float(obs.self_state.battery_kwh)
        target = self.charge_target_soc * 40.0
        if bat >= target - 1e-6:
            return False
        # If any announced task is feasible, prefer service over readiness charge.
        act = ActionInterface(self.sim, actor_vehicle_id=obs.vehicle_id)
        for t in obs.announced:
            if act.check_insertion(obs.vehicle_id, t.request_id).feasible:
                return False
        return True

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
        if not self._can_send(vid, task.request_id, float(obs.now_s)):
            return False
        act = ActionInterface(self.sim, actor_vehicle_id=vid)
        bid = compute_self_bid(obs, act, task)
        if not bid.feasible:
            return False
        payload = bid.to_payload()
        if self.ablation == ABLATION_F:
            payload["energy_certificate"] = True
            payload["race_mechanism"] = "energy_certified_contest"
        if self.ablation == ABLATION_E:
            for k in (
                "energy_flex_kwh",
                "energy_cost_kwh",
                "residual_energy_kwh",
                "charge_burden_s",
                "marginal_energy_kwh",
            ):
                if k in payload:
                    payload[k] = 0.0
            payload["energy_certificate"] = False
        act.broadcast_task_bid(vid, payload)
        key = (vid, task.request_id)
        self._send_counts[key] = self._send_counts.get(key, 0) + 1
        self._send_cooldown[key] = float(obs.now_s) + COMM_COOLDOWN_S
        self._n_send_actions += 1
        return True

    def _resolve_comm_action(
        self, vid: str, comm_a: int, tasks: list, obs: RestrictedObservation
    ) -> tuple[int, bool]:
        if not self.comm_enabled or not tasks:
            return COMM_SUPPRESS, False
        self._n_comm_opportunities += 1
        if self.ablation == ABLATION_B:
            for i, t in enumerate(tasks):
                act = ActionInterface(self.sim, actor_vehicle_id=vid)
                chk = act.check_insertion(vid, t.request_id)
                if chk.feasible and self._can_send(vid, t.request_id, float(obs.now_s)):
                    return i, False
            return COMM_SUPPRESS, False
        if self.ablation == ABLATION_C:
            if self._rng.random() < self.matched_send_p:
                for i, t in enumerate(tasks):
                    act = ActionInterface(self.sim, actor_vehicle_id=vid)
                    chk = act.check_insertion(vid, t.request_id)
                    if chk.feasible and self._can_send(vid, t.request_id, float(obs.now_s)):
                        return i, False
            return COMM_SUPPRESS, False
        if 0 <= comm_a < K_TASKS and comm_a < len(tasks):
            return int(comm_a), True
        self._n_comm_suppress += 1
        return COMM_SUPPRESS, True

    def _batched_resolve_claims(self, proposals: dict[str, dict[str, Any]]) -> None:
        assert self.sim is not None
        fresh_obs = {vid: build_restricted_observation(self.sim, vid) for vid in proposals}
        by_rid: dict[str, list[tuple[str, int, TaskBid]]] = {}
        charge_vids: list[str] = []
        defer_vids: list[str] = []
        for vid in sorted(proposals.keys()):
            prop = proposals[vid]
            op_a = int(prop["op"])
            tasks = prop["tasks"]
            obs = fresh_obs[vid]
            act = ActionInterface(self.sim, actor_vehicle_id=vid)
            if op_a < K_TASKS and op_a < len(tasks):
                task = tasks[op_a]
                rid = task.request_id
                chk = act.check_insertion(vid, rid)
                if not chk.feasible:
                    defer_vids.append(vid)
                    continue
                own = compute_self_bid(obs, act, task)
                peers_raw = (obs.peer_bids or {}).get(rid, {}) or {}
                peers: list[TaskBid] = []
                for sid, payload in peers_raw.items():
                    if sid == vid or not payload:
                        continue
                    try:
                        peers.append(TaskBid.from_payload(payload))
                    except (KeyError, TypeError, ValueError):
                        continue
                if peers and not self_should_claim(own, peers, now_s=float(obs.now_s)):
                    self._n_claim_defers_to_peer += 1
                    defer_vids.append(vid)
                    continue
                by_rid.setdefault(rid, []).append((vid, op_a, own))
            elif op_a == OP_CHARGE:
                charge_vids.append(vid)
            else:
                defer_vids.append(vid)
        winners: set[str] = set()
        awarded_rids: set[str] = set()
        losers: list[str] = []
        for rid in sorted(by_rid.keys()):
            cand = by_rid[rid]
            if len(cand) > 1:
                self._n_batched_conflicts += 1
            ranked = sorted(
                cand,
                key=lambda x: (float(x[2].marginal_travel_s), -float(x[2].energy_flex_kwh), x[0]),
            )
            got = False
            for vid, _op, _bid in ranked:
                if vid in winners:
                    continue
                act = ActionInterface(self.sim, actor_vehicle_id=vid)
                chk = act.check_insertion(vid, rid)
                if not chk.feasible:
                    continue
                if act.claim_task(vid, rid):
                    self._n_op_claims += 1
                    winners.add(vid)
                    awarded_rids.add(rid)
                    got = True
                    break
            for vid, _, _ in cand:
                if vid not in winners:
                    losers.append(vid)
        # Second-choice: losers may claim another feasible announced task (local info only).
        for vid in sorted(set(losers)):
            if vid in winners or vid in charge_vids:
                continue
            prop = proposals[vid]
            obs = fresh_obs[vid]
            act = ActionInterface(self.sim, actor_vehicle_id=vid)
            tasks = prop["tasks"]
            for i, task in enumerate(tasks):
                rid = task.request_id
                if rid in awarded_rids:
                    continue
                chk = act.check_insertion(vid, rid)
                if not chk.feasible:
                    continue
                own = compute_self_bid(obs, act, task)
                peers_raw = (obs.peer_bids or {}).get(rid, {}) or {}
                peers = []
                for sid, payload in peers_raw.items():
                    if sid == vid or not payload:
                        continue
                    try:
                        peers.append(TaskBid.from_payload(payload))
                    except (KeyError, TypeError, ValueError):
                        continue
                if peers and not self_should_claim(own, peers, now_s=float(obs.now_s)):
                    continue
                if act.claim_task(vid, rid):
                    self._n_op_claims += 1
                    self._n_second_choice_claims += 1
                    winners.add(vid)
                    awarded_rids.add(rid)
                    break
            if vid not in winners:
                defer_vids.append(vid)
        for vid in charge_vids:
            if vid in winners:
                continue
            # Honor mask: only charge if still legal after bid refresh
            if not self._charge_action_legal(fresh_obs[vid]):
                defer_vids.append(vid)
                continue
            act = ActionInterface(self.sim, actor_vehicle_id=vid)
            act.request_return_depot(vid, charge=True, target_soc=self.charge_target_soc)
            self._n_op_charge += 1
        for vid in defer_vids:
            if vid not in winners and vid not in charge_vids:
                self._n_op_defer += 1

    def step(self, actions: dict[str, tuple[int, int] | int]) -> dict[str, AgentStep]:
        assert self.sim is not None
        self._n_decisions += 1
        t_before = float(self.sim.now_s)
        msgs_before = int(self.sim.n_bid_messages)
        proposals: dict[str, dict[str, Any]] = {}
        pending_available = [
            r
            for r in self.sim.requests.values()
            if r.status == RequestStatus.AVAILABLE and r.owner is None
        ]
        for vid, raw in actions.items():
            if isinstance(raw, tuple):
                op_a, comm_a = int(raw[0]), int(raw[1])
            else:
                op_a, comm_a = int(raw), COMM_SUPPRESS
            # Clamp illegal charge to defer
            if op_a == OP_CHARGE and not self._charge_action_legal(self._pending_obs[vid]):
                op_a = OP_DEFER
            obs = self._pending_obs[vid]
            tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
            # Diagnostics: idle with serviceable pending, claim attempts, missed feasible
            vstate = self.sim.vehicles[vid]
            if (not vstate.busy) and vstate.mode == VehicleMode.IDLE and pending_available:
                act_chk = ActionInterface(self.sim, actor_vehicle_id=vid)
                if any(act_chk.check_insertion(vid, r.request_id).feasible for r in pending_available):
                    self._n_idle_with_pending += 1
            if 0 <= op_a < K_TASKS:
                self._n_claim_attempts += 1
            elif op_a in (OP_DEFER, OP_CHARGE) and tasks:
                act_chk = ActionInterface(self.sim, actor_vehicle_id=vid)
                if any(act_chk.check_insertion(vid, t.request_id).feasible for t in tasks):
                    self._n_missed_feasible_pickup += 1
            proposals[vid] = {"op": op_a, "comm_proposed": comm_a, "tasks": tasks, "obs": obs}
        # Duplicate simultaneous proposals for the same request id
        claimed_idxs: dict[str, int] = {}
        for vid, prop in proposals.items():
            op_a = int(prop["op"])
            tasks = prop["tasks"]
            if 0 <= op_a < K_TASKS and op_a < len(tasks):
                rid = tasks[op_a].request_id
                claimed_idxs[rid] = claimed_idxs.get(rid, 0) + 1
        self._n_duplicate_task_proposals += sum(1 for c in claimed_idxs.values() if c > 1)
        self._last_executed_comm = {}
        self._last_comm_learnable = {}
        for vid in sorted(proposals.keys()):
            prop = proposals[vid]
            exec_comm, learnable = self._resolve_comm_action(
                vid, prop["comm_proposed"], prop["tasks"], prop["obs"]
            )
            self._last_executed_comm[vid] = exec_comm
            self._last_comm_learnable[vid] = learnable
            if 0 <= exec_comm < K_TASKS and exec_comm < len(prop["tasks"]):
                self._send_bid(vid, prop["obs"], prop["tasks"][exec_comm])
        # Two-phase parity with native RaceCooperativePolicy: deliver zero-delay
        # bids before ownership resolution so peer certificates are visible.
        flush = getattr(self.sim, "_flush_zero_delay_task_bids", None)
        if callable(flush):
            flush()
        self._n_msgs_before_commit += max(0, int(self.sim.n_bid_messages) - msgs_before)
        self._batched_resolve_claims(proposals)
        # After claims/charges, start deferred next legs (native post-decide timing).
        self._flush_autoleg()
        done = self._advance_to_decision()
        truncated_budget = False
        if self._n_decisions >= self.max_decisions:
            done = True
            truncated_budget = True
        if done:
            # Drain without further agent control; still flush legs after each trigger.
            while self.sim._eq:
                self._flush_autoleg()
                if self._advance_to_decision():
                    break
            self._flush_autoleg()
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
        team_r = 1.0 * delta_ot + 0.1 * max(0.0, delta_served - delta_ot) - self.msg_cost * delta_msgs
        self._last_served = served
        self._last_on_time = on_time
        self._last_bid_msgs = bid_msgs
        elapsed = max(0.0, float(self.sim.now_s) - t_before)
        out = self._observe_all(reward=team_r, done=done)
        for vid, st in out.items():
            st.info["elapsed_s"] = elapsed
            st.info["truncated_budget"] = truncated_budget
            st.info["delta_on_time"] = delta_ot
            st.info["delta_messages"] = delta_msgs
            st.info["executed_comm"] = int(self._last_executed_comm.get(vid, COMM_SUPPRESS))
            st.info["comm_learnable"] = bool(self._last_comm_learnable.get(vid, False))
            st.info["comm_externally_controlled"] = self.comm_externally_controlled
            st.info["msgs_before_commit_step"] = max(0, int(self.sim.n_bid_messages) - msgs_before)
            st.info["decision_reason"] = self._last_decision_reason
        if not done:
            self._decision_t0 = float(self.sim.now_s)
        return out

    def final_metrics(self) -> dict[str, Any]:
        assert self.sim is not None
        m = self.sim._metrics().to_dict()
        m["n_bid_messages"] = int(getattr(self.sim, "n_bid_messages", 0) or 0)
        m["n_bid_bytes"] = int(getattr(self.sim, "n_bid_bytes", 0) or 0)
        m["n_send_actions"] = self._n_send_actions
        m["n_op_claims"] = self._n_op_claims
        m["n_op_charge"] = self._n_op_charge
        m["n_op_defer"] = self._n_op_defer
        m["n_comm_suppress"] = self._n_comm_suppress
        m["n_comm_opportunities"] = self._n_comm_opportunities
        m["n_msgs_before_commit"] = self._n_msgs_before_commit
        m["n_batched_conflicts"] = self._n_batched_conflicts
        m["n_claim_defers_to_peer"] = self._n_claim_defers_to_peer
        m["n_second_choice_claims"] = self._n_second_choice_claims
        m["n_idle_with_pending"] = self._n_idle_with_pending
        m["n_missed_feasible_pickup"] = self._n_missed_feasible_pickup
        m["n_claim_attempts"] = self._n_claim_attempts
        m["n_duplicate_task_proposals"] = self._n_duplicate_task_proposals
        m["n_decisions"] = self._n_decisions
        m["n_decision_service_end"] = self._n_decision_service_end
        m["n_decision_vehicle_idle"] = self._n_decision_vehicle_idle
        m["n_decision_charge_end"] = self._n_decision_charge_end
        m["n_decision_release"] = self._n_decision_release
        m["ablation"] = self.ablation
        m["obs_dim"] = self.obs_dim
        m["task_feat"] = TASK_FEAT
        m["message_triggers_decision"] = self.message_triggers_decision
        m["matched_send_p"] = self.matched_send_p
        m["comm_externally_controlled"] = self.comm_externally_controlled
        return m
