"""Build zonal and citywide congestion factor profiles from Waze-derived TTI."""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_tti_profiles(trajectories: pd.DataFrame, exclude_days: list[str] | None = None) -> dict[str, pd.DataFrame]:
    clean = trajectories.dropna(subset=["tti"]).copy()
    clean = clean[clean["tti"] > 0]
    if exclude_days:
        clean = clean[~clean["day"].isin(exclude_days)]
    zone_hour = (
        clean.groupby(["commune", "day", "hour"], as_index=False)["tti"]
        .median()
        .rename(columns={"tti": "tti_factor"})
    )
    city_hour = (
        clean.groupby(["day", "hour"], as_index=False)["tti"]
        .median()
        .rename(columns={"tti": "tti_factor"})
    )
    citywide_hour = (
        clean.groupby(["hour"], as_index=False)["tti"].median().rename(columns={"tti": "tti_factor"})
    )
    return {
        "zone_day_hour": zone_hour,
        "city_day_hour": city_hour,
        "citywide_hour": citywide_hour,
    }


def held_out_zone_hour_error(trajectories: pd.DataFrame, holdout_day: str = "Sunday") -> dict:
    """Evaluate citywide hour profile against a held-out day.

    This is not edge-level validation. It measures how well a citywide hourly
    TTI profile matches zone-day observations on an unused day.
    """

    clean = trajectories.dropna(subset=["tti"]).copy()
    clean = clean[clean["tti"] > 0]
    train = clean[clean["day"] != holdout_day]
    test = clean[clean["day"] == holdout_day]
    if train.empty or test.empty:
        return {"status": "insufficient_data", "holdout_day": holdout_day}
    profile = train.groupby("hour")["tti"].median()
    merged = test.copy()
    merged["predicted"] = merged["hour"].map(profile)
    err = (merged["predicted"] - merged["tti"]).abs()
    return {
        "status": "ok",
        "holdout_day": holdout_day,
        "n_test_rows": int(len(merged)),
        "mae": float(err.mean()),
        "rmse": float(np.sqrt(((merged["predicted"] - merged["tti"]) ** 2).mean())),
        "median_abs_error": float(err.median()),
    }


def fifo_check_piecewise_constant(factors_by_hour: pd.Series, free_flow_seconds: float = 600.0) -> dict:
    """Check FIFO for travel_time(t)=factor(hour(t))*free_flow with piecewise-constant factors.

    Waiting until the next hour is sufficient to restore FIFO when factors jump upward.
    """

    factors = factors_by_hour.sort_index()
    violations = 0
    examples = []
    for hour in range(24):
        f0 = float(factors.get(hour, 1.0))
        f1 = float(factors.get((hour + 1) % 24, 1.0))
        # Depart at end of hour h vs start of next: without waiting, a later departure
        # can overtake if factor falls sharply. Classic FIFO break when
        # t1 + f1*FF < t0 + f0*FF for t1>t0 within adjacent buckets.
        # For unit free-flow, departure at hour boundary:
        if f1 * free_flow_seconds + 0 < f0 * free_flow_seconds:
            # Later departure immediately after hour change arrives earlier.
            violations += 1
            if len(examples) < 5:
                examples.append({"from_hour": hour, "to_hour": (hour + 1) % 24, "f0": f0, "f1": f1})
    return {
        "n_downward_jumps": violations,
        "fifo_without_waiting": violations == 0,
        "remedy": "wait_for_next_bucket_or_time_dependent_dijkstra",
        "examples": examples,
    }
