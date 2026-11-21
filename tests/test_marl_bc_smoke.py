"""Phase 1 slice 3: short BC smoke from native_execute teacher."""

from __future__ import annotations

from copy import deepcopy

import pytest
import torch

from race_casablanca.marl.bc import behavior_clone, collect_bc_batch
from race_casablanca.marl.env import ABLATION_D, RaceMultiAgentEnv
from race_casablanca.marl.nets import FactorizedActor
from race_casablanca.marl.scenarios import resolve_eval_dirs
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
from race_casablanca.sim.types import RequestStatus


@pytest.mark.slow
def test_bc_smoke_native_execute_student_ot():
    """After short BC, student via env.step should not collapse."""
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
        claim_resolve_mode="sequential_native",
    )
    batch = collect_bc_batch(env, n_steps=128, seed=0, teacher="native_execute")
    actor = FactorizedActor(obs_dim=env.obs_dim, n_op=env.n_op, n_comm=env.n_comm)
    behavior_clone(actor, batch, epochs=15, lr=1e-3)

    steps = env.reset(seed=1)
    actor.eval()
    while True:
        actions = {}
        for vid, st in steps.items():
            with torch.no_grad():
                o = torch.as_tensor(st.obs).unsqueeze(0)
                om = torch.as_tensor(st.op_mask).unsqueeze(0)
                cm = torch.as_tensor(st.comm_mask).unsqueeze(0)
                op_logits, comm_logits = actor(o, om, cm)
                actions[vid] = (int(op_logits.argmax(-1)), int(comm_logits.argmax(-1)))
        steps = env.step(actions)
        if list(steps.values())[0].done:
            break
    ot = float(env.final_metrics().get("on_time_rate_all", 0.0))
    # Smoke (not full G2 ≥0.78): pipeline runs and avoids total collapse.
    assert ot >= 0.40, f"BC smoke student OT too low: {ot}"
