"""Stage 8.3: native-bridge intent labels apply via env.step without collapsing OT."""

from __future__ import annotations

from copy import deepcopy

import pytest


@pytest.mark.slow
def test_native_bridge_intent_competitive_on_peak():
    from race_casablanca.marl.bc import NativeBridgeTeacher
    from race_casablanca.marl.env import ABLATION_D, RaceMultiAgentEnv
    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
    from race_casablanca.sim.types import RequestStatus

    paths = resolve_eval_dirs()
    if not paths:
        pytest.skip("no eval scenarios")
    graph = load_drive_graph()
    model = load_congestion_model()
    sc = load_scenario(paths[0], load_network=False, graph=graph, model=model)
    reqs0 = deepcopy(sc.requests)

    def factory(seed=0, n_vehicles=3):
        reqs = deepcopy(reqs0)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        return {
            "scenario_id": sc.scenario_id,
            "graph": graph,
            "model": model,
            "requests": reqs,
            "fleet": {**sc.fleet, "n_vehicles": 3},
            "depot_node": sc.depot_node,
            "shift_start_s": sc.shift_start_s,
            "shift_end_s": sc.shift_end_s,
            "day": getattr(sc, "day", "Monday"),
        }

    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ABLATION_D,
        seed=0,
        max_decisions=2000,
        initial_soc=0.35,
    )
    teacher = NativeBridgeTeacher(mode="intent")
    steps = env.reset(seed=0)
    while True:
        steps = env.step(teacher.actions(env))
        if list(steps.values())[0].done:
            break
    ot = float(env.final_metrics().get("on_time_rate_all", 0.0))
    assert ot >= 0.70, f"intent bridge OT too low: {ot}"
