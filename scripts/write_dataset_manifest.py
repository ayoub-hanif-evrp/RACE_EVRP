"""Write a top-level Casablanca dataset provenance manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import manifest_dir, project_root, scenarios_dir


def main() -> int:
    manifests = {}
    for path in sorted(manifest_dir().glob("*.json")):
        try:
            manifests[path.name] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            manifests[path.name] = {"error": str(exc)}
    scenario_dirs = sorted(p for p in scenarios_dir().rglob("scenario_metadata.json"))
    splits = {"train": [], "validation": [], "test": []}
    for meta_path in scenario_dirs:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        split = meta.get("split", "custom")
        if split in splits:
            splits[split].append(
                {
                    "regime": meta.get("regime"),
                    "seed": meta.get("seed"),
                    "path": str(meta_path.parent.relative_to(project_root())),
                }
            )
    payload = {
        "generated_at_utc": utc_now(),
        "dataset": "casablanca_stage1",
        "geography": "Casablanca study area = union of 22 workbook zones matched to OSM admin (with documented OD-hull fallbacks)",
        "claim_discipline": {
            "allowed": [
                "published Waze-derived zonal/hourly congestion",
                "OSM geometry and distances",
                "synthetic geographically grounded pickups",
                "hypothetical depot-only EV fleet",
            ],
            "forbidden": [
                "edge-calibrated digital twin claims",
                "Chinese/LaDe demand",
                "calling synthetic requests real orders",
                "claiming observed Casablanca EV logistics",
            ],
        },
        "splits": splits,
        "component_manifests": {k: {"keys": list(v.keys()) if isinstance(v, dict) else type(v).__name__} for k, v in manifests.items()},
        "licenses": [
            "OpenStreetMap ODbL",
            "Mendeley traffic workbook CC BY 4.0 (DOI 10.17632/8hj76bpzpv.1)",
            "HCP RGPH-2024 attribution required",
        ],
    }
    write_json(manifest_dir() / "casablanca_dataset_manifest.json", payload)
    print(json.dumps({"scenarios": {k: len(v) for k, v in splits.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
