"""Time-dependent earliest-arrival routing with explicit waiting policy."""

from __future__ import annotations

import heapq
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
        if self.zone_day_hour is not None and commune is not None and day is not None:
            hit = self.zone_day_hour[
                (self.zone_day_hour["commune"] == commune)
                & (self.zone_day_hour["day"] == day)
                & (self.zone_day_hour["hour"] == hour)
            ]
            if not hit.empty:
                return max(float(hit.iloc[0]["tti_factor"]), 1e-6)
        return max(float(self.citywide_hour.get(hour, 1.0)), 1e-6)


def _best_parallel_edge(edge_dict: dict) -> dict:
    """Select the parallel edge with the smallest free-flow time."""

    if not edge_dict:
        raise ValueError("empty parallel-edge dict")
    # NetworkX MultiDiGraph weight callbacks receive {key: attr_dict}.
    return min(edge_dict.values(), key=lambda d: float(d.get("free_flow_time_s") or math.inf))


def edge_departure_and_travel(
    free_flow_s: float,
    ready_time_s: float,
    model: CongestionModel,
    commune: str | None = None,
    day: str | None = None,
    allow_wait: bool = True,
    max_wait_hours: int = 24,
) -> tuple[float, float]:
    """Choose departure and travel duration under piecewise-constant TTI factors.

    Waiting policy (explicit):
    - The vehicle may wait at the current node before entering the edge.
    - Candidate departures are the ready time and each subsequent hour boundary
      within ``max_wait_hours``.
    - Among candidates, choose the departure that minimizes arrival time
      (earliest arrival). Ties keep the earliest departure.

    Returns (departure_time_s, travel_duration_s). Arrival = departure + duration.
    """

    if free_flow_s < 0:
        raise ValueError("free_flow_s must be nonnegative")
    candidates = [ready_time_s]
    if allow_wait:
        base = math.floor(ready_time_s / 3600.0)
        for k in range(1, max_wait_hours + 1):
            boundary = (base + k) * 3600.0
            if boundary > ready_time_s:
                candidates.append(boundary)
    best_dep = ready_time_s
    best_dur = free_flow_s * model.factor(int(math.floor(ready_time_s / 3600.0)) % 24, commune, day)
    best_arr = best_dep + best_dur
    for dep in candidates:
        hour = int(math.floor(dep / 3600.0)) % 24
        dur = free_flow_s * model.factor(hour, commune, day)
        arr = dep + dur
        if arr < best_arr - 1e-9 or (abs(arr - best_arr) <= 1e-9 and dep < best_dep):
            best_arr = arr
            best_dep = dep
            best_dur = dur
    return best_dep, best_dur


def travel_time_seconds(
    free_flow_s: float,
    departure_time_s: float,
    model: CongestionModel,
    commune: str | None = None,
    day: str | None = None,
    wait_for_fifo: bool = True,
) -> float:
    """Backward-compatible wrapper: duration from ready time including optional wait."""

    _dep, dur = edge_departure_and_travel(
        free_flow_s,
        departure_time_s,
        model,
        commune=commune,
        day=day,
        allow_wait=wait_for_fifo,
    )
    wait = max(0.0, _dep - departure_time_s)
    return wait + dur


