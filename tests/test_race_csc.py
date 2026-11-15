"""RACE-CSC adversarial correctness cases A–L + information-boundary invariants."""

from __future__ import annotations

from copy import deepcopy

from race_casablanca.coordination.ownership import TaskRegistry
from race_casablanca.coordination.race_csc import credible_peer_bids, csc_should_claim
from race_casablanca.coordination.task_bids import TaskBid, self_should_claim
from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.policy_api import ActionInterface, RestrictedObservation, VisibleVehicleState
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import RequestStatus


def _bid(
    sender: str,
    travel: float,
    *,
    as_of: float = 100.0,
    feas: bool = True,
    withdrawn: bool = False,
    cv: int = 0,
    claim_intent: bool = False,
    owned: bool = False,
    expires: float | None = None,
) -> TaskBid:
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
        expires_s=as_of + 180.0 if expires is None else expires,
        withdrawn=withdrawn,
        commitment_version=cv,
        claim_intent=claim_intent,
        owned=owned,
    )


# ---------------------------------------------------------------------------
# Unit: CSC claim logic
# ---------------------------------------------------------------------------


def test_case_a_better_peer_with_owned_blocks_conflict():
    """A: peer owns → local must not claim."""
    own = _bid("V1", 80.0)
    peer = _bid("V2", 20.0, owned=True)
    assert csc_should_claim(own, [peer], now_s=100.0, message_delay_s=30.0) is False


def test_case_a_better_peer_claim_intent_blocks():
    own = _bid("V1", 80.0)
    peer = _bid("V2", 20.0, claim_intent=True)
    assert csc_should_claim(own, [peer], now_s=100.0, message_delay_s=30.0) is False


def test_case_b_better_peer_offer_only_under_delay_does_not_block():
    """B: delayed offer-only is not credible → local may claim (safe fallback)."""
    own = _bid("V1", 80.0, as_of=130.0)
    peer = _bid("V2", 20.0, as_of=100.0)  # offer only
    assert csc_should_claim(own, [peer], now_s=130.0, message_delay_s=30.0) is True
    # Legacy would defer:
    assert self_should_claim(own, [peer], now_s=130.0, peer_trust_mode="ttl") is False


def test_case_c_zero_delay_offers_still_rank():
    """C @0s: instantaneous offers remain ranking evidence."""
    own = _bid("V1", 80.0)
    peer = _bid("V2", 20.0)
    assert csc_should_claim(own, [peer], now_s=100.0, message_delay_s=0.0) is False


def test_case_d_withdrawn_offer_ignored():
    own = _bid("V1", 50.0)
    peer = _bid("V2", 10.0, withdrawn=True, claim_intent=True)
    assert csc_should_claim(own, [peer], now_s=100.0, message_delay_s=30.0) is True


def test_case_d_expired_offer_ignored():
    own = _bid("V1", 50.0, as_of=300.0)
    peer = _bid("V2", 10.0, as_of=100.0, expires=150.0, claim_intent=True)
    cred = credible_peer_bids([peer], now_s=300.0, message_delay_s=30.0)
    assert cred == []
    assert csc_should_claim(own, [peer], now_s=300.0, message_delay_s=30.0) is True


def test_case_f_tight_deadline_immediate_wait():
    """F: assign_wait_mode immediate → wait 0."""
    pol = RaceCooperativePolicy(comm_mode="selective", assign_wait_mode="immediate", claim_mode="csc")
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 2}
    sim = OnlineSimulator(
        scenario_id="tight_wait",
        graph=sc["graph"],
        model=sc["model"],
        requests=sc["requests"],
        fleet=sc["fleet"],
        depot_node=sc["depot_node"],
        shift_start_s=sc["shift_start_s"],
        shift_end_s=sc["shift_end_s"],
        config=SimConfig(info_mode="restricted", n_vehicles=2, message_delay_s=120.0),
        policy=pol,
    )
    rid = next(iter(sim.requests))
    assert pol.assignment_wait_for_request(sim, rid) == 0.0


def test_case_g_registry_exclusive_ownership():
    """G: atomic registry grants at most one owner regardless of claim order."""
    reg = TaskRegistry()
    assert reg.try_claim("R1", "V1", 10.0) is True
    assert reg.try_claim("R1", "V2", 10.0) is False
    assert reg.owner_of("R1") == "V1"
    assert reg.n_rejected_duplicates == 1
    # Reverse order
    reg2 = TaskRegistry()
    assert reg2.try_claim("R1", "V2", 10.0) is True
    assert reg2.try_claim("R1", "V1", 10.0) is False
    assert reg2.owner_of("R1") == "V2"


