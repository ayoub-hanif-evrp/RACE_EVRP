"""Replace clearly incorrect admin polygons with OD-hull study areas (no live APIs)."""

from __future__ import annotations

import sys

import geopandas as gpd
import pandas as pd

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.boundary import pin_boundary_artifact_checksums
from race_casablanca.paths import manifest_dir, traffic_dir, zones_dir


# Zones whose retained OSM/Nominatim geometry is known-wrong (e.g. Al Idrissia→Al Fida).
REPAIR = {
    "Al Idrissia": "rejected_al_fida_nominatim_match_replaced_with_od_hull",
    "Sidi Maarouf": "rejected_annex_nominatim_match_replaced_with_od_hull",
}


def _od_hull(coords: pd.DataFrame, commune: str, buffer_m: float = 250.0):
    pts = coords[coords["commune"] == commune]
    if pts.empty:
        raise RuntimeError(f"No OD coordinates for {commune}")
    gdf = gpd.GeoDataFrame(geometry=gpd.points_from_xy(pts["lon"], pts["lat"]), crs="EPSG:4326")
    projected = gdf.to_crs(gdf.estimate_utm_crs())
    hull = projected.unary_union.convex_hull.buffer(buffer_m)
    return gpd.GeoSeries([hull], crs=projected.crs).to_crs("EPSG:4326").iloc[0]


def main() -> int:
    zones_path = zones_dir() / "zone_crosswalk.gpkg"
    csv_path = zones_dir() / "zone_crosswalk.csv"
    zones = gpd.read_file(zones_path, layer="zones")
    coords = pd.read_csv(traffic_dir() / "coordinate_points.csv")
    repaired = []
    for commune, note in REPAIR.items():
        mask = zones["workbook_commune"] == commune
        if not mask.any():
            continue
        geom = _od_hull(coords, commune)
        zones.loc[mask, "geometry"] = geom
        zones.loc[mask, "matched"] = True
        zones.loc[mask, "osm_name"] = None
        zones.loc[mask, "osm_id"] = None
        zones.loc[mask, "admin_level"] = None
        zones.loc[mask, "match_score"] = 0.0
        zones.loc[mask, "nominatim_query"] = None
        zones.loc[mask, "match_method"] = "workbook_od_convex_hull_buffer"
        zones.loc[mask, "geography_status"] = "approximate_study_zone"
        zones.loc[mask, "audit_note"] = note
        repaired.append(commune)

    # Rebuild study boundary as union of zone polygons.
    boundary = zones.unary_union
    boundary_gdf = gpd.GeoDataFrame({"name": ["casablanca_study_area"]}, geometry=[boundary], crs=zones.crs)
    zones.to_file(zones_path, layer="zones", driver="GPKG")
    boundary_gdf.to_file(zones_dir() / "study_boundary.gpkg", layer="boundary", driver="GPKG")
    zones.drop(columns="geometry").to_csv(csv_path, index=False, lineterminator="\n")

    import json

    manifest_path = manifest_dir() / "boundary_manifest.json"
    summary = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    summary["generated_at_utc"] = utc_now()
    summary["checksums"] = pin_boundary_artifact_checksums(zones_dir())
    summary["geometry_repair"] = {
        "repaired_communes": repaired,
        "note": "Suspicious Nominatim geometries replaced with OD convex-hull study areas; not official admin polygons.",
    }
    # Refresh geography counts.
    frame = zones.drop(columns="geometry")
    summary["geography_status_counts"] = {
        str(k): int(v) for k, v in frame["geography_status"].value_counts().items()
    }
    write_json(manifest_path, summary)
    print({"repaired": repaired, "checksums": summary["checksums"]["artifacts"]})
    return 0


if __name__ == "__main__":
    sys.exit(main())
