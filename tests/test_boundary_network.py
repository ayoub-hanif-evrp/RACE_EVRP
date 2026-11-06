"""Integrity tests for Casablanca boundary, network, and snapping artifacts."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
import pytest

from race_casablanca.paths import candidates_dir, roads_dir, traffic_dir, zones_dir


@pytest.fixture(scope="module")
def boundary():
    path = zones_dir() / "study_boundary.gpkg"
    if not path.exists():
        pytest.skip("study boundary not built")
    return gpd.read_file(path, layer="boundary")


@pytest.fixture(scope="module")
def crosswalk():
    path = zones_dir() / "zone_crosswalk.csv"
    if not path.exists():
        pytest.skip("zone crosswalk not built")
    return pd.read_csv(path)


def test_boundary_crs_and_nonempty(boundary):
    assert boundary.crs is not None
    assert str(boundary.crs).lower() in {"epsg:4326", "epsg:4326"}
    geom = boundary.geometry.iloc[0]
    assert geom is not None and not geom.is_empty
    assert geom.area > 0


def test_crosswalk_reports_matches(crosswalk):
    assert len(crosswalk) == 22
    assert "matched" in crosswalk.columns
    assert int(crosswalk["matched"].sum()) >= 1


def test_network_lengths_directions_connectivity():
    graphml = roads_dir() / "casablanca_drive.graphml"
    if not graphml.exists():
        pytest.skip("drive graph not built")
    graph = ox.load_graphml(graphml)
    assert graph.is_directed()
    assert graph.number_of_nodes() > 1000
    assert graph.number_of_edges() > 1000
    lengths = [float(d.get("length") or 0.0) for _, _, _, d in graph.edges(keys=True, data=True)]
    assert lengths and min(lengths) > 0
    assert all(float(d.get("free_flow_time_s") or 0.0) >= 0 for _, _, _, d in graph.edges(keys=True, data=True))
    weak = max(len(c) for c in nx.weakly_connected_components(graph))
    assert weak == graph.number_of_nodes()


def test_pickup_candidate_snap_stats():
    path = candidates_dir() / "pickup_candidates.csv"
    if not path.exists():
        pytest.skip("pickup candidates not built")
    df = pd.read_csv(path)
    assert len(df) > 100
    assert "accessible" in df.columns
    assert float(df["accessible"].mean()) > 0.9
    assert float(df.loc[df["accessible"], "snap_distance_m"].median()) < 150


def test_communes_have_population_column():
    path = traffic_dir() / "communes.csv"
    assert path.exists()
    df = pd.read_csv(path)
    assert "population" in df.columns
    assert df["population"].notna().all()
    assert (df["population"] > 0).all()
