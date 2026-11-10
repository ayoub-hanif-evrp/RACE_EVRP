"""Peer-bid content must reach the neural observation."""

from __future__ import annotations

import numpy as np

from race_casablanca.marl.env import BASE_FEAT, K_TASKS, TASK_FEAT, RaceMultiAgentEnv
from race_casablanca.sim.synthetic import make_two_request_scenario


def _factory(seed: int = 0, n_vehicles: int = 2):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
    return sc


def test_obs_dim_documents_peer_features():
    env = RaceMultiAgentEnv(scenario_factory=_factory, n_vehicles=2, initial_soc=1.0, seed=0)
    assert env.obs_dim == BASE_FEAT + K_TASKS * TASK_FEAT
    steps = env.reset(seed=0)
    for st in steps.values():
        assert st.obs.shape[0] == env.obs_dim


def test_peer_bid_payload_changes_observation():
    env = RaceMultiAgentEnv(
        scenario_factory=_factory,
        n_vehicles=2,
        initial_soc=1.0,
        ablation="F_race_marl",
        seed=0,
        max_decisions=20,
    )
    steps = env.reset(seed=0)
    vid = list(steps.keys())[0]
    obs = env._pending_obs[vid]
    # Inject a synthetic delivered peer bid for the first announced task if any
    if not obs.announced:
        return
    rid = obs.announced[0].request_id
    before = steps[vid].obs.copy()
    env._pending_obs[vid].peer_bids[rid] = {
        "peer_x": {
            "request_id": rid,
            "sender_id": "peer_x",
            "feasible": True,
            "marginal_travel_s": 100.0,
            "energy_flex_kwh": 5.0,
            "deadline_slack_s": 600.0,
            "as_of_s": float(obs.now_s) - 10.0,
            "expires_s": float(obs.now_s) + 1000.0,
            "withdrawn": False,
        }
    }
    vec, _, _, _ = env._encode(env._pending_obs[vid])
    assert not np.allclose(before, vec), "peer bid content must change the observation vector"
    # Peer travel feature slot for task 0: BASE + 6 (own) + 0 (peer_travel index inside peer block)
    # own=6, peer starts at index 6 within task block → peer_travel at BASE+6
    peer_travel_idx = BASE_FEAT + 6
    assert vec[peer_travel_idx] > 0.0
