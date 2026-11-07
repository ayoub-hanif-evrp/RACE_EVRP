"""Generate reproducible Casablanca pickup scenarios with graph-certified feasibility."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import osmnx as ox
import pandas as pd
import yaml

from race_casablanca.demand.feasibility import build_graph_feasible_witness, validate_schedule
from race_casablanca.demand.generator import (
    generate_requests,
    load_demand_config,
    load_demand_zone_weights,
    zone_sampling_weights_from_table,
)
from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.travel_time import CongestionModel
from race_casablanca.paths import (
    candidates_dir,
    config_dir,
    fleet_dir,
    manifest_dir,
    project_root,
    roads_dir,
    scenarios_dir,
    traffic_dir,
    zones_dir,
)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root().resolve())).replace("\\", "/")
    except ValueError:
        return str(path)


def _load_congestion_model() -> CongestionModel:
    city = pd.read_csv(traffic_dir() / "tti_citywide_hour.csv")
    citywide = pd.Series(city["tti_factor"].to_numpy(), index=city["hour"].astype(int))
    zone = None
    zone_path = traffic_dir() / "tti_zone_day_hour.csv"
    if zone_path.exists():
        zone = pd.read_csv(zone_path)
    return CongestionModel(citywide_hour=citywide, zone_day_hour=zone)


def _require_fresh(path: Path, newer_than: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"Missing required input for scenarios: {path}")
    if newer_than.exists() and path.stat().st_mtime < newer_than.stat().st_mtime - 1.0:
        raise SystemExit(
            f"Stale {label}: {path} is older than {newer_than}. Rebuild the release pipeline."
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--regime", default="baseline")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--split", default="train", choices=["train", "validation", "test", "custom"])
    args = parser.parse_args()

    config = load_demand_config(config_dir() / "demand_default.yaml")
    fleet = yaml.safe_load((config_dir() / "fleet_default.yaml").read_text(encoding="utf-8"))
    if args.regime not in config["regimes"]:
        raise SystemExit(f"Unknown regime {args.regime}")
    regime = config["regimes"][args.regime]
    benchmark_version = str(config.get("benchmark_version", "unknown"))

    weights_path = zones_dir() / "demand_zone_weights.csv"
    candidates_path = candidates_dir() / "pickup_candidates.csv"
    boundary_path = zones_dir() / "study_boundary.gpkg"
    graph_path = roads_dir() / "casablanca_drive.graphml"
    _require_fresh(weights_path, boundary_path, "demand_zone_weights")
    _require_fresh(candidates_path, boundary_path, "pickup_candidates")
    _require_fresh(weights_path, candidates_path, "demand_zone_weights vs candidates")
    if not graph_path.exists():
        raise SystemExit(f"Missing drive graph: {graph_path}")

    weight_table = load_demand_zone_weights(weights_path)
    weights = zone_sampling_weights_from_table(weight_table)
    candidates = pd.read_csv(candidates_path)

    access = candidates[candidates["accessible"] == True].copy()  # noqa: E712
    if access.empty:
        raise SystemExit("No accessible pickup candidates")
    depot_row = access.assign(
        d=((access["lat"] - access["lat"].median()) ** 2 + (access["lon"] - access["lon"].median()) ** 2)
    ).sort_values("d").iloc[0]
    depot = {
        "label": "scenario_depot_not_observed_facility",
        "lat": float(depot_row["lat"]),
        "lon": float(depot_row["lon"]),
        "snap_node": int(depot_row["snap_node"]) if pd.notna(depot_row["snap_node"]) else None,
        "note": "Accessible OSM-derived location used as a scenario depot. Not a validated Casablanca logistics facility.",
    }
    fleet_dir().mkdir(parents=True, exist_ok=True)
    write_json(fleet_dir() / "depot.json", depot)
    write_json(fleet_dir() / "fleet.json", fleet)

    requests_df = generate_requests(candidates, weights, args.regime, regime, config, args.seed)

    final_dir = scenarios_dir() / args.split / f"{args.regime}_seed{args.seed}"
    with tempfile.TemporaryDirectory(prefix="race_scenario_") as tmp:
        staging = Path(tmp) / "scenario"
        staging.mkdir(parents=True, exist_ok=True)
        witness_dir = staging / "witnesses"
        witness_dir.mkdir(exist_ok=True)
        requests_df.to_csv(staging / "requests.csv", index=False, lineterminator="\n")

        feasibility = {
            "attempt_certificate": bool(regime.get("attempt_feasible_certificate", False)),
            "label": regime.get("label", "unlabeled"),
            "certified_feasible": False,
            "note": regime.get("label_note"),
        }

        if regime.get("attempt_feasible_certificate", False):
            graph = ox.load_graphml(graph_path)
            model = _load_congestion_model()
            shift_start_s = float(regime["start_hour"]) * 3600.0
            shift_end_s = shift_start_s + float(regime["horizon_hours"]) * 3600.0
            result = build_graph_feasible_witness(
                requests_df,
                fleet,
                depot.get("snap_node"),
                graph,
                model,
                day="Monday",
                shift_start_s=shift_start_s,
                shift_end_s=shift_end_s,
            )
            if result.certified:
                result.schedule.to_csv(witness_dir / "reference_schedule.csv", index=False, lineterminator="\n")
                validation = validate_schedule(
                    result.schedule,
                    requests_df,
                    fleet,
                    depot.get("snap_node"),
                    graph,
                    model,
                    day="Monday",
                    shift_start_s=shift_start_s,
                    shift_end_s=shift_end_s,
                )
                feasibility.update(
                    {
                        "certified_feasible": bool(validation["valid"]),
                        "independent_validator": validation,
                        **result.summary,
                        "online_policy_must_not_read": _rel(final_dir / "witnesses"),
                    }
                )
                if not validation["valid"]:
                    feasibility["certified_feasible"] = False
                    feasibility["label"] = "construction_failed_independent_validation"
                    feasibility["reason"] = "independent_validator_rejected_schedule"
                    # Do not keep a reference schedule if independent validation failed.
                    (witness_dir / "reference_schedule.csv").unlink(missing_ok=True)
                    result.schedule.to_csv(
                        witness_dir / "partial_schedule_uncertified.csv", index=False, lineterminator="\n"
                    )
            else:
                feasibility.update(
                    {
                        "certified_feasible": False,
                        "label": "uncertified",
                        "reason": result.reason,
                        **result.summary,
                    }
                )
                if not result.schedule.empty:
                    result.schedule.to_csv(
                        witness_dir / "partial_schedule_uncertified.csv", index=False, lineterminator="\n"
                    )
                # Explicit: never leave a reference schedule for uncertified builds.
                (witness_dir / "reference_schedule.csv").unlink(missing_ok=True)

        # Enforce single authoritative witness set.
        if feasibility.get("certified_feasible"):
            (witness_dir / "partial_schedule_uncertified.csv").unlink(missing_ok=True)
        else:
            (witness_dir / "reference_schedule.csv").unlink(missing_ok=True)

        meta = {
            "generated_at_utc": utc_now(),
            "regime": args.regime,
            "seed": args.seed,
            "split": args.split,
            "generator_version": config["generator_version"],
            "benchmark_version": benchmark_version,
            "n_requests": int(len(requests_df)),
            "fleet": fleet,
            "depot": depot,
            "feasibility": feasibility,
            "inputs": {
                "demand_zone_weights": _rel(weights_path),
                "demand_zone_weights_sha256": sha256_file(weights_path),
                "pickup_candidates": _rel(candidates_path),
                "pickup_candidates_sha256": sha256_file(candidates_path),
                "drive_graph": _rel(graph_path),
            },
            "claim": "Synthetic geographically grounded requests. Not observed Casablanca customer orders.",
            "arrival_process": "fixed_count_hourly_intensity_sampling",
            "shift_policy": {
                "start_hour": regime.get("start_hour"),
                "horizon_hours": regime.get("horizon_hours"),
                "customer_service_must_finish_by_shift_end": True,
                "depot_return_may_finish_after_shift_end": True,
            },
        }
        write_json(staging / "scenario_metadata.json", meta)

        # Atomic replace of final scenario directory.
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        if final_dir.exists():
            shutil.rmtree(final_dir)
        shutil.copytree(staging, final_dir)

    write_json(manifest_dir() / f"scenario_{args.split}_{args.regime}_seed{args.seed}.json", meta)
    print(json.dumps({"scenario_dir": _rel(final_dir), **feasibility}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
