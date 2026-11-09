#!/usr/bin/env python
"""Stage 6 complete: fair frozen-policy comparison on release train + full evaluation_v1/default.

Supports checkpoint resume. Locked_final is NEVER used here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import (
    ChargingController,
    GreedyInsertionPolicy,
    RaceRollingHorizonPolicy,
    ServiceFirstRollingHorizonPolicy,
)
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def make_policy(kind: str):
    if kind == "greedy_charge_07":
        return GreedyInsertionPolicy(
            name=kind, charging=ChargingController(mode="charge_to_target", target_soc=0.70)
        )
    if kind == "greedy_adaptive":
        return GreedyInsertionPolicy(
            name=kind, charging=ChargingController(mode="adaptive_headroom", target_soc=1.0)
        )
    if kind == "greedy_always_full":
        return GreedyInsertionPolicy(
            name=kind, charging=ChargingController(mode="always_on_return", target_soc=1.0)
        )
    if kind == "sf_rh_07":
        return ServiceFirstRollingHorizonPolicy(
            name=kind,
            time_budget_s=0.35,
            charging=ChargingController(mode="charge_to_target", target_soc=0.70),
            enable_readiness=True,
        )
    if kind == "sf_rh_charge_aware":
        return ServiceFirstRollingHorizonPolicy(
            name=kind, time_budget_s=0.35, optimize_charges=True, enable_readiness=True
        )
    if kind == "race_rh":
        return RaceRollingHorizonPolicy(
            name=kind, time_budget_s=0.5, enable_readiness=True, readiness_target_soc=0.70
        )
    raise KeyError(kind)


def run_one(sim: OnlineSimulator, experiment: str) -> dict:
    m = sim.run()
    row = m.to_dict()
    row["experiment"] = experiment
    pol = sim.policy
    row["policy_timeouts"] = int(getattr(pol, "n_timeouts", 0) or 0)
    row["policy_runtime_s"] = float(getattr(pol, "total_decision_runtime_s", 0.0) or 0.0)
    row["n_chose_optimized"] = int(getattr(pol, "n_chose_optimized", 0) or 0)
    row["n_chose_incumbent"] = int(getattr(pol, "n_chose_incumbent", 0) or 0)
    row["n_proactive_charges"] = int(
        getattr(getattr(pol, "readiness", None), "n_proactive_charges", 0) or 0
    )
    print(
        f"  {experiment}: ot={row['on_time_rate_all']:.3f} "
        f"{row['n_served']}/{row['n_requests']} rt={row['policy_runtime_s']:.1f}s "
        f"opt={row['n_chose_optimized']} to={row['policy_timeouts']}",
        flush=True,
    )
    return row


def paired_summary(df: pd.DataFrame, base: str, other: str) -> dict:
    a = df[df.policy_kind == base].set_index(["scenario_key", "suite"])
    b = df[df.policy_kind == other].set_index(["scenario_key", "suite"])
    common = a.index.intersection(b.index)
    if len(common) == 0:
        return {"n": 0, "base": base, "other": other}
    da = a.loc[common, "on_time_rate_all"].astype(float)
    db = b.loc[common, "on_time_rate_all"].astype(float)
    diff = (db - da).to_numpy()
    n = len(diff)
    mean = float(np.mean(diff))
    se = float(np.std(diff, ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    return {
        "base": base,
        "other": other,
        "n_paired": n,
        "mean_diff_ot": mean,
        "se_diff_ot": se,
        "ci95_low": mean - 1.96 * se,
        "ci95_high": mean + 1.96 * se,
        "other_wins": int(np.sum(diff > 1e-12)),
        "ties": int(np.sum(np.abs(diff) <= 1e-12)),
        "base_wins": int(np.sum(diff < -1e-12)),
        "mean_base_ot": float(da.mean()),
        "mean_other_ot": float(db.mean()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true", default=True)
    parser.add_argument("--soc35-only-race", action="store_true", default=False,
                        help="If set, skip race_rh on full_soc (still fair within soc35).")
    args = parser.parse_args()

    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "stage6_final_comparison.csv"
    ckpt_path = out_dir / "stage6_final_comparison_checkpoint.json"

    done_keys: set[str] = set()
    rows: list[dict] = []
    if args.resume and csv_path.exists():
        prev = pd.read_csv(csv_path)
        rows = prev.to_dict(orient="records")
        for r in rows:
            done_keys.add(f"{r['scenario_key']}|{r['suite']}|{r['policy_kind']}")
        print(f"Resuming with {len(done_keys)} completed runs", flush=True)

    print("Loading network...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

    release_dirs = [d for d in sorted((scenarios_dir() / "train").iterdir()) if d.is_dir()]
    eval_root = project_root() / "data" / "casablanca" / "evaluation_v1" / "default"
    eval_dirs = sorted(eval_root.glob("*_seed*")) if eval_root.exists() else []

    scenarios: list[tuple[str, Path]] = []
    for d in release_dirs:
        scenarios.append((f"release/{d.name}", d))
    for d in eval_dirs:
        scenarios.append((f"eval/{d.name}", d))

    policies = [
        "greedy_charge_07",
        "greedy_adaptive",
        "greedy_always_full",
        "sf_rh_07",
        "sf_rh_charge_aware",
        "race_rh",
    ]
    suites = [("full_soc", 1.0), ("soc35", 0.35)]

    landmarks = []
    loaded = {}
    for key, path in scenarios:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        loaded[key] = sc
        landmarks.append(sc.depot_node)
        landmarks.extend(r.snap_node for r in sc.requests)
    router.warmup(landmarks)
    print(f"Scenarios loaded: {len(scenarios)}", flush=True)

    for key, path in scenarios:
        sc = loaded[key]
        for suite_name, soc in suites:
            print(f"\n=== {key} / {suite_name} ===", flush=True)
            for pk in policies:
                exp_key = f"{key}|{suite_name}|{pk}"
                if exp_key in done_keys:
                    continue
                if pk == "race_rh" and args.soc35_only_race and suite_name != "soc35":
                    continue
                cfg = SimConfig(
                    info_mode="full",
                    seed=1,
                    initial_soc=soc,
                    energy_uncertainty_delta=0.0,
                    charge_on_return=False,
                    day=sc.day,
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
                    config=cfg,
                    policy=make_policy(pk),
                    router=router,
                )
                row = run_one(sim, exp_key)
                row.update(
                    scenario_key=key,
                    suite=suite_name,
                    policy_kind=pk,
                    initial_soc=soc,
                    source="release" if key.startswith("release/") else "evaluation_v1",
                    commit="stage6_complete",
                )
                rows.append(row)
                done_keys.add(exp_key)
                # checkpoint after each run
                pd.DataFrame(rows).to_csv(csv_path, index=False)
                ckpt_path.write_text(
                    json.dumps({"n_done": len(done_keys), "last": exp_key}, indent=2),
                    encoding="utf-8",
                )

    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)
    (out_dir / "stage6_final_comparison.json").write_text(
        json.dumps(rows, indent=2, default=str), encoding="utf-8"
    )

    # Summaries: overall soc35 and eval-only soc35
    summaries = {}
    for label, sub in [
        ("all_soc35", df[df.suite == "soc35"]),
        ("eval_soc35", df[(df.suite == "soc35") & (df.source == "evaluation_v1")]),
        ("release_soc35", df[(df.suite == "soc35") & (df.source == "release")]),
        ("all_full_soc", df[df.suite == "full_soc"]),
    ]:
        if sub.empty:
            continue
        paired = [
            paired_summary(sub, "greedy_charge_07", other)
            for other in [
                "race_rh",
                "sf_rh_07",
                "sf_rh_charge_aware",
                "greedy_adaptive",
                "greedy_always_full",
            ]
        ]
        agg = (
            sub.groupby("policy_kind")
            .agg(
                n=("on_time_rate_all", "count"),
                mean_ot=("on_time_rate_all", "mean"),
                std_ot=("on_time_rate_all", "std"),
                mean_served=("n_served", "mean"),
                mean_distance_m=("total_distance_m", "mean"),
                mean_energy_kwh=("energy_consumed_kwh", "mean"),
                mean_charge_kwh=("energy_delivered_kwh", "mean"),
                mean_charge_s=("charge_duration_s", "mean"),
                mean_reserve_viol=("battery_reserve_violations", "mean"),
                mean_exhaustion=("battery_exhaustion", "mean"),
                mean_late_missed=("n_missed", "mean"),
                mean_expired=("n_expired", "mean"),
                mean_rejected=("n_rejected", "mean"),
                mean_runtime=("policy_runtime_s", "mean"),
                mean_timeouts=("policy_timeouts", "mean"),
                mean_opt_chosen=("n_chose_optimized", "mean"),
                mean_incumbent=("n_chose_incumbent", "mean"),
            )
            .reset_index()
        )
        summaries[label] = {
            "policy_means": agg.to_dict(orient="records"),
            "paired_vs_greedy_07": paired,
        }

    summary = {
        "n_rows": len(df),
        "n_scenario_keys": int(df.scenario_key.nunique()),
        "fairness_note": "All frozen policies on all release-train + evaluation_v1/default scenarios; locked_final unused.",
        "slices": summaries,
    }
    (out_dir / "stage6_final_comparison_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({"n_rows": len(df), "n_scenarios": int(df.scenario_key.nunique())}, indent=2), flush=True)
    print(f"Wrote {csv_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
