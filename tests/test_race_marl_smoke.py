"""Prove RACE-MARL actually runs neural forward/backward updates (Stage 8.1)."""

from __future__ import annotations

import torch

from race_casablanca.marl.env import RaceMultiAgentEnv
from race_casablanca.marl.mappo import MAPPOTrainer
from race_casablanca.sim.synthetic import make_two_request_scenario


def _factory(seed: int = 0, n_vehicles: int = 2):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
    return sc


def test_mappo_parameters_change_and_forward_pass():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        message_delay_s=0.0,
        comm_enabled=True,
        seed=0,
        max_decisions=20,
    )
    trainer = MAPPOTrainer(env, epochs=2)
    before = {k: v.detach().clone() for k, v in trainer.actor.named_parameters()}
    logs = trainer.train(iterations=2, steps_per_iter=8)
    assert len(logs) == 2
    assert "loss" in logs[-1]
    changed = any(not torch.allclose(before[k], v) for k, v in trainer.actor.named_parameters())
    assert changed, "expected gradient updates to change actor weights"
    steps = env.reset(seed=1)
    for st in steps.values():
        o = torch.as_tensor(st.obs).unsqueeze(0)
        om = torch.as_tensor(st.op_mask).unsqueeze(0)
        cm = torch.as_tensor(st.comm_mask).unsqueeze(0)
        op_logits, comm_logits = trainer.actor(o, om, cm)
        assert op_logits.shape[-1] == env.n_op
        assert comm_logits.shape[-1] == env.n_comm
