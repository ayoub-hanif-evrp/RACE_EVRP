#!/usr/bin/env python
"""Stage 6 credibility checks: request fields, release vs eval inventory, witness notes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.paths import project_root


def check_requests(root: Path) -> dict:
    n = 0
    missing_snap = 0
    missing_zone = 0
    claimed_observed = 0
    for csv in root.rglob("requests.csv"):
        df = pd.read_csv(csv)
        n += len(df)
        if "snap_node" in df.columns:
            missing_snap += int(df["snap_node"].isna().sum())
        else:
            missing_snap += len(df)
        zone_col = next((c for c in ("declared_zone_id", "zone_id", "commune") if c in df.columns), None)
        if zone_col:
            missing_zone += int(df[zone_col].isna().sum())
        else:
            missing_zone += len(df)
        if "is_observed_order" in df.columns:
            claimed_observed += int(df["is_observed_order"].astype(str).str.lower().isin(["true", "1"]).sum())
    return {
        "n_requests": n,
        "missing_snap_node": missing_snap,
        "missing_zone_field": missing_zone,
        "claimed_observed_orders": claimed_observed,
    }


def main() -> int:
    cas = project_root() / "data" / "casablanca"
    out = {
        "release_scenarios": check_requests(cas / "scenarios"),
        "evaluation_v1_default": check_requests(cas / "evaluation_v1" / "default"),
        "historical_artifacts": {
            "constraint_binding_diagnosis.json": "HISTORICAL — do not use as active release authority",
            "CONSTRAINT_BINDING_DIAGNOSIS.md": "HISTORICAL report",
        },
        "notes": [
            "Traffic workbook rows are congestion OD observations, not courier orders.",
            "OSM candidates are sampling-frame locations, not observed customers.",
            "Eval_v1 expands synthetic episodes only; locked seeds 2100–2399 unused.",
        ],
    }
    man = cas / "manifests" / "casablanca_dataset_manifest.json"
    if man.exists():
        j = json.loads(man.read_text(encoding="utf-8"))
        out["release_manifest_keys"] = sorted(j.keys())[:30]
        out["n_scenarios_in_manifest"] = len(j.get("scenarios", j.get("scenario_ids", [])) or [])
    dest = cas / "online_results" / "stage6_credibility_checks.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    print(f"Wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
