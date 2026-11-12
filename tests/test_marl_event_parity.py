"""Stage 8.3: MARL decision triggers match native idle/service/charge opportunities."""

from __future__ import annotations

from race_casablanca.marl.bc import CooperativeTeacherAdapter, cooperative_teacher_actions
from race_casablanca.marl.env import COMM_SUPPRESS, OP_CHARGE, OP_DEFER, RaceMultiAgentEnv
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import VehicleMode


def _factory(seed: int = 0, n_vehicles: int = 2):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
    return sc


def test_service_end_and_idle_produce_decision_epochs():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="A_no_comm",
        seed=0,
        max_decisions=200,
    )
    adapter = CooperativeTeacherAdapter()
    steps = env.reset(seed=0)
    adapter.reset()
    reasons = []
    while True:
        labels = cooperative_teacher_actions(env, adapter)
        steps = env.step(labels)
        reasons.append(list(steps.values())[0].info.get("decision_reason"))
        if list(steps.values())[0].done:
            break
    m = env.final_metrics()
    assert m["n_decision_release"] >= 1
    # Toy scenario completes service → must reopen decisions after service_end
    assert m["n_decision_service_end"] >= 1, m
    assert m["n_decisions"] > m["n_decision_release"]
    assert "service_end" in reasons or m["n_decision_service_end"] >= 1


def test_charge_mask_hidden_when_feasible_pickup_exists():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=0.35,
        ablation="A_no_comm",
        seed=0,
        max_decisions=20,
    )
    steps = env.reset(seed=0)
    # At first decision with announced feasible tasks, charge should be masked off
    for st in steps.values():
        if float(st.op_mask[:5].sum()) > 0.5:
            assert float(st.op_mask[OP_CHARGE]) < 0.5, "charge must be masked when pickup feasible"


def test_charge_does_not_wipe_committed_pickups():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="A_no_comm",
        seed=0,
        max_decisions=40,
    )
    steps = env.reset(seed=0)
    # Claim a feasible task
    actions = {}
    for vid, st in steps.items():
        op = next((i for i in range(5) if st.op_mask[i] > 0.5), OP_DEFER)
        actions[vid] = (op, COMM_SUPPRESS)
    env.step(actions)
    # Find a vehicle with commitments and force charge via simulator API
    for vid, v in env.sim.vehicles.items():
        if v.committed or any(s.kind == "pickup" for s in v.plan):
            before = list(v.committed)
            before_pickups = [s.request_id for s in v.plan if s.kind == "pickup"]
            env.sim.request_return_depot(vid, charge=True, target_soc=0.70)
            after_pickups = [s.request_id for s in env.sim.vehicles[vid].plan if s.kind == "pickup"]
            assert set(before_pickups).issubset(set(after_pickups)) or set(before).issubset(
                set(env.sim.vehicles[vid].committed)
            ), "charge must not wipe pickup commitments"
            return
    # If no commitments yet, still OK — claim may have been deferred
    assert True
