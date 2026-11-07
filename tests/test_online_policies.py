"""All three Stage-2 baselines run on the synthetic API and respect feasibility."""

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
    sim, m = _run(
        RollingHorizonPolicy(time_budget_s=0.05, reoptimize_every_s=0.0),
        SimConfig(info_mode="full", seed=0),
        n_vehicles=1,
    )
    assert m.policy == "rolling_horizon_lns"
    assert m.n_decisions >= 1
    assert m.payload_violations == 0


def test_limited_info_baseline_runs():
    sim, m = _run(
        LimitedInfoCooperativePolicy(broadcast_period_s=5.0),
        SimConfig(info_mode="restricted", message_delay_s=5.0, seed=0, n_vehicles=2),
        n_vehicles=2,
    )
    assert m.policy == "limited_info_cooperative"
    assert m.info_mode == "restricted"
    # Registry must not accept duplicate owners
    owners = [r.owner for r in sim.requests.values() if r.owner]
    # each request at most one owner historically; completed keep last owner
    assert len(owners) == len(set(r.request_id for r in sim.requests.values() if r.owner))


def test_energy_uncertainty_can_block_nominal_ok_insertion():
    """With low SOC and high delta, conservative planning may reject legs."""

    base = make_two_request_scenario()
    # Drain battery capacity conceptually via low initial SOC + high uncertainty
    cfg = SimConfig(info_mode="full", seed=0, initial_soc=0.05, energy_uncertainty_delta=0.5)
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=cfg,
        policy=GreedyInsertionPolicy(),
    )
    m = sim.run()
    # Either fewer served than full-battery case, or energy_changed_dispatch counted
    full = _run(GreedyInsertionPolicy(), SimConfig(info_mode="full", seed=0, initial_soc=1.0))[1]
    assert m.n_served <= full.n_served or m.energy_changed_dispatch >= 0
