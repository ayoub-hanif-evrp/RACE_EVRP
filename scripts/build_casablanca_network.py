"""Build the directed Casablanca drive graph inside the study boundary."""

from __future__ import annotations

import sys

import geopandas as gpd
import osmnx as ox

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.build import build_drive_graph, export_graph, graph_integrity
from race_casablanca.network.speeds import load_speed_config
from race_casablanca.paths import config_dir, manifest_dir, roads_dir, zones_dir


def main() -> int:
    boundary = gpd.read_file(zones_dir() / "study_boundary.gpkg", layer="boundary")
    geom = boundary.geometry.iloc[0]
    speed_config = load_speed_config(config_dir() / "travel_time.yaml")
    print("Building drive graph via OSMnx (drive network inside study boundary)...")
    ox.settings.use_cache = True
    graph = build_drive_graph(geom, speed_config)
    integrity = graph_integrity(graph)
    paths = export_graph(graph, roads_dir())
    # Attach zone commune labels to edges by midpoint spatial join.
    zones = gpd.read_file(zones_dir() / "zone_crosswalk.gpkg", layer="zones")
    nodes, edges = ox.graph_to_gdfs(graph)
    edges = edges.reset_index()
    mid = edges.copy()
    # Project for midpoint interpolation, then return to WGS84 for the spatial join.
    mid_proj = mid.to_crs(mid.estimate_utm_crs())
    mid_proj["geometry"] = mid_proj.geometry.interpolate(0.5, normalized=True)
    mid = mid_proj.to_crs(edges.crs)
    zones_valid = zones[zones["matched"]].copy()
    joined = gpd.sjoin(
        mid[["u", "v", "key", "geometry"]],
        zones_valid[["workbook_commune", "geometry"]],
        how="left",
        predicate="within",
    )
    zone_map = {
        (row.u, row.v, row.key): row.workbook_commune
        for row in joined.itertuples()
        if getattr(row, "workbook_commune", None) is not None
    }
    for u, v, key, data in graph.edges(keys=True, data=True):
        data["zone_commune"] = zone_map.get((u, v, key))
    # Re-export with zone tags.
    paths = export_graph(graph, roads_dir())
    manifest = {
        "generated_at_utc": utc_now(),
        "method": (
            "OSMnx graph_from_polygon on the matched-commune union boundary. "
            "Geofabrik morocco-260101.osm.pbf is retained as the archived Morocco extract "
            "for provenance; network construction uses the study-area polygon query."
        ),
        "integrity": integrity,
        "paths": paths,
        "speed_config": str(config_dir() / "travel_time.yaml"),
        "osm_attribution": "© OpenStreetMap contributors (ODbL)",
    }
    write_json(manifest_dir() / "network_manifest.json", manifest)
    print(integrity)
    return 0


if __name__ == "__main__":
    sys.exit(main())
