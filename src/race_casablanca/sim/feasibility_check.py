"""Conservative route feasibility from projected post-lock state."""

from __future__ import annotations

from dataclasses import dataclass

from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.types import ProjectedState, Request, Stop, VehicleMode, VehicleState


@dataclass
class FeasibilityCheck:
    feasible: bool
    reason: str = ""
    added_travel_s: float = 0.0
    final_battery_kwh: float = 0.0
    energy_binding: bool = False
    # Residual flexibility after a feasible conservative plan (depot return included)
    energy_flex_kwh: float = 0.0
    min_deadline_slack_s: float = 0.0


def locked_prefix(vehicle: VehicleState) -> list[Stop]:
    """Stops that cannot be edited: active movement / service target."""

    if vehicle.moving_to is not None:
        return [vehicle.moving_to]
    return []


def editable_suffix(vehicle: VehicleState) -> list[Stop]:
    """Future stops after the locked active stop."""

    locked = locked_prefix(vehicle)
    if not locked:
        return list(vehicle.plan)
    # plan[0] should be the locked stop while busy; keep remaining
    if vehicle.plan and vehicle.moving_to is not None:
        # Drop any occurrence of the locked stop from the front if present
        rest = list(vehicle.plan)
        if rest and rest[0].request_id == vehicle.moving_to.request_id and rest[0].kind == vehicle.moving_to.kind:
            return rest[1:]
        # If plan was reordered incorrectly, filter locked id from editable part
        locked_id = vehicle.moving_to.request_id
        return [s for s in rest if not (s.kind == "pickup" and s.request_id == locked_id)]
    return list(vehicle.plan)


def projected_state_after_lock(
    vehicle: VehicleState,
    requests: dict[str, Request],
    router: RouteCache,
    energy: EnergyModel,
    depot_node: int,
    now_s: float,
) -> ProjectedState:
    """Planning origin after finishing the currently locked leg/service.

    Hidden realized en-route energy must NOT enter planning. For an unfinished
    leg, remaining consumption uses the conservative bound on the known path
    length (or re-routed length). Arrival timing uses deterministic TTI routing.
    """

    if vehicle.mode == VehicleMode.EMERGENCY_STRANDED:
        return ProjectedState(
            node=vehicle.node,
            ready_s=max(vehicle.ready_s, now_s),
            battery_kwh=vehicle.battery_kwh,
            load_kg=vehicle.load_kg,
            locked_request_ids=(),
        )

    if not vehicle.busy or vehicle.moving_to is None:
        ready = max(float(vehicle.ready_s), float(now_s))
        return ProjectedState(
            node=vehicle.node,
            ready_s=ready,
            battery_kwh=vehicle.battery_kwh,
            load_kg=vehicle.load_kg,
            locked_request_ids=(),
        )

    stop = vehicle.moving_to
    # Conservative remaining energy for unfinished travel (no realized xi leakage).
    if vehicle.path_length_m > 0:
        e_remain = energy.conservative_kwh(vehicle.path_length_m)
    else:
        e_remain = float(vehicle.en_route_conservative_kwh or 0.0)
    bat = vehicle.battery_kwh - e_remain
    load = vehicle.load_kg
    locked_ids: list[str] = []

    if stop.kind == "pickup":
        assert stop.request_id is not None
        req = requests[stop.request_id]
        locked_ids.append(req.request_id)
        if vehicle.departed_s is not None:
            rt = router.route(vehicle.node, req.snap_node, vehicle.departed_s)
            arr = rt.arrival_s
        else:
            rt = router.route(vehicle.node, req.snap_node, max(vehicle.ready_s, now_s))
            arr = rt.arrival_s
        start = max(arr, req.tw_start_s, now_s)
        ready = start + req.service_s
        load = load + req.weight_kg
        node = req.snap_node
        return ProjectedState(node, ready, bat, load, tuple(locked_ids))

    if vehicle.departed_s is not None:
        rt = router.route(vehicle.node, depot_node, vehicle.departed_s)
        arr = rt.arrival_s
    else:
        rt = router.route(vehicle.node, depot_node, max(vehicle.ready_s, now_s))
        arr = rt.arrival_s
    ready = arr
    if stop.kind == "depot_charge":
        need = max(0.0, energy.battery_kwh_max - bat)
        ready += energy.charge_time_s(need)
        bat = energy.battery_kwh_max
    return ProjectedState(depot_node, ready, bat, 0.0, ())


