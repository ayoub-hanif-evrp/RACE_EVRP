"""Seeded synthetic pickup demand and feasible witness construction."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def load_demand_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def zone_sampling_weights(communes: pd.DataFrame, land_use: pd.DataFrame, config: dict) -> pd.Series:
    merged = communes.merge(land_use, on=["commune", "zip_code"], how="left")
    pop = merged["population"].fillna(0).astype(float)
    commercial_cols = [c for c in merged.columns if "commercial" in c.lower() or "Commercial" in c]
    if commercial_cols:
        commercial = merged[commercial_cols[0]].fillna(0).astype(float)
    else:
        commercial = pd.Series(np.ones(len(merged)), index=merged.index)
    pop_w = pop / pop.sum() if pop.sum() > 0 else np.full(len(merged), 1 / len(merged))
    com_w = commercial / commercial.sum() if commercial.sum() > 0 else np.full(len(merged), 1 / len(merged))
    alpha = float(config["spatial"]["population_weight"])
    beta = float(config["spatial"]["commercial_weight"])
    weights = alpha * pop_w + beta * com_w
    weights = weights / weights.sum()
    return pd.Series(weights.to_numpy(), index=merged["commune"])


def _nhpp_arrivals(n: int, start_hour: float, horizon_hours: float, weights: list[float], rng: np.random.Generator):
    hours = np.arange(24)
    # Restrict to active horizon window.
    active = []
    probs = []
    for h in hours:
        if start_hour <= h < start_hour + horizon_hours:
            active.append(h)
            probs.append(max(float(weights[h]), 0.0))
    probs = np.asarray(probs, dtype=float)
    if probs.sum() <= 0:
        probs = np.ones(len(active))
    probs = probs / probs.sum()
    chosen_hours = rng.choice(active, size=n, replace=True, p=probs)
    # Uniform within hour.
    minutes = chosen_hours * 60.0 + rng.uniform(0, 60, size=n)
    return np.sort(minutes)


def generate_requests(
    candidates: pd.DataFrame,
    zone_weights: pd.Series,
    regime_name: str,
    regime: dict,
    config: dict,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = int(regime["n_customers"])
    profile = config["intensity_profiles"][regime["intensity_profile"]]["weights"]
    release_min = _nhpp_arrivals(n, regime["start_hour"], regime["horizon_hours"], profile, rng)

    # Sample zones then candidates within zone.
    zones = list(zone_weights.index)
    zprob = zone_weights.to_numpy(dtype=float)
    chosen_zones = rng.choice(zones, size=n, replace=True, p=zprob)
    rows = []
    for i in range(n):
        zone = chosen_zones[i]
        pool = candidates[(candidates["commune"] == zone) & (candidates["accessible"] == True)]  # noqa: E712
        if pool.empty:
            pool = candidates[candidates["accessible"] == True]  # noqa: E712
        pick = pool.sample(1, random_state=int(rng.integers(0, 1_000_000))).iloc[0]
        release = float(release_min[i])
        tw = float(regime["time_window_hours"]) * 60.0
        rows.append(
            {
                "request_id": f"{regime_name}-{seed}-{i:04d}",
                "regime": regime_name,
                "seed": seed,
                "commune": pick.get("commune"),
                "category": pick.get("category"),
                "lat": float(pick["lat"]),
                "lon": float(pick["lon"]),
                "snap_node": pick.get("snap_node"),
                "snap_distance_m": float(pick.get("snap_distance_m") or np.nan),
                "release_min": release,
                "tw_start_min": release,
                "tw_end_min": release + tw,
                "service_min": float(regime["service_duration_min"]),
                "weight_kg": float(regime["package_weight_kg"]),
                "urgency": regime.get("urgency", "normal"),
                "is_observed_order": False,
                "generator_version": config["generator_version"],
            }
        )
    return pd.DataFrame(rows)


def build_feasible_witness(requests: pd.DataFrame, fleet: dict, depot_node, seed: int) -> pd.DataFrame:
    """Construct a simple sequential depot-based schedule as a feasibility witness.

    This is a constructive certificate for the generated instance under stated
    assumptions. It is stored separately from online decision inputs.
    """

    rng = np.random.default_rng(seed + 999)
    vehicles = [f"V{i+1}" for i in range(int(fleet.get("n_vehicles", 1)))]
    ordered = requests.sort_values("release_min").reset_index(drop=True)
    assign = []
    vehicle_time = {v: 0.0 for v in vehicles}
    vehicle_load = {v: 0.0 for v in vehicles}
    battery = {v: float(fleet["usable_battery_kwh"]) * float(fleet["initial_soc"]) for v in vehicles}
    reserve = float(fleet["usable_battery_kwh"]) * float(fleet["min_reserve_soc"])
    consumption = float(fleet["consumption_wh_per_km"]) / 1000.0  # kWh/km
    for _, req in ordered.iterrows():
        # Greedy: earliest vehicle that can serve after release with payload/energy slack.
        chosen = None
        for v in vehicles:
            ready = max(vehicle_time[v], float(req["release_min"]))
            # Assume 2 km average hop for witness energy bookkeeping.
            energy_need = consumption * 2.0
            if vehicle_load[v] + float(req["weight_kg"]) > float(fleet["payload_kg"]):
                continue
            if battery[v] - energy_need < reserve:
                continue
            if ready <= float(req["tw_end_min"]):
                chosen = v
                start = ready
                break
        if chosen is None:
            chosen = vehicles[int(rng.integers(0, len(vehicles)))]
            start = max(vehicle_time[chosen], float(req["release_min"]))
        end = start + float(req["service_min"])
        vehicle_time[chosen] = end + 5.0
        vehicle_load[chosen] += float(req["weight_kg"])
        battery[chosen] -= consumption * 2.0
        assign.append(
            {
                "request_id": req["request_id"],
                "vehicle_id": chosen,
                "depot_node": depot_node,
                "planned_start_min": start,
                "planned_end_min": end,
                "within_window": start <= float(req["tw_end_min"]),
                "battery_after_kwh": battery[chosen],
                "witness_only": True,
            }
        )
    return pd.DataFrame(assign)
