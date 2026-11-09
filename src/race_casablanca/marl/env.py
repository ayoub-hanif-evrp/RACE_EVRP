"""Multi-agent adapter over OnlineSimulator for CTDE MAPPO.

Event-driven simulator is stepped via decision epochs. Agents never receive the
mutable simulator or privileged peer truth — only local obs + delivered bids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.policy_api import ActionInterface, RestrictedObservation, build_restricted_observation
from race_casablanca.sim.types import EventType, RequestStatus


K_TASKS = 5
# Actions: claim task 0..K-1 | defer | charge | send_bid_for_top | suppress
N_ACTIONS = K_TASKS + 4
ACT_DEFER = K_TASKS
ACT_CHARGE = K_TASKS + 1
ACT_SEND = K_TASKS + 2
ACT_SUPPRESS = K_TASKS + 3


@dataclass
class AgentStep:
    obs: np.ndarray
    mask: np.ndarray
    reward: float
    done: bool
    info: dict[str, Any]


class RaceMultiAgentEnv:
    """Semi-Markov multi-agent wrapper: decisions at request/message/charge events."""

    def __init__(
        self,
        *,
        scenario_factory,
        n_vehicles: int = 3,
        initial_soc: float = 0.35,
        message_delay_s: float = 0.0,
        comm_enabled: bool = True,
        seed: int = 0,
        max_decisions: int = 500,
    ):
        self.scenario_factory = scenario_factory
        self.n_vehicles = int(n_vehicles)
        self.initial_soc = float(initial_soc)
        self.message_delay_s = float(message_delay_s)
        self.comm_enabled = bool(comm_enabled)
        self.seed = int(seed)
        self.max_decisions = int(max_decisions)
        self.sim: OnlineSimulator | None = None
        self._agent_ids: list[str] = []
        self._last_served = 0
        self._n_decisions = 0
        self._pending_obs: dict[str, RestrictedObservation] = {}
        self.obs_dim = 16 + K_TASKS * 6
        self.n_actions = N_ACTIONS

    def reset(self, seed: int | None = None) -> dict[str, AgentStep]:
        if seed is not None:
            self.seed = int(seed)
        sc = self.scenario_factory(seed=self.seed, n_vehicles=self.n_vehicles)
        # Shadow cooperative policy disabled; env drives actions.
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
                periodic_state_broadcast=False,
                decision_on_release=True,
            ),
            policy=None,
        )
        self._agent_ids = list(self.sim.vehicles.keys())
        self._last_served = 0
        self._n_decisions = 0
        self._advance_to_decision()
        return self._observe_all(reward=0.0, done=False)

    def _advance_to_decision(self) -> bool:
        """Pop events until a decision point or episode end. Returns done."""

        assert self.sim is not None
        sim = self.sim
        while sim._eq:
            ev = __import__("heapq").heappop(sim._eq)
            if ev.time_s + 1e-12 < sim.now_s:
                raise RuntimeError("event causality violated")
            sim.now_s = ev.time_s
            if ev.type == EventType.REQUEST_RELEASE:
                rid = ev.payload["request_id"]
                req = sim.requests[rid]
                if req.status == RequestStatus.UNRELEASED:
                    req.status = RequestStatus.AVAILABLE
                    return False  # decision point
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
                return False
            elif ev.type == EventType.BID_ASSIGN_WINDOW:
                return False
            elif ev.type == EventType.SHIFT_END:
                sim._expire_open_requests()
            elif ev.type == EventType.EPISODE_END:
                return True
        return True

    def _encode(self, obs: RestrictedObservation) -> tuple[np.ndarray, np.ndarray, list]:
        v = obs.self_state
        shift_left = 1.0  # normalized placeholder
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
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
        ]
        tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
        mask = np.zeros(N_ACTIONS, dtype=np.float32)
        mask[ACT_DEFER] = 1.0
        mask[ACT_CHARGE] = 1.0
        if self.comm_enabled:
            mask[ACT_SEND] = 1.0
            mask[ACT_SUPPRESS] = 1.0
        task_feats = []
        actions = ActionInterface(self.sim, actor_vehicle_id=obs.vehicle_id)
        for i in range(K_TASKS):
            if i < len(tasks):
                t = tasks[i]
                chk = actions.check_insertion(obs.vehicle_id, t.request_id)
                task_feats.extend(
                    [
                        1.0,
                        float(chk.feasible),
                        float(chk.marginal_travel_s or 0.0) / 3600.0,
                        float(chk.energy_flex_kwh or 0.0) / 40.0,
                        float(chk.min_deadline_slack_s or 0.0) / 3600.0,
                        (float(t.tw_end_s) - float(obs.now_s)) / 3600.0,
                    ]
                )
                if chk.feasible:
                    mask[i] = 1.0
            else:
                task_feats.extend([0.0] * 6)
        vec = np.asarray(feats + task_feats, dtype=np.float32)
        assert vec.shape[0] == self.obs_dim
        return vec, mask, tasks

    def _observe_all(self, reward: float, done: bool) -> dict[str, AgentStep]:
        assert self.sim is not None
        out = {}
        self._pending_obs = {}
        for vid in self._agent_ids:
            obs = build_restricted_observation(self.sim, vid)
            self._pending_obs[vid] = obs
            vec, mask, _ = self._encode(obs)
            out[vid] = AgentStep(obs=vec, mask=mask, reward=reward, done=done, info={})
        return out

    def step(self, actions: dict[str, int]) -> dict[str, AgentStep]:
        assert self.sim is not None
        self._n_decisions += 1
        # Execute actions for each agent using restricted interface only.
        for vid, a in actions.items():
            obs = self._pending_obs[vid]
            act = ActionInterface(self.sim, actor_vehicle_id=vid)
            tasks = sorted(obs.announced, key=lambda t: t.tw_end_s)[:K_TASKS]
            if a < K_TASKS and a < len(tasks):
                rid = tasks[a].request_id
                chk = act.check_insertion(vid, rid)
                if chk.feasible:
                    act.claim_task(vid, rid)
            elif a == ACT_CHARGE:
                act.request_return_depot(vid, charge=True, target_soc=0.70)
            elif a == ACT_SEND and self.comm_enabled and tasks:
                # Publish energy-feasible bid for top task via cooperative helper
                from race_casablanca.coordination.task_bids import compute_self_bid

                bid = compute_self_bid(obs, act, tasks[0])
                if bid.feasible:
                    act.broadcast_task_bid(vid, bid.to_payload())
            # defer / suppress: no-op

        served = sum(1 for r in self.sim.requests.values() if r.status == RequestStatus.COMPLETED)
        team_r = float(served - self._last_served)
        # Small communication cost
        team_r -= 0.001 * float(self.sim.n_bid_messages)
        self._last_served = served

        done = self._advance_to_decision()
        if self._n_decisions >= self.max_decisions:
            done = True
        if done:
            # Finish remaining event queue quickly without further agent control
            while self.sim._eq:
                d = self._advance_to_decision()
                if d:
                    break
            metrics = self.sim._metrics()
            team_r += float(metrics.on_time_rate_all)
            return self._observe_all(reward=team_r, done=True)
        return self._observe_all(reward=team_r, done=False)

    def final_metrics(self) -> dict[str, Any]:
        assert self.sim is not None
        return self.sim._metrics().to_dict()
