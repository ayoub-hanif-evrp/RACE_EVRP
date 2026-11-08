"""Service-first rolling horizon: maximize feasible assignments, then min travel."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from race_casablanca.policies.charging_controller import ChargingController
from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.policies.readiness_charging import ReadinessChargingController
from race_casablanca.sim.feasibility_check import projected_state_after_lock, simulate_plan_conservative
from race_casablanca.sim.policy_api import ActionInterface, FullInfoObservation, RestrictedObservation
from race_casablanca.sim.types import RequestStatus, Stop, VehicleMode


@dataclass
class ServiceFirstRollingHorizonPolicy:
    name: str = "service_first_rolling_horizon"
    time_budget_s: float = 0.35
    reoptimize_every_s: float = 300.0
    _last_reopt_s: float = -1e18
    # Stage 5: after pickup RH, run discrete-target charge DP on each vehicle plan
    optimize_charges: bool = False
    fixed_target_soc: float | None = None
    enable_readiness: bool = False
    readiness_target_soc: float = 0.70
    charging: ChargingController = field(
        default_factory=lambda: ChargingController(mode="adaptive_headroom")
    )
    readiness: ReadinessChargingController = field(default_factory=ReadinessChargingController)

    def __post_init__(self) -> None:
        # Charge-aware RH: controller fallback uses discrete 0.7 if not overridden
        if self.optimize_charges and self.charging.mode == "adaptive_headroom":
            self.charging = ChargingController(mode="charge_to_target", target_soc=0.70)
        self.readiness = ReadinessChargingController(
            target_soc=self.readiness_target_soc,
            enabled=self.enable_readiness or self.optimize_charges,
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
        fill = GreedyInsertionPolicy(charging=ChargingController(mode="none"))
        if reason != "request_release" and (sim.now_s - self._last_reopt_s) < self.reoptimize_every_s:
            fill.on_decision(obs, actions, "fill")
            if self.optimize_charges:
                self._attach_charge_schedules(sim)
            else:
                self.charging.apply(sim, actions)
            self.readiness.apply(sim, actions)
            return
        self._reoptimize(sim)
        self._last_reopt_s = sim.now_s
        sim.config.extras["rh_time_budget_s"] = self.time_budget_s
        fill.on_decision(obs, actions, "fill")
        if self.optimize_charges:
            self._attach_charge_schedules(sim)
        else:
            self.charging.apply(sim, actions)
        self.readiness.apply(sim, actions)

    def _attach_charge_schedules(self, sim) -> None:
        """Post-hoc discrete-target charge DP for equalized charge-aware RH baseline."""
        from race_casablanca.optimization.charge_label_dp import optimize_charge_schedule

        for vid, v in sim.vehicles.items():
            if v.mode == VehicleMode.EMERGENCY_STRANDED:
                continue
            locked = []
            if v.moving_to and v.moving_to.kind == "pickup" and v.moving_to.request_id:
                locked.append(v.moving_to.request_id)
            edit = [s.request_id for s in v.plan if s.kind == "pickup" and s.request_id not in locked]
            if not edit and not self.optimize_charges:
                continue
            proj = projected_state_after_lock(
                v, sim.requests, sim.router, sim.energy, sim.depot_node, sim.now_s
            )
            # Temporarily mark editable as available for DP status checks
            backup = {rid: sim.requests[rid].status for rid in edit}
            for rid in edit:
                if sim.requests[rid].status in {RequestStatus.AVAILABLE, RequestStatus.COMMITTED}:
                    sim.requests[rid].status = RequestStatus.AVAILABLE
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
            if res.feasible:
                locked_stops = [v.moving_to] if v.moving_to is not None else []
                v.plan = locked_stops + list(res.plan)
                if not v.busy and v.plan:
                    sim._start_next_leg(vid)
        # Always allow controller fallback for idle low-headroom vehicles
        self.charging.apply(sim, ActionInterface(sim))

    def _reoptimize(self, sim) -> None:
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

        def plan_ok(assign: dict[str, list[str]]) -> bool:
            for vid, rids in assign.items():
                v = sim.vehicles[vid]
                edit = [rid for rid in rids if rid not in locked[vid]]
                backup = {rid: sim.requests[rid].status for rid in edit}
                for rid in edit:
                    if sim.requests[rid].status in {RequestStatus.AVAILABLE, RequestStatus.COMMITTED}:
                        sim.requests[rid].status = RequestStatus.AVAILABLE
                proj = projected_state_after_lock(
                    v, sim.requests, sim.router, sim.energy, sim.depot_node, sim.now_s
                )
                plan = [Stop("pickup", rid, sim.requests[rid].snap_node) for rid in edit]
                chk = simulate_plan_conservative(
                    proj, plan, sim.requests, sim.router, sim.energy,
                    sim.depot_node, sim.payload_max, sim.shift_end_s,
                )
                for rid, st in backup.items():
                    sim.requests[rid].status = st
                if not chk.feasible:
                    return False
            return True

        def n_assigned(assign: dict[str, list[str]]) -> int:
            return sum(len(rids) for rids in assign.values())

        def travel_cost(assign: dict[str, list[str]]) -> float:
            total = 0.0
            for vid, rids in assign.items():
                v = sim.vehicles[vid]
                edit = [rid for rid in rids if rid not in locked[vid]]
                backup = {rid: sim.requests[rid].status for rid in edit}
                for rid in edit:
                    if sim.requests[rid].status in {RequestStatus.AVAILABLE, RequestStatus.COMMITTED}:
                        sim.requests[rid].status = RequestStatus.AVAILABLE
                proj = projected_state_after_lock(
                    v, sim.requests, sim.router, sim.energy, sim.depot_node, sim.now_s
                )
                plan = [Stop("pickup", rid, sim.requests[rid].snap_node) for rid in edit]
                chk = simulate_plan_conservative(
                    proj, plan, sim.requests, sim.router, sim.energy,
                    sim.depot_node, sim.payload_max, sim.shift_end_s,
                )
                for rid, st in backup.items():
                    sim.requests[rid].status = st
                total += chk.total_travel_s if chk.feasible else 1e18
            return total

        # Service-first construction: insert if feasible, prefer assignments that raise count
        for rid in sorted(pool, key=lambda x: sim.requests[x].tw_end_s):
            best = None  # (n_assigned, -travel, vid)
            for vid in sim.vehicles:
                trial = {**assignment, vid: assignment[vid] + [rid]}
                if not plan_ok(trial):
                    continue
                key = (n_assigned(trial), -travel_cost(trial), vid)
                if best is None or key > best:
                    best = key
            if best is not None:
                assignment[best[2]].append(rid)

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
                    if not plan_ok(trial):
                        continue
                    # Accept if more assignments (shouldn't change) or same count lower travel
                    if n_assigned(trial) < n_assigned(assignment):
                        continue
                    if travel_cost(trial) + 1e-9 < travel_cost(assignment):
                        assignment = trial
                        improved = True
                        break

        sim.commit_fleet_plans(assignment)
