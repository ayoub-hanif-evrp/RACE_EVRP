"""Conservative route feasibility for planning (not clairvoyant)."""

from __future__ import annotations

from dataclasses import dataclass

from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.types import Request, Stop, VehicleState


@dataclass
class FeasibilityCheck:
    feasible: bool
    reason: str = ""
    added_travel_s: float = 0.0
    final_battery_kwh: float = 0.0
    energy_binding: bool = False


def simulate_plan_conservative(
    vehicle: VehicleState,
    plan: list[Stop],
    requests: dict[str, Request],
    router: RouteCache,
    energy: EnergyModel,
    depot_node: int,
    payload_max: float,
    shift_end_s: float,
    *,
    require_depot_return: bool = True,
) -> FeasibilityCheck:
    """Roll forward a planned stop sequence under conservative energy.

    Uses current vehicle node/ready/battery/load. Does not mutate state.
    """

    node = vehicle.node
    # Planning uses the vehicle's ready time; callers should sync ready_s to now
    # for idle vehicles before invoking this checker when evaluating online inserts.
    t = vehicle.ready_s
    bat = vehicle.battery_kwh
    load = vehicle.load_kg
    travel = 0.0
    energy_binding = False

    for stop in plan:
        if stop.kind == "pickup":
            assert stop.request_id is not None
            req = requests[stop.request_id]
            if req.status.value in {"completed", "expired", "rejected", "in_service"}:
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
            # Check depot reachability after this leg with remaining plan prefix...
            bat -= e_cons
            t = max(rt.arrival_s, req.tw_start_s)
            if t + req.service_s > req.tw_end_s + 1e-9:
                return FeasibilityCheck(False, "time_window")
            if t + req.service_s > shift_end_s + 1e-9:
                return FeasibilityCheck(False, "shift_end")
            t = t + req.service_s
            load += req.weight_kg
            travel += rt.duration_s
            node = req.snap_node
            # Must still be able to reach depot from here under conservative energy
            try:
                to_dep = router.route(node, depot_node, t)
            except Exception as exc:  # noqa: BLE001
                return FeasibilityCheck(False, f"no_depot_path:{exc}")
            e_dep = energy.conservative_kwh(to_dep.length_m)
            if bat - e_dep < energy.reserve_kwh - 1e-9:
                energy_binding = True
                return FeasibilityCheck(False, "energy_to_depot", energy_binding=True)
        elif stop.kind in {"depot_unload", "depot_charge"}:
            try:
                rt = router.route(node, depot_node, t)
            except Exception as exc:  # noqa: BLE001
                return FeasibilityCheck(False, f"no_path_depot:{exc}")
            e_cons = energy.conservative_kwh(rt.length_m)
            if bat - e_cons < energy.reserve_kwh - 1e-9 and bat - e_cons < -1e-9:
                return FeasibilityCheck(False, "energy_to_depot", energy_binding=True)
            if bat - e_cons < energy.reserve_kwh - 1e-9:
                energy_binding = True
                # Still allow arrival if nonnegative; reserve checked as soft for planning reject
                if bat - e_cons < -1e-9:
                    return FeasibilityCheck(False, "energy_to_depot", energy_binding=True)
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

    return FeasibilityCheck(True, "", added_travel_s=travel, final_battery_kwh=bat, energy_binding=energy_binding)


def insertion_cost(
    vehicle: VehicleState,
    request: Request,
    requests: dict[str, Request],
    router: RouteCache,
    energy: EnergyModel,
    depot_node: int,
    payload_max: float,
    shift_end_s: float,
) -> FeasibilityCheck:
    """Cheapest append-or-insert among positions in current pickup plan."""

    base_pickups = [s for s in vehicle.plan if s.kind == "pickup"]
    best: FeasibilityCheck | None = None
    for pos in range(len(base_pickups) + 1):
        new_plan = list(base_pickups)
        new_plan.insert(pos, Stop(kind="pickup", request_id=request.request_id, node=request.snap_node))
        # Always append implicit feasibility via simulate (require depot return)
        chk = simulate_plan_conservative(
            vehicle,
            new_plan,
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
