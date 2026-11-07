#!/usr/bin/env python
"""Stage 3B: RACE vs strong baselines + opportunity-cost ablation (training scenarios)."""

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
    RaceCommitmentPolicy,
    RollingHorizonPolicy,
)
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def run_one(sim: OnlineSimulator, experiment: str) -> dict:
    row = sim.run().to_dict()
    row["experiment"] = experiment
    pol = sim.policy
    row["use_opportunity_cost"] = bool(getattr(pol, "use_opportunity_cost", None))
    row["rh_time_budget_s"] = sim.config.extras.get("rh_time_budget_s")
    print(
        f"  {experiment}: served={row['n_served']}/{row['n_requests']} "
        f"on_time_all={row['on_time_rate_all']:.3f} "
        f"E={row['energy_consumed_kwh']:.2f} dist_km={row['total_distance_m']/1000:.2f} "
        f"reserve={row['battery_reserve_violations']} strand={row['battery_exhaustion']} "
        f"charges={row['n_charges']} reassign={row['n_reassignments']} "
        f"dec_ms={1000*row['mean_decision_runtime_s']:.1f}",
        flush=True,
    )
    return row


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading Casablanca network...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

    scenarios = {
        "baseline_seed1": load_scenario(
            scenarios_dir() / "train" / "baseline_seed1", load_network=False, graph=graph, model=model
        ),
        "peak_stress_seed2": load_scenario(
            scenarios_dir() / "train" / "peak_stress_seed2", load_network=False, graph=graph, model=model
        ),
        "tight_windows_seed3": load_scenario(
            scenarios_dir() / "train" / "tight_windows_seed3", load_network=False, graph=graph, model=model
        ),
    }
    landmarks = []
    for sc in scenarios.values():
        landmarks.append(sc.depot_node)
        landmarks.extend(r.snap_node for r in sc.requests)
    router.warmup(landmarks)

    def make(scen, policy, cfg: SimConfig):
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
            router=router,
        )

    rows: list[dict] = []

    # Matched policy suite under identical exogenous settings
    suites = [
        ("full_soc", dict(initial_soc=1.0, energy_uncertainty_delta=0.0, realization_mode="crn")),
        ("soc35", dict(initial_soc=0.35, energy_uncertainty_delta=0.0, realization_mode="crn")),
        ("soc35_delta20", dict(initial_soc=0.35, energy_uncertainty_delta=0.20, realization_mode="adversarial_worst")),
    ]

    policies = [
        ("greedy", lambda: GreedyInsertionPolicy(), "full"),
        ("robust_greedy", lambda: GreedyInsertionPolicy(), "full"),  # same gate; labeled for clarity
        ("rolling_horizon", lambda: RollingHorizonPolicy(time_budget_s=0.25), "full"),
        ("race", lambda: RaceCommitmentPolicy(use_opportunity_cost=True), "full"),
        ("race_ablation", lambda: RaceCommitmentPolicy(use_opportunity_cost=False, allow_reassign=False), "full"),
        ("restricted_none", lambda: LimitedInfoCooperativePolicy(comm_mode="none"), "restricted"),
    ]

    for scen_key, scen in scenarios.items():
        for suite_name, suite_kw in suites:
            # Skip expensive low-SOC tight combo redundancy slightly: still run all for honesty
            print(f"=== {scen_key} / {suite_name} ===", flush=True)
            for pol_name, pol_factory, info_mode in policies:
                if pol_name == "robust_greedy":
                    # identical to greedy; keep one row alias for report tables
                    continue
                cfg = SimConfig(
                    info_mode=info_mode,
                    seed=1,
                    message_delay_s=0.0,
                    periodic_broadcast_s=0.0,
                    charge_on_return=False,
                    **suite_kw,
                )
                exp = f"{scen_key}__{suite_name}__{pol_name}"
                rows.append(run_one(make(scen, pol_factory(), cfg), exp))

    # Charging-enabled stress probe (peak, SOC 35%)
    print("=== charging probe (peak_stress, soc35) ===", flush=True)
    stress = scenarios["peak_stress_seed2"]
    for pol_name, pol_factory, info_mode in [
        ("greedy", lambda: GreedyInsertionPolicy(), "full"),
        ("race", lambda: RaceCommitmentPolicy(use_opportunity_cost=True), "full"),
    ]:
        cfg = SimConfig(
            info_mode=info_mode,
            seed=1,
            initial_soc=0.35,
            energy_uncertainty_delta=0.0,
            charge_on_return=True,
        )
        rows.append(run_one(make(stress, pol_factory(), cfg), f"peak_stress_seed2__soc35_charge__{pol_name}"))

    df = pd.DataFrame(rows)
    csv_path = out_dir / "stage3b_race_metrics.csv"
    json_path = out_dir / "stage3b_race_metrics.json"
    cfg_path = out_dir / "stage3b_experiment_config.json"
    df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    cfg_path.write_text(
        json.dumps(
            {
                "stage": "3B",
                "scenarios": list(scenarios.keys()),
                "suites": [s[0] for s in suites],
                "policies": [p[0] for p in policies if p[0] != "robust_greedy"],
                "rh_time_budget_s": 0.25,
                "race_defaults": {
                    "alpha_energy": 240.0,
                    "beta_time": 0.5,
                    "e_typical_kwh": 2.0,
                    "t_typical_s": 900.0,
                    "charge_flex_threshold_kwh": 3.0,
                },
                "seed": 1,
                "dataset": "casablanca_release_v1",
                "notes": "Training scenarios only; not tuned on test.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {csv_path}", flush=True)
    print(f"Wrote {json_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
