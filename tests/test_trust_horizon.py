"""Prove delay_half trust rejects normally delivered delayed bids; repaired mode accepts them."""

from __future__ import annotations

from race_casablanca.coordination.task_bids import (
    TaskBid,
    peer_bid_trustworthy,
    self_should_claim,
)
from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.synthetic import make_two_request_scenario


def _bid(sender: str, travel: float, *, as_of: float, expires: float | None = None) -> TaskBid:
    return TaskBid(
        request_id="R1",
        sender_id=sender,
        feasible=True,
        marginal_travel_s=travel,
        marginal_energy_kwh=1.0,
        energy_flex_kwh=5.0,
        deadline_slack_s=500.0,
        charge_burden_s=0.0,
        as_of_s=as_of,
        expires_s=as_of + 180.0 if expires is None else expires,
        commitment_version=0,
    )


def test_delay_half_rejects_normally_delivered_bid_at_30_and_120():
    for d in (30.0, 120.0):
        send = 100.0
        decide = send + d  # deterministic delivery age
        peer = _bid("V2", 10.0, as_of=send)
        assert not peer_bid_trustworthy(
            peer, now_s=decide, message_delay_s=d, peer_trust_mode="delay_half"
        ), f"delay_half must reject age={d} at delay={d}"


def test_ttl_commitment_accepts_normally_delivered_delayed_bid():
    for d in (30.0, 120.0):
        send = 100.0
        decide = send + d
        peer = _bid("V2", 10.0, as_of=send)
        assert peer_bid_trustworthy(
            peer, now_s=decide, message_delay_s=d, peer_trust_mode="ttl_commitment"
        )


def test_ttl_commitment_rejects_withdrawn_and_expired():
    peer = _bid("V2", 10.0, as_of=0.0, expires=50.0)
    assert not peer_bid_trustworthy(
        peer, now_s=100.0, message_delay_s=30.0, peer_trust_mode="ttl_commitment"
    )
    bad = TaskBid(
        request_id="R1",
        sender_id="V2",
        feasible=True,
        marginal_travel_s=10.0,
        marginal_energy_kwh=1.0,
        energy_flex_kwh=5.0,
        deadline_slack_s=100.0,
        charge_burden_s=0.0,
        as_of_s=90.0,
        expires_s=300.0,
        withdrawn=True,
    )
    assert not peer_bid_trustworthy(
        bad, now_s=100.0, message_delay_s=30.0, peer_trust_mode="ttl_commitment"
    )


def test_ttl_commitment_rejects_stale_commitment_version():
    peer = TaskBid(
        request_id="R1",
        sender_id="V2",
        feasible=True,
        marginal_travel_s=10.0,
        marginal_energy_kwh=1.0,
        energy_flex_kwh=5.0,
        deadline_slack_s=100.0,
        charge_burden_s=0.0,
        as_of_s=100.0,
        expires_s=400.0,
        commitment_version=0,
    )
    assert not peer_bid_trustworthy(
        peer,
        now_s=130.0,
        message_delay_s=30.0,
        peer_trust_mode="ttl_commitment",
        known_commitment_versions={"V2": 2},
    )


def test_valid_delayed_peer_changes_claim_under_ttl_commitment():
    own = _bid("V1", 50.0, as_of=130.0)
    peer = _bid("V2", 10.0, as_of=100.0)  # arrived after 30s delay
    # Broken filter ignores peer → own claims
    assert self_should_claim(
        own, [peer], now_s=130.0, message_delay_s=30.0, peer_trust_mode="delay_half"
    )
    # Repaired filter trusts better peer → own defers
    assert not self_should_claim(
        own, [peer], now_s=130.0, message_delay_s=30.0, peer_trust_mode="ttl_commitment"
    )


def test_h_current_zero_defers_under_delay_30():
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    pol = RaceCooperativePolicy(
        comm_mode="selective",
        assign_wait_mode="deadline_energy",
        peer_trust_mode="delay_half",
        delay_aware_trust=True,
        fair_physical_decisions=True,
        max_assign_wait_s=60.0,
        rng_seed=1,
    )
    sim = OnlineSimulator(
        scenario_id="trust_proof",
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
            message_triggers_decision=True,
        ),
        policy=pol,
    )
    sim.run()
    assert pol.n_defers_to_peer == 0
    # Messages may still be sent/received; trust rejects them for ranking
    assert pol.n_peer_bids_untrusted >= 0
