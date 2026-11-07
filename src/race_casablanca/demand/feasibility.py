"""Graph-based constructive feasibility witnesses and independent validation."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import pandas as pd

from race_casablanca.network.travel_time import CongestionModel, edge_departure_and_travel

# Timestamp agreement tolerance between recorded schedule and reconstruction.
TIMESTAMP_TOL_MIN = 1e-3
DISTANCE_TOL_M = 1.0
ENERGY_TOL_KWH = 1e-6


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
        release_s = float(req["release_min"]) * 60.0
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
            start_s = max(arrive_s, tw_start_s, release_s)
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
    timestamp_tol_min: float = TIMESTAMP_TOL_MIN,
) -> dict:
    """Independently reconstruct and certify a schedule against scenario inputs.

    A schedule is never valid merely because no rows were processed: every request
    must appear exactly once, used vehicles must return to the actual depot, and
    recorded timestamps must agree with reconstruction.
    """

    violations: list[dict] = []
    if schedule is None or (isinstance(schedule, pd.DataFrame) and schedule.empty):
        if len(requests) > 0:
            violations.append({"type": "empty_schedule", "n_requests": int(len(requests))})
            return {
                "valid": False,
                "n_violations": len(violations),
                "violations": violations,
                "vehicles": {},
                "coverage": {"required": int(len(requests)), "served": 0},
            }

    req_ids = [str(x) for x in requests["request_id"].tolist()]
    required = set(req_ids)
    pickup_rows = schedule[~schedule["request_id"].astype(str).str.startswith("RETURN-")].copy()
    return_rows = schedule[schedule["request_id"].astype(str).str.startswith("RETURN-")].copy()
    served = pickup_rows["request_id"].astype(str).tolist()
    served_set = set(served)

    for rid in required - served_set:
        violations.append({"type": "missing_pickup", "request_id": rid})
    for rid in served_set - required:
        violations.append({"type": "unknown_request", "request_id": rid})
    dupes = pickup_rows["request_id"].astype(str).value_counts()
    for rid, count in dupes.items():
        if count > 1:
            violations.append({"type": "duplicate_pickup", "request_id": rid, "count": int(count)})

    usable = float(fleet["usable_battery_kwh"])
    reserve = usable * float(fleet["min_reserve_soc"])
    consumption = float(fleet["consumption_wh_per_km"]) / 1000.0
    payload_cap = float(fleet["payload_kg"])
    req_map = requests.set_index("request_id")
    vehicle_state: dict = {}
    vehicles_used: set[str] = set()

    ordered = schedule.sort_values(["vehicle_id", "planned_arrival_min", "planned_start_min"]).reset_index(drop=True)
    for _, row in ordered.iterrows():
        v = str(row["vehicle_id"])
        if v not in vehicle_state:
            vehicle_state[v] = {
                "node": depot_node,
                "time_s": 0.0,
                "load": 0.0,
                "battery": usable * float(fleet["initial_soc"]),
                "returned": False,
                "served": 0,
            }
        st = vehicle_state[v]
        rid = str(row["request_id"])
        is_return = rid.startswith("RETURN-")

        try:
            path = [int(x) for x in str(row["path_nodes"]).split()]
        except (TypeError, ValueError):
            violations.append({"type": "invalid_path_nodes", "request_id": rid})
            continue
        if not path:
            violations.append({"type": "empty_path", "request_id": rid})
            continue
        try:
            to_node = int(row["to_node"])
        except (TypeError, ValueError):
            violations.append({"type": "invalid_to_node", "request_id": rid})
            continue
        if path[0] != st["node"] or path[-1] != to_node:
            violations.append(
                {
                    "type": "path_endpoints",
                    "request_id": rid,
                    "expected_from": st["node"],
                    "path_from": path[0],
                    "expected_to": to_node,
                    "path_to": path[-1],
                }
            )
            continue

        ready_s = st["time_s"]
        t = ready_s
        dist = 0.0
        broken = False
        for u, w in zip(path[:-1], path[1:]):
            if w not in graph[u]:
                violations.append({"type": "missing_edge", "u": u, "v": w, "request_id": rid})
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
            if dep + 1e-9 < t:
                violations.append({"type": "time_non_monotonic", "request_id": rid})
            t = dep + dur
            dist += float(data.get("length") or 0.0)
        if broken:
            continue

        energy = _energy_kwh(dist, consumption)
        recorded_dist = float(row.get("travel_distance_m") or 0.0)
        if abs(dist - recorded_dist) > DISTANCE_TOL_M:
            violations.append(
                {
                    "type": "distance_mismatch",
                    "request_id": rid,
                    "recomputed_m": dist,
                    "recorded_m": recorded_dist,
                }
            )
        recorded_energy = float(row.get("energy_used_kwh") or 0.0)
        if abs(energy - recorded_energy) > max(ENERGY_TOL_KWH, 1e-3 * max(energy, 1.0)):
            violations.append(
                {
                    "type": "energy_mismatch",
                    "request_id": rid,
                    "recomputed_kwh": energy,
                    "recorded_kwh": recorded_energy,
                }
            )

        st["battery"] -= energy
        arrive_s = t
        recorded_arrival = float(row["planned_arrival_min"]) * 60.0
        if abs(arrive_s - recorded_arrival) > timestamp_tol_min * 60.0:
            violations.append(
                {
                    "type": "arrival_timestamp_mismatch",
                    "request_id": rid,
                    "recomputed_s": arrive_s,
                    "recorded_s": recorded_arrival,
                }
            )

        if is_return:
            if int(row["to_node"]) != int(depot_node):
                violations.append(
                    {
                        "type": "return_not_to_depot",
                        "request_id": rid,
                        "to_node": int(row["to_node"]),
                        "depot_node": int(depot_node),
                    }
                )
            st["node"] = int(row["to_node"]) if int(row["to_node"]) == int(depot_node) else st["node"]
            # Prefer reconstructing state at depot only if destination is depot.
            if int(row["to_node"]) == int(depot_node):
                st["node"] = depot_node
                st["returned"] = True
            st["time_s"] = arrive_s
            recorded_end = float(row["planned_end_min"]) * 60.0
            if abs(arrive_s - recorded_end) > timestamp_tol_min * 60.0:
                violations.append(
                    {
                        "type": "return_timestamp_mismatch",
                        "request_id": rid,
                        "recomputed_s": arrive_s,
                        "recorded_s": recorded_end,
                    }
                )
            if st["battery"] < reserve - ENERGY_TOL_KWH:
                violations.append({"type": "reserve_violation", "request_id": rid, "battery_kwh": st["battery"]})
            continue

        # Pickup service.
        vehicles_used.add(v)
        st["served"] += 1
        if rid not in req_map.index:
            # Already flagged as unknown above; skip reconstruction details.
            continue
        req = req_map.loc[rid]
        release_s = float(req["release_min"]) * 60.0
        tw_start_s = float(req["tw_start_min"]) * 60.0
        tw_end_s = float(req["tw_end_min"]) * 60.0
        service_s = float(req["service_min"]) * 60.0
        start_s = max(arrive_s, tw_start_s, release_s)
        end_s = start_s + service_s

        if start_s + 1e-9 < release_s:
            violations.append({"type": "before_release", "request_id": rid, "start_s": start_s, "release_s": release_s})

        recorded_start = float(row["planned_start_min"]) * 60.0
        recorded_end = float(row["planned_end_min"]) * 60.0
        if abs(start_s - recorded_start) > timestamp_tol_min * 60.0:
            violations.append(
                {
                    "type": "start_timestamp_mismatch",
                    "request_id": rid,
                    "recomputed_s": start_s,
                    "recorded_s": recorded_start,
                }
            )
        if abs(end_s - recorded_end) > timestamp_tol_min * 60.0:
            violations.append(
                {
                    "type": "end_timestamp_mismatch",
                    "request_id": rid,
                    "recomputed_s": end_s,
                    "recorded_s": recorded_end,
                }
            )

        ok_window = (end_s <= tw_end_s + 1e-6) if window_requires_finish else (start_s <= tw_end_s + 1e-6)
        if not ok_window:
            violations.append({"type": "window_violation", "request_id": rid})

        st["load"] += float(req["weight_kg"])
        if st["load"] > payload_cap + 1e-6:
            violations.append({"type": "payload_violation", "request_id": rid, "load_kg": st["load"]})
        st["node"] = to_node
        st["time_s"] = end_s
        if st["battery"] < reserve - ENERGY_TOL_KWH:
            violations.append({"type": "reserve_violation", "request_id": rid, "battery_kwh": st["battery"]})

    # Depot returns for every used vehicle.
    returns_by_vehicle = return_rows.groupby(return_rows["vehicle_id"].astype(str)).size().to_dict()
    for v in vehicles_used:
        n_ret = int(returns_by_vehicle.get(v, 0))
        if n_ret == 0:
            violations.append({"type": "missing_depot_return", "vehicle_id": v})
        elif n_ret > 1:
            violations.append({"type": "duplicate_depot_return", "vehicle_id": v, "count": n_ret})
        else:
            st = vehicle_state.get(v)
            if st is not None and (not st.get("returned") or st.get("node") != depot_node):
                violations.append(
                    {
                        "type": "vehicle_not_at_depot",
                        "vehicle_id": v,
                        "final_node": st.get("node"),
                        "depot_node": depot_node,
                    }
                )

    # Vehicles that only appear in fabricated returns still checked above via return destination.

    return {
        "valid": len(violations) == 0,
        "n_violations": len(violations),
        "violations": violations[:50],
        "coverage": {
            "required": int(len(required)),
            "served": int(len(served_set & required)),
            "duplicates": int(sum(1 for c in dupes if c > 1)),
        },
        "vehicles": {
            v: {
                "final_node": s["node"],
                "battery_kwh": s["battery"],
                "load_kg": s["load"],
                "returned": bool(s.get("returned")),
                "n_served": int(s.get("served", 0)),
            }
            for v, s in vehicle_state.items()
        },
        "timestamp_tol_min": timestamp_tol_min,
    }
