"""Conservative route feasibility from projected post-lock state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.types import ProjectedState, Request, Stop, VehicleMode, VehicleState


def apply_depot_charge(
    battery_kwh: float,
    ready_s: float,
    energy: EnergyModel,
    stop: Stop | None = None,
    *,
    target_kwh: float | None = None,
) -> tuple[float, float, float]:
    """Apply a depot charge respecting Stop.target_kwh (Stage 5).

    Returns (battery_after, ready_after, energy_delivered_kwh).
    If neither stop.target_kwh nor target_kwh is set, defaults to full Bmax
    (legacy depot_charge without an explicit target).
    """

    bmax = float(energy.battery_kwh_max)
    bat = float(battery_kwh)
    if target_kwh is not None:
        raw = float(target_kwh)
    elif stop is not None and stop.target_kwh is not None:
        raw = float(stop.target_kwh)
    else:
        raw = bmax
    target = min(bmax, max(bat, raw))
    need = max(0.0, target - bat)
    dur = energy.charge_time_s(need)
    return target, float(ready_s) + dur, need


@dataclass
class FeasibilityCheck:
    feasible: bool
    reason: str = ""
    # Backward-compatible ranking field: prefer marginal_travel_s when set for insertions
    added_travel_s: float = 0.0
    total_travel_s: float = 0.0
    marginal_travel_s: float = 0.0
    total_energy_kwh: float = 0.0
    marginal_energy_kwh: float = 0.0
    final_battery_kwh: float = 0.0
    energy_binding: bool = False
    # Residual flexibility after a feasible conservative plan (depot return included)
    energy_flex_kwh: float = 0.0
    min_deadline_slack_s: float = 0.0
    insert_position: int | None = None
    baseline_total_travel_s: float = 0.0
    baseline_energy_flex_kwh: float = 0.0
    baseline_min_deadline_slack_s: float = 0.0


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
    if vehicle.plan and vehicle.moving_to is not None:
        rest = list(vehicle.plan)
        if rest and rest[0].request_id == vehicle.moving_to.request_id and rest[0].kind == vehicle.moving_to.kind:
            return rest[1:]
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
    """Planning origin after finishing the currently locked activity.

    Mode-specific (Stage 5.1):
    - IDLE / not busy: current node/battery/ready.
    - EN_ROUTE: unfinished leg only — deduct remaining conservative travel energy.
    - SERVING: already at customer; travel energy already consumed — do NOT re-deduct
      path_length_m; project remaining service; add payload once.
    - CHARGING: already at depot; travel already consumed — project remaining charge
      to Stop.target_kwh without replaying the depot journey.
    """

    if vehicle.mode == VehicleMode.EMERGENCY_STRANDED:
        return ProjectedState(
            node=vehicle.node,
            ready_s=max(vehicle.ready_s, now_s),
            battery_kwh=vehicle.battery_kwh,
            load_kg=vehicle.load_kg,
            locked_request_ids=(),
        )

    if vehicle.mode == VehicleMode.IDLE or not vehicle.busy or vehicle.moving_to is None:
        ready = max(float(vehicle.ready_s), float(now_s))
        return ProjectedState(
            node=vehicle.node,
            ready_s=ready,
            battery_kwh=vehicle.battery_kwh,
            load_kg=vehicle.load_kg,
            locked_request_ids=(),
        )

    stop = vehicle.moving_to

    # ---- SERVING: arrived; energy already deducted ----
    if vehicle.mode == VehicleMode.SERVING:
        assert stop is not None and stop.request_id is not None
        req = requests[stop.request_id]
        start = float(req.service_start_s) if req.service_start_s is not None else float(vehicle.ready_s)
        ready = max(float(now_s), start + req.service_s)
        return ProjectedState(
            node=int(vehicle.node),
            ready_s=ready,
            battery_kwh=float(vehicle.battery_kwh),
            load_kg=float(vehicle.load_kg) + float(req.weight_kg),
            locked_request_ids=(req.request_id,),
        )

    # ---- CHARGING: at depot; travel already deducted; battery rises at CHARGE_END ----
    if vehicle.mode == VehicleMode.CHARGING:
        bat0 = float(vehicle.battery_kwh)
        charge_start = float(vehicle.ready_s)
        if stop is not None and stop.target_kwh is not None:
            target = float(stop.target_kwh)
        else:
            target = float(energy.battery_kwh_max)
        target = min(float(energy.battery_kwh_max), max(bat0, target))
        need = max(0.0, target - bat0)
        full_dur = energy.charge_time_s(need)
        ready = max(float(now_s), charge_start + full_dur)
        return ProjectedState(
            node=int(depot_node),
            ready_s=ready,
            battery_kwh=target,
            load_kg=0.0,
            locked_request_ids=(),
        )

    # ---- EN_ROUTE: unfinished travel ----
    if vehicle.path_length_m > 0:
        e_remain = energy.conservative_kwh(vehicle.path_length_m)
    else:
        e_remain = float(vehicle.en_route_conservative_kwh or 0.0)
    bat = float(vehicle.battery_kwh) - e_remain
    load = float(vehicle.load_kg)
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
        bat, ready, _ = apply_depot_charge(bat, ready, energy, stop)
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
        node = origin.node
        t = origin.ready_s if now_s is None else max(origin.ready_s, now_s)
        bat0 = origin.battery_kwh
        bat = origin.battery_kwh
        load = origin.load_kg
    else:
        node = origin.node
        t = origin.ready_s
        bat0 = origin.battery_kwh
        bat = origin.battery_kwh
        load = origin.load_kg

    travel = 0.0
    energy_binding = False
    min_slack = float("inf")

    for stop in plan:
        if stop.kind == "pickup":
            assert stop.request_id is not None
            req = requests[stop.request_id]
            if req.status.value in {"completed", "expired", "rejected", "in_service", "missed"}:
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
                bat, t, _ = apply_depot_charge(bat, t, energy, stop)
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
    e_used = max(0.0, bat0 - bat)
    return FeasibilityCheck(
        True,
        "",
        added_travel_s=travel,  # legacy: total for bare simulate; evaluate_insertion overwrites
        total_travel_s=travel,
        marginal_travel_s=0.0,
        total_energy_kwh=e_used,
        marginal_energy_kwh=0.0,
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
        return FeasibilityCheck(
            True,
            "",
            added_travel_s=rt.duration_s,
            total_travel_s=rt.duration_s,
            marginal_travel_s=rt.duration_s,
            final_battery_kwh=bat,
        )
    if require_reserve_at_depot_after:
        try:
            to_dep = router.route(target_node, depot_node, arr)
        except Exception as exc:  # noqa: BLE001
            return FeasibilityCheck(False, f"no_depot_path:{exc}")
        e_dep = energy.conservative_kwh(to_dep.length_m)
        if bat - e_dep < energy.reserve_kwh - 1e-9:
            return FeasibilityCheck(False, "energy_to_depot_after_leg", energy_binding=True)
    return FeasibilityCheck(
        True,
        "",
        added_travel_s=rt.duration_s,
        total_travel_s=rt.duration_s,
        marginal_travel_s=rt.duration_s,
        final_battery_kwh=bat,
    )


def evaluate_insertion(
    vehicle: VehicleState,
    request: Request,
    requests: dict[str, Request],
    router: RouteCache,
    energy: EnergyModel,
    depot_node: int,
    payload_max: float,
    shift_end_s: float,
    now_s: float,
    *,
    score_key: Callable[[FeasibilityCheck], float] | None = None,
) -> list[FeasibilityCheck]:
    """All feasible insertion positions with explicit total and marginal metrics.

    If ``score_key`` is provided, the list is sorted ascending by that key.
    """

    proj = projected_state_after_lock(vehicle, requests, router, energy, depot_node, now_s)
    suffix = editable_suffix(vehicle)
    pickups = [s for s in suffix if s.kind == "pickup"]
    baseline = simulate_plan_conservative(
        proj, pickups, requests, router, energy, depot_node, payload_max, shift_end_s
    )
    base_travel = float(baseline.total_travel_s) if baseline.feasible else 0.0
    base_energy = float(baseline.total_energy_kwh) if baseline.feasible else 0.0
    base_flex = float(baseline.energy_flex_kwh) if baseline.feasible else 0.0
    base_slack = float(baseline.min_deadline_slack_s) if baseline.feasible else 0.0

    candidates: list[FeasibilityCheck] = []
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
        if not chk.feasible:
            continue
        marg_t = chk.total_travel_s - base_travel
        marg_e = chk.total_energy_kwh - base_energy
        chk.marginal_travel_s = marg_t
        chk.marginal_energy_kwh = marg_e
        chk.added_travel_s = marg_t  # Stage 3C: ranking uses marginal, not total
        chk.insert_position = pos
        chk.baseline_total_travel_s = base_travel
        chk.baseline_energy_flex_kwh = base_flex
        chk.baseline_min_deadline_slack_s = base_slack
        chk.reason = f"insert_at_{pos}"
        candidates.append(chk)

    if score_key is not None:
        candidates.sort(key=score_key)
    return candidates


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
    """Best feasible insert by marginal travel cost."""

    cands = evaluate_insertion(
        vehicle,
        request,
        requests,
        router,
        energy,
        depot_node,
        payload_max,
        shift_end_s,
        now_s,
        score_key=lambda c: c.marginal_travel_s,
    )
    if not cands:
        return FeasibilityCheck(False, "no_feasible_insertion")
    return cands[0]
