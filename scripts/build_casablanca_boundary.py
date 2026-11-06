"""Match workbook communes to OSM admin polygons and write the study boundary."""

from __future__ import annotations

import sys

import pandas as pd
from shapely.geometry import box

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.boundary import (
    fetch_admin_in_envelope,
    fill_unmatched_with_od_hulls,
    match_admin_polygons,
    match_communes_via_nominatim,
    write_boundary_products,
)
from race_casablanca.paths import manifest_dir, traffic_dir, zones_dir


def main() -> int:
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
    # Fill unmatched via Nominatim if Overpass matched partially.
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
    summary = write_boundary_products(matched, zones_dir())
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
    write_json(manifest_dir() / "boundary_manifest.json", summary)
    print(summary)
    if summary["n_matched"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
