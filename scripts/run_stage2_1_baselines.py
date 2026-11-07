#!/usr/bin/env python
"""Stage 2.1 one-factor-at-a-time baseline comparisons + energy diagnostic."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root, scenarios_dir
from race_casablanca.policies import (
    GreedyInsertionPolicy,
    LimitedInfoCooperativePolicy,
    RollingHorizonPolicy,
)
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario
from race_casablanca.sim.synthetic import make_two_request_scenario


def _run(sim: OnlineSimulator, experiment: str) -> dict:
    row = sim.run().to_dict()
    row["experiment"] = experiment
    if sim.first_reserve_violation_trace:
        row["first_reserve_violation"] = sim.first_reserve_violation_trace
    print(
        f"  {experiment}: served={row['n_served']}/{row['n_requests']} "
        f"on_time={row['n_on_time']} E={row['energy_consumed_kwh']:.2f} "
        f"reserve_viol={row['battery_reserve_violations']} "
        f"plan_rej={row['planned_energy_rejections']} "
        f"charges={row['n_charges']} msgs={row['n_messages']}",
        flush=True,
    )
    return row


def run_synthetic_charge(rows: list[dict]) -> None:
    base = make_two_request_scenario()
    sim = OnlineSimulator(
        scenario_id=base["scenario_id"],
        graph=base["graph"],
        model=base["model"],
        requests=base["requests"][:1],
        fleet=base["fleet"],
        depot_node=base["depot_node"],
        shift_start_s=base["shift_start_s"],
        shift_end_s=base["shift_end_s"],
        config=SimConfig(info_mode="full", seed=0, initial_soc=0.5, charge_on_return=True),
        policy=GreedyInsertionPolicy(),
    )
    rows.append(_run(sim, "synthetic_charge_on"))


def run_oat(rows: list[dict], traces: dict) -> None:
    print("Loading Casablanca network...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")

    baseline = load_scenario(
        scenarios_dir() / "train" / "baseline_seed1",
        load_network=False,
        graph=graph,
        model=model,
    )
    stress = load_scenario(
        scenarios_dir() / "train" / "peak_stress_seed2",
        load_network=False,
        graph=graph,
        model=model,
    )
    landmarks = (
        [baseline.depot_node, stress.depot_node]
        + [r.snap_node for r in baseline.requests]
        + [r.snap_node for r in stress.requests]
    )
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

    # --- Axis: SOC (hold δ=0, full info, charge off)
    print("=== OAT SOC ===", flush=True)
    for label, soc in [("soc_full_greedy", 1.0), ("soc_low_greedy", 0.35)]:
        rows.append(
            _run(
                make(
                    baseline,
                    GreedyInsertionPolicy(),
                    SimConfig(info_mode="full", seed=1, initial_soc=soc, energy_uncertainty_delta=0.0),
                ),
                label,
            )
        )

    # --- Axis: energy δ at fixed SOC=0.35
    print("=== OAT energy delta ===", flush=True)
    for label, delta in [("delta0_soc035", 0.0), ("delta02_soc035", 0.2)]:
        rows.append(
            _run(
                make(
                    baseline,
                    GreedyInsertionPolicy(),
                    SimConfig(
                        info_mode="full",
                        seed=1,
                        initial_soc=0.35,
                        energy_uncertainty_delta=delta,
                        realization_mode="crn",
                    ),
                ),
                label,
            )
        )

    # --- Axis: info mode at matched SOC/δ
    print("=== OAT info mode ===", flush=True)
    for label, mode, policy, delay in [
        ("info_full_greedy", "full", GreedyInsertionPolicy(), 0.0),
        (
            "info_restricted",
            "restricted",
            LimitedInfoCooperativePolicy(broadcast_period_s=300.0),
            60.0,
        ),
    ]:
        rows.append(
            _run(
                make(
                    baseline,
                    policy,
                    SimConfig(
                        info_mode=mode,
                        seed=1,
                        initial_soc=1.0,
                        energy_uncertainty_delta=0.0,
                        message_delay_s=delay,
                    ),
                ),
                label,
            )
        )

    # --- Axis: communication delay (restricted only)
    print("=== OAT comm delay ===", flush=True)
    for label, delay in [("comm_delay0", 0.0), ("comm_delay300", 300.0)]:
        rows.append(
            _run(
                make(
                    baseline,
                    LimitedInfoCooperativePolicy(broadcast_period_s=300.0),
                    SimConfig(
                        info_mode="restricted",
                        seed=1,
                        initial_soc=1.0,
                        message_delay_s=delay,
                    ),
                ),
                label,
            )
        )

    # --- Axis: charging at low SOC
    print("=== OAT charge ===", flush=True)
    for label, charge in [("charge_off_soc035", False), ("charge_on_soc035", True)]:
        rows.append(
            _run(
                make(
                    baseline,
                    GreedyInsertionPolicy(),
                    SimConfig(
                        info_mode="full",
                        seed=1,
                        initial_soc=0.35,
                        energy_uncertainty_delta=0.0,
                        charge_on_return=charge,
                    ),
                ),
                label,
            )
        )

    # --- RH vs greedy at matched conditions
    print("=== RH vs greedy ===", flush=True)
    rows.append(
        _run(
            make(
                baseline,
                RollingHorizonPolicy(time_budget_s=0.2, reoptimize_every_s=1800.0),
                SimConfig(info_mode="full", seed=1),
            ),
            "rh_baseline",
        )
    )

    # --- Stress: SOC and δ separately + diagnostic combined (documented as interaction)
    print("=== Peak stress OAT ===", flush=True)
    for label, soc, delta in [
        ("stress_soc1_d0", 1.0, 0.0),
        ("stress_soc035_d0", 0.35, 0.0),
        ("stress_soc035_d02", 0.35, 0.2),
        ("stress_soc1_d02", 1.0, 0.2),
    ]:
        sim = make(
            stress,
            GreedyInsertionPolicy(),
            SimConfig(
                info_mode="full",
                seed=1,
                initial_soc=soc,
                energy_uncertainty_delta=delta,
                realization_mode="crn",
            ),
        )
        row = _run(sim, label)
        rows.append(row)
        if sim.first_reserve_violation_trace:
            traces[label] = sim.first_reserve_violation_trace
        # Also save short event trace for low-SOC cases
        if soc < 1.0:
            traces[f"{label}_depart_events"] = [
                e for e in sim.event_trace if e.get("event") in {"depart", "reserve_violation", "emergency_stranded"}
            ][:40]

    # Restricted vs full on stress at matched SOC=1
    rows.append(
        _run(
            make(
                stress,
                LimitedInfoCooperativePolicy(broadcast_period_s=600.0),
                SimConfig(info_mode="restricted", seed=1, message_delay_s=60.0),
            ),
            "stress_restricted",
        )
    )

    # Adversarial worst-case at low SOC — must have zero reserve violations if safe
    print("=== Adversarial worst delta stress ===", flush=True)
    sim = make(
        stress,
        GreedyInsertionPolicy(),
        SimConfig(
            info_mode="full",
            seed=1,
            initial_soc=0.35,
            energy_uncertainty_delta=0.2,
            realization_mode="adversarial_worst",
        ),
    )
    row = _run(sim, "stress_soc035_adversarial")
    rows.append(row)
    if sim.first_reserve_violation_trace:
        traces["stress_soc035_adversarial"] = sim.first_reserve_violation_trace
    traces["stress_soc035_adversarial_events"] = [
        e for e in sim.event_trace if e.get("event") in {"depart", "reserve_violation", "emergency_stranded"}
    ][:50]


def main() -> int:
    rows: list[dict] = []
    traces: dict = {}
    run_synthetic_charge(rows)
    run_oat(rows, traces)

    out = project_root() / "data" / "casablanca" / "online_results"
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "stage2_1_baseline_metrics.csv"
    json_path = out / "stage2_1_baseline_metrics.json"
    trace_path = out / "stage2_1_energy_traces.json"
    # Drop nested traces from CSV-friendly rows
    flat = []
    for r in rows:
        rr = {k: v for k, v in r.items() if k != "first_reserve_violation"}
        flat.append(rr)
    pd.DataFrame(flat).to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    trace_path.write_text(json.dumps(traces, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {csv_path} ({len(rows)} rows)", flush=True)
    print(f"Wrote {trace_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
