"""Cross-check charge_label_dp against charge_commit_enum on identical toys.

Claim A only: fixed pickup order + discrete charge alphabet.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Any

from race_casablanca.exact.charge_commit_enum import (
    DISCRETE_TARGETS,
    ChargeCommitInstance,
    _simulate_plan,
    instance_a_early_charge,
    instance_b_serve_before_charge,
    instance_c_partial_better,
    instance_d_charge_enables_later,
)
from race_casablanca.optimization.charge_label_dp import optimize_charge_schedule
from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.types import ProjectedState, Request, RequestStatus, Stop


@dataclass
class _ToyRoute:
    length_m: float
    duration_s: float
    arrival_s: float
    wait_s: float = 0.0
    path: list = None  # type: ignore

    def __post_init__(self):
        if self.path is None:
            self.path = []


class _ToyRouter:
    def __init__(self, inst: ChargeCommitInstance):
        self.inst = inst

    def route(self, o: int, d: int, depart_s: float) -> _ToyRoute:
        ts = float(self.inst.travel_s[(o, d)])
        ek = float(self.inst.travel_kwh[(o, d)])
        # Encode energy via length so EnergyModel.conservative matches ek at 1 kWh/km
        length_m = ek * 1000.0
        return _ToyRoute(length_m=length_m, duration_s=ts, arrival_s=depart_s + ts, path=[o, d])


def _energy_for(inst: ChargeCommitInstance) -> EnergyModel:
    return EnergyModel(
        consumption_kwh_per_km=1.0,
        uncertainty_delta=0.0,
        battery_kwh_max=inst.bmax,
        reserve_soc=inst.reserve_kwh / inst.bmax if inst.bmax > 0 else 0.15,
        charge_power_kw=inst.charge_kw,
    )


def _requests_for(inst: ChargeCommitInstance) -> dict[str, Request]:
    out = {}
    for r in inst.requests:
        out[r.rid] = Request(
            request_id=r.rid,
            snap_node=r.node,
            release_s=r.release_s,
            tw_start_s=r.tw_start,
            tw_end_s=r.tw_end,
            service_s=r.service_s,
            weight_kg=1.0,
            status=RequestStatus.AVAILABLE,
        )
    return out


def best_enum_for_order(inst: ChargeCommitInstance, order: tuple[str, ...]) -> tuple[int, float]:
    """Best on-time / travel among charge insertions for a fixed order (enum model)."""
    opts: list[float | None] = [None, *DISCRETE_TARGETS]
    best_ot = -1
    best_travel = float("inf")

    def rec(i: int, prefix: list[tuple]) -> None:
        nonlocal best_ot, best_travel
        if i == len(order):
            ot, travel, ok, _ = _simulate_plan(inst, prefix)
            if ok and (ot > best_ot or (ot == best_ot and travel < best_travel)):
                best_ot = ot
                best_travel = travel
            return
        for c in opts:
            p2 = list(prefix)
            if c is not None:
                p2.append(("charge", c))
            p2.append(("serve", order[i]))
            rec(i + 1, p2)

    if not order:
        return 0, 0.0
    rec(0, [])
    if best_ot < 0:
        return 0, float("inf")
    return best_ot, best_travel


def dp_for_order(inst: ChargeCommitInstance, order: tuple[str, ...]) -> tuple[int, float, bool]:
    energy = _energy_for(inst)
    router = _ToyRouter(inst)
    reqs = _requests_for(inst)
    origin = ProjectedState(
        node=inst.depot,
        ready_s=0.0,
        battery_kwh=inst.initial_soc * inst.bmax,
        load_kg=0.0,
    )
    res = optimize_charge_schedule(
        origin,
        list(order),
        reqs,
        router,  # type: ignore[arg-type]
        energy,
        inst.depot,
        payload_max=1e9,
        shift_end_s=inst.shift_end,
    )
    if not res.feasible:
        return 0, float("inf"), False
    return res.n_served, res.total_travel_s, True


def crosscheck_instance(inst: ChargeCommitInstance) -> dict[str, Any]:
    """Compare enum vs DP on every nonempty order (claim A)."""
    rids = [r.rid for r in inst.requests]
    mismatches = []
    n = 0
    for k in range(1, len(rids) + 1):
        for order in permutations(rids, k):
            n += 1
            e_ot, e_tr = best_enum_for_order(inst, order)
            d_ot, d_tr, d_ok = dp_for_order(inst, order)
            # Claim A: fixed sequence must serve ALL stops in order.
            # Enum can "miss" mid-sequence and still count earlier serves; DP requires
            # the full sequence. Only compare when enum can serve the entire order.
            if e_ot == len(order):
                if not d_ok or d_ot != e_ot:
                    mismatches.append(
                        {
                            "order": order,
                            "enum_ot": e_ot,
                            "dp_ot": d_ot,
                            "enum_tr": e_tr,
                            "dp_tr": d_tr,
                            "note": "full_order_must_match",
                        }
                    )
            elif e_ot == 0 and d_ok and d_ot > 0:
                mismatches.append(
                    {
                        "order": order,
                        "enum_ot": e_ot,
                        "dp_ot": d_ot,
                        "note": "dp_served_when_enum_zero",
                    }
                )
    return {
        "instance": inst.name,
        "n_orders": n,
        "n_mismatches": len(mismatches),
        "mismatches": mismatches[:10],
        "ok": len(mismatches) == 0,
    }


def run_canned_crosscheck() -> list[dict]:
    return [
        crosscheck_instance(instance_a_early_charge()),
        crosscheck_instance(instance_b_serve_before_charge()),
        crosscheck_instance(instance_c_partial_better()),
        crosscheck_instance(instance_d_charge_enables_later()),
    ]
