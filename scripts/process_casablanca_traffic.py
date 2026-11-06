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
    holdout = held_out_zone_hour_error(trajectories)
    fifo = fifo_check_piecewise_constant(profiles["citywide_hour"].set_index("hour")["tti_factor"])

    out = traffic_dir()
    out.mkdir(parents=True, exist_ok=True)
    trajectories.to_parquet(out / "trajectory_hours.parquet", index=False)
    communes.to_csv(out / "communes.csv", index=False)
    coords.to_csv(out / "coordinate_points.csv", index=False)
    land.to_csv(out / "land_use.csv", index=False)
    for name, frame in profiles.items():
        frame.to_csv(out / f"tti_{name}.csv", index=False)

    summary = {
        "generated_at_utc": utc_now(),
        "audit": audit,
        "holdout_evaluation": holdout,
        "fifo_check": fifo,
        "outputs": {
            "trajectory_hours": str(out / "trajectory_hours.parquet"),
            "profiles": [f"tti_{name}.csv" for name in profiles],
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

## FIFO check on citywide hourly factors

{json.dumps(summary['fifo_check'], indent=2)}

## Held-out day evaluation of citywide hourly TTI

{json.dumps(summary['holdout_evaluation'], indent=2)}
"""


if __name__ == "__main__":
    sys.exit(main())
