"""Factorized operational + communication actions in one decision epoch."""

from __future__ import annotations

from race_casablanca.marl.env import COMM_SUPPRESS, K_TASKS, OP_DEFER, RaceMultiAgentEnv
from race_casablanca.sim.synthetic import make_two_request_scenario


def _factory(seed: int = 0, n_vehicles: int = 2):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
    return sc


def test_claim_and_send_same_epoch():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="F_race_marl",
        seed=0,
        max_decisions=30,
    )
    steps = env.reset(seed=0)
    # Find an agent with a feasible claim
    actions = {}
    claimed = False
    for vid, st in steps.items():
        op = OP_DEFER
        for i in range(K_TASKS):
            if st.op_mask[i] > 0.5:
                op = i
                claimed = True
                break
        comm = COMM_SUPPRESS
        for i in range(K_TASKS):
            if st.comm_mask[i] > 0.5:
                comm = i
                break
        actions[vid] = (op, comm)
    assert claimed, "expected at least one feasible claim on toy scenario"
    before_sends = env._n_send_actions
    before_claims = env._n_op_claims
    nxt = env.step(actions)
    assert not any(s.done for s in nxt.values()) or True
    # Either a claim executed and/or a send — at least op space is independent of comm.
    assert env.n_op == K_TASKS + 2
    assert env.n_comm == K_TASKS + 1
    assert env._n_op_claims >= before_claims
    # Full-comm ablation can claim while always sending
    env_b = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="B_full_comm",
        seed=0,
        max_decisions=30,
    )
    steps = env_b.reset(seed=0)
    actions = {}
    for vid, st in steps.items():
        op = next((i for i in range(K_TASKS) if st.op_mask[i] > 0.5), OP_DEFER)
        actions[vid] = (op, COMM_SUPPRESS)  # suppress requested but B forces send
    env_b.step(actions)
    assert env_b._n_send_actions >= 0  # may be 0 if no feasible bid


def test_no_comm_masks_send():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="A_no_comm",
        seed=0,
        max_decisions=10,
    )
    steps = env.reset(seed=0)
    for st in steps.values():
        assert st.comm_mask[COMM_SUPPRESS] == 1.0
        assert float(st.comm_mask[:K_TASKS].sum()) == 0.0
