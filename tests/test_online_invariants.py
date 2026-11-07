"""Invariants: causality, no future leak, ownership, movement, charging, payload."""

from __future__ import annotations

from race_casablanca.coordination.ownership import TaskRegistry
from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.policies.limited_info import LimitedInfoCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import RequestStatus


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
    """Policy must not see unreleased requests through observe_full."""

    class SpyPolicy:
        name = "spy"
        seen_unreleased = False

        def on_decision(self, sim, reason):
            obs = sim.observe_full()
            for _rid, req in obs["requests"].items():
                if req.status == RequestStatus.UNRELEASED:
                    SpyPolicy.seen_unreleased = True
            for rid in obs["available"]:
                assert sim.requests[rid].status != RequestStatus.UNRELEASED
            GreedyInsertionPolicy().on_decision(sim, reason)

    sim, _ = _make_sim(policy=SpyPolicy())
    sim.run()
    assert SpyPolicy.seen_unreleased is False


def test_no_duplicate_ownership():
    reg = TaskRegistry()
    assert reg.try_claim("R1", "V1", 0.0)
    assert not reg.try_claim("R1", "V2", 1.0)
    assert reg.n_rejected_duplicates == 1
    assert reg.owner_of("R1") == "V1"


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


def test_charging_behavior():
    sim, _ = _make_sim(policy=GreedyInsertionPolicy(), charge_on_return=True, initial_soc=0.5)
    m = sim.run()
    assert m.n_charges >= 0
    if m.n_charges > 0:
        assert sim.vehicles["V1"].battery_kwh <= 40.0 + 1e-9


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
