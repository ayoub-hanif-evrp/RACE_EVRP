"""Independent tests for time-dependent earliest-arrival routing."""

from __future__ import annotations

import networkx as nx
import pandas as pd
import pytest

from race_casablanca.network.travel_time import (
    CongestionModel,
    earliest_arrival,
    exhaustive_earliest_arrival_dag,
    travel_time_seconds,
)


def _model(factors: dict[int, float]) -> CongestionModel:
    series = pd.Series({h: factors.get(h, 1.0) for h in range(24)})
    return CongestionModel(citywide_hour=series)


def test_parallel_edges_choose_faster_edge():
    g = nx.MultiDiGraph()
    g.add_edge(0, 1, key=0, free_flow_time_s=100.0, length=1000.0)
    g.add_edge(0, 1, key=1, free_flow_time_s=2.0, length=20.0)
    model = _model({})
    total, path, legs = earliest_arrival(g, 0, 1, 0.0, model)
    assert path == [0, 1]
    # TTI baseline: length/60 km/h → 20 m = 1.2 s
    assert abs(total - 1.2) < 1e-9
    assert legs[0]["key"] == 1


def test_agrees_with_exhaustive_dag_reference():
    g = nx.MultiDiGraph()
    # 0 -> 1 -> 3 and 0 -> 2 -> 3 with congestion jump after hour 1.
    g.add_edge(0, 1, key=0, free_flow_time_s=1000.0, length=1000.0)
    g.add_edge(1, 3, key=0, free_flow_time_s=1000.0, length=1000.0)
    g.add_edge(0, 2, key=0, free_flow_time_s=1500.0, length=1500.0)
    g.add_edge(2, 3, key=0, free_flow_time_s=100.0, length=100.0)
    model = _model({0: 3.0, 1: 1.0})
    dep = 3500.0  # near end of hour 0
    algo, _path, _legs = earliest_arrival(g, 0, 3, dep, model, allow_wait=True)
    ref = exhaustive_earliest_arrival_dag(g, 0, 3, dep, model, allow_wait=True)
    assert abs(algo - ref) < 1e-6


def test_waiting_can_improve_arrival_at_hour_boundary():
    g = nx.MultiDiGraph()
    g.add_edge(0, 1, key=0, free_flow_time_s=600.0, length=600.0)
    # Hour 8 congested, hour 9 free.
    model = _model({8: 3.0, 9: 1.0})
    ready = 8 * 3600 + 3500  # 100s before hour 9
    total_wait = travel_time_seconds(600.0, ready, model, wait_for_fifo=True)
    total_now = travel_time_seconds(600.0, ready, model, wait_for_fifo=False)
    assert total_wait < total_now


def test_disconnected_raises():
    g = nx.MultiDiGraph()
    g.add_node(0)
    g.add_node(1)
    model = _model({})
    with pytest.raises(nx.NetworkXNoPath):
        earliest_arrival(g, 0, 1, 0.0, model)


def test_directed_reachability_one_way():
    g = nx.MultiDiGraph()
    g.add_edge(0, 1, key=0, free_flow_time_s=5.0, length=50.0)
    model = _model({})
    total, path, _ = earliest_arrival(g, 0, 1, 0.0, model)
    assert path == [0, 1]
    # TTI baseline: 50 m / 60 km/h = 3.0 s
    assert abs(total - 3.0) < 1e-9
    with pytest.raises(nx.NetworkXNoPath):
        earliest_arrival(g, 1, 0, 0.0, model)