def simulate_plan_conservative(
    origin: ProjectedState | VehicleState,
    plan: list[Stop],
    requests: dict[str, Request],
    router: RouteCache,
    energy: EnergyModel,
    depot_node: int,
    payload_max: float,
    shift_end_s: float,
    *,
    require_depot_return: bool = True,
    now_s: float | None = None,
) -> FeasibilityCheck:
    """Roll forward a planned stop sequence under conservative energy from origin."""

    if isinstance(origin, VehicleState):
        # Idle snapshot only — callers should prefer ProjectedState while busy.
        node = origin.node
        t = origin.ready_s if now_s is None else max(origin.ready_s, now_s)
        bat = origin.battery_kwh
        load = origin.load_kg
    else:
        node = origin.node
        t = origin.ready_s
        bat = origin.battery_kwh
        load = origin.load_kg

    travel = 0.0
    energy_binding = False
    min_slack = float("inf")

    for stop in plan:
        if stop.kind == "pickup":
            assert stop.request_id is not None
            req = requests[stop.request_id]
            if req.status.value in {"completed", "expired", "rejected", "in_service"}:
                # in_service locked stops must not appear in editable suffix
                return FeasibilityCheck(False, f"request_not_assignable:{req.status}")
            if load + req.weight_kg > payload_max + 1e-9:
                return FeasibilityCheck(False, "payload")
            try:
                rt = router.route(node, req.snap_node, t)
            except Exception as exc:  # noqa: BLE001
                return FeasibilityCheck(False, f"no_path:{exc}")
            e_cons = energy.conservative_kwh(rt.length_m)
            if bat - e_cons < -1e-9:
                return FeasibilityCheck(False, "energy_en_route", energy_binding=True)
            bat -= e_cons
            t = max(rt.arrival_s, req.tw_start_s)
            if t + req.service_s > req.tw_end_s + 1e-9:
                return FeasibilityCheck(False, "time_window")
            if t + req.service_s > shift_end_s + 1e-9:
                return FeasibilityCheck(False, "shift_end")
            slack = req.tw_end_s - (t + req.service_s)
            min_slack = min(min_slack, slack)
            t = t + req.service_s
            load += req.weight_kg
            travel += rt.duration_s
            node = req.snap_node
            try:
                to_dep = router.route(node, depot_node, t)
            except Exception as exc:  # noqa: BLE001
                return FeasibilityCheck(False, f"no_depot_path:{exc}")
            e_dep = energy.conservative_kwh(to_dep.length_m)
            if bat - e_dep < energy.reserve_kwh - 1e-9:
                return FeasibilityCheck(False, "energy_to_depot", energy_binding=True)
        elif stop.kind in {"depot_unload", "depot_charge"}:
            try:
                rt = router.route(node, depot_node, t)
            except Exception as exc:  # noqa: BLE001
                return FeasibilityCheck(False, f"no_path_depot:{exc}")
            e_cons = energy.conservative_kwh(rt.length_m)
            if bat - e_cons < energy.reserve_kwh - 1e-9:
                return FeasibilityCheck(False, "energy_reserve_to_depot", energy_binding=True)
            bat -= e_cons
            t = rt.arrival_s
            travel += rt.duration_s
            node = depot_node
            load = 0.0
            if stop.kind == "depot_charge":
                need = energy.battery_kwh_max - bat
                t += energy.charge_time_s(need)
                bat = energy.battery_kwh_max
        else:
            return FeasibilityCheck(False, f"unknown_stop:{stop.kind}")

    if require_depot_return and node != depot_node:
        try:
            rt = router.route(node, depot_node, t)
        except Exception as exc:  # noqa: BLE001
            return FeasibilityCheck(False, f"no_final_depot:{exc}")
        e_cons = energy.conservative_kwh(rt.length_m)
        if bat - e_cons < energy.reserve_kwh - 1e-9:
            return FeasibilityCheck(False, "energy_final_depot", energy_binding=True)
        bat -= e_cons
        travel += rt.duration_s

    energy_flex = max(0.0, bat - energy.reserve_kwh)
    slack_out = 0.0 if min_slack == float("inf") else float(min_slack)
    return FeasibilityCheck(
        True,
        "",
        added_travel_s=travel,
        final_battery_kwh=bat,
        energy_binding=energy_binding,
        energy_flex_kwh=energy_flex,
        min_deadline_slack_s=slack_out,
    )


