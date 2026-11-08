"""RACE-RH: feasibility-preserving rolling-horizon charging and commitment.

Stage 5.1 repairs:
- Shared readiness charging (observable, discrete target)
- Competitive incumbent (greedy charge-to-target) with validated commit
- Per-vehicle charge-schedule cache during neighborhood search
- Explicit decision-source logging; timeout keeps verified incumbent
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from race_casablanca.optimization.charge_label_dp import optimize_charge_schedule
from race_casablanca.policies.charging_controller import ChargingController
from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.policies.readiness_charging import ReadinessChargingController
from race_casablanca.sim.feasibility_check import projected_state_after_lock
from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation
from race_casablanca.sim.types import RequestStatus, Stop


@dataclass
class RaceRollingHorizonPolicy:
    name: str = "race_rh"
    time_budget_s: float = 0.5
    reoptimize_every_s: float = 300.0
    enable_charge_opt: bool = True
    fixed_target_soc: float | None = None
    enable_neighborhood: bool = True
    enable_readiness: bool = True
    readiness_target_soc: float = 0.70
    incumbent_charge_soc: float = 0.70
    _last_reopt_s: float = -1e18
    total_decision_runtime_s: float = 0.0
    n_timeouts: int = 0
    n_fallbacks: int = 0
    n_reopts: int = 0
    n_chose_optimized: int = 0
    n_chose_incumbent: int = 0
    n_chose_safety: int = 0
    decision_sources: list[str] = field(default_factory=list)
    charging_fallback: ChargingController = field(
        default_factory=lambda: ChargingController(mode="charge_to_target", target_soc=0.70)
    )
    readiness: ReadinessChargingController = field(default_factory=ReadinessChargingController)

    def __post_init__(self) -> None:
        self.readiness = ReadinessChargingController(
            target_soc=self.readiness_target_soc, enabled=self.enable_readiness
        )

    def on_decision(
        self,
        obs: FullInfoObservation | RestrictedObservation,
        actions: ActionInterface,
        reason: str,
    ) -> None:
        if not isinstance(obs, FullInfoObservation):
            return
        if reason == "message":
            return
        sim = actions._sim
        t0 = time.perf_counter()
        fill = GreedyInsertionPolicy(charging=ChargingController(mode="none"))

        if reason != "request_release" and (sim.now_s - self._last_reopt_s) < self.reoptimize_every_s:
            fill.on_decision(obs, actions, "fill")
            self.readiness.apply(sim, actions)
            self.total_decision_runtime_s += time.perf_counter() - t0
            return

        source = self._reoptimize_with_incumbent(sim, actions, obs)
        self.decision_sources.append(source)
        self._last_reopt_s = sim.now_s
        self.n_reopts += 1
        if source == "safety":
            self.n_chose_safety += 1
            self.n_fallbacks += 1
        elif source == "incumbent":
            self.n_chose_incumbent += 1
        else:
            self.n_chose_optimized += 1

        # Proactive readiness after plan (overridable by urgent claimable work)
        self.readiness.apply(sim, actions)
        sim.config.extras["race_rh_time_budget_s"] = self.time_budget_s
        sim.config.extras["race_rh_timeouts"] = self.n_timeouts
        sim.config.extras["race_rh_last_source"] = source
        self.total_decision_runtime_s += time.perf_counter() - t0

    def _snapshot_assignment(self, sim) -> dict[str, list[str]]:
        locked: dict[str, list[str]] = {vid: [] for vid in sim.vehicles}
        for vid, v in sim.vehicles.items():
            if v.moving_to and v.moving_to.kind == "pickup" and v.moving_to.request_id:
                locked[vid].append(v.moving_to.request_id)
        assign = {vid: list(locked[vid]) for vid in sim.vehicles}
        for vid, v in sim.vehicles.items():
            for rid in v.committed:
                if rid not in assign[vid]:
                    assign[vid].append(rid)
        return assign

    def _build_incumbent(self, sim, actions: ActionInterface, obs: FullInfoObservation) -> tuple[dict, dict, tuple]:
        """Feasible conventional candidate: greedy + charge-to-target plans via DP."""
        snap_assign = self._snapshot_assignment(sim)
        # Greedy fill without mutating permanently — use try/restore via commit only at end
        # Build assignment greedily in a shadow dict
        locked = {vid: [] for vid in sim.vehicles}
        for vid, v in sim.vehicles.items():
            if v.moving_to and v.moving_to.kind == "pickup" and v.moving_to.request_id:
                locked[vid].append(v.moving_to.request_id)
        assign = {vid: list(locked[vid]) for vid in sim.vehicles}
        for vid, v in sim.vehicles.items():
            for rid in v.committed:
                if rid not in assign[vid]:
                    assign[vid].append(rid)

        available = sorted(
            [t for t in obs.available],
            key=lambda t: t.tw_end_s,
        )
        for task in available:
            best = None
            for vid in sim.vehicles:
                trial = {**assign, vid: assign[vid] + [task.request_id]}
                ok, plans, sc = self._fleet_ok(sim, trial, locked, cache={})
                if not ok:
                    continue
                key = (sc[0], -sc[1])
                if best is None or key > best[0]:
                    best = (key, vid, plans)
            if best is not None:
                assign[best[1]].append(task.request_id)

        ok, plans, sc = self._fleet_ok(sim, assign, locked, cache={})
        if not ok:
            # Fall back to current commitments only
            ok2, plans2, sc2 = self._fleet_ok(sim, snap_assign, locked, cache={})
            return snap_assign, plans2 if ok2 else {}, sc2 if ok2 else (0, 1e18, 1e18)
        return assign, plans, sc

    def _reoptimize_with_incumbent(self, sim, actions: ActionInterface, obs: FullInfoObservation) -> str:
        t_end = time.perf_counter() + self.time_budget_s
        locked: dict[str, list[str]] = {vid: [] for vid in sim.vehicles}
        for vid, v in sim.vehicles.items():
            if v.moving_to and v.moving_to.kind == "pickup" and v.moving_to.request_id:
                locked[vid].append(v.moving_to.request_id)

        pool: list[str] = []
        for req in sim.requests.values():
            if req.status == RequestStatus.AVAILABLE:
                pool.append(req.request_id)
            elif req.status == RequestStatus.COMMITTED:
                if req.owner and req.request_id in locked.get(req.owner, []):
                    continue
                pool.append(req.request_id)

        # Incumbent first (verified conventional)
        inc_assign, inc_plans, inc_score = self._build_incumbent(sim, actions, obs)
        best_assign = {k: list(v) for k, v in inc_assign.items()}
        best_plans = {k: list(v) for k, v in inc_plans.items()}
        best_score = inc_score
        source = "incumbent"
        timed_out = False
        cache: dict[tuple, Any] = {}

        assignment = {vid: list(locked[vid]) for vid in sim.vehicles}
        # Seed with current committed editable
        for vid, v in sim.vehicles.items():
            for rid in v.committed:
                if rid not in assignment[vid]:
                    assignment[vid].append(rid)

        # Construction
        for rid in sorted(pool, key=lambda x: sim.requests[x].tw_end_s):
            if time.perf_counter() >= t_end:
                timed_out = True
                self.n_timeouts += 1
                break
            best_key = None
            best_vid = None
            best_p = None
            for vid in sim.vehicles:
                trial = {**assignment, vid: assignment[vid] + [rid]}
                ok, plans, sc = self._fleet_ok(sim, trial, locked, cache)
                if not ok:
                    continue
                key = (sc[0], -sc[1], -sc[2])
                if best_key is None or key > best_key:
                    best_key = key
                    best_vid = vid
                    best_p = plans
            if best_vid is not None and best_p is not None:
                assignment[best_vid].append(rid)
                ok, plans, sc = self._fleet_ok(sim, assignment, locked, cache)
                if ok and (sc[0] > best_score[0] or (sc[0] == best_score[0] and sc[1] + 1e-9 < best_score[1])):
                    best_assign = {k: list(v) for k, v in assignment.items()}
                    best_plans = plans
                    best_score = sc
                    source = "optimized"

        # Neighborhood
        if self.enable_neighborhood and not timed_out:
            improved = True
            while improved and time.perf_counter() < t_end:
                improved = False
                movable = [
                    rid
                    for rids in assignment.values()
                    for rid in rids
                    if all(rid not in locked[v] for v in locked)
                ]
                for rid in movable:
                    if time.perf_counter() >= t_end:
                        timed_out = True
                        self.n_timeouts += 1
                        break
                    cur_v = next(vid for vid, rids in assignment.items() if rid in rids)
                    for vid in sim.vehicles:
                        if vid == cur_v:
                            continue
                        trial = {
                            **assignment,
                            cur_v: [r for r in assignment[cur_v] if r != rid],
                            vid: assignment[vid] + [rid],
                        }
                        ok, plans, sc = self._fleet_ok(sim, trial, locked, cache)
                        if not ok:
                            continue
                        if sc[0] > best_score[0] or (
                            sc[0] == best_score[0] and sc[1] + 1e-9 < best_score[1]
                        ):
                            assignment = trial
                            best_assign = {k: list(v) for k, v in trial.items()}
                            best_plans = plans
                            best_score = sc
                            source = "optimized"
                            improved = True
                            break
                    if improved:
                        break

        if timed_out and source == "optimized":
            # Keep optimized only if still better than incumbent; else revert label
            if not (
                best_score[0] > inc_score[0]
                or (best_score[0] == inc_score[0] and best_score[1] + 1e-9 < inc_score[1])
            ):
                best_assign, best_plans, best_score = inc_assign, inc_plans, inc_score
                source = "incumbent"

        if not best_plans:
            fill = GreedyInsertionPolicy(charging=ChargingController(mode="none"))
            from race_casablanca.sim.policy_api import build_full_observation

            fill.on_decision(build_full_observation(sim), actions, "fill")
            self.charging_fallback.apply(sim, actions)
            return "safety"

        ok = sim.commit_fleet_plans(best_assign, stop_plans=best_plans)
        if not ok:
            # Try incumbent commit
            if best_plans is not inc_plans and inc_plans:
                ok = sim.commit_fleet_plans(inc_assign, stop_plans=inc_plans)
                if ok:
                    return "incumbent"
            fill = GreedyInsertionPolicy(charging=ChargingController(mode="none"))
            from race_casablanca.sim.policy_api import build_full_observation

            fill.on_decision(build_full_observation(sim), actions, "fill")
            self.charging_fallback.apply(sim, actions)
            return "safety"
        return source

    def _fleet_ok(
        self,
        sim,
        assign: dict[str, list[str]],
        locked: dict[str, list[str]],
        cache: dict,
    ) -> tuple[bool, dict[str, list[Stop]], tuple]:
        plans: dict[str, list[Stop]] = {}
        n_srv = 0
        travel = 0.0
        delivered = 0.0
        for vid, rids in assign.items():
            key = (vid, tuple(rids))
            if key in cache:
                ok, plan, sc = cache[key]
            else:
                ok, plan, sc = self._eval_vehicle(sim, vid, rids, locked)
                cache[key] = (ok, plan, sc)
            if not ok:
                return False, {}, (0, 1e18, 1e18)
            plans[vid] = plan
            n_srv += sc[0]
            travel += sc[1]
            delivered += sc[2]
        return True, plans, (n_srv, travel, delivered)

    def _eval_vehicle(
        self, sim, vid: str, rids: list[str], locked: dict[str, list[str]]
    ) -> tuple[bool, list[Stop], tuple]:
        v = sim.vehicles[vid]
        edit = [rid for rid in rids if rid not in locked[vid]]
        backup = {rid: sim.requests[rid].status for rid in edit}
        for rid in edit:
            if sim.requests[rid].status in {RequestStatus.AVAILABLE, RequestStatus.COMMITTED}:
                sim.requests[rid].status = RequestStatus.AVAILABLE
        proj = projected_state_after_lock(
            v, sim.requests, sim.router, sim.energy, sim.depot_node, sim.now_s
        )
        if self.enable_charge_opt:
            res = optimize_charge_schedule(
                proj,
                edit,
                sim.requests,
                sim.router,
                sim.energy,
                sim.depot_node,
                sim.payload_max,
                sim.shift_end_s,
                fixed_target_soc=self.fixed_target_soc,
            )
        else:
            res = optimize_charge_schedule(
                proj,
                edit,
                sim.requests,
                sim.router,
                sim.energy,
                sim.depot_node,
                sim.payload_max,
                sim.shift_end_s,
                allow_leading_charge=False,
                allow_between_charge=False,
                allow_trailing_charge=False,
            )
        for rid, st in backup.items():
            sim.requests[rid].status = st
        if not res.feasible:
            return False, [], (0, 1e18, 1e18)
        return True, list(res.plan), (res.n_served, res.total_travel_s, res.energy_delivered_kwh)
