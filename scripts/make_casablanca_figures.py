"""Publication figures for the Casablanca Stage-1 benchmark."""

from __future__ import annotations

import sys

import geopandas as gpd
import matplotlib.pyplot as plt
import osmnx as ox
import pandas as pd

from race_casablanca.paths import figure_dir, roads_dir, traffic_dir, zones_dir

INK = "#1c2833"
BLUE = "#1f4e79"


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "text.color": INK,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
        }
    )


def main() -> int:
    _style()
    figure_dir().mkdir(parents=True, exist_ok=True)

    # Congestion by hour from real workbook-derived citywide profile.
    profile = pd.read_csv(traffic_dir() / "tti_citywide_hour.csv")
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    ax.plot(profile["hour"], profile["tti_factor"], color=BLUE, linewidth=1.8)
    ax.fill_between(profile["hour"], profile["tti_factor"], color=BLUE, alpha=0.12)
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Median Travel Time Index")
    ax.set_title("Casablanca congestion by hour (Waze-derived TTI)")
    ax.set_xlim(0, 23)
    fig.savefig(figure_dir() / "casablanca_congestion_by_hour.png", dpi=300, bbox_inches="tight")
    fig.savefig(figure_dir() / "casablanca_congestion_by_hour.pdf", bbox_inches="tight")
    plt.close(fig)

    # Road network map.
    graph = ox.load_graphml(roads_dir() / "casablanca_drive.graphml")
    boundary = gpd.read_file(zones_dir() / "study_boundary.gpkg", layer="boundary")
    fig, ax = plt.subplots(figsize=(7.0, 7.0))
    ox.plot_graph(graph, ax=ax, node_size=0, edge_color="#5d6d7e", edge_linewidth=0.25, show=False, close=False)
    boundary.boundary.plot(ax=ax, color=BLUE, linewidth=1.2)
    ax.set_title("Casablanca study-area drive network (OSM)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    fig.savefig(figure_dir() / "casablanca_road_network.png", dpi=300, bbox_inches="tight")
    fig.savefig(figure_dir() / "casablanca_road_network.pdf", bbox_inches="tight")
    plt.close(fig)
    print("Wrote congestion and network figures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
