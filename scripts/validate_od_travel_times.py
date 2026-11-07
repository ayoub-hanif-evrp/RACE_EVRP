"""Compare modeled OSM travel times against genuinely held-out Sunday Waze OD times."""

from __future__ import annotations

import sys

import numpy as np
import osmnx as ox
import pandas as pd

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.travel_time import CongestionModel, earliest_arrival
from race_casablanca.paths import figure_dir, manifest_dir, roads_dir, traffic_dir
from race_casablanca.traffic.profiles import build_tti_profiles


def main() -> int:
    traj = pd.read_parquet(traffic_dir() / "trajectory_hours.parquet")
    holdout_day = "Sunday"
    # Genuine holdout: fit congestion on Mon–Sat only.
    fit_profiles = build_tti_profiles(traj, exclude_days=[holdout_day])
    fit_city = fit_profiles["citywide_hour"]
    fit_city.to_csv(traffic_dir() / "tti_citywide_hour_fit_mon_sat.csv", index=False)
    fit_profiles["zone_day_hour"].to_csv(traffic_dir() / "tti_zone_day_hour_fit_mon_sat.csv", index=False)

    hold = traj[traj["day"] == holdout_day].copy()
    hold["travel_time_s"] = hold["travel_time_min"].astype(float) * 60.0
    grouped = hold.groupby(["origin_lat", "origin_lon", "dest_lat", "dest_lon", "hour"], as_index=False).agg(
        travel_time_s=("travel_time_s", "median"),
        tti=("tti", "median"),
        distance_m=("distance_m", "median"),
    )
    sample = grouped.sample(n=min(120, len(grouped)), random_state=42) if len(grouped) else grouped
    if sample.empty:
        raise SystemExit(f"No holdout rows. Columns={list(hold.columns)}")

    graph = ox.load_graphml(roads_dir() / "casablanca_drive.graphml")
    model = CongestionModel(
        citywide_hour=pd.Series(fit_city["tti_factor"].to_numpy(), index=fit_city["hour"].astype(int))
    )

    rows = []
    snap_failures = 0
    collapsed = 0
    for _, r in sample.iterrows():
        try:
            o = ox.distance.nearest_nodes(graph, float(r["origin_lon"]), float(r["origin_lat"]))
            d = ox.distance.nearest_nodes(graph, float(r["dest_lon"]), float(r["dest_lat"]))
        except Exception:  # noqa: BLE001
            snap_failures += 1
            continue
        if o == d:
            collapsed += 1
            rows.append(
                {
                    "hour": int(r["hour"]),
                    "observed_s": float(r["travel_time_s"]),
                    "predicted_s": np.nan,
                    "abs_error_s": np.nan,
                    "abs_error_min": np.nan,
                    "rel_error": np.nan,
                    "path_nodes": 1,
                    "o_node": int(o),
                    "d_node": int(d),
                    "status": "collapsed_same_node",
                    "distance_m": float(r["distance_m"]),
                }
            )
            continue
        try:
            dep = float(r["hour"]) * 3600.0
            pred_s, path, _legs = earliest_arrival(graph, o, d, dep, model, day=None)
            obs_s = float(r["travel_time_s"])
            rows.append(
                {
                    "hour": int(r["hour"]),
                    "observed_s": obs_s,
                    "predicted_s": pred_s,
                    "abs_error_s": abs(pred_s - obs_s),
                    "abs_error_min": abs(pred_s - obs_s) / 60.0,
                    "rel_error": abs(pred_s - obs_s) / max(obs_s, 1.0),
                    "path_nodes": len(path),
                    "o_node": int(o),
                    "d_node": int(d),
                    "status": "ok",
                    "distance_m": float(r["distance_m"]),
                    "implied_obs_kmh": (float(r["distance_m"]) / 1000.0) / (obs_s / 3600.0) if obs_s > 0 else np.nan,
                    "implied_pred_kmh": (float(r["distance_m"]) / 1000.0) / (pred_s / 3600.0) if pred_s > 0 else np.nan,
                }
            )
        except Exception:  # noqa: BLE001
            snap_failures += 1

    out = pd.DataFrame(rows)
    out_path = traffic_dir() / "od_travel_time_holdout_sunday.csv"
    out.to_csv(out_path, index=False)

    ok = out[out["status"] == "ok"].copy() if "status" in out.columns else out
    if ok.empty:
        summary = {
            "generated_at_utc": utc_now(),
            "status": "failed",
            "reason": "no_successful_od_predictions",
            "n_snap_failures": snap_failures,
            "n_collapsed_same_node": collapsed,
        }
        write_json(manifest_dir() / "od_travel_time_validation.json", summary)
        print(summary)
        return 1

    peak = ok[ok["hour"].between(7, 10)]
    summary = {
        "generated_at_utc": utc_now(),
        "status": "ok",
        "holdout_day": holdout_day,
        "fit_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        "congestion_profile": "tti_citywide_hour_fit_mon_sat.csv",
        "unit_note": (
            "Observed times from workbook minutes after correcting Excel milli-minute "
            "artifacts (values>180 divided by 1000, not 60)."
        ),
        "n_sampled": int(len(sample)),
        "n_compared": int(len(ok)),
        "n_snap_failures": int(snap_failures),
        "n_collapsed_same_node": int(collapsed),
        "mae_min": float(ok["abs_error_min"].mean()),
        "rmse_min": float(np.sqrt((ok["abs_error_min"] ** 2).mean())),
        "median_abs_error_min": float(ok["abs_error_min"].median()),
        "mean_rel_error": float(ok["rel_error"].mean()),
        "peak_7_10_mae_min": float(peak["abs_error_min"].mean()) if not peak.empty else None,
        "median_obs_min": float((ok["observed_s"] / 60.0).median()),
        "median_pred_min": float((ok["predicted_s"] / 60.0).median()),
        "claim": (
            "Sunday OD durations predicted with Mon–Sat-only citywide TTI. "
            "Does not claim edge calibration or identical Waze/OSM routes."
        ),
        "output": str(out_path),
    }
    write_json(manifest_dir() / "od_travel_time_validation.json", summary)

    import matplotlib.pyplot as plt

    figure_dir().mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5.5, 5.0))
    ax.scatter(ok["observed_s"] / 60.0, ok["predicted_s"] / 60.0, s=18, alpha=0.7, c="#1f4e79")
    lim = max(ok["observed_s"].max(), ok["predicted_s"].max()) / 60.0
    ax.plot([0, lim], [0, lim], color="#922b21", linewidth=1.0)
    ax.set_xlabel("Waze observed travel time (min)")
    ax.set_ylabel("Modeled OSM travel time (min)")
    ax.set_title(f"Held-out {holdout_day} OD travel times (fit Mon–Sat)")
    fig.savefig(figure_dir() / "casablanca_od_travel_time_holdout.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
