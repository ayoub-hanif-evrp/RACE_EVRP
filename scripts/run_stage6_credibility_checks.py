#!/usr/bin/env python
"""Stage 6 credibility: request fields, graph accessibility, certified witness revalidation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.demand.feasibility import validate_schedule
from race_casablanca.hashing import sha256_file
from race_casablanca.paths import candidates_dir, project_root, scenarios_dir, zones_dir
from race_casablanca.sim.scenario_loader import load_congestion_model, load_drive_graph, load_scenario


def check_requests(root: Path, graph) -> dict:
    n = 0
    missing_snap = 0
    missing_zone = 0
    claimed_observed = 0
    snap_not_in_graph = 0
    for csv in root.rglob("requests.csv"):
        df = pd.read_csv(csv)
        n += len(df)
        if "snap_node" in df.columns:
            missing_snap += int(df["snap_node"].isna().sum())
            for node in df["snap_node"].dropna().astype(int):
                if node not in graph:
                    snap_not_in_graph += 1
        else:
            missing_snap += len(df)
        zone_col = next(
            (c for c in ("declared_zone_id", "zone_id", "commune") if c in df.columns), None
        )
        if zone_col:
            missing_zone += int(df[zone_col].isna().sum())
        else:
            missing_zone += len(df)
        if "is_observed_order" in df.columns:
            claimed_observed += int(
                df["is_observed_order"].astype(str).str.lower().isin(["true", "1"]).sum()
            )
    return {
        "n_requests": n,
        "missing_snap_node": missing_snap,
        "missing_zone_field": missing_zone,
        "snap_node_not_in_graph": snap_not_in_graph,
        "claimed_observed_orders": claimed_observed,
    }


def revalidate_certified_witnesses(graph, model) -> list[dict]:
    results = []
    for meta_path in scenarios_dir().rglob("scenario_metadata.json"):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        feas = meta.get("feasibility") or {}
        if not feas.get("certified_feasible"):
            continue
        scen_dir = meta_path.parent
        witness = scen_dir / "witnesses" / "reference_schedule.csv"
        row = {
            "scenario": str(scen_dir.relative_to(project_root())).replace("\\", "/"),
            "certified_flag": True,
            "witness_exists": witness.exists(),
        }
        if not witness.exists():
            row["revalidation"] = {"valid": False, "error": "missing_witness_file"}
            results.append(row)
            continue
        sc = load_scenario(scen_dir, load_network=False, graph=graph, model=model)
        # Build request frame expected by validate_schedule
        req_df = pd.read_csv(scen_dir / "requests.csv")
        schedule = pd.read_csv(witness)
        validation = validate_schedule(
            schedule,
            req_df,
            sc.fleet,
            sc.depot_node,
            graph,
            model,
            day=sc.day,
            shift_start_s=sc.shift_start_s,
            shift_end_s=sc.shift_end_s,
        )
        row["revalidation"] = {
            "valid": bool(validation.get("valid")),
            "n_violations": int(validation.get("n_violations", len(validation.get("violations", [])))),
            "coverage": validation.get("coverage"),
        }
        results.append(row)
    return results


def main() -> int:
    print("Loading graph for accessibility / witness checks...", flush=True)
    graph = load_drive_graph()
    model = load_congestion_model()

    cas = project_root() / "data" / "casablanca"
    out = {
        "release_scenarios": check_requests(cas / "scenarios", graph),
        "evaluation_v1_default": check_requests(cas / "evaluation_v1" / "default", graph),
        "evaluation_v1_locked_final": check_requests(cas / "evaluation_v1" / "locked_final", graph)
        if (cas / "evaluation_v1" / "locked_final").exists()
        else {"status": "not_generated"},
        "source_hashes": {
            "demand_zone_weights": sha256_file(zones_dir() / "demand_zone_weights.csv"),
            "pickup_candidates": sha256_file(candidates_dir() / "pickup_candidates.csv"),
        },
        "certified_witness_revalidation": revalidate_certified_witnesses(graph, model),
        "historical_artifacts": {
            "constraint_binding_diagnosis.json": "HISTORICAL — not active release authority",
            "CONSTRAINT_BINDING_DIAGNOSIS.md": "HISTORICAL report",
        },
        "model_validation_matrix": {
            "independently_checked": [
                "Release request snap_node presence and graph membership",
                "Declared zone fields on all release/eval requests",
                "is_observed_order=False on synthetic requests",
                "Certified witness files revalidated via validate_schedule",
                "Source file checksums for weights/candidates",
            ],
            "assumed": [
                "60/40 population/commercial spatial mixture",
                "Hourly intensity profiles",
                "EV energy/charge parameters",
                "Three-vehicle depot configuration",
            ],
            "unverified": [
                "Empirical parcel arrival-rate calibration",
                "Observed customer-location match to OSM sampling frame",
                "Measured van energy curves",
            ],
        },
        "notes": [
            "Traffic workbook rows are congestion OD observations, not courier orders.",
            "OSM candidates are sampling-frame locations, not observed customers.",
            "Eval_v1 expands synthetic episodes; locked_final is reserved untuned.",
            "Published traffic covers a limited observation period only.",
        ],
    }
    dest = cas / "online_results" / "stage6_credibility_checks.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print(f"Wrote {dest}", flush=True)
    n_cert = len(out["certified_witness_revalidation"])
    n_ok = sum(1 for r in out["certified_witness_revalidation"] if r.get("revalidation", {}).get("valid"))
    print(f"Certified witnesses revalidated: {n_ok}/{n_cert}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
