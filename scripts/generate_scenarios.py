"""Generate reproducible Casablanca pickup scenarios with graph-certified feasibility."""

from __future__ import annotations

import argparse
import json
import sys

import osmnx as ox
import pandas as pd
import yaml

from race_casablanca.demand.feasibility import build_graph_feasible_witness, validate_schedule
from race_casablanca.demand.generator import generate_requests, load_demand_config, zone_sampling_weights
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.travel_time import CongestionModel
from race_casablanca.paths import (
    candidates_dir,
    config_dir,
    fleet_dir,
    manifest_dir,
    roads_dir,
    scenarios_dir,
    traffic_dir,
)


def _load_congestion_model() -> CongestionModel:
    city = pd.read_csv(traffic_dir() / "tti_citywide_hour.csv")
    citywide = pd.Series(city["tti_factor"].to_numpy(), index=city["hour"].astype(int))
    zone = None
    zone_path = traffic_dir() / "tti_zone_day_hour.csv"
    if zone_path.exists():
        zone = pd.read_csv(zone_path)
    return CongestionModel(citywide_hour=citywide, zone_day_hour=zone)


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

    communes = pd.read_csv(traffic_dir() / "communes.csv")
    land = pd.read_csv(traffic_dir() / "land_use.csv")
    candidates = pd.read_csv(candidates_dir() / "pickup_candidates.csv")
    weights = zone_sampling_weights(communes, land, config)

    access = candidates[candidates["accessible"] == True].copy()  # noqa: E712
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
    scenario_dir = scenarios_dir() / args.split / f"{args.regime}_seed{args.seed}"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    requests_df.to_csv(scenario_dir / "requests.csv", index=False)

    feasibility = {
        "attempt_certificate": bool(regime.get("attempt_feasible_certificate", False)),
        "label": regime.get("label", "unlabeled"),
        "certified_feasible": False,
        "note": regime.get("label_note"),
    }

    if regime.get("attempt_feasible_certificate", False):
        graph = ox.load_graphml(roads_dir() / "casablanca_drive.graphml")
        model = _load_congestion_model()
        result = build_graph_feasible_witness(
            requests_df, fleet, depot.get("snap_node"), graph, model, day="Monday"
        )
        witness_dir = scenario_dir / "witnesses"
        witness_dir.mkdir(exist_ok=True)
        if result.certified:
            result.schedule.to_csv(witness_dir / "reference_schedule.csv", index=False)
            validation = validate_schedule(
                result.schedule, requests_df, fleet, depot.get("snap_node"), graph, model, day="Monday"
            )
            feasibility.update(
                {
                    "certified_feasible": bool(validation["valid"]),
                    "independent_validator": validation,
                    **result.summary,
                    "online_policy_must_not_read": str(witness_dir),
                }
            )
            if not validation["valid"]:
                feasibility["certified_feasible"] = False
                feasibility["label"] = "construction_failed_independent_validation"
                feasibility["reason"] = "independent_validator_rejected_schedule"
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
                result.schedule.to_csv(witness_dir / "partial_schedule_uncertified.csv", index=False)

    meta = {
        "generated_at_utc": utc_now(),
        "regime": args.regime,
        "seed": args.seed,
        "split": args.split,
        "generator_version": config["generator_version"],
        "n_requests": int(len(requests_df)),
        "fleet": fleet,
        "depot": depot,
        "feasibility": feasibility,
        "claim": "Synthetic geographically grounded requests. Not observed Casablanca customer orders.",
        "arrival_process": "fixed_count_hourly_intensity_sampling",
    }
    write_json(scenario_dir / "scenario_metadata.json", meta)
    write_json(manifest_dir() / f"scenario_{args.split}_{args.regime}_seed{args.seed}.json", meta)
    print(json.dumps({"scenario_dir": str(scenario_dir), **feasibility}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
