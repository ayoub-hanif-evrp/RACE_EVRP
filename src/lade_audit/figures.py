"""Publication figures drawn from the audited Jilin frame."""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MaxNLocator

INK = "#1c2833"
BLUE = "#1f4e79"
AMBER = "#b86e00"
GRID = "#d5d8dc"


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "text.color": INK,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.4,
            "axes.axisbelow": True,
            "legend.frameon": False,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def _save(figure: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path.with_suffix(".png"), dpi=300, bbox_inches="tight")
    figure.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(figure)


def figure_daily_volumes(daily: pd.DataFrame, path: Path) -> None:
    _style()
    observed = daily.dropna(subset=["ds_date"]).copy()
    observed["ds_date"] = pd.to_datetime(observed["ds_date"])
    span = pd.date_range(observed["ds_date"].min(), observed["ds_date"].max(), freq="D")
    series = observed.set_index("ds_date")["n_tasks"].reindex(span, fill_value=0)
    figure, axis = plt.subplots(figsize=(7.4, 3.6))
    axis.plot(series.index, series.to_numpy(), color=BLUE, linewidth=1.0)
    axis.fill_between(series.index, series.to_numpy(), color=BLUE, alpha=0.12, linewidth=0)
    axis.set_title("Daily pickup tasks in the Jilin partition")
    axis.set_ylabel("Tasks")
    axis.set_xlabel("Month and day stored in ds (the file does not contain a year)")
    axis.yaxis.set_major_locator(MaxNLocator(integer=True))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    axis.xaxis.set_major_locator(mdates.MonthLocator())
    axis.set_xlim(series.index.min(), series.index.max())
    figure.autofmt_xdate(rotation=0, ha="center")
    _save(figure, path)


def figure_tasks_per_duty(duties: pd.DataFrame, path: Path) -> None:
    _style()
    counts = duties["n_tasks"].to_numpy()
    cap = int(np.quantile(counts, 0.99))
    bins = np.arange(0.5, max(cap, 1) + 1.5, 1.0)
    figure, axis = plt.subplots(figsize=(7.2, 3.8))
    axis.hist(counts, bins=bins, color=BLUE, edgecolor="white", linewidth=0.3)
    median = float(np.median(counts))
    axis.axvline(median, color=AMBER, linewidth=1.2, label=f"Median {median:.0f}")
    axis.set_xlim(0.5, cap + 0.5)
    axis.set_title("Tasks per courier per business day")
    axis.set_xlabel("Tasks in one courier-day")
    axis.set_ylabel("Courier-days")
    axis.legend(loc="upper right")
    axis.text(
        0.98,
        0.72,
        f"Maximum {int(counts.max())}\nAxis capped at the 99th percentile ({cap})",
        transform=axis.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        color=INK,
    )
    _save(figure, path)


def figure_geography(frame: pd.DataFrame, path: Path) -> None:
    _style()
    valid = frame.loc[frame["package_lng_valid"], ["lng", "lat"]]
    lng = valid["lng"].to_numpy(dtype="float64")
    lat = valid["lat"].to_numpy(dtype="float64")
    x_lo, x_hi = np.quantile(lng, [0.005, 0.995])
    y_lo, y_hi = np.quantile(lat, [0.005, 0.995])
    figure, axis = plt.subplots(figsize=(6.4, 5.6))
    hexbin = axis.hexbin(
        lng,
        lat,
        gridsize=45,
        extent=(x_lo, x_hi, y_lo, y_hi),
        cmap="cividis",
        mincnt=1,
        linewidths=0,
    )
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlim(x_lo, x_hi)
    axis.set_ylim(y_lo, y_hi)
    axis.set_title("Pickup-stop locations, Jilin partition")
    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")
    colorbar = figure.colorbar(hexbin, ax=axis, fraction=0.046, pad=0.04)
    colorbar.set_label("Tasks per cell")
    figure.tight_layout()
    figure.text(
        0.01,
        0.01,
        "Window is the central 99 percent of longitude and latitude. "
        "Two stops east of longitude 128 fall outside it. Cells are map bins.",
        fontsize=8,
        color=INK,
    )
    figure.subplots_adjust(bottom=0.16)
    _save(figure, path)


def figure_time_windows(frame: pd.DataFrame, path: Path) -> None:
    _style()
    duration_h = frame["window_minutes"].dropna() / 60.0
    start_hour = frame["window_start_hour"].dropna().to_numpy()
    figure, axes = plt.subplots(1, 2, figsize=(7.6, 3.6))
    cap = float(np.quantile(duration_h, 0.99)) if len(duration_h) else 1.0
    axes[0].hist(
        duration_h.to_numpy(),
        bins=30,
        range=(0.0, cap),
        color=BLUE,
        edgecolor="white",
        linewidth=0.3,
    )
    axes[0].set_title("Promised window length")
    axes[0].set_xlabel("Hours from window start to window end")
    axes[0].set_ylabel("Tasks")
    axes[1].hist(
        start_hour,
        bins=np.arange(-0.5, 24.5, 1.0),
        color=BLUE,
        edgecolor="white",
        linewidth=0.3,
    )
    axes[1].set_title("Hour of window start")
    axes[1].set_xlabel("Hour of day")
    axes[1].set_ylabel("Tasks")
    axes[1].set_xlim(-0.5, 23.5)
    figure.tight_layout()
    _save(figure, path)


def figure_event_times(frame: pd.DataFrame, path: Path) -> None:
    _style()
    accept_hour = frame["accept_hour"].dropna().to_numpy()
    pickup_hour = frame["pickup_hour"].dropna().to_numpy()
    delay = frame["accept_to_pickup_minutes"].dropna()
    delay = delay[delay >= 0]
    figure, axes = plt.subplots(1, 2, figsize=(7.6, 3.6))
    bins = np.arange(-0.5, 24.5, 1.0)
    axes[0].hist(
        accept_hour,
        bins=bins,
        histtype="step",
        linewidth=1.6,
        color=BLUE,
        label="Acceptance",
    )
    axes[0].hist(
        pickup_hour,
        bins=bins,
        histtype="step",
        linewidth=1.6,
        color=AMBER,
        label="Pickup completion",
    )
    axes[0].set_xlim(-0.5, 23.5)
    axes[0].set_title("Clock time of observed events")
    axes[0].set_xlabel("Hour of day")
    axes[0].set_ylabel("Tasks")
    axes[0].legend(loc="upper right")
    cap = float(np.quantile(delay, 0.99)) if len(delay) else 1.0
    axes[1].hist(
        delay.to_numpy(),
        bins=40,
        range=(0.0, cap),
        color="#3d5a40",
        edgecolor="white",
        linewidth=0.2,
    )
    median_delay = float(np.median(delay)) if len(delay) else 0.0
    axes[1].axvline(median_delay, color=AMBER, linewidth=1.2, label=f"Median {median_delay:.0f} min")
    axes[1].set_title("Acceptance to pickup completion")
    axes[1].set_xlabel("Minutes (axis ends at the 99th percentile)")
    axes[1].set_ylabel("Tasks")
    axes[1].legend(loc="upper right")
    figure.tight_layout()
    _save(figure, path)
