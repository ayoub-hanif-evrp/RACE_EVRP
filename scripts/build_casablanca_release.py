"""Deterministic Casablanca benchmark rebuild in correct dependency order."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import (
    candidates_dir,
    manifest_dir,
    project_root,
    raw_dir,
    roads_dir,
    zones_dir,
)


STEPS = [
    ("verify_boundary", ["scripts/build_casablanca_boundary.py"]),
    ("build_network", ["scripts/build_casablanca_network.py"]),
    ("build_candidates", ["scripts/build_pickup_candidates.py"]),
    ("build_demand_weights", ["scripts/build_demand_zone_weights.py"]),
    ("generate_scenarios", ["scripts/generate_all_scenarios.py"]),
    ("write_dataset_manifest", ["scripts/write_dataset_manifest.py"]),
]


def _run(cmd: list[str]) -> None:
    py = sys.executable
    full = [py, str(project_root() / cmd[0]), *cmd[1:]]
    print("RUN", " ".join(full))
    result = subprocess.run(full, cwd=project_root())
    if result.returncode != 0:
        raise SystemExit(f"Step failed ({result.returncode}): {full}")


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else -1.0


def main() -> int:
    boundary = zones_dir() / "study_boundary.gpkg"
    crosswalk = zones_dir() / "zone_crosswalk.csv"
    pbf = raw_dir() / "osm" / "morocco-260101.osm.pbf"
    if not boundary.exists() or not crosswalk.exists():
        raise SystemExit("Pinned boundary artifacts missing")
    if not pbf.exists():
        raise SystemExit(f"Frozen Morocco PBF missing: {pbf}")

    for name, cmd in STEPS:
        _run(cmd)

    # Post-condition freshness: graph/candidates/weights must not predate boundary.
    graph = roads_dir() / "casablanca_drive.graphml"
    candidates = candidates_dir() / "pickup_candidates.csv"
    weights = zones_dir() / "demand_zone_weights.csv"
    b_m = _mtime(boundary)
    for path, label in [(graph, "graph"), (candidates, "candidates"), (weights, "weights")]:
        if _mtime(path) + 1.0 < b_m:
            raise SystemExit(f"Release integrity failure: {label} older than repaired boundary")

    summary = {
        "generated_at_utc": utc_now(),
        "pipeline": [s[0] for s in STEPS],
        "boundary_sha256": sha256_file(boundary),
        "crosswalk_sha256": sha256_file(crosswalk),
        "pbf_sha256": sha256_file(pbf) if pbf.exists() else None,
        "graph_sha256": sha256_file(graph),
        "candidates_sha256": sha256_file(candidates),
        "demand_weights_sha256": sha256_file(weights),
        "paths": {
            "boundary": "data/casablanca/zones/study_boundary.gpkg",
            "crosswalk": "data/casablanca/zones/zone_crosswalk.csv",
            "graph": "data/casablanca/roads/casablanca_drive.graphml",
            "candidates": "data/casablanca/pickup_candidates/pickup_candidates.csv",
            "weights": "data/casablanca/zones/demand_zone_weights.csv",
        },
    }
    write_json(manifest_dir() / "casablanca_release_build.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
