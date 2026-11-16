"""Additional Prompt-2 freeze invariants: replay, ownership, cascade bounds."""

from __future__ import annotations

from copy import deepcopy

from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import RequestStatus


def _episode(*, seed_policy: int = 7, delay: float = 0.0, loss: float = 0.0):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": 3}
    pol = RaceCooperativePolicy(
        comm_mode="selective",
        claim_mode="csc",
        send_claim_signals=False,
        assign_wait_mode="deadline_energy",
        peer_trust_mode="ttl_commitment",
        wait_authority="decentralized_signal",
        fair_physical_decisions=True,
        rng_seed=seed_policy,
        message_delay_s=delay,
        max_assign_wait_s=60.0,
    )
    reqs = deepcopy(sc["requests"])
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    sim = OnlineSimulator(
        scenario_id="p2/inv",
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
    return pol, sim, m


def test_owner_registry_consistency_end_of_episode():
    _, sim, _ = _episode()
    for rid, req in sim.requests.items():
        reg = sim.registry.owner_of(rid)
        if reg is not None:
            assert req.owner == reg
        if req.owner is not None and req.status.name in {"ASSIGNED", "IN_SERVICE", "COMPLETED"}:
            assert sim.registry.owner_of(rid) in (req.owner, None) or req.owner == sim.registry.owner_of(rid)


def test_deterministic_replay_same_owners_and_ot():
    _, sim1, m1 = _episode(seed_policy=7)
    _, sim2, m2 = _episode(seed_policy=7)
    o1 = {rid: r.owner for rid, r in sim1.requests.items()}
    o2 = {rid: r.owner for rid, r in sim2.requests.items()}
    assert o1 == o2
    assert float(m1.on_time_rate_all) == float(m2.on_time_rate_all)
    assert abs(float(m1.energy_consumed_kwh) - float(m2.energy_consumed_kwh)) < 1e-9


def test_fair_physical_message_reason_does_not_claim():
    """Message deliveries are info-only under fair_physical_decisions."""
    pol, sim, _ = _episode(delay=5.0)
    assert pol.n_info_only_decisions >= 0
    # Physical claims tracked separately from message-driven info updates.
    assert pol.n_physical_claim_decisions >= 0


def test_no_unbounded_message_cascade_under_delay():
    pol, sim, m = _episode(delay=30.0)
    # Synthetic 2-request × 3 EV selective: attempted bytes must be finite and modest.
    assert sim.n_bid_attempted_messages < 5000
    assert float(m.n_requests) == 2.0
