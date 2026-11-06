"""Fetch OSM pickup candidates, snap to the drive graph, assign zones."""

from __future__ import annotations

import sys

import geopandas as gpd
import osmnx as ox
import pandas as pd
import yaml

from race_casablanca.demand.candidates import assign_zones, fetch_candidates, snap_to_graph
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import candidates_dir, config_dir, manifest_dir, roads_dir, zones_dir


def main() -> int:
    boundary = gpd.read_file(zones_dir() / "study_boundary.gpkg", layer="boundary").geometry.iloc[0]
    zones = gpd.read_file(zones_dir() / "zone_crosswalk.gpkg", layer="zones")
    config = yaml.safe_load((config_dir() / "demand_default.yaml").read_text(encoding="utf-8"))
    print("Fetching OSM POI/building candidates...")
    ox.settings.use_cache = True
    candidates = fetch_candidates(boundary)
    print(f"Candidates before snap: {len(candidates)}")
    graph = ox.load_graphml(roads_dir() / "casablanca_drive.graphml")
    snapped = snap_to_graph(candidates, graph, max_snap_m=float(config["spatial"]["max_snap_distance_m"]))
    zoned = assign_zones(snapped, zones)
    out = candidates_dir()
    out.mkdir(parents=True, exist_ok=True)
    keep_cols = [
        c
        for c in [
            "osmid",
            "category",
            "name",
            "commune",
            "lat",
            "lon",
            "snap_node",
            "snap_distance_m",
            "accessible",
            "geometry",
        ]
        if c in zoned.columns
    ]
    final = zoned[keep_cols].copy()
    final.to_file(out / "pickup_candidates.gpkg", driver="GPKG")
    final.drop(columns="geometry").to_csv(out / "pickup_candidates.csv", index=False)
    summary = {
        "generated_at_utc": utc_now(),
        "n_candidates": int(len(final)),
        "n_accessible": int(final["accessible"].sum()),
        "rejection_rate": float((~final["accessible"]).mean()),
        "median_snap_distance_m": float(final.loc[final["accessible"], "snap_distance_m"].median()),
        "n_with_commune": int(final["commune"].notna().sum()) if "commune" in final.columns else 0,
    }
    write_json(manifest_dir() / "pickup_candidates_manifest.json", summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
