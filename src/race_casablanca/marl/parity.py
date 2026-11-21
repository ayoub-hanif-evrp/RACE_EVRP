"""Native vs MARL-teacher parity helpers (top-tier Phase 1 / gate G1)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from race_casablanca.marl.bc import NativeBridgeTeacher, _advance_without_reexec
from race_casablanca.marl.env import ABLATION_D, RaceMultiAgentEnv
from race_casablanca.policies import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.types import RequestStatus


def run_native_cooperative(
    sc,
    graph,
    model,
    *,
    n_vehicles: int = 3,
    soc: float = 0.35,
    delay_s: float = 0.0,
    seed: int = 0,
    comm_mode: str = "selective",
) -> dict[str, float]:
    reqs = deepcopy(sc.requests)
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    pol = RaceCooperativePolicy(comm_mode=comm_mode, enable_readiness_charge=True, rng_seed=7)
    sim = OnlineSimulator(
        scenario_id=f"{sc.scenario_id}/native",
        graph=graph,
        model=model,
        requests=reqs,
        fleet={**sc.fleet, "n_vehicles": n_vehicles},
        depot_node=sc.depot_node,
        shift_start_s=sc.shift_start_s,
        shift_end_s=sc.shift_end_s,
        config=SimConfig(
            info_mode="restricted",
            seed=seed,
            initial_soc=soc,
            n_vehicles=n_vehicles,
            message_delay_s=delay_s,
            packet_loss_p=0.0,
            periodic_state_broadcast=False,
            decision_on_release=True,
            day=str(getattr(sc, "day", "Monday")),
        ),
        policy=pol,
    )
    m = sim.run().to_dict()
    return {
        "on_time_rate_all": float(m["on_time_rate_all"]),
        "n_served": float(m["n_served"]),
        "n_on_time": float(m["n_on_time"]),
        "n_requests": float(m["n_requests"]),
    }


def _scenario_factory(sc, graph, model, *, n_vehicles: int) -> Callable[..., dict]:
    reqs0 = deepcopy(sc.requests)

    def factory(seed: int = 0, n_vehicles: int = n_vehicles):
        reqs = deepcopy(reqs0)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        return {
            "scenario_id": sc.scenario_id,
            "graph": graph,
            "model": model,
            "requests": reqs,
            "fleet": {**sc.fleet, "n_vehicles": n_vehicles},
            "depot_node": sc.depot_node,
            "shift_start_s": sc.shift_start_s,
            "shift_end_s": sc.shift_end_s,
            "day": getattr(sc, "day", "Monday"),
        }

    return factory


def run_marl_native_teacher(
    sc,
    graph,
    model,
    *,
    n_vehicles: int = 3,
    soc: float = 0.35,
    delay_s: float = 0.0,
    seed: int = 0,
    teacher_mode: str = "execute",
    claim_resolve_mode: str = "sequential_native",
    max_decisions: int = 2000,
    ablation: str = ABLATION_D,
) -> dict[str, float]:
    factory = _scenario_factory(sc, graph, model, n_vehicles=n_vehicles)
    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=n_vehicles,
        initial_soc=soc,
        message_delay_s=delay_s,
        ablation=ablation,
        seed=seed,
        max_decisions=max_decisions,
        claim_resolve_mode=claim_resolve_mode,
    )
    teacher = NativeBridgeTeacher(mode=teacher_mode)
    env.reset(seed=seed)
    teacher.reset()
    if teacher_mode == "execute":
        while True:
            teacher.actions(env)
            steps = _advance_without_reexec(env)
            if list(steps.values())[0].done:
                break
    else:
        # intent_matched / intent: labels then env.step
        while True:
            steps = env.step(teacher.actions(env))
            if list(steps.values())[0].done:
                break
    m = env.final_metrics()
    return {
        "on_time_rate_all": float(m["on_time_rate_all"]),
        "n_served": float(m.get("n_served", 0)),
        "n_on_time": float(m.get("n_on_time", 0)),
        "n_requests": float(m.get("n_requests", 0)),
        "claim_resolve_mode": str(m.get("claim_resolve_mode", "")),
        "teacher_mode": teacher_mode,
    }


def parity_rows(
    scenarios: list[Any],
    graph,
    model,
    *,
    n_vehicles: int = 3,
    soc: float = 0.35,
    delay_s: float = 0.0,
    teacher_mode: str = "execute",
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for sc in scenarios:
        native = run_native_cooperative(
            sc, graph, model, n_vehicles=n_vehicles, soc=soc, delay_s=delay_s
        )
        marl = run_marl_native_teacher(
            sc,
            graph,
            model,
            n_vehicles=n_vehicles,
            soc=soc,
            delay_s=delay_s,
            teacher_mode=teacher_mode,
        )
        ot_n = float(native["on_time_rate_all"])
        ot_m = float(marl["on_time_rate_all"])
        rows.append(
            {
                "scenario_id": str(getattr(sc, "scenario_id", "")),
                "native_ot": ot_n,
                "marl_teacher_ot": ot_m,
                "delta_ot": ot_m - ot_n,
                "teacher_mode": teacher_mode,
            }
        )
    return rows


def mean_delta_ot(rows: list[dict[str, float | str]]) -> float:
    if not rows:
        return 0.0
    return float(sum(float(r["delta_ot"]) for r in rows) / len(rows))
