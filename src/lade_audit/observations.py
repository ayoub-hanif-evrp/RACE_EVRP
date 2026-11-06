"""Schema gate and derived-field construction.

Processing runs only after the on-disk Arrow schema matches the published
LaDe-P column list. Rows are not dropped and missing GPS fields are not filled.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from lade_audit.constants import REQUIRED_COLUMNS
from lade_audit.parsing import (
    clock_parts,
    minutes_between,
    parse_business_date,
    parse_clock,
    year_boundary_wrap,
)


def read_arrow_schema(path: Path) -> dict:
    parquet = pq.ParquetFile(path)
    arrow_schema = parquet.schema_arrow
    columns = []
    for field in arrow_schema:
        columns.append(
            {
                "name": field.name,
                "type": str(field.type),
                "nullable": field.nullable,
            }
        )
    return {
        "num_rows": int(parquet.metadata.num_rows),
        "num_row_groups": int(parquet.num_row_groups),
        "columns": columns,
    }


def assert_published_schema(schema_report: dict) -> None:
    names = [column["name"] for column in schema_report["columns"]]
    if tuple(names) != REQUIRED_COLUMNS:
        missing = [name for name in REQUIRED_COLUMNS if name not in names]
        unexpected = [name for name in names if name not in REQUIRED_COLUMNS]
        raise ValueError(
            "Parquet schema does not match the published LaDe-P pickup fields. "
            f"Missing={missing}; unexpected={unexpected}; observed={names}."
        )


def load_raw_frame(path: Path) -> tuple[pd.DataFrame, dict]:
    schema_report = read_arrow_schema(path)
    assert_published_schema(schema_report)
    frame = pd.read_parquet(path, engine="pyarrow")
    if list(frame.columns) != list(REQUIRED_COLUMNS):
        raise ValueError("pandas column order does not match the Arrow schema.")
    if len(frame) != schema_report["num_rows"]:
        raise ValueError("pandas row count does not match the Parquet metadata.")
    return frame, schema_report


def _blank_to_na(series: pd.Series) -> pd.Series:
    if series.dtype == object or pd.api.types.is_string_dtype(series):
        text = series.astype("string").str.strip()
        return text.mask(text.isin(["", "None", "nan", "NaN", "null", "<NA>"]))
    return series


def prepare_observations(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach parsed clocks and distances without removing source columns."""

    out = frame.copy()
    for column in (
        "accept_time",
        "time_window_start",
        "time_window_end",
        "pickup_time",
        "pickup_gps_time",
        "accept_gps_time",
        "city",
    ):
        out[column] = _blank_to_na(out[column])

    business = parse_business_date(out["ds"])
    out = pd.concat([out, business], axis=1)

    out["accept_ts"] = parse_clock(out["accept_time"])
    out["window_start_ts"] = parse_clock(out["time_window_start"])
    out["window_end_ts"] = parse_clock(out["time_window_end"])
    out["pickup_ts"] = parse_clock(out["pickup_time"])
    out["accept_gps_ts"] = parse_clock(out["accept_gps_time"])
    out["pickup_gps_ts"] = parse_clock(out["pickup_gps_time"])

    out["window_year_wrap"] = year_boundary_wrap(out["window_start_ts"], out["window_end_ts"])
    out["accept_pickup_year_wrap"] = year_boundary_wrap(out["accept_ts"], out["pickup_ts"])
    out["window_minutes"] = minutes_between(out["window_start_ts"], out["window_end_ts"])
    out["accept_to_pickup_minutes"] = minutes_between(out["accept_ts"], out["pickup_ts"])
    out["accept_to_gps_minutes"] = minutes_between(out["accept_ts"], out["accept_gps_ts"])
    out["pickup_to_gps_minutes"] = minutes_between(out["pickup_ts"], out["pickup_gps_ts"])

    accept_clock = clock_parts(out["accept_ts"]).add_prefix("accept_")
    pickup_clock = clock_parts(out["pickup_ts"]).add_prefix("pickup_")
    start_clock = clock_parts(out["window_start_ts"]).add_prefix("window_start_")
    end_clock = clock_parts(out["window_end_ts"]).add_prefix("window_end_")
    out = pd.concat([out, accept_clock, pickup_clock, start_clock, end_clock], axis=1)

    out["accept_date"] = out["accept_ts"].dt.normalize()
    out["pickup_date"] = out["pickup_ts"].dt.normalize()
    out["window_start_date"] = out["window_start_ts"].dt.normalize()
    out["window_end_date"] = out["window_end_ts"].dt.normalize()
    out["window_crosses_midnight"] = (
        out["window_start_date"].notna()
        & out["window_end_date"].notna()
        & (out["window_end_date"] > out["window_start_date"])
    )
    out["accept_pickup_crosses_date"] = (
        out["accept_date"].notna()
        & out["pickup_date"].notna()
        & (out["accept_date"] != out["pickup_date"])
    )
    out["accept_matches_ds"] = out["accept_date"].eq(out["ds_date"])
    out["pickup_matches_ds"] = out["pickup_date"].eq(out["ds_date"])
    out["window_start_matches_ds"] = out["window_start_date"].eq(out["ds_date"])

    out["package_lng_valid"] = _coordinate_valid(out["lng"], out["lat"])
    out["accept_gps_valid"] = _coordinate_valid(out["accept_gps_lng"], out["accept_gps_lat"])
    out["pickup_gps_valid"] = _coordinate_valid(out["pickup_gps_lng"], out["pickup_gps_lat"])
    out["accept_gps_distance_m"] = _pairwise_haversine(
        out["lng"], out["lat"], out["accept_gps_lng"], out["accept_gps_lat"]
    )
    out["pickup_gps_distance_m"] = _pairwise_haversine(
        out["lng"], out["lat"], out["pickup_gps_lng"], out["pickup_gps_lat"]
    )
    return out


