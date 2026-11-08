"""RACE-RH: feasibility-preserving rolling-horizon charging and commitment.

Outer service-first neighborhood search; inner discrete-target charging DP.
Does not hard-code 70% SOC. Timeout retains the previous safe plan.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from race_casablanca.optimization.charge_label_dp import optimize_charge_schedule
from race_casablanca.policies.charging_controller import ChargingController
from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.sim.feasibility_check import projected_state_after_lock
from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation
from race_casablanca.sim.types import RequestStatus, Stop


@dataclass
class RaceRollingHorizonPolicy:
    name: str = "race_rh"
    time_budget_s: float = 0.5
    reoptimize_every_s: float = 300.0
    # Ablation knobs
    enable_charge_opt: bool = True
    fixed_target_soc: float | None = None  # if set, DP only uses this target
    enable_neighborhood: bool = True  # False → greedy order + DP only
    _last_reopt_s: float = -1e18
    total_decision_runtime_s: float = 0.0
    n_timeouts: int = 0
    n_fallbacks: int = 0
    n_reopts: int = 0
    charging_fallback: ChargingController = field(
        default_factory=lambda: ChargingController(mode="adaptive_headroom", target_soc=1.0)
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
            if not self.enable_charge_opt:
                self.charging_fallback.apply(sim, actions)
            self.total_decision_runtime_s += time.perf_counter() - t0
            return

        ok = self._reoptimize(sim)
        self._last_reopt_s = sim.now_s
        self.n_reopts += 1
        if not ok:
            self.n_fallbacks += 1
            fill.on_decision(obs, actions, "fill")
            self.charging_fallback.apply(sim, actions)
        sim.config.extras["race_rh_time_budget_s"] = self.time_budget_s
        sim.config.extras["race_rh_timeouts"] = self.n_timeouts
        self.total_decision_runtime_s += time.perf_counter() - t0

    def _reoptimize(self, sim) -> bool:
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

        assignment: dict[str, list[str]] = {vid: list(locked[vid]) for vid in sim.vehicles}
        stop_plans: dict[str, list[Stop]] = {vid: [] for vid in sim.vehicles}

        def eval_vehicle(vid: str, rids: list[str]) -> tuple[bool, list[Stop], tuple]:
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
                for rid, st in backup.items():
                    sim.requests[rid].status = st
                if not res.feasible:
                    return False, [], (0, 1e18, 1e18)
                return True, list(res.plan), (res.n_served, res.total_travel_s, res.energy_delivered_kwh)
            # No charge opt: pickup-only feasibility via DP with charges disabled
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
            return True, list(res.plan), (res.n_served, res.total_travel_s, 0.0)

        def fleet_ok(assign: dict[str, list[str]]) -> tuple[bool, dict[str, list[Stop]], tuple]:
            plans: dict[str, list[Stop]] = {}
            n_srv = 0
            travel = 0.0
            delivered = 0.0
            for vid, rids in assign.items():
                ok, plan, sc = eval_vehicle(vid, rids)
                if not ok:
                    return False, {}, (0, 1e18, 1e18)
                plans[vid] = plan
                n_srv += sc[0]
                travel += sc[1]
                delivered += sc[2]
            return True, plans, (n_srv, travel, delivered)

        # Construction: earliest deadline first
        for rid in sorted(pool, key=lambda x: sim.requests[x].tw_end_s):
            if time.perf_counter() >= t_end:
                self.n_timeouts += 1
                break
            best_key = None
            best_vid = None
            best_plans = None
            for vid in sim.vehicles:
                trial = {**assignment, vid: assignment[vid] + [rid]}
                ok, plans, sc = fleet_ok(trial)
                if not ok:
                    continue
                key = (sc[0], -sc[1], -sc[2])
                if best_key is None or key > best_key:
                    best_key = key
                    best_vid = vid
                    best_plans = plans
            if best_vid is not None and best_plans is not None:
                assignment[best_vid].append(rid)
                stop_plans = best_plans

        # Neighborhood relocate
        if self.enable_neighborhood:
            improved = True
            while improved and time.perf_counter() < t_end:
                improved = False
                movable = [
                    rid
                    for rids in assignment.values()
                    for rid in rids
                    if all(rid not in locked[v] for v in locked)
                ]
                cur_score = fleet_ok(assignment)[2]
                for rid in movable:
                    if time.perf_counter() >= t_end:
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
                        ok, plans, sc = fleet_ok(trial)
                        if not ok:
                            continue
                        # Lex: more served, then less travel
                        if sc[0] > cur_score[0] or (
                            sc[0] == cur_score[0] and sc[1] + 1e-9 < cur_score[1]
                        ):
                            assignment = trial
                            stop_plans = plans
                            cur_score = sc
                            improved = True
                            break
                    if improved:
                        break

        # Final evaluate plans
        ok, plans, _ = fleet_ok(assignment)
        if not ok:
            return False
        stop_plans = plans
        return bool(sim.commit_fleet_plans(assignment, stop_plans=stop_plans))
