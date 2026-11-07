"""Independently verify the Casablanca benchmark release integrity."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import Point

from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import (
    candidates_dir,
    config_dir,
    manifest_dir,
    project_root,
    raw_dir,
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


def _fail(errors: list[str], msg: str) -> None:
    errors.append(msg)
    print("FAIL:", msg)


def verify_light(errors: list[str], warnings: list[str]) -> dict:
    config = yaml.safe_load((config_dir() / "demand_default.yaml").read_text(encoding="utf-8"))
    gen = str(config["generator_version"])
    bench = str(config.get("benchmark_version"))
    exclude = set(int(x) for x in config.get("splits", {}).get("exclude_legacy_seeds", []))

    boundary = zones_dir() / "study_boundary.gpkg"
    crosswalk_csv = zones_dir() / "zone_crosswalk.csv"
    weights = zones_dir() / "demand_zone_weights.csv"
    candidates = candidates_dir() / "pickup_candidates.csv"
    for p in [boundary, crosswalk_csv, weights, candidates]:
        if not p.exists():
            _fail(errors, f"missing artifact {_rel(p)}")

    bman = manifest_dir() / "boundary_manifest.json"
    if bman.exists() and crosswalk_csv.exists():
        man = json.loads(bman.read_text(encoding="utf-8"))
        pinned = ((man.get("checksums") or {}).get("artifacts") or {}).get("zone_crosswalk.csv") or {}
        actual = sha256_file(crosswalk_csv)
        if pinned.get("sha256") and pinned["sha256"] != actual:
            _fail(errors, f"zone_crosswalk.csv sha256 mismatch pinned={pinned['sha256']} actual={actual}")

    # Demand weights invariants.
    stats = {}
    if weights.exists():
        w = pd.read_csv(weights)
        if not w["zone_id"].is_unique:
            _fail(errors, "demand_zone_weights zone_id not unique")
        elig = w[w["eligible_for_sampling"] == True]  # noqa: E712
        if abs(float(elig["zone_weight"].sum()) - 1.0) > 1e-6 and abs(float(w["zone_weight"].sum()) - 1.0) > 1e-6:
            _fail(errors, "demand weights do not sum to 1")
        pos = int((w["zone_weight"] > 1e-12).sum())
        stats.update(
            {
                "n_zones": int(len(w)),
                "n_eligible": int(elig.shape[0]),
                "n_positive_weight": pos,
                "zero_weight_with_candidates": w[(w["n_accessible_candidates"] > 0) & (w["zone_weight"] <= 1e-12)][
                    "zone_id"
                ].tolist(),
            }
        )
        if stats["zero_weight_with_candidates"]:
            warnings.append(
                "zones with accessible candidates but ~0 weight: "
                + ", ".join(map(str, stats["zero_weight_with_candidates"]))
            )

    # Scenario release integrity.
    metas = list(scenarios_dir().rglob("scenario_metadata.json"))
    gens = set()
    for meta_path in metas:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        seed = int(meta.get("seed"))
        g = str(meta.get("generator_version"))
        gens.add(g)
        scen = meta_path.parent
        wit = scen / "witnesses"
        cert = bool((meta.get("feasibility") or {}).get("certified_feasible"))
        ref = wit / "reference_schedule.csv"
        partial = wit / "partial_schedule_uncertified.csv"
        if seed in exclude:
            _fail(errors, f"legacy excluded seed still present: {_rel(scen)}")
        if g != gen:
            _fail(errors, f"generator mix: {_rel(scen)} has {g}, release expects {gen}")
        if cert and not ref.exists():
            _fail(errors, f"certified but missing reference_schedule: {_rel(scen)}")
        if cert and partial.exists():
            _fail(errors, f"certified but leftover partial_schedule_uncertified: {_rel(scen)}")
        if not cert and ref.exists():
            _fail(errors, f"uncertified but obsolete reference_schedule present: {_rel(scen)}")

    # Freshness: candidates/weights must not predate boundary.
    if boundary.exists() and candidates.exists() and weights.exists():
        bm = boundary.stat().st_mtime
        if candidates.stat().st_mtime + 1 < bm:
            _fail(errors, "pickup_candidates older than study_boundary")
        if weights.stat().st_mtime + 1 < candidates.stat().st_mtime:
            _fail(errors, "demand_zone_weights older than pickup_candidates")

    # Point-in-polygon for a sample of requests in release scenarios.
    geo_ok = 0
    geo_checked = 0
    if (zones_dir() / "zone_crosswalk.gpkg").exists():
        zones = gpd.read_file(zones_dir() / "zone_crosswalk.gpkg", layer="zones")
        for meta_path in metas[:20]:
            req_path = meta_path.parent / "requests.csv"
            if not req_path.exists():
                continue
            req = pd.read_csv(req_path)
            for _, row in req.head(5).iterrows():
                zone_name = str(row.get("declared_zone_id") or row.get("commune"))
                pt = Point(float(row["lon"]), float(row["lat"]))
                poly = zones.loc[zones["workbook_commune"] == zone_name, "geometry"]
                geo_checked += 1
                if poly.empty:
                    _fail(errors, f"request zone missing from crosswalk: {zone_name}")
                    continue
                if not poly.iloc[0].covers(pt) and not poly.iloc[0].intersects(pt):
                    # Allow tiny snap float issues via buffer 1e-6 deg.
                    if not poly.iloc[0].buffer(1e-5).contains(pt):
                        _fail(errors, f"request outside declared zone {zone_name} in {_rel(meta_path.parent)}")
                        continue
                geo_ok += 1

    return {
        "mode": "light",
        "benchmark_version": bench,
        "generator_version": gen,
        "n_scenario_metadata": len(metas),
        "generator_versions_found": sorted(gens),
        "demand_stats": stats,
        "geo_point_in_polygon_checked": geo_checked,
        "geo_point_in_polygon_ok": geo_ok,
        "n_errors": len(errors),
        "n_warnings": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }


def verify_full(errors: list[str], warnings: list[str], light: dict) -> dict:
    pbf = raw_dir() / "osm" / "morocco-260101.osm.pbf"
    graph = roads_dir() / "casablanca_drive.graphml"
    if not pbf.exists():
        warnings.append("full mode: Morocco PBF not present locally; skipped PBF hash")
    else:
        light["pbf_sha256"] = sha256_file(pbf)
    if not graph.exists():
        _fail(errors, "missing casablanca_drive.graphml")
    else:
        light["graph_sha256"] = sha256_file(graph)
        # Optional: certify one baseline schedule if present.
        base = scenarios_dir() / "train" / "baseline_seed1"
        meta_path = base / "scenario_metadata.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if (meta.get("feasibility") or {}).get("certified_feasible"):
                import osmnx as ox
                from race_casablanca.demand.feasibility import validate_schedule
                from race_casablanca.network.travel_time import CongestionModel

                graph_obj = ox.load_graphml(graph)
                fleet = meta["fleet"]
                depot = meta["depot"]["snap_node"]
                req = pd.read_csv(base / "requests.csv")
                sched = pd.read_csv(base / "witnesses" / "reference_schedule.csv")
                city = pd.read_csv(traffic_dir() / "tti_citywide_hour.csv")
                citywide = pd.Series(city["tti_factor"].to_numpy(), index=city["hour"].astype(int))
                zone = None
                zone_path = traffic_dir() / "tti_zone_day_hour.csv"
                if zone_path.exists():
                    zone = pd.read_csv(zone_path)
                model = CongestionModel(citywide_hour=citywide, zone_day_hour=zone)
                shift_start = float(meta["shift_policy"]["start_hour"]) * 3600.0
                shift_end = shift_start + float(meta["shift_policy"]["horizon_hours"]) * 3600.0
                val = validate_schedule(
                    sched, req, fleet, depot, graph_obj, model, day="Monday",
                    shift_start_s=shift_start, shift_end_s=shift_end,
                )
                light["baseline_seed1_revalidation"] = {
                    "valid": val["valid"],
                    "n_violations": val["n_violations"],
                }
                if not val["valid"]:
                    _fail(errors, f"baseline_seed1 independent revalidation failed: {val['violations'][:3]}")
    light["mode"] = "full"
    light["n_errors"] = len(errors)
    light["errors"] = errors
    light["warnings"] = warnings
    return light


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--light", action="store_true", help="Skip PBF/graph-heavy checks")
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    summary = verify_light(errors, warnings)
    if not args.light:
        summary = verify_full(errors, warnings, summary)
    summary["generated_at_utc"] = utc_now()
    summary["ok"] = len(errors) == 0
    out = manifest_dir() / "benchmark_release_verification.json"
    write_json(out, summary)
    print(json.dumps({k: summary[k] for k in ["ok", "mode", "n_errors", "n_warnings", "benchmark_version", "generator_version", "demand_stats", "errors", "warnings"] if k in summary}, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
