"""Compare modeled OSM travel times against held-out Waze OD route times."""

from __future__ import annotations

import sys

import numpy as np
import osmnx as ox
import pandas as pd

from race_casablanca.io_utils import utc_now, write_json
from race_casablanca.network.travel_time import CongestionModel, earliest_arrival
from race_casablanca.paths import figure_dir, manifest_dir, roads_dir, traffic_dir


def main() -> int:
    traj = pd.read_parquet(traffic_dir() / "trajectory_hours.parquet")
    # Hold out one day entirely for OD travel-time comparison.
    holdout_day = "Sunday"
    hold = traj[traj["day"] == holdout_day].copy()
    # Unique OD endpoints sampled; use a bounded subset for runtime.
    hold = hold.copy()
    hold["travel_time_s"] = hold["travel_time_min"].astype(float) * 60.0
    grouped = hold.groupby(["origin_lat", "origin_lon", "dest_lat", "dest_lon", "hour"], as_index=False).agg(
        travel_time_s=("travel_time_s", "median"),
        tti=("tti", "median"),
    )
    sample = grouped.sample(n=min(80, len(grouped)), random_state=42) if len(grouped) else grouped
    if sample.empty:
        raise SystemExit(f"No holdout rows. Columns={list(hold.columns)}")

    graph = ox.load_graphml(roads_dir() / "casablanca_drive.graphml")
    city = pd.read_csv(traffic_dir() / "tti_citywide_hour.csv")
    model = CongestionModel(citywide_hour=pd.Series(city["tti_factor"].to_numpy(), index=city["hour"].astype(int)))

    rows = []
    failures = 0
    for _, r in sample.iterrows():
        try:
            o = ox.distance.nearest_nodes(graph, float(r["origin_lon"]), float(r["origin_lat"]))
            d = ox.distance.nearest_nodes(graph, float(r["dest_lon"]), float(r["dest_lat"]))
            dep = float(r["hour"]) * 3600.0
            pred_s, path, _legs = earliest_arrival(graph, o, d, dep, model, day=holdout_day)
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
                }
            )
        except Exception:  # noqa: BLE001
            failures += 1

    out = pd.DataFrame(rows)
    traffic_dir().mkdir(parents=True, exist_ok=True)
    out_path = traffic_dir() / "od_travel_time_holdout_sunday.csv"
    out.to_csv(out_path, index=False)

    if out.empty:
        summary = {
            "generated_at_utc": utc_now(),
            "status": "failed",
            "reason": "no_successful_od_predictions",
            "failures": failures,
        }
        write_json(manifest_dir() / "od_travel_time_validation.json", summary)
        print(summary)
        return 1

    peak = out[out["hour"].between(7, 10)]
    summary = {
        "generated_at_utc": utc_now(),
        "status": "ok",
        "holdout_day": holdout_day,
        "n_compared": int(len(out)),
        "n_failures": int(failures),
        "mae_min": float(out["abs_error_min"].mean()),
        "rmse_min": float(np.sqrt((out["abs_error_min"] ** 2).mean())),
        "median_abs_error_min": float(out["abs_error_min"].median()),
        "mean_rel_error": float(out["rel_error"].mean()),
        "peak_7_10_mae_min": float(peak["abs_error_min"].mean()) if not peak.empty else None,
        "claim": (
            "Compares modeled OSM earliest-arrival times to Waze-reported OD durations. "
            "Does not claim identical physical routes or edge-level traffic calibration."
        ),
        "output": str(out_path),
    }
    write_json(manifest_dir() / "od_travel_time_validation.json", summary)

    # Simple residual figure.
    import matplotlib.pyplot as plt

    figure_dir().mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5.5, 5.0))
    ax.scatter(out["observed_s"] / 60.0, out["predicted_s"] / 60.0, s=18, alpha=0.7, c="#1f4e79")
    lim = max(out["observed_s"].max(), out["predicted_s"].max()) / 60.0
    ax.plot([0, lim], [0, lim], color="#922b21", linewidth=1.0)
    ax.set_xlabel("Waze observed travel time (min)")
    ax.set_ylabel("Modeled OSM travel time (min)")
    ax.set_title(f"Held-out {holdout_day} OD travel-time comparison")
    fig.savefig(figure_dir() / "casablanca_od_travel_time_holdout.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
