"""Process the Mendeley traffic workbook into tidy profiles and an audit report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import manifest_dir, project_root, report_dir, traffic_dir
from race_casablanca.traffic.profiles import (
    build_tti_profiles,
    fifo_check_piecewise_constant,
    held_out_zone_hour_error,
)
from race_casablanca.traffic.workbook import (
    audit_workbook,
    load_all_trajectories,
    load_communes,
    load_coordinates,
    load_land_use,
)


def main() -> int:
    manifest = json.loads((manifest_dir() / "traffic_workbook_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") == "failed" or not manifest.get("checksum_matches_published", False):
        print("Traffic workbook is missing or unverified.", file=sys.stderr)
        return 1
    workbook = project_root() / manifest["local_path"]
    if not workbook.is_file():
        # Fallback to raw traffic directory.
        workbook = Path(manifest_dir().parents[0] / "raw" / "traffic" / manifest["filename"])
    print(f"Processing {workbook}")
    audit = audit_workbook(workbook)
    trajectories = load_all_trajectories(workbook)
    communes = load_communes(workbook)
    coords = load_coordinates(workbook)
    land = load_land_use(workbook)
    profiles = build_tti_profiles(trajectories)
    profiles_mon_sat = build_tti_profiles(trajectories, exclude_days=["Sunday"])
    holdout = held_out_zone_hour_error(trajectories)
    fifo = fifo_check_piecewise_constant(profiles["citywide_hour"].set_index("hour")["tti_factor"])

    # Unit-audit diagnostics after milli-minute correction.
    tt = trajectories.dropna(subset=["travel_time_min", "distance_m", "tti"]).copy()
    tt = tt[(tt["travel_time_min"] > 0) & (tt["distance_m"] > 0) & (tt["tti"] > 0)]
    tt["speed_kmh"] = (tt["distance_m"] / 1000.0) / (tt["travel_time_min"] / 60.0)
    tt["ff_speed_kmh"] = (tt["distance_m"] / 1000.0) / ((tt["travel_time_min"] / tt["tti"]) / 60.0)
    if "travel_time_raw" in trajectories.columns:
        raw_big = float((trajectories["travel_time_raw"] > 180).mean())
    else:
        raw_big = None
    unit_audit = {
        "rule": "values>180 interpreted as minutes*1000 (Excel decimal artifacts), else minutes",
        "rejected_rule": "values>180 as seconds (/60) — yields ~1.5 km/h median speeds (invalid)",
        "share_raw_values_gt_180": raw_big,
        "median_travel_min": float(tt["travel_time_min"].median()),
        "median_speed_kmh": float(tt["speed_kmh"].median()),
        "median_free_flow_speed_kmh": float(tt["ff_speed_kmh"].median()),
        "share_speed_5_to_120": float(((tt["speed_kmh"] >= 5) & (tt["speed_kmh"] <= 120)).mean()),
    }

    out = traffic_dir()
    out.mkdir(parents=True, exist_ok=True)
    trajectories.to_parquet(out / "trajectory_hours.parquet", index=False)
    # Workbook Table-1 populations only. Never the demand-weight authority.
    # Demand uses zones/demand_zone_weights.csv (built by build_demand_zone_weights.py).
    communes.to_csv(out / "communes_workbook.csv", index=False)
    communes.to_csv(out / "communes.csv", index=False)
    coords.to_csv(out / "coordinate_points.csv", index=False)
    land.to_csv(out / "land_use.csv", index=False)
    for name, frame in profiles.items():
        frame.to_csv(out / f"tti_{name}.csv", index=False)
    profiles_mon_sat["citywide_hour"].to_csv(out / "tti_citywide_hour_fit_mon_sat.csv", index=False)
    profiles_mon_sat["zone_day_hour"].to_csv(out / "tti_zone_day_hour_fit_mon_sat.csv", index=False)

    summary = {
        "generated_at_utc": utc_now(),
        "audit": audit,
        "unit_audit": unit_audit,
        "holdout_evaluation": holdout,
        "fifo_check": fifo,
        "outputs": {
            "trajectory_hours": str(out / "trajectory_hours.parquet"),
            "profiles": [f"tti_{name}.csv" for name in profiles],
            "holdout_fit_profiles": [
                "tti_citywide_hour_fit_mon_sat.csv",
                "tti_zone_day_hour_fit_mon_sat.csv",
            ],
        },
    }
    write_json(out / "traffic_process_summary.json", summary)

    report = report_dir() / "CASABLANCA_TRAFFIC_AUDIT.md"
    report.write_text(
        _render_audit_markdown(summary, manifest),
        encoding="utf-8",
    )
    print(f"Wrote {report}")
    print(f"Trajectory-hour rows: {audit['n_trajectory_hour_rows']}")
    return 0


def _render_audit_markdown(summary: dict, manifest: dict) -> str:
    audit = summary["audit"]
    return f"""# Casablanca traffic workbook audit

Source: Rouky & Bousouf, Mendeley Data DOI {manifest.get('doi')}, CC BY 4.0.  
Retrieved: {manifest.get('retrieved_at_utc')}  
SHA-256: `{manifest.get('sha256')}` (verified={manifest.get('checksum_matches_published')})

## Worksheets

The workbook contains Summary, Table 0 coordinates, Tables 1–4 zone attributes, and Tables 5–11 daily trajectory travel times (Monday–Sunday).

## Key facts from the downloaded file

- Communes / ZIP zones: **{audit['n_communes']}**
- Coordinate points: **{audit['n_coordinate_points']}** (5 per commune)
- Trajectory-hour rows: **{audit['n_trajectory_hour_rows']}**
- Days: {', '.join(audit['days'])}
- Hours: 0–23 present
- OD coordinates present on trajectories: **{audit['share_rows_with_od_coordinates']:.3f}**
- Bidirectional OD pairs observed: **{audit['bidirectional_pairs']}**
- TTI median/min/max: {audit['tti_summary']['median']:.3f} / {audit['tti_summary']['min']:.3f} / {audit['tti_summary']['max']:.3f}

## What the workbook can support

- Zone-level and hour-of-day congestion factors (Travel Time Index).
- Day-of-week variation.
- OD endpoint coordinates and Waze-reported route distances/times for held-out evaluation of aggregate travel-time models.

## What the workbook cannot support

- Road-segment GPS telemetry.
- Exact Waze route polylines.
- Edge-specific traffic calibration on the OSM graph.

{audit['coordinate_claim']}

## Travel-time unit interpretation

Workbook headers label travel times as minutes. Across Tue–Sun, many cells are
integers >180. Treating those as seconds (/60) produces impossible ~1.5 km/h
median speeds. Treating them as minutes×1000 (/1000) aligns distributions with
true-minute cells and yields free-flow speeds clustered at ~60 km/h (matching
the workbook TTI definition).

{json.dumps(summary['unit_audit'], indent=2)}

## FIFO check on citywide hourly factors

{json.dumps(summary['fifo_check'], indent=2)}

## Held-out day evaluation of citywide hourly TTI

TTI profile fitted on Mon–Sat and scored on Sunday (profile-level, not OD minutes):

{json.dumps(summary['holdout_evaluation'], indent=2)}

Operational full-week profiles remain in `tti_citywide_hour.csv`. Genuine OD
holdout predictions must use `tti_citywide_hour_fit_mon_sat.csv` (see
`scripts/validate_od_travel_times.py`).
"""


if __name__ == "__main__":
    sys.exit(main())
