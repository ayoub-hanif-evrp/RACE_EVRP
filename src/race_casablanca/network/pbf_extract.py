"""Extract Casablanca roads and POIs from a frozen Geofabrik OSM PBF snapshot."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd

from race_casablanca.network.speeds import free_flow_speed_kmh


def _bbox_from_geom(geom) -> list[float]:
    minx, miny, maxx, maxy = geom.bounds
    pad = 0.01
    return [minx - pad, miny - pad, maxx + pad, maxy + pad]


def build_drive_graph_from_pbf(pbf_path: Path, boundary_geom, speed_config: dict):
    """Build a directed drive MultiDiGraph from a local PBF using pyrosm."""

    from pyrosm import OSM

    if not pbf_path.exists():
        raise FileNotFoundError(f"Missing OSM PBF snapshot: {pbf_path}")
    bbox = _bbox_from_geom(boundary_geom)
    osm = OSM(str(pbf_path), bounding_box=bbox)
    nodes, edges = osm.get_network(network_type="driving", nodes=True)
    if nodes is None or edges is None or edges.empty:
        raise RuntimeError("PBF extract returned an empty driving network.")
    # Keep edges intersecting the study boundary.
    edges = gpd.GeoDataFrame(edges, geometry="geometry", crs="EPSG:4326")
    nodes = gpd.GeoDataFrame(nodes, geometry="geometry", crs="EPSG:4326")
    boundary_gdf = gpd.GeoDataFrame(geometry=[boundary_geom], crs="EPSG:4326")
    edges = edges[edges.intersects(boundary_geom)].copy()
    if edges.empty:
        raise RuntimeError("No driving edges intersect the study boundary after PBF clip.")
    # OSMnx expects u/v/key columns for graph_from_gdfs.
    if "u" not in edges.columns or "v" not in edges.columns:
        raise RuntimeError("pyrosm edges missing u/v columns")
    if "id" in nodes.columns and "osmid" not in nodes.columns:
        nodes = nodes.rename(columns={"id": "osmid"})
    nodes = nodes.set_index("osmid", drop=False)
    # Keep only nodes referenced by retained edges.
    used = set(edges["u"].astype("int64")).union(set(edges["v"].astype("int64")))
    nodes = nodes[nodes.index.isin(used)].copy()
    nodes["x"] = nodes.geometry.x
    nodes["y"] = nodes.geometry.y
    # OSMnx expects a unique MultiIndex (u, v, key) on edges; key must not
    # also appear as a data column or add_edge receives duplicate kwargs.
    edges = edges.copy()
    if "key" not in edges.columns:
        edges["key"] = 0
    edges = edges.set_index(["u", "v", "key"], drop=True)
    graph = ox.graph_from_gdfs(nodes, edges)
    # Ensure lengths exist; pyrosm usually provides length in meters.
    graph = ox.distance.add_edge_lengths(graph)
    # Match OSMnx Stage-1 practice: simplify true junctions only, drop tiny fragments.
    try:
        graph = ox.simplify_graph(graph)
    except Exception:  # noqa: BLE001
        pass
    # Keep largest weakly connected component for a contiguous study network.
    pre_wcc_nodes, pre_wcc_edges = graph.number_of_nodes(), graph.number_of_edges()
    if not nx.is_weakly_connected(graph):
        largest = max(nx.weakly_connected_components(graph), key=len)
        graph = graph.subgraph(largest).copy()
    post_wcc_nodes, post_wcc_edges = graph.number_of_nodes(), graph.number_of_edges()
    # Restrict further to the largest strongly connected component so depot
    # returns and directed tours are graph-feasible under one-way constraints.
    pre_scc_nodes, pre_scc_edges = post_wcc_nodes, post_wcc_edges
    if not nx.is_strongly_connected(graph):
        scc = max(nx.strongly_connected_components(graph), key=len)
        graph = graph.subgraph(scc).copy()
        graph.graph["race_scc_note"] = (
            "Retained largest strongly connected component from the PBF drive extract "
            "so directed tours with depot return remain feasible under one-way streets."
        )
    post_scc_nodes, post_scc_edges = graph.number_of_nodes(), graph.number_of_edges()
    graph.graph["race_connectivity_filter"] = {
        "pre_wcc_nodes": int(pre_wcc_nodes),
        "pre_wcc_edges": int(pre_wcc_edges),
        "post_wcc_nodes": int(post_wcc_nodes),
        "post_wcc_edges": int(post_wcc_edges),
        "pre_scc_nodes": int(pre_scc_nodes),
        "pre_scc_edges": int(pre_scc_edges),
        "post_scc_nodes": int(post_scc_nodes),
        "post_scc_edges": int(post_scc_edges),
        "nodes_excluded_by_scc": int(pre_scc_nodes - post_scc_nodes),
        "edges_excluded_by_scc": int(pre_scc_edges - post_scc_edges),
        "fraction_nodes_excluded_by_scc": float(
            (pre_scc_nodes - post_scc_nodes) / pre_scc_nodes if pre_scc_nodes else 0.0
        ),
        "fraction_edges_excluded_by_scc": float(
            (pre_scc_edges - post_scc_edges) / pre_scc_edges if pre_scc_edges else 0.0
        ),
    }
    for u, v, key, data in graph.edges(keys=True, data=True):
        highway = data.get("highway")
        speed = free_flow_speed_kmh(highway, data.get("maxspeed"), speed_config)
        length = float(data.get("length") or 0.0)
        data["free_flow_speed_kmh"] = speed
        data["free_flow_time_s"] = (length * 3.6 / max(speed, 1e-6)) if length > 0 else 0.0
        data["race_highway"] = highway if not isinstance(highway, list) else ",".join(map(str, highway))
    graph.graph["crs"] = "epsg:4326"
    graph.graph["race_source"] = "geofabrik_pbf"
    graph.graph["race_pbf"] = str(pbf_path)
    graph.graph["race_bbox"] = bbox
    return graph


def extract_poi_candidates_from_pbf(pbf_path: Path, boundary_geom) -> gpd.GeoDataFrame:
    """Extract shop/office/amenity/building candidates from the frozen PBF."""

    from pyrosm import OSM
    import pandas as pd

    bbox = _bbox_from_geom(boundary_geom)
    osm = OSM(str(pbf_path), bounding_box=bbox)
    frames = []
    # Custom filters for Stage-1 pickup-like places.
    try:
        pois = osm.get_pois(custom_filter={"shop": True, "office": True, "amenity": True})
        if pois is not None and not pois.empty:
            frames.append(pois)
    except Exception:  # noqa: BLE001
        pass
    try:
        buildings = osm.get_buildings()
        if buildings is not None and not buildings.empty:
            keep = buildings[
                buildings.get("building", pd.Series(dtype=object)).astype(str).str.lower().isin(
                    ["commercial", "office", "retail", "apartments", "residential", "house", "yes"]
                )
            ]
            frames.append(keep)
    except Exception:  # noqa: BLE001
        pass
    if not frames:
        raise RuntimeError("No POI/building candidates extracted from PBF.")
    feats = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    feats = feats[feats.intersects(boundary_geom)].copy()
    geoms = []
    for geom in feats.geometry:
        if geom is None or geom.is_empty:
            geoms.append(None)
        elif geom.geom_type == "Point":
            geoms.append(geom)
        else:
            geoms.append(geom.centroid)
    feats = feats.copy()
    feats["geometry"] = geoms
    feats = feats[feats["geometry"].notna()].copy()
    feats = gpd.GeoDataFrame(feats, geometry="geometry", crs="EPSG:4326")
    category = []
    for _, row in feats.iterrows():
        for key in ("shop", "office", "amenity", "building"):
            val = row.get(key)
            if pd.notna(val) and str(val).lower() not in {"nan", "none", ""}:
                category.append(f"{key}={val}")
                break
        else:
            category.append("unknown")
    feats["category"] = category
    feats["lon"] = feats.geometry.x
    feats["lat"] = feats.geometry.y
    if "id" in feats.columns and "osmid" not in feats.columns:
        feats["osmid"] = feats["id"]
    return feats
