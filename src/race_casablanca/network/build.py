"""Build a directed drive graph for the Casablanca study boundary."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd

from race_casablanca.network.speeds import free_flow_speed_kmh, load_speed_config


def fetch_admin_polygons(polygon) -> gpd.GeoDataFrame:
    """Fetch administrative boundaries intersecting the study envelope."""

    tags = {"boundary": "administrative"}
    features = ox.features_from_polygon(polygon, tags=tags)
    if features.empty:
        raise RuntimeError("OSM returned no administrative boundaries for the envelope.")
    # Keep polygonal admin features with a name.
    polys = features[features.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    if "name" not in polys.columns:
        raise RuntimeError("Administrative features lack name tags.")
    polys = polys[polys["name"].notna()].copy()
    polys = polys.reset_index()
    return polys


def build_drive_graph(boundary_geom, speed_config: dict):
    from race_casablanca.network.osm_settings import OVERPASS_ENDPOINTS, configure_osmnx

    last_error: Exception | None = None
    graph = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            configure_osmnx(use_cache=True, overpass_endpoint=endpoint)
            print(f"Trying Overpass endpoint {endpoint}")
            graph = ox.graph_from_polygon(
                boundary_geom,
                network_type="drive",
                simplify=True,
                retain_all=False,
                truncate_by_edge=True,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"Overpass failed at {endpoint}: {exc}")
    if graph is None:
        raise RuntimeError(f"All Overpass endpoints failed for drive graph. Last error: {last_error}")
    graph = ox.add_edge_speeds(graph)
    graph = ox.add_edge_travel_times(graph)
    # Attach documented free-flow seconds using local fallbacks when needed.
    for u, v, key, data in graph.edges(keys=True, data=True):
        highway = data.get("highway")
        speed = free_flow_speed_kmh(highway, data.get("maxspeed"), speed_config)
        length = float(data.get("length") or 0.0)
        data["free_flow_speed_kmh"] = speed
        # length metres / (speed km/h -> m/s) = length * 3.6 / speed
        data["free_flow_time_s"] = (length * 3.6 / max(speed, 1e-6)) if length > 0 else 0.0
        data["race_highway"] = highway if not isinstance(highway, list) else ",".join(map(str, highway))
    return graph


def graph_integrity(graph) -> dict:
    undirected = graph.to_undirected()
    weak = [len(c) for c in nx.weakly_connected_components(graph)]
    strong = [len(c) for c in nx.strongly_connected_components(graph)]
    lengths = [float(d.get("length") or 0.0) for _, _, _, d in graph.edges(keys=True, data=True)]
    return {
        "n_nodes": int(graph.number_of_nodes()),
        "n_edges": int(graph.number_of_edges()),
        "crs": str(graph.graph.get("crs")),
        "largest_weak_component_nodes": int(max(weak) if weak else 0),
        "largest_strong_component_nodes": int(max(strong) if strong else 0),
        "n_weak_components": int(len(weak)),
        "n_strong_components": int(len(strong)),
        "min_edge_length_m": float(min(lengths) if lengths else 0.0),
        "max_edge_length_m": float(max(lengths) if lengths else 0.0),
        "mean_edge_length_m": float(sum(lengths) / len(lengths) if lengths else 0.0),
        "nonpositive_length_edges": int(sum(1 for value in lengths if value <= 0)),
        "turn_restriction_note": (
            "OSMnx drive graphs encode one-way restrictions on edges. Complex turn "
            "restrictions that require relation-level turn bans are not fully enforced "
            "by a simple directed graph representation."
        ),
    }


def export_graph(graph, roads_dir: Path) -> dict:
    roads_dir.mkdir(parents=True, exist_ok=True)
    graphml = roads_dir / "casablanca_drive.graphml"
    ox.save_graphml(graph, graphml)
    nodes, edges = ox.graph_to_gdfs(graph)
    nodes_path = roads_dir / "nodes.gpkg"
    edges_path = roads_dir / "edges.gpkg"
    nodes.to_file(nodes_path, driver="GPKG")
    edges.to_file(edges_path, driver="GPKG")
    return {
        "graphml": str(graphml),
        "nodes_gpkg": str(nodes_path),
        "edges_gpkg": str(edges_path),
    }
