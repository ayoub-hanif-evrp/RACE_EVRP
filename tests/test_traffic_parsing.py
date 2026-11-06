from pathlib import Path

import pandas as pd

from race_casablanca.paths import project_root
from race_casablanca.traffic.profiles import fifo_check_piecewise_constant
from race_casablanca.traffic.workbook import load_all_trajectories, load_communes


def _workbook() -> Path:
    path = project_root() / "data/casablanca/raw/traffic/Dataset for traffic analysis in Casablanca, Morocco.xlsx"
    assert path.is_file(), "Run scripts/download_casablanca_traffic.py first"
    return path


def test_communes_count():
    communes = load_communes(_workbook())
    assert len(communes) == 22


def test_trajectory_hours_cover_week_and_day():
    traj = load_all_trajectories(_workbook())
    assert set(traj["day"]) >= {"Monday", "Sunday"}
    assert traj["hour"].min() == 0
    assert traj["hour"].max() == 23
    assert traj[["origin_lat", "dest_lon"]].notna().all(axis=None)
    assert len(traj) > 50_000


def test_fifo_helper_reports_downward_jumps():
    series = pd.Series({h: 2.0 for h in range(24)})
    series[8] = 1.0
    result = fifo_check_piecewise_constant(series)
    assert result["n_downward_jumps"] >= 1
