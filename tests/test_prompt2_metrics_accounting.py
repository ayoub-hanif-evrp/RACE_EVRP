"""Prompt 2: energy, decision runtime, and packet-loss communication accounting."""

from __future__ import annotations

from copy import deepcopy

from race_casablanca.policies.race_cooperative import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import RequestStatus


def _run(*, delay: float = 0.0, loss: float = 0.0, comm: str = "full", n_vehicles: int = 2):
    sc = make_two_request_scenario()
    sc["fleet"] = {**sc["fleet"], "n_vehicles": n_vehicles}
    pol = RaceCooperativePolicy(
        comm_mode=comm,
        claim_mode="csc",
        send_claim_signals=False,
        assign_wait_mode="deadline_energy",
        fair_physical_decisions=True,
        rng_seed=1,
        message_delay_s=delay,
        max_assign_wait_s=60.0,
    )
    reqs = deepcopy(sc["requests"])
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    sim = OnlineSimulator(
        scenario_id=f"p2/metrics/d{delay}/l{loss}",
        graph=sc["graph"],
        model=sc["model"],
        requests=reqs,
        fleet=sc["fleet"],
        depot_node=sc["depot_node"],
        shift_start_s=sc["shift_start_s"],
        shift_end_s=sc["shift_end_s"],
        config=SimConfig(
            info_mode="restricted",
            n_vehicles=n_vehicles,
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


def test_moving_ev_consumes_strictly_positive_energy():
    _, sim, m = _run(comm="none", n_vehicles=1)
    assert float(m.energy_consumed_kwh) > 0.0
    assert float(m.total_distance_m) > 0.0
    # Must not look up nonexistent total_energy_kwh
    d = m.to_dict()
    assert "energy_consumed_kwh" in d
    assert "total_energy_kwh" not in d or d.get("total_energy_kwh") is None


def test_decision_runtime_fields_populated():
    _, sim, m = _run(comm="selective")
    d = m.to_dict()
    assert int(d["n_decisions"]) > 0
    assert float(d["mean_decision_runtime_s"]) > 0.0
    assert float(d["p50_decision_runtime_s"]) > 0.0
    assert float(d["p95_decision_runtime_s"]) >= float(d["p50_decision_runtime_s"]) - 1e-12
    # Conversion used by experiment extractors
    assert 1000.0 * float(d["mean_decision_runtime_s"]) > 0.0


def test_packet_loss_0_attempted_equals_delivered_zero_delay():
    _, sim, m = _run(comm="full", loss=0.0, delay=0.0, n_vehicles=3)
    assert sim.n_bid_attempted_messages > 0
    assert sim.n_bid_attempted_bytes > 0
    assert sim.n_bid_dropped_messages == 0
    assert sim.n_bid_dropped_bytes == 0
    assert sim.n_bid_attempted_bytes == sim.n_bid_scheduled_bytes
    assert sim.n_bid_delivered_bytes == sim.n_bid_scheduled_bytes


def test_packet_loss_10_attempted_ge_delivered():
    _, sim, m = _run(comm="full", loss=0.10, delay=0.0, n_vehicles=3)
    assert sim.n_bid_attempted_bytes > 0
    assert sim.n_bid_attempted_bytes >= sim.n_bid_delivered_bytes
    assert sim.n_bid_dropped_bytes == sim.n_bid_attempted_bytes - sim.n_bid_scheduled_bytes


def test_packet_loss_100_attempted_positive_delivered_zero_no_deadlock():
    pol, sim, m = _run(comm="full", loss=1.0, delay=0.0, n_vehicles=3)
    assert sim.n_bid_attempted_bytes > 0
    assert sim.n_bid_delivered_bytes == 0
    assert sim.n_bid_dropped_bytes == sim.n_bid_attempted_bytes
    # Exclusive ownership / no crash
    for rid, req in sim.requests.items():
        reg = sim.registry.owner_of(rid)
        if reg is not None:
            assert req.owner == reg
    assert float(m.n_requests) == 2.0


def test_legacy_scheduled_counters_exclude_drops():
    """Historical n_bid_bytes must not include dropped frames."""
    _, sim, _ = _run(comm="full", loss=1.0, delay=0.0, n_vehicles=3)
    assert sim.n_bid_bytes == 0
    assert sim.n_bid_messages == 0
    assert sim.n_bid_attempted_bytes > 0
