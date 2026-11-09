"""Milestone-1 protocol repairs: expiry trigger, async wait, packet loss, supersession."""

from __future__ import annotations

from race_casablanca.coordination.selective_protocol import BidMemory, selective_should_send
from race_casablanca.coordination.task_bids import TaskBid, assignment_wait_s
from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.policy_api import TaskAnnouncement
from race_casablanca.sim.synthetic import make_two_request_scenario


def _bid(**kwargs) -> TaskBid:
    base = dict(
        request_id="R1",
        sender_id="V1",
        feasible=True,
        marginal_travel_s=100.0,
        marginal_energy_kwh=1.0,
        energy_flex_kwh=5.0,
        deadline_slack_s=600.0,
        charge_burden_s=0.0,
        as_of_s=0.0,
        expires_s=100.0,
        seq=1,
        commitment_version=0,
    )
    base.update(kwargs)
    return TaskBid(**base)


def test_selective_expiry_uses_transmitted_bid_not_new_bid():
    mem = BidMemory(bid=_bid(expires_s=50.0), send_s=0.0)
    # Newly computed bid has far-future expiry; trigger must still fire from memory.
    own = _bid(expires_s=10_000.0)
    send, kind = selective_should_send(own, [], mem, now_s=40.0, refresh_before_expiry_s=45.0)
    assert send is True
    assert kind == "expiry_refresh"


def test_assignment_wait_zero_when_urgent_or_zero_delay():
    task = TaskAnnouncement("R1", 1, 0.0, 200.0, 60.0, 5.0)
    assert assignment_wait_s(task, now_s=0.0, message_delay_s=0.0) == 0.0
    assert assignment_wait_s(task, now_s=50.0, message_delay_s=30.0, urgency_slack_s=180.0) == 0.0


def test_assignment_wait_positive_when_slack_allows():
    task = TaskAnnouncement("R1", 1, 0.0, 3600.0, 60.0, 5.0)
    w = assignment_wait_s(task, now_s=0.0, message_delay_s=30.0, max_wait_s=120.0, urgency_slack_s=180.0)
    assert 0.0 < w <= 120.0


def test_delayed_bid_assign_window_runs():
    base = make_two_request_scenario()
    pol = RaceCooperativePolicy(comm_mode="full", enable_readiness_charge=False, max_assign_wait_s=30.0)
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet={**base["fleet"], "n_vehicles": 2},
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(
            info_mode="restricted",
            seed=3,
            n_vehicles=2,
            message_delay_s=5.0,
            periodic_state_broadcast=False,
        ),
        policy=pol,
    )
    m = sim.run()
    assert m.n_requests >= 1
    assert pol.n_messages_sent_by_policy >= 0


def test_packet_loss_can_drop_bids():
    base = make_two_request_scenario()
    pol = RaceCooperativePolicy(comm_mode="full", enable_readiness_charge=False)
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet={**base["fleet"], "n_vehicles": 2},
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(
            info_mode="restricted",
            seed=4,
            n_vehicles=2,
            message_delay_s=0.0,
            packet_loss_p=1.0,
            packet_loss_seed=99,
            periodic_state_broadcast=False,
        ),
        policy=pol,
    )
    sim.run()
    assert sim.n_packets_dropped > 0
    assert sim.n_bid_messages == 0
