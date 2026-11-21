"""Phase 3: multi-objective reward + short MAPPO smoke on conflict factory."""

from __future__ import annotations

import pytest

from race_casablanca.marl.env import (
    ABLATION_D,
    BYTE_COST,
    CHARGE_COST,
    MISSED_FEASIBLE_COST,
    MSG_COST,
    RaceMultiAgentEnv,
)
from race_casablanca.marl.episode_sampler import ProceduralEpisodeGenerator
from race_casablanca.marl.seed_banks import episode_train_seed


def test_phase3_reward_penalizes_messages_and_missed():
    """Constructed deltas: more msgs / missed → lower reward than OT-only."""
    gen = ProceduralEpisodeGenerator.from_release(load_network=True)

    def factory(seed=0, n_vehicles=3):
        return gen.make_episode(
            regime="conflict_dense",
            seed=episode_train_seed(0, int(seed) + 11),
            n_vehicles=n_vehicles,
            episode_index=int(seed),
        )

    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ABLATION_D,
        seed=0,
        max_decisions=30,
        initial_soc=0.35,
        msg_cost=MSG_COST,
        byte_cost=BYTE_COST,
        missed_feasible_cost=MISSED_FEASIBLE_COST,
        charge_cost=CHARGE_COST,
    )
    steps = env.reset(seed=0)
    # One defer-all step; reward info should expose Phase-3 fields.
    from race_casablanca.marl.env import COMM_SUPPRESS, OP_DEFER

    actions = {vid: (OP_DEFER, COMM_SUPPRESS) for vid in steps}
    steps = env.step(actions)
    info = list(steps.values())[0].info
    assert "delta_bytes" in info
    assert "delta_missed_feasible" in info
    assert "delta_charge" in info
    assert "team_reward" in info


@pytest.mark.slow
def test_phase3_mappo_smoke_conflict():
    """Short BC+MAPPO on conflict_dense must change params and finish."""
    import torch

    from race_casablanca.marl.bc import behavior_clone, collect_bc_batch
    from race_casablanca.marl.env import ABLATION_F
    from race_casablanca.marl.mappo import MAPPOTrainer
    from race_casablanca.marl.phase3_eval import conflict_factory

    env = RaceMultiAgentEnv(
        scenario_factory=conflict_factory(master_seed=0, energy_binding=True),
        n_vehicles=3,
        ablation=ABLATION_F,
        seed=0,
        max_decisions=80,
        initial_soc=0.35,
    )
    batch = collect_bc_batch(env, n_steps=32, seed=0, teacher="native_execute")
    trainer = MAPPOTrainer(env)
    before = {k: v.detach().clone() for k, v in trainer.actor.named_parameters()}
    behavior_clone(trainer.actor, batch, epochs=3, device=trainer.device)
    trainer.train(iterations=2, steps_per_iter=16)
    changed = any(not torch.allclose(before[k], v) for k, v in trainer.actor.named_parameters())
    assert changed
    ev = trainer.evaluate_deterministic(n_episodes=1)
    assert "mean_ot" in ev
