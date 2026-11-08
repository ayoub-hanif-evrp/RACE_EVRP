#!/usr/bin/env python
"""Stage 5: RACE-RH vs equalized charge-aware baselines (train only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import (
    ChargingController,
    GreedyInsertionPolicy,
    RaceRollingHorizonPolicy,
    ServiceFirstRollingHorizonPolicy,
)
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def make_policy(kind: str, budget: float = 0.5):
    if kind == "greedy_adaptive_full":
        return GreedyInsertionPolicy(
            name=kind, charging=ChargingController(mode="adaptive_headroom", target_soc=1.0)
        )
    if kind == "greedy_always_full":
        return GreedyInsertionPolicy(
            name=kind, charging=ChargingController(mode="always_on_return", target_soc=1.0)
        )
    if kind == "greedy_charge_07":
        return GreedyInsertionPolicy(
            name=kind, charging=ChargingController(mode="charge_to_target", target_soc=0.70)
        )
    if kind == "sf_rh_adaptive":
        return ServiceFirstRollingHorizonPolicy(
            name=kind,
            time_budget_s=budget,
            charging=ChargingController(mode="adaptive_headroom", target_soc=1.0),
        )
    if kind == "sf_rh_07":
        return ServiceFirstRollingHorizonPolicy(
            name=kind,
            time_budget_s=budget,
            charging=ChargingController(mode="charge_to_target", target_soc=0.70),
        )
    if kind == "sf_rh_charge_aware":
        return ServiceFirstRollingHorizonPolicy(
            name=kind, time_budget_s=budget, optimize_charges=True
        )
    if kind == "race_rh":
        return RaceRollingHorizonPolicy(name=kind, time_budget_s=budget)
    if kind == "race_rh_no_charge_opt":
        return RaceRollingHorizonPolicy(
            name=kind, time_budget_s=budget, enable_charge_opt=False
        )
    if kind == "race_rh_fixed_07":
        return RaceRollingHorizonPolicy(
            name=kind, time_budget_s=budget, fixed_target_soc=0.70
        )
    if kind == "race_rh_greedy_order":
        return RaceRollingHorizonPolicy(
            name=kind, time_budget_s=budget, enable_neighborhood=False
        )
    raise KeyError(kind)


def run_one(sim: OnlineSimulator, experiment: str) -> dict:
    m = sim.run()
    row = m.to_dict()
    row["experiment"] = experiment
    pol = sim.policy
    row["policy_timeouts"] = int(getattr(pol, "n_timeouts", 0) or 0)
    row["policy_fallbacks"] = int(getattr(pol, "n_fallbacks", 0) or 0)
    row["policy_runtime_s"] = float(getattr(pol, "total_decision_runtime_s", 0.0) or 0.0)
    print(
        f"  {experiment}: ot_all={row['on_time_rate_all']:.3f} "
        f"served={row['n_served']}/{row['n_requests']} "
        f"missed={row.get('n_missed', 0)} "
        f"deliv={row.get('energy_delivered_kwh', 0):.1f} "
        f"rt={row['policy_runtime_s']:.1f}s "
        f"to={row['policy_timeouts']}",
        flush=True,
    )
    return row


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading network (Stage 5 RACE-RH, train only)...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

    scen_ids = ["baseline_seed1", "peak_stress_seed2", "tight_windows_seed3"]
    scenarios = {
        sid: load_scenario(
            scenarios_dir() / "train" / sid, load_network=False, graph=graph, model=model
        )
        for sid in scen_ids
    }
    landmarks = []
    for sc in scenarios.values():
        landmarks.append(sc.depot_node)
        landmarks.extend(r.snap_node for r in sc.requests)
    router.warmup(landmarks)

    core_policies = [
        "greedy_adaptive_full",
        "greedy_always_full",
        "greedy_charge_07",
        "sf_rh_adaptive",
        "sf_rh_07",
        "sf_rh_charge_aware",
        "race_rh",
    ]
    ablations = ["race_rh_no_charge_opt", "race_rh_fixed_07", "race_rh_greedy_order"]
    suites = [
        ("full_soc", 1.0, 0.0),
        ("soc35", 0.35, 0.0),
        ("soc35_delta02", 0.35, 0.2),
    ]
    # Budget sweep on peak soc35 for RH family only
    budget_sweep = [0.25, 0.5, 1.0]

    rows: list[dict] = []

    for sid, scen in scenarios.items():
        for suite_name, init_soc, delta in suites:
            if suite_name == "soc35_delta02" and sid != "peak_stress_seed2":
                continue
            print(f"\n=== {sid} / {suite_name} ===", flush=True)
            for pk in core_policies:
                cfg = SimConfig(
                    info_mode="full",
                    seed=1,
                    initial_soc=init_soc,
                    energy_uncertainty_delta=delta,
                    charge_on_return=False,
                    day=scen.day,
                )
                sim = OnlineSimulator(
                    scenario_id=scen.scenario_id,
                    graph=graph,
                    model=model,
                    requests=scen.requests,
                    fleet=scen.fleet,
                    depot_node=scen.depot_node,
                    shift_start_s=scen.shift_start_s,
                    shift_end_s=scen.shift_end_s,
                    config=cfg,
                    policy=make_policy(pk, budget=0.5),
                    router=router,
                )
                row = run_one(sim, f"{sid}|{suite_name}|{pk}|b0.5")
                row.update(
                    scenario=sid, suite=suite_name, policy_kind=pk, budget_s=0.5,
                    initial_soc=init_soc, delta=delta, arm="core",
                )
                rows.append(row)

            # Ablations on peak/tight soc35 only
            if suite_name == "soc35" and sid in {"peak_stress_seed2", "tight_windows_seed3"}:
                for pk in ablations:
                    cfg = SimConfig(
                        info_mode="full", seed=1, initial_soc=init_soc,
                        energy_uncertainty_delta=delta, charge_on_return=False, day=scen.day,
                    )
                    sim = OnlineSimulator(
                        scenario_id=scen.scenario_id, graph=graph, model=model,
                        requests=scen.requests, fleet=scen.fleet, depot_node=scen.depot_node,
                        shift_start_s=scen.shift_start_s, shift_end_s=scen.shift_end_s,
                        config=cfg, policy=make_policy(pk, 0.5), router=router,
                    )
                    row = run_one(sim, f"{sid}|{suite_name}|{pk}|b0.5")
                    row.update(
                        scenario=sid, suite=suite_name, policy_kind=pk, budget_s=0.5,
                        initial_soc=init_soc, delta=delta, arm="ablation",
                    )
                    rows.append(row)

    # Budget sweep: peak soc35, RH-family
    print("\n=== budget sweep peak_stress_seed2 / soc35 ===", flush=True)
    scen = scenarios["peak_stress_seed2"]
    for budget in budget_sweep:
        for pk in ["sf_rh_charge_aware", "race_rh"]:
            cfg = SimConfig(
                info_mode="full", seed=1, initial_soc=0.35,
                energy_uncertainty_delta=0.0, charge_on_return=False, day=scen.day,
            )
            sim = OnlineSimulator(
                scenario_id=scen.scenario_id, graph=graph, model=model,
                requests=scen.requests, fleet=scen.fleet, depot_node=scen.depot_node,
                shift_start_s=scen.shift_start_s, shift_end_s=scen.shift_end_s,
                config=cfg, policy=make_policy(pk, budget), router=router,
            )
            row = run_one(sim, f"peak_stress_seed2|soc35|{pk}|b{budget}")
            row.update(
                scenario="peak_stress_seed2", suite="soc35", policy_kind=pk,
                budget_s=budget, initial_soc=0.35, delta=0.0, arm="budget",
            )
            rows.append(row)

    df = pd.DataFrame(rows)
    csv_path = out_dir / "stage5_race_rh.csv"
    json_path = out_dir / "stage5_race_rh.json"
    df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {csv_path}", flush=True)
    print(f"Wrote {json_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
