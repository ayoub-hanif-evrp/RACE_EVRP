"""Audit workbook zone matches; mark verified vs approximate study zones."""

from __future__ import annotations

import sys

import geopandas as gpd
import pandas as pd

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import manifest_dir, zones_dir


# Names that previously received incorrect Nominatim annex/parent matches.
FORCE_APPROXIMATE = {
    "Al Idrissia",  # matched to Arrondissement d'Al Fida
    "Sidi Maarouf",  # matched to annex/poi rather than clear admin polygon
}


def main() -> int:
    path = zones_dir() / "zone_crosswalk.gpkg"
    zones = gpd.read_file(path, layer="zones")
    statuses = []
    notes = []
    for _, row in zones.iterrows():
        name = row["workbook_commune"]
        method = row.get("match_method")
        osm_name = str(row.get("osm_name") or "")
        admin_level = row.get("admin_level")
        if name in FORCE_APPROXIMATE:
            statuses.append("approximate_study_zone")
            notes.append("reclassified_after_audit_suspicious_osm_match")
            continue
        if method == "workbook_od_convex_hull_buffer":
            statuses.append("approximate_study_zone")
            notes.append("od_convex_hull_buffer_not_official_admin")
            continue
        if method == "osm_admin_name_match" and str(admin_level) in {"9", "10"} and "arrondissement" in osm_name.lower():
            statuses.append("verified_admin")
            notes.append("admin_level_9_or_10_arrondissement_name_match")
            continue
        if method == "osm_admin_name_match" and "arrondissement" in osm_name.lower():
            statuses.append("verified_admin")
            notes.append("arrondissement_name_match")
            continue
        statuses.append("approximate_study_zone")
        notes.append("insufficient_admin_evidence")
    zones["geography_status"] = statuses
    zones["audit_note"] = notes
    # For forced approximate zones, clear misleading osm identity while keeping geometry for study use.
    for name in FORCE_APPROXIMATE:
        mask = zones["workbook_commune"] == name
        zones.loc[mask, "match_method"] = "approximate_retained_geometry_pending_admin_id"
    zones.to_file(path, layer="zones", driver="GPKG")
    zones.drop(columns="geometry").to_csv(zones_dir() / "zone_crosswalk.csv", index=False)

    summary = {
        "generated_at_utc": utc_now(),
        "n_zones": int(len(zones)),
        "n_verified_admin": int((zones["geography_status"] == "verified_admin").sum()),
        "n_approximate_study_zone": int((zones["geography_status"] == "approximate_study_zone").sum()),
        "verified": zones.loc[zones["geography_status"] == "verified_admin", "workbook_commune"].tolist(),
        "approximate": zones.loc[zones["geography_status"] == "approximate_study_zone", "workbook_commune"].tolist(),
        "claim": (
            "Not all 22 workbook zones are verified official Casablanca communes. "
            "Approximate study zones are retained for synthetic demand geography only."
        ),
    }
    write_json(manifest_dir() / "zone_audit_manifest.json", summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
