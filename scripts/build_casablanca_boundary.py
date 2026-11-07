"""Verify pinned Casablanca study geography, or explicitly regenerate with audit."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd
from shapely.geometry import box

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.boundary import (
    fetch_admin_in_envelope,
    fill_unmatched_with_od_hulls,
    match_admin_polygons,
    match_communes_via_nominatim,
    pin_boundary_artifact_checksums,
    verify_boundary_checksums,
    write_boundary_products,
)
from race_casablanca.paths import manifest_dir, traffic_dir, zones_dir


def _load_manifest() -> dict:
    path = manifest_dir() / "boundary_manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def verify_only() -> int:
    zones = zones_dir()
    manifest = _load_manifest()
    result = verify_boundary_checksums(zones, manifest)
    print(result)
    if not result["ok"]:
        print(
            "Pinned boundary checksum verification FAILED. "
            "Do not overwrite from live Overpass/Nominatim without --force-regenerate.",
            file=sys.stderr,
        )
        return 1
    print("Pinned study geography verified; no live rebuild performed.")
    return 0


def regenerate(*, audit_dir: Path) -> int:
    """Live Overpass/Nominatim rebuild into a staging area with checksum audit."""

    communes = pd.read_csv(traffic_dir() / "communes.csv")
    coords = pd.read_csv(traffic_dir() / "coordinate_points.csv")
    west, east = float(coords["lon"].min() - 0.05), float(coords["lon"].max() + 0.05)
    south, north = float(coords["lat"].min() - 0.05), float(coords["lat"].max() + 0.05)
    envelope = box(west, south, east, north)
    print(f"Fetching OSM admin polygons in envelope {west, south, east, north}")
    try:
        admin = fetch_admin_in_envelope(west, south, east, north)
        print(f"Admin candidates: {len(admin)}")
        matched = match_admin_polygons(communes, admin, envelope=envelope)
        method = "overpass_admin_features_name_match"
    except Exception as exc:  # noqa: BLE001
        print(f"Overpass admin fetch failed ({exc}); falling back to Nominatim.")
        matched = match_communes_via_nominatim(communes, envelope=envelope)
        method = "nominatim_geocode_fallback"
        admin = None
    if method.startswith("overpass") and (~matched["matched"]).any():
        print("Attempting Nominatim fill for unmatched communes...")
        unmatched = communes[communes["commune"].isin(matched.loc[~matched["matched"], "workbook_commune"])]
        filled = match_communes_via_nominatim(unmatched, envelope=envelope)
        for _, row in filled[filled["matched"]].iterrows():
            idx = matched.index[matched["workbook_commune"] == row["workbook_commune"]][0]
            for col in ["matched", "osm_name", "osm_id", "geometry"]:
                matched.at[idx, col] = row[col]
            if "nominatim_query" in filled.columns:
                matched.at[idx, "nominatim_query"] = row.get("nominatim_query")
        method = "overpass_plus_nominatim_fill"
    osm_matched = int(matched["matched"].sum())
    if (~matched["matched"]).any():
        print("Filling remaining unmatched communes with workbook OD convex hulls...")
        matched = fill_unmatched_with_od_hulls(matched, coords)
        method = f"{method}+od_hull_fallback"

    audit_dir.mkdir(parents=True, exist_ok=True)
    staging = audit_dir / "staging_zones"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    summary = write_boundary_products(matched, staging)
    summary["generated_at_utc"] = utc_now()
    summary["envelope"] = {"west": west, "south": south, "east": east, "north": north}
    summary["method"] = method
    summary["n_admin_candidates"] = int(len(admin)) if admin is not None else None
    summary["n_osm_admin_matched"] = osm_matched
    summary["n_od_hull_fallback"] = int(
        matched["match_method"].eq("workbook_od_convex_hull_buffer").sum()
        if "match_method" in matched.columns
        else 0
    )
    summary["checksums"] = pin_boundary_artifact_checksums(staging)

    old = _load_manifest()
    old_pin = (old.get("checksums") or {}).get("artifacts") or {}
    new_pin = summary["checksums"]["artifacts"]
    diff = {}
    for name in sorted(set(old_pin) | set(new_pin)):
        diff[name] = {
            "old_sha256": (old_pin.get(name) or {}).get("sha256"),
            "new_sha256": (new_pin.get(name) or {}).get("sha256"),
            "changed": (old_pin.get(name) or {}).get("sha256") != (new_pin.get(name) or {}).get("sha256"),
        }
    summary["geometry_checksum_diff_vs_pinned"] = diff
    write_json(audit_dir / "boundary_regeneration_audit.json", summary)

    # Promote staging into zones only after writing the audit.
    zones = zones_dir()
    zones.mkdir(parents=True, exist_ok=True)
    for name in ["study_boundary.gpkg", "zone_crosswalk.gpkg", "zone_crosswalk.csv"]:
        shutil.copy2(staging / name, zones / name)
    write_json(manifest_dir() / "boundary_manifest.json", summary)
    print(summary)
    print(f"Audit written to {audit_dir / 'boundary_regeneration_audit.json'}")
    if summary["n_matched"] == 0:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Default: verify SHA-256-pinned study geography (no live APIs). "
            "Use --force-regenerate for an audited live rebuild."
        )
    )
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Live Overpass/Nominatim rebuild with staging + checksum audit (not the default Stage-1 path).",
    )
    parser.add_argument(
        "--audit-dir",
        type=Path,
        default=manifest_dir() / "boundary_regen_audit",
        help="Directory for regeneration staging and audit JSON.",
    )
    args = parser.parse_args()
    if args.force_regenerate:
        return regenerate(audit_dir=args.audit_dir)
    return verify_only()


if __name__ == "__main__":
    sys.exit(main())
