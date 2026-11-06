"""Graph-based constructive feasibility witnesses and independent validation."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import pandas as pd

from race_casablanca.network.travel_time import CongestionModel, edge_departure_and_travel


@dataclass
class FeasibilityResult:
    certified: bool
    schedule: pd.DataFrame
    reason: str
    summary: dict


def _energy_kwh(length_m: float, consumption_kwh_per_km: float) -> float:
    return (length_m / 1000.0) * consumption_kwh_per_km


def _best_edge(graph: nx.MultiDiGraph, u, v) -> dict:
    return min(graph[u][v].values(), key=lambda d: float(d.get("free_flow_time_s") or float("inf")))


def free_flow_path(graph: nx.MultiDiGraph, source, target) -> list:
    """Static free-flow shortest path with correct MultiDiGraph parallel-edge weights."""

    def weight(u, v, edgedict):
        data = min(edgedict.values(), key=lambda d: float(d.get("free_flow_time_s") or float("inf")))
        return float(data.get("free_flow_time_s") or 0.0)

    return nx.shortest_path(graph, source, target, weight=weight)


def evaluate_path(
    graph: nx.MultiDiGraph,
    path: list,
    ready_time_s: float,
    model: CongestionModel,
    day: str | None,
) -> tuple[float, float, float]:
    """Evaluate a fixed node sequence under the time-dependent waiting model.

    Returns (arrival_time_s, travel_duration_s, length_m).
    """

    t = ready_time_s
    length_m = 0.0
    for u, v in zip(path[:-1], path[1:]):
        data = _best_edge(graph, u, v)
        dep, dur = edge_departure_and_travel(
            float(data.get("free_flow_time_s") or 0.0),
            t,
            model,
            commune=data.get("zone_commune"),
            day=day,
        )
        t = dep + dur
        length_m += float(data.get("length") or 0.0)
    return t, t - ready_time_s, length_m


def build_graph_feasible_witness(
    requests: pd.DataFrame,
    fleet: dict,
    depot_node,
    graph: nx.MultiDiGraph,
    model: CongestionModel,
    day: str | None = "Monday",
    window_requires_finish: bool = True,
) -> FeasibilityResult:
    """Constructive multi-vehicle schedule using directed road paths.

    Paths are chosen by free-flow Dijkstra (correct MultiDiGraph weights). Travel
    times along those paths are evaluated with the time-dependent waiting model.
    This certifies feasibility of the constructed schedule, not optimality of
    the routes. The independent validator recomputes times/energy along path_nodes.
    """

    empty = pd.DataFrame()
    if depot_node is None or depot_node not in graph:
        return FeasibilityResult(False, empty, "depot_node_missing_from_graph", {})

    vehicles = [f"V{i+1}" for i in range(int(fleet.get("n_vehicles", 1)))]
    usable = float(fleet["usable_battery_kwh"])
    reserve = usable * float(fleet["min_reserve_soc"])
    consumption = float(fleet["consumption_wh_per_km"]) / 1000.0
    payload_cap = float(fleet["payload_kg"])
    state = {
        v: {
            "node": depot_node,
            "time_s": 0.0,
            "load": 0.0,
            "battery": usable * float(fleet["initial_soc"]),
            "distance_m": 0.0,
        }
        for v in vehicles
    }
    rows: list[dict] = []
    ordered = requests.sort_values("release_min").reset_index(drop=True)

    for _, req in ordered.iterrows():
        if pd.isna(req["snap_node"]):
            return FeasibilityResult(False, pd.DataFrame(rows), "customer_node_missing", {"failed_request_id": req["request_id"]})
        cust = int(req["snap_node"])
        if cust not in graph:
            return FeasibilityResult(False, pd.DataFrame(rows), "customer_node_missing", {"failed_request_id": req["request_id"]})

        tw_start_s = float(req["tw_start_min"]) * 60.0
        tw_end_s = float(req["tw_end_min"]) * 60.0
        service_s = float(req["service_min"]) * 60.0
        weight = float(req["weight_kg"])
        best = None
        for v in vehicles:
            st = state[v]
            if st["load"] + weight > payload_cap + 1e-9:
                continue
            try:
                path = free_flow_path(graph, st["node"], cust)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            arrive_s, travel_s, length_m = evaluate_path(graph, path, st["time_s"], model, day)
            energy = _energy_kwh(length_m, consumption)
            start_s = max(arrive_s, tw_start_s)
            end_s = start_s + service_s
            within = (end_s <= tw_end_s + 1e-6) if window_requires_finish else (start_s <= tw_end_s + 1e-6)
            if not within:
                continue
            try:
                ret_path = free_flow_path(graph, cust, depot_node)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            _ra, _rt, ret_len = evaluate_path(graph, ret_path, end_s, model, day)
            ret_energy = _energy_kwh(ret_len, consumption)
            if st["battery"] - energy - ret_energy < reserve - 1e-9:
                continue
            cand = {
                "vehicle_id": v,
                "path": path,
                "length_m": length_m,
                "energy_kwh": energy,
                "arrive_s": arrive_s,
                "start_s": start_s,
                "end_s": end_s,
                "travel_s": travel_s,
                "from_node": st["node"],
            }
            if best is None or cand["end_s"] < best["end_s"]:
                best = cand
        if best is None:
            return FeasibilityResult(
                False,
                pd.DataFrame(rows),
                "no_vehicle_can_serve_request_under_constraints",
                {"failed_request_id": req["request_id"]},
            )

        v = best["vehicle_id"]
        st = state[v]
        ready_before = st["time_s"]
        st["battery"] -= best["energy_kwh"]
        st["load"] += weight
        st["node"] = cust
        st["time_s"] = best["end_s"]
        st["distance_m"] += best["length_m"]
        rows.append(
            {
                "request_id": req["request_id"],
                "vehicle_id": v,
                "depot_node": depot_node,
                "from_node": best["from_node"],
                "to_node": cust,
                "path_nodes": " ".join(map(str, best["path"])),
                "travel_distance_m": best["length_m"],
                "travel_time_s": best["travel_s"],
                "vehicle_ready_min": ready_before / 60.0,
                "planned_arrival_min": best["arrive_s"] / 60.0,
                "planned_start_min": best["start_s"] / 60.0,
                "planned_end_min": best["end_s"] / 60.0,
                "within_window": True,
                "battery_after_kwh": st["battery"],
                "load_after_kg": st["load"],
                "energy_used_kwh": best["energy_kwh"],
                "witness_only": True,
                "window_definition": "service_must_finish_by_tw_end",
                "routing_note": "free_flow_path_with_time_dependent_evaluation",
            }
        )

    returns: list[dict] = []
    for v, st in state.items():
        if st["node"] == depot_node:
            continue
        try:
            path = free_flow_path(graph, st["node"], depot_node)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return FeasibilityResult(False, pd.DataFrame(rows), "depot_return_unreachable", {"vehicle_id": v})
        arrive_s, travel_s, length_m = evaluate_path(graph, path, st["time_s"], model, day)
        energy = _energy_kwh(length_m, consumption)
        if st["battery"] - energy < reserve - 1e-9:
            return FeasibilityResult(False, pd.DataFrame(rows), "insufficient_battery_for_depot_return", {"vehicle_id": v})
        st["battery"] -= energy
        st["time_s"] = arrive_s
        st["distance_m"] += length_m
        st["node"] = depot_node
        returns.append(
            {
                "request_id": f"RETURN-{v}",
                "vehicle_id": v,
                "depot_node": depot_node,
                "from_node": path[0],
                "to_node": depot_node,
                "path_nodes": " ".join(map(str, path)),
                "travel_distance_m": length_m,
                "travel_time_s": travel_s,
                "vehicle_ready_min": (arrive_s - travel_s) / 60.0,
                "planned_arrival_min": arrive_s / 60.0,
                "planned_start_min": arrive_s / 60.0,
                "planned_end_min": arrive_s / 60.0,
                "within_window": True,
                "battery_after_kwh": st["battery"],
                "load_after_kg": st["load"],
                "energy_used_kwh": energy,
                "witness_only": True,
                "window_definition": "depot_return",
                "routing_note": "free_flow_path_with_time_dependent_evaluation",
            }
        )

    schedule = pd.DataFrame(rows + returns)
    summary = {
        "n_requests": int(len(requests)),
        "n_served": int(len(rows)),
        "n_returns": int(len(returns)),
        "share_within_window": 1.0 if rows else 0.0,
        "min_battery_after_kwh": float(schedule["battery_after_kwh"].min()) if not schedule.empty else None,
        "total_travel_distance_m": float(sum(state[v]["distance_m"] for v in vehicles)),
        "vehicles_used": sorted({r["vehicle_id"] for r in rows}),
        "certificate": "graph_constructive_freeflow_path_td_eval_with_depot_return",
        "window_definition": "service_must_finish_by_tw_end",
    }
    return FeasibilityResult(True, schedule, "certified", summary)


def validate_schedule(
    schedule: pd.DataFrame,
    requests: pd.DataFrame,
    fleet: dict,
    depot_node,
    graph: nx.MultiDiGraph,
    model: CongestionModel,
    day: str | None = "Monday",
    window_requires_finish: bool = True,
) -> dict:
    """Independently reconstruct travel/energy/windows from path_nodes."""

    req_map = requests.set_index("request_id")
    usable = float(fleet["usable_battery_kwh"])
    reserve = usable * float(fleet["min_reserve_soc"])
    consumption = float(fleet["consumption_wh_per_km"]) / 1000.0
    payload_cap = float(fleet["payload_kg"])
    vehicle_state: dict = {}
    violations: list[dict] = []

    for _, row in schedule.sort_values(["vehicle_id", "planned_arrival_min"]).iterrows():
        v = row["vehicle_id"]
        if v not in vehicle_state:
            vehicle_state[v] = {
                "node": depot_node,
                "time_s": 0.0,
                "load": 0.0,
                "battery": usable * float(fleet["initial_soc"]),
            }
        st = vehicle_state[v]
        path = [int(x) for x in str(row["path_nodes"]).split()]
        if not path or path[0] != st["node"] or path[-1] != int(row["to_node"]):
            violations.append({"type": "path_endpoints", "request_id": row["request_id"]})
            continue
        t = st["time_s"]
        dist = 0.0
        broken = False
        for u, w in zip(path[:-1], path[1:]):
            if w not in graph[u]:
                violations.append({"type": "missing_edge", "u": u, "v": w, "request_id": row["request_id"]})
                broken = True
                break
            data = _best_edge(graph, u, w)
            dep, dur = edge_departure_and_travel(
                float(data.get("free_flow_time_s") or 0.0),
                t,
                model,
                commune=data.get("zone_commune"),
                day=day,
            )
            t = dep + dur
            dist += float(data.get("length") or 0.0)
        if broken:
            continue
        energy = _energy_kwh(dist, consumption)
        st["battery"] -= energy
        if abs(dist - float(row["travel_distance_m"])) > 1.0:
            violations.append(
                {
                    "type": "distance_mismatch",
                    "request_id": row["request_id"],
                    "recomputed_m": dist,
                    "recorded_m": float(row["travel_distance_m"]),
                }
            )
        if str(row["request_id"]).startswith("RETURN-"):
            st["node"] = depot_node
            st["time_s"] = t
            if st["battery"] < reserve - 1e-6:
                violations.append({"type": "reserve_violation", "request_id": row["request_id"]})
            continue
        rid = row["request_id"]
        if rid not in req_map.index:
            violations.append({"type": "unknown_request", "request_id": rid})
            continue
        req = req_map.loc[rid]
        start_s = max(t, float(req["tw_start_min"]) * 60.0)
        end_s = start_s + float(req["service_min"]) * 60.0
        tw_end = float(req["tw_end_min"]) * 60.0
        ok = end_s <= tw_end + 1e-6 if window_requires_finish else start_s <= tw_end + 1e-6
        if not ok:
            violations.append({"type": "window_violation", "request_id": rid})
        st["load"] += float(req["weight_kg"])
        if st["load"] > payload_cap + 1e-6:
            violations.append({"type": "payload_violation", "request_id": rid})
        st["node"] = int(row["to_node"])
        st["time_s"] = end_s
        if st["battery"] < reserve - 1e-6:
            violations.append({"type": "reserve_violation", "request_id": rid})

    return {
        "valid": len(violations) == 0,
        "n_violations": len(violations),
        "violations": violations[:20],
        "vehicles": {
            v: {"final_node": s["node"], "battery_kwh": s["battery"], "load_kg": s["load"]}
            for v, s in vehicle_state.items()
        },
    }
