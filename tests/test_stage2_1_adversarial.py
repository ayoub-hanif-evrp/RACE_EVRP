"""Stage 2.1 adversarial checks: energy bound, info isolation, locks."""

from __future__ import annotations

import pytest

from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.policies.limited_info import LimitedInfoCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.policy_api import (
    ActionInterface,
    RestrictedObservation,
    build_restricted_observation,
)
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import RequestStatus


def test_adversarial_worst_case_delta_no_reserve_violation():
    """With conservative planning and ξ=+δ always, reserve must hold."""

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
        config=SimConfig(
            info_mode="full",
            seed=0,
            initial_soc=0.5,
            energy_uncertainty_delta=0.2,
            realization_mode="adversarial_worst",
        ),
        policy=GreedyInsertionPolicy(),
    )
    m = sim.run()
    assert m.battery_reserve_violations == 0
    assert m.battery_exhaustion == 0


def test_restricted_policy_cannot_check_peer_insertion():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet={**base["fleet"], "n_vehicles": 2},
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="restricted", seed=0, n_vehicles=2),
        policy=None,
    )
    actions = ActionInterface(sim, actor_vehicle_id="V1")
    with pytest.raises(PermissionError):
        actions.check_insertion("V2", "R1")


def test_restricted_observation_hides_peer_true_state():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet={**base["fleet"], "n_vehicles": 2},
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="restricted", seed=0, n_vehicles=2, message_delay_s=1000.0),
        policy=None,
    )
    # Corrupt peer true state; without messages, restricted obs must not include it
    sim.vehicles["V2"].battery_kwh = 1.23
    sim.vehicles["V2"].node = 3
    obs = build_restricted_observation(sim, "V1")
    assert isinstance(obs, RestrictedObservation)
    assert "V2" not in obs.peers
    assert obs.self_state.vehicle_id == "V1"
    # No unreleased tasks
    for t in obs.announced:
        assert sim.requests[t.request_id].status == RequestStatus.AVAILABLE


def test_locked_leg_not_overwritten_by_suffix_insert():
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
        policy=None,
    )
    sim.now_s = 0.0
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    sim.try_assign("V1", "R1")
    moving = sim.vehicles["V1"].moving_to
    assert moving is not None
    sim.requests["R2"].status = RequestStatus.AVAILABLE
    sim.try_assign("V1", "R2")
    assert sim.vehicles["V1"].moving_to.request_id == moving.request_id