def check_leg_dispatch(
    node: int,
    ready_s: float,
    battery_kwh: float,
    target_node: int,
    router: RouteCache,
    energy: EnergyModel,
    depot_node: int,
    *,
    require_reserve_at_depot_after: bool = True,
) -> FeasibilityCheck:
    """Pre-departure gate: conservative energy for this leg + depot reserve thereafter."""

    try:
        rt = router.route(node, target_node, ready_s)
    except Exception as exc:  # noqa: BLE001
        return FeasibilityCheck(False, f"no_path:{exc}")
    e_cons = energy.conservative_kwh(rt.length_m)
    if battery_kwh - e_cons < -1e-9:
        return FeasibilityCheck(False, "energy_en_route", energy_binding=True)
    bat = battery_kwh - e_cons
    arr = rt.arrival_s
    if target_node == depot_node:
        if bat < energy.reserve_kwh - 1e-9:
            return FeasibilityCheck(False, "energy_reserve_at_depot", energy_binding=True)
        return FeasibilityCheck(True, "", added_travel_s=rt.duration_s, final_battery_kwh=bat)
    if require_reserve_at_depot_after:
        try:
            to_dep = router.route(target_node, depot_node, arr)
        except Exception as exc:  # noqa: BLE001
            return FeasibilityCheck(False, f"no_depot_path:{exc}")
        e_dep = energy.conservative_kwh(to_dep.length_m)
        if bat - e_dep < energy.reserve_kwh - 1e-9:
            return FeasibilityCheck(False, "energy_to_depot_after_leg", energy_binding=True)
    return FeasibilityCheck(True, "", added_travel_s=rt.duration_s, final_battery_kwh=bat)


def insertion_cost(
    vehicle: VehicleState,
    request: Request,
    requests: dict[str, Request],
    router: RouteCache,
    energy: EnergyModel,
    depot_node: int,
    payload_max: float,
    shift_end_s: float,
    now_s: float,
) -> FeasibilityCheck:
    """Cheapest insert into editable suffix from projected post-lock state."""

    proj = projected_state_after_lock(vehicle, requests, router, energy, depot_node, now_s)
    suffix = editable_suffix(vehicle)
    pickups = [s for s in suffix if s.kind == "pickup"]
    best: FeasibilityCheck | None = None
    for pos in range(len(pickups) + 1):
        new_pickups = list(pickups)
        new_pickups.insert(pos, Stop(kind="pickup", request_id=request.request_id, node=request.snap_node))
        chk = simulate_plan_conservative(
            proj,
            new_pickups,
            requests,
            router,
            energy,
            depot_node,
            payload_max,
            shift_end_s,
            require_depot_return=True,
        )
        if chk.feasible and (best is None or chk.added_travel_s < best.added_travel_s):
            best = chk
            best.reason = f"insert_at_{pos}"
    if best is None:
        return FeasibilityCheck(False, "no_feasible_insertion")
    return best
