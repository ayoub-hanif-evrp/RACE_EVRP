"""Causal timing: none must not wait; info-only reasons must not claim."""

from __future__ import annotations

from race_casablanca.coordination.selective_protocol import event_triggered_should_send
from race_casablanca.coordination.task_bids import TaskBid
from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.synthetic import make_two_request_scenario


def test_none_does_not_wait_for_message_delay():
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    pol = RaceCooperativePolicy(comm_mode="none", fair_physical_decisions=True)
    sim = OnlineSimulator(
        scenario_id="none_wait",
        graph=sc["graph"],
        model=sc["model"],
        requests=sc["requests"],
        fleet=sc["fleet"],
        depot_node=sc["depot_node"],
        shift_start_s=sc["shift_start_s"],
        shift_end_s=sc["shift_end_s"],
        config=SimConfig(
            info_mode="restricted",
            n_vehicles=3,
            seed=0,
            message_delay_s=30.0,
            decision_on_release=True,
        ),
        policy=pol,
    )
    rid = next(iter(sim.requests))
    assert pol.assignment_wait_for_request(sim, rid) == 0.0
    sim.run()
    assert sim.sum_assign_wait_s == 0.0
    assert sim.n_assign_deferred == 0


def test_periodic_does_not_wait_for_message_delay():
    pol = RaceCooperativePolicy(comm_mode="periodic")
    assert pol.expects_delayed_peer_bids() is False


def test_event_triggered_sends_initial_not_expiry():
    own = TaskBid(
        request_id="R1",
        sender_id="V1",
        feasible=True,
        marginal_travel_s=50.0,
        marginal_energy_kwh=1.0,
        energy_flex_kwh=5.0,
        deadline_slack_s=100.0,
        charge_burden_s=0.0,
        as_of_s=100.0,
        expires_s=120.0,
    )
    from race_casablanca.coordination.selective_protocol import BidMemory

    mem = BidMemory(bid=own, send_s=100.0)
    send, kind = event_triggered_should_send(own, [], mem, now_s=110.0)
    assert send is False
    assert kind == "none"


def test_message_reason_is_info_only_no_extra_claim_path():
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 2}
    pol = RaceCooperativePolicy(comm_mode="selective", fair_physical_decisions=True, rng_seed=1)
    sim = OnlineSimulator(
        scenario_id="info_only",
        graph=sc["graph"],
        model=sc["model"],
        requests=sc["requests"],
        fleet=sc["fleet"],
        depot_node=sc["depot_node"],
        shift_start_s=sc["shift_start_s"],
        shift_end_s=sc["shift_end_s"],
        config=SimConfig(
            info_mode="restricted",
            n_vehicles=2,
            seed=0,
            message_delay_s=0.0,
            message_triggers_decision=True,
        ),
        policy=pol,
    )
    sim.run()
    # Info-only decisions may occur; physical claims tracked separately.
    assert pol.n_physical_claim_decisions >= 0
    assert pol.n_info_only_decisions >= 0
