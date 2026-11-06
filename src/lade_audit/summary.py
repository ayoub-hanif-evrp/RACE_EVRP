"""Summaries computed from prepared LaDe-P observations.

Derived quantities are labeled as derived. Fields that the file does not
contain are not estimated here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lade_audit.observations import haversine_m, open_tasks_at_accepts


def numeric_profile(series: pd.Series) -> dict:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty:
        return {"n": 0}
    quantiles = (0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)
    profile = {
        "n": int(values.shape[0]),
        "mean": float(values.mean()),
        "std": float(values.std(ddof=1)) if len(values) > 1 else 0.0,
        "min": float(values.min()),
        "max": float(values.max()),
    }
    for quantile in quantiles:
        label = f"p{int(round(quantile * 100)):02d}"
        profile[label] = float(values.quantile(quantile))
    return profile


def missing_profile(frame: pd.DataFrame, columns: list[str]) -> dict:
    profile = {}
    n_rows = len(frame)
    for column in columns:
        missing = int(frame[column].isna().sum())
        profile[column] = {
            "missing": missing,
            "missing_share": float(missing / n_rows) if n_rows else None,
            "nunique": int(frame[column].nunique(dropna=True)),
        }
    return profile


def _duty_table(frame: pd.DataFrame) -> pd.DataFrame:
    records = []
    grouped = frame.groupby(["courier_id", "ds"], sort=False, dropna=False)
    for (courier_id, ds), group in grouped:
        accept = group["accept_ts"].to_numpy(dtype="datetime64[ns]")
        pickup = group["pickup_ts"].to_numpy(dtype="datetime64[ns]")
        finite = ~pd.isna(accept) & ~pd.isna(pickup)
        open_counts = (
            open_tasks_at_accepts(accept[finite], pickup[finite]) if finite.any() else np.array([])
        )
        accept_finite = accept[finite]
        if len(accept_finite):
            order = np.argsort(accept_finite, kind="mergesort")
            sorted_accept = accept_finite[order]
            gaps = np.diff(sorted_accept).astype("timedelta64[s]").astype(np.float64) / 60.0
            n_positive_gaps = int(np.sum(gaps > 0))
            n_zero_gaps = int(np.sum(gaps == 0))
        else:
            gaps = np.array([])
            n_positive_gaps = 0
            n_zero_gaps = 0
        pickup_finite = pickup[~pd.isna(pickup)]
        if len(pickup_finite) > 1:
            pickup_gaps = np.diff(np.sort(pickup_finite)).astype("timedelta64[s]").astype(np.float64) / 60.0
        else:
            pickup_gaps = np.array([])
        start_row = group.loc[group["accept_ts"].idxmin()] if group["accept_ts"].notna().any() else None
        records.append(
            {
                "courier_id": courier_id,
                "ds": ds,
                "n_tasks": int(len(group)),
                "n_timed_tasks": int(finite.sum()),
                "n_accept_times": int(group["accept_ts"].nunique(dropna=True)),
                "n_pickup_times": int(group["pickup_ts"].nunique(dropna=True)),
                "open_at_accept_max": int(open_counts.max()) if len(open_counts) else None,
                "open_at_accept_median": float(np.median(open_counts)) if len(open_counts) else None,
                "share_accepts_with_other_open": (
                    float(np.mean(open_counts > 1)) if len(open_counts) else None
                ),
                "n_positive_accept_gaps": n_positive_gaps,
                "n_zero_accept_gaps": n_zero_gaps,
                "median_positive_accept_gap_min": (
                    float(np.median(gaps[gaps > 0])) if n_positive_gaps else None
                ),
                "median_positive_pickup_gap_min": (
                    float(np.median(pickup_gaps[pickup_gaps > 0]))
                    if np.any(pickup_gaps > 0)
                    else None
                ),
                "duty_span_min": (
                    float((group["pickup_ts"].max() - group["accept_ts"].min()).total_seconds() / 60.0)
                    if group["accept_ts"].notna().any() and group["pickup_ts"].notna().any()
                    else None
                ),
                "start_accept_lng": None if start_row is None else start_row["accept_gps_lng"],
                "start_accept_lat": None if start_row is None else start_row["accept_gps_lat"],
                "start_accept_gps_valid": None if start_row is None else bool(start_row["accept_gps_valid"]),
                "n_regions": int(group["region_id"].nunique(dropna=True)),
                "n_aoi": int(group["aoi_id"].nunique(dropna=True)),
            }
        )
    return pd.DataFrame.from_records(records)


def _start_location_stability(duties: pd.DataFrame) -> dict:
    usable = duties.loc[duties["start_accept_gps_valid"] == True].copy()  # noqa: E712
    if usable.empty:
        return {"n_couriers_with_start_gps": 0}
    distances = []
    n_days = []
    anchor_points = []
    for _, group in usable.groupby("courier_id"):
        if len(group) < 5:
            continue
        lng = pd.to_numeric(group["start_accept_lng"], errors="coerce").to_numpy()
        lat = pd.to_numeric(group["start_accept_lat"], errors="coerce").to_numpy()
        finite = np.isfinite(lng) & np.isfinite(lat)
        lng = lng[finite]
        lat = lat[finite]
        if len(lng) < 5:
            continue
        anchor_lng = float(np.median(lng))
        anchor_lat = float(np.median(lat))
        offset = haversine_m(lng, lat, np.full(len(lng), anchor_lng), np.full(len(lat), anchor_lat))
        distances.append(float(np.median(offset)))
        n_days.append(int(len(lng)))
        anchor_points.append((anchor_lng, anchor_lat))
    if not distances:
        return {"n_couriers_with_at_least_5_start_days": 0}
    series = pd.Series(distances)
    anchors = np.array(anchor_points, dtype="float64")
    center_lng = float(np.median(anchors[:, 0]))
    center_lat = float(np.median(anchors[:, 1]))
    between = haversine_m(
        anchors[:, 0],
        anchors[:, 1],
        np.full(len(anchors), center_lng),
        np.full(len(anchors), center_lat),
    )
    return {
        "definition": (
            "For each courier with at least five duties that have a finite accept-GPS "
            "at the earliest accept, the median distance from that courier's median "
            "start coordinate. The between-courier radius compares those personal "
            "medians. Neither quantity is a depot location."
        ),
        "n_couriers_with_at_least_5_start_days": int(len(series)),
        "median_of_courier_median_offset_m": float(series.median()),
        "p90_of_courier_median_offset_m": float(series.quantile(0.90)),
        "share_couriers_median_offset_within_500m": float((series <= 500).mean()),
        "share_couriers_median_offset_within_2000m": float((series <= 2000).mean()),
        "median_start_days_per_courier": float(np.median(n_days)),
        "between_courier_start_radius_m": numeric_profile(pd.Series(between)),
        "share_personal_starts_within_2km_of_their_median": float((between <= 2_000).mean()),
        "share_personal_starts_within_10km_of_their_median": float((between <= 10_000).mean()),
    }


def _spatial_concentration(frame: pd.DataFrame) -> dict:
    valid = frame.loc[frame["package_lng_valid"], ["lng", "lat"]].copy()
    lng = valid["lng"].to_numpy(dtype="float64")
    lat = valid["lat"].to_numpy(dtype="float64")
    anchor_lng = float(np.median(lng))
    anchor_lat = float(np.median(lat))
    radius = haversine_m(lng, lat, np.full(len(lng), anchor_lng), np.full(len(lat), anchor_lat))
    radius_series = pd.Series(radius)
    # Approximately 1 km cells at this latitude. This is a concentration grid,
    # not a road network.
    cell_lng = np.floor(lng / 0.012).astype(np.int64)
    cell_lat = np.floor(lat / 0.009).astype(np.int64)
    cells = pd.Series(list(zip(cell_lng, cell_lat, strict=True)))
    counts = cells.value_counts()
    return {
        "n_valid_package_coordinates": int(len(valid)),
        "median_lng": anchor_lng,
        "median_lat": anchor_lat,
        "lng_min": float(lng.min()),
        "lng_max": float(lng.max()),
        "lat_min": float(lat.min()),
        "lat_max": float(lat.max()),
        "radius_from_median_m": numeric_profile(radius_series),
        "share_within_5km": float((radius <= 5_000).mean()),
        "share_within_10km": float((radius <= 10_000).mean()),
        "share_within_20km": float((radius <= 20_000).mean()),
        "n_beyond_20km": int((radius > 20_000).sum()),
        "n_beyond_50km": int((radius > 50_000).sum()),
        "grid_cell_deg": {"lng": 0.012, "lat": 0.009},
        "n_occupied_1km_cells": int(counts.shape[0]),
        "densest_cell_tasks": int(counts.iloc[0]),
        "densest_cell_share": float(counts.iloc[0] / len(valid)),
        "top_10_cells_share": float(counts.iloc[:10].sum() / len(valid)),
    }


def _aoi_overlap(frame: pd.DataFrame) -> dict:
    aoi_day = frame.groupby(["ds", "aoi_id"], dropna=False)["courier_id"].nunique()
    region_day = frame.groupby(["ds", "region_id"], dropna=False)["courier_id"].nunique()
    task_aoi = frame.merge(
        aoi_day.rename("n_couriers").reset_index(),
        on=["ds", "aoi_id"],
        how="left",
    )
    return {
        "n_aoi_days": int(aoi_day.shape[0]),
        "share_aoi_days_with_2plus_couriers": float((aoi_day >= 2).mean()),
        "share_tasks_in_shared_aoi_days": float((task_aoi["n_couriers"] >= 2).mean()),
        "n_region_days": int(region_day.shape[0]),
        "share_region_days_with_2plus_couriers": float((region_day >= 2).mean()),
        "max_couriers_in_one_aoi_day": int(aoi_day.max()),
        "max_couriers_in_one_region_day": int(region_day.max()),
    }


def _interval_pool(duties: pd.DataFrame, column: str) -> dict:
    values = duties[column].dropna()
    return numeric_profile(values)


def _recorded_structure(frame: pd.DataFrame) -> dict:
    """Counts that are easy to misread from the marginal profiles alone."""

    lng = frame["lng"].to_numpy(dtype="float64")
    lat = frame["lat"].to_numpy(dtype="float64")
    radius = haversine_m(lng, lat, np.full(len(frame), np.median(lng)), np.full(len(lat), np.median(lat)))
    beyond = radius > 50_000
    stop_counts = frame.groupby(["lng", "lat"], sort=False).size()
    batch = frame.groupby(["courier_id", "ds", "accept_ts"], sort=False, dropna=False).size()
    active_days = frame.groupby("courier_id")["ds"].nunique()
    one_day = active_days[active_days == 1].index
    regular = active_days[active_days >= 30].index
    duty_sizes = frame.groupby(["courier_id", "ds"], sort=False).size()
    window = frame["window_minutes"].round()
    delay = frame["accept_to_pickup_minutes"]
    far_regions = sorted(int(value) for value in frame.loc[beyond, "region_id"].dropna().unique())
    near_regions = sorted(int(value) for value in frame.loc[~beyond, "region_id"].dropna().unique())
    far_couriers = set(frame.loc[beyond, "courier_id"].dropna().unique())
    near_couriers = set(frame.loc[~beyond, "courier_id"].dropna().unique())
    daily = frame.groupby("ds").size()
    trough = daily.loc[(daily.index >= 621) & (daily.index <= 625)]
    return {
        "n_unique_stop_coordinates": int(stop_counts.shape[0]),
        "n_coordinates_used_more_than_once": int((stop_counts > 1).sum()),
        "max_tasks_at_one_coordinate": int(stop_counts.max()),
        "share_tasks_at_repeated_coordinates": float(stop_counts.loc[stop_counts > 1].sum() / len(frame)),
        "n_tasks_beyond_50km_of_median_stop": int(beyond.sum()),
        "regions_beyond_50km": far_regions,
        "regions_within_50km": near_regions,
        "n_couriers_only_beyond_50km": int(len(far_couriers - near_couriers)),
        "n_couriers_only_within_50km": int(len(near_couriers - far_couriers)),
        "n_couriers_in_both_components": int(len(far_couriers & near_couriers)),
        "n_tasks_latitude_above_44_2": int((lat > 44.2).sum()),
        "n_tasks_latitude_below_43_2": int((lat < 43.2).sum()),
        "n_tasks_longitude_above_128": int((lng > 128).sum()),
        "window_share_exactly_120_min": float((window == 120).mean()),
        "window_share_exactly_899_min": float((window == 899).mean()),
        "n_windows_neither_120_nor_899": int((~window.isin([120, 899])).sum()),
        "share_accept_to_pickup_over_12h": float((delay > 720).mean()),
        "share_accept_to_pickup_over_24h": float((delay > 1440).mean()),
        "share_accept_to_pickup_zero": float((delay == 0).mean()),
        "n_accept_gps_beyond_50km_of_stop": int((frame["accept_gps_distance_m"] > 50_000).sum()),
        "n_pickup_gps_beyond_50km_of_stop": int((frame["pickup_gps_distance_m"] > 50_000).sum()),
        "n_pickup_gps_beyond_5km_of_stop": int((frame["pickup_gps_distance_m"] > 5_000).sum()),
        "share_duties_with_one_task": float((duty_sizes == 1).mean()),
        "share_tasks_in_one_task_duties": float(duty_sizes.loc[duty_sizes == 1].sum() / len(frame)),
        "n_couriers_observed_on_one_day": int(len(one_day)),
        "task_share_of_one_day_couriers": float(frame["courier_id"].isin(one_day).mean()),
        "n_couriers_observed_on_at_least_30_days": int(len(regular)),
        "task_share_of_couriers_with_at_least_30_days": float(frame["courier_id"].isin(regular).mean()),
        "share_tasks_sharing_accept_minute_within_duty": float(batch.loc[batch > 1].sum() / len(frame)),
        "tasks_on_21_to_25_june_codes": {str(int(index)): int(value) for index, value in trough.items()},
        "accept_hour_counts": {
            str(int(hour)): int(count)
            for hour, count in frame["accept_hour"].dropna().astype(int).value_counts().sort_index().items()
        },
        "pickup_hour_counts": {
            str(int(hour)): int(count)
            for hour, count in frame["pickup_hour"].dropna().astype(int).value_counts().sort_index().items()
        },
    }


def build_summary(frame: pd.DataFrame, source_columns: list[str]) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    n_rows = int(len(frame))
    duplicate_order_rows = int(frame["order_id"].duplicated(keep=False).sum())
    n_duplicate_order_ids = int(frame.loc[frame["order_id"].duplicated(keep=False), "order_id"].nunique())
    n_exact_duplicate_rows = int(frame.duplicated(subset=source_columns, keep=False).sum())

    duties = _duty_table(frame)
    daily = (
        frame.groupby("ds_date", dropna=False)
        .agg(
            n_tasks=("order_id", "size"),
            n_couriers=("courier_id", "nunique"),
            n_regions=("region_id", "nunique"),
            n_aoi=("aoi_id", "nunique"),
        )
        .reset_index()
    )
    observed_dates = daily.loc[daily["ds_date"].notna(), "ds_date"]
    if not observed_dates.empty:
        full_index = pd.date_range(observed_dates.min(), observed_dates.max(), freq="D")
        n_calendar_days = int(len(full_index))
        n_silent_days = int(n_calendar_days - observed_dates.nunique())
    else:
        n_calendar_days = 0
        n_silent_days = 0

    accept_seconds = frame["accept_second"].dropna()
    pickup_seconds = frame["pickup_second"].dropna()
    window_start_seconds = frame["window_start_second"].dropna()

    def _share(mask: pd.Series) -> float | None:
        return float(mask.fillna(False).mean()) if n_rows else None

    def _conditional_share(flag: pd.Series, eligible: pd.Series) -> float | None:
        chosen = flag.loc[eligible.fillna(False)]
        if chosen.empty:
            return None
        return float(chosen.mean())

    timed = frame["accept_ts"].notna() & frame["pickup_ts"].notna()
    windowed = frame["window_start_ts"].notna() & frame["window_end_ts"].notna()
    within_window = (
        windowed
        & frame["pickup_ts"].notna()
        & frame["pickup_ts"].ge(frame["window_start_ts"])
        & frame["pickup_ts"].le(frame["window_end_ts"])
    )
    early_pickup = windowed & frame["pickup_ts"].notna() & frame["pickup_ts"].lt(frame["window_start_ts"])
    late_pickup = windowed & frame["pickup_ts"].notna() & frame["pickup_ts"].gt(frame["window_end_ts"])

    aoi_counts = frame["aoi_id"].value_counts(dropna=False)
    aoi_share = (aoi_counts / n_rows).astype(float)
    herfindahl = float((aoi_share**2).sum())
    type_counts = frame["aoi_type"].value_counts(dropna=False)
    region_counts = frame["region_id"].value_counts(dropna=False)

    summary = {
        "n_rows": n_rows,
        "n_unique_order_id": int(frame["order_id"].nunique(dropna=True)),
        "n_duplicate_order_ids": n_duplicate_order_ids,
        "n_rows_belonging_to_duplicate_order_ids": duplicate_order_rows,
        "n_rows_in_exact_duplicate_groups": n_exact_duplicate_rows,
        "cities": sorted(frame["city"].dropna().astype(str).unique().tolist()),
        "n_couriers": int(frame["courier_id"].nunique(dropna=True)),
        "n_regions": int(frame["region_id"].nunique(dropna=True)),
        "n_aoi": int(frame["aoi_id"].nunique(dropna=True)),
        "n_aoi_types": int(frame["aoi_type"].nunique(dropna=True)),
        "n_distinct_ds_codes": int(frame["ds"].nunique(dropna=True)),
        "n_valid_business_dates": int(frame.loc[frame["ds_valid"], "ds_date"].nunique()),
        "n_invalid_business_dates": int((~frame["ds_valid"]).sum()),
        "ds_min": None if frame["ds"].dropna().empty else int(frame["ds"].min()),
        "ds_max": None if frame["ds"].dropna().empty else int(frame["ds"].max()),
        "business_date_min": None if observed_dates.empty else str(observed_dates.min().date()),
        "business_date_max": None if observed_dates.empty else str(observed_dates.max().date()),
        "n_calendar_days_in_observed_span": n_calendar_days,
        "n_dates_with_tasks": int(observed_dates.nunique()),
        "n_dates_in_span_without_tasks": n_silent_days,
        "ordering_year_note": (
            "Month and day are taken from the file. The year 2001 is an internal "
            "ordering device and is not an observed collection year."
        ),
        "missingness": missing_profile(frame, source_columns),
        "time_parse_failures": {
            "accept_time": int(frame["accept_time"].notna().sum() - frame["accept_ts"].notna().sum()),
            "time_window_start": int(
                frame["time_window_start"].notna().sum() - frame["window_start_ts"].notna().sum()
            ),
            "time_window_end": int(frame["time_window_end"].notna().sum() - frame["window_end_ts"].notna().sum()),
            "pickup_time": int(frame["pickup_time"].notna().sum() - frame["pickup_ts"].notna().sum()),
            "accept_gps_time": int(
                frame["accept_gps_time"].notna().sum() - frame["accept_gps_ts"].notna().sum()
            ),
            "pickup_gps_time": int(
                frame["pickup_gps_time"].notna().sum() - frame["pickup_gps_ts"].notna().sum()
            ),
        },
        "timestamps_rounded_to_minute": {
            "accept_share_second_zero": float((accept_seconds == 0).mean()) if len(accept_seconds) else None,
            "pickup_share_second_zero": float((pickup_seconds == 0).mean()) if len(pickup_seconds) else None,
            "window_start_share_second_zero": (
                float((window_start_seconds == 0).mean()) if len(window_start_seconds) else None
            ),
        },
        "cross_date": {
            "window_crosses_midnight_share": _share(frame["window_crosses_midnight"]),
            "window_year_wrap_count": int(frame["window_year_wrap"].sum()),
            "accept_pickup_crosses_date_share": _share(frame["accept_pickup_crosses_date"]),
            "accept_pickup_year_wrap_count": int(frame["accept_pickup_year_wrap"].sum()),
            "accept_matches_ds_share": _conditional_share(
                frame["accept_matches_ds"], frame["accept_date"].notna() & frame["ds_date"].notna()
            ),
            "pickup_matches_ds_share": _conditional_share(
                frame["pickup_matches_ds"], frame["pickup_date"].notna() & frame["ds_date"].notna()
            ),
            "window_start_matches_ds_share": _conditional_share(
                frame["window_start_matches_ds"],
                frame["window_start_date"].notna() & frame["ds_date"].notna(),
            ),
            "accept_before_window_start_share": _share(
                frame["accept_ts"].notna()
                & frame["window_start_ts"].notna()
                & frame["accept_ts"].lt(frame["window_start_ts"])
            ),
            "accept_after_window_end_share": _share(
                frame["accept_ts"].notna()
                & frame["window_end_ts"].notna()
                & frame["accept_ts"].gt(frame["window_end_ts"])
            ),
            "pickup_before_accept_count": int(
                (timed & frame["pickup_ts"].lt(frame["accept_ts"])).sum()
            ),
            "pickup_within_window_share": _share(within_window),
            "pickup_before_window_share": _share(early_pickup),
            "pickup_after_window_share": _share(late_pickup),
        },
        "intervals_minutes": {
            "window": numeric_profile(frame["window_minutes"]),
            "accept_to_pickup": numeric_profile(frame["accept_to_pickup_minutes"]),
            "accept_event_to_accept_gps": numeric_profile(frame["accept_to_gps_minutes"]),
            "pickup_event_to_pickup_gps": numeric_profile(frame["pickup_to_gps_minutes"]),
            "duty_span": _interval_pool(duties, "duty_span_min"),
            "median_positive_inter_accept_by_duty": _interval_pool(
                duties, "median_positive_accept_gap_min"
            ),
            "median_positive_inter_pickup_by_duty": _interval_pool(
                duties, "median_positive_pickup_gap_min"
            ),
        },
        "duties": {
            "n_courier_days": int(len(duties)),
            "tasks_per_courier_day": numeric_profile(duties["n_tasks"]),
            "couriers_per_active_day": numeric_profile(daily["n_couriers"]),
            "tasks_per_active_day": numeric_profile(daily["n_tasks"]),
            "share_duties_with_an_accept_while_another_task_open": float(
                duties["share_accepts_with_other_open"].dropna().gt(0).mean()
            )
            if duties["share_accepts_with_other_open"].notna().any()
            else None,
            "share_accepts_that_see_another_open_task": float(
                np.average(
                    duties.loc[duties["share_accepts_with_other_open"].notna(), "share_accepts_with_other_open"],
                    weights=duties.loc[duties["share_accepts_with_other_open"].notna(), "n_timed_tasks"],
                )
            )
            if duties["n_timed_tasks"].sum()
            else None,
            "max_open_tasks_at_an_accept": (
                None
                if duties["open_at_accept_max"].dropna().empty
                else int(duties["open_at_accept_max"].max())
            ),
            "share_duties_with_at_least_one_zero_accept_gap": float((duties["n_zero_accept_gaps"] > 0).mean()),
            "tasks_per_courier_overall": numeric_profile(frame.groupby("courier_id").size()),
            "active_days_per_courier": numeric_profile(duties.groupby("courier_id").size()),
        },
        "spatial": _spatial_concentration(frame),
        "accept_gps_distance_m": numeric_profile(frame["accept_gps_distance_m"]),
        "pickup_gps_distance_m": numeric_profile(frame["pickup_gps_distance_m"]),
        "start_location_stability": _start_location_stability(duties),
        "overlap": _aoi_overlap(frame),
        "aoi_concentration": {
            "herfindahl": herfindahl,
            "top_1_share": float(aoi_share.iloc[0]),
            "top_10_share": float(aoi_share.iloc[:10].sum()),
            "top_10": [
                {"aoi_id": None if pd.isna(index) else int(index), "n": int(count), "share": float(count / n_rows)}
                for index, count in aoi_counts.iloc[:10].items()
            ],
        },
        "aoi_type_counts": [
            {"aoi_type": None if pd.isna(index) else int(index), "n": int(count)}
            for index, count in type_counts.items()
        ],
        "region_counts": [
            {"region_id": None if pd.isna(index) else int(index), "n": int(count)}
            for index, count in region_counts.items()
        ],
        "coordinate_flags": {
            "invalid_package_coordinates": int((~frame["package_lng_valid"]).sum()),
            "missing_accept_gps": int((~frame["accept_gps_valid"]).sum()),
            "missing_pickup_gps": int((~frame["pickup_gps_valid"]).sum()),
        },
        "structure": _recorded_structure(frame),
    }
    return summary, duties, daily
