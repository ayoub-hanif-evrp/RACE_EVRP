"""Resource-constrained charging DP for a fixed pickup sequence.

Exact for continuous time + discrete charge targets {0.50, 0.70, 1.00}
with at most one depot charge inserted before the route and between
consecutive pickups (optional trailing unload/charge after last pickup).

Not a global EVRP optimum — fixed route order only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.feasibility_check import apply_depot_charge
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.types import ProjectedState, Request, Stop

# Keep local to avoid circular import via policies/__init__.py
DISCRETE_TARGET_SOCS: tuple[float, ...] = (0.50, 0.70, 1.00)


@dataclass
class ChargeScheduleResult:
    feasible: bool
    reason: str = ""
    plan: list[Stop] = field(default_factory=list)
    n_served: int = 0
    total_travel_s: float = 0.0
    energy_delivered_kwh: float = 0.0
    charge_duration_s: float = 0.0
    final_battery_kwh: float = 0.0
    # Lex helpers
    score: tuple = ()  # (-n_served, travel, delivered) for min-heap style ranking


@dataclass
class _Label:
    pos: int  # next pickup index to serve
    t: float
    bat: float
    load: float
    node: int
    travel: float
    delivered: float
    charge_s: float
    plan: list[Stop]
    served: int


def optimize_charge_schedule(
    origin: ProjectedState,
    pickup_ids: list[str],
    requests: dict[str, Request],
    router: RouteCache,
    energy: EnergyModel,
    depot_node: int,
    payload_max: float,
    shift_end_s: float,
    *,
    allow_leading_charge: bool = True,
    allow_between_charge: bool = True,
    allow_trailing_charge: bool = True,
    fixed_target_soc: float | None = None,
) -> ChargeScheduleResult:
    """Find a feasible charge-augmented plan for a fixed pickup order.

    If ``fixed_target_soc`` is set, only that target (plus noop) is considered.
    """

    if fixed_target_soc is not None:
        targets = (float(fixed_target_soc),)
    else:
        targets = tuple(DISCRETE_TARGET_SOCS)

    n = len(pickup_ids)
    best: ChargeScheduleResult | None = None

    def consider(lab: _Label) -> None:
        nonlocal best
        t, bat, node, travel = lab.t, lab.bat, lab.node, lab.travel
        delivered, charge_s = lab.delivered, lab.charge_s
        plan = list(lab.plan)
        if node != depot_node:
            try:
                rt = router.route(node, depot_node, t)
            except Exception:  # noqa: BLE001
                return
            e_cons = energy.conservative_kwh(rt.length_m)
            if bat - e_cons < energy.reserve_kwh - 1e-9:
                return
            bat -= e_cons
            travel += rt.duration_s
        res = ChargeScheduleResult(
            feasible=True,
            plan=plan,
            n_served=lab.served,
            total_travel_s=travel,
            energy_delivered_kwh=delivered,
            charge_duration_s=charge_s,
            final_battery_kwh=bat,
            score=(-lab.served, travel, delivered),
        )
        if best is None or res.score < best.score:
            best = res

    # BFS/DFS over charge choices at each position
    stack: list[_Label] = [
        _Label(0, origin.ready_s, origin.battery_kwh, origin.load_kg, origin.node, 0.0, 0.0, 0.0, [], 0)
    ]

    # Leading charge options from depot
    if allow_leading_charge and n >= 0:
        base = stack[0]
        for soc in targets:
            lab = _try_charge_at_depot(base, soc, energy, router, depot_node)
            if lab is not None:
                stack.append(lab)

    seen: set[tuple] = set()
    while stack:
        lab = stack.pop()
        key = (lab.pos, round(lab.t, 3), round(lab.bat, 4), lab.node, lab.served, len(lab.plan))
        if key in seen:
            continue
        seen.add(key)

        if lab.pos >= n:
            consider(lab)
            if allow_trailing_charge:
                for soc in targets:
                    charged = _try_charge_at_depot(lab, soc, energy, router, depot_node)
                    if charged is not None:
                        consider(charged)
            continue

        rid = pickup_ids[lab.pos]
        req = requests[rid]
        # Option A: serve next without charging first
        nxt = _try_serve(lab, req, router, energy, depot_node, payload_max, shift_end_s)
        if nxt is not None:
            stack.append(nxt)
            # Option B: after serving, optional between-charge before next
            if allow_between_charge and nxt.pos < n:
                for soc in targets:
                    charged = _try_charge_at_depot(nxt, soc, energy, router, depot_node)
                    if charged is not None:
                        stack.append(charged)

        # Option C: charge first (if not already just charged as leading), then serve
        if allow_between_charge or (allow_leading_charge and lab.pos == 0):
            for soc in targets:
                charged = _try_charge_at_depot(lab, soc, energy, router, depot_node)
                if charged is None:
                    continue
                nxt2 = _try_serve(charged, req, router, energy, depot_node, payload_max, shift_end_s)
                if nxt2 is not None:
                    stack.append(nxt2)

    if best is None:
        return ChargeScheduleResult(False, "no_feasible_charge_schedule")
    return best


def _try_charge_at_depot(
    lab: _Label,
    target_soc: float,
    energy: EnergyModel,
    router: RouteCache,
    depot_node: int,
) -> _Label | None:
    t, bat, node, travel = lab.t, lab.bat, lab.node, lab.travel
    delivered, charge_s = lab.delivered, lab.charge_s
    plan = list(lab.plan)
    load = 0.0 if node == depot_node else lab.load
    if node != depot_node:
        try:
            rt = router.route(node, depot_node, t)
        except Exception:  # noqa: BLE001
            return None
        e_cons = energy.conservative_kwh(rt.length_m)
        if bat - e_cons < energy.reserve_kwh - 1e-9:
            return None
        bat -= e_cons
        travel += rt.duration_s
        t = rt.arrival_s
        node = depot_node
        load = 0.0
        plan.append(Stop("depot_unload", None, depot_node))
    target_kwh = target_soc * energy.battery_kwh_max
    if bat >= target_kwh - 1e-9:
        return None  # noop
    stop = Stop("depot_charge", None, depot_node, target_kwh=target_kwh)
    # Replace trailing unload with charge if we just added unload
    if plan and plan[-1].kind == "depot_unload":
        plan[-1] = stop
    else:
        plan.append(stop)
    bat, t, need = apply_depot_charge(bat, t, energy, stop)
    delivered += need
    charge_s += energy.charge_time_s(need)
    return _Label(lab.pos, t, bat, load, node, travel, delivered, charge_s, plan, lab.served)


def _try_serve(
    lab: _Label,
    req: Request,
    router: RouteCache,
    energy: EnergyModel,
    depot_node: int,
    payload_max: float,
    shift_end_s: float,
) -> _Label | None:
    if lab.load + req.weight_kg > payload_max + 1e-9:
        return None
    try:
        rt = router.route(lab.node, req.snap_node, lab.t)
    except Exception:  # noqa: BLE001
        return None
    e_cons = energy.conservative_kwh(rt.length_m)
    if lab.bat - e_cons < -1e-9:
        return None
    bat = lab.bat - e_cons
    start = max(rt.arrival_s, req.tw_start_s)
    finish = start + req.service_s
    if finish > req.tw_end_s + 1e-9 or finish > shift_end_s + 1e-9:
        return None
    # Must be able to return to depot above reserve after service
    try:
        to_dep = router.route(req.snap_node, depot_node, finish)
    except Exception:  # noqa: BLE001
        return None
    e_dep = energy.conservative_kwh(to_dep.length_m)
    if bat - e_dep < energy.reserve_kwh - 1e-9:
        return None
    plan = list(lab.plan) + [Stop("pickup", req.request_id, req.snap_node)]
    return _Label(
        lab.pos + 1,
        finish,
        bat,
        lab.load + req.weight_kg,
        req.snap_node,
        lab.travel + rt.duration_s,
        lab.delivered,
        lab.charge_s,
        plan,
        lab.served + 1,
    )
