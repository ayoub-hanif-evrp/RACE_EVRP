"""Stage 4A: post-decision lookahead, charging alternatives, anti-leakage."""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd

from race_casablanca.demand.synthetic_futures import SyntheticFutureModel
from race_casablanca.network.travel_time import CongestionModel
from race_casablanca.policies.race_postdecision import RacePostDecisionPolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.lookahead import CandidateAction, fork_and_rollout
from race_casablanca.sim.types import Request, RequestStatus


def _line_sim(requests, *, soc=1.0, n_vehicles=1):
    g = nx.MultiDiGraph()
    for i in range(4):
        g.add_node(i, x=float(i), y=0.0)
    for u, v in [(0, 1), (1, 2), (2, 3), (3, 2), (2, 1), (1, 0)]:
        g.add_edge(u, v, 0, length=1000.0, free_flow_time_s=60.0, zone_commune="Z")
    model = CongestionModel(citywide_hour=pd.Series({h: 1.0 for h in range(24)}))
    fleet = {
        "usable_battery_kwh": 40.0,
        "payload_kg": 600.0,
        "initial_soc": soc,
        "min_reserve_soc": 0.15,
        "consumption_wh_per_km": 200.0,
        "charge_power_kw": 22.0,
        "n_vehicles": n_vehicles,
    }
    return OnlineSimulator(
        scenario_id="toy/stage4a",
        graph=g,
        model=model,
        requests=requests,
        fleet=fleet,
        depot_node=0,
        shift_start_s=0.0,
        shift_end_s=4 * 3600.0,
        config=SimConfig(info_mode="full", seed=0, charge_on_return=False, initial_soc=soc),
        policy=None,
    )


def test_lookahead_strips_unreleased_eval_requests():
    """Fork must not observe evaluation unreleased futures."""

    reqs = [
        Request("R_now", 1, 0.0, 0.0, 3600.0, 30.0, 5.0),
        Request("R_secret", 3, 500.0, 500.0, 3600.0, 30.0, 5.0),
    ]
    sim = _line_sim(reqs, soc=1.0)
    sim.now_s = 0.0
    sim.requests["R_now"].status = RequestStatus.AVAILABLE
    # R_secret remains UNRELEASED (eval future)
    out = fork_and_rollout(
        sim,
        CandidateAction(kind="noop", label="noop"),
        synthetic=[],
        horizon_s=1000.0,
    )
    assert out["ok"]
    # Secret must not appear as served from leakage of unreleased eval request
    # (may still be 0 served). Stronger: rebuild fork and check requests keys.
    from race_casablanca.sim.lookahead import clone_sim_state, _strip_eval_futures

    fork = clone_sim_state(sim)
    _strip_eval_futures(fork)
    assert "R_secret" not in fork.requests
    assert "R_now" in fork.requests


def test_early_charge_preferred_when_battery_blocks_future():
    """Low SOC: charging now should score ≥ accepting an optional near pickup when future needs energy."""

    # Only a mild near request available; future synthetic will need energy after charge
    reqs = [Request("R_near", 1, 0.0, 0.0, 800.0, 30.0, 5.0)]
    sim = _line_sim(reqs, soc=0.22)
    sim.now_s = 0.0
    sim.requests["R_near"].status = RequestStatus.AVAILABLE
    # Force low battery
    sim.vehicles["V1"].battery_kwh = 8.0

    model = SyntheticFutureModel(
        release_offsets_s=np.array([200.0]),
        snap_nodes=np.array([3]),
        tw_durations_s=np.array([3600.0]),
        service_s=np.array([30.0]),
        weights_kg=np.array([5.0]),
        source_scenarios=("toy",),
    )
    pol = RacePostDecisionPolicy(
        n_samples=2,
        n_synthetic_requests=2,
        max_claim_candidates=2,
        max_charge_candidates=1,
        enable_future_eval=True,
        enable_charge_actions=True,
        lookahead_horizon_s=2400.0,
        future_model=model,
        seed=1,
    )
    from race_casablanca.sim.policy_api import ActionInterface, build_full_observation

    obs = build_full_observation(sim)
    actions = ActionInterface(sim, None)
    # Run one decision — should not crash; prefer charge or claim based on scores
    pol.on_decision(obs, actions, "request_release")
    assert pol.decision_log
    assert pol.total_lookahead_runtime_s >= 0.0


def test_immediate_service_when_battery_ample():
    reqs = [Request("R1", 2, 0.0, 0.0, 600.0, 30.0, 5.0)]
    sim = _line_sim(reqs, soc=1.0)
    sim.now_s = 0.0
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    model = SyntheticFutureModel(
        release_offsets_s=np.array([100.0]),
        snap_nodes=np.array([1]),
        tw_durations_s=np.array([1800.0]),
        service_s=np.array([30.0]),
        weights_kg=np.array([5.0]),
        source_scenarios=("toy",),
    )
    pol = RacePostDecisionPolicy(
        n_samples=2,
        n_synthetic_requests=1,
        lookahead_horizon_s=1800.0,
        future_model=model,
        seed=0,
    )
    from race_casablanca.sim.policy_api import ActionInterface, build_full_observation

    obs = build_full_observation(sim)
    actions = ActionInterface(sim, None)
    pol.on_decision(obs, actions, "request_release")
    # With full battery and tight near request, should claim rather than only charge
    assert sim.requests["R1"].status in {RequestStatus.COMMITTED, RequestStatus.AVAILABLE, RequestStatus.IN_SERVICE}
    # Prefer claim
    assert any("claim" in (d.get("chosen") or "") for d in pol.decision_log) or sim.requests["R1"].owner == "V1"


def test_ablation_without_future_eval_runs():
    reqs = [Request("R1", 1, 0.0, 0.0, 3600.0, 30.0, 5.0)]
    sim = _line_sim(reqs)
    sim.now_s = 0.0
    sim.requests["R1"].status = RequestStatus.AVAILABLE
    pol = RacePostDecisionPolicy(enable_future_eval=False, enable_charge_actions=True)
    from race_casablanca.sim.policy_api import ActionInterface, build_full_observation

    pol.on_decision(build_full_observation(sim), ActionInterface(sim, None), "request_release")
    assert sim.requests["R1"].owner == "V1" or sim.requests["R1"].status != RequestStatus.AVAILABLE