def earliest_arrival(
    graph: nx.MultiDiGraph,
    source,
    target,
    departure_time_s: float,
    model: CongestionModel,
    day: str | None = None,
    allow_wait: bool = True,
) -> tuple[float, list, list[dict]]:
    """Label-setting earliest-arrival Dijkstra on a directed MultiDiGraph.

    Edge costs are time-dependent under the waiting policy in
    ``edge_departure_and_travel``. Parallel edges are resolved by evaluating
    every parallel key and keeping the earliest arrival option.
    """

    if source not in graph or target not in graph:
        raise nx.NodeNotFound(f"source={source} or target={target} missing from graph")
    if source == target:
        return 0.0, [source], []

    best_arrival = {source: departure_time_s}
    pred: dict = {source: None}  # node -> (prev_node, edge_key, edge_data, dep, dur)
    heap = [(departure_time_s, source)]

    while heap:
        arr_u, u = heapq.heappop(heap)
        if arr_u > best_arrival.get(u, math.inf) + 1e-12:
            continue
        if u == target:
            break
        for _v, edge_dict in graph[u].items():
            for key, data in edge_dict.items():
                free = float(data.get("free_flow_time_s") or 0.0)
                commune = data.get("zone_commune")
                dep, dur = edge_departure_and_travel(
                    free, arr_u, model, commune=commune, day=day, allow_wait=allow_wait
                )
                arr_v = dep + dur
                if arr_v + 1e-12 < best_arrival.get(_v, math.inf):
                    best_arrival[_v] = arr_v
                    pred[_v] = (u, key, data, dep, dur)
                    heapq.heappush(heap, (arr_v, _v))

    if target not in best_arrival:
        raise nx.NetworkXNoPath(f"No path from {source} to {target}")

    # Reconstruct path.
    path = [target]
    legs: list[dict] = []
    cur = target
    while pred[cur] is not None:
        u, key, data, dep, dur = pred[cur]
        legs.append(
            {
                "u": u,
                "v": cur,
                "key": key,
                "departure_s": dep,
                "travel_s": dur,
                "arrival_s": dep + dur,
                "length_m": float(data.get("length") or 0.0),
                "free_flow_time_s": float(data.get("free_flow_time_s") or 0.0),
                "zone_commune": data.get("zone_commune"),
            }
        )
        path.append(u)
        cur = u
    path.reverse()
    legs.reverse()
    total = best_arrival[target] - departure_time_s
    return total, path, legs


def shortest_path_time(
    graph: nx.MultiDiGraph,
    source,
    target,
    departure_time_s: float,
    model: CongestionModel,
    day: str | None = None,
) -> tuple[float, list]:
    """Public API: earliest-arrival travel duration and node path."""

    total, path, _legs = earliest_arrival(
        graph, source, target, departure_time_s, model, day=day, allow_wait=True
    )
    return total, path


def path_length_m(graph: nx.MultiDiGraph, path: list) -> float:
    total = 0.0
    for u, v in zip(path[:-1], path[1:]):
        data = _best_parallel_edge(graph[u][v])
        total += float(data.get("length") or 0.0)
    return total


def exhaustive_earliest_arrival_dag(
    graph: nx.DiGraph | nx.MultiDiGraph,
    source,
    target,
    departure_time_s: float,
    model: CongestionModel,
    day: str | None = None,
    allow_wait: bool = True,
) -> float:
    """Independent reference for small acyclic digraphs via path enumeration."""

    if not nx.is_directed_acyclic_graph(nx.DiGraph(graph)):
        raise ValueError("exhaustive reference requires a DAG")
    best = math.inf
    for path in nx.all_simple_paths(graph, source, target):
        t = departure_time_s
        for u, v in zip(path[:-1], path[1:]):
            if graph.is_multigraph():
                options = []
                for _key, data in graph[u][v].items():
                    free = float(data.get("free_flow_time_s") or 0.0)
                    dep, dur = edge_departure_and_travel(
                        free, t, model, commune=data.get("zone_commune"), day=day, allow_wait=allow_wait
                    )
                    options.append(dep + dur)
                t = min(options)
            else:
                data = graph[u][v]
                free = float(data.get("free_flow_time_s") or 0.0)
                dep, dur = edge_departure_and_travel(
                    free, t, model, commune=data.get("zone_commune"), day=day, allow_wait=allow_wait
                )
                t = dep + dur
        best = min(best, t - departure_time_s)
    if not math.isfinite(best):
        raise nx.NetworkXNoPath(f"No path from {source} to {target}")
    return best
