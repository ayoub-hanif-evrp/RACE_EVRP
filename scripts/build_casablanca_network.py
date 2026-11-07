"""Build the directed Casablanca drive graph from the frozen Geofabrik PBF."""

from __future__ import annotations

import sys

import geopandas as gpd
import osmnx as ox

from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.build import export_graph, graph_integrity
from race_casablanca.network.pbf_extract import build_drive_graph_from_pbf
from race_casablanca.network.speeds import load_speed_config
from race_casablanca.paths import config_dir, manifest_dir, raw_dir, roads_dir, zones_dir


def main() -> int:
    boundary = gpd.read_file(zones_dir() / "study_boundary.gpkg", layer="boundary")
    geom = boundary.geometry.iloc[0]
    speed_config = load_speed_config(config_dir() / "travel_time.yaml")
    pbf = raw_dir() / "osm" / "morocco-260101.osm.pbf"
    print(f"Building drive graph from frozen PBF {pbf} ...")
    graph = build_drive_graph_from_pbf(pbf, geom, speed_config)
    integrity = graph_integrity(graph)

    zones = gpd.read_file(zones_dir() / "zone_crosswalk.gpkg", layer="zones")
    nodes, edges = ox.graph_to_gdfs(graph)
    edges = edges.reset_index()
    mid = edges.copy()
    mid_proj = mid.to_crs(mid.estimate_utm_crs())
    mid_proj["geometry"] = mid_proj.geometry.interpolate(0.5, normalized=True)
    mid = mid_proj.to_crs(edges.crs)
    # Prefer verified admin zones for edge labeling when overlaps exist.
    if "geography_status" in zones.columns:
        preferred = zones[zones["geography_status"] == "verified_admin"].copy()
        if preferred.empty:
            preferred = zones[zones["matched"]].copy()
    else:
        preferred = zones[zones["matched"]].copy()
    joined = gpd.sjoin(
        mid[["u", "v", "key", "geometry"]],
        preferred[["workbook_commune", "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined.drop_duplicates(subset=["u", "v", "key"], keep="first")
    zone_map = {
        (row.u, row.v, row.key): row.workbook_commune
        for row in joined.itertuples()
        if getattr(row, "workbook_commune", None) is not None
    }
    for u, v, key, data in graph.edges(keys=True, data=True):
        data["zone_commune"] = zone_map.get((u, v, key))

    paths = export_graph(graph, roads_dir())
    connectivity = dict(graph.graph.get("race_connectivity_filter") or {})
    manifest = {
        "generated_at_utc": utc_now(),
        "method": "pyrosm_extract_from_geofabrik_morocco-260101.osm.pbf clipped to study boundary",
        "pbf_path": str(pbf),
        "pbf_sha256": sha256_file(pbf) if pbf.exists() else None,
        "integrity": integrity,
        "connectivity_filter": connectivity,
        "scc_exclusion": {
            "pre_scc_nodes": connectivity.get("pre_scc_nodes"),
            "pre_scc_edges": connectivity.get("pre_scc_edges"),
            "post_scc_nodes": connectivity.get("post_scc_nodes"),
            "post_scc_edges": connectivity.get("post_scc_edges"),
            "nodes_excluded": connectivity.get("nodes_excluded_by_scc"),
            "edges_excluded": connectivity.get("edges_excluded_by_scc"),
            "fraction_nodes_excluded": connectivity.get("fraction_nodes_excluded_by_scc"),
            "fraction_edges_excluded": connectivity.get("fraction_edges_excluded_by_scc"),
            "note": graph.graph.get("race_scc_note"),
        },
        "paths": paths,
        "speed_config": str(config_dir() / "travel_time.yaml"),
        "osm_attribution": "© OpenStreetMap contributors (ODbL)",
        "software": {"pyrosm": "required", "osmnx": ox.__version__},
    }
    write_json(manifest_dir() / "network_manifest.json", manifest)
    print(integrity)
    return 0


if __name__ == "__main__":
    sys.exit(main())
