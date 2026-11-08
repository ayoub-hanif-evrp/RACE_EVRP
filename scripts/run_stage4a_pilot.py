#!/usr/bin/env python
"""Stage 4A pilot: post-decision RACE vs charge-aware and rollout baselines."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.demand.synthetic_futures import SyntheticFutureModel
from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import (
    ChargingController,
    GreedyInsertionPolicy,
    OneStepRolloutPolicy,
    RacePostDecisionPolicy,
    ServiceFirstRollingHorizonPolicy,
)
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def run_one(sim: OnlineSimulator, experiment: str) -> dict:
    row = sim.run().to_dict()
    row["experiment"] = experiment
    pol = sim.policy
    row["lookahead_runtime_s"] = float(getattr(pol, "total_lookahead_runtime_s", 0.0) or 0.0)
    row["n_decision_log"] = len(getattr(pol, "decision_log", []) or [])
    print(
        f"  {experiment}: served={row['n_served']}/{row['n_requests']} "
        f"on_time_all={row['on_time_rate_all']:.3f} "
        f"E={row['energy_consumed_kwh']:.2f} chg={row['n_charges']} "
        f"LA_s={row['lookahead_runtime_s']:.1f} "
        f"reserve={row['battery_reserve_violations']}",
        flush=True,
    )
    return row


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading network + synthetic future model (train only)...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")
    future_model = SyntheticFutureModel.from_training()

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

    def make_pol(kind: str):
        if kind == "greedy_adaptive":
            return GreedyInsertionPolicy(charging=ChargingController(mode="adaptive_headroom"))
        if kind == "greedy_always":
            return GreedyInsertionPolicy(charging=ChargingController(mode="always_on_return"))
        if kind == "service_first_rh":
            return ServiceFirstRollingHorizonPolicy(
                time_budget_s=0.35, charging=ChargingController(mode="adaptive_headroom")
            )
        if kind == "one_step_rollout":
            return OneStepRolloutPolicy(
                n_samples=2,
                n_synthetic_requests=3,
                max_claim_candidates=6,
                future_model=future_model,
                seed=1,
            )
        if kind == "race_pd":
            return RacePostDecisionPolicy(
                n_samples=2,
                n_synthetic_requests=3,
                max_claim_candidates=6,
                max_charge_candidates=2,
                enable_future_eval=True,
                enable_charge_actions=True,
                lookahead_horizon_s=2400.0,
                future_model=future_model,
                seed=1,
            )
        if kind == "race_pd_no_future":
            return RacePostDecisionPolicy(
                enable_future_eval=False,
                enable_charge_actions=True,
                future_model=future_model,
                seed=1,
            )
        if kind == "race_pd_no_charge":
            return RacePostDecisionPolicy(
                n_samples=2,
                n_synthetic_requests=3,
                max_claim_candidates=6,
                max_charge_candidates=0,
                enable_future_eval=True,
                enable_charge_actions=False,
                lookahead_horizon_s=2400.0,
                future_model=future_model,
                seed=1,
            )
        raise ValueError(kind)

    rows: list[dict] = []
    suites = [
        ("full_soc", dict(initial_soc=1.0, energy_uncertainty_delta=0.0)),
        ("soc35", dict(initial_soc=0.35, energy_uncertainty_delta=0.0)),
    ]
    # Heavy anticipatory policies only on peak + baseline soc35 to bound runtime
    light = ["greedy_adaptive", "greedy_always", "service_first_rh", "race_pd_no_future"]
    heavy = ["one_step_rollout", "race_pd", "race_pd_no_charge"]

    for sid, scen in scenarios.items():
        for suite_name, suite_kw in suites:
            pols = list(light)
            if sid in {"baseline_seed1", "peak_stress_seed2"} and suite_name in {"full_soc", "soc35"}:
                pols = light + heavy
            elif sid == "tight_windows_seed3" and suite_name == "soc35":
                pols = light + ["race_pd"]  # one heavy check
            print(f"=== {sid} / {suite_name} ===", flush=True)
            for pol_name in pols:
                cfg = SimConfig(info_mode="full", seed=1, charge_on_return=False, **suite_kw)
                rows.append(
                    run_one(make(scen, make_pol(pol_name), cfg), f"{sid}__{suite_name}__{pol_name}")
                )

    df = pd.DataFrame(rows)
    csv_path = out_dir / "stage4a_pilot_metrics.csv"
    json_path = out_dir / "stage4a_pilot_metrics.json"
    cfg_path = out_dir / "stage4a_experiment_config.json"
    df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    cfg_path.write_text(
        json.dumps(
            {
                "stage": "4A",
                "scenarios": scen_ids,
                "suites": [s[0] for s in suites],
                "n_samples": 2,
                "n_synthetic_requests": 3,
                "lookahead_horizon_s": 2400.0,
                "future_model": "SyntheticFutureModel.from_training",
                "future_model_sources": list(future_model.source_scenarios),
                "seed": 1,
                "dataset": "casablanca_release_v1",
                "notes": "Pilot only; Stage 3C FAIL preserved. No test tuning.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {csv_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
