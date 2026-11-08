"""Exact enumeration for tiny depot-charge + commitment instances.

Discrete-action model (exact for this alphabet):
  - travel times/energies are deterministic between nodes
  - charge targets in {0.50, 0.70, 1.00} clipped to [soc, 1]
  - hard windows: service finish ≤ tw_end
  - single vehicle, depot charging only
  - actions: serve remaining request r | charge-to-target

State is finite because charge targets are discrete and request sets are tiny
(≤4). Time advances by known route durations + charge durations.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from typing import Any


DISCRETE_TARGETS = (0.50, 0.70, 1.00)


@dataclass
class ToyRequest:
    rid: str
    node: int
    tw_start: float
    tw_end: float
    service_s: float
    release_s: float = 0.0


@dataclass
class ChargeCommitInstance:
    name: str
    description: str
    travel_s: dict[tuple[int, int], float]
    travel_kwh: dict[tuple[int, int], float]
    requests: list[ToyRequest]
    depot: int = 0
    bmax: float = 40.0
    reserve_kwh: float = 6.0
    charge_kw: float = 22.0
    initial_soc: float = 0.35
    shift_end: float = 1e6

    def charge_time(self, delta_kwh: float) -> float:
        if delta_kwh <= 1e-12:
            return 0.0
        return 3600.0 * delta_kwh / self.charge_kw


@dataclass
class EnumResult:
    instance: str
    best_on_time: int
    best_distance_proxy_s: float
    best_plan: list[dict[str, Any]]
    n_enumerated: int
    greedy_on_time: int
    always_full_on_time: int
    notes: str = ""


def _leg(inst: ChargeCommitInstance, u: int, v: int) -> tuple[float, float]:
    if u == v:
        return 0.0, 0.0
    return float(inst.travel_s[(u, v)]), float(inst.travel_kwh[(u, v)])


def _simulate_plan(
    inst: ChargeCommitInstance,
    actions: list[tuple],
) -> tuple[int, float, bool, list[dict]]:
    t = 0.0
    bat = inst.initial_soc * inst.bmax
    loc = inst.depot
    served: set[str] = set()
    travel = 0.0
    log: list[dict] = []
    req_map = {r.rid: r for r in inst.requests}

    for act in actions:
        if act[0] == "charge":
            tgt_soc = float(act[1])
            if loc != inst.depot:
                ts, ek = _leg(inst, loc, inst.depot)
                if bat - ek < inst.reserve_kwh - 1e-9:
                    return len(served), travel, False, log
                bat -= ek
                t += ts
                travel += ts
                loc = inst.depot
                log.append({"op": "return_depot", "t": t, "bat": bat})
            target = min(inst.bmax, max(bat, tgt_soc * inst.bmax))
            need = target - bat
            dur = inst.charge_time(need)
            t += dur
            bat = target
            log.append({"op": "charge", "target_soc": tgt_soc, "t": t, "bat": bat, "dur": dur})
            continue

        rid = act[1]
        if rid in served:
            continue
        req = req_map[rid]
        if t < req.release_s:
            t = req.release_s
        ts, ek = _leg(inst, loc, req.node)
        if bat - ek < inst.reserve_kwh - 1e-9:
            return len(served), travel, False, log
        bat -= ek
        t += ts
        travel += ts
        loc = req.node
        start = max(t, req.tw_start)
        if start + req.service_s > req.tw_end + 1e-9:
            log.append({"op": "miss", "rid": rid, "t": t})
            continue
        t = start + req.service_s
        served.add(rid)
        log.append({"op": "serve", "rid": rid, "t": t, "bat": bat})

    if loc != inst.depot and served:
        ts, ek = _leg(inst, loc, inst.depot)
        if bat - ek < inst.reserve_kwh - 1e-9:
            # Drop last serve conceptually: mark energy-infeasible plan
            return 0, travel, False, log
        travel += ts
        bat -= ek
        loc = inst.depot
    return len(served), travel, True, log


def _action_variants(order: tuple[str, ...]) -> list[list[tuple]]:
    """Generate action sequences: optional charge before/between serves."""
    opts: list[float | None] = [None, *DISCRETE_TARGETS]
    out: list[list[tuple]] = []
    k = len(order)
    # charges[i] = optional charge before serve i; charges[k] unused trailing
    # For k serves there are k+1 charge slots (before each and after last before end)
    if k == 0:
        for c in DISCRETE_TARGETS:
            out.append([("charge", c)])
        out.append([])
        return out

    def rec(i: int, prefix: list[tuple]) -> None:
        if i == k:
            out.append(list(prefix))
            return
        for c in opts:
            p2 = list(prefix)
            if c is not None:
                p2.append(("charge", c))
            p2.append(("serve", order[i]))
            rec(i + 1, p2)

    rec(0, [])
    # Also allow a trailing charge after last serve (doesn't help on-time; skip)
    return out


def enumerate_charge_commit(inst: ChargeCommitInstance) -> EnumResult:
    rids = [r.rid for r in inst.requests]
    best_ot = -1
    best_travel = float("inf")
    best_plan: list[dict] = []
    n = 0

    for k in range(len(rids) + 1):
        for order in permutations(rids, k):
            for actions in _action_variants(order):
                n += 1
                ot, travel, ok, log = _simulate_plan(inst, actions)
                if not ok:
                    continue
                if ot > best_ot or (ot == best_ot and travel < best_travel):
                    best_ot = ot
                    best_travel = travel
                    best_plan = log

    if best_ot < 0:
        best_ot = 0
        best_travel = 0.0

    return EnumResult(
        instance=inst.name,
        best_on_time=best_ot,
        best_distance_proxy_s=best_travel if best_travel < float("inf") else 0.0,
        best_plan=best_plan,
        n_enumerated=n,
        greedy_on_time=_simple_online(inst, mode="adaptive"),
        always_full_on_time=_simple_online(inst, mode="always_full"),
        notes=inst.description,
    )


def _simple_online(inst: ChargeCommitInstance, *, mode: str) -> int:
    """Myopic online baselines on the toy graph.

    always_full: charge to 1.0 at start (and whenever stuck) before serving.
    adaptive: try earliest-deadline serve first; charge to 0.7 only when stuck.
    """
    t = 0.0
    bat = inst.initial_soc * inst.bmax
    loc = inst.depot
    remaining = list(inst.requests)
    served = 0
    charged_once = False

    def go_depot_and_charge(target_soc: float) -> bool:
        nonlocal t, bat, loc
        if loc != inst.depot:
            ts, ek = _leg(inst, loc, inst.depot)
            if bat - ek < inst.reserve_kwh - 1e-9:
                return False
            bat -= ek
            t += ts
            loc = inst.depot
        target = min(inst.bmax, max(bat, target_soc * inst.bmax))
        need = target - bat
        if need <= 1e-12:
            return False
        t += inst.charge_time(need)
        bat = target
        return True

    if mode == "always_full" and bat < inst.bmax - 1e-6:
        go_depot_and_charge(1.0)
        charged_once = True

    for _ in range(30):
        remaining.sort(key=lambda r: r.tw_end)
        progressed = False
        for req in list(remaining):
            if t < req.release_s:
                continue
            ts, ek = _leg(inst, loc, req.node)
            _, ek_ret = _leg(inst, req.node, inst.depot)
            if bat - ek < inst.reserve_kwh - 1e-9:
                continue
            # Conservative: must be able to return to depot above reserve after serve
            if bat - ek - ek_ret < inst.reserve_kwh - 1e-9:
                continue
            arr = t + ts
            start = max(arr, req.tw_start)
            if start + req.service_s > req.tw_end + 1e-9:
                continue
            bat -= ek
            t = start + req.service_s
            loc = req.node
            remaining.remove(req)
            served += 1
            progressed = True
            break
        if progressed:
            continue
        if mode == "always_full":
            tgt = 1.0
            want = bat < inst.bmax - 1e-6
        else:
            # adaptive: charge to 0.7 when headroom low OR when stuck with work left
            tgt = 0.70
            want = (bat - inst.reserve_kwh) < 3.0 or (bool(remaining) and bat < 0.99 * inst.bmax)
        if want and go_depot_and_charge(tgt):
            charged_once = True
            continue
        break
    return served


def _line_travel(n_nodes: int = 4, edge_s: float = 60.0, edge_kwh: float = 0.2) -> tuple[dict, dict]:
    ts: dict[tuple[int, int], float] = {}
    ek: dict[tuple[int, int], float] = {}
    for u in range(n_nodes):
        for v in range(n_nodes):
            d = abs(u - v)
            ts[(u, v)] = d * edge_s
            ek[(u, v)] = d * edge_kwh
    return ts, ek


def instance_a_early_charge() -> ChargeCommitInstance:
    """Must charge before serving far R1 (energy); no-charge fails return reserve."""
    ts, ek = _line_travel()
    ek2 = {k: abs(k[0] - k[1]) * 1.0 for k in ek}  # 3 kWh each way
    return ChargeCommitInstance(
        name="A_early_charge",
        description="Early charge optimal: soc=0.20 cannot round-trip 0↔3 under reserve without charging.",
        travel_s=ts,
        travel_kwh=ek2,
        requests=[ToyRequest("R1", node=3, tw_start=0, tw_end=20000, service_s=60)],
        initial_soc=0.20,  # 8 kWh; need ≥9 after outbound for return+reserve
        reserve_kwh=6.0,
        bmax=40.0,
        charge_kw=22.0,
    )


def instance_b_serve_before_charge() -> ChargeCommitInstance:
    """Tight R1: always-full before serve misses; serve-first succeeds."""
    ts, ek = _line_travel()
    return ChargeCommitInstance(
        name="B_serve_before_charge",
        description="Serve-before-charge optimal; charging full first misses R1 window.",
        travel_s=ts,
        travel_kwh=ek,
        requests=[
            ToyRequest("R1", node=1, tw_start=0, tw_end=150, service_s=30),
            ToyRequest("R2", node=3, tw_start=0, tw_end=50000, service_s=60),
        ],
        initial_soc=0.55,
        reserve_kwh=4.0,
        bmax=40.0,
        charge_kw=5.0,  # full charge from 0.55: 18 kWh → 12960 s >> 150
    )


def instance_c_partial_better() -> ChargeCommitInstance:
    """Window allows charge-to-0.50 then serve; full charge overshoots time."""
    ts, ek = _line_travel()
    ek2 = {k: abs(k[0] - k[1]) * 1.5 for k in ek}  # 4.5 kWh each way
    return ChargeCommitInstance(
        name="C_partial_better",
        description="Partial target 0.50 enables serve in window; full charge too slow.",
        travel_s=ts,
        travel_kwh=ek2,
        requests=[ToyRequest("R1", node=3, tw_start=0, tw_end=2800, service_s=60)],
        initial_soc=0.40,  # 16 kWh; round-trip 9 + reserve 8 ⇒ must charge
        reserve_kwh=8.0,
        bmax=40.0,
        charge_kw=11.0,
    )


def instance_d_charge_enables_later() -> ChargeCommitInstance:
    """Serve R1, return+charge, then R2 — without mid charge only one fits energy."""
    ts, ek = _line_travel()
    ek2 = {k: abs(k[0] - k[1]) * 1.2 for k in ek}
    return ChargeCommitInstance(
        name="D_charge_enables_later",
        description="Mid-tour charge enables second commitment after first service.",
        travel_s=ts,
        travel_kwh=ek2,
        requests=[
            ToyRequest("R1", node=2, tw_start=0, tw_end=3000, service_s=60),
            ToyRequest("R2", node=3, tw_start=0, tw_end=50000, service_s=60),
        ],
        initial_soc=0.28,  # 11.2 kWh
        reserve_kwh=6.0,
        bmax=40.0,
        charge_kw=22.0,
    )


def run_all_canned() -> list[EnumResult]:
    return [
        enumerate_charge_commit(instance_a_early_charge()),
        enumerate_charge_commit(instance_b_serve_before_charge()),
        enumerate_charge_commit(instance_c_partial_better()),
        enumerate_charge_commit(instance_d_charge_enables_later()),
    ]


def results_to_rows(results: list[EnumResult]) -> list[dict]:
    rows = []
    for r in results:
        rows.append(
            {
                "instance": r.instance,
                "best_on_time": r.best_on_time,
                "best_travel_s": r.best_distance_proxy_s,
                "n_enumerated": r.n_enumerated,
                "greedy_on_time": r.greedy_on_time,
                "always_full_on_time": r.always_full_on_time,
                "gap_greedy": r.best_on_time - r.greedy_on_time,
                "gap_always_full": r.best_on_time - r.always_full_on_time,
                "notes": r.notes,
                "best_plan": r.best_plan,
            }
        )
    return rows
