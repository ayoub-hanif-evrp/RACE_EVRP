"""Shared types for the online simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


class RequestStatus(str, Enum):
    UNRELEASED = "unreleased"
    AVAILABLE = "available"
    COMMITTED = "committed"
    IN_SERVICE = "in_service"
    COMPLETED = "completed"
    EXPIRED = "expired"
    REJECTED = "rejected"


class EventType(str, Enum):
    REQUEST_RELEASE = "request_release"
    VEHICLE_ARRIVAL = "vehicle_arrival"
    SERVICE_END = "service_end"
    CHARGE_END = "charge_end"
    MESSAGE_DELIVER = "message_deliver"
    DECISION_EPOCH = "decision_epoch"
    SHIFT_END = "shift_end"
    EPISODE_END = "episode_end"


class EventPriority(IntEnum):
    """Lower value = higher priority at equal time (causality)."""

    MESSAGE_DELIVER = 0
    REQUEST_RELEASE = 1
    VEHICLE_ARRIVAL = 2
    SERVICE_END = 3
    CHARGE_END = 4
    DECISION_EPOCH = 5
    SHIFT_END = 6
    EPISODE_END = 7


@dataclass(order=True)
class Event:
    time_s: float
    priority: int
    seq: int
    type: EventType = field(compare=False)
    payload: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass
class Request:
    request_id: str
    snap_node: int
    release_s: float
    tw_start_s: float
    tw_end_s: float
    service_s: float
    weight_kg: float
    status: RequestStatus = RequestStatus.UNRELEASED
    owner: str | None = None
    service_start_s: float | None = None
    service_end_s: float | None = None
    on_time: bool | None = None


@dataclass
class Stop:
    kind: str  # pickup | depot_unload | depot_charge
    request_id: str | None = None
    node: int | None = None


@dataclass
class VehicleState:
    vehicle_id: str
    node: int
    ready_s: float
    battery_kwh: float
    load_kg: float
    busy: bool = False
    plan: list[Stop] = field(default_factory=list)
    committed: list[str] = field(default_factory=list)
    moving_to: Stop | None = None
    path_nodes: list[int] = field(default_factory=list)
    path_length_m: float = 0.0
    departed_s: float | None = None
    en_route_energy_kwh: float = 0.0
    total_distance_m: float = 0.0
    total_travel_s: float = 0.0
    total_wait_s: float = 0.0
    energy_consumed_kwh: float = 0.0
    n_depot_returns: int = 0
    n_charges: int = 0
    reserve_violations: int = 0
    payload_violations: int = 0
