"""Timestamp and business-date parsing for LaDe-P strings.

LaDe-P stores clock times as ``MM-DD HH:MM:SS`` and the business date ``ds``
as an integer month-day code (for example 821 is 21 August and 1004 is 4
October). Neither field contains a calendar year.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from lade_audit.constants import ORDERING_YEAR

_CLOCK_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_business_date(ds: pd.Series) -> pd.DataFrame:
    """Split the integer ``ds`` code into month and day.

    The published encoding is ``month * 100 + day``. Values that do not form
    a real month-day are marked invalid and are not coerced to a nearby date.
    """

    values = pd.to_numeric(ds, errors="coerce")
    month = np.floor_divide(values.to_numpy(dtype="float64"), 100.0)
    day = np.mod(values.to_numpy(dtype="float64"), 100.0)
    month_i = pd.Series(month, index=ds.index, dtype="Float64")
    day_i = pd.Series(day, index=ds.index, dtype="Float64")
    valid = (
        values.notna()
        & month_i.between(1, 12)
        & day_i.between(1, 31)
        & ~((month_i == 2) & (day_i > 28))
        & ~((month_i.isin([4, 6, 9, 11])) & (day_i > 30))
    )
    # February is checked against 28 days because the file has no year.
    # A 29 February code would be an unresolvable leap-day, not a valid date.
    stamp = pd.Series(pd.NaT, index=ds.index, dtype="datetime64[ns]")
    if valid.any():
        stamp.loc[valid] = pd.to_datetime(
            {
                "year": ORDERING_YEAR,
                "month": month_i.loc[valid].astype(int),
                "day": day_i.loc[valid].astype(int),
            },
            errors="coerce",
        )
    return pd.DataFrame(
        {
            "ds_month": month_i.astype("Int64"),
            "ds_day": day_i.astype("Int64"),
            "ds_valid": valid.fillna(False),
            "ds_date": stamp,
        }
    )


def parse_clock(values: pd.Series) -> pd.Series:
    """Parse ``MM-DD HH:MM:SS`` onto the placeholder ordering year.

    Unparseable or missing values become ``NaT``. The placeholder year is not
    written back as an observed year.
    """

    text = values.astype("string").str.strip()
    text = text.mask(text.isin(["", "<NA>", "None", "nan", "NaN", "null"]))
    stamped = text.radd(f"{ORDERING_YEAR}-")
    return pd.to_datetime(stamped, format=_CLOCK_FORMAT, errors="coerce")


def minutes_between(start: pd.Series, end: pd.Series) -> pd.Series:
    """Elapsed minutes from ``start`` to ``end``.

    When both timestamps parse and ``end`` is earlier only because a
    December-to-January boundary was stored without a year, 365 days are added
    and the caller can detect that case from ``year_wrap``. Ordinary overnight
    windows already carry an explicit next month-day, so they do not use this
    adjustment.
    """

    delta = (end - start).dt.total_seconds() / 60.0
    return delta


def year_boundary_wrap(start: pd.Series, end: pd.Series) -> pd.Series:
    """True when a parsed end falls before its start on the placeholder year."""

    return start.notna() & end.notna() & (end < start)


def clock_parts(stamps: pd.Series) -> pd.DataFrame:
    """Hour and minute components. Missing stamps stay missing."""

    return pd.DataFrame(
        {
            "hour": stamps.dt.hour.astype("Float64"),
            "minute": stamps.dt.minute.astype("Float64"),
            "second": stamps.dt.second.astype("Float64"),
        }
    )
