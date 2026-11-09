#!/usr/bin/env python
"""Stage 6: frozen-policy comparison on release train + evaluation_v1 (canonical sim)."""

from __future__ import annotations

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
        f"{row['n_served']}/{row['n_requests']} rt={row['policy_runtime_s']:.1f}s",
        flush=True,
    )
    return row


def paired_summary(df: pd.DataFrame, base: str, other: str) -> dict:
    a = df[df.policy_kind == base].set_index(["scenario_key", "suite"])
    b = df[df.policy_kind == other].set_index(["scenario_key", "suite"])
    common = a.index.intersection(b.index)
    if len(common) == 0:
        return {"n": 0}
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
    }


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading network...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

    # Release train scenarios (all 8)
    release_dirs = sorted((scenarios_dir() / "train").iterdir())
    release_dirs = [d for d in release_dirs if d.is_dir()]
    # Evaluation ensemble default tag — peak/tight emphasize energy stress
    eval_root = project_root() / "data" / "casablanca" / "evaluation_v1" / "default"
    eval_dirs = sorted(eval_root.glob("*_seed*")) if eval_root.exists() else []

    scenarios: list[tuple[str, Path]] = []
    for d in release_dirs:
        scenarios.append((f"release/{d.name}", d))
    for d in eval_dirs:
        # Cap runtime: include all baseline eval + first 4 peak + first 4 tight
        name = d.name
        if name.startswith("baseline_"):
            scenarios.append((f"eval/{name}", d))
        elif name.startswith("peak_stress_"):
            seed = int(name.split("seed")[-1])
            if seed <= 1204:
                scenarios.append((f"eval/{name}", d))
        elif name.startswith("tight_windows_"):
            seed = int(name.split("seed")[-1])
            if seed <= 1304:
                scenarios.append((f"eval/{name}", d))

    policies = [
        "greedy_charge_07",
        "greedy_adaptive",
        "greedy_always_full",
        "sf_rh_07",
        "sf_rh_charge_aware",
        "race_rh",
    ]
    suites = [("full_soc", 1.0), ("soc35", 0.35)]

    # Warmup landmarks
    landmarks = []
    loaded = {}
    for key, path in scenarios:
        sc = load_scenario(path, load_network=False, graph=graph, model=model)
        loaded[key] = sc
        landmarks.append(sc.depot_node)
        landmarks.extend(r.snap_node for r in sc.requests)
    router.warmup(landmarks)

    rows: list[dict] = []
    for key, path in scenarios:
        sc = loaded[key]
        for suite_name, soc in suites:
            # Skip expensive race_rh on full_soc eval baselines to save time? Keep all for fairness.
            print(f"\n=== {key} / {suite_name} ===", flush=True)
            for pk in policies:
                # Bound RACE-RH cost: release all + first 2 peak/tight eval at soc35 only
                if pk == "race_rh":
                    if suite_name != "soc35":
                        continue
                    if key.startswith("eval/baseline"):
                        continue
                    if key.startswith("eval/peak_stress_"):
                        seed = int(key.split("seed")[-1])
                        if seed > 1202:
                            continue
                    if key.startswith("eval/tight_windows_"):
                        seed = int(key.split("seed")[-1])
                        if seed > 1302:
                            continue
                if pk == "sf_rh_charge_aware" and suite_name == "full_soc" and key.startswith("eval/"):
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
                row = run_one(sim, f"{key}|{suite_name}|{pk}")
                row.update(
                    scenario_key=key,
                    suite=suite_name,
                    policy_kind=pk,
                    initial_soc=soc,
                    source="release" if key.startswith("release/") else "evaluation_v1",
                    commit="stage6",
                )
                rows.append(row)

    df = pd.DataFrame(rows)
    csv_path = out_dir / "stage6_final_comparison.csv"
    json_path = out_dir / "stage6_final_comparison.json"
    df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    # Paired summaries vs greedy_07 on soc35
    sub = df[df.suite == "soc35"]
    summaries = [
        paired_summary(sub, "greedy_charge_07", "race_rh"),
        paired_summary(sub, "greedy_charge_07", "sf_rh_07"),
        paired_summary(sub, "greedy_charge_07", "sf_rh_charge_aware"),
        paired_summary(sub, "greedy_charge_07", "greedy_adaptive"),
        paired_summary(sub, "greedy_charge_07", "greedy_always_full"),
    ]
    # Aggregate means by policy
    agg = (
        sub.groupby("policy_kind")
        .agg(
            n=("on_time_rate_all", "count"),
            mean_ot=("on_time_rate_all", "mean"),
            std_ot=("on_time_rate_all", "std"),
            mean_served=("n_served", "mean"),
            mean_runtime=("policy_runtime_s", "mean"),
            mean_timeouts=("policy_timeouts", "mean"),
        )
        .reset_index()
    )
    summary = {
        "soc35_policy_means": agg.to_dict(orient="records"),
        "paired_vs_greedy_07": summaries,
        "n_rows": len(df),
        "n_scenario_keys": int(df.scenario_key.nunique()),
    }
    (out_dir / "stage6_final_comparison_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, default=str), flush=True)
    print(f"Wrote {csv_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
