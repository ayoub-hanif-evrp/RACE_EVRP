"""Parsing rules that do not require the published file."""

from __future__ import annotations

import numpy as np
import pandas as pd

from lade_audit.observations import open_tasks_at_accepts
from lade_audit.parsing import minutes_between, parse_business_date, parse_clock, year_boundary_wrap


def test_business_date_codes() -> None:
    parsed = parse_business_date(pd.Series([821, 1004, 501, 229, 1332]))
    assert list(parsed.loc[0, ["ds_month", "ds_day"]]) == [8, 21]
    assert list(parsed.loc[1, ["ds_month", "ds_day"]]) == [10, 4]
    assert list(parsed.loc[2, ["ds_month", "ds_day"]]) == [5, 1]
    assert bool(parsed.loc[0, "ds_valid"]) is True
    assert bool(parsed.loc[3, "ds_valid"]) is False
    assert bool(parsed.loc[4, "ds_valid"]) is False
    assert parsed.loc[0, "ds_date"] == pd.Timestamp("2001-08-21")


def test_clock_parse_and_overnight_window() -> None:
    start = parse_clock(pd.Series(["09-17 17:05:00"]))
    end = parse_clock(pd.Series(["09-18 23:59:00"]))
    assert start.iloc[0] == pd.Timestamp("2001-09-17 17:05:00")
    assert bool(year_boundary_wrap(start, end).iloc[0]) is False
    assert minutes_between(start, end).iloc[0] == (24 * 60 + (23 * 60 + 59) - (17 * 60 + 5))


def test_missing_clock_is_not_invented() -> None:
    parsed = parse_clock(pd.Series([None, "", "not-a-time"]))
    assert parsed.isna().all()


def test_open_tasks_count_the_unfinished_batch() -> None:
    accept = np.array(
        [
            "2001-05-01T08:00",
            "2001-05-01T08:00",
            "2001-05-01T09:30",
        ],
        dtype="datetime64[ns]",
    )
    pickup = np.array(
        [
            "2001-05-01T08:20",
            "2001-05-01T10:00",
            "2001-05-01T11:00",
        ],
        dtype="datetime64[ns]",
    )
    counts = open_tasks_at_accepts(accept, pickup)
    assert list(counts) == [2, 2, 2]


def test_acceptance_is_not_labeled_as_request_creation() -> None:
    """The published field is courier acceptance, not customer request time."""

    from lade_audit.constants import REQUIRED_COLUMNS

    assert "accept_time" in REQUIRED_COLUMNS
    assert "request_time" not in REQUIRED_COLUMNS
    assert "release_time" not in REQUIRED_COLUMNS
