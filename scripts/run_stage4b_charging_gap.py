#!/usr/bin/env python
"""Stage 4B diagnostic: equalized discrete target-SOC charging gap (train only)."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import (
    ChargingController,
    GreedyInsertionPolicy,
    ServiceFirstRollingHorizonPolicy,
)
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
from race_casablanca.sim.types import RequestStatus


def _miss_reason_tags(sim: OnlineSimulator) -> dict[str, int]:
    tags: Counter[str] = Counter()
    for e in sim.event_trace:
        if e.get("event") == "pickup_missed":
            tags[str(e.get("reason", "deadline_on_arrival"))] += 1
        if e.get("event") == "emergency_stranded":
            tags["energy"] += 1
    for r in sim.requests.values():
        if r.status == RequestStatus.EXPIRED:
            tags["expired_unserved"] += 1
        elif r.status == RequestStatus.MISSED:
            tags["deadline_on_arrival"] += 1
        elif r.status == RequestStatus.REJECTED:
            tags["rejected"] += 1
    return dict(tags)


def run_one(sim: OnlineSimulator, experiment: str) -> dict:
    m = sim.run()
    row = m.to_dict()
    row["experiment"] = experiment
    row["miss_tags"] = _miss_reason_tags(sim)
    print(
        f"  {experiment}: ot_all={row['on_time_rate_all']:.3f} "
        f"served={row['n_served']}/{row['n_requests']} "
        f"missed={row.get('n_missed', 0)} exp={row['n_expired']} "
        f"E={row['energy_consumed_kwh']:.1f} "
        f"deliv={row.get('energy_delivered_kwh', 0):.1f} "
        f"chg_s={row.get('charge_duration_s', 0):.0f} "
        f"n_chg={row['n_charges']}",
        flush=True,
    )
    return row


def make_policy(kind: str):
    if kind == "greedy_adaptive_full":
        return GreedyInsertionPolicy(
            name="greedy_adaptive_full",
            charging=ChargingController(mode="adaptive_headroom", target_soc=1.0),
        )
    if kind == "greedy_always_full":
        return GreedyInsertionPolicy(
            name="greedy_always_full",
            charging=ChargingController(mode="always_on_return", target_soc=1.0),
        )
    if kind == "greedy_charge_07":
        return GreedyInsertionPolicy(
            name="greedy_charge_07",
            charging=ChargingController(mode="charge_to_target", target_soc=0.70),
        )
    if kind == "service_first_rh_adaptive":
        return ServiceFirstRollingHorizonPolicy(
            name="service_first_rh_adaptive",
            time_budget_s=0.35,
            charging=ChargingController(mode="adaptive_headroom", target_soc=1.0),
        )
    if kind == "service_first_rh_07":
        return ServiceFirstRollingHorizonPolicy(
            name="service_first_rh_07",
            time_budget_s=0.35,
            charging=ChargingController(mode="charge_to_target", target_soc=0.70),
        )
    raise KeyError(kind)


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading network (Stage 4B charging gap, train only)...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

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

    policies = [
        "greedy_adaptive_full",
        "greedy_always_full",
        "greedy_charge_07",
        "service_first_rh_adaptive",
        "service_first_rh_07",
    ]
    suites = [
        ("full_soc", 1.0, 0.0),
        ("soc35", 0.35, 0.0),
        ("soc35_delta02", 0.35, 0.2),  # one δ stress row
    ]

    rows: list[dict] = []
    for sid, scen in scenarios.items():
        for suite_name, init_soc, delta in suites:
            # δ stress only on peak (cheap)
            if suite_name == "soc35_delta02" and sid != "peak_stress_seed2":
                continue
            print(f"\n=== {sid} / {suite_name} ===", flush=True)
            for pk in policies:
                cfg = SimConfig(
                    info_mode="full",
                    seed=1,
                    initial_soc=init_soc,
                    energy_uncertainty_delta=delta,
                    charge_on_return=False,
                    day=scen.day,
                )
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
                    policy=make_policy(pk),
                    router=router,
                )
                row = run_one(sim, f"{sid}|{suite_name}|{pk}")
                row["scenario"] = sid
                row["suite"] = suite_name
                row["policy_kind"] = pk
                row["initial_soc"] = init_soc
                row["delta"] = delta
                rows.append(row)

    df = pd.DataFrame(rows)
    csv_path = out_dir / "stage4b_charging_gap.csv"
    json_path = out_dir / "stage4b_charging_gap.json"
    # miss_tags is dict — stringify for csv
    df_csv = df.copy()
    if "miss_tags" in df_csv.columns:
        df_csv["miss_tags"] = df_csv["miss_tags"].apply(json.dumps)
    df_csv.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {csv_path}", flush=True)
    print(f"Wrote {json_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
