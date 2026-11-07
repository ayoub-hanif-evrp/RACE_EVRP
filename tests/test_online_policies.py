"""Stage-2/2.1 baselines on the synthetic API."""

from __future__ import annotations

from race_casablanca.policies import (
    GreedyInsertionPolicy,
    LimitedInfoCooperativePolicy,
    RollingHorizonPolicy,
)
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.synthetic import make_two_request_scenario


def _run(policy, cfg: SimConfig, n_vehicles: int = 1):
    base = make_two_request_scenario()
    fleet = {**base["fleet"], "n_vehicles": n_vehicles}
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=fleet,
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=cfg,
        policy=policy,
    )
    return sim, sim.run()


def test_greedy_baseline_runs():
    sim, m = _run(GreedyInsertionPolicy(), SimConfig(info_mode="full", seed=0))
    assert m.policy == "greedy_insertion"
    assert m.n_served + m.n_expired + m.n_rejected == m.n_requests
    assert m.payload_violations == 0


def test_rolling_horizon_baseline_runs():
    _, m = _run(
        RollingHorizonPolicy(time_budget_s=0.05, reoptimize_every_s=0.0),
        SimConfig(info_mode="full", seed=0),
    )
    assert m.policy == "rolling_horizon_lns"
    assert m.n_decisions >= 1


def test_limited_info_baseline_runs():
    sim, m = _run(
        LimitedInfoCooperativePolicy(broadcast_period_s=5.0),
        SimConfig(info_mode="restricted", message_delay_s=5.0, seed=0, n_vehicles=2),
        n_vehicles=2,
    )
    assert m.policy == "limited_info_cooperative"
    assert m.info_mode == "restricted"
    owners = [r.owner for r in sim.requests.values() if r.owner]
    assert len(owners) == len(set(r.request_id for r in sim.requests.values() if r.owner))


def test_energy_uncertainty_reduces_or_equals_service():
    full = _run(GreedyInsertionPolicy(), SimConfig(info_mode="full", seed=0, initial_soc=1.0))[1]
    tight = _run(
        GreedyInsertionPolicy(),
        SimConfig(info_mode="full", seed=0, initial_soc=0.05, energy_uncertainty_delta=0.5),
    )[1]
    assert tight.n_served <= full.n_served
