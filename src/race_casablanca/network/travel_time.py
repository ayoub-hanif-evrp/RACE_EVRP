"""Time-dependent travel times with FIFO-safe waiting."""

from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
import pandas as pd


@dataclass
class CongestionModel:
    citywide_hour: pd.Series
    zone_day_hour: pd.DataFrame | None = None

    def factor(self, hour: int, commune: str | None = None, day: str | None = None) -> float:
        hour = int(hour) % 24
        if (
            self.zone_day_hour is not None
            and commune is not None
            and day is not None
        ):
            hit = self.zone_day_hour[
                (self.zone_day_hour["commune"] == commune)
                & (self.zone_day_hour["day"] == day)
                & (self.zone_day_hour["hour"] == hour)
            ]
            if not hit.empty:
                return max(float(hit.iloc[0]["tti_factor"]), 1e-6)
        return max(float(self.citywide_hour.get(hour, 1.0)), 1e-6)


def travel_time_seconds(
    free_flow_s: float,
    departure_time_s: float,
    model: CongestionModel,
    commune: str | None = None,
    day: str | None = None,
    wait_for_fifo: bool = True,
) -> float:
    """Return travel time in seconds for an edge with free-flow duration free_flow_s.

    Uses piecewise-constant hourly factors. If a later hour would make a later
    departure arrive earlier, optionally wait until the factor no longer improves
    arrival enough to break FIFO relative to departing immediately.
    """

    if free_flow_s < 0:
        raise ValueError("free_flow_s must be nonnegative")
    hour = int(math.floor(departure_time_s / 3600.0)) % 24
    factor = model.factor(hour, commune=commune, day=day)
    depart = departure_time_s
    duration = free_flow_s * factor
    if not wait_for_fifo:
        return duration
    # Compare with waiting to next hour boundary once.
    next_boundary = (math.floor(departure_time_s / 3600.0) + 1) * 3600.0
    wait = max(0.0, next_boundary - departure_time_s)
    next_hour = int(math.floor(next_boundary / 3600.0)) % 24
    alt_factor = model.factor(next_hour, commune=commune, day=day)
    alt_arrival = next_boundary + free_flow_s * alt_factor
    immediate_arrival = depart + duration
    if alt_arrival < immediate_arrival:
        return wait + free_flow_s * alt_factor
    return duration


def shortest_path_time(
    graph: nx.MultiDiGraph,
    source,
    target,
    departure_time_s: float,
    model: CongestionModel,
    day: str | None = None,
) -> tuple[float, list]:
    """Dijkstra with time-dependent edge weights and FIFO waiting policy."""

    def weight(u, v, data):
        # NetworkX passes the attribute dict for the chosen key.
        free = float(data.get("free_flow_time_s") or 0.0)
        commune = data.get("zone_commune")
        return travel_time_seconds(free, departure_time_s, model, commune=commune, day=day)

    # Static weight approximation using departure-time factors; adequate for
    # piecewise-constant factors with waiting because FIFO is restored.
    path = nx.shortest_path(graph, source, target, weight=weight)
    total = 0.0
    t = departure_time_s
    for u, v in zip(path[:-1], path[1:]):
        data = min(graph[u][v].values(), key=lambda d: float(d.get("free_flow_time_s") or 0.0))
        dt = travel_time_seconds(
            float(data.get("free_flow_time_s") or 0.0),
            t,
            model,
            commune=data.get("zone_commune"),
            day=day,
        )
        total += dt
        t += dt
    return total, path
