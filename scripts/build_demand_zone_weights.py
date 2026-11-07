"""Freeze immutable demand spatial weights from documented population sources.

Measured HCP population is used only for zones that are both:
  - geography_status == verified_admin in the pinned zone crosswalk, and
  - matched in hcp_population_measured_only.csv

Approximate / unmatched zones contribute commercial weight only (population term 0)
and are never silently filled with incompatible HCP or workbook census numbers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from race_casablanca.hashing import sha256_file
from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.paths import candidates_dir, config_dir, manifest_dir, traffic_dir, zones_dir


def _require_newer(derived: Path, source: Path, label: str) -> None:
    if not derived.exists():
        raise SystemExit(f"Missing {label}: {derived}")
    if not source.exists():
        raise SystemExit(f"Missing source for {label}: {source}")
    if derived.stat().st_mtime + 1.0 < source.stat().st_mtime:
        raise SystemExit(
            f"Stale input for demand weights: {derived} is older than {source}. Rebuild candidates/network first."
        )


def main() -> int:
    config = yaml.safe_load((config_dir() / "demand_default.yaml").read_text(encoding="utf-8"))
    alpha = float(config["spatial"]["population_weight"])
    beta = float(config["spatial"]["commercial_weight"])
    gen_ver = str(config["generator_version"])

    candidates_path = candidates_dir() / "pickup_candidates.csv"
    boundary_path = zones_dir() / "study_boundary.gpkg"
    _require_newer(candidates_path, boundary_path, "pickup_candidates vs boundary")

    workbook = pd.read_csv(traffic_dir() / "communes_workbook.csv")
    if workbook.empty:
        workbook = pd.read_csv(traffic_dir() / "communes.csv")
    land = pd.read_csv(traffic_dir() / "land_use.csv")
    hcp = pd.read_csv(zones_dir() / "hcp_population_measured_only.csv")
    crosswalk = pd.read_csv(zones_dir() / "zone_crosswalk.csv")
    candidates = pd.read_csv(candidates_path)

    commercial_cols = [c for c in land.columns if "commercial" in c.lower()]
    if not commercial_cols:
        raise SystemExit("land_use.csv missing commercial-buildings column")
    com_col = commercial_cols[0]

    rows = []
    for _, wb in workbook.iterrows():
        commune = str(wb["commune"])
        zip_code = str(wb["zip_code"])
        cw = crosswalk[crosswalk["workbook_commune"] == commune]
        geo = str(cw.iloc[0]["geography_status"]) if not cw.empty else "unresolved"
        h = hcp[(hcp["commune"] == commune) & (hcp["zip_code"].astype(str) == zip_code)]
        hcp_matched = bool(h.iloc[0]["matched"]) if not h.empty and pd.notna(h.iloc[0].get("matched")) else False
        hcp_pop = float(h.iloc[0]["population"]) if hcp_matched and pd.notna(h.iloc[0].get("population")) else np.nan
        hcp_name = h.iloc[0]["hcp_name"] if hcp_matched else None
        land_row = land[(land["commune"] == commune) & (land["zip_code"].astype(str) == zip_code)]
        commercial = float(land_row.iloc[0][com_col]) if not land_row.empty else 0.0

        use_hcp = geo == "verified_admin" and hcp_matched and np.isfinite(hcp_pop)
        if use_hcp:
            population = float(hcp_pop)
            population_source = "hcp_rgph2024_measured_verified_admin"
            evidence = f"HCP unit '{hcp_name}' + verified_admin crosswalk"
        else:
            population = 0.0
            if geo != "verified_admin":
                population_source = "excluded_approximate_or_unresolved_geography"
                evidence = (
                    f"geography_status={geo}; HCP not applied to avoid incompatible admin coverage. "
                    "Zone weight uses commercial term only."
                )
            elif not hcp_matched:
                population_source = "excluded_no_hcp_name_match"
                evidence = "verified_admin geometry but no measured HCP name match; commercial-only weight"
            else:
                population_source = "excluded_other"
                evidence = "population excluded from measured term"

        n_access = int(
            (
                (candidates["commune"] == commune)
                & (candidates["accessible"] == True)  # noqa: E712
            ).sum()
        )
        rows.append(
            {
                "zone_id": commune,
                "commune": commune,
                "zip_code": zip_code,
                "geography_status": geo,
                "population": population,
                "population_source": population_source,
                "hcp_name": hcp_name,
                "workbook_population_mendeley": float(wb["population"]),
                "commercial_buildings": commercial,
                "n_accessible_candidates": n_access,
                "eligible_for_sampling": n_access > 0,
                "evidence": evidence,
            }
        )

    frame = pd.DataFrame(rows)
    pop = frame["population"].astype(float)
    com = frame["commercial_buildings"].astype(float)
    pop_sum = float(pop.sum())
    com_sum = float(com.sum())
    frame["pop_w"] = (pop / pop_sum) if pop_sum > 0 else 0.0
    frame["com_w"] = (com / com_sum) if com_sum > 0 else (1.0 / len(frame))
    raw = alpha * frame["pop_w"] + beta * frame["com_w"]
    # Zero out zones with no accessible pickup locations, then renormalize.
    raw = raw.where(frame["eligible_for_sampling"], 0.0)
    if float(raw.sum()) <= 0:
        raise SystemExit("No eligible zones with accessible candidates for demand weights")
    frame["zone_weight"] = raw / raw.sum()
    frame["population_weight_alpha"] = alpha
    frame["commercial_weight_beta"] = beta
    frame["generator_version"] = gen_ver
    frame["benchmark_version"] = str(config.get("benchmark_version", "casablanca_release_v1"))

    # Validate invariants.
    assert frame["zone_id"].is_unique
    assert (frame["zone_weight"] >= -1e-15).all()
    assert abs(float(frame["zone_weight"].sum()) - 1.0) < 1e-9
    assert frame.loc[frame["eligible_for_sampling"], "zone_weight"].sum() > 0.99

    out = zones_dir() / "demand_zone_weights.csv"
    frame.to_csv(out, index=False, lineterminator="\n")
    digest = sha256_file(out)
    summary = {
        "generated_at_utc": utc_now(),
        "path": "data/casablanca/zones/demand_zone_weights.csv",
        "sha256": digest,
        "n_zones": int(len(frame)),
        "n_measured_hcp_population": int((frame["population_source"] == "hcp_rgph2024_measured_verified_admin").sum()),
        "n_commercial_only": int(frame["population_source"].str.startswith("excluded").sum()),
        "n_eligible_sampling": int(frame["eligible_for_sampling"].sum()),
        "population_weight_alpha": alpha,
        "commercial_weight_beta": beta,
        "generator_version": gen_ver,
        "benchmark_version": str(config.get("benchmark_version", "casablanca_release_v1")),
        "claim": (
            "Demand spatial weights freeze measured HCP population only for verified_admin "
            "zones with HCP name matches. Approximate zones are commercial-only. "
            "Generator must read this file exclusively."
        ),
    }
    write_json(manifest_dir() / "demand_zone_weights_manifest.json", summary)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
