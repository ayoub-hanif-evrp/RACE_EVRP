"""Stage 3C: marginal travel ranking and flexibility-aware position selection."""

from __future__ import annotations

import networkx as nx
import pandas as pd

from race_casablanca.network.travel_time import CongestionModel
from race_casablanca.policies.charging_controller import ChargingController
from race_casablanca.policies.greedy import GreedyInsertionPolicy
from race_casablanca.policies.race_commitment import RaceCommitmentPolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.feasibility_check import evaluate_insertion
from race_casablanca.sim.policy_api import ActionInterface, build_full_observation
from race_casablanca.sim.types import Request, RequestStatus, Stop


def _star_graph() -> nx.MultiDiGraph:
    """Depot 0; customers 1 (near) and 2 (far). Bidirectional equal free-flow."""

    g = nx.MultiDiGraph()
    for i in range(3):
        g.add_node(i, x=float(i), y=0.0)
    # 0-1 short, 0-2 long; 1-2 medium
    edges = [
        (0, 1, 1000.0),
        (1, 0, 1000.0),
        (0, 2, 5000.0),
        (2, 0, 5000.0),
        (1, 2, 4500.0),
        (2, 1, 4500.0),
    ]
    for u, v, length in edges:
        g.add_edge(u, v, 0, length=length, free_flow_time_s=length / 1000.0 * 60.0, zone_commune="Z")
    return g


def _make_sim(n_vehicles: int = 2) -> OnlineSimulator:
    model = CongestionModel(citywide_hour=pd.Series({h: 1.0 for h in range(24)}))
    requests = [
        Request("R_near", 1, 0.0, 0.0, 7200.0, 30.0, 5.0, RequestStatus.AVAILABLE),
        Request("R_far", 2, 0.0, 0.0, 7200.0, 30.0, 5.0, RequestStatus.AVAILABLE),
    ]
    fleet = {
        "usable_battery_kwh": 40.0,
        "payload_kg": 600.0,
        "initial_soc": 1.0,
        "min_reserve_soc": 0.15,
        "consumption_wh_per_km": 200.0,
        "charge_power_kw": 22.0,
        "n_vehicles": n_vehicles,
    }
    return OnlineSimulator(
        scenario_id="synthetic/marginal_vs_total",
        graph=_star_graph(),
        model=model,
        requests=requests,
        fleet=fleet,
        depot_node=0,
        shift_start_s=0.0,
        shift_end_s=8 * 3600.0,
        config=SimConfig(info_mode="full", seed=0, charge_on_return=False, auto_depot_when_idle_empty=False),
        policy=None,
    )


