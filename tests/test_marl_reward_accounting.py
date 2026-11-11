"""Incremental reward accounting tests."""

from __future__ import annotations

from race_casablanca.marl.env import COMM_SUPPRESS, OP_DEFER, RaceMultiAgentEnv
from race_casablanca.sim.synthetic import make_two_request_scenario


def _factory(seed: int = 0, n_vehicles: int = 2):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
    return sc


def test_message_cost_is_incremental_not_cumulative():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="B_full_comm",
        seed=0,
        max_decisions=40,
        msg_cost=0.01,
    )
    steps = env.reset(seed=0)
    penalties = []
    for _ in range(5):
        actions = {vid: (OP_DEFER, COMM_SUPPRESS) for vid in steps}
        steps = env.step(actions)
        info = list(steps.values())[0].info
        penalties.append(info.get("delta_messages", 0.0))
        if list(steps.values())[0].done:
            break
    assert all(p >= 0 for p in penalties)
    assert abs(sum(penalties) - float(env.sim.n_bid_messages)) < 1e-6
    assert env.sim.n_bid_messages >= 1, "full-comm defer loop must still emit bids"


def test_completed_pickup_rewarded_once():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="A_no_comm",
        seed=0,
        max_decisions=80,
        msg_cost=0.0,
    )
    steps = env.reset(seed=0)
    total_ot = 0.0
    while True:
        actions = {}
        for vid, st in steps.items():
            op = OP_DEFER
            for i in range(5):
                if st.op_mask[i] > 0.5:
                    op = i
                    break
            actions[vid] = (op, COMM_SUPPRESS)
        steps = env.step(actions)
        total_ot += list(steps.values())[0].info.get("delta_on_time", 0.0)
        if list(steps.values())[0].done:
            break
    m = env.final_metrics()
    n_on_time = float(m.get("n_on_time", 0.0))
    assert n_on_time >= 1.0, "toy scenario must complete at least one on-time pickup"
    assert abs(total_ot - n_on_time) < 1e-6, "incremental OT reward must match final n_on_time"
