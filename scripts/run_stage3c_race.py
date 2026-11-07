#!/usr/bin/env python
"""Stage 3C: fair charging, marginal-cost baselines, 2x2 RACE ablation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import (
    ChargingController,
    GreedyInsertionPolicy,
    RaceCommitmentPolicy,
    RollingHorizonPolicy,
)
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def make_policy(kind: str, charge_mode: str = "adaptive_headroom"):
    ch = ChargingController(mode=charge_mode, headroom_threshold_kwh=3.0)
    if kind == "greedy":
        return GreedyInsertionPolicy(charging=ch)
    if kind == "rolling_horizon":
        return RollingHorizonPolicy(time_budget_s=0.25, charging=ch)
    if kind == "A":
        return RaceCommitmentPolicy(
            name="race_A_no_price_no_reassign",
            use_flexibility_pricing=False,
            allow_reassign=False,
            charging=ch,
        )
    if kind == "B":
        return RaceCommitmentPolicy(
            name="race_B_price_only",
            use_flexibility_pricing=True,
            allow_reassign=False,
            pricing_mode="inverse_slack",
            charging=ch,
        )
    if kind == "C":
        return RaceCommitmentPolicy(
            name="race_C_reassign_only",
            use_flexibility_pricing=False,
            allow_reassign=True,
            charging=ch,
        )
    if kind == "D":
        return RaceCommitmentPolicy(
            name="race_D_full",
            use_flexibility_pricing=True,
            allow_reassign=True,
            pricing_mode="inverse_slack",
            charging=ch,
        )
    if kind == "fixed_weight":
        return RaceCommitmentPolicy(
            name="race_fixed_weight",
            use_flexibility_pricing=True,
            allow_reassign=False,
            pricing_mode="fixed_weight",
            charging=ch,
        )
    raise ValueError(kind)


def run_one(sim: OnlineSimulator, experiment: str) -> dict:
    row = sim.run().to_dict()
    row["experiment"] = experiment
    pol = sim.policy
    row["charge_mode"] = getattr(getattr(pol, "charging", None), "mode", None)
    row["use_flexibility_pricing"] = getattr(pol, "use_flexibility_pricing", None)
    row["allow_reassign"] = getattr(pol, "allow_reassign", None)
    row["pricing_mode"] = getattr(pol, "pricing_mode", None)
    row["rh_time_budget_s"] = sim.config.extras.get("rh_time_budget_s")
    traces = getattr(pol, "decision_traces", None) or []
    row["n_flex_differing_decisions"] = len(traces)
    row["decision_trace_sample"] = traces[:5]
    # Driving energy already in energy_consumed_kwh; charging recovered approximated via charges
    row["n_charges"] = row.get("n_charges", 0)
    print(
        f"  {experiment}: served={row['n_served']}/{row['n_requests']} "
        f"on_time_all={row['on_time_rate_all']:.3f} "
        f"E={row['energy_consumed_kwh']:.2f} dist_km={row['total_distance_m']/1000:.2f} "
        f"chg={row['n_charges']} re={row['n_reassignments']} "
        f"flex_diff={row['n_flex_differing_decisions']} "
        f"reserve={row['battery_reserve_violations']}",
        flush=True,
    )
    return row


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading Casablanca network...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

    train_ids = [
        "baseline_seed1",
        "baseline_seed4",
        "peak_stress_seed2",
        "peak_stress_seed5",
        "tight_windows_seed3",
        "tight_windows_seed6",
    ]
    scenarios = {}
    for sid in train_ids:
        scenarios[sid] = load_scenario(
            scenarios_dir() / "train" / sid, load_network=False, graph=graph, model=model
        )

    # Validation scenarios if present
    val_dir = scenarios_dir() / "validation"
    val_ids = sorted(p.name for p in val_dir.iterdir() if p.is_dir())[:2] if val_dir.exists() else []
    for sid in val_ids:
        scenarios[f"val::{sid}"] = load_scenario(
            val_dir / sid, load_network=False, graph=graph, model=model
        )

    landmarks = []
    for sc in scenarios.values():
        landmarks.append(sc.depot_node)
        landmarks.extend(r.snap_node for r in sc.requests)
    router.warmup(landmarks)

    def make(scen, policy, cfg: SimConfig):
        cfg.day = scen.day
        return OnlineSimulator(
            scenario_id=scen.scenario_id,
            graph=graph,
            model=model,
            requests=scen.requests,
            fleet=scen.fleet,
            depot_node=scen.depot_node,
            shift_start_s=scen.shift_start_s,
            shift_end_s=scen.shift_end_s,
            config=cfg,
            policy=policy,
            router=router,
        )

    rows: list[dict] = []
    suites = [
        ("full_soc", dict(initial_soc=1.0, energy_uncertainty_delta=0.0, realization_mode="crn")),
        ("soc35", dict(initial_soc=0.35, energy_uncertainty_delta=0.0, realization_mode="crn")),
        ("soc35_delta20", dict(initial_soc=0.35, energy_uncertainty_delta=0.20, realization_mode="adversarial_worst")),
    ]
    primary_policies = ["greedy", "rolling_horizon", "A", "B", "C", "D", "fixed_weight"]

    # Primary fair comparison: adaptive charging for all
    for scen_key in train_ids:
        scen = scenarios[scen_key]
        for suite_name, suite_kw in suites:
            print(f"=== TRAIN {scen_key} / {suite_name} / adaptive ===", flush=True)
            for pol_name in primary_policies:
                cfg = SimConfig(
                    info_mode="full",
                    seed=1,
                    charge_on_return=False,  # per-decision controller only
                    **suite_kw,
                )
                exp = f"{scen_key}__{suite_name}__adaptive__{pol_name}"
                rows.append(run_one(make(scen, make_policy(pol_name, "adaptive_headroom"), cfg), exp))

    # Auxiliaries on peak_stress_seed2
    stress = scenarios["peak_stress_seed2"]
    for charge_mode in ("none", "always_on_return"):
        print(f"=== AUX peak_stress_seed2 / soc35 / {charge_mode} ===", flush=True)
        for pol_name in ("greedy", "D"):
            cfg = SimConfig(
                info_mode="full",
                seed=1,
                initial_soc=0.35,
                energy_uncertainty_delta=0.0,
                # Episode default stays False; controller issues explicit charge=True
                charge_on_return=False,
            )
            exp = f"peak_stress_seed2__soc35__{charge_mode}__{pol_name}"
            rows.append(run_one(make(stress, make_policy(pol_name, charge_mode), cfg), exp))

    # Limited validation check (no tuning)
    for key in [k for k in scenarios if k.startswith("val::")]:
        scen = scenarios[key]
        print(f"=== VALIDATION {key} / soc35 / adaptive ===", flush=True)
        for pol_name in ("greedy", "rolling_horizon", "D"):
            cfg = SimConfig(
                info_mode="full",
                seed=1,
                initial_soc=0.35,
                energy_uncertainty_delta=0.0,
                charge_on_return=False,
            )
            exp = f"{key}__soc35__adaptive__{pol_name}"
            rows.append(run_one(make(scen, make_policy(pol_name, "adaptive_headroom"), cfg), exp))

    # Collect decision traces from D runs
    all_traces = []
    for r in rows:
        for t in r.get("decision_trace_sample") or []:
            all_traces.append({"experiment": r["experiment"], **t})

    df = pd.DataFrame(rows)
    # Drop bulky nested sample from CSV friendliness
    csv_df = df.drop(columns=["decision_trace_sample"], errors="ignore")
    csv_path = out_dir / "stage3c_race_metrics.csv"
    json_path = out_dir / "stage3c_race_metrics.json"
    cfg_path = out_dir / "stage3c_experiment_config.json"
    trace_path = out_dir / "stage3c_decision_traces.json"
    csv_df.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    trace_path.write_text(json.dumps(all_traces, indent=2), encoding="utf-8")
    cfg_path.write_text(
        json.dumps(
            {
                "stage": "3C",
                "train_scenarios": train_ids,
                "validation_scenarios": val_ids,
                "suites": [s[0] for s in suites],
                "primary_charge_mode": "adaptive_headroom",
                "headroom_threshold_kwh": 3.0,
                "policies": primary_policies,
                "rh_time_budget_s": 0.25,
                "seed": 1,
                "dataset": "casablanca_release_v1",
                "notes": "Marginal insertion costs; shared adaptive charging; 2x2 ablation.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {csv_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
