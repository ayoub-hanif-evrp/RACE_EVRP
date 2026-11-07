"""Diagnose workbook TTI vs OSM free-flow baseline mismatch (Mon–Sat only)."""

from __future__ import annotations

import sys

import numpy as np
import osmnx as ox
import pandas as pd

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.travel_time import TTI_REFERENCE_SPEED_KMH, earliest_arrival
from race_casablanca.paths import manifest_dir, report_dir, roads_dir, traffic_dir
from race_casablanca.traffic.profiles import build_tti_profiles


def main() -> int:
    traj = pd.read_parquet(traffic_dir() / "trajectory_hours.parquet")
    fit_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    train = traj[traj["day"].isin(fit_days)].dropna(
        subset=["travel_time_min", "distance_m", "tti"]
    ).copy()
    train = train[(train["travel_time_min"] > 0) & (train["distance_m"] > 0) & (train["tti"] > 0)]
    train["ff_speed_kmh"] = (train["distance_m"] / 1000.0) / (
        (train["travel_time_min"] / train["tti"]) / 60.0
    )
    train["pred_a_min"] = train["tti"] * (train["distance_m"] / 1000.0) / TTI_REFERENCE_SPEED_KMH * 60.0
    # Formulation B uses a fixed urban OSM-like fallback (30 km/h) on workbook distance.
    osm_like = 30.0
    train["pred_b_min"] = train["tti"] * (train["distance_m"] / 1000.0) / osm_like * 60.0
    train["err_a"] = train["pred_a_min"] - train["travel_time_min"]
    train["err_b"] = train["pred_b_min"] - train["travel_time_min"]

    profiles = build_tti_profiles(traj, exclude_days=["Sunday"])
    city = profiles["citywide_hour"]
    model_city = pd.Series(city["tti_factor"].to_numpy(), index=city["hour"].astype(int))

    # Path-level ratio on a Mon–Sat sample (no Sunday).
    sample = train.sample(n=min(80, len(train)), random_state=7)
    graph = ox.load_graphml(roads_dir() / "casablanca_drive.graphml")
    from race_casablanca.network.travel_time import CongestionModel, edge_tti_baseline_free_flow_s

    model = CongestionModel(citywide_hour=model_city)
    ratios = []
    for _, r in sample.iterrows():
        try:
            o = ox.distance.nearest_nodes(graph, float(r["origin_lon"]), float(r["origin_lat"]))
            d = ox.distance.nearest_nodes(graph, float(r["dest_lon"]), float(r["dest_lat"]))
            if o == d:
                continue
            dep = float(r["hour"]) * 3600.0
            pred_s, path, legs = earliest_arrival(graph, o, d, dep, model, day=None)
            path_m = sum(float(leg["length_m"]) for leg in legs)
            tti = float(model.factor(int(r["hour"])))
            baseline_path_s = (path_m * 3.6 / TTI_REFERENCE_SPEED_KMH) * tti
            # Compare against OSM-class free-flow × TTI on same path.
            osm_ff = 0.0
            for leg in legs:
                osm_ff += float(leg.get("osm_free_flow_time_s") or 0.0)
            osm_pred_s = osm_ff * tti
            if baseline_path_s > 0:
                ratios.append(
                    {
                        "pred_tti60_s": pred_s,
                        "baseline_closed_s": baseline_path_s,
                        "osm_x_tti_s": osm_pred_s,
                        "ratio_osm_over_tti60": osm_pred_s / max(pred_s, 1e-9),
                        "obs_s": float(r["travel_time_min"]) * 60.0,
                    }
                )
        except Exception:  # noqa: BLE001
            continue

    ratio_df = pd.DataFrame(ratios)
    summary = {
        "generated_at_utc": utc_now(),
        "fit_days": fit_days,
        "tti_reference_speed_kmh": TTI_REFERENCE_SPEED_KMH,
        "workbook_free_flow": {
            "n_rows": int(len(train)),
            "median_ff_speed_kmh": float(train["ff_speed_kmh"].median()),
            "mean_ff_speed_kmh": float(train["ff_speed_kmh"].mean()),
            "p10_ff_speed_kmh": float(train["ff_speed_kmh"].quantile(0.1)),
            "p90_ff_speed_kmh": float(train["ff_speed_kmh"].quantile(0.9)),
        },
        "closed_form_mon_sat": {
            "A_tti_times_d_over_60": {
                "mae_min": float((train["err_a"].abs()).mean()),
                "signed_bias_min": float(train["err_a"].mean()),
                "median_signed_bias_min": float(train["err_a"].median()),
            },
            "B_tti_times_d_over_30_osm_like": {
                "mae_min": float((train["err_b"].abs()).mean()),
                "signed_bias_min": float(train["err_b"].mean()),
                "median_signed_bias_min": float(train["err_b"].median()),
            },
            "interpretation": (
                "If A tracks observations and B is systematically long, workbook TTI "
                "is relative to ~60 km/h and must not be multiplied onto slower OSM free-flow."
            ),
        },
        "path_sample": {
            "n": int(len(ratio_df)),
            "median_ratio_osm_over_tti60": (
                float(ratio_df["ratio_osm_over_tti60"].median()) if not ratio_df.empty else None
            ),
            "median_signed_bias_tti60_min": (
                float(((ratio_df["pred_tti60_s"] - ratio_df["obs_s"]) / 60.0).median())
                if not ratio_df.empty
                else None
            ),
            "median_signed_bias_osm_x_tti_min": (
                float(((ratio_df["osm_x_tti_s"] - ratio_df["obs_s"]) / 60.0).median())
                if not ratio_df.empty
                else None
            ),
        },
        "decision": (
            "Adopt t = (3.6 * length_m / 60) * TTI for congested travel times; "
            "retain OSM topology/routing and documented class speeds for provenance only."
        ),
    }
    write_json(manifest_dir() / "tti_baseline_diagnosis.json", summary)

    md = report_dir() / "TTI_BASELINE_DIAGNOSIS.md"
    md.write_text(
        "# TTI baseline diagnosis (Mon–Sat only)\n\n"
        "Sunday held out from this diagnosis; no holdout tuning.\n\n"
        f"```json\n{__import__('json').dumps(summary, indent=2)}\n```\n",
        encoding="utf-8",
    )
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
