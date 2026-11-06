"""Graph-based feasibility witness and independent validator tests."""

from __future__ import annotations

import networkx as nx
import pandas as pd
import pytest

from race_casablanca.demand.feasibility import build_graph_feasible_witness, validate_schedule
from race_casablanca.network.travel_time import CongestionModel


def _tiny_graph():
    g = nx.MultiDiGraph()
    # Depot 0 --1km-- 1 --1km-- 2, with return edges.
    for u, v in [(0, 1), (1, 0), (1, 2), (2, 1), (0, 2), (2, 0)]:
        g.add_edge(u, v, key=0, length=1000.0, free_flow_time_s=120.0)
    return g


def _fleet(**over):
    base = {
        "usable_battery_kwh": 40.0,
        "payload_kg": 600.0,
        "initial_soc": 1.0,
        "min_reserve_soc": 0.15,
        "consumption_wh_per_km": 200.0,
        "n_vehicles": 2,
    }
    base.update(over)
    return base


def _model():
    return CongestionModel(citywide_hour=pd.Series({h: 1.0 for h in range(24)}))


def test_certified_feasible_schedule_on_tiny_graph():
    g = _tiny_graph()
    requests = pd.DataFrame(
        [
            {
                "request_id": "r0",
                "snap_node": 1,
                "release_min": 0,
                "tw_start_min": 0,
                "tw_end_min": 60,
                "service_min": 5,
                "weight_kg": 10,
            },
            {
                "request_id": "r1",
                "snap_node": 2,
                "release_min": 5,
                "tw_start_min": 5,
                "tw_end_min": 90,
                "service_min": 5,
                "weight_kg": 10,
            },
        ]
    )
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    assert result.certified
    assert "RETURN-" in " ".join(result.schedule["request_id"].astype(str))
    validation = validate_schedule(result.schedule, requests, _fleet(), 0, g, _model())
    assert validation["valid"]


def test_validator_rejects_insufficient_battery_route():
    g = _tiny_graph()
    requests = pd.DataFrame(
        [
            {
                "request_id": "r0",
                "snap_node": 1,
                "release_min": 0,
                "tw_start_min": 0,
                "tw_end_min": 60,
                "service_min": 5,
                "weight_kg": 10,
            }
        ]
    )
    # Tiny battery cannot cover out-and-back 2 km at 0.2 kWh/km with reserve.
    fleet = _fleet(usable_battery_kwh=0.2, min_reserve_soc=0.5, consumption_wh_per_km=200.0)
    result = build_graph_feasible_witness(requests, fleet, 0, g, _model())
    assert not result.certified


def test_impossible_tight_window_uncertified():
    g = _tiny_graph()
    requests = pd.DataFrame(
        [
            {
                "request_id": "r0",
                "snap_node": 2,
                "release_min": 0,
                "tw_start_min": 0,
                "tw_end_min": 0.5,  # 30 seconds; travel alone is 120s+
                "service_min": 5,
                "weight_kg": 10,
            }
        ]
    )
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    assert not result.certified
