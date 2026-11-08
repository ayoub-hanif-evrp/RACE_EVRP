#!/usr/bin/env python
"""Stage 5.1: repaired RACE-RH vs equalized baselines (train only) + decision inputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.exact.dp_crosscheck import run_canned_crosscheck
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
    if kind == "sf_rh_07":
        return ServiceFirstRollingHorizonPolicy(
            name=kind,
            time_budget_s=budget,
            charging=ChargingController(mode="charge_to_target", target_soc=0.70),
            enable_readiness=True,
            readiness_target_soc=0.70,
        )
    if kind == "sf_rh_charge_aware":
        return ServiceFirstRollingHorizonPolicy(
            name=kind,
            time_budget_s=budget,
            optimize_charges=True,
            enable_readiness=True,
            readiness_target_soc=0.70,
        )
    if kind == "race_rh":
        return RaceRollingHorizonPolicy(
            name=kind,
            time_budget_s=budget,
            enable_readiness=True,
            readiness_target_soc=0.70,
        )
    if kind == "race_rh_no_ready":
        return RaceRollingHorizonPolicy(name=kind, time_budget_s=budget, enable_readiness=False)
    raise KeyError(kind)


def run_one(sim: OnlineSimulator, experiment: str) -> dict:
    m = sim.run()
    row = m.to_dict()
    row["experiment"] = experiment
    pol = sim.policy
    row["policy_timeouts"] = int(getattr(pol, "n_timeouts", 0) or 0)
    row["policy_fallbacks"] = int(getattr(pol, "n_fallbacks", 0) or 0)
    row["policy_runtime_s"] = float(getattr(pol, "total_decision_runtime_s", 0.0) or 0.0)
    row["n_chose_optimized"] = int(getattr(pol, "n_chose_optimized", 0) or 0)
    row["n_chose_incumbent"] = int(getattr(pol, "n_chose_incumbent", 0) or 0)
    row["n_chose_safety"] = int(getattr(pol, "n_chose_safety", 0) or 0)
    row["n_proactive_charges"] = int(getattr(getattr(pol, "readiness", None), "n_proactive_charges", 0) or 0)
    print(
        f"  {experiment}: ot={row['on_time_rate_all']:.3f} "
        f"served={row['n_served']}/{row['n_requests']} "
        f"deliv={row.get('energy_delivered_kwh', 0):.1f} "
        f"rt={row['policy_runtime_s']:.1f}s to={row['policy_timeouts']} "
        f"src=opt{row['n_chose_optimized']}/inc{row['n_chose_incumbent']}/safe{row['n_chose_safety']} "
        f"ready={row['n_proactive_charges']}",
        flush=True,
    )
    return row


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Exact DP crosscheck...", flush=True)
    xx = run_canned_crosscheck()
    (out_dir / "stage5_1_exact_crosscheck.json").write_text(json.dumps(xx, indent=2), encoding="utf-8")
    print(f"  crosscheck ok={[r['ok'] for r in xx]}", flush=True)

    print("Loading network (Stage 5.1 decision gate, train only)...", flush=True)
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

    policies = [
        "greedy_adaptive_full",
        "greedy_always_full",
        "greedy_charge_07",
        "sf_rh_07",
        "sf_rh_charge_aware",
        "race_rh",
        "race_rh_no_ready",
    ]
    suites = [("full_soc", 1.0, 0.0), ("soc35", 0.35, 0.0), ("soc35_delta02", 0.35, 0.2)]
    rows: list[dict] = []

    for sid, scen in scenarios.items():
        for suite_name, init_soc, delta in suites:
            if suite_name == "soc35_delta02" and sid != "peak_stress_seed2":
                continue
            print(f"\n=== {sid} / {suite_name} ===", flush=True)
            for pk in policies:
                if pk == "race_rh_no_ready" and not (
                    suite_name == "soc35" and sid in {"peak_stress_seed2", "tight_windows_seed3"}
                ):
                    continue
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
                    policy=make_policy(pk, 0.5),
                    router=router,
                )
                row = run_one(sim, f"{sid}|{suite_name}|{pk}|b0.5")
                row.update(
                    scenario=sid,
                    suite=suite_name,
                    policy_kind=pk,
                    budget_s=0.5,
                    initial_soc=init_soc,
                    delta=delta,
                )
                rows.append(row)

    # Budget sweep peak soc35
    print("\n=== budget sweep peak soc35 ===", flush=True)
    scen = scenarios["peak_stress_seed2"]
    for budget in [0.25, 0.5, 1.0]:
        for pk in ["sf_rh_07", "race_rh"]:
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
                budget_s=budget, initial_soc=0.35, delta=0.0,
            )
            rows.append(row)

    df = pd.DataFrame(rows)
    csv_path = out_dir / "stage5_1_decision.csv"
    json_path = out_dir / "stage5_1_decision.json"
    df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {csv_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
