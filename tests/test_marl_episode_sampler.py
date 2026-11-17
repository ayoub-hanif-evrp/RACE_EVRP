"""Scientific hygiene for procedural MARL training episodes."""

from __future__ import annotations

import pytest

from race_casablanca.marl.seed_banks import (
    FORBIDDEN_TRAIN_SEEDS,
    LOCKED_FINAL_SEEDS,
    TRAIN_SEED_RANGE,
    assert_train_seed_allowed,
    curriculum_regime,
    episode_train_seed,
    is_forbidden_train_seed,
)


def test_train_seed_range_disjoint_from_locked_and_eval():
    lo, hi = TRAIN_SEED_RANGE
    assert lo > max(FORBIDDEN_TRAIN_SEEDS)
    for s in (2101, 2201, 2301, 1101, 1, 101, 201):
        assert is_forbidden_train_seed(s)
        assert not (lo <= s <= hi)


def test_episode_seeds_deterministic_and_allowed():
    a = [episode_train_seed(7, i) for i in range(50)]
    b = [episode_train_seed(7, i) for i in range(50)]
    assert a == b
    assert len(set(a)) == 50
    for s in a:
        assert_train_seed_allowed(s)
        assert s not in LOCKED_FINAL_SEEDS
        assert s not in FORBIDDEN_TRAIN_SEEDS


def test_assert_rejects_locked_seed():
    with pytest.raises(ValueError):
        assert_train_seed_allowed(2101)
    with pytest.raises(ValueError):
        assert_train_seed_allowed(42)


def test_curriculum_round_robin():
    assert curriculum_regime(0) == "baseline"
    assert curriculum_regime(1) == "peak_stress"
    assert curriculum_regime(2) == "tight_windows"
    assert curriculum_regime(3) == "baseline"


def test_protocol_file_exists_and_forbids_locked_training():
    from race_casablanca.marl.episode_sampler import load_protocol

    proto = load_protocol()
    assert proto["no_retune_on_locked_final"] is True
    assert proto["splits"]["locked_final"]["training_forbidden"] is True
    assert proto["splits"]["train"]["source"] == "on_the_fly_generator"
    assert proto["splits"]["train"]["recommended_episodes"] >= 2000


def test_procedural_episode_generates_valid_requests():
    from race_casablanca.marl.episode_sampler import ProceduralEpisodeGenerator

    gen = ProceduralEpisodeGenerator.from_release(load_network=False)
    ep0 = gen.make_episode(regime="baseline", seed=episode_train_seed(0, 0), n_vehicles=3)
    ep1 = gen.make_episode(regime="peak_stress", seed=episode_train_seed(0, 1), n_vehicles=3)
    assert ep0["metadata"]["split"] == "procedural_train"
    assert ep0["metadata"]["is_observed_order"] is False
    assert len(ep0["requests"]) == 12
    assert len(ep1["requests"]) == 40
    assert ep0["depot_node"] > 0
    assert all(r.snap_node > 0 for r in ep0["requests"])
    assert all(r.tw_end_s > r.tw_start_s for r in ep0["requests"])
    # Different episodes => different request ids / content
    assert {r.request_id for r in ep0["requests"]} != {r.request_id for r in ep1["requests"]}


def test_factory_never_emits_forbidden_seeds():
    from race_casablanca.marl.episode_sampler import make_procedural_train_factory

    _gen, factory = make_procedural_train_factory(master_seed=3, n_vehicles=3, load_network=False)
    for i in range(30):
        sc = factory(seed=i)
        seed = int(sc["metadata"]["seed"])
        assert seed not in FORBIDDEN_TRAIN_SEEDS
        assert "locked" not in sc["scenario_id"]
