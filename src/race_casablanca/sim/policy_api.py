"""Immutable observation / controlled action boundary for policies.

Restricted policies must not receive a mutable simulator or peer true states.
Policy-visible vehicle state excludes hidden future energy realizations.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from race_casablanca.sim.feasibility_check import FeasibilityCheck
from race_casablanca.sim.types import Request, RequestStatus, VehicleMode, VehicleState

if TYPE_CHECKING:
    from race_casablanca.sim.environment import OnlineSimulator


@dataclass(frozen=True)
class TaskAnnouncement:
    request_id: str
    snap_node: int
    tw_start_s: float
    tw_end_s: float
    service_s: float
    weight_kg: float


@dataclass(frozen=True)
class PeerSnapshot:
    vehicle_id: str
    node: int | None
    ready_s: float | None
    battery_kwh: float | None
    load_kg: float | None
    committed: tuple[str, ...]
    as_of_s: float


@dataclass(frozen=True)
class VisibleVehicleState:
    """Policy-visible vehicle fields — no hidden en-route realized energy."""

    vehicle_id: str
    node: int
    ready_s: float
    battery_kwh: float
    load_kg: float
    busy: bool
    mode: str
    committed: tuple[str, ...]
    plan_pickup_ids: tuple[str, ...]
    locked_request_id: str | None
    path_length_m: float  # known geometry of active leg; not realized energy


def to_visible(v: VehicleState) -> VisibleVehicleState:
    locked = None
    if v.moving_to and v.moving_to.kind == "pickup":
        locked = v.moving_to.request_id
    pickups = tuple(s.request_id for s in v.plan if s.kind == "pickup" and s.request_id)
    return VisibleVehicleState(
        vehicle_id=v.vehicle_id,
        node=v.node,
        ready_s=v.ready_s,
        battery_kwh=v.battery_kwh,
        load_kg=v.load_kg,
        busy=v.busy,
        mode=v.mode.value if isinstance(v.mode, VehicleMode) else str(v.mode),
        committed=tuple(v.committed),
        plan_pickup_ids=pickups,
        locked_request_id=locked,
        path_length_m=float(v.path_length_m) if v.busy else 0.0,
    )


@dataclass
class FullInfoObservation:
    now_s: float
    available: list[TaskAnnouncement]
    vehicles: dict[str, VisibleVehicleState]
    released_requests: dict[str, Request]
    info_mode: str = "full"


@dataclass
class RestrictedObservation:
    now_s: float
    vehicle_id: str
    self_state: VisibleVehicleState
    own_committed: tuple[str, ...]
    announced: list[TaskAnnouncement]
    peers: dict[str, PeerSnapshot]
    inbox: list[Any] = field(default_factory=list)
    info_mode: str = "restricted"


class ActionInterface:
    """Controlled actions; does not expose peer true states."""

    def __init__(self, sim: "OnlineSimulator", actor_vehicle_id: str | None = None):
        self._sim = sim
        self.actor_vehicle_id = actor_vehicle_id

    def list_announced_tasks(self) -> list[TaskAnnouncement]:
        out = []
        for r in self._sim.available_requests():
            out.append(
                TaskAnnouncement(
                    r.request_id, r.snap_node, r.tw_start_s, r.tw_end_s, r.service_s, r.weight_kg
                )
            )
        return out

    def check_insertion(self, vehicle_id: str, request_id: str) -> FeasibilityCheck:
        if self._sim.config.info_mode == "restricted":
            if self.actor_vehicle_id is None or vehicle_id != self.actor_vehicle_id:
                raise PermissionError("restricted policy may only check insertion for self")
        return self._sim.check_insertion(vehicle_id, request_id)

    def claim_task(
        self, vehicle_id: str, request_id: str, *, force_position: int | None = None
    ) -> bool:
        if self._sim.config.info_mode == "restricted":
            if self.actor_vehicle_id is None or vehicle_id != self.actor_vehicle_id:
                raise PermissionError("restricted policy may only claim for self")
        # Single source of truth: simulator counters only
        return self._sim.try_assign(vehicle_id, request_id, force_position=force_position)

    def reject_request(self, request_id: str) -> None:
        self._sim.reject_request(request_id)

    def broadcast_own_state(self, vehicle_id: str) -> None:
        if self._sim.config.info_mode == "restricted":
            if self.actor_vehicle_id is None or vehicle_id != self.actor_vehicle_id:
                raise PermissionError("restricted policy may only broadcast self")
        self._sim.broadcast_state(vehicle_id)

    def request_return_depot(
        self,
        vehicle_id: str,
        *,
        charge: bool | None = None,
        target_soc: float | None = None,
    ) -> None:
        if self._sim.config.info_mode == "restricted":
            if self.actor_vehicle_id is None or vehicle_id != self.actor_vehicle_id:
                raise PermissionError("restricted policy may only return self")
        self._sim.request_return_depot(vehicle_id, charge=charge, target_soc=target_soc)


class Policy(Protocol):
    name: str

    def on_decision(
        self, obs: FullInfoObservation | RestrictedObservation, actions: ActionInterface, reason: str
    ) -> None: ...


def build_full_observation(sim: "OnlineSimulator") -> FullInfoObservation:
    available = [
        TaskAnnouncement(r.request_id, r.snap_node, r.tw_start_s, r.tw_end_s, r.service_s, r.weight_kg)
        for r in sim.available_requests()
    ]
    released = {
        rid: copy.deepcopy(r)
        for rid, r in sim.requests.items()
        if r.status != RequestStatus.UNRELEASED
    }
    return FullInfoObservation(
        now_s=sim.now_s,
        available=available,
        vehicles={k: to_visible(v) for k, v in sim.vehicles.items()},
        released_requests=released,
    )


def build_restricted_observation(sim: "OnlineSimulator", vehicle_id: str) -> RestrictedObservation:
    v = sim.vehicles[vehicle_id]
    inbox = sim.bus.pop_inbox(vehicle_id)
    peers: dict[str, PeerSnapshot] = {}
    for peer_id, snap in sim.local_views.get(vehicle_id, {}).items():
        peers[peer_id] = PeerSnapshot(
            vehicle_id=peer_id,
            node=snap.get("node"),
            ready_s=snap.get("ready_s"),
            battery_kwh=snap.get("battery_kwh"),
            load_kg=snap.get("load_kg"),
            committed=tuple(snap.get("committed") or ()),
            as_of_s=float(snap.get("as_of_s", sim.now_s)),
        )
    announced = [
        TaskAnnouncement(r.request_id, r.snap_node, r.tw_start_s, r.tw_end_s, r.service_s, r.weight_kg)
        for r in sim.available_requests()
    ]
    return RestrictedObservation(
        now_s=sim.now_s,
        vehicle_id=vehicle_id,
        self_state=to_visible(v),
        own_committed=tuple(v.committed),
        announced=announced,
        peers=peers,
        inbox=inbox,
    )
