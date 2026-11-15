"""Deadline/energy-aware assignment wait and stale-peer trust."""

from race_casablanca.coordination.task_bids import (
    TaskBid,
    assignment_wait_s,
    deadline_energy_assignment_wait_s,
    peer_bid_trustworthy,
    self_should_claim,
)
from race_casablanca.sim.policy_api import TaskAnnouncement


def _task(tw_end: float) -> TaskAnnouncement:
    return TaskAnnouncement("R1", 1, 0.0, tw_end, 60.0, 1.0)


def test_legacy_wait_scales_with_delay():
    t = _task(10_000.0)
    w = assignment_wait_s(
        t, now_s=0.0, message_delay_s=120.0, urgency_slack_s=180.0, max_wait_s=200.0
    )
    assert abs(w - 150.0) < 1e-6  # 1.25 * 120, under max_wait


def test_deadline_energy_commits_when_delay_eats_slack():
    t = _task(300.0)  # slack 300; delay 120 >= 0.35*300=105 → commit-now
    w = deadline_energy_assignment_wait_s(
        t,
        now_s=0.0,
        message_delay_s=120.0,
        urgency_slack_s=180.0,
        n_roster_competitors=2,
    )
    assert w == 0.0


def test_deadline_energy_brief_wait_when_slack_ample():
    t = _task(2000.0)
    w = deadline_energy_assignment_wait_s(
        t,
        now_s=0.0,
        message_delay_s=30.0,
        urgency_slack_s=180.0,
        max_wait_s=60.0,
        n_roster_competitors=2,
        n_fresh_peer_bids=0,
    )
    assert abs(w - 30.0) < 1e-6


def test_stale_peer_not_trusted_under_delay_half_mode():
    """Historical broken filter (delay_half) rejects age > 0.5*delay."""
    peer = TaskBid(
        request_id="R1",
        sender_id="V2",
        feasible=True,
        marginal_travel_s=10.0,
        marginal_energy_kwh=1.0,
        energy_flex_kwh=5.0,
        deadline_slack_s=100.0,
        charge_burden_s=0.0,
        as_of_s=0.0,
        expires_s=500.0,
    )
    assert not peer_bid_trustworthy(
        peer, now_s=100.0, message_delay_s=120.0, peer_trust_mode="delay_half"
    )
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
        expires_s=500.0,
    )
    # TTL mode: peer wins; delay_half ignores peer → own claims.
    assert not self_should_claim(own, [peer], now_s=100.0, peer_trust_mode="ttl")
    assert self_should_claim(
        own, [peer], now_s=100.0, message_delay_s=120.0, peer_trust_mode="delay_half"
    )
