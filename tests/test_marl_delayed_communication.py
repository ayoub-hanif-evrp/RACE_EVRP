"""Delayed-message semantics: no unbounded send loops."""

from __future__ import annotations

from race_casablanca.marl.env import COMM_SUPPRESS, MAX_SENDS_PER_TASK, OP_DEFER, RaceMultiAgentEnv
from race_casablanca.sim.synthetic import make_two_request_scenario


def _factory(seed: int = 0, n_vehicles: int = 2):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
    return sc


def test_message_delivery_does_not_trigger_extra_decision_by_default():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        message_delay_s=30.0,
        ablation="B_full_comm",
        seed=0,
        max_decisions=50,
        message_triggers_decision=False,
    )
    steps = env.reset(seed=0)
    n = 0
    while n < 50:
        actions = {vid: (OP_DEFER, COMM_SUPPRESS) for vid in steps}
        steps = env.step(actions)
        n += 1
        if list(steps.values())[0].done:
            break
    m = env.final_metrics()
    # Finite decisions and bounded sends (cooldown + max per task)
    assert m["n_decisions"] <= 50
    assert m["n_send_actions"] <= env.n_vehicles * 10 * MAX_SENDS_PER_TASK


def test_no_infinite_loop_under_delay_full_comm():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        message_delay_s=30.0,
        ablation="F_race_marl",
        seed=0,
        max_decisions=40,
    )
    steps = env.reset(seed=0)
    for _ in range(40):
        actions = {}
        for vid, st in steps.items():
            op = next((i for i in range(5) if st.op_mask[i] > 0.5), OP_DEFER)
            comm = next((i for i in range(5) if st.comm_mask[i] > 0.5), COMM_SUPPRESS)
            actions[vid] = (op, comm)
        steps = env.step(actions)
        if list(steps.values())[0].done:
            break
    assert env._n_decisions <= 40
    # Must not hit pathological 1500-send regime on toy scenario
    assert env._n_send_actions < 200
