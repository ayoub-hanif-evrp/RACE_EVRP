"""Post-decision lookahead forks (Stage 4A).

Clones mutable simulator state while sharing the RouteCache/network.
Strips evaluation-scenario unreleased requests (anti-leakage), injects synthetic
continuations, applies a candidate action, and rolls out a base policy.
"""

from __future__ import annotations

import copy
import heapq
import time
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from race_casablanca.policies.charging_controller import ChargingController
from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.sim.types import Event, EventPriority, EventType, Request, RequestStatus


ActionKind = Literal["noop", "claim", "charge"]


@dataclass(frozen=True)
class CandidateAction:
    kind: ActionKind
    vehicle_id: str | None = None
    request_id: str | None = None
    position: int | None = None
    label: str = ""


@dataclass
class LookaheadScore:
    mean_on_time: float
    mean_served: float
    mean_travel_s: float
    mean_energy_kwh: float
    samples: int
    action: CandidateAction
    runtime_s: float = 0.0


def clone_sim_state(sim):
    """Shallow structural clone: share router; deepcopy mutable episode state."""

    fork = object.__new__(type(sim))
    fork.__dict__.update(sim.__dict__)
    fork.vehicles = copy.deepcopy(sim.vehicles)
    fork.requests = copy.deepcopy(sim.requests)
    fork.registry = copy.deepcopy(sim.registry)
    fork.bus = copy.deepcopy(sim.bus)
    fork._eq = copy.deepcopy(list(sim._eq))
    heapq.heapify(fork._eq)
    fork.energy = copy.deepcopy(sim.energy)
    fork.config = copy.deepcopy(sim.config)
    fork.local_views = copy.deepcopy(sim.local_views)
    fork._decision_runtimes = []
    fork.event_trace = []
    fork.info_ages = []
    fork.first_reserve_violation_trace = None
    # Share router (read-mostly cache). Do NOT deepcopy graph.
    fork.router = sim.router
    fork.rng = np.random.default_rng(int(sim.config.seed) + int(sim.now_s) % 10_000)
    return fork


def _strip_eval_futures(fork) -> None:
    drop = {rid for rid, r in fork.requests.items() if r.status == RequestStatus.UNRELEASED}
    for rid in drop:
        del fork.requests[rid]
    new_eq: list[Event] = []
    for ev in fork._eq:
        if ev.type == EventType.REQUEST_RELEASE and ev.payload.get("request_id") in drop:
            continue
        new_eq.append(ev)
    heapq.heapify(new_eq)
    fork._eq = new_eq


def _inject_synthetic(fork, synth: list[Request]) -> None:
    for req in synth:
        r = copy.deepcopy(req)
        r.status = RequestStatus.UNRELEASED
        r.owner = None
        fork.requests[r.request_id] = r
        fork._seq += 1
        heapq.heappush(
            fork._eq,
            Event(
                r.release_s,
                int(EventPriority.REQUEST_RELEASE),
                fork._seq,
                EventType.REQUEST_RELEASE,
                {"request_id": r.request_id},
            ),
        )


def _apply_action(fork, action: CandidateAction) -> bool:
    if action.kind == "noop":
        return True
    if action.kind == "claim":
        assert action.vehicle_id and action.request_id
        if action.request_id not in fork.requests:
            return False
        if fork.requests[action.request_id].status != RequestStatus.AVAILABLE:
            return False
        return fork.try_assign(
            action.vehicle_id, action.request_id, force_position=action.position, start_leg=True
        )
    if action.kind == "charge":
        assert action.vehicle_id
        v = fork.vehicles[action.vehicle_id]
        if v.busy:
            return False
        if float(v.battery_kwh) >= float(fork.energy.battery_kwh_max) - 1e-6:
            return False
        fork.request_return_depot(action.vehicle_id, charge=True)
        return True
    return False


def fork_and_rollout(
    sim,
    action: CandidateAction,
    synthetic: list[Request],
    *,
    base_charge_mode: str = "adaptive_headroom",
    horizon_s: float | None = 3600.0,
) -> dict[str, Any]:
    fork = clone_sim_state(sim)
    fork.policy = GreedyInsertionPolicy(
        charging=ChargingController(mode=base_charge_mode, headroom_threshold_kwh=3.0)
    )
    fork.config.info_mode = "full"
    if horizon_s is not None and horizon_s > 0:
        # Truncate lookahead horizon for online feasibility (documented budget)
        now = float(fork.now_s)
        raw_end = min(float(fork.shift_end_s), now + float(horizon_s))
        h_end = max(now, raw_end)
        fork.shift_end_s = h_end
        kept: list[Event] = []
        for ev in fork._eq:
            if ev.type in {EventType.SHIFT_END, EventType.EPISODE_END}:
                continue
            # Keep only future/present events within horizon
            if ev.time_s + 1e-12 < now:
                continue
            if ev.time_s <= h_end + 1e-9:
                kept.append(ev)
        max_t = h_end
        if kept:
            max_t = max(max_t, max(e.time_s for e in kept))
        fork._seq += 1
        kept.append(
            Event(h_end, int(EventPriority.SHIFT_END), fork._seq, EventType.SHIFT_END, {})
        )
        fork._seq += 1
        kept.append(
            Event(
                max_t + 10.0,
                int(EventPriority.EPISODE_END),
                fork._seq,
                EventType.EPISODE_END,
                {},
            )
        )
        heapq.heapify(kept)
        fork._eq = kept
    _strip_eval_futures(fork)
    if not _apply_action(fork, action):
        return {"ok": False, "n_on_time": -1e9, "n_served": -1e9, "travel_s": 1e18, "energy_kwh": 1e18}
    # Filter synthetic to horizon
    if horizon_s is not None:
        synthetic = [r for r in synthetic if r.release_s <= fork.shift_end_s]
    _inject_synthetic(fork, synthetic)
    m = fork.run()
    return {
        "ok": True,
        "n_on_time": float(m.n_on_time),
        "n_served": float(m.n_served),
        "travel_s": float(m.total_travel_s),
        "energy_kwh": float(m.energy_consumed_kwh),
        "n_charges": int(m.n_charges),
    }


def score_action(
    sim,
    action: CandidateAction,
    continuations: list[list[Request]],
    *,
    base_charge_mode: str = "adaptive_headroom",
    horizon_s: float | None = 3600.0,
) -> LookaheadScore:
    t0 = time.perf_counter()
    on_times: list[float] = []
    served: list[float] = []
    travels: list[float] = []
    energies: list[float] = []
    for synth in continuations:
        out = fork_and_rollout(
            sim, action, synth, base_charge_mode=base_charge_mode, horizon_s=horizon_s
        )
        if not out["ok"]:
            on_times.append(-1e6)
            served.append(-1e6)
            travels.append(1e18)
            energies.append(1e18)
        else:
            on_times.append(float(out["n_on_time"]))
            served.append(float(out["n_served"]))
            travels.append(float(out["travel_s"]))
            energies.append(float(out["energy_kwh"]))
    return LookaheadScore(
        mean_on_time=float(np.mean(on_times)),
        mean_served=float(np.mean(served)),
        mean_travel_s=float(np.mean(travels)),
        mean_energy_kwh=float(np.mean(energies)),
        samples=len(continuations),
        action=action,
        runtime_s=time.perf_counter() - t0,
    )
