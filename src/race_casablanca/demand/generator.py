"""Seeded synthetic pickup demand generation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml


def load_demand_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_demand_zone_weights(path: Path) -> pd.DataFrame:
    """Load the immutable demand weight table (sole spatial-probability authority)."""

    frame = pd.read_csv(path)
    required = {
        "zone_id",
        "zone_weight",
        "eligible_for_sampling",
        "population_source",
        "n_accessible_candidates",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"demand_zone_weights.csv missing columns: {sorted(missing)}")
    if not frame["zone_id"].is_unique:
        raise ValueError("demand_zone_weights.csv zone_id values are not unique")
    eligible = frame[frame["eligible_for_sampling"] == True].copy()  # noqa: E712
    if eligible.empty:
        raise ValueError("no eligible zones in demand_zone_weights.csv")
    if (eligible["zone_weight"] < -1e-15).any():
        raise ValueError("negative zone weights")
    wsum = float(eligible["zone_weight"].sum())
    if wsum <= 0:
        raise ValueError("eligible zone weights sum to zero")
    # Renormalize over eligible zones only (frozen file may include zero-weight rows).
    eligible = eligible.copy()
    eligible["zone_weight"] = eligible["zone_weight"] / wsum
    if abs(float(eligible["zone_weight"].sum()) - 1.0) > 1e-8:
        raise ValueError("eligible zone weights do not sum to 1 after renormalization")
    return eligible


def zone_sampling_weights_from_table(weights: pd.DataFrame) -> pd.Series:
    return pd.Series(
        weights["zone_weight"].to_numpy(dtype=float),
        index=weights["zone_id"].astype(str),
    )


def zone_sampling_weights(communes: pd.DataFrame, land_use: pd.DataFrame, config: dict) -> pd.Series:
    """Deprecated live recompute — retained for tests of the formula only.

    Scenario generation must use ``load_demand_zone_weights`` instead.
    """

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

    # Restrict to zones that currently have accessible candidates; renormalize.
    eligible_zones = []
    eligible_probs = []
    for zone, prob in zone_weights.items():
        pool = candidates[(candidates["commune"] == zone) & (candidates["accessible"] == True)]  # noqa: E712
        if not pool.empty and float(prob) > 0:
            eligible_zones.append(zone)
            eligible_probs.append(float(prob))
    if not eligible_zones:
        raise RuntimeError(
            "No demand zones have accessible candidates; refuse silent citywide fallback"
        )
    eligible_probs = np.asarray(eligible_probs, dtype=float)
    eligible_probs = eligible_probs / eligible_probs.sum()

    chosen_zones = rng.choice(eligible_zones, size=n, replace=True, p=eligible_probs)
    weight_jitter = float(regime.get("weight_jitter", 0.0))
    service_jitter = float(regime.get("service_jitter_min", 0.0))
    window_jitter = float(regime.get("window_jitter_hours", 0.0))
    rows = []
    for i in range(n):
        zone = chosen_zones[i]
        pool = candidates[(candidates["commune"] == zone) & (candidates["accessible"] == True)]  # noqa: E712
        if pool.empty:
            raise RuntimeError(
                f"Selected zone '{zone}' has no accessible candidates after eligibility filter"
            )
        pick = pool.sample(1, random_state=int(rng.integers(0, 1_000_000))).iloc[0]
        # Geographic integrity: declared commune must match candidate commune.
        if str(pick.get("commune")) != str(zone):
            raise RuntimeError(f"candidate commune mismatch for zone {zone}")
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
                "commune": str(zone),
                "declared_zone_id": str(zone),
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
                "spatial_weight_source": "demand_zone_weights.csv",
            }
        )
    return pd.DataFrame(rows)
