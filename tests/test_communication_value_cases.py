"""Deterministic cases: when delayed peer info should/shouldn't change ownership."""

from __future__ import annotations

from race_casablanca.coordination.task_bids import TaskBid, self_should_claim
from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.synthetic import make_two_request_scenario


def _bid(sender, travel, *, as_of, feas=True, withdrawn=False, cv=0):
    return TaskBid(
        request_id="R1",
        sender_id=sender,
        feasible=feas,
        marginal_travel_s=travel,
        marginal_energy_kwh=1.0,
        energy_flex_kwh=5.0,
        deadline_slack_s=200.0,
        charge_burden_s=0.0,
        as_of_s=as_of,
        expires_s=as_of + 180.0,
        withdrawn=withdrawn,
        commitment_version=cv,
    )


def test_case1_valid_delayed_bid_assigns_better_ev():
    """Better peer arrives after delay; ttl_commitment defers; delay_half would wrongly claim."""
    own = _bid("V1", 80.0, as_of=130.0)
    peer = _bid("V2", 20.0, as_of=100.0)
    assert self_should_claim(own, [peer], now_s=130.0, peer_trust_mode="ttl_commitment") is False
    assert self_should_claim(own, [peer], now_s=130.0, message_delay_s=30.0, peer_trust_mode="delay_half") is True


def test_case2_withdrawn_stale_bid_ignored():
    own = _bid("V1", 50.0, as_of=130.0)
    peer = _bid("V2", 10.0, as_of=100.0, withdrawn=True)
    assert self_should_claim(own, [peer], now_s=130.0, peer_trust_mode="ttl_commitment") is True


def test_case3_no_peer_immediate_claim():
    own = _bid("V1", 50.0, as_of=100.0)
    assert self_should_claim(own, [], now_s=100.0, peer_trust_mode="ttl_commitment") is True


def test_case4_infeasible_own_does_not_claim_even_if_nearest():
    own = _bid("V1", 5.0, as_of=100.0, feas=False)
    peer = _bid("V2", 50.0, as_of=100.0)
    assert self_should_claim(own, [peer], now_s=100.0, peer_trust_mode="ttl_commitment") is False


def test_case5_executed_h_current_matches_no_peer_owners_under_delay():
    """Under 30s delay, broken trust ⇒ H_CURRENT ownership equals ignore-peers."""
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}

    def run2(trust_mode: str, ignore: bool = False):
        from copy import deepcopy

        from race_casablanca.sim.types import RequestStatus

        pol = RaceCooperativePolicy(
            comm_mode="selective",
            assign_wait_mode="deadline_energy",
            peer_trust_mode=trust_mode,
            ignore_peer_bids=ignore,
            delay_aware_trust=(trust_mode == "delay_half"),
            fair_physical_decisions=True,
            max_assign_wait_s=60.0,
            rng_seed=3,
            message_delay_s=30.0,
        )
        reqs = deepcopy(sc["requests"])
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        sim = OnlineSimulator(
            scenario_id=f"commval/{trust_mode}",
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
                message_delay_s=30.0,
                decision_on_release=True,
                message_triggers_decision=True,
            ),
            policy=pol,
        )
        m = sim.run()
        owners = {rid: req.owner for rid, req in sim.requests.items()}
        return {
            "owners": owners,
            "defers": pol.n_defers_to_peer,
            "trusted": pol.n_peer_bids_trusted,
            "ot": float(m.on_time_rate_all),
        }

    cur = run2("delay_half")
    nop = run2("ttl_commitment", ignore=True)
    val = run2("ttl_commitment")
    assert cur["defers"] == 0
    assert cur["owners"] == nop["owners"]
    assert val["ot"] >= 0.0

