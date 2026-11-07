"""Graph-based feasibility witness and independent validator tests."""

from __future__ import annotations

import networkx as nx
import pandas as pd
import pytest

from race_casablanca.demand.feasibility import build_graph_feasible_witness, validate_schedule
from race_casablanca.network.travel_time import CongestionModel


def _tiny_graph():
    g = nx.MultiDiGraph()
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


def _requests():
    return pd.DataFrame(
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


def test_certified_feasible_schedule_on_tiny_graph():
    g = _tiny_graph()
    requests = _requests()
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    assert result.certified
    assert "RETURN-" in " ".join(result.schedule["request_id"].astype(str))
    validation = validate_schedule(result.schedule, requests, _fleet(), 0, g, _model())
    assert validation["valid"], validation["violations"]
    assert validation["coverage"]["served"] == 2


def test_validator_rejects_insufficient_battery_route():
    g = _tiny_graph()
    requests = _requests().iloc[:1]
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
                "tw_end_min": 0.5,
                "service_min": 5,
                "weight_kg": 10,
            }
        ]
    )
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    assert not result.certified


def test_empty_schedule_rejected_against_requests():
    g = _tiny_graph()
    validation = validate_schedule(pd.DataFrame(), _requests(), _fleet(), 0, g, _model())
    assert not validation["valid"]
    assert any(v["type"] == "empty_schedule" for v in validation["violations"])


def test_missing_pickup_rejected():
    g = _tiny_graph()
    requests = _requests()
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    assert result.certified
    schedule = result.schedule[result.schedule["request_id"] != "r1"].copy()
    validation = validate_schedule(schedule, requests, _fleet(), 0, g, _model())
    assert not validation["valid"]
    assert any(v["type"] == "missing_pickup" for v in validation["violations"])


def test_duplicate_pickup_rejected():
    g = _tiny_graph()
    requests = _requests()
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    pickup = result.schedule[~result.schedule["request_id"].astype(str).str.startswith("RETURN-")].iloc[[0]]
    schedule = pd.concat([result.schedule, pickup], ignore_index=True)
    validation = validate_schedule(schedule, requests, _fleet(), 0, g, _model())
    assert not validation["valid"]
    assert any(v["type"] == "duplicate_pickup" for v in validation["violations"])


def test_fabricated_return_wrong_depot_rejected():
    g = _tiny_graph()
    requests = _requests()
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    schedule = result.schedule.copy()
    mask = schedule["request_id"].astype(str).str.startswith("RETURN-")
    schedule.loc[mask, "to_node"] = 1
    # Keep path_nodes ending at 1 so endpoint check can also fire; force destination mismatch.
    schedule.loc[mask, "path_nodes"] = schedule.loc[mask, "path_nodes"].astype(str).str.replace(
        r"\d+$", "1", regex=True
    )
    validation = validate_schedule(schedule, requests, _fleet(), 0, g, _model())
    assert not validation["valid"]
    assert any(v["type"] in {"return_not_to_depot", "vehicle_not_at_depot", "path_endpoints"} for v in validation["violations"])


def test_missing_return_rejected():
    g = _tiny_graph()
    requests = _requests()
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    schedule = result.schedule[~result.schedule["request_id"].astype(str).str.startswith("RETURN-")].copy()
    validation = validate_schedule(schedule, requests, _fleet(), 0, g, _model())
    assert not validation["valid"]
    assert any(v["type"] == "missing_depot_return" for v in validation["violations"])


def test_broken_path_rejected():
    g = _tiny_graph()
    requests = _requests()
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    schedule = result.schedule.copy()
    # Invent a non-existent edge 0->99 in the first pickup path.
    first = schedule.index[~schedule["request_id"].astype(str).str.startswith("RETURN-")][0]
    schedule.at[first, "path_nodes"] = "0 99"
    schedule.at[first, "to_node"] = 99
    validation = validate_schedule(schedule, requests, _fleet(), 0, g, _model())
    assert not validation["valid"]
    assert any(v["type"] in {"missing_edge", "path_endpoints"} for v in validation["violations"])


def test_altered_timestamps_rejected():
    g = _tiny_graph()
    requests = _requests()
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    schedule = result.schedule.copy()
    first = schedule.index[~schedule["request_id"].astype(str).str.startswith("RETURN-")][0]
    schedule.at[first, "planned_arrival_min"] = float(schedule.at[first, "planned_arrival_min"]) + 30.0
    validation = validate_schedule(schedule, requests, _fleet(), 0, g, _model())
    assert not validation["valid"]
    assert any(v["type"] == "arrival_timestamp_mismatch" for v in validation["violations"])


def test_service_before_release_rejected():
    g = _tiny_graph()
    requests = _requests()
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    # Make release later than recorded start while keeping schedule timestamps.
    requests = requests.copy()
    requests.loc[requests["request_id"] == "r0", "release_min"] = 999.0
    requests.loc[requests["request_id"] == "r0", "tw_start_min"] = 999.0
    requests.loc[requests["request_id"] == "r0", "tw_end_min"] = 1200.0
    validation = validate_schedule(result.schedule, requests, _fleet(), 0, g, _model())
    assert not validation["valid"]
    assert any(
        v["type"] in {"before_release", "start_timestamp_mismatch", "end_timestamp_mismatch", "window_violation"}
        for v in validation["violations"]
    )


def test_unknown_vehicle_id_rejected():
    g = _tiny_graph()
    requests = _requests()
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    schedule = result.schedule.copy()
    schedule["vehicle_id"] = "V99"
    validation = validate_schedule(schedule, requests, _fleet(), 0, g, _model())
    assert not validation["valid"]
    assert any(v["type"] == "unknown_vehicle" for v in validation["violations"])


def test_too_many_vehicles_rejected():
    g = _tiny_graph()
    requests = _requests()
    # Allowlist larger than n_vehicles so excess count (not unknown ID) is the failure mode.
    fleet = _fleet(n_vehicles=2, vehicle_ids=["V1", "V2", "V3"])
    result = build_graph_feasible_witness(requests, _fleet(n_vehicles=2), 0, g, _model())
    assert result.certified
    schedule = result.schedule.copy()
    schedule = pd.concat(
        [schedule, schedule.iloc[[0]].assign(vehicle_id="V3", request_id="RETURN-V3")],
        ignore_index=True,
    )
    validation = validate_schedule(schedule, requests, fleet, 0, g, _model())
    assert not validation["valid"]
    assert any(v["type"] == "too_many_vehicles" for v in validation["violations"])


def test_malformed_vehicle_id_rejected():
    g = _tiny_graph()
    requests = _requests()
    result = build_graph_feasible_witness(requests, _fleet(), 0, g, _model())
    schedule = result.schedule.copy()
    schedule.loc[schedule.index[0], "vehicle_id"] = ""
    validation = validate_schedule(schedule, requests, _fleet(), 0, g, _model())
    assert not validation["valid"]
    assert any(v["type"] == "malformed_vehicle_id" for v in validation["violations"])