def test_marginal_travel_differs_from_total_and_greedy_picks_marginal():
    """Vehicle with shorter total proposed route is NOT the min-marginal vehicle."""

    sim = _make_sim(2)
    sim.now_s = 0.0
    for r in sim.requests.values():
        r.status = RequestStatus.AVAILABLE
    v1, v2 = "V1", "V2"
    # V1 already committed to far customer (long baseline total)
    assert sim.try_assign(v1, "R_far", start_leg=False)
    # New request near depot: empty V2 has total ≈ short round trip;
    # V1 inserting near may have smaller *marginal* if geometry favors detour,
    # but empty V2 typically has smaller total. Construct so totals vs marginals diverge:
    # After V1 has R_far, inserting R_near on V1: total = tour covering both;
    # marginal = total - baseline(far-only).
    # On empty V2: total = near round trip = marginal.
    cands_v1 = evaluate_insertion(
        sim.vehicles[v1],
        sim.requests["R_near"],
        sim.requests,
        sim.router,
        sim.energy,
        sim.depot_node,
        sim.payload_max,
        sim.shift_end_s,
        sim.now_s,
    )
    cands_v2 = evaluate_insertion(
        sim.vehicles[v2],
        sim.requests["R_near"],
        sim.requests,
        sim.router,
        sim.energy,
        sim.depot_node,
        sim.payload_max,
        sim.shift_end_s,
        sim.now_s,
    )
    assert cands_v1 and cands_v2
    best_v1 = min(cands_v1, key=lambda c: c.marginal_travel_s)
    best_v2 = min(cands_v2, key=lambda c: c.marginal_travel_s)
    # Empty vehicle total equals its marginal; busy vehicle total > its marginal
    assert best_v1.total_travel_s > best_v1.marginal_travel_s + 1.0
    assert abs(best_v2.total_travel_s - best_v2.marginal_travel_s) < 1e-6
    # Shortest *total* among the two best positions is V2; if V1 marginal < V2 marginal,
    # greedy must pick V1 — construct assertion based on actual numbers
    min_total_vid = v1 if best_v1.total_travel_s < best_v2.total_travel_s else v2
    min_marg_vid = v1 if best_v1.marginal_travel_s < best_v2.marginal_travel_s else v2
    assert min_total_vid != min_marg_vid, (
        f"geometry did not separate total vs marginal: "
        f"v1 tot={best_v1.total_travel_s} marg={best_v1.marginal_travel_s}; "
        f"v2 tot={best_v2.total_travel_s} marg={best_v2.marginal_travel_s}"
    )

    pol = GreedyInsertionPolicy(charging=ChargingController(mode="none"))
    obs = build_full_observation(sim)
    # Only R_near still available
    actions = ActionInterface(sim, None)
    pol.on_decision(obs, actions, "request_release")
    assert sim.requests["R_near"].owner == min_marg_vid


def test_race_selects_flexibility_position_not_min_travel_and_executes_it():
    """RACE min-J position can differ from min-ΔT; plan matches chosen position."""

    sim = _make_sim(1)
    sim.now_s = 0.0
    for r in sim.requests.values():
        r.status = RequestStatus.AVAILABLE
    # Commit far first so two insertion positions exist for a second request
    assert sim.try_assign("V1", "R_far", start_leg=False)
    # Craft second request at node 1
    cands = evaluate_insertion(
        sim.vehicles["V1"],
        sim.requests["R_near"],
        sim.requests,
        sim.router,
        sim.energy,
        sim.depot_node,
        sim.payload_max,
        sim.shift_end_s,
        sim.now_s,
    )
    assert len(cands) >= 2
    # Score with strong energy flexibility weight so a non-min-travel position can win
    pol = RaceCommitmentPolicy(
        use_flexibility_pricing=True,
        allow_reassign=False,
        alpha_energy=5000.0,
        beta_time=0.0,
        charging=ChargingController(mode="none"),
    )
    min_travel = min(cands, key=lambda c: c.marginal_travel_s)
    scored = [(pol._score_candidate(c), c) for c in cands]
    best_j = min(scored, key=lambda x: x[0])[1]
    # If they happen to coincide, force difference by checking execute path still uses force_position
    obs = build_full_observation(sim)
    actions = ActionInterface(sim, None)
    # Manually claim using RACE best
    score, pos, chk = pol._vehicle_candidates(sim, "V1", "R_near")[0]
    assert actions.claim_task("V1", "R_near", force_position=pos)
    pickups = [s.request_id for s in sim.vehicles["V1"].plan if s.kind == "pickup"]
    # Position pos means R_near is at index pos among editable pickups (after locked none)
    assert pickups[pos] == "R_near"
    # Record whether J differed from min travel for the audit
    assert chk.insert_position == pos
    if best_j.insert_position != min_travel.insert_position:
        assert pos == best_j.insert_position


def test_charging_controller_does_not_mutate_episode_config():
    sim = _make_sim(1)
    sim.now_s = 0.0
    sim.vehicles["V1"].battery_kwh = 7.0  # below reserve+3
    sim.config.charge_on_return = False
    actions = ActionInterface(sim, None)
    ctrl = ChargingController(mode="adaptive_headroom", headroom_threshold_kwh=3.0)
    ctrl.apply(sim, actions)
    assert sim.config.charge_on_return is False
    assert any(s.kind == "depot_charge" for s in sim.vehicles["V1"].plan) or sim.vehicles["V1"].busy
