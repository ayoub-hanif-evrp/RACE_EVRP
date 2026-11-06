"""Generate reproducible Casablanca pickup scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

from race_casablanca.demand.generator import (
    build_feasible_witness,
    generate_requests,
    load_demand_config,
    zone_sampling_weights,
)
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import (
    candidates_dir,
    config_dir,
    fleet_dir,
    manifest_dir,
    scenarios_dir,
    traffic_dir,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--regime", default="baseline_feasible")
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

    # Choose an accessible candidate near the median location as scenario depot.
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

    witness = None
    feasibility = {
        "feasible_mode": bool(regime.get("feasible_mode", False)),
        "label": regime.get("label", "baseline" if regime.get("feasible_mode") else "unlabeled"),
    }
    if regime.get("feasible_mode"):
        witness = build_feasible_witness(requests_df, fleet, depot.get("snap_node"), args.seed)
        witness_dir = scenario_dir / "witnesses"
        witness_dir.mkdir(exist_ok=True)
        witness.to_csv(witness_dir / "reference_schedule.csv", index=False)
        feasibility.update(
            {
                "n_requests": int(len(requests_df)),
                "share_within_window": float(witness["within_window"].mean()),
                "min_battery_after_kwh": float(witness["battery_after_kwh"].min()),
                "certificate": "constructive_sequential_depot_schedule",
                "online_policy_must_not_read": str(witness_dir),
            }
        )

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
    }
    write_json(scenario_dir / "scenario_metadata.json", meta)
    write_json(
        manifest_dir() / f"scenario_{args.split}_{args.regime}_seed{args.seed}.json",
        meta,
    )
    print(json.dumps({"scenario_dir": str(scenario_dir), **feasibility}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
