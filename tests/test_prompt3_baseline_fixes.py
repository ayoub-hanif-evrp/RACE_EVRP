"""Prompt 3: corrected random byte-matching and periodic task-bid baselines."""

from __future__ import annotations

import random
from copy import deepcopy

from race_casablanca.coordination.selective_protocol import MatchedByteBudgetController
from race_casablanca.policies.race_cooperative import INFO_ONLY_REASONS, RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import RequestStatus


def test_byte_budget_uses_actual_payload_and_fanout():
    rng = random.Random(0)
    ctrl = MatchedByteBudgetController(budget_bytes=1000.0, n_recipients=2, typical_payload_bytes=9999.0)
    assert ctrl.allow(rng, n_candidates=1, payload_bytes=100.0) is True
    assert abs(ctrl.used_bytes - 200.0) < 1e-9
    ctrl2 = MatchedByteBudgetController(budget_bytes=150.0, n_recipients=2)
    assert ctrl2.allow(random.Random(1), 1, payload_bytes=100.0) is False


def test_byte_budget_reproducible_under_seed():
    rng_a = random.Random(3)
    rng_b = random.Random(3)
    ca = MatchedByteBudgetController(budget_bytes=800.0, n_recipients=2)
    cb = MatchedByteBudgetController(budget_bytes=800.0, n_recipients=2)
    seq_a = [ca.allow(rng_a, 3, payload_bytes=40.0) for _ in range(10)]
    seq_b = [cb.allow(rng_b, 3, payload_bytes=40.0) for _ in range(10)]
    assert seq_a == seq_b
    assert abs(ca.used_bytes - cb.used_bytes) < 1e-12


def test_random_matched_bytes_positive_and_tracks_attempted():
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    pol = RaceCooperativePolicy(
        comm_mode="random_matched_bytes",
        matched_byte_budget=1e9,
        typical_payload_bytes=400.0,
        matched_n_recipients=2,
        claim_mode="legacy",
        fair_physical_decisions=True,
        rng_seed=1,
        enable_readiness_charge=False,
    )
    reqs = deepcopy(sc["requests"])
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    sim = OnlineSimulator(
        scenario_id="p3/bytes",
        graph=sc["graph"],
        model=sc["model"],
        requests=reqs,
        fleet=sc["fleet"],
        depot_node=sc["depot_node"],
        shift_start_s=sc["shift_start_s"],
        shift_end_s=sc["shift_end_s"],
        config=SimConfig(
            info_mode="restricted",
            n_vehicles=3,
            seed=0,
            message_delay_s=0.0,
            decision_on_release=True,
        ),
        policy=pol,
    )
    sim.run()
    assert sim.n_bid_attempted_messages > 0
    assert sim.n_bid_attempted_bytes > 0
    assert pol._matched_bytes is not None
    assert pol._matched_bytes.used_bytes > 0
    assert pol._matched_bytes.used_bytes <= float(sim.n_bid_attempted_bytes) + 1.0


def test_tiny_budget_cannot_exceed():
    ctrl = MatchedByteBudgetController(budget_bytes=50.0, n_recipients=2)
    assert ctrl.allow(random.Random(0), 1, payload_bytes=40.0) is False
    assert ctrl.used_bytes == 0.0


def test_periodic_300s_fires_and_sends_positive_bytes():
    class CommOnlyPeriodic(RaceCooperativePolicy):
        def _claim_pass(self, obs, actions, own_bids):  # noqa: ANN001
            return None

    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    for r in sc["requests"]:
        r.tw_end_s = 7200.0
        r.release_s = 0.0 if r.request_id == "R1" else 10.0
    pol = CommOnlyPeriodic(
        comm_mode="periodic",
        claim_mode="legacy",
        fair_physical_decisions=True,
        enable_readiness_charge=False,
        rng_seed=1,
        assign_wait_mode="immediate",
    )
    reqs = deepcopy(sc["requests"])
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    sim = OnlineSimulator(
        scenario_id="p3/periodic",
        graph=sc["graph"],
        model=sc["model"],
        requests=reqs,
        fleet=sc["fleet"],
        depot_node=sc["depot_node"],
        shift_start_s=0.0,
        shift_end_s=8 * 3600.0,
        config=SimConfig(
            info_mode="restricted",
            n_vehicles=3,
            seed=0,
            message_delay_s=0.0,
            periodic_broadcast_s=300.0,
            periodic_state_broadcast=False,
            decision_on_release=True,
            message_triggers_decision=True,
        ),
        policy=pol,
    )
    assert float(sim.config.periodic_broadcast_s) == 300.0
    n_periodic_scheduled = sum(
        1 for ev in sim._eq if getattr(ev, "type", None) and ev.type.name == "PERIODIC_BROADCAST"
    )
    assert n_periodic_scheduled >= 90
    m = sim.run()
    assert float(m.n_requests) == 2.0
    assert sim.n_bid_attempted_bytes > 0
    assert pol.n_info_only_decisions >= 1
    assert sim.now_s >= sim.shift_end_s - 1.0


def test_periodic_does_not_grant_extra_physical_claims_via_tick():
    assert "periodic_broadcast" in INFO_ONLY_REASONS


def test_periodic_respects_packet_loss_accounting():
    class CommOnlyPeriodic(RaceCooperativePolicy):
        def _claim_pass(self, obs, actions, own_bids):  # noqa: ANN001
            return None

    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    for r in sc["requests"]:
        r.tw_end_s = 7200.0
    pol = CommOnlyPeriodic(
        comm_mode="periodic",
        fair_physical_decisions=True,
        enable_readiness_charge=False,
        rng_seed=2,
    )
    reqs = deepcopy(sc["requests"])
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    sim = OnlineSimulator(
        scenario_id="p3/per_loss",
        graph=sc["graph"],
        model=sc["model"],
        requests=reqs,
        fleet=sc["fleet"],
        depot_node=sc["depot_node"],
        shift_start_s=0.0,
        shift_end_s=sc["shift_end_s"],
        config=SimConfig(
            info_mode="restricted",
            n_vehicles=3,
            seed=0,
            message_delay_s=5.0,
            packet_loss_p=1.0,
            periodic_broadcast_s=300.0,
            periodic_state_broadcast=False,
            decision_on_release=True,
        ),
        policy=pol,
    )
    sim.run()
    assert sim.n_bid_attempted_bytes > 0
    assert sim.n_bid_delivered_bytes == 0
    assert sim.n_bid_dropped_bytes == sim.n_bid_attempted_bytes