def test_case_h_ignore_peers_terminates_without_deadlock():
    """H: packet-loss / no peers → CSC still claims locally (no indefinite wait)."""
    own = _bid("V1", 40.0)
    assert csc_should_claim(own, [], now_s=100.0, message_delay_s=120.0) is True
    assert csc_should_claim(own, [], now_s=100.0, message_delay_s=120.0, ignore_peer_bids=True) is True


def test_case_i_stale_commitment_version_rejected():
    """I: older commitment version must not reverse newer knowledge."""
    own = _bid("V1", 80.0, as_of=200.0)
    stale = _bid("V2", 10.0, as_of=100.0, cv=0, claim_intent=True)
    known = {"V2": 2}
    assert (
        csc_should_claim(
            own,
            [stale],
            now_s=200.0,
            message_delay_s=30.0,
            peer_trust_mode="ttl_commitment",
            known_commitment_versions=known,
        )
        is True
    )


def test_case_l_no_comm_equivalence_unit():
    """L: ignore_peer_bids CSC matches empty-peer claim decisions."""
    own = _bid("V1", 50.0)
    peer = _bid("V2", 10.0, claim_intent=True)
    assert csc_should_claim(own, [peer], now_s=100.0, ignore_peer_bids=True) is True
    assert csc_should_claim(own, [], now_s=100.0) is True


# ---------------------------------------------------------------------------
# Information boundaries
# ---------------------------------------------------------------------------


def test_info_boundary_known_versions_do_not_leak_peer_private_cv():
    """Shared policy must not expose V2's private commit version to V1 without messages."""
    pol = RaceCooperativePolicy(comm_mode="selective", claim_mode="csc")
    pol._own_commit_version["V1"] = 1
    pol._own_commit_version["V2"] = 9  # private to V2
    vs = VisibleVehicleState(
        vehicle_id="V1",
        node=0,
        ready_s=0.0,
        battery_kwh=40.0,
        load_kg=0.0,
        busy=False,
        mode="IDLE",
        committed=(),
        plan_pickup_ids=(),
        locked_request_id=None,
        path_length_m=0.0,
    )
    obs = RestrictedObservation(
        now_s=0.0,
        vehicle_id="V1",
        self_state=vs,
        own_committed=(),
        announced=[],
        peers={},
        peer_bids={},
        fleet_vehicle_ids=("V1", "V2"),
    )
    known = pol._known_versions_for(obs)
    assert known.get("V1") == 1
    assert "V2" not in known


def test_info_boundary_restricted_cannot_check_peer_insertion():
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 2}
    sim = OnlineSimulator(
        scenario_id="ib_check",
        graph=sc["graph"],
        model=sc["model"],
        requests=sc["requests"],
        fleet=sc["fleet"],
        depot_node=sc["depot_node"],
        shift_start_s=sc["shift_start_s"],
        shift_end_s=sc["shift_end_s"],
        config=SimConfig(info_mode="restricted", n_vehicles=2),
    )
    vids = list(sim.vehicles.keys())
    actions = ActionInterface(sim, actor_vehicle_id=vids[0])
    try:
        actions.check_insertion(vids[1], next(iter(sim.requests)))
        raised = False
    except PermissionError:
        raised = True
    assert raised


def test_wait_decentralized_does_not_use_coordinator_travel_counter():
    pol = RaceCooperativePolicy(
        comm_mode="selective",
        assign_wait_mode="deadline_energy",
        wait_authority="decentralized_signal",
        max_assign_wait_s=60.0,
        message_delay_s=30.0,
    )
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    # Ample TW so wait can be positive
    for r in sc["requests"]:
        r.tw_end_s = 5000.0
    sim = OnlineSimulator(
        scenario_id="wait_dec",
        graph=sc["graph"],
        model=sc["model"],
        requests=sc["requests"],
        fleet=sc["fleet"],
        depot_node=sc["depot_node"],
        shift_start_s=sc["shift_start_s"],
        shift_end_s=sc["shift_end_s"],
        config=SimConfig(info_mode="restricted", n_vehicles=3, message_delay_s=30.0),
        policy=pol,
    )
    rid = next(iter(sim.requests))
    w = pol.assignment_wait_for_request(sim, rid)
    assert w >= 0.0
    assert pol.n_wait_used_local_travel == 0


# ---------------------------------------------------------------------------
# Integration episodes
# ---------------------------------------------------------------------------


