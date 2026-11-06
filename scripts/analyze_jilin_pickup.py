"""Inspect the Jilin parquet, write audit tables, and draw the figures.

The script stops if the local file does not match the published checksum.
"""

from __future__ import annotations

import json
import math
import platform
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from lade_audit.constants import REQUIRED_COLUMNS
from lade_audit.figures import (
    figure_daily_volumes,
    figure_event_times,
    figure_geography,
    figure_tasks_per_duty,
    figure_time_windows,
)
from lade_audit.hashing import sha256_file
from lade_audit.observations import load_raw_frame, prepare_observations
from lade_audit.paths import figure_dir, manifest_path, processed_dir, raw_parquet_path
from lade_audit.summary import build_summary


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if not np.isfinite(value):
            return None
        return float(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def main() -> int:
    parquet_path = raw_parquet_path()
    if not parquet_path.is_file():
        print(f"Missing raw file: {parquet_path}", file=sys.stderr)
        print("Run scripts/download_lade_p_jilin.py first. No substitute data will be generated.", file=sys.stderr)
        return 1
    if not manifest_path().is_file():
        print(f"Missing manifest: {manifest_path()}", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
    file_record = next(item for item in manifest["files"] if item["role"] == "jilin_pickup_partition")
    digest = sha256_file(parquet_path)
    if digest != file_record["sha256"] or not file_record["checksum_matches_published_lfs_oid"]:
        print("Raw file checksum does not match a verified manifest. Analysis stopped.", file=sys.stderr)
        return 1

    print("Arrow schema before processing:")
    frame, schema_report = load_raw_frame(parquet_path)
    for column in schema_report["columns"]:
        print(f"  {column['name']}: {column['type']} nullable={column['nullable']}")
    print(f"Rows in parquet metadata: {schema_report['num_rows']}")

    prepared = prepare_observations(frame)
    summary, duties, daily = build_summary(prepared, list(REQUIRED_COLUMNS))
    summary["schema"] = schema_report
    summary["source_sha256"] = digest
    summary["source_revision"] = manifest["revision"]
    summary["generated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    summary["runtime"] = {
        "python": platform.python_version(),
        "pandas": version("pandas"),
        "pyarrow": version("pyarrow"),
        "numpy": version("numpy"),
        "matplotlib": version("matplotlib"),
    }

    processed_dir().mkdir(parents=True, exist_ok=True)
    figure_dir().mkdir(parents=True, exist_ok=True)
    daily.to_parquet(processed_dir() / "daily_task_counts.parquet", index=False)
    duties.to_parquet(processed_dir() / "courier_day_summary.parquet", index=False)
    audit_path = processed_dir() / "audit_summary.json"
    audit_path.write_text(json.dumps(_jsonable(summary), indent=2), encoding="utf-8")

    figure_daily_volumes(daily, figure_dir() / "fig1_daily_pickup_volumes")
    figure_tasks_per_duty(duties, figure_dir() / "fig2_tasks_per_courier_day")
    figure_geography(prepared, figure_dir() / "fig3_geographic_distribution")
    figure_time_windows(prepared, figure_dir() / "fig4_time_windows")
    figure_event_times(prepared, figure_dir() / "fig5_acceptance_and_completion")

    print(f"Tasks: {summary['n_rows']}")
    print(f"Couriers: {summary['n_couriers']}")
    print(f"Business dates: {summary['n_dates_with_tasks']}")
    print(f"Courier-days: {summary['duties']['n_courier_days']}")
    print(f"Wrote {audit_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
