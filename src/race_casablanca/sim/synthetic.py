"""Tiny synthetic network with independently calculable routing/energy outcomes."""

from __future__ import annotations

import networkx as nx
import pandas as pd

from race_casablanca.network.travel_time import CongestionModel
from race_casablanca.sim.types import Request, RequestStatus


def make_line_graph() -> nx.MultiDiGraph:
    """Depot 0 — 1 — 2 — 3 (customer). Each edge 1000 m, free-flow at 60 km/h = 60 s."""

    g = nx.MultiDiGraph()
    for i in range(4):
        g.add_node(i, x=float(i), y=0.0)
    for u, v in [(0, 1), (1, 2), (2, 3), (3, 2), (2, 1), (1, 0)]:
        g.add_edge(u, v, 0, length=1000.0, free_flow_time_s=60.0, zone_commune="Z")
    return g


def make_unit_congestion() -> CongestionModel:
    return CongestionModel(citywide_hour=pd.Series({h: 1.0 for h in range(24)}))


def make_two_request_scenario() -> dict:
    """One vehicle, two sequential pickups on the line graph.

    Exact under TTI=1 and 0.2 kWh/km:
    - 0→3: 3000 m, 180 s, 0.6 kWh
    - service at 3
    - 3→0 return: 3000 m, 180 s, 0.6 kWh
    """

    requests = [
        Request(
            request_id="R1",
            snap_node=3,
            release_s=0.0,
            tw_start_s=0.0,
            tw_end_s=3600.0,
            service_s=60.0,
            weight_kg=10.0,
            status=RequestStatus.UNRELEASED,
        ),
        Request(
            request_id="R2",
            snap_node=2,
            release_s=50.0,
            tw_start_s=50.0,
            tw_end_s=3600.0,
            service_s=60.0,
            weight_kg=10.0,
            status=RequestStatus.UNRELEASED,
        ),
    ]
    fleet = {
        "usable_battery_kwh": 40.0,
        "payload_kg": 600.0,
        "initial_soc": 1.0,
        "min_reserve_soc": 0.15,
        "consumption_wh_per_km": 200.0,
        "charge_power_kw": 22.0,
        "n_vehicles": 1,
    }
    return {
        "graph": make_line_graph(),
        "model": make_unit_congestion(),
        "requests": requests,
        "fleet": fleet,
        "depot_node": 0,
        "shift_start_s": 0.0,
        "shift_end_s": 8 * 3600.0,
        "day": "Monday",
        "scenario_id": "synthetic/line_two_requests",
    }
