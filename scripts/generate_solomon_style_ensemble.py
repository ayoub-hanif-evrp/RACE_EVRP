#!/usr/bin/env python
"""Materialize Casablanca C / R / RC instances (sizes 15/30/45) on real OSM buildings.

Does not modify locked_final. Uses pickup_candidates_realistic.csv.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.demand.generator import (
    generate_solomon_style_requests,
    load_demand_config,
    load_demand_zone_weights,
    zone_sampling_weights_from_table,
)
from race_casablanca.demand.realistic_frame import filter_realistic_pickup_candidates
from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import candidates_dir, config_dir, fleet_dir, project_root, zones_dir


def _depot(access: pd.DataFrame) -> dict:
    depot_path = fleet_dir() / "depot.json"
    if depot_path.exists():
        return json.loads(depot_path.read_text(encoding="utf-8"))
    row = (
        access.assign(
            d=(access["lat"] - access["lat"].median()) ** 2
            + (access["lon"] - access["lon"].median()) ** 2
        )
        .sort_values("d")
        .iloc[0]
    )
    return {
        "label": "scenario_depot_not_observed_facility",
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "snap_node": int(row["snap_node"]),
        "note": "Accessible OSM-derived depot; not a validated facility.",
    }


def _seed_for(class_name: str, n: int, local_i: int, base: int, classes: list[str], sizes: list[int]) -> int:
    ci = classes.index(class_name)
    si = sizes.index(n)
    return int(base + ci * 1000 + si * 100 + local_i)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-class-size", type=int, default=5)
    parser.add_argument("--replace", action="store_true", help="Delete existing solomon_style tree first")
    parser.add_argument("--out", default="data/casablanca/evaluation_v1/solomon_style")
    args = parser.parse_args()

    solomon = load_demand_config(config_dir() / "demand_solomon_style.yaml")
    fleet = yaml.safe_load((config_dir() / "fleet_default.yaml").read_text(encoding="utf-8"))
    weights = zone_sampling_weights_from_table(
        load_demand_zone_weights(zones_dir() / "demand_zone_weights.csv")
    )

    realistic_path = candidates_dir() / "pickup_candidates_realistic.csv"
    raw_path = candidates_dir() / "pickup_candidates.csv"
    if realistic_path.exists():
        candidates = pd.read_csv(realistic_path)
    else:
        candidates = filter_realistic_pickup_candidates(pd.read_csv(raw_path))
        candidates.to_csv(realistic_path, index=False, lineterminator="\n")

    if "accessible" in candidates.columns:
        access = candidates[candidates["accessible"] == True]  # noqa: E712
    else:
        access = candidates
    if access.empty:
        raise SystemExit("Realistic pickup frame is empty")
    depot = _depot(access)

    classes = list(solomon["classes"].keys())
    sizes = [int(x) for x in solomon["sizes"]]
    per = max(1, int(args.per_class_size))
    base = int(solomon["seeds"]["eval_base"])
    fleet_nv = {int(k): int(v) for k, v in (solomon.get("fleet_default_n_vehicles") or {}).items()}

    out_root = project_root() / args.out
    if args.replace and out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    index = {
        "benchmark_version": solomon["benchmark_version"],
        "generator_version": solomon["generator_version"],
        "classes": classes,
        "sizes": sizes,
        "per_class_size": per,
        "n_expected": len(classes) * len(sizes) * per,
        "pickup_frame": str(realistic_path.relative_to(project_root())).replace("\\", "/"),
        "pickup_frame_n": int(len(candidates)),
        "locked_final_untouched": True,
        "layout": "{class}/n{size}/{class}_n{size}_seed{seed}/",
        "generated_at_utc": utc_now(),
        "claim": solomon.get("claim"),
        "scenarios": [],
    }

    op = solomon.get("operational") or {}
    for class_name in classes:
        for n in sizes:
            for i in range(per):
                seed = _seed_for(class_name, n, i, base, classes, sizes)
                name = f"{class_name}_n{n}_seed{seed}"
                scen_dir = out_root / class_name / f"n{n}" / name
                print(f"Generating {name} ...", flush=True)
                req_df = generate_solomon_style_requests(
                    candidates, weights, class_name, n, solomon, seed
                )
                # Sanity: every request must keep a real snap_node (OSM-linked).
                if req_df["snap_node"].isna().any():
                    raise SystemExit(f"{name}: missing snap_node — refused random projection")
                scen_dir.mkdir(parents=True, exist_ok=True)
                req_df.to_csv(scen_dir / "requests.csv", index=False, lineterminator="\n")
                nv = int(fleet_nv.get(n, fleet.get("n_vehicles", 3)))
                fleet_i = dict(fleet)
                fleet_i["n_vehicles"] = nv
                meta = {
                    "generated_at_utc": utc_now(),
                    "benchmark_version": solomon["benchmark_version"],
                    "generator_version": solomon["generator_version"],
                    "instance_class": class_name,
                    "spatial_pattern": class_name,
                    "n_customers": n,
                    "seed": seed,
                    "split": "solomon_style_eval",
                    "n_requests": int(len(req_df)),
                    "fleet": fleet_i,
                    "depot": depot,
                    "shift_policy": {
                        "start_hour": op.get("start_hour", 8),
                        "horizon_hours": op.get("horizon_hours", 8),
                        "customer_service_must_finish_by_shift_end": True,
                        "depot_return_may_finish_after_shift_end": True,
                    },
                    "pickup_semantics": {
                        "customer_lat_lon": "OSM building/POI feature centroid or point",
                        "snap_node": "nearest drive-graph access node for routing only",
                        "not_random_map_projection": True,
                        "frame": "pickup_candidates_realistic.csv",
                    },
                    "inputs": {
                        "demand_zone_weights_sha256": sha256_file(
                            zones_dir() / "demand_zone_weights.csv"
                        ),
                        "pickup_candidates_realistic_sha256": sha256_file(realistic_path),
                        "demand_config": "configs/demand_solomon_style.yaml",
                    },
                    "claim": (
                        "C/R/RC Casablanca synthetic instance on real OSM buildings/POIs. "
                        "Not Euclidean Solomon. Not observed courier orders. Not locked_final."
                    ),
                }
                write_json(scen_dir / "scenario_metadata.json", meta)
                write_json(scen_dir / "depot.json", depot)
                write_json(scen_dir / "fleet.json", fleet_i)
                index["scenarios"].append(
                    {
                        "instance_class": class_name,
                        "n_customers": n,
                        "seed": seed,
                        "n_vehicles": nv,
                        "path": str(scen_dir.relative_to(project_root())).replace("\\", "/"),
                        "n_requests": int(len(req_df)),
                    }
                )

    write_json(out_root / "ensemble_index.json", index)
    write_json(
        project_root() / "data" / "casablanca" / "manifests" / "casablanca_solomon_style_v2.json",
        index,
    )
    print(json.dumps({"n_scenarios": len(index["scenarios"]), "out": str(out_root)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
