"""Invariants: causality, ownership, movement, charging, payload, Stage 2.1 locks."""

from __future__ import annotations

from race_casablanca.coordination.ownership import TaskRegistry
from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.policies.limited_info import LimitedInfoCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.policy_api import FullInfoObservation, RestrictedObservation
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import RequestStatus, Stop


def _make_sim(policy=None, **cfg_kw):
    base = make_two_request_scenario()
    cfg = SimConfig(info_mode="full", seed=0, **cfg_kw)
    return (
        OnlineSimulator(
            scenario_id=base["scenario_id"],
            graph=base["graph"],
            model=base["model"],
            requests=base["requests"],
            fleet=base["fleet"],
            depot_node=base["depot_node"],
            shift_start_s=base["shift_start_s"],
            shift_end_s=base["shift_end_s"],
            config=cfg,
            policy=policy or GreedyInsertionPolicy(),
        ),
        base,
    )


def test_event_causality_nondecreasing_time():
    sim, _ = _make_sim()
    m = sim.run()
    assert sim.now_s >= sim.shift_start_s
    assert m.n_requests == 2


def test_no_future_request_observation():
    class SpyPolicy:
        name = "spy"
        seen_unreleased = False

        def on_decision(self, obs, actions, reason):
            assert isinstance(obs, FullInfoObservation)
            for req in obs.released_requests.values():
                if req.status == RequestStatus.UNRELEASED:
                    SpyPolicy.seen_unreleased = True
            GreedyInsertionPolicy().on_decision(obs, actions, reason)

    sim, _ = _make_sim(policy=SpyPolicy())
    sim.run()
    assert SpyPolicy.seen_unreleased is False


def test_no_duplicate_ownership():
    reg = TaskRegistry()
    assert reg.try_claim("R1", "V1", 0.0)
    assert not reg.try_claim("R1", "V2", 1.0)
    assert reg.n_rejected_duplicates == 1


def test_vehicle_not_instantaneous_and_single_pickup_completion():
    sim, _ = _make_sim()
    sim.run()
    completed_ids = [r.request_id for r in sim.requests.values() if r.status == RequestStatus.COMPLETED]
    assert len(completed_ids) == len(set(completed_ids))
    if completed_ids:
        assert sim.vehicles["V1"].total_distance_m > 0


def test_payload_evolution_and_depot_unload():
    sim, _ = _make_sim()
    sim.run()
    v = sim.vehicles["V1"]
    if v.n_depot_returns > 0:
        assert v.load_kg == 0.0
    assert v.payload_violations == 0


def test_charging_triggers_positive_interval():
    """Forced low SOC + charge_on_return must produce a positive charge event."""

    base = make_two_request_scenario()
    # Only one nearby request so vehicle returns and charges
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"][:1],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0, initial_soc=0.5, charge_on_return=True),
        policy=GreedyInsertionPolicy(),
    )
    m = sim.run()
    assert m.n_charges >= 1
    assert sim.vehicles["V1"].battery_kwh >= 39.999


def test_restricted_messages_deliver_with_delay():
    base = make_two_request_scenario()
    policy = LimitedInfoCooperativePolicy(broadcast_period_s=1.0)
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet={**base["fleet"], "n_vehicles": 2},
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="restricted", message_delay_s=25.0, seed=0, n_vehicles=2),
        policy=policy,
    )
    m = sim.run()
    if m.n_messages > 0:
        assert abs(m.mean_message_delay_s - 25.0) < 1e-9


def test_active_leg_immutable_under_replan():
    sim, base = _make_sim()
    # Manually put vehicle en route to R1, then try assign R2 into plan
    sim.now_s = 0.0
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    assert sim.try_assign("V1", "R1")
    v = sim.vehicles["V1"]
    assert v.busy and v.moving_to is not None
    locked_id = v.moving_to.request_id
    sim.requests["R2"].status = RequestStatus.AVAILABLE
    # Insertion while busy must keep locked stop
    before_moving = v.moving_to.request_id
    sim.try_assign("V1", "R2")
    assert v.moving_to is not None
    assert v.moving_to.request_id == before_moving == locked_id


def test_atomic_reassign_rollback():
    base = make_two_request_scenario()
    fleet = {**base["fleet"], "n_vehicles": 2, "usable_battery_kwh": 40.0}
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=fleet,
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0, n_vehicles=2, initial_soc=1.0, energy_uncertainty_delta=0.0),
        policy=None,
    )
    sim.now_s = 0.0
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    assert sim.try_assign("V1", "R1")
    # Force destination unable to take it: drain V2 below reserve feasibility
    sim.vehicles["V2"].battery_kwh = 0.0
    ok = sim.try_reassign("V1", "V2", "R1")
    assert ok is False
    assert sim.requests["R1"].owner == "V1"
    assert "R1" in sim.vehicles["V1"].committed
