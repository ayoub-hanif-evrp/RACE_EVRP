"""Stage 3A preflight: energy non-leakage, atomic commit, metric integrity."""

from __future__ import annotations

import copy

from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.feasibility_check import projected_state_after_lock
from race_casablanca.sim.policy_api import build_full_observation, to_visible
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import RequestStatus


def test_projected_state_ignores_hidden_realized_energy():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0, energy_uncertainty_delta=0.3),
        policy=None,
    )
    sim.now_s = 0.0
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    assert sim.try_assign("V1", "R1")
    v = sim.vehicles["V1"]
    assert v.busy
    # Corrupt hidden realized energy to an extreme value
    v.en_route_energy_kwh = 999.0
    proj = projected_state_after_lock(
        v, sim.requests, sim.router, sim.energy, sim.depot_node, sim.now_s
    )
    # Must use conservative path energy, not 999
    assert proj.battery_kwh > 40.0 - 999.0 + 1.0
    assert abs(proj.battery_kwh - (v.battery_kwh - sim.energy.conservative_kwh(v.path_length_m))) < 1e-6


def test_observations_hide_en_route_realized_energy():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0, energy_uncertainty_delta=0.25),
        policy=None,
    )
    sim.now_s = 0.0
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    sim.try_assign("V1", "R1")
    sim.vehicles["V1"].en_route_energy_kwh = 12.345
    obs = build_full_observation(sim)
    vis = obs.vehicles["V1"]
    assert not hasattr(vis, "en_route_energy_kwh")
    d = vis.__dict__
    assert "en_route_energy_kwh" not in d


def test_identical_obs_under_different_hidden_xi():
    """Same public history ⇒ same observations despite different hidden realized xi."""

    def setup(xi_force: float):
        base = make_two_request_scenario()
        sim = OnlineSimulator(
            scenario_id=base["scenario_id"],
            graph=base["graph"],
            model=base["model"],
            requests=base["requests"],
            fleet=base["fleet"],
            depot_node=base["depot_node"],
            shift_start_s=base["shift_start_s"],
            shift_end_s=base["shift_end_s"],
            config=SimConfig(info_mode="full", seed=0, energy_uncertainty_delta=0.2),
            policy=None,
        )
        sim.now_s = 0.0
        sim.requests["R1"].status = RequestStatus.AVAILABLE
        sim.try_assign("V1", "R1")
        sim.vehicles["V1"].en_route_energy_kwh = xi_force
        return build_full_observation(sim)

    a = setup(0.1)
    b = setup(9.9)
    assert a.vehicles["V1"] == b.vehicles["V1"]


def test_atomic_commit_rollback_restores_event_queue():
    base = make_two_request_scenario()
    fleet = {**base["fleet"], "n_vehicles": 2}
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=fleet,
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0, n_vehicles=2),
        policy=None,
    )
    sim.now_s = 0.0
    eq_before = list(sim._eq)
    plans_before = {vid: list(v.plan) for vid, v in sim.vehicles.items()}
    # Invalid: duplicate ownership of same request
    ok = sim.commit_fleet_plans({"V1": ["R1"], "V2": ["R1"]})
    assert ok is False
    assert list(sim._eq) == eq_before
    assert {vid: list(v.plan) for vid, v in sim.vehicles.items()} == plans_before


def test_claim_metrics_not_doubled():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0),
        policy=GreedyInsertionPolicy(),
    )
    m = sim.run()
    # Claims should be close to served (may be slightly higher if reassign, none here)
    assert m.n_claims == m.n_served or m.n_claims <= m.n_served + 2
    assert m.n_claims != 2 * m.n_served or m.n_served == 0
