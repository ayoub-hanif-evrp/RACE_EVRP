#!/usr/bin/env python
"""Run Stage-2 online baselines on synthetic + Casablanca scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, report_dir, scenarios_dir
from race_casablanca.policies import (
    GreedyInsertionPolicy,
    LimitedInfoCooperativePolicy,
    RollingHorizonPolicy,
)
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.scenario_loader import load_drive_graph, load_congestion_model, load_scenario
from race_casablanca.sim.synthetic import make_two_request_scenario


def _run_one(sim: OnlineSimulator) -> dict:
    metrics = sim.run()
    return metrics.to_dict()


def run_synthetic(out_rows: list[dict]) -> None:
    base = make_two_request_scenario()
    configs = [
        ("greedy_insertion", "full", GreedyInsertionPolicy(), SimConfig(info_mode="full", seed=0)),
        ("rolling_horizon_lns", "full", RollingHorizonPolicy(time_budget_s=0.1), SimConfig(info_mode="full", seed=0)),
        (
            "limited_info_cooperative",
            "restricted",
            LimitedInfoCooperativePolicy(broadcast_period_s=30.0),
            SimConfig(info_mode="restricted", message_delay_s=10.0, seed=0),
        ),
    ]
    for _name, mode, policy, cfg in configs:
        cfg.day = base["day"]
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
            policy=policy,
        )
        row = _run_one(sim)
        row["experiment"] = "synthetic"
        out_rows.append(row)


def run_casablanca(
    out_rows: list[dict],
    *,
    scenario_rel: str = "train/baseline_seed1",
    stress: bool = True,
) -> None:
    print("Loading Casablanca road network (one-time)...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    scen = load_scenario(
        scenarios_dir() / scenario_rel.replace("/", "\\") if False else scenarios_dir().joinpath(*scenario_rel.split("/")),
        load_network=False,
        graph=graph,
        model=model,
        day="Monday",
    )

    experiments = [
        {
            "label": "ref_greedy",
            "policy": GreedyInsertionPolicy(),
            "cfg": SimConfig(info_mode="full", seed=1, energy_uncertainty_delta=0.0),
        },
        {
            "label": "ref_rh",
            "policy": RollingHorizonPolicy(time_budget_s=0.5, reoptimize_every_s=600.0),
            "cfg": SimConfig(info_mode="full", seed=1, energy_uncertainty_delta=0.0),
        },
        {
            "label": "ref_limited",
            "policy": LimitedInfoCooperativePolicy(broadcast_period_s=180.0),
            "cfg": SimConfig(info_mode="restricted", message_delay_s=60.0, seed=1, energy_uncertainty_delta=0.0),
        },
    ]
    if stress:
        experiments.extend(
            [
                {
                    "label": "low_soc_greedy",
                    "policy": GreedyInsertionPolicy(),
                    "cfg": SimConfig(info_mode="full", seed=1, initial_soc=0.35, energy_uncertainty_delta=0.0),
                },
                {
                    "label": "energy_uncert_greedy",
                    "policy": GreedyInsertionPolicy(),
                    "cfg": SimConfig(info_mode="full", seed=1, initial_soc=0.40, energy_uncertainty_delta=0.25),
                },
                {
                    "label": "delay_limited",
                    "policy": LimitedInfoCooperativePolicy(broadcast_period_s=300.0),
                    "cfg": SimConfig(
                        info_mode="restricted",
                        message_delay_s=300.0,
                        seed=1,
                        initial_soc=0.40,
                        energy_uncertainty_delta=0.15,
                    ),
                },
                {
                    "label": "fleet1_greedy",
                    "policy": GreedyInsertionPolicy(),
                    "cfg": SimConfig(info_mode="full", seed=1, n_vehicles=1, energy_uncertainty_delta=0.0),
                },
            ]
        )

    # Paired second seed on reference greedy / limited
    paired = [
        {
            "label": "ref_greedy_seed2",
            "policy": GreedyInsertionPolicy(),
            "cfg": SimConfig(info_mode="full", seed=2, energy_uncertainty_delta=0.0),
        },
        {
            "label": "ref_limited_seed2",
            "policy": LimitedInfoCooperativePolicy(broadcast_period_s=180.0),
            "cfg": SimConfig(info_mode="restricted", message_delay_s=60.0, seed=2),
        },
    ]
    experiments.extend(paired)

    for exp in experiments:
        print(f"  running {exp['label']} ...", flush=True)
        cfg: SimConfig = exp["cfg"]
        cfg.day = scen.day
        sim = OnlineSimulator(
            scenario_id=scen.scenario_id,
            graph=scen.graph or graph,
            model=scen.model or model,
            requests=scen.requests,
            fleet=scen.fleet,
            depot_node=scen.depot_node,
            shift_start_s=scen.shift_start_s,
            shift_end_s=scen.shift_end_s,
            config=cfg,
            policy=exp["policy"],
        )
        row = _run_one(sim)
        row["experiment"] = exp["label"]
        out_rows.append(row)
        print(
            f"    served={row['n_served']}/{row['n_requests']} "
            f"dist_km={row['total_distance_m']/1000:.2f} "
            f"E={row['energy_consumed_kwh']:.2f} "
            f"msgs={row['n_messages']} energy_bind_events={row['energy_changed_dispatch']}",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-casablanca", action="store_true")
    parser.add_argument("--scenario", default="train/baseline_seed1")
    parser.add_argument("--also-stress-scenario", default="train/peak_stress_seed2")
    args = parser.parse_args()

    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    print("=== Synthetic ===", flush=True)
    run_synthetic(rows)

    if not args.skip_casablanca:
        print("=== Casablanca baseline_seed1 ===", flush=True)
        run_casablanca(rows, scenario_rel=args.scenario, stress=True)
        stress_path = scenarios_dir().joinpath(*args.also_stress_scenario.split("/"))
        if stress_path.exists():
            print(f"=== Casablanca {args.also_stress_scenario} (ref policies) ===", flush=True)
            # Reuse network already loaded inside run_casablanca when possible.
            graph = load_drive_graph()
            model = load_congestion_model()
            scen = load_scenario(stress_path, load_network=False, graph=graph, model=model)
            for label, policy, cfg in [
                ("stress_greedy", GreedyInsertionPolicy(), SimConfig(info_mode="full", seed=1)),
                (
                    "stress_rh",
                    RollingHorizonPolicy(time_budget_s=0.2, reoptimize_every_s=1800.0),
                    SimConfig(info_mode="full", seed=1),
                ),
                (
                    "stress_limited",
                    LimitedInfoCooperativePolicy(broadcast_period_s=600.0),
                    SimConfig(info_mode="restricted", message_delay_s=60.0, seed=1),
                ),
            ]:
                print(f"  running {label} ...", flush=True)
                cfg.day = scen.day
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
                    policy=policy,
                )
                row = _run_one(sim)
                row["experiment"] = label
                rows.append(row)
                print(
                    f"    served={row['n_served']}/{row['n_requests']} "
                    f"dist_km={row['total_distance_m']/1000:.2f}",
                    flush=True,
                )

    df = pd.DataFrame(rows)
    csv_path = out_dir / "stage2_baseline_metrics.csv"
    json_path = out_dir / "stage2_baseline_metrics.json"
    df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {csv_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
