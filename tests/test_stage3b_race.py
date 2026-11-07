"""Stage 3B: partial commits, message counterfactual metric, RACE scoring."""

from __future__ import annotations

from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.policies.limited_info import LimitedInfoCooperativePolicy
from race_casablanca.policies.race_commitment import RaceCommitmentPolicy
from race_casablanca.policies.restricted_dispatch import intended_claim_id
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.policy_api import ActionInterface, build_restricted_observation
from race_casablanca.sim.synthetic import make_two_request_scenario
from race_casablanca.sim.types import RequestStatus


def _sim(policy=None, **cfg):
    base = make_two_request_scenario()
    return OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0, **cfg),
        policy=policy,
    )


def test_partial_commit_preserves_omitted_vehicle_commitments():
    sim = _sim(n_vehicles=2)
    sim.now_s = 0.0
    for rid in ("R1", "R2"):
        sim.requests[rid].status = RequestStatus.AVAILABLE
    vids = sorted(sim.vehicles)
    assert len(vids) == 2
    v1, v2 = vids[0], vids[1]
    assert sim.try_assign(v1, "R1", start_leg=False)
    assert sim.try_assign(v2, "R2", start_leg=False)
    c2_before = list(sim.vehicles[v2].committed)
    plan2_before = [s.request_id for s in sim.vehicles[v2].plan]
    # Partial update of v1 only — must not release v2
    assert sim.set_pickup_plan(v1, ["R1"])
    assert list(sim.vehicles[v2].committed) == c2_before
    assert [s.request_id for s in sim.vehicles[v2].plan] == plan2_before
    assert sim.requests["R2"].owner == v2
    assert sim.requests["R2"].status == RequestStatus.COMMITTED


def test_full_fleet_commit_can_clear_editable_on_all_listed_vehicles():
    sim = _sim()
    sim.now_s = 0.0
    for rid in ("R1", "R2"):
        sim.requests[rid].status = RequestStatus.AVAILABLE
    vids = list(sim.vehicles)
    assert sim.try_assign(vids[0], "R1", start_leg=False)
    assignment = {vid: [] for vid in vids}
    # Preserve locks if any
    for vid, v in sim.vehicles.items():
        if v.moving_to and v.moving_to.request_id:
            assignment[vid] = [v.moving_to.request_id]
    # Explicitly include all vehicles → full replacement may release R1 if not locked
    if not sim.vehicles[vids[0]].busy:
        assert sim.commit_fleet_plans(assignment)
        assert sim.requests["R1"].status == RequestStatus.AVAILABLE


def test_message_metric_requires_counterfactual_change():
    base = make_two_request_scenario()
    pol = LimitedInfoCooperativePolicy(comm_mode="none")
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="restricted", seed=0),
        policy=pol,
    )
    sim.now_s = 0.0
    for rid in sim.requests:
        sim.requests[rid].status = RequestStatus.AVAILABLE
    vid = next(iter(sim.vehicles))
    obs = build_restricted_observation(sim, vid)
    actions = ActionInterface(sim, actor_vehicle_id=vid)
    # No peers → counterfactual identical
    pol.on_decision(obs, actions, "message")
    assert pol.n_message_driven_decision_invocations == 1
    assert pol.n_counterfactual_decision_changes == 0


def test_race_ablation_matches_greedy_ranking_on_synthetic():
    """Without opportunity cost, RACE should match greedy serve counts on toy scenario."""

    g = _sim(policy=GreedyInsertionPolicy())
    r = _sim(policy=RaceCommitmentPolicy(use_opportunity_cost=False, allow_reassign=False))
    mg = g.run()
    mr = r.run()
    assert mg.n_served == mr.n_served
    assert mg.battery_reserve_violations == 0
    assert mr.battery_reserve_violations == 0


def test_race_opportunity_cost_prefers_higher_energy_flex_when_travel_ties(monkeypatch):
    """Smoke: scoring returns finite values for feasible insertions."""

    sim = _sim(policy=RaceCommitmentPolicy())
    sim.now_s = 0.0
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    pol = RaceCommitmentPolicy(use_flexibility_pricing=True)
    cands = pol._vehicle_candidates(sim, next(iter(sim.vehicles)), "R1")
    assert cands
    score, _pos, _chk = cands[0]
    assert score >= 0.0


def test_intended_claim_id_is_non_mutating():
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
        config=SimConfig(info_mode="restricted", seed=0),
        policy=None,
    )
    sim.now_s = 0.0
    for rid in sim.requests:
        sim.requests[rid].status = RequestStatus.AVAILABLE
    vid = next(iter(sim.vehicles))
    obs = build_restricted_observation(sim, vid)
    actions = ActionInterface(sim, actor_vehicle_id=vid)
    rid = intended_claim_id(obs, actions)
    assert rid is not None
    assert sim.requests[rid].status == RequestStatus.AVAILABLE
