#!/usr/bin/env python
"""Stage 3A: paired communication-value experiment (same restricted dispatch rule)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import GreedyInsertionPolicy, LimitedInfoCooperativePolicy, RollingHorizonPolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def run_one(sim: OnlineSimulator, experiment: str) -> dict:
    row = sim.run().to_dict()
    row["experiment"] = experiment
    pol = sim.policy
    row["policy_messages"] = getattr(pol, "n_messages_sent_by_policy", 0)
    row["decision_changing_msg_heuristic"] = getattr(pol, "n_decision_changing_messages", 0)
    print(
        f"  {experiment}: served={row['n_served']}/{row['n_requests']} "
        f"E={row['energy_consumed_kwh']:.2f} msgs={row['n_messages']} "
        f"claims={row['n_claims']} reserve={row['battery_reserve_violations']}",
        flush=True,
    )
    return row


def main() -> int:
    print("Loading network...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")
    baseline = load_scenario(
        scenarios_dir() / "train" / "baseline_seed1", load_network=False, graph=graph, model=model
    )
    stress = load_scenario(
        scenarios_dir() / "train" / "peak_stress_seed2", load_network=False, graph=graph, model=model
    )
    router.warmup(
        [baseline.depot_node, stress.depot_node]
        + [r.snap_node for r in baseline.requests]
        + [r.snap_node for r in stress.requests]
    )

    rows: list[dict] = []

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

    # Metric integrity check: full greedy claims ≈ served
    print("=== Metric integrity (baseline) ===", flush=True)
    rows.append(
        run_one(
            make(baseline, GreedyInsertionPolicy(), SimConfig(info_mode="full", seed=1)),
            "metric_full_greedy",
        )
    )

    # Communication triad on peak stress (same restricted dispatch rule)
    # Hold: SOC=1, δ=0, delay=60s for message delivery when messages exist
    print("=== Communication triad (peak_stress, matched dispatch) ===", flush=True)
    for label, mode, period in [
        ("stress_comm_none", "none", 0.0),
        ("stress_comm_periodic", "periodic", 300.0),
        ("stress_comm_triggered", "decision_triggered", 0.0),
    ]:
        rows.append(
            run_one(
                make(
                    stress,
                    LimitedInfoCooperativePolicy(comm_mode=mode),
                    SimConfig(
                        info_mode="restricted",
                        seed=1,
                        message_delay_s=60.0,
                        periodic_broadcast_s=period,
                        energy_uncertainty_delta=0.0,
                        initial_soc=1.0,
                    ),
                ),
                label,
            )
        )

    # Same triad on baseline
    print("=== Communication triad (baseline_seed1) ===", flush=True)
    for label, mode, period in [
        ("base_comm_none", "none", 0.0),
        ("base_comm_periodic", "periodic", 300.0),
        ("base_comm_triggered", "decision_triggered", 0.0),
    ]:
        rows.append(
            run_one(
                make(
                    baseline,
                    LimitedInfoCooperativePolicy(comm_mode=mode),
                    SimConfig(
                        info_mode="restricted",
                        seed=1,
                        message_delay_s=60.0,
                        periodic_broadcast_s=period,
                    ),
                ),
                label,
            )
        )

    # Reference full-info baselines (not message-value estimates)
    print("=== Full-info references (stress) ===", flush=True)
    rows.append(
        run_one(
            make(stress, GreedyInsertionPolicy(), SimConfig(info_mode="full", seed=1)),
            "stress_full_greedy_ref",
        )
    )
    rows.append(
        run_one(
            make(
                stress,
                RollingHorizonPolicy(time_budget_s=0.2, reoptimize_every_s=1800.0),
                SimConfig(info_mode="full", seed=1),
            ),
            "stress_full_rh_ref",
        )
    )

    # Energy-active setting with matched CRN: SOC 0.35, triad
    print("=== Communication triad under low SOC (stress) ===", flush=True)
    for label, mode, period in [
        ("stress_low_comm_none", "none", 0.0),
        ("stress_low_comm_periodic", "periodic", 300.0),
        ("stress_low_comm_triggered", "decision_triggered", 0.0),
    ]:
        rows.append(
            run_one(
                make(
                    stress,
                    LimitedInfoCooperativePolicy(comm_mode=mode),
                    SimConfig(
                        info_mode="restricted",
                        seed=1,
                        initial_soc=0.35,
                        energy_uncertainty_delta=0.0,
                        message_delay_s=60.0,
                        periodic_broadcast_s=period,
                        realization_mode="crn",
                    ),
                ),
                label,
            )
        )

    out = project_root() / "data" / "casablanca" / "online_results"
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "stage3a_communication_metrics.csv"
    json_path = out / "stage3a_communication_metrics.json"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    meta = {
        "source_commit_hint": "Stage3A local run",
        "scenarios": ["train/baseline_seed1", "train/peak_stress_seed2"],
        "seed": 1,
        "note": "Same restricted_claim_pass dispatch for none/periodic/triggered.",
    }
    (out / "stage3a_experiment_config.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Wrote {csv_path} ({len(rows)} rows)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
