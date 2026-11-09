#!/usr/bin/env python
"""Stage 6 sensitivity suite (all hypothetical; not calibrated to courier data)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root
from race_casablanca.policies import ChargingController, GreedyInsertionPolicy, RaceRollingHorizonPolicy
from race_casablanca.sim.environment import OnlineSimulator, SimConfig
from race_casablanca.sim.router import RouteCache
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def policies():
    return [
        (
            "greedy_charge_07",
            GreedyInsertionPolicy(
                charging=ChargingController(mode="charge_to_target", target_soc=0.70)
            ),
        ),
        ("race_rh", RaceRollingHorizonPolicy(time_budget_s=0.5, enable_readiness=True)),
    ]


def run_pair(graph, model, router, path: Path, tag: str, factor: str, soc: float, delta: float, n_veh=None):
    rows = []
    sc = load_scenario(path, load_network=False, graph=graph, model=model)
    router.warmup([sc.depot_node] + [r.snap_node for r in sc.requests])
    fleet = dict(sc.fleet)
    if n_veh is not None:
        fleet = dict(fleet)
        fleet["n_vehicles"] = int(n_veh)
    for pk, pol in policies():
        print(f"{factor}/{tag}/{path.name}/{pk} soc={soc} nveh={fleet.get('n_vehicles')}", flush=True)
        sim = OnlineSimulator(
            scenario_id=sc.scenario_id,
            graph=graph,
            model=model,
            requests=sc.requests,
            fleet=fleet,
            depot_node=sc.depot_node,
            shift_start_s=sc.shift_start_s,
            shift_end_s=sc.shift_end_s,
            config=SimConfig(
                info_mode="full",
                seed=1,
                initial_soc=soc,
                energy_uncertainty_delta=delta,
                charge_on_return=False,
                day=sc.day,
                n_vehicles=n_veh,
            ),
            policy=pol,
            router=router,
        )
        m = sim.run().to_dict()
        rows.append(
            {
                "factor": factor,
                "tag": tag,
                "scenario": path.name,
                "policy_kind": pk,
                "initial_soc": soc,
                "energy_uncertainty_delta": delta,
                "n_vehicles": int(fleet.get("n_vehicles", 3)),
                "on_time_rate_all": m["on_time_rate_all"],
                "n_served": m["n_served"],
                "n_requests": m["n_requests"],
                "total_distance_m": m["total_distance_m"],
                "energy_consumed_kwh": m["energy_consumed_kwh"],
                "energy_delivered_kwh": m["energy_delivered_kwh"],
                "battery_reserve_violations": m["battery_reserve_violations"],
                "note": "hypothetical sensitivity; not calibrated",
            }
        )
        print(f"  ot={m['on_time_rate_all']:.3f} {m['n_served']}/{m['n_requests']}", flush=True)
    return rows


def main() -> int:
    out_dir = project_root() / "data" / "casablanca" / "online_results"
    out_dir.mkdir(parents=True, exist_ok=True)
    graph = load_drive_graph()
    model = load_congestion_model()
    router = RouteCache(graph, model, day="Monday")
    rows: list[dict] = []

    # 1) Spatial mixture — peak seeds 1201-1204 across tags
    for tag in ["default", "spatial_pop80", "spatial_com80", "spatial_neutral"]:
        root = project_root() / "data" / "casablanca" / "evaluation_v1" / tag
        if not root.exists():
            continue
        for path in sorted(root.glob("peak_stress_seed120[1-4]")):
            rows.extend(run_pair(graph, model, router, path, tag, "spatial_mixture", 0.35, 0.0))

    # 2) Hourly intensity / informative candidates — dedicated tags if present
    for tag, factor in [
        ("hourly_flat", "hourly_profile"),
        ("candidates_informative", "candidate_categories"),
    ]:
        root = project_root() / "data" / "casablanca" / "evaluation_v1" / tag
        if not root.exists():
            continue
        for path in sorted(root.glob("peak_stress_seed120[1-4]")):
            rows.extend(run_pair(graph, model, router, path, tag, factor, 0.35, 0.0))

    # 3) Workload / windows via default regimes on seeds 1201-1202 and 1301-1302
    default = project_root() / "data" / "casablanca" / "evaluation_v1" / "default"
    for path in sorted(list(default.glob("baseline_seed110[1-2]"))
                       + list(default.glob("peak_stress_seed120[1-2]"))
                       + list(default.glob("tight_windows_seed130[1-2]"))):
        rows.extend(run_pair(graph, model, router, path, "default", "workload_regime", 0.35, 0.0))

    # 4) Fleet size on peak 1201-1202
    for path in sorted(default.glob("peak_stress_seed120[1-2]")):
        for nveh in (2, 3, 4):
            rows.extend(
                run_pair(graph, model, router, path, f"fleet_{nveh}", "fleet_size", 0.35, 0.0, n_veh=nveh)
            )

    # 5) Initial SOC + energy uncertainty on peak 1201-1202
    for path in sorted(default.glob("peak_stress_seed120[1-2]")):
        for soc, delta, tag in [
            (1.0, 0.0, "soc100_d0"),
            (0.35, 0.0, "soc35_d0"),
            (0.35, 0.10, "soc35_d10"),
            (0.50, 0.0, "soc50_d0"),
        ]:
            rows.extend(run_pair(graph, model, router, path, tag, "soc_energy", soc, delta))

    df = pd.DataFrame(rows)
    path = out_dir / "stage6_sensitivity_full.csv"
    df.to_csv(path, index=False)
    # Also keep spatial-only summary path for backward compatibility
    spatial = df[df.factor == "spatial_mixture"]
    spatial.to_csv(out_dir / "stage6_sensitivity_spatial.csv", index=False)

    summary = (
        df.groupby(["factor", "tag", "policy_kind"])["on_time_rate_all"]
        .agg(["mean", "count", "std"])
        .reset_index()
    )
    (out_dir / "stage6_sensitivity_full_summary.json").write_text(
        summary.to_json(orient="records", indent=2), encoding="utf-8"
    )
    (out_dir / "stage6_sensitivity_spatial_summary.json").write_text(
        spatial.groupby(["tag", "policy_kind"])["on_time_rate_all"]
        .agg(["mean", "count"])
        .reset_index()
        .to_json(orient="records", indent=2),
        encoding="utf-8",
    )
    print(summary.to_string(index=False), flush=True)
    print(f"Wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
