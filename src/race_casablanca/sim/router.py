"""Cached free-flow path routing with time-dependent evaluation.

Paths match Stage-1 constructive witnesses (free-flow Dijkstra). Travel times
are evaluated with the documented waiting / TTI model — never haversine.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from race_casablanca.demand.feasibility import evaluate_path, free_flow_path
from race_casablanca.network.travel_time import CongestionModel, path_length_m


@dataclass
class RouteResult:
    path: list
    duration_s: float
    arrival_s: float
    length_m: float
    wait_s: float


class RouteCache:
    def __init__(
        self,
        graph: nx.MultiDiGraph,
        model: CongestionModel,
        day: str | None = "Monday",
    ):
        self.graph = graph
        self.model = model
        self.day = day
        self._path_cache: dict[tuple, list] = {}
        self.n_queries = 0
        self.n_cache_hits = 0

    def warmup(self, nodes: list) -> None:
        """Precompute free-flow paths among landmarks via one Dijkstra per source."""

        uniq = []
        seen: set = set()
        for n in nodes:
            if n in seen or n not in self.graph:
                continue
            seen.add(n)
            uniq.append(n)

        def weight(u, v, edgedict):
            from race_casablanca.network.travel_time import edge_tti_baseline_free_flow_s

            data = min(edgedict.values(), key=lambda d: edge_tti_baseline_free_flow_s(d))
            return edge_tti_baseline_free_flow_s(data)

        for s in uniq:
            self._path_cache[(s, s)] = [s]
            # Skip sources whose landmark targets are already cached.
            if all((s, t) in self._path_cache for t in uniq):
                continue
            paths = nx.single_source_dijkstra_path(self.graph, s, weight=weight)
            for t in uniq:
                if s == t:
                    continue
                if t in paths:
                    self._path_cache[(s, t)] = paths[t]

    def path(self, source, target) -> list:
        key = (source, target)
        if key in self._path_cache:
            self.n_cache_hits += 1
            return self._path_cache[key]
        if source == target:
            p = [source]
        else:
            p = free_flow_path(self.graph, source, target)
        self._path_cache[key] = p
        return p

    def route(self, source, target, ready_s: float) -> RouteResult:
        self.n_queries += 1
        if source == target:
            return RouteResult([source], 0.0, ready_s, 0.0, 0.0)
        path = self.path(source, target)
        arrival, duration, length_m = evaluate_path(
            self.graph, path, ready_s, self.model, self.day
        )
        # Wait component: duration beyond free-flow-ish lower bound is not
        # split explicitly; approximate wait as max(0, arrival - ready - pure_drive)
        # where pure_drive uses length at 60 km/h for diagnostics only.
        pure = (length_m * 3.6 / 60.0) if length_m > 0 else 0.0
        wait = max(0.0, duration - pure)
        return RouteResult(path, duration, arrival, length_m, wait)

    def length_m(self, source, target) -> float:
        if source == target:
            return 0.0
        return float(path_length_m(self.graph, self.path(source, target)))
