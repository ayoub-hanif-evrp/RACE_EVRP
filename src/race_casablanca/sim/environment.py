"""Event-driven online electric pickup simulator (Stage 2.1 semantics)."""

from __future__ import annotations

import copy
import heapq
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from race_casablanca.coordination.messaging import Message, MessageBus
from race_casablanca.coordination.ownership import TaskRegistry
from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.feasibility_check import (
    FeasibilityCheck,
    check_leg_dispatch,
    editable_suffix,
    insertion_cost,
    locked_prefix,
    projected_state_after_lock,
    simulate_plan_conservative,
)
from race_casablanca.sim.metrics import EpisodeMetrics
from race_casablanca.sim.policy_api import (
    ActionInterface,
    Policy,
    build_full_observation,
    build_restricted_observation,
)
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.types import (
    Event,
    EventPriority,
    EventType,
    Request,
    RequestStatus,
    Stop,
    VehicleMode,
    VehicleState,
)


@dataclass
class SimConfig:
    info_mode: str = "full"  # full | restricted
    energy_uncertainty_delta: float = 0.0
    message_delay_s: float = 0.0
    initial_soc: float | None = None
    n_vehicles: int | None = None
    charge_on_return: bool = False
    auto_depot_when_idle_empty: bool = True
    decision_on_release: bool = True
    seed: int = 0
    day: str = "Monday"
    realization_mode: str = "crn"  # crn | adversarial_worst | stochastic
    # Genuine periodic broadcast clock (seconds); 0 disables independent timer
    periodic_broadcast_s: float = 0.0
    extras: dict[str, Any] = field(default_factory=dict)


