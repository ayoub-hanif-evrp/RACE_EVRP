"""Seeded synthetic pickup demand generation."""

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


def fixed_count_hourly_arrivals(
    n: int,
    start_hour: float,
    horizon_hours: float,
    weights: list[float],
    rng: np.random.Generator,
):
    """Sample exactly n arrival times with hourly intensity weights.

    This is fixed-count temporal sampling, not an unconditional nonhomogeneous
    Poisson process (NHPP). Naming is intentional after the Stage-1 audit.
    """

    hours = np.arange(24)
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
    minutes = chosen_hours * 60.0 + rng.uniform(0, 60, size=n)
    return np.sort(minutes)


# Backward-compatible alias used by older tests/docs.
_nhpp_arrivals = fixed_count_hourly_arrivals


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
    release_min = fixed_count_hourly_arrivals(n, regime["start_hour"], regime["horizon_hours"], profile, rng)

    zones = list(zone_weights.index)
    zprob = zone_weights.to_numpy(dtype=float)
    chosen_zones = rng.choice(zones, size=n, replace=True, p=zprob)
    # Optional within-regime heterogeneity multipliers.
    weight_jitter = float(regime.get("weight_jitter", 0.0))
    service_jitter = float(regime.get("service_jitter_min", 0.0))
    window_jitter = float(regime.get("window_jitter_hours", 0.0))
    rows = []
    for i in range(n):
        zone = chosen_zones[i]
        pool = candidates[(candidates["commune"] == zone) & (candidates["accessible"] == True)]  # noqa: E712
        if pool.empty:
            pool = candidates[candidates["accessible"] == True]  # noqa: E712
        pick = pool.sample(1, random_state=int(rng.integers(0, 1_000_000))).iloc[0]
        release = float(release_min[i])
        tw_hours = float(regime["time_window_hours"])
        if window_jitter > 0:
            tw_hours = max(0.25, tw_hours + float(rng.uniform(-window_jitter, window_jitter)))
        service = float(regime["service_duration_min"])
        if service_jitter > 0:
            service = max(1.0, service + float(rng.uniform(-service_jitter, service_jitter)))
        pkg = float(regime["package_weight_kg"])
        if weight_jitter > 0:
            pkg = max(0.5, pkg * float(rng.uniform(1.0 - weight_jitter, 1.0 + weight_jitter)))
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
                "tw_end_min": release + tw_hours * 60.0,
                "service_min": service,
                "weight_kg": pkg,
                "urgency": regime.get("urgency", "normal"),
                "is_observed_order": False,
                "arrival_process": "fixed_count_hourly_intensity_sampling",
                "generator_version": config["generator_version"],
            }
        )
    return pd.DataFrame(rows)