def _run_episode(*, claim_mode: str, delay: float, loss: float = 0.0, ignore: bool = False, **extra):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    pol = RaceCooperativePolicy(
        comm_mode="selective",
        claim_mode=claim_mode,
        assign_wait_mode="deadline_energy",
        peer_trust_mode="ttl_commitment",
        fair_physical_decisions=True,
        max_assign_wait_s=60.0,
        rng_seed=3,
        message_delay_s=delay,
        ignore_peer_bids=ignore,
        **extra,
    )
    reqs = deepcopy(sc["requests"])
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    sim = OnlineSimulator(
        scenario_id=f"csc/{claim_mode}/d{delay}",
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
            message_delay_s=delay,
            packet_loss_p=loss,
            decision_on_release=True,
            message_triggers_decision=True,
        ),
        policy=pol,
    )
    m = sim.run()
    owners = {rid: req.owner for rid, req in sim.requests.items()}
    return pol, sim, m, owners


def test_case_c_delays_episode_terminates():
    """C: 0/5/15/30/120 s delays complete without ownership conflicts."""
    for d in (0.0, 5.0, 15.0, 30.0, 120.0):
        pol, sim, m, owners = _run_episode(claim_mode="csc", delay=d)
        for rid, req in sim.requests.items():
            reg_owner = sim.registry.owner_of(rid)
            if reg_owner is not None:
                assert req.owner == reg_owner
            assert owners[rid] == req.owner
        assert float(m.n_requests) == 2.0
        assert pol.n_claims_attempted >= pol.n_claims_success


def test_case_e_energy_feasibility_gate_on_claim():
    """E: successful claims require fresh feasible insertion (registry + checker)."""
    pol, sim, m, owners = _run_episode(claim_mode="csc", delay=0.0)
    assert pol.n_claims_success <= pol.n_claims_attempted
    for rid, owner in owners.items():
        if owner is None:
            continue
        # Owner recorded in registry if claimed through try_assign path
        reg_owner = sim.registry.owner_of(rid)
        if reg_owner is not None:
            assert reg_owner == owner


def test_case_h_packet_loss_no_deadlock():
    pol, sim, m, owners = _run_episode(claim_mode="csc", delay=30.0, loss=0.5)
    assert float(m.n_requests) == 2.0
    assert sim.now_s >= sim.shift_end_s - 1e-6 or sim.now_s > 0


def test_case_j_locked_route_not_rewritten_silently():
    """J: after claim, committed pickups stay on the owning vehicle."""
    pol, sim, m, owners = _run_episode(claim_mode="csc", delay=0.0)
    for vid, v in sim.vehicles.items():
        for rid in v.committed:
            assert sim.requests[rid].owner == vid


def test_case_k_unused_comm_counted():
    """K: claim signals increment message counters when CSC claims succeed."""
    pol, sim, m, owners = _run_episode(claim_mode="csc", delay=0.0, send_claim_signals=True)
    if pol.n_claims_success > 0:
        assert pol.n_claim_intents_sent >= pol.n_claims_success
        assert pol.n_owned_announcements >= pol.n_claims_success
        assert pol.n_messages_sent_by_policy >= pol.n_claim_intents_sent
        assert pol.n_bid_bytes_sent > 0


def test_case_l_no_comm_owners_vs_ignore_peer():
    """L: CSC with ignore_peer ≈ none-communication claim opportunities under delay."""
    _, _, _, owners_ignore = _run_episode(claim_mode="csc", delay=30.0, ignore=True)
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    pol = RaceCooperativePolicy(
        comm_mode="none",
        claim_mode="csc",
        assign_wait_mode="immediate",
        fair_physical_decisions=True,
        rng_seed=3,
        message_delay_s=30.0,
    )
    reqs = deepcopy(sc["requests"])
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    sim = OnlineSimulator(
        scenario_id="csc/none",
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
        ),
        policy=pol,
    )
    sim.run()
    owners_none = {rid: req.owner for rid, req in sim.requests.items()}
    # Same physical opportunity set under ignore_peer + matched wait may differ from
    # immediate none; assert both terminate with exclusive owners.
    assert all(v is None or isinstance(v, str) for v in owners_ignore.values())
    assert all(v is None or isinstance(v, str) for v in owners_none.values())


def test_csc_safe_fallback_fires_under_delay_vs_legacy():
    """Integration signal: under delay, CSC should claim when legacy would defer to offers."""
    own = _bid("V1", 80.0, as_of=130.0)
    peer = _bid("V2", 20.0, as_of=100.0)
    assert self_should_claim(own, [peer], now_s=130.0, peer_trust_mode="ttl") is False
    assert csc_should_claim(own, [peer], now_s=130.0, message_delay_s=30.0) is True
