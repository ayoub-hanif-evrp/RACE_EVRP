#!/usr/bin/env python
"""Matched request-level failure diagnosis: greedy_07 vs race_rh on peak SOC35."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import ChargingController, GreedyInsertionPolicy, RaceRollingHorizonPolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
from race_casablanca.sim.types import RequestStatus


def run_policy(graph, model, router, path, policy, soc=0.35):
    sc = load_scenario(path, load_network=False, graph=graph, model=model)
    router.warmup([sc.depot_node] + [r.snap_node for r in sc.requests])
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
            info_mode="full", seed=1, initial_soc=soc,
            energy_uncertainty_delta=0.0, charge_on_return=False, day=sc.day,
        ),
        policy=policy,
        router=router,
    )
    metrics = sim.run().to_dict()
    outcomes = {
        rid: {
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "on_time": bool(getattr(r, "on_time", False)),
            "owner": r.owner,
            "completed": r.status == RequestStatus.COMPLETED,
        }
        for rid, r in sim.requests.items()
    }
    pol = sim.policy
    search = {
        "n_chose_optimized": int(getattr(pol, "n_chose_optimized", 0) or 0),
        "n_chose_incumbent": int(getattr(pol, "n_chose_incumbent", 0) or 0),
        "n_timeouts": int(getattr(pol, "n_timeouts", 0) or 0),
        "policy_runtime_s": float(getattr(pol, "total_decision_runtime_s", 0.0) or 0.0),
        "n_proactive_charges": int(
            getattr(getattr(pol, "readiness", None), "n_proactive_charges", 0) or 0
        ),
    }
    return metrics, outcomes, search


def classify_diff(g_out, r_out):
    """Where greedy succeeds and RACE fails (or vice versa)."""
    greedy_only = []
    race_only = []
    both_fail = []
    both_ok = []
    for rid in g_out:
        g_ok = g_out[rid]["completed"] and g_out[rid]["on_time"]
        r_ok = r_out[rid]["completed"] and r_out[rid]["on_time"]
        entry = {
            "request_id": rid,
            "greedy_status": g_out[rid]["status"],
            "race_status": r_out[rid]["status"],
            "greedy_owner": g_out[rid]["owner"],
            "race_owner": r_out[rid]["owner"],
        }
        if g_ok and not r_ok:
            greedy_only.append(entry)
        elif r_ok and not g_ok:
            race_only.append(entry)
        elif g_ok and r_ok:
            both_ok.append(rid)
        else:
            both_fail.append(entry)
    return greedy_only, race_only, both_fail, both_ok


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

    scenarios = [
        ("release", scenarios_dir() / "train" / "peak_stress_seed2"),
        ("release", scenarios_dir() / "train" / "peak_stress_seed5"),
        ("release", scenarios_dir() / "train" / "tight_windows_seed3"),
        ("eval", project_root() / "data" / "casablanca" / "evaluation_v1" / "default" / "peak_stress_seed1201"),
        ("eval", project_root() / "data" / "casablanca" / "evaluation_v1" / "default" / "peak_stress_seed1202"),
    ]

    reports = []
    for source, path in scenarios:
        if not path.exists():
            continue
        print(f"Diagnosing {path.name}...", flush=True)
        g_pol = GreedyInsertionPolicy(
            name="greedy_charge_07",
            charging=ChargingController(mode="charge_to_target", target_soc=0.70),
        )
        r_pol = RaceRollingHorizonPolicy(name="race_rh", time_budget_s=0.5, enable_readiness=True)
        g_m, g_out, g_s = run_policy(graph, model, router, path, g_pol)
        r_m, r_out, r_s = run_policy(graph, model, router, path, r_pol)
        greedy_only, race_only, both_fail, both_ok = classify_diff(g_out, r_out)
        reports.append(
            {
                "source": source,
                "scenario": path.name,
                "greedy_ot": g_m["on_time_rate_all"],
                "race_ot": r_m["on_time_rate_all"],
                "greedy_served": f"{g_m['n_served']}/{g_m['n_requests']}",
                "race_served": f"{r_m['n_served']}/{r_m['n_requests']}",
                "delta_ot": r_m["on_time_rate_all"] - g_m["on_time_rate_all"],
                "race_search": r_s,
                "n_greedy_only_success": len(greedy_only),
                "n_race_only_success": len(race_only),
                "n_both_ok": len(both_ok),
                "n_both_fail": len(both_fail),
                "greedy_only_success_requests": greedy_only,
                "race_only_success_requests": race_only,
                "both_fail_requests": both_fail,
                "interpretation": (
                    "RACE search selected optimized plans "
                    f"{r_s['n_chose_optimized']} times vs incumbent {r_s['n_chose_incumbent']}; "
                    "timeouts="
                    f"{r_s['n_timeouts']}. "
                    "Differences are assignment/charging/timing outcomes under identical request streams, "
                    "not simulator nondeterminism (seed fixed)."
                ),
            }
        )

    dest = out_dir / "stage6_failure_diagnosis.json"
    dest.write_text(json.dumps(reports, indent=2, default=str), encoding="utf-8")
    # Flat CSV of mismatched requests
    flat = []
    for rep in reports:
        for kind, key in [
            ("greedy_only", "greedy_only_success_requests"),
            ("race_only", "race_only_success_requests"),
            ("both_fail", "both_fail_requests"),
        ]:
            for e in rep[key]:
                flat.append({"scenario": rep["scenario"], "diff_kind": kind, **e})
    pd.DataFrame(flat).to_csv(out_dir / "stage6_failure_diagnosis_requests.csv", index=False)
    print(json.dumps([{k: r[k] for k in r if k.endswith("_requests") is False} for r in reports], indent=2))
    print(f"Wrote {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
