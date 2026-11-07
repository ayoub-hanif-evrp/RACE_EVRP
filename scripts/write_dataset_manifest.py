"""Write a top-level Casablanca dataset provenance manifest for the active release."""

from __future__ import annotations

import json
import sys

import yaml

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import config_dir, manifest_dir, project_root, scenarios_dir


def main() -> int:
    config = yaml.safe_load((config_dir() / "demand_default.yaml").read_text(encoding="utf-8"))
    release_gen = str(config["generator_version"])
    release_bench = str(config.get("benchmark_version", "casablanca_release_v1"))
    exclude = set(int(x) for x in config.get("splits", {}).get("exclude_legacy_seeds", []))

    manifests = {}
    for path in sorted(manifest_dir().glob("*.json")):
        try:
            manifests[path.name] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            manifests[path.name] = {"error": str(exc)}

    scenario_dirs = sorted(p for p in scenarios_dir().rglob("scenario_metadata.json"))
    splits = {"train": [], "validation": [], "test": []}
    skipped = []
    for meta_path in scenario_dirs:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        seed = meta.get("seed")
        gen = str(meta.get("generator_version"))
        if seed in exclude or gen != release_gen:
            skipped.append(
                {
                    "path": str(meta_path.parent.relative_to(project_root())).replace("\\", "/"),
                    "seed": seed,
                    "generator_version": gen,
                    "reason": "legacy_or_wrong_generator",
                }
            )
            continue
        split = meta.get("split", "custom")
        if split in splits:
            splits[split].append(
                {
                    "regime": meta.get("regime"),
                    "seed": seed,
                    "generator_version": gen,
                    "benchmark_version": meta.get("benchmark_version"),
                    "certified_feasible": (meta.get("feasibility") or {}).get("certified_feasible"),
                    "path": str(meta_path.parent.relative_to(project_root())).replace("\\", "/"),
                }
            )
    payload = {
        "generated_at_utc": utc_now(),
        "dataset": release_bench,
        "generator_version": release_gen,
        "benchmark_version": release_bench,
        "geography": (
            "Casablanca study area = union of 22 workbook zones "
            "(verified_admin OSM polygons + documented OD-hull approximate study zones)"
        ),
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
        "skipped_non_release_scenarios": skipped,
        "component_manifests": {
            k: {"keys": list(v.keys()) if isinstance(v, dict) else type(v).__name__}
            for k, v in manifests.items()
        },
        "licenses": [
            "OpenStreetMap ODbL",
            "Mendeley traffic workbook CC BY 4.0 (DOI 10.17632/8hj76bpzpv.1)",
            "HCP RGPH-2024 attribution required",
        ],
    }
    write_json(manifest_dir() / "casablanca_dataset_manifest.json", payload)
    print(
        json.dumps(
            {
                "scenarios": {k: len(v) for k, v in splits.items()},
                "skipped": len(skipped),
                "generator_version": release_gen,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