def _coordinate_valid(lng: pd.Series, lat: pd.Series) -> pd.Series:
    lng_num = pd.to_numeric(lng, errors="coerce")
    lat_num = pd.to_numeric(lat, errors="coerce")
    finite = np.isfinite(lng_num.to_numpy(dtype="float64")) & np.isfinite(
        lat_num.to_numpy(dtype="float64")
    )
    in_range = lng_num.between(-180, 180) & lat_num.between(-90, 90)
    not_origin = ~((lng_num == 0) & (lat_num == 0))
    return pd.Series(finite, index=lng.index) & in_range & not_origin & lng_num.notna() & lat_num.notna()


def haversine_m(
    lon1: np.ndarray,
    lat1: np.ndarray,
    lon2: np.ndarray,
    lat2: np.ndarray,
) -> np.ndarray:
    """Great-circle distance in metres. Invalid inputs become NaN."""

    lon1 = np.asarray(lon1, dtype="float64")
    lat1 = np.asarray(lat1, dtype="float64")
    lon2 = np.asarray(lon2, dtype="float64")
    lat2 = np.asarray(lat2, dtype="float64")
    valid = np.isfinite(lon1) & np.isfinite(lat1) & np.isfinite(lon2) & np.isfinite(lat2)
    radius = 6_371_000.0
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlmb / 2.0) ** 2
    a = np.clip(a, 0.0, 1.0)
    distance = 2.0 * radius * np.arcsin(np.sqrt(a))
    distance[~valid] = np.nan
    return distance


def _pairwise_haversine(
    lon1: pd.Series, lat1: pd.Series, lon2: pd.Series, lat2: pd.Series
) -> pd.Series:
    distance = haversine_m(
        pd.to_numeric(lon1, errors="coerce").to_numpy(),
        pd.to_numeric(lat1, errors="coerce").to_numpy(),
        pd.to_numeric(lon2, errors="coerce").to_numpy(),
        pd.to_numeric(lat2, errors="coerce").to_numpy(),
    )
    return pd.Series(distance, index=lon1.index)


def open_tasks_at_accepts(accept: np.ndarray, pickup: np.ndarray) -> np.ndarray:
    """Count tasks already accepted and not yet picked up at each accept time.

    A task is known at time ``t`` when its accept time is less than or equal
    to ``t``. It is still open when its pickup time is strictly later than
    ``t``. Simultaneous accepts are one batch: each of them sees the whole batch.
    """

    accept = np.asarray(accept)
    pickup = np.asarray(pickup)
    if accept.shape != pickup.shape:
        raise ValueError("accept and pickup arrays must have the same shape.")
    if len(accept) == 0:
        return np.array([], dtype=int)
    order = np.argsort(accept, kind="mergesort")
    accept_sorted = accept[order]
    pickup_sorted = pickup[order]
    counts_sorted = np.empty(len(accept), dtype=int)
    for index, moment in enumerate(accept_sorted):
        known = accept_sorted <= moment
        counts_sorted[index] = int(np.sum(pickup_sorted[known] > moment))
    counts = np.empty(len(accept), dtype=int)
    counts[order] = counts_sorted
    return counts
