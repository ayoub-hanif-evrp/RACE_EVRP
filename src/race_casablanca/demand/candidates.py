"""Build and snap OSM pickup candidates."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
from shapely.geometry import Point


POI_TAGS = {
    "shop": True,
    "office": True,
    "amenity": ["restaurant", "cafe", "bank", "pharmacy", "clinic", "hospital", "university", "school"],
    "building": ["commercial", "office", "retail", "apartments", "residential", "house"],
}


def fetch_candidates(boundary_geom) -> gpd.GeoDataFrame:
    from race_casablanca.network.osm_settings import OVERPASS_ENDPOINTS, configure_osmnx

    feats = None
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            configure_osmnx(use_cache=True, overpass_endpoint=endpoint)
            feats = ox.features_from_polygon(boundary_geom, tags=POI_TAGS)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if feats is None or feats.empty:
        raise RuntimeError(
            f"No OSM POI/building candidates found in the study boundary. Last error: {last_error}"
        )
    feats = feats.reset_index()
    # Prefer point geometries; polygons become centroids.
    geoms = []
    for geom in feats.geometry:
        if geom is None or geom.is_empty:
            geoms.append(None)
        elif geom.geom_type == "Point":
            geoms.append(geom)
        else:
            geoms.append(geom.centroid)
    out = feats.copy()
    out["geometry"] = geoms
    out = out[out["geometry"].notna()].copy()
    out = gpd.GeoDataFrame(out, geometry="geometry", crs=feats.crs)
    out["source_osm_type"] = out.get("element_type", out.get("osmid"))
    category = []
    for _, row in out.iterrows():
        for key in ("shop", "office", "amenity", "building"):
            val = row.get(key)
            if pd.notna(val):
                category.append(f"{key}={val}")
                break
        else:
            category.append("unknown")
    out["category"] = category
    out["lon"] = out.geometry.x
    out["lat"] = out.geometry.y
    return out


def snap_to_graph(candidates: gpd.GeoDataFrame, graph, max_snap_m: float = 150.0) -> gpd.GeoDataFrame:
    import osmnx as ox

    xs = candidates.geometry.x.to_numpy()
    ys = candidates.geometry.y.to_numpy()
    nearest = ox.distance.nearest_nodes(graph, xs, ys, return_dist=True)
    if isinstance(nearest, tuple):
        nodes, dists = nearest
    else:
        nodes, dists = nearest, [None] * len(candidates)
    snapped = candidates.copy()
    snapped["snap_node"] = list(nodes)
    snapped["snap_distance_m"] = list(dists)
    snapped["accessible"] = snapped["snap_distance_m"].le(max_snap_m)
    rejected = int((~snapped["accessible"]).sum())
    snapped.attrs["rejection_rate"] = rejected / max(len(snapped), 1)
    return snapped


def assign_zones(candidates: gpd.GeoDataFrame, zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    zones_valid = zones[zones["matched"] & zones.geometry.notna()][["workbook_commune", "geometry"]]
    joined = gpd.sjoin(candidates, zones_valid, how="left", predicate="within")
    joined = joined.rename(columns={"workbook_commune": "commune"})
    return joined
