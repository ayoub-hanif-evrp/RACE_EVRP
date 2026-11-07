"""Pin SHA-256 of committed study geography without live Overpass/Nominatim rebuild."""

from __future__ import annotations

import json
import sys

import pandas as pd

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.boundary import pin_boundary_artifact_checksums
from race_casablanca.paths import manifest_dir, zones_dir


def main() -> int:
    zones = zones_dir()
    manifest_path = manifest_dir() / "boundary_manifest.json"
    if manifest_path.exists():
        summary = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        summary = {}
    summary["generated_at_utc"] = utc_now()
    summary["checksums"] = pin_boundary_artifact_checksums(zones)
    summary["pinning_note"] = (
        "Checksums refreshed against committed artifacts only. "
        "Live rebuilds are non-bit-identical and must not overwrite without audit."
    )
    crosswalk = zones / "zone_crosswalk.csv"
    if crosswalk.exists():
        frame = pd.read_csv(crosswalk)
        if "geography_status" in frame.columns:
            summary["geography_status_counts"] = {
                str(k): int(v) for k, v in frame["geography_status"].value_counts().items()
            }
            summary["verified_admin"] = frame.loc[
                frame["geography_status"] == "verified_admin", "workbook_commune"
            ].tolist()
            summary["approximate_study_zone"] = frame.loc[
                frame["geography_status"] == "approximate_study_zone", "workbook_commune"
            ].tolist()
    write_json(manifest_path, summary)
    print(summary["checksums"])
    print("geography_status_counts:", summary.get("geography_status_counts"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
