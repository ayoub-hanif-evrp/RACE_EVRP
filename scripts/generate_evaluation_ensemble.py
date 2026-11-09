#!/usr/bin/env python
"""Generate casablanca_evaluation_v1 / locked_final from the frozen generator.

Does not modify casablanca_release_v1. Does not claim new real courier observations.
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
    project_root,
    zones_dir,
)

EVAL_SEEDS = {
    "baseline": list(range(1101, 1121)),  # 20
    "peak_stress": list(range(1201, 1221)),
    "tight_windows": list(range(1301, 1321)),
}
LOCKED_FINAL_SEEDS = {
    "baseline": list(range(2101, 2111)),  # 10 locked per regime
    "peak_stress": list(range(2201, 2211)),
    "tight_windows": list(range(2301, 2311)),
}
REGISTERED_LOCKED_FULL = {
    "baseline": list(range(2101, 2131)),
    "peak_stress": list(range(2201, 2231)),
    "tight_windows": list(range(2301, 2331)),
}


def _depot_from_candidates(access: pd.DataFrame) -> dict:
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
        "snap_node": int(depot_row["snap_node"]) if pd.notna(depot_row["snap_node"]) else None,
        "note": "Accessible OSM-derived location used as a scenario depot. Not a validated facility.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-regime", type=int, default=20, help="Eval seeds to materialize (≤20)")
    parser.add_argument("--spatial-alpha", type=float, default=None)
    parser.add_argument("--tag", default="default")
    parser.add_argument(
        "--locked",
        action="store_true",
        help="Generate locked final-evaluation set under evaluation_v1/locked_final (no policy tuning).",
    )
    parser.add_argument("--locked-per-regime", type=int, default=10)
    parser.add_argument(
        "--intensity-profile",
        default=None,
        help="Override regime intensity_profile name (hypothetical sensitivity).",
    )
    parser.add_argument(
        "--candidate-filter",
        choices=["all_accessible", "informative_osm"],
        default="all_accessible",
        help="informative_osm excludes generic building=yes for sampling frame sensitivity.",
    )
    parser.add_argument("--skip-existing", action="store_true", default=True)
    args = parser.parse_args()

    config = load_demand_config(config_dir() / "demand_default.yaml")
    if args.spatial_alpha is not None:
        config = dict(config)
        config["spatial"] = dict(config["spatial"])
        config["spatial"]["population_weight"] = float(args.spatial_alpha)
        config["spatial"]["commercial_weight"] = 1.0 - float(args.spatial_alpha)
        config["spatial"]["note"] = (
            f"Sensitivity override alpha={args.spatial_alpha}; hypothetical, not calibrated."
        )
    if args.intensity_profile:
        config = dict(config)
        config["regimes"] = {k: dict(v) for k, v in config["regimes"].items()}
        config["intensity_profiles"] = dict(config.get("intensity_profiles") or {})
        if args.intensity_profile == "flat_daytime":
            # Uniform over operating daytime hours 7–18; hypothetical sensitivity only.
            weights = [0.0] * 24
            for h in range(7, 19):
                weights[h] = 1.0
            config["intensity_profiles"]["flat_daytime"] = {"weights": weights}
        for regime_cfg in config["regimes"].values():
            regime_cfg["intensity_profile"] = args.intensity_profile
            regime_cfg["intensity_note"] = (
                f"Hypothetical override profile={args.intensity_profile}; not calibrated."
            )

    fleet = yaml.safe_load((config_dir() / "fleet_default.yaml").read_text(encoding="utf-8"))
    weights_path = zones_dir() / "demand_zone_weights.csv"
    candidates_path = candidates_dir() / "pickup_candidates.csv"
    weight_table = load_demand_zone_weights(weights_path)

    if args.spatial_alpha is None:
        weights = zone_sampling_weights_from_table(weight_table)
    else:
        df = weight_table.copy()
        # CSV columns from build_demand_zone_weights.py are pop_w / com_w
        # (not population_weight / w_pop — those fallbacks silently yielded uniform weights).
        if "pop_w" in df.columns:
            pop = df["pop_w"].astype(float)
        elif "population_weight" in df.columns:
            pop = df["population_weight"].astype(float)
        else:
            raise KeyError("demand_zone_weights.csv missing pop_w (or population_weight)")
        if "com_w" in df.columns:
            com = df["com_w"].astype(float)
        elif "commercial_weight" in df.columns:
            com = df["commercial_weight"].astype(float)
        else:
            raise KeyError("demand_zone_weights.csv missing com_w (or commercial_weight)")
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
    if args.candidate_filter == "informative_osm":
        cat = access.get("category", access.get("osm_category", pd.Series("", index=access.index))).astype(str)
        informative = ~cat.str.startswith("building=yes") & ~cat.isin(["building=yes", "yes", ""])
        # Keep residential/apartments/amenities; drop only generic building=yes
        informative = ~cat.eq("building=yes")
        filtered = access[informative].copy()
        if len(filtered) < 500:
            raise SystemExit(f"informative_osm filter too aggressive: {len(filtered)} candidates")
        access = filtered
        candidates = access
    depot = _depot_from_candidates(access)

    if args.locked:
        out_root = project_root() / "data" / "casablanca" / "evaluation_v1" / "locked_final"
        seed_map = {
            regime: seeds[: max(1, min(int(args.locked_per_regime), len(seeds)))]
            for regime, seeds in LOCKED_FINAL_SEEDS.items()
        }
        split_name = "evaluation_v1_locked_final"
        claim = (
            "LOCKED final-evaluation synthetic set. No policy tuning / selection on these seeds. "
            "Not new real courier observations."
        )
    else:
        out_root = project_root() / "data" / "casablanca" / "evaluation_v1" / args.tag
        n = max(1, min(int(args.per_regime), 20))
        seed_map = {regime: seeds[:n] for regime, seeds in EVAL_SEEDS.items()}
        split_name = "evaluation_v1"
        claim = "Synthetic expansion from frozen generator/geography. Not new real courier observations."

    out_root.mkdir(parents=True, exist_ok=True)
    index = {
        "dataset": "casablanca_evaluation_v1" + ("_locked_final" if args.locked else ""),
        "parent_release": "casablanca_release_v1",
        "generator_version": config["generator_version"],
        "claim": claim,
        "tag": "locked_final" if args.locked else args.tag,
        "spatial_alpha": args.spatial_alpha,
        "intensity_profile_override": args.intensity_profile,
        "candidate_filter": args.candidate_filter,
        "registered_eval_seeds": EVAL_SEEDS,
        "registered_locked_final_seeds": REGISTERED_LOCKED_FULL,
        "materialized_locked_seeds_this_run": seed_map if args.locked else None,
        "scenarios": [],
        "generated_at_utc": utc_now(),
        "policy_tuning_forbidden": bool(args.locked),
    }

    for regime, seeds in seed_map.items():
        for seed in seeds:
            scen_dir = out_root / f"{regime}_seed{seed}"
            if args.skip_existing and (scen_dir / "requests.csv").exists():
                meta_existing = json.loads((scen_dir / "scenario_metadata.json").read_text(encoding="utf-8"))
                index["scenarios"].append(
                    {
                        "regime": regime,
                        "seed": seed,
                        "path": str(scen_dir.relative_to(project_root())).replace("\\", "/"),
                        "n_requests": int(meta_existing.get("n_requests", 0)),
                        "skipped_existing": True,
                    }
                )
                print(f"Skip existing {regime} seed={seed}", flush=True)
                continue
            print(
                f"Generating {regime} seed={seed} tag={index['tag']} "
                f"filter={args.candidate_filter}...",
                flush=True,
            )
            regime_cfg = dict(config["regimes"][regime])
            requests_df = generate_requests(candidates, weights, regime, regime_cfg, config, seed)
            scen_dir.mkdir(parents=True, exist_ok=True)
            requests_df.to_csv(scen_dir / "requests.csv", index=False, lineterminator="\n")
            meta = {
                "generated_at_utc": utc_now(),
                "regime": regime,
                "seed": seed,
                "split": split_name,
                "tag": index["tag"],
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
                    "label": "uncertified_statistical_ensemble"
                    if not args.locked
                    else "locked_final_untuned",
                    "note": "Witness construction skipped; statistical / locked evaluation only.",
                },
                "inputs": {
                    "demand_zone_weights_sha256": sha256_file(weights_path),
                    "pickup_candidates_sha256": sha256_file(candidates_path),
                    "candidate_filter": args.candidate_filter,
                    "n_candidates_used": int(len(candidates)),
                },
                "claim": "Synthetic geographically grounded requests. Not observed Casablanca customer orders.",
                "spatial_alpha_override": args.spatial_alpha,
                "intensity_profile_override": args.intensity_profile,
                "policy_tuning_forbidden": bool(args.locked),
            }
            write_json(scen_dir / "scenario_metadata.json", meta)
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
    man_name = (
        "casablanca_evaluation_v1_locked_final.json"
        if args.locked
        else f"casablanca_evaluation_v1_{args.tag}.json"
    )
    write_json(project_root() / "data" / "casablanca" / "manifests" / man_name, index)
    print(json.dumps({"n_scenarios": len(index["scenarios"]), "out": str(out_root)}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
