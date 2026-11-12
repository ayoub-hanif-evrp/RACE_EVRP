#!/usr/bin/env python
"""Stage 8.3 Task 2: native RaceCooperativePolicy vs CooperativeTeacherAdapter-in-MARL.

Same scenarios, SOC, delay. Records OT / served / decisions / messages.
If the adapter-in-MARL is near 49% while native is ~83%, the gap is environment/interface.
"""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def run_native(sc, graph, model, *, n_vehicles: int, soc: float, delay: float, mode: str = "selective"):
    from race_casablanca.policies import RaceCooperativePolicy
    from race_casablanca.sim.environment import OnlineSimulator, SimConfig
    from race_casablanca.sim.types import RequestStatus

    reqs = deepcopy(sc.requests)
    for r in reqs:
        r.status = RequestStatus.UNRELEASED
        r.owner = None
    pol = RaceCooperativePolicy(comm_mode=mode, enable_readiness_charge=True, rng_seed=7)
    sim = OnlineSimulator(
        scenario_id=f"{sc.scenario_id}/native_{mode}",
        graph=graph,
        model=model,
        requests=reqs,
        fleet={**sc.fleet, "n_vehicles": n_vehicles},
        depot_node=sc.depot_node,
        shift_start_s=sc.shift_start_s,
        shift_end_s=sc.shift_end_s,
        config=SimConfig(
            info_mode="restricted",
            seed=0,
            initial_soc=soc,
            n_vehicles=n_vehicles,
            message_delay_s=delay,
            packet_loss_p=0.0,
            periodic_state_broadcast=False,
            decision_on_release=True,
            day=str(getattr(sc, "day", "Monday")),
        ),
        policy=pol,
    )
    m = sim.run().to_dict()
    return {
        "family": "native",
        "method": f"native_{mode}",
        "on_time_rate_all": float(m["on_time_rate_all"]),
        "n_served": float(m["n_served"]),
        "n_on_time": float(m["n_on_time"]),
        "n_requests": float(m["n_requests"]),
        "n_decisions": float(m.get("n_decisions", 0)),
        "n_bid_messages": float(getattr(sim, "n_bid_messages", 0)),
        "n_bid_bytes": float(getattr(sim, "n_bid_bytes", 0) or getattr(pol, "n_bid_bytes_sent", 0)),
        "policy_msgs": float(pol.n_messages_sent_by_policy),
        "n_claims_success": float(pol.n_claims_success),
        "n_defers_to_peer": float(pol.n_defers_to_peer),
    }


