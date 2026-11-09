#!/usr/bin/env python
"""Compact Milestone-1 delayed pilot (skips full@delay>0)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")
    scenarios = [
        scenarios_dir() / "train" / "peak_stress_seed2",
        scenarios_dir() / "train" / "tight_windows_seed3",
        project_root() / "data/casablanca/evaluation_v1/default/peak_stress_seed1201",
        project_root() / "data/casablanca/evaluation_v1/default/peak_stress_seed1202",
        project_root() / "data/casablanca/evaluation_v1/default/peak_stress_seed1203",
        project_root() / "data/casablanca/evaluation_v1/default/tight_windows_seed1301",
    ]
    rows = []
    for path in scenarios:
        if not path.exists():
            continue
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        router.warmup([sc.depot_node] + [r.snap_node for r in sc.requests])
        for delay in (0.0, 30.0):
            selective_msgs = 0
            modes = ["none", "selective", "periodic"] + (["full"] if delay == 0.0 else [])
            for mode in modes:
                pol = RaceCooperativePolicy(comm_mode=mode, enable_readiness_charge=True, rng_seed=7)
                print(f"{path.name}/d{int(delay)}/{mode}", flush=True)
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
                        info_mode="restricted",
                        seed=1,
                        initial_soc=0.35,
                        message_delay_s=delay,
                        periodic_broadcast_s=300.0 if mode == "periodic" else 0.0,
                        periodic_state_broadcast=False,
                        day=sc.day,
                    ),
                    policy=pol,
                    router=router,
                )
                m = sim.run().to_dict()
                if mode == "selective":
                    selective_msgs = int(pol.n_messages_sent_by_policy)
                rows.append(
                    {
                        "scenario": path.name,
                        "delay_s": delay,
                        "comm_mode": mode,
                        "on_time_rate_all": m["on_time_rate_all"],
                        "n_served": m["n_served"],
                        "n_requests": m["n_requests"],
                        "policy_msgs": pol.n_messages_sent_by_policy,
                        "bid_msgs": sim.n_bid_messages,
                        "cf_changes": pol.n_counterfactual_decision_changes,
                        "state_msgs": sim.n_state_broadcast_messages,
                    }
                )
                print(f"  ot={m['on_time_rate_all']:.3f} msgs={pol.n_messages_sent_by_policy} cf={pol.n_counterfactual_decision_changes}", flush=True)
            pol = RaceCooperativePolicy(
                comm_mode="random_matched",
                matched_message_budget=selective_msgs,
                enable_readiness_charge=True,
                rng_seed=11,
            )
            print(f"{path.name}/d{int(delay)}/random_matched budget={selective_msgs}", flush=True)
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
                    info_mode="restricted",
                    seed=1,
                    initial_soc=0.35,
                    message_delay_s=delay,
                    periodic_state_broadcast=False,
                    day=sc.day,
                ),
                policy=pol,
                router=router,
            )
            m = sim.run().to_dict()
            rows.append(
                {
                    "scenario": path.name,
                    "delay_s": delay,
                    "comm_mode": "random_matched",
                    "on_time_rate_all": m["on_time_rate_all"],
                    "n_served": m["n_served"],
                    "n_requests": m["n_requests"],
                    "policy_msgs": pol.n_messages_sent_by_policy,
                    "bid_msgs": sim.n_bid_messages,
                    "cf_changes": pol.n_counterfactual_decision_changes,
                    "state_msgs": sim.n_state_broadcast_messages,
                    "matched_budget": selective_msgs,
                }
            )
    df = pd.DataFrame(rows)
    csv = out_dir / "race_comm_pilot_v2.csv"
    df.to_csv(csv, index=False)
    summary = {}
    for delay, g in df.groupby("delay_s"):
        summary[str(delay)] = (
            g.groupby("comm_mode")[["on_time_rate_all", "policy_msgs", "cf_changes"]]
            .mean()
            .reset_index()
            .to_dict(orient="records")
        )
    (out_dir / "race_comm_pilot_v2_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Wrote {csv}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
