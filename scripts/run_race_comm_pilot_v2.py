#!/usr/bin/env python
"""Milestone-1 larger non-learning RACE-COMM pilot with delay / fairness fixes.

Uses task-bid-only periodic mode (no generic state floods), matched random budget,
and delays {0, 30}.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import ChargingController, GreedyInsertionPolicy, RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

    scenarios = []
    for d in sorted((scenarios_dir() / "train").iterdir()):
        if d.is_dir() and ("peak" in d.name or "tight" in d.name):
            scenarios.append(("release", d))
    eval_root = project_root() / "data/casablanca/evaluation_v1/default"
    for seed in range(1201, 1209):
        p = eval_root / f"peak_stress_seed{seed}"
        if p.exists():
            scenarios.append(("eval", p))
    for seed in range(1301, 1305):
        p = eval_root / f"tight_windows_seed{seed}"
        if p.exists():
            scenarios.append(("eval", p))

    delays = [0.0, 30.0]
    rows = []
    for source, path in scenarios:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        router.warmup([sc.depot_node] + [r.snap_node for r in sc.requests])
        for delay in delays:
            # 1) selective first to set matched budget
            # Skip full bidding when delay>0: event-queue blow-up from per-decision floods.
            modes_pass1 = ["none", "selective", "periodic"]
            if delay <= 1e-12:
                modes_pass1.insert(2, "full")
            selective_msgs = 0
            for mode in modes_pass1:
                pol = RaceCooperativePolicy(
                    comm_mode=mode, enable_readiness_charge=True, rng_seed=7
                )
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
                        "source": source,
                        "scenario": path.name,
                        "delay_s": delay,
                        "comm_mode": mode,
                        "on_time_rate_all": m["on_time_rate_all"],
                        "n_served": m["n_served"],
                        "n_requests": m["n_requests"],
                        "policy_msgs": pol.n_messages_sent_by_policy,
                        "bid_msgs": sim.n_bid_messages,
                        "bid_bytes": sim.n_bid_bytes,
                        "state_msgs": sim.n_state_broadcast_messages,
                        "cf_changes": pol.n_counterfactual_decision_changes,
                        "defers": pol.n_defers_to_peer,
                        "packets_dropped": sim.n_packets_dropped,
                    }
                )
                print(
                    f"  ot={m['on_time_rate_all']:.3f} msgs={pol.n_messages_sent_by_policy} "
                    f"cf={pol.n_counterfactual_decision_changes}",
                    flush=True,
                )

            # matched random
            pol = RaceCooperativePolicy(
                comm_mode="random_matched",
                matched_message_budget=max(0, selective_msgs),
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
                    "source": source,
                    "scenario": path.name,
                    "delay_s": delay,
                    "comm_mode": "random_matched",
                    "on_time_rate_all": m["on_time_rate_all"],
                    "n_served": m["n_served"],
                    "n_requests": m["n_requests"],
                    "policy_msgs": pol.n_messages_sent_by_policy,
                    "bid_msgs": sim.n_bid_messages,
                    "bid_bytes": sim.n_bid_bytes,
                    "state_msgs": sim.n_state_broadcast_messages,
                    "cf_changes": pol.n_counterfactual_decision_changes,
                    "defers": pol.n_defers_to_peer,
                    "packets_dropped": sim.n_packets_dropped,
                    "matched_budget": selective_msgs,
                }
            )

            # greedy reference once per scenario/delay
            g = GreedyInsertionPolicy(
                charging=ChargingController(mode="charge_to_target", target_soc=0.70)
            )
            sim = OnlineSimulator(
                scenario_id=sc.scenario_id,
                graph=graph,
                model=model,
                requests=sc.requests,
                fleet=sc.fleet,
                depot_node=sc.depot_node,
                shift_start_s=sc.shift_start_s,
                shift_end_s=sc.shift_end_s,
                config=SimConfig(info_mode="full", seed=1, initial_soc=0.35, day=sc.day),
                policy=g,
                router=router,
            )
            m = sim.run().to_dict()
            rows.append(
                {
                    "source": source,
                    "scenario": path.name,
                    "delay_s": delay,
                    "comm_mode": "greedy_fullinfo",
                    "on_time_rate_all": m["on_time_rate_all"],
                    "n_served": m["n_served"],
                    "n_requests": m["n_requests"],
                    "policy_msgs": 0,
                    "bid_msgs": 0,
                    "bid_bytes": 0,
                    "state_msgs": 0,
                    "cf_changes": 0,
                    "defers": 0,
                    "packets_dropped": 0,
                }
            )

    df = pd.DataFrame(rows)
    path = out_dir / "race_comm_pilot_v2.csv"
    df.to_csv(path, index=False)
    summary = {}
    for delay, g in df.groupby("delay_s"):
        sub = g[g.comm_mode != "greedy_fullinfo"]
        summary[str(delay)] = (
            sub.groupby("comm_mode")[["on_time_rate_all", "policy_msgs", "cf_changes", "bid_msgs"]]
            .mean()
            .reset_index()
            .to_dict(orient="records")
        )
    (out_dir / "race_comm_pilot_v2_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
