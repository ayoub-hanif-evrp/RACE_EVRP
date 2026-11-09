#!/usr/bin/env python
"""Generate casablanca_evaluation_v1: new seeds from frozen generator (not new real data).

Writes under data/casablanca/evaluation_v1/. Does not modify casablanca_release_v1 scenarios.
Witness certification is skipped for speed; scenarios are labeled uncertified_statistical.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.demand.generator import (
    generate_requests,
    load_demand_config,
    load_demand_zone_weights,
    zone_sampling_weights_from_table,
)
from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import (
    candidates_dir,
    config_dir,
    fleet_dir,
    project_root,
    zones_dir,
)

# Pre-registered evaluation seeds (disjoint from release train 1–8, val 101–102, test 201–203)
EVAL_SEEDS = {
    "baseline": list(range(1101, 1121)),  # 20
    "peak_stress": list(range(1201, 1221)),
    "tight_windows": list(range(1301, 1321)),
}
# Locked final-evaluation seeds (registered, not generated in this script by default)
LOCKED_FINAL_SEEDS = {
    "baseline": list(range(2101, 2131)),
    "peak_stress": list(range(2201, 2231)),
    "tight_windows": list(range(2301, 2331)),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-regime", type=int, default=8, help="How many seeds to materialize now (≤20)")
    parser.add_argument("--spatial-alpha", type=float, default=None, help="Override population weight")
    parser.add_argument("--tag", default="default", help="Subfolder tag for sensitivity variants")
    args = parser.parse_args()

    config = load_demand_config(config_dir() / "demand_default.yaml")
    if args.spatial_alpha is not None:
        beta = 1.0 - float(args.spatial_alpha)
        config = dict(config)
        config["spatial"] = dict(config["spatial"])
        config["spatial"]["population_weight"] = float(args.spatial_alpha)
        config["spatial"]["commercial_weight"] = beta
        config["spatial"]["note"] = (
            f"Sensitivity override alpha={args.spatial_alpha}; hypothetical, not calibrated."
        )

    fleet = yaml.safe_load((config_dir() / "fleet_default.yaml").read_text(encoding="utf-8"))
    weights_path = zones_dir() / "demand_zone_weights.csv"
    candidates_path = candidates_dir() / "pickup_candidates.csv"
    weight_table = load_demand_zone_weights(weights_path)
    # Recompute sampling weights if spatial override — use frozen table columns when alpha default
    if args.spatial_alpha is None:
        weights = zone_sampling_weights_from_table(weight_table)
    else:
        # Soft reweight: mix pop vs commercial columns if present
        df = weight_table.copy()
        pop = df.get("population_weight", df.get("w_pop", pd.Series(1.0, index=df.index))).astype(float)
        com = df.get("commercial_weight", df.get("w_com", pd.Series(1.0, index=df.index))).astype(float)
        pop = pop / pop.sum() if pop.sum() > 0 else pop
        com = com / com.sum() if com.sum() > 0 else com
        a = float(args.spatial_alpha)
        w = a * pop + (1 - a) * com
        w = w / w.sum()
        weights = w
        if "zone_id" in df.columns:
            weights.index = df["zone_id"]

    candidates = pd.read_csv(candidates_path)
    access = candidates[candidates["accessible"] == True].copy()  # noqa: E712
    depot_row = access.assign(
        d=((access["lat"] - access["lat"].median()) ** 2 + (access["lon"] - access["lon"].median()) ** 2)
    ).sort_values("d").iloc[0]
    depot = {
        "label": "scenario_depot_not_observed_facility",
        "lat": float(depot_row["lat"]),
        "lon": float(depot_row["lon"]),
        "snap_node": int(depot_row["snap_node"]) if pd.notna(depot_row["snap_node"]) else None,
        "note": "Accessible OSM-derived location used as a scenario depot. Not a validated facility.",
    }

    out_root = project_root() / "data" / "casablanca" / "evaluation_v1" / args.tag
    out_root.mkdir(parents=True, exist_ok=True)
    index = {
        "dataset": "casablanca_evaluation_v1",
        "parent_release": "casablanca_release_v1",
        "generator_version": config["generator_version"],
        "claim": "Synthetic expansion from frozen generator/geography. Not new real courier observations.",
        "tag": args.tag,
        "spatial_alpha": args.spatial_alpha,
        "registered_eval_seeds": EVAL_SEEDS,
        "registered_locked_final_seeds_not_generated_here": LOCKED_FINAL_SEEDS,
        "scenarios": [],
        "generated_at_utc": utc_now(),
    }

    n = max(1, min(int(args.per_regime), 20))
    for regime, seeds in EVAL_SEEDS.items():
        for seed in seeds[:n]:
            print(f"Generating {regime} seed={seed} tag={args.tag}...", flush=True)
            regime_cfg = config["regimes"][regime]
            requests_df = generate_requests(candidates, weights, regime, regime_cfg, config, seed)
            scen_dir = out_root / f"{regime}_seed{seed}"
            scen_dir.mkdir(parents=True, exist_ok=True)
            requests_df.to_csv(scen_dir / "requests.csv", index=False, lineterminator="\n")
            meta = {
                "generated_at_utc": utc_now(),
                "regime": regime,
                "seed": seed,
                "split": "evaluation_v1",
                "tag": args.tag,
                "generator_version": config["generator_version"],
                "benchmark_version": "casablanca_evaluation_v1",
                "parent_release": "casablanca_release_v1",
                "n_requests": int(len(requests_df)),
                "fleet": fleet,
                "depot": depot,
                "shift_policy": {
                    "start_hour": regime_cfg.get("start_hour"),
                    "horizon_hours": regime_cfg.get("horizon_hours"),
                    "customer_service_must_finish_by_shift_end": True,
                    "depot_return_may_finish_after_shift_end": True,
                },
                "feasibility": {
                    "certified_feasible": False,
                    "label": "uncertified_statistical_ensemble",
                    "note": "Witness construction skipped; for policy statistical comparison only.",
                },
                "inputs": {
                    "demand_zone_weights_sha256": sha256_file(weights_path),
                    "pickup_candidates_sha256": sha256_file(candidates_path),
                },
                "claim": "Synthetic geographically grounded requests. Not observed Casablanca customer orders.",
                "spatial_alpha_override": args.spatial_alpha,
            }
            write_json(scen_dir / "scenario_metadata.json", meta)
            # Copy depot into metadata path used by loader — also write sidecar fleet refs
            write_json(scen_dir / "depot.json", depot)
            write_json(scen_dir / "fleet.json", fleet)
            index["scenarios"].append(
                {
                    "regime": regime,
                    "seed": seed,
                    "path": str(scen_dir.relative_to(project_root())).replace("\\", "/"),
                    "n_requests": int(len(requests_df)),
                }
            )

    write_json(out_root / "ensemble_index.json", index)
    man = project_root() / "data" / "casablanca" / "manifests" / f"casablanca_evaluation_v1_{args.tag}.json"
    write_json(man, index)
    print(json.dumps({"n_scenarios": len(index["scenarios"]), "out": str(out_root)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
