"""Parse the published Casablanca traffic workbook into tidy tables."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DAY_SHEETS = {
    "Monday": "Table 5. Monday",
    "Tuesday": "Table 6. Tuesday",
    "Wednesday": "Table 7. Wednesday",
    "Thursday": "Table. 8 Thursday",
    "Friday": "Table. 9 Friday",
    "Saturday": "Table. 10 Saturday",
    "Sunday": "Table. 11 Sunday",
}


def _forward_fill_commune(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["commune"] = out["commune"].ffill()
    out["zip_code"] = out["zip_code"].ffill()
    return out


def load_communes(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="Table 1. Population size in eac", header=None)
    header_idx = raw.index[raw.iloc[:, 1].astype(str).str.contains("Commune", na=False)][0]
    body = raw.iloc[header_idx + 1 :, 1:6].copy()
    body.columns = ["commune", "zip_code", "population", "households", "density"]
    body = body.dropna(subset=["commune"]).reset_index(drop=True)
    for column in ["population", "households", "density"]:
        body[column] = pd.to_numeric(body[column], errors="coerce")
    body["zip_code"] = body["zip_code"].astype(str)
    return body


def load_coordinates(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="Table 0. Coordinates", header=None)
    header_idx = raw.index[raw.iloc[:, 1].astype(str).str.contains("Commune", na=False)][0]
    body = raw.iloc[header_idx + 1 :, 1:7].copy()
    body.columns = ["commune", "zip_code", "point_index", "lat", "lon", "coord_text"]
    body = _forward_fill_commune(body)
    body = body.dropna(subset=["point_index"]).reset_index(drop=True)
    body["point_index"] = pd.to_numeric(body["point_index"], errors="coerce").astype(int)
    body["lat"] = pd.to_numeric(body["lat"], errors="coerce")
    body["lon"] = pd.to_numeric(body["lon"], errors="coerce")
    body["zip_code"] = body["zip_code"].astype(str)
    return body


def load_land_use(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name="Table 4. Land use variables ", header=None)
    header_idx = raw.index[raw.iloc[:, 1].astype(str).str.contains("Commune", na=False)][0]
    header = [str(value).strip() for value in raw.iloc[header_idx, 1:].tolist()]
    body = raw.iloc[header_idx + 1 :, 1 : 1 + len(header)].copy()
    body.columns = header
    body = body.dropna(subset=[header[0]]).reset_index(drop=True)
    body = body.rename(columns={header[0]: "commune", header[1]: "zip_code"})
    body["zip_code"] = body["zip_code"].astype(str)
    for column in body.columns:
        if column not in {"commune", "zip_code"}:
            body[column] = pd.to_numeric(body[column], errors="coerce")
    return body


def _normalize_distance(value: float) -> float:
    """Return distance in metres.

    The sheet header says kilometres, but most values are metre-scale integers.
    Values below 100 are treated as kilometres already.
    """

    if not np.isfinite(value):
        return np.nan
    if value > 100:
        return float(value)
    return float(value) * 1000.0


def _normalize_travel_time_min(value: float) -> float:
    """Return travel time in minutes.

    Sheet headers label the field as minutes. Empirically, ~57% of cells on
    Tue–Sun are integers >180 that match minutes×1000 (Excel decimal artifacts),
    not seconds: after /1000, free-flow speeds cluster at 60 km/h and coincide
    with the minute-scale distribution. Values ≤180 are kept as minutes.
    """

    if not np.isfinite(value):
        return np.nan
    if value > 180:
        return float(value) / 1000.0
    return float(value)


def _find_commune_header_row(raw: pd.DataFrame) -> int:
    for i in range(min(20, len(raw))):
        if str(raw.iloc[i, 1]).strip().upper() == "COMMUNE":
            return int(i)
    raise RuntimeError("Could not locate COMMUNE header row in day sheet")


def _parse_day_sheet(path: Path, day: str, sheet: str) -> pd.DataFrame:
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    header_idx = _find_commune_header_row(raw)
    records = []
    current_commune = None
    current_zip = None
    for _, row in raw.iloc[header_idx + 1 :].iterrows():
        values = row.tolist()
        if isinstance(values[1], str) and values[1].strip() and values[1].strip() != "COMMUNE":
            current_commune = values[1].strip()
            current_zip = values[2]
        if current_commune is None:
            continue
        if pd.isna(values[3]) or pd.isna(values[7]):
            continue
        try:
            o_idx = int(float(values[3]))
            d_idx = int(float(values[7]))
            o_lat, o_lon = float(values[5]), float(values[6])
            d_lat, d_lon = float(values[9]), float(values[10])
        except (TypeError, ValueError):
            continue
        distance = values[11]
        travel_hours = values[12:36]
        tti_hours = values[36:60]
        for hour in range(24):
            travel = travel_hours[hour] if hour < len(travel_hours) else np.nan
            tti = tti_hours[hour] if hour < len(tti_hours) else np.nan
            try:
                travel_f = float(travel) if pd.notna(travel) else np.nan
                tti_f = float(tti) if pd.notna(tti) else np.nan
            except (TypeError, ValueError):
                continue
            records.append(
                {
                    "day": day,
                    "commune": current_commune,
                    "zip_code": str(current_zip),
                    "origin_index": o_idx,
                    "dest_index": d_idx,
                    "origin_lat": o_lat,
                    "origin_lon": o_lon,
                    "dest_lat": d_lat,
                    "dest_lon": d_lon,
                    "distance_raw": float(distance) if pd.notna(distance) else np.nan,
                    "distance_m": _normalize_distance(float(distance)) if pd.notna(distance) else np.nan,
                    "hour": hour,
                    "travel_time_min": _normalize_travel_time_min(travel_f) if pd.notna(travel_f) else np.nan,
                    "travel_time_raw": travel_f,
                    "tti": tti_f,
                }
            )
    return pd.DataFrame.from_records(records)


def load_all_trajectories(path: Path) -> pd.DataFrame:
    frames = [_parse_day_sheet(path, day, sheet) for day, sheet in DAY_SHEETS.items()]
    return pd.concat(frames, ignore_index=True)


def audit_workbook(path: Path) -> dict:
    communes = load_communes(path)
    coords = load_coordinates(path)
    land = load_land_use(path)
    trajectories = load_all_trajectories(path)
    od = trajectories.drop_duplicates(["day", "commune", "origin_index", "dest_index"])
    return {
        "workbook": str(path.name),
        "n_communes": int(len(communes)),
        "commune_names": communes["commune"].tolist(),
        "n_coordinate_points": int(len(coords)),
        "points_per_commune_median": float(coords.groupby("commune").size().median()),
        "n_trajectory_hour_rows": int(len(trajectories)),
        "n_od_rows_per_day_mean": float(od.groupby("day").size().mean()),
        "days": sorted(trajectories["day"].dropna().unique().tolist()),
        "hours": sorted(int(h) for h in trajectories["hour"].dropna().unique().tolist()),
        "share_rows_with_od_coordinates": float(
            trajectories[["origin_lat", "origin_lon", "dest_lat", "dest_lon"]].notna().all(axis=1).mean()
        ),
        "distance_missing_share": float(trajectories["distance_m"].isna().mean()),
        "travel_time_missing_share": float(trajectories["travel_time_min"].isna().mean()),
        "tti_missing_share": float(trajectories["tti"].isna().mean()),
        "tti_summary": {
            "min": float(trajectories["tti"].min()),
            "median": float(trajectories["tti"].median()),
            "max": float(trajectories["tti"].max()),
        },
        "bidirectional_pairs": int(_count_reverse_pairs(trajectories)),
        "land_use_columns": [column for column in land.columns if column not in {"commune", "zip_code"}],
        "route_geometry_present": False,
        "coordinate_claim": (
            "Origin and destination coordinates are present for each trajectory. "
            "Waze route polylines are not present, so OSM edge matching of the observed "
            "routes is not supported by this workbook alone."
        ),
    }


def _count_reverse_pairs(trajectories: pd.DataFrame) -> int:
    sample = trajectories.drop_duplicates(["day", "commune", "origin_index", "dest_index"])
    keys = set(zip(sample["day"], sample["commune"], sample["origin_index"], sample["dest_index"]))
    count = 0
    for day, commune, origin, dest in keys:
        if (day, commune, dest, origin) in keys:
            count += 1
    return count // 2
