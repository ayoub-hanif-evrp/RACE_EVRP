#!/usr/bin/env python
"""Build realistic OSM building/POI pickup frame (excludes generic building=yes)."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from race_casablanca.demand.realistic_frame import (
    filter_realistic_pickup_candidates,
    realism_summary,
)
from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import candidates_dir, manifest_dir, project_root


def main() -> int:
    src = candidates_dir() / "pickup_candidates.csv"
    raw = pd.read_csv(src)
    filt = filter_realistic_pickup_candidates(raw)
    out = candidates_dir() / "pickup_candidates_realistic.csv"
    filt.to_csv(out, index=False, lineterminator="\n")
    summary = {
        "generated_at_utc": utc_now(),
        "source": str(src.relative_to(project_root())).replace("\\", "/"),
        "source_sha256": sha256_file(src),
        "output": str(out.relative_to(project_root())).replace("\\", "/"),
        "output_sha256": sha256_file(out),
        **realism_summary(raw, filt),
        "top_categories": filt["category"].value_counts().head(20).to_dict(),
        "claim": (
            "Realistic sampling frame = typed OSM buildings + shops/offices/amenities. "
            "Customer lat/lon = OSM feature point/centroid. snap_node = routing access only. "
            "Not random map projections. Not observed courier addresses."
        ),
    }
    write_json(manifest_dir() / "pickup_candidates_realistic_manifest.json", summary)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
