"""Unit tests for RACE-CERT interval certification (heuristic)."""

from __future__ import annotations

from race_casablanca.coordination.certifying_protocol import (
    certify_assignment,
    certified_should_send,
    interval_from_bid,
)
from race_casablanca.coordination.selective_protocol import BidMemory
from race_casablanca.coordination.task_bids import TaskBid


def _bid(sender: str, travel: float, *, as_of: float = 100.0, feas: bool = True) -> TaskBid:
    return TaskBid(
        request_id="R1",
        sender_id=sender,
        feasible=feas,
        marginal_travel_s=travel,
        marginal_energy_kwh=1.0,
        energy_flex_kwh=5.0,
        deadline_slack_s=100.0,
        charge_burden_s=0.0,
        as_of_s=as_of,
        expires_s=as_of + 180.0,
        cost_L_s=travel if feas else None,
        cost_U_s=travel if feas else None,
        race_cert="heuristic_interval_v1",
    )


def test_singleton_feasible_is_certified():
    own = _bid("V1", 50.0)
    cert = certify_assignment(own, [], now_s=100.0)
    assert cert.certified and cert.winner_id == "V1"


def test_interval_dominance_certifies_clear_winner():
    own = _bid("V1", 40.0)
    peer = _bid("V2", 200.0, as_of=100.0)  # fresh; widen still leaves L_peer >> 40
    cert = certify_assignment(own, [peer], now_s=100.0)
    assert cert.certified
    assert cert.winner_id == "V1"
    assert cert.reason == "interval_dominance"


def test_overlapping_costs_not_certified():
    own = _bid("V1", 100.0)
    peer = _bid("V2", 101.0, as_of=100.0)
    cert = certify_assignment(own, [peer], now_s=100.0)
    assert not cert.certified
    assert cert.reason == "overlapping_intervals"


def test_incomplete_peer_coverage_forces_fallback():
    own = _bid("V1", 50.0)
    cert = certify_assignment(own, [], now_s=100.0, n_announced_peers=2)
    assert not cert.certified
    assert cert.reason == "incomplete_peer_coverage"


def test_certified_suppress_for_clear_loser():
    own = _bid("V2", 300.0)
    peer = _bid("V1", 40.0, as_of=100.0)
    mem = BidMemory(bid=own, send_s=90.0)
    send, kind, cert = certified_should_send(own, [peer], mem, now_s=100.0, n_announced_peers=1)
    assert cert.certified
    assert cert.winner_id == "V1"
    assert send is False
    assert kind == "certified_suppress"


def test_self_interval_is_point():
    own = _bid("V1", 12.5, as_of=50.0)
    iv = interval_from_bid(own, now_s=50.0, is_self=True)
    assert iv.L == iv.U == 12.5
    assert iv.certified_source == "self_exact"
