"""Event-driven online electric pickup simulator."""

from __future__ import annotations

import copy
import heapq
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np

from race_casablanca.coordination.messaging import Message, MessageBus
from race_casablanca.coordination.ownership import TaskRegistry
from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.feasibility_check import FeasibilityCheck, insertion_cost, simulate_plan_conservative
from race_casablanca.sim.metrics import EpisodeMetrics
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.types import (
    Event,
    EventPriority,
    EventType,
    Request,
    RequestStatus,
    Stop,
    VehicleState,
)


class Policy(Protocol):
    name: str

    def on_decision(self, sim: "OnlineSimulator", reason: str) -> None: ...


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
    extras: dict[str, Any] = field(default_factory=dict)


class OnlineSimulator:
    """Deterministic event queue; stochastic energy only via seeded RNG."""

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
        )
        owned_router = router is None
        self.router = router if router is not None else RouteCache(graph, model, day=config.day)
        self.registry = TaskRegistry()
        self.bus = MessageBus(delay_s=float(config.message_delay_s))

        self.requests: dict[str, Request] = {
            r.request_id: copy.deepcopy(r) for r in requests
        }
        for r in self.requests.values():
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        # Warm OD paths among depot and request snaps (exact same free-flow semantics).
        # Skip when caller supplies a pre-warmed shared router.
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
        self._seen_future_guard = True  # policies use only released set

        # Local views for restricted mode (vehicle_id -> last known peer snapshot)
        self.local_views: dict[str, dict[str, Any]] = {vid: {} for vid in self.vehicles}

        for req in self.requests.values():
            self._schedule(req.release_s, EventType.REQUEST_RELEASE, {"request_id": req.request_id})
        self._schedule(self.shift_end_s, EventType.SHIFT_END, {})
        self._schedule(self.shift_end_s + 24 * 3600.0, EventType.EPISODE_END, {})

    # ------------------------------------------------------------------ events
    def _schedule(self, time_s: float, etype: EventType, payload: dict) -> None:
        pri = int(getattr(EventPriority, etype.name))
        self._seq += 1
        heapq.heappush(self._eq, Event(time_s, pri, self._seq, etype, payload))

    def _schedule_message(self, deliver_s: float, msg: Message) -> None:
        self._schedule(deliver_s, EventType.MESSAGE_DELIVER, {"msg_id": msg.msg_id})

    # ------------------------------------------------------------------- observe
    def released_requests(self) -> list[Request]:
        return [
            r
            for r in self.requests.values()
            if r.status
            in {
                RequestStatus.AVAILABLE,
                RequestStatus.COMMITTED,
                RequestStatus.IN_SERVICE,
                RequestStatus.COMPLETED,
                RequestStatus.EXPIRED,
                RequestStatus.REJECTED,
            }
        ]

    def available_requests(self) -> list[Request]:
        return [r for r in self.requests.values() if r.status == RequestStatus.AVAILABLE]

    def observe_full(self) -> dict[str, Any]:
        assert self.config.info_mode == "full"
        return {
            "now_s": self.now_s,
            "vehicles": {k: copy.deepcopy(v) for k, v in self.vehicles.items()},
            "available": [r.request_id for r in self.available_requests()],
            "requests": {rid: copy.deepcopy(r) for rid, r in self.requests.items() if r.status != RequestStatus.UNRELEASED},
        }

    def observe_vehicle(self, vehicle_id: str) -> dict[str, Any]:
        v = self.vehicles[vehicle_id]
        own = [rid for rid in v.committed]
        msgs = self.bus.pop_inbox(vehicle_id)
        return {
            "now_s": self.now_s,
            "self": copy.deepcopy(v),
            "own_requests": own,
            "messages": msgs,
            "available_announced": [
                r.request_id
                for r in self.available_requests()
                # In restricted mode, unclaimed available tasks are visible via
                # a thin announcement channel (documented central bulletin).
            ],
            "peer_views": copy.deepcopy(self.local_views.get(vehicle_id, {})),
        }

    # ------------------------------------------------------------------- actions
    def _sync_idle_ready(self, vehicle_id: str) -> None:
        v = self.vehicles[vehicle_id]
        if not v.busy and v.ready_s < self.now_s:
            v.total_wait_s += self.now_s - v.ready_s
            v.ready_s = self.now_s

    def check_insertion(self, vehicle_id: str, request_id: str) -> FeasibilityCheck:
        self._sync_idle_ready(vehicle_id)
        v = self.vehicles[vehicle_id]
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
        )

    def try_assign(self, vehicle_id: str, request_id: str, *, force_position: int | None = None) -> bool:
        """Claim + insert request if feasibility-aware check passes."""

        req = self.requests[request_id]
        if req.status != RequestStatus.AVAILABLE:
            return False
        if not self.registry.try_claim(request_id, vehicle_id, self.now_s):
            return False

        self._sync_idle_ready(vehicle_id)
        v = self.vehicles[vehicle_id]
        pickups = [s for s in v.plan if s.kind == "pickup"]
        positions = range(len(pickups) + 1) if force_position is None else [force_position]
        best_plan = None
        best_cost = None
        for pos in positions:
            new_pickups = list(pickups)
            if pos < 0 or pos > len(new_pickups):
                continue
            new_pickups.insert(pos, Stop("pickup", request_id, req.snap_node))
            # Compare against nominal vs conservative to detect energy-changed decisions
            nom_energy = EnergyModel(
                self.energy.consumption_kwh_per_km,
                0.0,
                self.energy.battery_kwh_max,
                self.energy.reserve_soc,
                self.energy.charge_power_kw,
            )
            chk_cons = simulate_plan_conservative(
                v, new_pickups, self.requests, self.router, self.energy,
                self.depot_node, self.payload_max, self.shift_end_s,
            )
            chk_nom = simulate_plan_conservative(
                v, new_pickups, self.requests, self.router, nom_energy,
                self.depot_node, self.payload_max, self.shift_end_s,
            )
            if chk_nom.feasible and not chk_cons.feasible:
                self.energy_changed_dispatch += 1
            if not chk_cons.feasible:
                continue
            if best_cost is None or chk_cons.added_travel_s < best_cost:
                best_cost = chk_cons.added_travel_s
                best_plan = new_pickups
        if best_plan is None:
            self.registry.release(request_id, vehicle_id)
            return False

        req.status = RequestStatus.COMMITTED
        req.owner = vehicle_id
        v.committed.append(request_id)
        v.plan = list(best_plan)
        if not v.busy:
            self._start_next_leg(vehicle_id)
        return True

    def try_reassign(self, from_v: str, to_v: str, request_id: str) -> bool:
        req = self.requests[request_id]
        if req.status != RequestStatus.COMMITTED or req.owner != from_v:
            return False
        fv = self.vehicles[from_v]
        if any(s.request_id == request_id and fv.moving_to and fv.moving_to.request_id == request_id for s in [fv.moving_to] if s):
            return False
        # Remove from from_v plan
        fv.plan = [s for s in fv.plan if not (s.kind == "pickup" and s.request_id == request_id)]
        if request_id in fv.committed:
            fv.committed.remove(request_id)
        self.registry.release(request_id, from_v)
        req.status = RequestStatus.AVAILABLE
        req.owner = None
        return self.try_assign(to_v, request_id)

    def set_pickup_plan(self, vehicle_id: str, request_ids: list[str], *, charge: bool = False) -> bool:
        """Replace reassignable commitments with a new ordered plan (RH helper)."""

        v = self.vehicles[vehicle_id]
        # Keep in-service / completed ownership; only reassign committed not started
        locked = set()
        if v.moving_to and v.moving_to.kind == "pickup" and v.moving_to.request_id:
            locked.add(v.moving_to.request_id)
        for rid in list(v.committed):
            if rid in locked:
                continue
            req = self.requests[rid]
            if req.status == RequestStatus.COMMITTED:
                self.registry.release(rid, vehicle_id)
                req.status = RequestStatus.AVAILABLE
                req.owner = None
                v.committed.remove(rid)
        v.plan = [s for s in v.plan if s.kind == "pickup" and s.request_id in locked]

        ok = True
        for rid in request_ids:
            if rid in locked:
                continue
            if not self.try_assign(vehicle_id, rid):
                ok = False
        if charge and v.node != self.depot_node or True:
            # Optional trailing charge stop recorded when returning
            self.config.extras["prefer_charge"] = charge
        return ok

    def request_return_depot(self, vehicle_id: str, *, charge: bool | None = None) -> None:
        v = self.vehicles[vehicle_id]
        if v.busy:
            # Append after current plan pickups
            kind = "depot_charge" if (self.config.charge_on_return if charge is None else charge) else "depot_unload"
            if not any(s.kind.startswith("depot") for s in v.plan):
                v.plan.append(Stop(kind, None, self.depot_node))
            return
        kind = "depot_charge" if (self.config.charge_on_return if charge is None else charge) else "depot_unload"
        v.plan = [Stop(kind, None, self.depot_node)]
        self._start_next_leg(vehicle_id)

    # --------------------------------------------------------------- locomotion
    def _start_next_leg(self, vehicle_id: str) -> None:
        v = self.vehicles[vehicle_id]
        if v.busy:
            return
        if not v.plan:
            depot_kind = "depot_charge" if self.config.charge_on_return else "depot_unload"
            if (
                self.config.auto_depot_when_idle_empty
                and v.node != self.depot_node
                and v.load_kg > 0
            ):
                v.plan = [Stop(depot_kind, None, self.depot_node)]
            elif (
                self.config.auto_depot_when_idle_empty
                and v.node != self.depot_node
                and not v.committed
            ):
                v.plan = [Stop(depot_kind, None, self.depot_node)]
            else:
                return
        stop = v.plan[0]
        target = self.depot_node if stop.kind.startswith("depot") else self.requests[stop.request_id].snap_node
        # Idle vehicles may have ready_s in the past; never depart before now.
        depart_ready = max(float(v.ready_s), float(self.now_s))
        if depart_ready > v.ready_s:
            v.total_wait_s += depart_ready - v.ready_s
            v.ready_s = depart_ready
        rt = self.router.route(v.node, target, v.ready_s)
        if rt.arrival_s + 1e-9 < self.now_s:
            raise RuntimeError(
                f"computed arrival {rt.arrival_s} before now {self.now_s} for {vehicle_id}"
            )
        e_real = self.energy.sample_realized_kwh(rt.length_m, self.rng)
        v.busy = True
        v.moving_to = stop
        v.path_nodes = list(rt.path)
        v.path_length_m = rt.length_m
        v.departed_s = v.ready_s
        v.en_route_energy_kwh = e_real
        v.total_wait_s += rt.wait_s
        self._schedule(rt.arrival_s, EventType.VEHICLE_ARRIVAL, {"vehicle_id": vehicle_id})

    def _on_arrival(self, vehicle_id: str) -> None:
        v = self.vehicles[vehicle_id]
        stop = v.moving_to
        assert stop is not None
        # Apply realized energy
        v.battery_kwh -= v.en_route_energy_kwh
        v.energy_consumed_kwh += v.en_route_energy_kwh
        v.total_distance_m += v.path_length_m
        if v.departed_s is not None:
            v.total_travel_s += self.now_s - v.departed_s
        if stop.kind.startswith("depot"):
            v.node = self.depot_node
        else:
            v.node = self.requests[stop.request_id].snap_node
        if v.battery_kwh < self.energy.reserve_kwh - 1e-9:
            v.reserve_violations += 1
        if v.battery_kwh < -1e-9:
            v.reserve_violations += 1  # physical underflow also counted

        if stop.kind == "pickup":
            req = self.requests[stop.request_id]
            start = max(self.now_s, req.tw_start_s)
            req.status = RequestStatus.IN_SERVICE
            req.service_start_s = start
            v.ready_s = start  # waiting until service start counted as wait
            if start > self.now_s:
                v.total_wait_s += start - self.now_s
            self._schedule(start + req.service_s, EventType.SERVICE_END, {"vehicle_id": vehicle_id, "request_id": req.request_id})
            return

        # Depot unload / charge
        v.load_kg = 0.0
        v.n_depot_returns += 1
        v.ready_s = self.now_s
        if stop.kind == "depot_charge":
            need = max(0.0, self.energy.battery_kwh_max - v.battery_kwh)
            dur = self.energy.charge_time_s(need)
            if dur > 0:
                v.n_charges += 1
                self._schedule(self.now_s + dur, EventType.CHARGE_END, {"vehicle_id": vehicle_id, "target_kwh": self.energy.battery_kwh_max})
                return
        v.plan.pop(0)
        v.moving_to = None
        v.busy = False
        v.path_nodes = []
        self._maybe_decide("vehicle_idle")
        self._start_next_leg(vehicle_id)

    def _on_service_end(self, vehicle_id: str, request_id: str) -> None:
        v = self.vehicles[vehicle_id]
        req = self.requests[request_id]
        if v.load_kg + req.weight_kg > self.payload_max + 1e-9:
            v.payload_violations += 1
        else:
            v.load_kg += req.weight_kg
        req.service_end_s = self.now_s
        req.on_time = req.service_end_s <= req.tw_end_s + 1e-9
        req.status = RequestStatus.COMPLETED
        if request_id in v.committed:
            v.committed.remove(request_id)
        if v.plan and v.plan[0].request_id == request_id:
            v.plan.pop(0)
        v.moving_to = None
        v.busy = False
        v.ready_s = self.now_s
        self._maybe_decide("service_end")
        self._start_next_leg(vehicle_id)

    def _on_charge_end(self, vehicle_id: str, target_kwh: float) -> None:
        v = self.vehicles[vehicle_id]
        v.battery_kwh = min(self.energy.battery_kwh_max, float(target_kwh))
        v.ready_s = self.now_s
        if v.plan and v.plan[0].kind.startswith("depot"):
            v.plan.pop(0)
        v.moving_to = None
        v.busy = False
        self._maybe_decide("charge_end")
        self._start_next_leg(vehicle_id)

    # ---------------------------------------------------------------- decisions
    def _maybe_decide(self, reason: str) -> None:
        if self.policy is None:
            return
        t0 = time.perf_counter()
        self.policy.on_decision(self, reason)
        self._decision_runtimes.append(time.perf_counter() - t0)

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

    # -------------------------------------------------------------------- run
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
                self._on_charge_end(ev.payload["vehicle_id"], ev.payload["target_kwh"])
            elif ev.type == EventType.MESSAGE_DELIVER:
                msg = next(m for m in self.bus.history if m.msg_id == ev.payload["msg_id"])
                self.bus.deliver(msg)
                if msg.kind == "state_update":
                    peer = msg.payload["vehicle_id"]
                    self.local_views.setdefault(msg.recipient, {})[peer] = dict(msg.payload)
                self._maybe_decide("message")
            elif ev.type == EventType.SHIFT_END:
                self._expire_open_requests()
                # Pull remaining vehicles home
                for vid, v in self.vehicles.items():
                    if v.node != self.depot_node and not v.busy:
                        self.request_return_depot(vid, charge=False)
            elif ev.type == EventType.EPISODE_END:
                break
            elif ev.type == EventType.DECISION_EPOCH:
                self._maybe_decide("epoch")

        return self._metrics()

    def _expire_open_requests(self) -> None:
        for req in self.requests.values():
            if req.status in {RequestStatus.AVAILABLE, RequestStatus.COMMITTED, RequestStatus.UNRELEASED}:
                if req.tw_end_s <= self.now_s + 1e-9 or req.status != RequestStatus.UNRELEASED:
                    if req.status == RequestStatus.COMMITTED and req.owner:
                        v = self.vehicles[req.owner]
                        v.plan = [s for s in v.plan if s.request_id != req.request_id]
                        if req.request_id in v.committed:
                            v.committed.remove(req.request_id)
                        self.registry.release(req.request_id, req.owner)
                    if req.status != RequestStatus.COMPLETED:
                        req.status = RequestStatus.EXPIRED if req.status != RequestStatus.REJECTED else req.status

    def reject_request(self, request_id: str) -> None:
        req = self.requests[request_id]
        if req.status == RequestStatus.AVAILABLE:
            req.status = RequestStatus.REJECTED

    def _metrics(self) -> EpisodeMetrics:
        served = [r for r in self.requests.values() if r.status == RequestStatus.COMPLETED]
        on_time = [r for r in served if r.on_time]
        rejected = [r for r in self.requests.values() if r.status == RequestStatus.REJECTED]
        expired = [r for r in self.requests.values() if r.status == RequestStatus.EXPIRED]
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
            total_distance_m=sum(v.total_distance_m for v in self.vehicles.values()),
            total_travel_s=sum(v.total_travel_s for v in self.vehicles.values()),
            total_wait_s=sum(v.total_wait_s for v in self.vehicles.values()),
            energy_consumed_kwh=sum(v.energy_consumed_kwh for v in self.vehicles.values()),
            battery_reserve_violations=sum(v.reserve_violations for v in self.vehicles.values()),
            payload_violations=sum(v.payload_violations for v in self.vehicles.values()),
            n_depot_returns=sum(v.n_depot_returns for v in self.vehicles.values()),
            n_charges=sum(v.n_charges for v in self.vehicles.values()),
            n_messages=self.bus.n_sent,
            mean_message_delay_s=(self.bus.total_delay_s / self.bus.n_sent) if self.bus.n_sent else 0.0,
            mean_decision_runtime_s=(sum(self._decision_runtimes) / len(self._decision_runtimes)) if self._decision_runtimes else 0.0,
            n_decisions=len(self._decision_runtimes),
            energy_changed_dispatch=self.energy_changed_dispatch,
            config={
                "energy_uncertainty_delta": self.config.energy_uncertainty_delta,
                "message_delay_s": self.config.message_delay_s,
                "initial_soc": self.config.initial_soc,
                "n_vehicles": len(self.vehicles),
                "charge_on_return": self.config.charge_on_return,
            },
        )
        m.finalize()
        return m
