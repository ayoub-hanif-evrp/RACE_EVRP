#!/usr/bin/env python
"""Complete Stage-2 baseline metrics with one shared Casablanca graph load."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import (
    GreedyInsertionPolicy,
    LimitedInfoCooperativePolicy,
    RollingHorizonPolicy,
)
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
from race_casablanca.sim.synthetic import make_two_request_scenario


def _run(sim: OnlineSimulator, experiment: str) -> dict:
    row = sim.run().to_dict()
    row["experiment"] = experiment
    row["source"] = "executed"
    print(
        f"  {experiment}: served={row['n_served']}/{row['n_requests']} "
        f"on_time={row['n_on_time']} dist_km={row['total_distance_m']/1000:.2f} "
        f"E={row['energy_consumed_kwh']:.2f} returns={row['n_depot_returns']} "
        f"charges={row['n_charges']} msgs={row['n_messages']} "
        f"reserve_viol={row['battery_reserve_violations']} "
        f"energy_bind={row['energy_changed_dispatch']} "
        f"dec_ms={1000*row['mean_decision_runtime_s']:.1f}",
        flush=True,
    )
    return row


def run_synthetic(rows: list[dict]) -> None:
    print("=== Synthetic ===", flush=True)
    base = make_two_request_scenario()
    for name, policy, cfg in [
        ("synthetic_greedy", GreedyInsertionPolicy(), SimConfig(info_mode="full", seed=0)),
        ("synthetic_rh", RollingHorizonPolicy(time_budget_s=0.05), SimConfig(info_mode="full", seed=0)),
        (
            "synthetic_limited",
            LimitedInfoCooperativePolicy(broadcast_period_s=30.0),
            SimConfig(info_mode="restricted", message_delay_s=10.0, seed=0, n_vehicles=2),
        ),
    ]:
        fleet = dict(base["fleet"])
        if cfg.n_vehicles:
            fleet["n_vehicles"] = cfg.n_vehicles
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
        rows.append(_run(sim, name))


def run_casablanca_bundle(rows: list[dict]) -> None:
    print("Loading Casablanca network once...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    shared_router = RouteCache(graph, model, day="Monday")

    baseline = load_scenario(
        scenarios_dir() / "train" / "baseline_seed1",
        load_network=False,
        graph=graph,
        model=model,
    )
    stress = load_scenario(
        scenarios_dir() / "train" / "peak_stress_seed2",
        load_network=False,
        graph=graph,
        model=model,
    )
    landmarks = (
        [baseline.depot_node, stress.depot_node]
        + [r.snap_node for r in baseline.requests]
        + [r.snap_node for r in stress.requests]
    )
    print(f"Warming shared OD cache for {len(set(landmarks))} landmarks...", flush=True)
    shared_router.warmup(landmarks)
    print("OD warmup done.", flush=True)

    def make(scen, policy, cfg):
        cfg.day = scen.day
        return OnlineSimulator(
            scenario_id=scen.scenario_id,
            graph=graph,
            model=model,
            requests=scen.requests,
            fleet=scen.fleet,
            depot_node=scen.depot_node,
            shift_start_s=scen.shift_start_s,
            shift_end_s=scen.shift_end_s,
            config=cfg,
            policy=policy,
            router=shared_router,
        )

    experiments = [
        ("ref_greedy", baseline, GreedyInsertionPolicy(), SimConfig(info_mode="full", seed=1)),
        (
            "ref_rh",
            baseline,
            RollingHorizonPolicy(time_budget_s=0.15, reoptimize_every_s=1800.0),
            SimConfig(info_mode="full", seed=1),
        ),
        (
            "ref_limited",
            baseline,
            LimitedInfoCooperativePolicy(broadcast_period_s=300.0),
            SimConfig(info_mode="restricted", message_delay_s=60.0, seed=1),
        ),
        (
            "low_soc_greedy",
            baseline,
            GreedyInsertionPolicy(),
            SimConfig(info_mode="full", seed=1, initial_soc=0.35),
        ),
        (
            "energy_uncert_greedy",
            baseline,
            GreedyInsertionPolicy(),
            SimConfig(info_mode="full", seed=1, initial_soc=0.40, energy_uncertainty_delta=0.25),
        ),
        (
            "fleet1_greedy",
            baseline,
            GreedyInsertionPolicy(),
            SimConfig(info_mode="full", seed=1, n_vehicles=1),
        ),
        (
            "delay_limited",
            baseline,
            LimitedInfoCooperativePolicy(broadcast_period_s=600.0),
            SimConfig(
                info_mode="restricted",
                message_delay_s=300.0,
                seed=1,
                initial_soc=0.40,
                energy_uncertainty_delta=0.15,
            ),
        ),
        ("stress_greedy", stress, GreedyInsertionPolicy(), SimConfig(info_mode="full", seed=1)),
        (
            "stress_limited",
            stress,
            LimitedInfoCooperativePolicy(broadcast_period_s=600.0),
            SimConfig(info_mode="restricted", message_delay_s=60.0, seed=1),
        ),
        (
            "stress_low_soc",
            stress,
            GreedyInsertionPolicy(),
            SimConfig(info_mode="full", seed=1, initial_soc=0.35, energy_uncertainty_delta=0.2),
        ),
    ]

    for label, scen, policy, cfg in experiments:
        print(f"start {label} ...", flush=True)
        rows.append(_run(make(scen, policy, cfg), label))


def main() -> int:
    rows: list[dict] = []
    run_synthetic(rows)
    run_casablanca_bundle(rows)
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "stage2_baseline_metrics.csv"
    json_path = out_dir / "stage2_baseline_metrics.json"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {csv_path} ({len(rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
