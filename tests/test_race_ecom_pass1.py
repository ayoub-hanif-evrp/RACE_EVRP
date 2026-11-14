"""PASS1 correctness: roster coverage, silent competitor, delayed full, matched budget."""

from __future__ import annotations

from race_casablanca.coordination.certifying_protocol import certify_assignment
from race_casablanca.coordination.race_ecom import ecom_should_send, roster_competitor_count
from race_casablanca.coordination.selective_protocol import MatchedBudgetController
from race_casablanca.coordination.task_bids import TaskBid
from race_casablanca.sim.policy_api import build_restricted_observation
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.environment import OnlineSimulator, SimConfig


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
    )


def test_public_fleet_roster_on_restricted_obs():
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    sim = OnlineSimulator(
        scenario_id="roster",
        graph=sc["graph"],
        model=sc["model"],
        requests=sc["requests"],
        fleet=sc["fleet"],
        depot_node=sc["depot_node"],
        shift_start_s=sc["shift_start_s"],
        shift_end_s=sc["shift_end_s"],
        config=SimConfig(info_mode="restricted", n_vehicles=3, seed=0),
        policy=None,
    )
    obs = build_restricted_observation(sim, "V1")
    assert obs.fleet_vehicle_ids == ("V1", "V2", "V3")
    assert len(obs.peers) == 0  # no state floods yet
    assert roster_competitor_count(obs.fleet_vehicle_ids, "V1") == 2


def test_silent_best_competitor_blocks_false_certification():
    """V1 has a bid; silent V2 is best but unknown → must NOT certify V1 as unique winner."""

    own = _bid("V1", 50.0)
    # No peer bids, but roster says 2 competitors exist
    cert = certify_assignment(own, [], now_s=100.0, n_announced_peers=2)
    assert not cert.certified
    assert cert.reason == "incomplete_peer_coverage"
    dec = ecom_should_send(
        own, [], None, now_s=100.0, fleet_vehicle_ids=("V1", "V2", "V3")
    )
    # Initial still sends (need representation) but status is fallback, not proved
    assert dec.send is True
    assert dec.status in {"fallback", "heuristic"}


def test_matched_budget_charges_recipient_fanout():
    ctrl = MatchedBudgetController(budget=10, n_recipients=2)
    rng = __import__("random").Random(0)
    allows = 0
    for _ in range(100):
        if ctrl.allow(rng, n_candidates=5):
            allows += 1
    # Each allow costs 2 → at most 5 allows
    assert allows <= 5
    assert ctrl.sent <= 10


def test_delayed_full_completes_without_queue_blowup():
    from race_casablanca.policies import RaceCooperativePolicy

    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    pol = RaceCooperativePolicy(comm_mode="full", rng_seed=1)
    sim = OnlineSimulator(
        scenario_id="delay_full",
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
            message_triggers_decision=True,
            max_pending_bid_delivers=1,
        ),
        policy=pol,
    )
    m = sim.run()
    assert m.n_requests >= 1
    # Sanity: event queue drained; superseded counter may be >0 under delay
    assert sim.now_s >= sc["shift_end_s"] - 1e-6
