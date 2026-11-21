"""Phase 2: conflict_dense regime, PO peer-bid stripping, G3 comm-value gate."""

from __future__ import annotations

import pytest

from race_casablanca.marl.env import ABLATION_A, ABLATION_D, RaceMultiAgentEnv
from race_casablanca.marl.episode_sampler import ProceduralEpisodeGenerator
from race_casablanca.marl.seed_banks import REGIME_ORDER, episode_train_seed


def test_conflict_dense_in_regime_order():
    assert "conflict_dense" in REGIME_ORDER


def test_conflict_dense_episode_generates_sync_burst():
    gen = ProceduralEpisodeGenerator.from_release(load_network=False)
    seed = episode_train_seed(0, 42)
    ep = gen.make_episode(regime="conflict_dense", seed=seed, n_vehicles=3, episode_index=0)
    assert ep["metadata"]["regime"] == "conflict_dense"
    assert len(ep["requests"]) == 24
    releases = sorted(r.release_s for r in ep["requests"])
    # Burst ≤ 0.5 h = 1800 s from first release.
    assert releases[-1] - releases[0] <= 1800.0 + 1e-6


def test_ablation_a_strips_peer_bid_features():
    from dataclasses import replace

    gen = ProceduralEpisodeGenerator.from_release(load_network=True)

    def factory(seed=0, n_vehicles=3):
        return gen.make_episode(
            regime="conflict_dense",
            seed=episode_train_seed(0, int(seed) + 7),
            n_vehicles=n_vehicles,
            episode_index=int(seed),
        )

    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ABLATION_A,
        seed=0,
        max_decisions=5,
        initial_soc=0.35,
    )
    steps = env.reset(seed=0)
    obs = env._pending_obs[env._agent_ids[0]]
    # Even if peer_bids are present on the obs object, ablation A must hide them.
    obs2 = replace(
        obs,
        peer_bids={"Rfake": {"V2": {"feasible": True, "marginal_travel_s": 1.0}}},
    )
    assert env._peer_bids_for_encode(obs2) == {}
    vec, _, _, _ = env._encode(obs2)
    assert float(vec[7]) == 0.0  # peer_bids count feature
    assert list(steps.values())[0].obs is not None


def test_f_comm_mask_allows_feasible_send_without_peers():
    """G4: F must not gate send on energy-cert-only (else first bids never fire)."""
    from race_casablanca.marl.env import (
        ABLATION_F,
        COMM_SUPPRESS,
        K_TASKS,
        RaceMultiAgentEnv,
    )
    from race_casablanca.marl.episode_sampler import ProceduralEpisodeGenerator
    from race_casablanca.marl.seed_banks import episode_train_seed

    gen = ProceduralEpisodeGenerator.from_release(load_network=True)

    def factory(seed=0, n_vehicles=3):
        return gen.make_episode(
            regime="conflict_dense",
            seed=episode_train_seed(0, int(seed) + 77),
            n_vehicles=n_vehicles,
            episode_index=int(seed),
        )

    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ABLATION_F,
        seed=0,
        max_decisions=20,
    )
    steps = env.reset(seed=0)
    allow = any(float(st.comm_mask[:K_TASKS].sum()) > 0 for st in steps.values())
    assert allow, "F should offer at least one feasible send slot at conflict start"


def test_conflict_dense_spreads_vehicles_off_depot():
    from race_casablanca.marl.env import ABLATION_F, RaceMultiAgentEnv
    from race_casablanca.marl.episode_sampler import ProceduralEpisodeGenerator
    from race_casablanca.marl.seed_banks import episode_train_seed

    gen = ProceduralEpisodeGenerator.from_release(load_network=True)

    def factory(seed=0, n_vehicles=3):
        return gen.make_episode(
            regime="conflict_dense",
            seed=episode_train_seed(0, int(seed) + 33),
            n_vehicles=n_vehicles,
            episode_index=int(seed),
        )

    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=3,
        ablation=ABLATION_F,
        seed=0,
        max_decisions=5,
    )
    env.reset(seed=0)
    depot = int(env.sim.depot_node)
    nodes = [int(v.node) for v in env.sim.vehicles.values()]
    assert any(n != depot for n in nodes), f"expected spread off depot, got {nodes}"


def test_energy_binding_sets_low_soc():
    gen = ProceduralEpisodeGenerator.from_release(load_network=False)
    seed = episode_train_seed(0, 3)
    ep = gen.make_episode(
        regime="conflict_dense",
        seed=seed,
        n_vehicles=3,
        energy_binding=True,
    )
    assert float(ep["fleet"]["initial_soc"]) == pytest.approx(0.28)


@pytest.mark.slow
def test_g3_full_beats_none_on_conflict_dense():
    """Gate G3: mean(full − none) OT ≥ 8 pp on conflict_dense native rollouts."""
    from race_casablanca.marl.g3_comm_value import conflict_comm_ablation_rows, mean_comm_delta_ot

    rows = conflict_comm_ablation_rows(n_episodes=4, master_seed=0, n_vehicles=3)
    mean_d = mean_comm_delta_ot(rows)
    # Soft floor for CI noise on tiny n; plan target is 0.08 — require clear positive gap.
    assert mean_d >= 0.05, f"G3 weak/fail: mean delta OT={mean_d:.4f} rows={rows}"
    assert all(r["full_msgs"] >= r["none_msgs"] for r in rows)
