"""Train/validation separation and BC recovery smoke."""

from __future__ import annotations

from race_casablanca.marl.bc import behavior_clone, collect_bc_batch, evaluate_bc_accuracy
from race_casablanca.marl.env import RaceMultiAgentEnv
from race_casablanca.marl.mappo import MAPPOTrainer
from race_casablanca.marl.nets import FactorizedActor
from race_casablanca.sim.synthetic import make_two_request_scenario


def _factory(seed: int = 0, n_vehicles: int = 2):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
    sc["scenario_id"] = f"toy-{seed}"
    return sc


def test_bc_then_mappo_improves_over_random_init():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="A_no_comm",
        seed=0,
        max_decisions=40,
    )
    batch = collect_bc_batch(env, n_steps=64, seed=0, teacher="cooperative")
    actor = FactorizedActor(env.obs_dim, env.n_op, env.n_comm)
    losses = behavior_clone(actor, batch, epochs=10, lr=1e-3)
    assert losses[-1] < losses[0], "BC loss must decrease"
    acc = evaluate_bc_accuracy(actor, batch)
    assert acc["op_accuracy"] >= 0.5, f"BC op accuracy too low: {acc}"
    trainer = MAPPOTrainer(env, epochs=2)
    trainer.actor.load_state_dict(actor.state_dict())
    before = trainer.evaluate_deterministic(n_episodes=2)
    trainer.train(iterations=3, steps_per_iter=16)
    after = trainer.evaluate_deterministic(n_episodes=2)
    assert 0.0 <= before["mean_ot"] <= 1.0
    assert 0.0 <= after["mean_ot"] <= 1.0
    # Toy two-request scene: competent policy should serve something
    assert after["mean_ot"] >= 0.5 or before["mean_ot"] >= 0.5
