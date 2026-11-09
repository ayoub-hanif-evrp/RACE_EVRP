#!/usr/bin/env python
"""First-milestone RACE-COMM pilot: same assignment rule, varied communication modes.

Paired small set: release train peak/tight + a few eval peaks. No MARL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import GreedyInsertionPolicy, ChargingController, RaceCooperativePolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def make_coop(mode: str) -> RaceCooperativePolicy:
    return RaceCooperativePolicy(
        comm_mode=mode,
        enable_readiness_charge=True,
        charge_target_soc=0.70,
        random_p_send=0.25,
        rng_seed=7,
    )


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

    scenarios = [
        ("release", scenarios_dir() / "train" / "peak_stress_seed2"),
        ("release", scenarios_dir() / "train" / "tight_windows_seed3"),
        ("eval", project_root() / "data/casablanca/evaluation_v1/default/peak_stress_seed1201"),
        ("eval", project_root() / "data/casablanca/evaluation_v1/default/peak_stress_seed1202"),
    ]
    modes = ["none", "periodic", "full", "random", "selective"]
    suites = [("soc35", 0.35), ("full_soc", 1.0)]

    rows = []
    for source, path in scenarios:
        if not path.exists():
            continue
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        router.warmup([sc.depot_node] + [r.snap_node for r in sc.requests])
        for suite, soc in suites:
            # External full-info greedy reference
            for label, policy, info_mode, delay, period in [
                (
                    "greedy_charge_07_fullinfo",
                    GreedyInsertionPolicy(
                        charging=ChargingController(mode="charge_to_target", target_soc=0.70)
                    ),
                    "full",
                    0.0,
                    None,
                ),
            ]:
                print(f"{path.name}/{suite}/{label}", flush=True)
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
                        info_mode=info_mode,
                        seed=1,
                        initial_soc=soc,
                        message_delay_s=delay,
                        periodic_broadcast_s=period,
                        charge_on_return=False,
                        day=sc.day,
                    ),
                    policy=policy,
                    router=router,
                )
                m = sim.run().to_dict()
                rows.append(
                    {
                        "source": source,
                        "scenario": path.name,
                        "suite": suite,
                        "policy": label,
                        "comm_mode": "n/a",
                        "on_time_rate_all": m["on_time_rate_all"],
                        "n_served": m["n_served"],
                        "n_requests": m["n_requests"],
                        "n_messages": m["n_messages"],
                        "n_bid_messages": getattr(sim, "n_bid_messages", 0),
                        "n_bid_bytes": getattr(sim, "n_bid_bytes", 0),
                        "policy_msgs": 0,
                        "cf_changes": 0,
                        "defers": 0,
                        "reserve_viol": m["battery_reserve_violations"],
                        "exhaustion": m["battery_exhaustion"],
                    }
                )

            for mode in modes:
                pol = make_coop(mode)
                print(f"{path.name}/{suite}/race_coop:{mode}", flush=True)
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
                        initial_soc=soc,
                        # Zero delay enables same-tick two-phase bid→assign rounds.
                        message_delay_s=0.0,
                        periodic_broadcast_s=300.0 if mode == "periodic" else None,
                        charge_on_return=False,
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
                        "suite": suite,
                        "policy": f"race_cooperative:{mode}",
                        "comm_mode": mode,
                        "on_time_rate_all": m["on_time_rate_all"],
                        "n_served": m["n_served"],
                        "n_requests": m["n_requests"],
                        "n_messages": m["n_messages"],
                        "n_bid_messages": sim.n_bid_messages,
                        "n_bid_bytes": sim.n_bid_bytes,
                        "policy_msgs": pol.n_messages_sent_by_policy,
                        "cf_changes": pol.n_counterfactual_decision_changes,
                        "defers": pol.n_defers_to_peer,
                        "reserve_viol": m["battery_reserve_violations"],
                        "exhaustion": m["battery_exhaustion"],
                    }
                )
                print(
                    f"  ot={m['on_time_rate_all']:.3f} msgs={pol.n_messages_sent_by_policy} "
                    f"cf={pol.n_counterfactual_decision_changes} defers={pol.n_defers_to_peer}",
                    flush=True,
                )

    df = pd.DataFrame(rows)
    csv_path = out_dir / "race_comm_pilot.csv"
    df.to_csv(csv_path, index=False)

    # Paired vs none on soc35 cooperative modes
    sub = df[(df.suite == "soc35") & (df.comm_mode != "n/a")].copy()
    summary = {"soc35_by_mode": [], "paired_vs_none": []}
    for mode, g in sub.groupby("comm_mode"):
        summary["soc35_by_mode"].append(
            {
                "comm_mode": mode,
                "mean_ot": float(g.on_time_rate_all.mean()),
                "mean_policy_msgs": float(g.policy_msgs.mean()),
                "mean_bid_messages": float(g.n_bid_messages.mean()),
                "mean_cf_changes": float(g.cf_changes.mean()),
                "n": int(len(g)),
            }
        )
    base = sub[sub.comm_mode == "none"].set_index("scenario")
    for mode in ["periodic", "full", "random", "selective"]:
        other = sub[sub.comm_mode == mode].set_index("scenario")
        common = base.index.intersection(other.index)
        if len(common) == 0:
            continue
        diff = (other.loc[common, "on_time_rate_all"] - base.loc[common, "on_time_rate_all"]).astype(float)
        summary["paired_vs_none"].append(
            {
                "mode": mode,
                "n": int(len(common)),
                "mean_delta_ot": float(diff.mean()),
                "mean_msgs": float(other.loc[common, "policy_msgs"].mean()),
                "mean_cf_changes": float(other.loc[common, "cf_changes"].mean()),
            }
        )

    (out_dir / "race_comm_pilot_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Wrote {csv_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