class OnlineSimulator:
    """Deterministic event queue; energy disturbances via CRN / adversarial modes."""

    def __init__(
        self,
        *,
        scenario_id: str,
        graph,
        model,
        requests: list[Request],
        fleet: dict,
        depot_node: int,
        shift_start_s: float,
        shift_end_s: float,
        config: SimConfig,
        policy: Policy | None = None,
        router: RouteCache | None = None,
    ):
        self.scenario_id = scenario_id
        self.depot_node = int(depot_node)
        self.shift_start_s = float(shift_start_s)
        self.shift_end_s = float(shift_end_s)
        self.config = config
        self.policy = policy
        self.day = config.day

        self.rng = np.random.default_rng(config.seed)
        n_veh = int(config.n_vehicles if config.n_vehicles is not None else fleet.get("n_vehicles", 1))
        bat_max = float(fleet["usable_battery_kwh"])
        init_soc = float(config.initial_soc if config.initial_soc is not None else fleet.get("initial_soc", 1.0))
        cons_wh = float(fleet.get("consumption_wh_per_km", 200.0))
        self.payload_max = float(fleet["payload_kg"])
        self.energy = EnergyModel(
            consumption_kwh_per_km=cons_wh / 1000.0,
            uncertainty_delta=float(config.energy_uncertainty_delta),
            battery_kwh_max=bat_max,
            reserve_soc=float(fleet.get("min_reserve_soc", 0.15)),
            charge_power_kw=float(fleet.get("charge_power_kw", 22.0)),
            realization_mode=str(config.realization_mode),
            scenario_seed=int(config.seed),
        )
        owned_router = router is None
        self.router = router if router is not None else RouteCache(graph, model, day=config.day)
        self.registry = TaskRegistry()
        self.bus = MessageBus(delay_s=float(config.message_delay_s))

        self.requests: dict[str, Request] = {r.request_id: copy.deepcopy(r) for r in requests}
        for r in self.requests.values():
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        if owned_router:
            landmarks = [self.depot_node] + [r.snap_node for r in self.requests.values()]
            self.router.warmup(landmarks)

        self.vehicles: dict[str, VehicleState] = {}
        for i in range(n_veh):
            vid = f"V{i+1}"
            self.vehicles[vid] = VehicleState(
                vehicle_id=vid,
                node=self.depot_node,
                ready_s=self.shift_start_s,
                battery_kwh=bat_max * init_soc,
                load_kg=0.0,
            )

        self.now_s = self.shift_start_s
        self._eq: list[Event] = []
        self._seq = 0
        self._decision_runtimes: list[float] = []
        self.energy_changed_dispatch = 0
        self.planned_energy_rejections = 0
        self.n_claims = 0
        self.n_failed_claims = 0
        self.n_reassignments = 0
        self.info_ages: list[float] = []
        self.event_trace: list[dict[str, Any]] = []
        self.first_reserve_violation_trace: dict[str, Any] | None = None

        self.local_views: dict[str, dict[str, Any]] = {vid: {} for vid in self.vehicles}
        # recipient -> request_id -> sender_id -> bid payload
        self.local_bids: dict[str, dict[str, dict[str, Any]]] = {vid: {} for vid in self.vehicles}
        self.n_bid_messages = 0
        self.n_bid_bytes = 0

        for req in self.requests.values():
            self._schedule(req.release_s, EventType.REQUEST_RELEASE, {"request_id": req.request_id})
        self._schedule(self.shift_end_s, EventType.SHIFT_END, {})
        self._schedule(self.shift_end_s + 24 * 3600.0, EventType.EPISODE_END, {})
        if self.config.periodic_broadcast_s and self.config.periodic_broadcast_s > 0:
            t = self.shift_start_s + float(self.config.periodic_broadcast_s)
            while t <= self.shift_end_s:
                self._schedule(t, EventType.PERIODIC_BROADCAST, {})
                t += float(self.config.periodic_broadcast_s)

    def _schedule(self, time_s: float, etype: EventType, payload: dict) -> None:
        pri = int(getattr(EventPriority, etype.name))
        self._seq += 1
        heapq.heappush(self._eq, Event(time_s, pri, self._seq, etype, payload))

    def _schedule_message(self, deliver_s: float, msg: Message) -> None:
        self._schedule(deliver_s, EventType.MESSAGE_DELIVER, {"msg_id": msg.msg_id})

    def available_requests(self) -> list[Request]:
        return [r for r in self.requests.values() if r.status == RequestStatus.AVAILABLE]

    def _sync_idle_ready(self, vehicle_id: str) -> None:
        v = self.vehicles[vehicle_id]
        if not v.busy and v.mode != VehicleMode.EMERGENCY_STRANDED and v.ready_s < self.now_s:
            v.total_wait_s += self.now_s - v.ready_s
            v.ready_s = self.now_s

    def projected(self, vehicle_id: str):
        return projected_state_after_lock(
            self.vehicles[vehicle_id],
            self.requests,
            self.router,
            self.energy,
            self.depot_node,
            self.now_s,
        )

    def check_insertion(self, vehicle_id: str, request_id: str) -> FeasibilityCheck:
        self._sync_idle_ready(vehicle_id)
        v = self.vehicles[vehicle_id]
        if v.mode == VehicleMode.EMERGENCY_STRANDED:
            return FeasibilityCheck(False, "emergency_stranded")
        req = self.requests[request_id]
        return insertion_cost(
            v,
            req,
            self.requests,
            self.router,
            self.energy,
            self.depot_node,
            self.payload_max,
            self.shift_end_s,
            self.now_s,
        )

    def try_assign(
        self,
        vehicle_id: str,
        request_id: str,
        *,
        force_position: int | None = None,
        start_leg: bool = True,
    ) -> bool:
        """Claim + insert into editable suffix only; active leg immutable."""

        req = self.requests[request_id]
        if req.status != RequestStatus.AVAILABLE:
            self.n_failed_claims += 1
            return False
        if not self.registry.try_claim(request_id, vehicle_id, self.now_s):
            self.n_failed_claims += 1
            return False

        self._sync_idle_ready(vehicle_id)
        v = self.vehicles[vehicle_id]
        if v.mode == VehicleMode.EMERGENCY_STRANDED:
            self.registry.release(request_id, vehicle_id)
            self.n_failed_claims += 1
            return False

        proj = self.projected(vehicle_id)
        locked = locked_prefix(v)
        suffix_pickups = [s for s in editable_suffix(v) if s.kind == "pickup"]
        positions = range(len(suffix_pickups) + 1) if force_position is None else [force_position]

        best_suffix = None
        best_cost = None
        nom_energy = EnergyModel(
            self.energy.consumption_kwh_per_km,
            0.0,
            self.energy.battery_kwh_max,
            self.energy.reserve_soc,
            self.energy.charge_power_kw,
            realization_mode=self.energy.realization_mode,
            scenario_seed=self.energy.scenario_seed,
        )
        base_chk = simulate_plan_conservative(
            proj, suffix_pickups, self.requests, self.router, self.energy,
            self.depot_node, self.payload_max, self.shift_end_s,
        )
        base_travel = float(base_chk.total_travel_s) if base_chk.feasible else 0.0

        for pos in positions:
            new_suffix = list(suffix_pickups)
            if pos < 0 or pos > len(new_suffix):
                continue
            new_suffix.insert(pos, Stop("pickup", request_id, req.snap_node))
            chk_cons = simulate_plan_conservative(
                proj, new_suffix, self.requests, self.router, self.energy,
                self.depot_node, self.payload_max, self.shift_end_s,
            )
            chk_nom = simulate_plan_conservative(
                proj, new_suffix, self.requests, self.router, nom_energy,
                self.depot_node, self.payload_max, self.shift_end_s,
            )
            if chk_nom.feasible and not chk_cons.feasible:
                self.energy_changed_dispatch += 1
            if not chk_cons.feasible:
                if chk_cons.energy_binding:
                    self.planned_energy_rejections += 1
                continue
            # Marginal travel vs current editable plan (force_position still validated)
            cost = float(chk_cons.total_travel_s) - base_travel
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_suffix = new_suffix

        if best_suffix is None:
            self.registry.release(request_id, vehicle_id)
            self.n_failed_claims += 1
            return False

        req.status = RequestStatus.COMMITTED
        req.owner = vehicle_id
        if request_id not in v.committed:
            v.committed.append(request_id)
        depot_tail = [s for s in editable_suffix(v) if s.kind.startswith("depot")]
        v.plan = list(locked) + list(best_suffix) + depot_tail
        self.n_claims += 1
        if start_leg and not v.busy:
            self._start_next_leg(vehicle_id)
        return True

    def try_reassign(self, from_v: str, to_v: str, request_id: str) -> bool:
        """Atomic reassignment: validate then commit; else leave source unchanged."""

        req = self.requests[request_id]
        if req.status != RequestStatus.COMMITTED or req.owner != from_v:
            return False
        fv = self.vehicles[from_v]
        if fv.moving_to and fv.moving_to.request_id == request_id:
            return False  # locked active leg

        # Snapshot
        snap_from_plan = list(fv.plan)
        snap_from_committed = list(fv.committed)
        snap_req_status = req.status
        snap_req_owner = req.owner

        # Build candidate source plan without request
        new_from_plan = [
            s for s in fv.plan
            if not (s.kind == "pickup" and s.request_id == request_id)
        ]
        # Validate source remaining plan from projected state
        fv_tmp = copy.deepcopy(fv)
        fv_tmp.plan = new_from_plan
        if request_id in fv_tmp.committed:
            fv_tmp.committed.remove(request_id)
        proj_from = projected_state_after_lock(
            fv_tmp, self.requests, self.router, self.energy, self.depot_node, self.now_s
        )
        suffix_from = [s for s in editable_suffix(fv_tmp) if s.kind == "pickup"]
        chk_from = simulate_plan_conservative(
            proj_from, suffix_from, self.requests, self.router, self.energy,
            self.depot_node, self.payload_max, self.shift_end_s,
        )
        if not chk_from.feasible and suffix_from:
            return False

        # Validate destination insertion without mutating
        tv = self.vehicles[to_v]
        # Temporarily mark request available for insertion check
        req.status = RequestStatus.AVAILABLE
        req.owner = None
        chk_to = self.check_insertion(to_v, request_id)
        if not chk_to.feasible:
            req.status = snap_req_status
            req.owner = snap_req_owner
            return False

        # Commit: release from source then assign to dest
        self.registry.release(request_id, from_v)
        fv.plan = new_from_plan
        if request_id in fv.committed:
            fv.committed.remove(request_id)
        req.status = RequestStatus.AVAILABLE
        req.owner = None
        ok = self.try_assign(to_v, request_id)
        if not ok:
            # Rollback source
            fv.plan = snap_from_plan
            fv.committed = snap_from_committed
            req.status = snap_req_status
            req.owner = snap_req_owner
            self.registry.try_claim(request_id, from_v, self.now_s)
            return False
        self.n_reassignments += 1
        tv.n_reassignments += 1
        return True

    def _snapshot_world(self) -> dict[str, Any]:
        return {
            "vehicles": copy.deepcopy(self.vehicles),
            "requests": {
                rid: (r.status, r.owner, list(getattr(r, "__dict__", {})))
                for rid, r in self.requests.items()
            },
            "req_simple": {rid: (r.status, r.owner) for rid, r in self.requests.items()},
            "registry": copy.deepcopy(self.registry.claims),
            "eq": list(self._eq),
            "seq": self._seq,
            "n_claims": self.n_claims,
            "n_failed_claims": self.n_failed_claims,
            "planned_energy_rejections": self.planned_energy_rejections,
        }

    def _restore_world(self, snap: dict[str, Any]) -> None:
        self.vehicles = snap["vehicles"]
        for rid, (st, owner) in snap["req_simple"].items():
            self.requests[rid].status = st
            self.requests[rid].owner = owner
        self.registry.claims = snap["registry"]
        self._eq = list(snap["eq"])
        self._seq = snap["seq"]
        self.n_claims = snap["n_claims"]
        self.n_failed_claims = snap["n_failed_claims"]
        self.planned_energy_rejections = snap["planned_energy_rejections"]

    def commit_fleet_plans(
        self,
        assignment: dict[str, list[str]],
        *,
        stop_plans: dict[str, list[Stop]] | None = None,
    ) -> bool:
        """Two-phase atomic plan commit preserving exact pickup order.

        Partial updates: only vehicles listed in ``assignment`` are released/rebuilt.
        Omitted vehicles keep their commitments, plans, and ownership unchanged.

        Full-fleet replacement: pass every vehicle id (possibly with empty editable lists).

        Optional ``stop_plans[vid]``: editable stop sequence (pickups + depot_charge)
        used for validation and commit (Stage 5 charge-augmented plans). Pickup order
        in stop_plans must match editable request ids in ``assignment``.

        1) Validate without mutating. 2) Commit ownership+plans for touched vehicles.
        3) Activate legs for touched idle vehicles. On failure, restore full state.
        """

        if not assignment:
            return True
        unknown = [vid for vid in assignment if vid not in self.vehicles]
        if unknown:
            return False

        touched = set(assignment.keys())
        locked_by_v: dict[str, list[str]] = {vid: [] for vid in self.vehicles}
        for vid, v in self.vehicles.items():
            if v.moving_to and v.moving_to.kind == "pickup" and v.moving_to.request_id:
                locked_by_v[vid].append(v.moving_to.request_id)

        # Unique ownership within the proposed touched assignment
        seen: set[str] = set()
        for vid, rids in assignment.items():
            for rid in rids:
                if rid in seen:
                    return False
                seen.add(rid)

        # Phase 1 — validate (shadow statuses only, then restore)
        for vid, rids in assignment.items():
            locked = locked_by_v.get(vid, [])
            for rid in locked:
                if rid not in rids:
                    return False
            editable = [rid for rid in rids if rid not in locked]
            for rid in editable:
                if rid not in self.requests:
                    return False
                st = self.requests[rid].status
                if st not in {RequestStatus.AVAILABLE, RequestStatus.COMMITTED}:
                    return False
                # Cannot steal a commitment from an omitted vehicle in a partial update
                owner = self.requests[rid].owner
                if st == RequestStatus.COMMITTED and owner is not None and owner not in touched:
                    return False
            status_backup = {rid: self.requests[rid].status for rid in editable}
            for rid in editable:
                self.requests[rid].status = RequestStatus.AVAILABLE
            if stop_plans is not None and vid in stop_plans:
                plan = list(stop_plans[vid])
                plan_pickups = [s.request_id for s in plan if s.kind == "pickup"]
                if plan_pickups != editable:
                    for rid, st in status_backup.items():
                        self.requests[rid].status = st
                    return False
            else:
                plan = [Stop("pickup", rid, self.requests[rid].snap_node) for rid in editable]
            proj = self.projected(vid)
            chk = simulate_plan_conservative(
                proj, plan, self.requests, self.router, self.energy,
                self.depot_node, self.payload_max, self.shift_end_s,
            )
            for rid, st in status_backup.items():
                self.requests[rid].status = st
            if not chk.feasible:
                return False

        # Track which requests were newly available before this transaction
        newly_available = {
            rid for rid, r in self.requests.items() if r.status == RequestStatus.AVAILABLE
        }
        snap = self._snapshot_world()
        try:
            # Phase 2 — release editable commitments only for touched vehicles
            for vid in touched:
                v = self.vehicles[vid]
                locked = set(locked_by_v.get(vid, []))
                for rid in list(v.committed):
                    if rid in locked:
                        continue
                    if self.requests[rid].status == RequestStatus.COMMITTED and self.requests[rid].owner == vid:
                        self.registry.release(rid, vid)
                        self.requests[rid].status = RequestStatus.AVAILABLE
                        self.requests[rid].owner = None
                    if rid in v.committed:
                        v.committed.remove(rid)

            for vid, rids in assignment.items():
                v = self.vehicles[vid]
                locked = locked_by_v.get(vid, [])
                locked_stops = list(locked_prefix(v))
                if stop_plans is not None and vid in stop_plans:
                    editable_stops = list(stop_plans[vid])
                else:
                    editable_stops = [
                        Stop("pickup", rid, self.requests[rid].snap_node)
                        for rid in rids
                        if rid not in locked
                    ]
                for stop in editable_stops:
                    if stop.kind != "pickup" or stop.request_id is None:
                        continue
                    rid = stop.request_id
                    assert rid is not None
                    if self.requests[rid].status == RequestStatus.COMMITTED and self.requests[rid].owner not in (None, vid):
                        # Owner must be another touched vehicle already released above
                        other = self.requests[rid].owner
                        if other not in touched:
                            raise RuntimeError("ownership conflict during partial commit")
                        self.registry.release(rid, other)
                        self.requests[rid].status = RequestStatus.AVAILABLE
                        self.requests[rid].owner = None
                        if rid in self.vehicles[other].committed:
                            self.vehicles[other].committed.remove(rid)
                    if not self.registry.try_claim(rid, vid, self.now_s):
                        if self.registry.owner_of(rid) != vid:
                            raise RuntimeError(f"claim failed {rid}")
                    if rid in newly_available:
                        self.n_claims += 1
                        newly_available.discard(rid)
                    self.requests[rid].status = RequestStatus.COMMITTED
                    self.requests[rid].owner = vid
                    if rid not in v.committed:
                        v.committed.append(rid)
                v.plan = locked_stops + editable_stops

            # Phase 3 — activate only touched idle vehicles
            for vid in touched:
                v = self.vehicles[vid]
                if not v.busy and v.plan and v.mode != VehicleMode.EMERGENCY_STRANDED:
                    self._start_next_leg(vid)
            return True
        except Exception:
            self._restore_world(snap)
            return False

    def set_pickup_plan(self, vehicle_id: str, request_ids: list[str], *, charge: bool = False) -> bool:
        """Partial plan update for one vehicle; other vehicles are left unchanged."""

        locked = []
        v = self.vehicles[vehicle_id]
        if v.moving_to and v.moving_to.kind == "pickup" and v.moving_to.request_id:
            locked.append(v.moving_to.request_id)
        proposed = locked + [rid for rid in request_ids if rid not in locked]
        ok = self.commit_fleet_plans({vehicle_id: proposed})
        if ok and charge:
            # Explicit charge on this vehicle only — do not flip episode-wide config
            self.request_return_depot(vehicle_id, charge=True, target_soc=1.0)
        return ok

    def request_return_depot(
        self,
        vehicle_id: str,
        *,
        charge: bool | None = None,
        target_soc: float | None = None,
    ) -> None:
        """Queue depot return; optional discrete-target charge (target_soc in [0,1])."""
        v = self.vehicles[vehicle_id]
        if v.mode == VehicleMode.EMERGENCY_STRANDED:
            return
        # Explicit charge arg wins; otherwise episode default. Never mutate config here.
        do_charge = self.config.charge_on_return if charge is None else bool(charge)
        kind = "depot_charge" if do_charge else "depot_unload"
        tgt_kwh: float | None = None
        if do_charge:
            soc = 1.0 if target_soc is None else float(target_soc)
            soc = max(0.0, min(1.0, soc))
            tgt_kwh = soc * float(self.energy.battery_kwh_max)
        stop = Stop(kind, None, self.depot_node, target_kwh=tgt_kwh)
        if v.busy:
            if not any(s.kind.startswith("depot") for s in editable_suffix(v)):
                v.plan = list(locked_prefix(v)) + editable_suffix(v) + [stop]
            elif do_charge:
                # Refresh charge target on existing depot stop in editable suffix
                new_plan = list(locked_prefix(v)) + editable_suffix(v)
                for i, s in enumerate(new_plan):
                    if s.kind.startswith("depot"):
                        new_plan[i] = Stop(kind, None, self.depot_node, target_kwh=tgt_kwh)
                        break
                v.plan = new_plan
            return
        v.plan = [stop]
        self._start_next_leg(vehicle_id)

    def _enter_emergency(self, vehicle_id: str, reason: str, extra: dict | None = None) -> None:
        v = self.vehicles[vehicle_id]
        v.mode = VehicleMode.EMERGENCY_STRANDED
        v.busy = False
        v.moving_to = None
        v.path_nodes = []
        rec = {
            "event": "emergency_stranded",
            "vehicle_id": vehicle_id,
            "time_s": self.now_s,
            "battery_kwh": v.battery_kwh,
            "node": v.node,
            "reason": reason,
            **(extra or {}),
        }
        self.event_trace.append(rec)

    def _start_next_leg(self, vehicle_id: str) -> None:
        v = self.vehicles[vehicle_id]
        if v.busy or v.mode == VehicleMode.EMERGENCY_STRANDED:
            return
        if not v.plan:
            depot_kind = "depot_charge" if self.config.charge_on_return else "depot_unload"
            if self.config.auto_depot_when_idle_empty and v.node != self.depot_node and (
                v.load_kg > 0 or not v.committed
            ):
                v.plan = [Stop(depot_kind, None, self.depot_node)]
            else:
                return

        stop = v.plan[0]
        target = self.depot_node if stop.kind.startswith("depot") else self.requests[stop.request_id].snap_node
        depart_ready = max(float(v.ready_s), float(self.now_s))
        if depart_ready > v.ready_s:
            v.total_wait_s += depart_ready - v.ready_s
            v.ready_s = depart_ready

        gate = check_leg_dispatch(
            v.node, v.ready_s, v.battery_kwh, target, self.router, self.energy, self.depot_node,
            require_reserve_at_depot_after=True,
        )
        if not gate.feasible:
            self.planned_energy_rejections += 1
            # Cannot safely depart — strip unsafe stop if optional depot, else emergency
            if stop.kind.startswith("depot"):
                v.plan.pop(0)
                if not v.plan and v.node != self.depot_node:
                    self._enter_emergency(vehicle_id, gate.reason, {"stop": stop.kind})
                return
            # Pickup commitment that cannot be started safely
            if stop.request_id:
                rid = stop.request_id
                if rid in v.committed:
                    v.committed.remove(rid)
                self.registry.release(rid, vehicle_id)
                req = self.requests[rid]
                if req.status == RequestStatus.COMMITTED:
                    req.status = RequestStatus.EXPIRED
                    req.owner = None
                v.plan.pop(0)
            self._enter_emergency(vehicle_id, gate.reason, {"target": target})
            return

        rt = self.router.route(v.node, target, v.ready_s)
        if rt.arrival_s + 1e-9 < self.now_s:
            raise RuntimeError(f"computed arrival {rt.arrival_s} before now {self.now_s}")

        v.leg_seq += 1
        e_cons = self.energy.conservative_kwh(rt.length_m)
        e_real = self.energy.sample_realized_kwh(
            rt.length_m, self.rng, vehicle_id=vehicle_id, leg_seq=v.leg_seq
        )
        # Under bound, realized <= conservative
        assert e_real <= e_cons + 1e-9 or self.energy.realization_mode == "stochastic"

        v.busy = True
        v.mode = VehicleMode.EN_ROUTE
        v.moving_to = stop
        v.path_nodes = list(rt.path)
        v.path_length_m = rt.length_m
        v.departed_s = v.ready_s
        v.en_route_energy_kwh = e_real
        v.en_route_conservative_kwh = e_cons
        v.total_wait_s += rt.wait_s
        self.event_trace.append(
            {
                "event": "depart",
                "vehicle_id": vehicle_id,
                "time_s": self.now_s,
                "target": target,
                "battery_before": v.battery_kwh,
                "e_cons": e_cons,
                "e_real": e_real,
                "stop": stop.kind,
                "request_id": stop.request_id,
            }
        )
        self._schedule(rt.arrival_s, EventType.VEHICLE_ARRIVAL, {"vehicle_id": vehicle_id})

    def _record_reserve_if_needed(self, vehicle_id: str, battery_after: float, context: dict) -> None:
        v = self.vehicles[vehicle_id]
        if battery_after < self.energy.reserve_kwh - 1e-9:
            v.reserve_violations += 1
            if self.first_reserve_violation_trace is None:
                self.first_reserve_violation_trace = {
                    "vehicle_id": vehicle_id,
                    "time_s": self.now_s,
                    "battery_after_kwh": battery_after,
                    "reserve_kwh": self.energy.reserve_kwh,
                    **context,
                }
            self.event_trace.append({"event": "reserve_violation", **self.first_reserve_violation_trace})
        if battery_after < -1e-9:
            v.battery_exhaustion += 1
            self._enter_emergency(vehicle_id, "battery_exhaustion", {"battery": battery_after})

    def _on_arrival(self, vehicle_id: str) -> None:
        v = self.vehicles[vehicle_id]
        stop = v.moving_to
        assert stop is not None
        bat_before = v.battery_kwh
        v.battery_kwh -= v.en_route_energy_kwh
        v.energy_consumed_kwh += v.en_route_energy_kwh
        v.total_distance_m += v.path_length_m
        if v.departed_s is not None:
            v.total_travel_s += self.now_s - v.departed_s

        if stop.kind.startswith("depot"):
            v.node = self.depot_node
        else:
            v.node = self.requests[stop.request_id].snap_node

        self._record_reserve_if_needed(
            vehicle_id,
            v.battery_kwh,
            {
                "battery_before_kwh": bat_before,
                "e_real": v.en_route_energy_kwh,
                "e_cons": v.en_route_conservative_kwh,
                "destination": v.node,
                "commitment": stop.request_id,
                "why_allowed": "pre_dispatch_gate_passed_conservative",
            },
        )
        if v.mode == VehicleMode.EMERGENCY_STRANDED:
            return

        if stop.kind == "pickup":
            req = self.requests[stop.request_id]
            if req.status in {
                RequestStatus.COMPLETED,
                RequestStatus.EXPIRED,
                RequestStatus.REJECTED,
                RequestStatus.MISSED,
            }:
                # Stale event — drop stop and continue
                if v.plan and v.plan[0].request_id == stop.request_id:
                    v.plan.pop(0)
                v.moving_to = None
                v.busy = False
                v.mode = VehicleMode.IDLE
                v.ready_s = self.now_s
                self._start_next_leg(vehicle_id)
                return
            start = max(self.now_s, req.tw_start_s)
            # Hard deadline: service must finish by tw_end_s
            if start + req.service_s > req.tw_end_s + 1e-9:
                self._miss_pickup_on_arrival(
                    vehicle_id,
                    stop.request_id,
                    reason="deadline_unreachable_on_arrival",
                )
                return
            req.status = RequestStatus.IN_SERVICE
            req.service_start_s = start
            v.mode = VehicleMode.SERVING
            v.ready_s = start
            if start > self.now_s:
                v.total_wait_s += start - self.now_s
            self._schedule(
                start + req.service_s,
                EventType.SERVICE_END,
                {"vehicle_id": vehicle_id, "request_id": req.request_id},
            )
            return

        v.load_kg = 0.0
        v.n_depot_returns += 1
        v.ready_s = self.now_s
        if stop.kind == "depot_charge":
            bmax = float(self.energy.battery_kwh_max)
            if stop.target_kwh is not None:
                target = float(stop.target_kwh)
            else:
                target = bmax
            target = min(bmax, max(float(v.battery_kwh), target))
            need = max(0.0, target - float(v.battery_kwh))
            dur = self.energy.charge_time_s(need)
            if dur > 0:
                v.n_charges += 1
                v.mode = VehicleMode.CHARGING
                self._schedule(
                    self.now_s + dur,
                    EventType.CHARGE_END,
                    {
                        "vehicle_id": vehicle_id,
                        "target_kwh": target,
                        "energy_to_deliver_kwh": need,
                        "duration_s": dur,
                    },
                )
                return
        if v.plan and (
            (v.plan[0].kind == stop.kind and v.plan[0].request_id == stop.request_id)
            or v.plan[0].kind.startswith("depot")
        ):
            v.plan.pop(0)
        v.moving_to = None
        v.busy = False
        v.mode = VehicleMode.IDLE
        v.path_nodes = []
        self._maybe_decide("vehicle_idle")
        self._start_next_leg(vehicle_id)

    def _miss_pickup_on_arrival(self, vehicle_id: str, request_id: str, *, reason: str) -> None:
        """Hard-deadline miss: no COMPLETED; vehicle stays at customer node."""
        v = self.vehicles[vehicle_id]
        req = self.requests[request_id]
        req.status = RequestStatus.MISSED
        req.on_time = False
        req.service_start_s = None
        req.service_end_s = None
        if request_id in v.committed:
            v.committed.remove(request_id)
        v.plan = [s for s in v.plan if not (s.kind == "pickup" and s.request_id == request_id)]
        self.registry.release(request_id, vehicle_id)
        req.owner = None
        self.event_trace.append(
            {
                "event": "pickup_missed",
                "reason": reason,
                "request_id": request_id,
                "vehicle_id": vehicle_id,
                "time_s": self.now_s,
                "tw_end_s": req.tw_end_s,
                "service_s": req.service_s,
            }
        )
        v.moving_to = None
        v.busy = False
        v.mode = VehicleMode.IDLE
        v.ready_s = self.now_s
        v.path_nodes = []
        self._maybe_decide("pickup_missed")
        self._start_next_leg(vehicle_id)

    def _on_service_end(self, vehicle_id: str, request_id: str) -> None:
        v = self.vehicles[vehicle_id]
        req = self.requests[request_id]
        if req.status == RequestStatus.COMPLETED:
            return  # no double completion
        if req.status not in {RequestStatus.IN_SERVICE, RequestStatus.COMMITTED}:
            v.moving_to = None
            v.busy = False
            v.mode = VehicleMode.IDLE
            v.ready_s = self.now_s
            self._start_next_leg(vehicle_id)
            return

        if v.load_kg + req.weight_kg > self.payload_max + 1e-9:
            v.payload_violations += 1
        else:
            v.load_kg += req.weight_kg
        req.service_end_s = self.now_s
        # Hard-deadline gate on arrival: COMPLETED ≡ on-time
        req.on_time = True
        req.status = RequestStatus.COMPLETED
        if request_id in v.committed:
            v.committed.remove(request_id)
        # Remove by ID anywhere in plan (not only plan[0])
        v.plan = [s for s in v.plan if not (s.kind == "pickup" and s.request_id == request_id)]
        v.moving_to = None
        v.busy = False
        v.mode = VehicleMode.IDLE
        v.ready_s = self.now_s
        self._maybe_decide("service_end")
        self._start_next_leg(vehicle_id)

    def _on_charge_end(self, vehicle_id: str, target_kwh: float, *, energy_delivered: float = 0.0, duration_s: float = 0.0) -> None:
        v = self.vehicles[vehicle_id]
        before = float(v.battery_kwh)
        v.battery_kwh = min(self.energy.battery_kwh_max, float(target_kwh))
        delivered = energy_delivered if energy_delivered > 0 else max(0.0, float(v.battery_kwh) - before)
        v.energy_delivered_kwh += delivered
        if duration_s > 0:
            v.charge_duration_s += duration_s
        else:
            # Reconstruct from charge model if payload omitted
            v.charge_duration_s += self.energy.charge_time_s(delivered)
        v.ready_s = self.now_s
        if v.plan and v.plan[0].kind.startswith("depot"):
            v.plan.pop(0)
        v.moving_to = None
        v.busy = False
        v.mode = VehicleMode.IDLE
        self._maybe_decide("charge_end")
        self._start_next_leg(vehicle_id)

    def _maybe_decide(self, reason: str) -> None:
        if self.policy is None:
            return
        t0 = time.perf_counter()
        if self.config.info_mode == "restricted":
            two_phase = bool(getattr(self.policy, "two_phase_bidding", False))
            if two_phase and reason == "request_release":
                # Phase A: exchange bids only (no claims).
                for vid in self.vehicles:
                    obs = build_restricted_observation(self, vid)
                    actions = ActionInterface(self, actor_vehicle_id=vid)
                    self.policy.on_decision(obs, actions, "bid_exchange")
                # Flush zero-delay task bids into local tables before assign.
                self._flush_zero_delay_task_bids()
                # Phase B: claim using received bids.
                for vid in self.vehicles:
                    obs = build_restricted_observation(self, vid)
                    for peer in obs.peers.values():
                        self.info_ages.append(max(0.0, obs.now_s - peer.as_of_s))
                    actions = ActionInterface(self, actor_vehicle_id=vid)
                    self.policy.on_decision(obs, actions, "bid_assign")
            else:
                for vid in self.vehicles:
                    obs = build_restricted_observation(self, vid)
                    for peer in obs.peers.values():
                        self.info_ages.append(max(0.0, obs.now_s - peer.as_of_s))
                    actions = ActionInterface(self, actor_vehicle_id=vid)
                    self.policy.on_decision(obs, actions, reason)
        else:
            obs = build_full_observation(self)
            actions = ActionInterface(self, actor_vehicle_id=None)
            self.policy.on_decision(obs, actions, reason)
        self._decision_runtimes.append(time.perf_counter() - t0)

    def _flush_zero_delay_task_bids(self) -> None:
        """Deliver pending same-time task_bid messages into local_bids without waiting."""

        if float(self.bus.delay_s) > 1e-12:
            return
        for msg in self.bus.history:
            if msg.delivered or msg.kind != "task_bid":
                continue
            if abs(msg.deliver_s - self.now_s) > 1e-9:
                continue
            self.bus.deliver(msg)
            rid = str(msg.payload.get("request_id", ""))
            sender = str(msg.payload.get("sender_id", msg.sender))
            if rid:
                self.local_bids.setdefault(msg.recipient, {}).setdefault(rid, {})[sender] = dict(
                    msg.payload
                )

    def broadcast_state(self, vehicle_id: str) -> None:
        v = self.vehicles[vehicle_id]
        payload = {
            "vehicle_id": vehicle_id,
            "node": v.node,
            "ready_s": v.ready_s,
            "battery_kwh": v.battery_kwh,
            "load_kg": v.load_kg,
            "committed": list(v.committed),
            "as_of_s": self.now_s,
        }
        for peer in self.vehicles:
            if peer == vehicle_id:
                continue
            self.bus.send(
                vehicle_id,
                peer,
                "state_update",
                payload,
                self.now_s,
                schedule_delivery=self._schedule_message,
            )

    def broadcast_task_bid(self, vehicle_id: str, payload: dict[str, Any]) -> int:
        """Broadcast a compact task bid to all peers. Returns serialized payload bytes."""

        import json

        body = dict(payload)
        body.setdefault("sender_id", vehicle_id)
        nbytes = len(json.dumps(body, separators=(",", ":")).encode("utf-8"))
        zero_delay = float(self.bus.delay_s) <= 1e-12
        for peer in self.vehicles:
            if peer == vehicle_id:
                continue
            msg = self.bus.send(
                vehicle_id,
                peer,
                "task_bid",
                body,
                self.now_s,
                schedule_delivery=None if zero_delay else self._schedule_message,
            )
            self.n_bid_messages += 1
            self.n_bid_bytes += nbytes
            if zero_delay:
                # Immediate local delivery for same-tick bid rounds.
                self.bus.deliver(msg)
                rid = str(body.get("request_id", ""))
                sender = str(body.get("sender_id", vehicle_id))
                if rid:
                    self.local_bids.setdefault(peer, {}).setdefault(rid, {})[sender] = dict(body)
        return nbytes

    def run(self) -> EpisodeMetrics:
        while self._eq:
            ev = heapq.heappop(self._eq)
            if ev.time_s + 1e-12 < self.now_s:
                raise RuntimeError(f"event causality violated: {ev.type} at {ev.time_s} < now {self.now_s}")
            self.now_s = ev.time_s

            if ev.type == EventType.REQUEST_RELEASE:
                rid = ev.payload["request_id"]
                req = self.requests[rid]
                if req.status == RequestStatus.UNRELEASED:
                    req.status = RequestStatus.AVAILABLE
                    if self.config.decision_on_release:
                        self._maybe_decide("request_release")
            elif ev.type == EventType.VEHICLE_ARRIVAL:
                self._on_arrival(ev.payload["vehicle_id"])
            elif ev.type == EventType.SERVICE_END:
                self._on_service_end(ev.payload["vehicle_id"], ev.payload["request_id"])
            elif ev.type == EventType.CHARGE_END:
                self._on_charge_end(
                    ev.payload["vehicle_id"],
                    ev.payload["target_kwh"],
                    energy_delivered=float(ev.payload.get("energy_to_deliver_kwh", 0.0)),
                    duration_s=float(ev.payload.get("duration_s", 0.0)),
                )
            elif ev.type == EventType.MESSAGE_DELIVER:
                msg = next(m for m in self.bus.history if m.msg_id == ev.payload["msg_id"])
                self.bus.deliver(msg)
                if msg.kind == "state_update":
                    peer = msg.payload["vehicle_id"]
                    self.local_views.setdefault(msg.recipient, {})[peer] = dict(msg.payload)
                elif msg.kind == "task_bid":
                    rid = str(msg.payload.get("request_id", ""))
                    sender = str(msg.payload.get("sender_id", msg.sender))
                    if rid:
                        self.local_bids.setdefault(msg.recipient, {}).setdefault(rid, {})[sender] = dict(
                            msg.payload
                        )
                self._maybe_decide("message")
            elif ev.type == EventType.PERIODIC_BROADCAST:
                # Independent clock: broadcast only, then allow decision with delivered info later
                for vid in self.vehicles:
                    self.broadcast_state(vid)
                self._maybe_decide("periodic_broadcast")
            elif ev.type == EventType.SHIFT_END:
                self._expire_open_requests()
                for vid, v in self.vehicles.items():
                    if v.node != self.depot_node and not v.busy and v.mode != VehicleMode.EMERGENCY_STRANDED:
                        self.request_return_depot(vid, charge=False)
            elif ev.type == EventType.EPISODE_END:
                break
            elif ev.type == EventType.DECISION_EPOCH:
                self._maybe_decide("epoch")

        return self._metrics()

    def _expire_open_requests(self) -> None:
        for req in self.requests.values():
            if req.status == RequestStatus.IN_SERVICE:
                continue  # finish service already scheduled
            if req.status in {RequestStatus.AVAILABLE, RequestStatus.COMMITTED, RequestStatus.UNRELEASED}:
                # Do not expire locked in-transit commitments
                if req.status == RequestStatus.COMMITTED and req.owner:
                    v = self.vehicles[req.owner]
                    if v.moving_to and v.moving_to.request_id == req.request_id:
                        continue
                if req.status == RequestStatus.COMMITTED and req.owner:
                    v = self.vehicles[req.owner]
                    v.plan = [s for s in v.plan if s.request_id != req.request_id]
                    if req.request_id in v.committed:
                        v.committed.remove(req.request_id)
                    self.registry.release(req.request_id, req.owner)
                    req.owner = None
                if req.status not in {
                    RequestStatus.COMPLETED,
                    RequestStatus.REJECTED,
                    RequestStatus.MISSED,
                }:
                    req.status = RequestStatus.EXPIRED

    def reject_request(self, request_id: str) -> None:
        req = self.requests[request_id]
        if req.status == RequestStatus.AVAILABLE:
            req.status = RequestStatus.REJECTED

    def _metrics(self) -> EpisodeMetrics:
        served = [r for r in self.requests.values() if r.status == RequestStatus.COMPLETED]
        on_time = [r for r in served if r.on_time]
        rejected = [r for r in self.requests.values() if r.status == RequestStatus.REJECTED]
        expired = [r for r in self.requests.values() if r.status == RequestStatus.EXPIRED]
        missed = [r for r in self.requests.values() if r.status == RequestStatus.MISSED]
        m = EpisodeMetrics(
            scenario_id=self.scenario_id,
            policy=getattr(self.policy, "name", "none"),
            info_mode=self.config.info_mode,
            seed=self.config.seed,
            n_requests=len(self.requests),
            n_served=len(served),
            n_on_time=len(on_time),
            n_rejected=len(rejected),
            n_expired=len(expired),
            n_missed=len(missed),
            total_distance_m=sum(v.total_distance_m for v in self.vehicles.values()),
            total_travel_s=sum(v.total_travel_s for v in self.vehicles.values()),
            total_wait_s=sum(v.total_wait_s for v in self.vehicles.values()),
            energy_consumed_kwh=sum(v.energy_consumed_kwh for v in self.vehicles.values()),
            energy_delivered_kwh=sum(v.energy_delivered_kwh for v in self.vehicles.values()),
            charge_duration_s=sum(v.charge_duration_s for v in self.vehicles.values()),
            battery_reserve_violations=sum(v.reserve_violations for v in self.vehicles.values()),
            battery_exhaustion=sum(v.battery_exhaustion for v in self.vehicles.values()),
            planned_energy_rejections=self.planned_energy_rejections,
            payload_violations=sum(v.payload_violations for v in self.vehicles.values()),
            n_depot_returns=sum(v.n_depot_returns for v in self.vehicles.values()),
            n_charges=sum(v.n_charges for v in self.vehicles.values()),
            n_messages=self.bus.n_sent,
            n_claims=self.n_claims,
            n_failed_claims=self.n_failed_claims + self.registry.n_rejected_duplicates,
            n_reassignments=self.n_reassignments,
            mean_message_delay_s=(self.bus.total_delay_s / self.bus.n_sent) if self.bus.n_sent else 0.0,
            mean_info_age_s=(sum(self.info_ages) / len(self.info_ages)) if self.info_ages else 0.0,
            mean_decision_runtime_s=(sum(self._decision_runtimes) / len(self._decision_runtimes))
            if self._decision_runtimes
            else 0.0,
            n_decisions=len(self._decision_runtimes),
            energy_changed_dispatch=self.energy_changed_dispatch,
            config={
                "energy_uncertainty_delta": self.config.energy_uncertainty_delta,
                "message_delay_s": self.config.message_delay_s,
                "initial_soc": self.config.initial_soc,
                "n_vehicles": len(self.vehicles),
                "charge_on_return": self.config.charge_on_return,
                "realization_mode": self.config.realization_mode,
            },
        )
        m.finalize()
        return m
