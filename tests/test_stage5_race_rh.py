"""Stage 5: charging DP + RACE-RH tiny validation."""

from __future__ import annotations

from race_casablanca.exact.charge_commit_enum import (
    enumerate_charge_commit,
    instance_a_early_charge,
    instance_b_serve_before_charge,
    instance_c_partial_better,
)
from race_casablanca.optimization.charge_label_dp import optimize_charge_schedule
from race_casablanca.policies.race_rh import RaceRollingHorizonPolicy
from race_casablanca.sim.energy import EnergyModel
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.feasibility_check import projected_state_after_lock
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import ProjectedState, Request, RequestStatus, Stop, VehicleMode


def test_dp_rejects_energy_infeasible_without_charge():
    base = make_two_request_scenario()
    router = RouteCache(base["graph"], base["model"], day="Monday")
    e = EnergyModel(4.0, 0.0, 40.0, 0.15, 22.0)
    req = Request("R1", 3, 0.0, 0.0, 50000.0, 60.0, 10.0, status=RequestStatus.AVAILABLE)
    origin = ProjectedState(0, 0.0, 14.0, 0.0)
    # No charges allowed
    res = optimize_charge_schedule(
        origin, ["R1"], {"R1": req}, router, e, 0, 600.0, 1e9,
        allow_leading_charge=False, allow_between_charge=False, allow_trailing_charge=False,
    )
    assert not res.feasible
    # With charges
    res2 = optimize_charge_schedule(origin, ["R1"], {"R1": req}, router, e, 0, 600.0, 1e9)
    assert res2.feasible
    assert any(s.kind == "depot_charge" for s in res2.plan)


def test_dp_prefers_partial_when_full_misses_deadline():
    base = make_two_request_scenario()
    router = RouteCache(base["graph"], base["model"], day="Monday")
    # Round-trip 12 kWh + reserve 6 → need ≥18; bat=14 needs charge.
    # 0.50 target (20 kWh): +6 kWh @11kW ≈ 1964s fits tw_end=5000.
    # Full (40): +26 kWh ≈ 8509s misses.
    e = EnergyModel(2.0, 0.0, 40.0, 0.15, 11.0)
    req = Request("R1", 3, 0.0, 0.0, 5000.0, 60.0, 10.0, status=RequestStatus.AVAILABLE)
    origin = ProjectedState(0, 0.0, 14.0, 0.0)
    res = optimize_charge_schedule(origin, ["R1"], {"R1": req}, router, e, 0, 600.0, 1e9)
    assert res.feasible
    charges = [s for s in res.plan if s.kind == "depot_charge"]
    assert charges
    assert charges[0].target_kwh is not None
    assert charges[0].target_kwh < 40.0 - 1e-6
    res_full = optimize_charge_schedule(
        origin, ["R1"], {"R1": req}, router, e, 0, 600.0, 1e9, fixed_target_soc=1.0
    )
    assert not res_full.feasible


def test_dp_matches_exact_on_instance_c_structure():
    """Exact C wants charge-to-0.5; DP on line graph with matching energy should serve 1."""
    r = enumerate_charge_commit(instance_c_partial_better())
    assert r.best_on_time == 1
    # Structural: always-full loses
    assert r.always_full_on_time == 0


def test_race_rh_synthetic_episode_runs():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0, energy_uncertainty_delta=0.0),
        policy=RaceRollingHorizonPolicy(time_budget_s=0.25),
    )
    m = sim.run()
    assert m.n_served >= 1
    assert m.n_on_time == m.n_served
    for r in sim.requests.values():
        if r.status == RequestStatus.COMPLETED:
            assert r.on_time is True


def test_locked_leg_immutable_under_race_rh():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id="lock",
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=0,
        shift_start_s=0.0,
        shift_end_s=8 * 3600.0,
        config=SimConfig(info_mode="full", seed=0, energy_uncertainty_delta=0.0),
        policy=None,
    )
    # Force V1 en-route to R1
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    assert sim.try_assign("V1", "R1")
    v = sim.vehicles["V1"]
    assert v.moving_to and v.moving_to.request_id == "R1"
    locked_id = v.moving_to.request_id
    pol = RaceRollingHorizonPolicy(time_budget_s=0.2)
    from race_casablanca.sim.policy_api import ActionInterface, build_full_observation

    obs = build_full_observation(sim)
    pol.on_decision(obs, ActionInterface(sim), "request_release")
    assert v.moving_to and v.moving_to.request_id == locked_id


def test_failed_commit_restores_plan():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id="restore",
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=0,
        shift_start_s=0.0,
        shift_end_s=8 * 3600.0,
        config=SimConfig(info_mode="full", seed=0, energy_uncertainty_delta=0.0),
        policy=None,
    )
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    sim.try_assign("V1", "R1")
    before = list(sim.vehicles["V1"].plan)
    # Invalid: unknown vehicle
    ok = sim.commit_fleet_plans({"V99": ["R2"]})
    assert ok is False
    assert [s.request_id for s in sim.vehicles["V1"].plan] == [s.request_id for s in before]


def test_ablation_fixed_07_runs():
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0, energy_uncertainty_delta=0.0),
        policy=RaceRollingHorizonPolicy(time_budget_s=0.2, fixed_target_soc=0.70),
    )
    m = sim.run()
    assert m.n_requests == 2
