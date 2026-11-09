#!/usr/bin/env python
"""Stage 6 spatial-mixture sensitivity: greedy_07 vs race_rh on peak SOC35."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root
from race_casablanca.policies import ChargingController, GreedyInsertionPolicy, RaceRollingHorizonPolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

    tags = ["default", "spatial_pop80", "spatial_com80", "spatial_neutral"]
    rows = []
    for tag in tags:
        root = project_root() / "data" / "casablanca" / "evaluation_v1" / tag
        peaks = sorted(root.glob("peak_stress_seed120[1-2]"))
        for path in peaks:
            sc = load_scenario(path, load_network=False, graph=graph, model=model)
            router.warmup([sc.depot_node] + [r.snap_node for r in sc.requests])
            for pk, pol in [
                ("greedy_charge_07", GreedyInsertionPolicy(
                    charging=ChargingController(mode="charge_to_target", target_soc=0.70)
                )),
                ("race_rh", RaceRollingHorizonPolicy(time_budget_s=0.5, enable_readiness=True)),
            ]:
                print(f"{tag}/{path.name}/{pk}", flush=True)
                sim = OnlineSimulator(
                    scenario_id=sc.scenario_id,
                    graph=graph,
                    model=model,
                    requests=sc.requests,
                    fleet=sc.fleet,
                    depot_node=sc.depot_node,
                    shift_start_s=sc.shift_start_s,
                    shift_end_s=sc.shift_end_s,
                    config=SimConfig(
                        info_mode="full", seed=1, initial_soc=0.35,
                        energy_uncertainty_delta=0.0, charge_on_return=False, day=sc.day,
                    ),
                    policy=pol,
                    router=router,
                )
                m = sim.run().to_dict()
                rows.append(
                    {
                        "tag": tag,
                        "scenario": path.name,
                        "policy_kind": pk,
                        "on_time_rate_all": m["on_time_rate_all"],
                        "n_served": m["n_served"],
                        "n_requests": m["n_requests"],
                        "note": "hypothetical spatial mixture; not calibrated",
                    }
                )
                print(f"  ot={m['on_time_rate_all']:.3f} {m['n_served']}/{m['n_requests']}", flush=True)

    df = pd.DataFrame(rows)
    path = out_dir / "stage6_sensitivity_spatial.csv"
    df.to_csv(path, index=False)
    summary = (
        df.groupby(["tag", "policy_kind"])["on_time_rate_all"].agg(["mean", "count"]).reset_index()
    )
    (out_dir / "stage6_sensitivity_spatial_summary.json").write_text(
        summary.to_json(orient="records", indent=2), encoding="utf-8"
    )
    print(summary.to_string(index=False), flush=True)
    print(f"Wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
