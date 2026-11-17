#!/usr/bin/env python
"""Materialize Solomon-style Casablanca instance classes (C/R/RC × 1/2 × 15/30/45).

Does not modify locked_final or casablanca_release_v1.
Demand is synthetic on frozen OSM / zone / candidate assets.
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
    generate_solomon_style_requests,
    load_demand_config,
    load_demand_zone_weights,
    zone_sampling_weights_from_table,
)
from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import candidates_dir, config_dir, fleet_dir, project_root, zones_dir


def _depot_from_file_or_candidates(access: pd.DataFrame) -> dict:
    depot_path = fleet_dir() / "depot.json"
    if depot_path.exists():
        return json.loads(depot_path.read_text(encoding="utf-8"))
    depot_row = (
        access.assign(
            d=(
                (access["lat"] - access["lat"].median()) ** 2
                + (access["lon"] - access["lon"].median()) ** 2
            )
        )
        .sort_values("d")
        .iloc[0]
    )
    return {
        "label": "scenario_depot_not_observed_facility",
        "lat": float(depot_row["lat"]),
        "lon": float(depot_row["lon"]),
        "snap_node": int(depot_row["snap_node"]),
        "note": "Accessible OSM-derived depot; not a validated facility.",
    }


def _seed_for(class_name: str, n: int, local_i: int, base: int, classes: list[str], sizes: list[int]) -> int:
    """Deterministic unique eval seed per (class, size, replicate)."""
    ci = classes.index(class_name)
    si = sizes.index(n)
    # Keep well below locked/eval legacy banks and above 3000.
    return int(base + ci * 1000 + si * 100 + local_i)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-class-size", type=int, default=5)
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument(
        "--out",
        default="data/casablanca/evaluation_v1/solomon_style",
        help="Organized instance root",
    )
    args = parser.parse_args()

    solomon = load_demand_config(config_dir() / "demand_solomon_style.yaml")
    fleet = yaml.safe_load((config_dir() / "fleet_default.yaml").read_text(encoding="utf-8"))
    weights_path = zones_dir() / "demand_zone_weights.csv"
    candidates_path = candidates_dir() / "pickup_candidates.csv"
    weight_table = load_demand_zone_weights(weights_path)
    weights = zone_sampling_weights_from_table(weight_table)
    candidates = pd.read_csv(candidates_path)
    access = candidates[candidates["accessible"] == True]  # noqa: E712
    depot = _depot_from_file_or_candidates(access)

    classes = list(solomon["classes"].keys())
    sizes = [int(x) for x in solomon["sizes"]]
    per = max(1, int(args.per_class_size))
    base = int(solomon["seeds"]["eval_base"])
    fleet_nv = {int(k): int(v) for k, v in (solomon.get("fleet_default_n_vehicles") or {}).items()}

    out_root = project_root() / args.out
    out_root.mkdir(parents=True, exist_ok=True)

    index = {
        "benchmark_version": solomon["benchmark_version"],
        "generator_version": solomon["generator_version"],
        "parent_release": solomon.get("parent_release"),
        "claim": solomon.get("claim"),
        "sizes": sizes,
        "classes": classes,
        "per_class_size": per,
        "n_expected": len(classes) * len(sizes) * per,
        "locked_final_untouched": True,
        "generated_at_utc": utc_now(),
        "layout": "{class}_n{size}_seed{seed}/",
        "scenarios": [],
    }

    for class_name in classes:
        for n in sizes:
            for i in range(per):
                seed = _seed_for(class_name, n, i, base, classes, sizes)
                name = f"{class_name}_n{n}_seed{seed}"
                scen_dir = out_root / class_name / f"n{n}" / name
                if args.skip_existing and (scen_dir / "requests.csv").exists():
                    meta = json.loads((scen_dir / "scenario_metadata.json").read_text(encoding="utf-8"))
                    index["scenarios"].append(
                        {
                            "instance_class": class_name,
                            "n_customers": n,
                            "seed": seed,
                            "path": str(scen_dir.relative_to(project_root())).replace("\\", "/"),
                            "n_requests": int(meta.get("n_requests", n)),
                            "skipped_existing": True,
                        }
                    )
                    continue
                print(f"Generating {name} ...", flush=True)
                req_df = generate_solomon_style_requests(
                    candidates, weights, class_name, n, solomon, seed
                )
                scen_dir.mkdir(parents=True, exist_ok=True)
                req_df.to_csv(scen_dir / "requests.csv", index=False, lineterminator="\n")
                nv = int(fleet_nv.get(n, fleet.get("n_vehicles", 3)))
                fleet_i = dict(fleet)
                fleet_i["n_vehicles"] = nv
                series = str(solomon["classes"][class_name]["series"])
                series_cfg = solomon["series"][series]
                meta = {
                    "generated_at_utc": utc_now(),
                    "benchmark_version": solomon["benchmark_version"],
                    "generator_version": solomon["generator_version"],
                    "instance_class": class_name,
                    "spatial_pattern": solomon["classes"][class_name]["pattern"],
                    "series": series,
                    "series_name": series_cfg["name"],
                    "n_customers": n,
                    "seed": seed,
                    "split": "solomon_style_eval",
                    "n_requests": int(len(req_df)),
                    "fleet": fleet_i,
                    "depot": depot,
                    "shift_policy": {
                        "start_hour": series_cfg["start_hour"],
                        "horizon_hours": series_cfg["horizon_hours"],
                        "customer_service_must_finish_by_shift_end": True,
                        "depot_return_may_finish_after_shift_end": True,
                    },
                    "inputs": {
                        "demand_zone_weights_sha256": sha256_file(weights_path),
                        "pickup_candidates_sha256": sha256_file(candidates_path),
                        "demand_config": "configs/demand_solomon_style.yaml",
                    },
                    "claim": (
                        "Solomon-style Casablanca synthetic instance. "
                        "Not Euclidean Solomon. Not observed courier orders. "
                        "Not locked_final."
                    ),
                    "policy_tuning_forbidden": False,
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
        project_root() / "data" / "casablanca" / "manifests" / "casablanca_solomon_style_v1.json",
        index,
    )
    print(
        json.dumps(
            {
                "n_scenarios": len(index["scenarios"]),
                "expected": index["n_expected"],
                "out": str(out_root).replace("\\", "/"),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
