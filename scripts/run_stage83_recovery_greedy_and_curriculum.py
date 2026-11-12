#!/usr/bin/env python
"""Append greedy charge-to-70% to Stage 8.3 recovery table + document curriculum stages A–F."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-vehicles", type=int, default=3)
    args = parser.parse_args()

    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.policies import ChargingController, GreedyInsertionPolicy
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
    from race_casablanca.sim.types import RequestStatus

    root = project_root()
    out = root / "data" / "casablanca" / "online_results"
    graph = load_drive_graph()
    model = load_congestion_model()
    paths = resolve_eval_dirs()

    rows = []
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        reqs = deepcopy(sc.requests)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        pol = GreedyInsertionPolicy(
            charging=ChargingController(mode="charge_to_target", target_soc=0.70)
        )
        sim = OnlineSimulator(
            scenario_id=f"{sc.scenario_id}/greedy70",
            graph=graph,
            model=model,
            requests=reqs,
            fleet={**sc.fleet, "n_vehicles": args.n_vehicles},
            depot_node=sc.depot_node,
            shift_start_s=sc.shift_start_s,
            shift_end_s=sc.shift_end_s,
            config=SimConfig(
                info_mode="full",
                seed=0,
                initial_soc=0.35,
                n_vehicles=args.n_vehicles,
                message_delay_s=0.0,
                day=str(getattr(sc, "day", "Monday")),
            ),
            policy=pol,
        )
        m = sim.run().to_dict()
        rows.append(
            {
                "scenario": path.name,
                "ablation": "greedy_charge70",
                "ot": float(m["on_time_rate_all"]),
                "n_bid_bytes": 0.0,
                "n_bid_messages": 0.0,
                "n_decisions": float(m.get("n_decisions", 0)),
                "seed": -1,
                "stage": "greedy_charge70",
            }
        )
        print("greedy", path.name, rows[-1]["ot"], flush=True)

    gdf = pd.DataFrame(rows)
    recovery_path = out / "stage83_recovery_study.csv"
    if recovery_path.exists():
        big = pd.read_csv(recovery_path)
        # drop prior greedy rows if re-run
        big = big[big["stage"] != "greedy_charge70"]
        big = pd.concat([big, gdf], ignore_index=True)
    else:
        big = gdf
    big.to_csv(recovery_path, index=False)

    summary = (
        big.groupby("stage")[["ot", "n_bid_bytes", "n_bid_messages"]]
        .agg(["mean", "std"])
        .reset_index()
    )
    summary.columns = ["_".join(c).strip("_") for c in summary.columns.values]
    summary.to_csv(out / "stage83_recovery_summary_table.csv", index=False)

    js_path = out / "stage83_recovery_summary.json"
    js = json.loads(js_path.read_text(encoding="utf-8")) if js_path.exists() else {}
    js["by_stage"] = (
        big.groupby("stage")["ot"].agg(["mean", "std", "count"]).reset_index().to_dict(orient="records")
    )
    js["curriculum"] = {
        "A_imitate_validated_teacher": "NativeBridgeTeacher intent + weighted BC (stage83_bc_dagger_*)",
        "B_eval_before_RL": "bc_dagger_native_bridge row in recovery (~0.629 mean)",
        "C_mappo_no_comm": "mappo_A freeze_comm, val-selected",
        "D_full_peer_bids": "mappo_D / env ablation D_selective (certificates change masks/features)",
        "E_selective_byte_budget": "mappo_F from A with selective energy-certified gate; E strips peer energy",
        "F_limited_joint_finetune": "10 MAPPO iters F/C/E/D from A; seed-2 shows catastrophic forgetting risk",
        "greedy_reference": "centralized greedy charge-to-70% appended as greedy_charge70",
    }
    js_path.write_text(json.dumps(js, indent=2), encoding="utf-8")
    (out / "stage83_curriculum_map.json").write_text(json.dumps(js["curriculum"], indent=2), encoding="utf-8")
    print(json.dumps(js["by_stage"], indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
