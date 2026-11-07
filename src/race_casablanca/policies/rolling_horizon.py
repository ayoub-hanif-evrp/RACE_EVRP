"""Baseline B — centralized rolling-horizon reoptimization.

Uses sequential cheapest insertion + relocate/swap LNS within a wall-clock
budget. OR-Tools is not required. Solutions are validated via the simulator's
conservative feasibility checker before commitments are applied.
No offline clairvoyant witness is used.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from race_casablanca.sim.environment import OnlineSimulator
from race_casablanca.sim.feasibility_check import simulate_plan_conservative
from race_casablanca.sim.types import RequestStatus, Stop


@dataclass
class RollingHorizonPolicy:
    name: str = "rolling_horizon_lns"
    time_budget_s: float = 0.25
    reoptimize_every_s: float = 300.0
    _last_reopt_s: float = -1e18

    def on_decision(self, sim: OnlineSimulator, reason: str) -> None:
        if reason not in {"request_release", "epoch", "service_end", "vehicle_idle"}:
            # Still allow on release; skip pure message ticks
            if reason == "message":
                return
        if reason != "request_release" and (sim.now_s - self._last_reopt_s) < self.reoptimize_every_s:
            # Lightweight greedy fill between reoptimizations
            self._greedy_fill(sim)
            return
        self._reoptimize(sim)
        self._last_reopt_s = sim.now_s

    def _greedy_fill(self, sim: OnlineSimulator) -> None:
        from race_casablanca.policies.greedy import GreedyInsertionPolicy

        GreedyInsertionPolicy().on_decision(sim, "fill")

    def _reoptimize(self, sim: OnlineSimulator) -> None:
        t_end = time.perf_counter() + self.time_budget_s
        # Collect reassignable requests: available + committed (not in service)
        pool: list[str] = []
        for req in sim.requests.values():
            if req.status.value == "available":
                pool.append(req.request_id)
            elif req.status.value == "committed":
                v = sim.vehicles.get(req.owner or "", None)
                if v is None:
                    pool.append(req.request_id)
                    continue
                if v.moving_to and v.moving_to.request_id == req.request_id:
                    continue  # immutable once en route / in service
                pool.append(req.request_id)

        # Release all reassignable commitments back to available
        for rid in list(pool):
            req = sim.requests[rid]
            if req.status.value == "committed" and req.owner:
                vid = req.owner
                v = sim.vehicles[vid]
                if v.moving_to and v.moving_to.request_id == rid:
                    pool.remove(rid)
                    continue
                v.plan = [s for s in v.plan if s.request_id != rid]
                if rid in v.committed:
                    v.committed.remove(rid)
                sim.registry.release(rid, vid)
                req.status = RequestStatus.AVAILABLE
                req.owner = None

        # Build empty plans (keep locked in-service legs only)
        assignment: dict[str, list[str]] = {vid: [] for vid in sim.vehicles}
        for vid, v in sim.vehicles.items():
            for s in v.plan:
                if s.kind == "pickup" and s.request_id:
                    assignment[vid].append(s.request_id)

        # Seed by deadline urgency, sequential cheapest insertion across fleet
        pool_sorted = sorted(pool, key=lambda rid: sim.requests[rid].tw_end_s)
        unassigned: list[str] = []
        for rid in pool_sorted:
            best = None
            for vid in sim.vehicles:
                v = sim.vehicles[vid]
                trial = list(assignment[vid]) + [rid]
                plan = [Stop("pickup", r, sim.requests[r].snap_node) for r in trial]
                # Include locked prefix already in v.plan that are in-service targets
                locked = [
                    s
                    for s in v.plan
                    if s.kind == "pickup" and s.request_id and s.request_id not in trial
                ]
                full = locked + plan
                chk = simulate_plan_conservative(
                    v,
                    full,
                    sim.requests,
                    sim.router,
                    sim.energy,
                    sim.depot_node,
                    sim.payload_max,
                    sim.shift_end_s,
                )
                if chk.feasible and (best is None or chk.added_travel_s < best[0]):
                    best = (chk.added_travel_s, vid)
            if best is None:
                unassigned.append(rid)
            else:
                assignment[best[1]].append(rid)

        # LNS relocate while budget remains
        improved = True
        while improved and time.perf_counter() < t_end:
            improved = False
            for rid in list(sum(assignment.values(), [])):
                if time.perf_counter() >= t_end:
                    break
                cur_v = next(vid for vid, rids in assignment.items() if rid in rids)
                for vid in sim.vehicles:
                    if vid == cur_v:
                        continue
                    # try move
                    new_cur = [r for r in assignment[cur_v] if r != rid]
                    new_dst = list(assignment[vid]) + [rid]
                    if self._plans_ok(sim, {**assignment, cur_v: new_cur, vid: new_dst}):
                        # accept if total travel decreases
                        before = self._total_cost(sim, assignment)
                        trial_map = {**assignment, cur_v: new_cur, vid: new_dst}
                        after = self._total_cost(sim, trial_map)
                        if after + 1e-9 < before:
                            assignment = trial_map
                            improved = True
                            break

        # Apply via try_assign (validates again)
        for vid, rids in assignment.items():
            for rid in rids:
                req = sim.requests[rid]
                if req.status.value == "available":
                    sim.try_assign(vid, rid)
                elif req.owner == vid:
                    continue
                else:
                    if req.status.value == "committed" and req.owner:
                        sim.try_reassign(req.owner, vid, rid)

        for rid in unassigned:
            req = sim.requests[rid]
            if req.status.value == "available" and req.tw_end_s <= sim.now_s:
                sim.reject_request(rid)

    def _plans_ok(self, sim: OnlineSimulator, assignment: dict[str, list[str]]) -> bool:
        for vid, rids in assignment.items():
            v = sim.vehicles[vid]
            plan = [Stop("pickup", r, sim.requests[r].snap_node) for r in rids]
            chk = simulate_plan_conservative(
                v, plan, sim.requests, sim.router, sim.energy,
                sim.depot_node, sim.payload_max, sim.shift_end_s,
            )
            if not chk.feasible:
                return False
        return True

    def _total_cost(self, sim: OnlineSimulator, assignment: dict[str, list[str]]) -> float:
        total = 0.0
        for vid, rids in assignment.items():
            v = sim.vehicles[vid]
            plan = [Stop("pickup", r, sim.requests[r].snap_node) for r in rids]
            chk = simulate_plan_conservative(
                v, plan, sim.requests, sim.router, sim.energy,
                sim.depot_node, sim.payload_max, sim.shift_end_s,
            )
            total += chk.added_travel_s if chk.feasible else 1e18
        return total