def run_adapter_marl(sc, graph, model, *, n_vehicles: int, soc: float, delay: float, ablation: str):
    from race_casablanca.marl.bc import CooperativeTeacherAdapter, cooperative_teacher_actions
    from race_casablanca.marl.env import RaceMultiAgentEnv
    from race_casablanca.sim.types import RequestStatus

    reqs0 = deepcopy(sc.requests)

    def factory(seed: int = 0, n_vehicles: int = n_vehicles):
        reqs = deepcopy(reqs0)
        for r in reqs:
            r.status = RequestStatus.UNRELEASED
            r.owner = None
        return {
            "scenario_id": f"{sc.scenario_id}/adapter",
            "graph": graph,
            "model": model,
            "requests": reqs,
            "fleet": {**sc.fleet, "n_vehicles": n_vehicles},
            "depot_node": sc.depot_node,
            "shift_start_s": sc.shift_start_s,
            "shift_end_s": sc.shift_end_s,
            "day": getattr(sc, "day", "Monday"),
        }

    env = RaceMultiAgentEnv(
        scenario_factory=factory,
        n_vehicles=n_vehicles,
        initial_soc=soc,
        message_delay_s=delay,
        ablation=ablation,
        seed=0,
        max_decisions=2000,
    )
    adapter = CooperativeTeacherAdapter()
    steps = env.reset(seed=0)
    adapter.reset()
    reasons = []
    while True:
        labels = cooperative_teacher_actions(env, adapter)
        steps = env.step(labels)
        info = list(steps.values())[0].info
        reasons.append(info.get("decision_reason", ""))
        if list(steps.values())[0].done:
            break
    m = env.final_metrics()
    from collections import Counter

    rc = Counter(reasons)
    return {
        "family": "adapter_marl",
        "method": f"adapter_{ablation}",
        "on_time_rate_all": float(m.get("on_time_rate_all", 0.0)),
        "n_served": float(m.get("n_served", 0.0)),
        "n_on_time": float(m.get("n_on_time", 0.0)),
        "n_requests": float(m.get("n_requests", 0.0)),
        "n_decisions": float(m.get("n_decisions", 0.0)),
        "n_bid_messages": float(m.get("n_bid_messages", 0.0)),
        "n_bid_bytes": float(m.get("n_bid_bytes", 0.0)),
        "n_op_claims": float(m.get("n_op_claims", 0.0)),
        "n_op_charge": float(m.get("n_op_charge", 0.0)),
        "n_decision_service_end": float(m.get("n_decision_service_end", 0.0)),
        "n_decision_vehicle_idle": float(m.get("n_decision_vehicle_idle", 0.0)),
        "n_decision_charge_end": float(m.get("n_decision_charge_end", 0.0)),
        "n_decision_release": float(m.get("n_decision_release", 0.0)),
        "reason_counts": dict(rc),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-vehicles", type=int, default=3)
    parser.add_argument("--soc", type=float, default=0.35)
    args = parser.parse_args()

    from race_casablanca.marl.scenarios import resolve_eval_dirs
    from race_casablanca.paths import project_root
    from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario

    root = project_root()
    out_dir = root / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading network...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    paths = resolve_eval_dirs()
    rows = []
    cases = [
        ("selective", "D_selective", 0.0),
        ("selective", "D_selective", 30.0),
        ("none", "A_no_comm", 0.0),
        ("full", "B_full_comm", 0.0),
    ]
    for path in paths:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        for mode, abl, delay in cases:
            if mode == "full" and delay > 0:
                continue
            print(f"parity {path.name} native={mode} adapter={abl} d={delay}", flush=True)
            n = run_native(sc, graph, model, n_vehicles=args.n_vehicles, soc=args.soc, delay=delay, mode=mode)
            n["scenario"] = path.name
            n["delay_s"] = delay
            n["soc"] = args.soc
            rows.append(n)
            a = run_adapter_marl(
                sc, graph, model, n_vehicles=args.n_vehicles, soc=args.soc, delay=delay, ablation=abl
            )
            a["scenario"] = path.name
            a["delay_s"] = delay
            a["soc"] = args.soc
            rows.append(a)

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "stage83_teacher_parity.csv", index=False)

    # Paired gaps: adapter D vs native selective at delay 0
    gaps = []
    for scen, g in df[(df.delay_s == 0) & (df.soc == args.soc)].groupby("scenario"):
        nat = g[g.method == "native_selective"]
        ada = g[g.method == "adapter_D_selective"]
        if nat.empty or ada.empty:
            continue
        gaps.append(
            {
                "scenario": scen,
                "native_ot": float(nat.iloc[0]["on_time_rate_all"]),
                "adapter_ot": float(ada.iloc[0]["on_time_rate_all"]),
                "ot_gap": float(nat.iloc[0]["on_time_rate_all"] - ada.iloc[0]["on_time_rate_all"]),
                "native_decisions": float(nat.iloc[0]["n_decisions"]),
                "adapter_decisions": float(ada.iloc[0]["n_decisions"]),
                "adapter_service_end_decisions": float(ada.iloc[0].get("n_decision_service_end", 0)),
                "adapter_idle_decisions": float(ada.iloc[0].get("n_decision_vehicle_idle", 0)),
            }
        )
    gdf = pd.DataFrame(gaps)
    gdf.to_csv(out_dir / "stage83_teacher_parity_gaps.csv", index=False)
    summary = {
        "mean_native_selective_ot": float(gdf["native_ot"].mean()) if len(gdf) else None,
        "mean_adapter_ot": float(gdf["adapter_ot"].mean()) if len(gdf) else None,
        "mean_ot_gap": float(gdf["ot_gap"].mean()) if len(gdf) else None,
        "mean_adapter_decisions": float(gdf["adapter_decisions"].mean()) if len(gdf) else None,
        "mean_native_decisions": float(gdf["native_decisions"].mean()) if len(gdf) else None,
        "n_scenarios": int(len(gdf)),
    }
    (out_dir / "stage83_teacher_parity_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print("PASS teacher parity artifacts written", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
