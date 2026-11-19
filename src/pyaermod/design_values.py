"""
Regulatory design-value calculations from POSTFILE output.

This module turns raw concentration time series (parsed via
:mod:`pyaermod.postfile`) into the percentile / design-value figures
that NAAQS regulatory submittals quote. Each function is annotated
with its 40 CFR Part 50 citation and the EPA design-value guidance
that prescribes the math.

All functions accept a :class:`pandas.DataFrame` shaped like the
``data`` attribute of :class:`pyaermod.postfile.PostfileResult`,
i.e. with columns ``x``, ``y``, ``concentration``, ``date`` (string
in YYMMDDHH form), ``ave``, ``grp``.

Background concentrations (uniform or time-varying) can be added
via :func:`add_background` before computing design values; per-
pollutant pairing rules are in the function docstring.

Years are meteorological years, as AERMOD counts them: a year ends on
the anniversary of the first met hour (``CHK_ENDYR`` in ``aermod.f``,
with the boundary set in ``meset.f``). Every design-value function takes
``year_start``: ``None`` (the default) reads the boundary from the first
date in the data, ``"calendar"`` groups by calendar year, and a
``(month, day)`` pair names the boundary. For data that start on
1 January the met year is the calendar year and nothing changes. Where
40 CFR Part 50 speaks of a calendar year (the annual NO2 mean of 50.11(e)
and Appendix S, the annual statistics of Appendices N, S and T), the
modelled met year stands in for it. The boundary is taken at day level:
a run whose first hour is not hour 01 starts its year at midnight of
that day here, a few hours earlier than AERMOD does.
"""

from __future__ import annotations

import calendar
import contextvars
import datetime as _dt
import math
import numbers
import warnings
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple, Union

import numpy as np
import pandas as pd

from ._fortran import fortran_float
from .pathways import SHORT_TERM_HOURS
from .postfile import label_hours, warn_hourly_mean_limitation

if TYPE_CHECKING:
    from .pathways import OutputPathway


@dataclass(frozen=True)
class DesignValue:
    """Result of a design-value computation at one receptor."""
    x: float
    y: float
    value: float
    pollutant: str
    averaging_period: str
    form: str  # e.g. "98th percentile", "H8H", "annual mean"
    n_years: int


# ---------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------

#: What ``pd.api.types.infer_dtype`` calls an object column holding floats.
_FLOAT_KINDS = frozenset({"floating", "mixed-integer-float", "mixed"})


def _whole_float_as_int(value: object) -> object:
    """``value`` as an int when it is a whole-number float, else unchanged."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _date_text(date_col: pd.Series) -> pd.Series:
    """A date column as stripped text, whole-number floats written as integers.

    A date column read back from a CSV with a blank date is float64, and
    ``str(16010101.0)`` is not a stamp, so a whole-number float is written
    as its integer. NaN and fractional floats keep their text (``nan``,
    ``19010101.5``) for the caller's error to name. Numbers have lost any
    leading zero (2005 reads 5010101); callers that want a YYMMDDHH stamp
    ``zfill(8)`` the result.
    """
    if pd.api.types.is_float_dtype(date_col.dtype):
        whole = (date_col.notna() & (date_col % 1 == 0)).fillna(False).astype(bool)
        text = date_col.astype(str)
        text[whole] = date_col[whole].astype("int64").astype(str)
        date_col = text
    elif (date_col.dtype == object
          and pd.api.types.infer_dtype(date_col, skipna=False) in _FLOAT_KINDS):
        date_col = date_col.map(_whole_float_as_int)
    return date_col.astype(str).str.strip()


def _stamp_text(date_col: pd.Series) -> pd.Series:
    """A date column as 8-character YYMMDDHH text (:func:`_date_text`, zero-filled).

    The one normalisation every stamp comparison and parse starts from;
    callers that need both the text and the parsed dates compute it once
    and hand it to :func:`_stamp_text_to_date`.
    """
    return _date_text(date_col).str.zfill(8)


def _parse_yymmddhh_to_year(date_col: pd.Series) -> pd.Series:
    """Extract the 4-digit year from an YYMMDDHH POSTFILE date column.

    AERMOD encodes the year as 2 digits prefixed by century rollover
    behaviour: 00..49 -> 2000..2049, 50..99 -> 1950..1999.
    """
    s = _stamp_text(date_col)
    yy = s.str.slice(0, 2).astype(int)
    return yy.where(yy < 50, yy + 1900).where(yy >= 50, yy + 2000)


def _parse_yymmddhh_to_date(date_col: pd.Series) -> pd.Series:
    """Convert YYMMDDHH to a pandas Timestamp (truncated to day)."""
    return _stamp_text_to_date(_stamp_text(date_col))


def _stamp_text_to_date(s: pd.Series) -> pd.Series:
    """Day timestamps of YYMMDDHH text already normalised by :func:`_stamp_text`."""
    yy = s.str.slice(0, 2).astype(int)
    yyyy = yy.where(yy < 50, yy + 1900).where(yy >= 50, yy + 2000)
    mm = s.str.slice(2, 4).astype(int)
    dd = s.str.slice(4, 6).astype(int)
    return pd.to_datetime(
        {"year": yyyy, "month": mm, "day": dd}, errors="coerce"
    )


# ---------------------------------------------------------------------
# Meteorological years
# ---------------------------------------------------------------------

#: What ``year_start`` accepts: None (detect from the data), "calendar",
#: or a (month, day) pair naming the first day of each year.
YearStart = Union[None, str, Tuple[int, int]]

#: The (month, day) a calendar year starts on.
_CALENDAR = (1, 1)


def _year_start(
    year_start: YearStart, dates: pd.Series, *, month_values: bool = False,
) -> tuple[int, int]:
    """``year_start`` resolved to the (month, day) each year begins on.

    ``None`` takes the first date in ``dates`` (day timestamps), which is
    where AERMOD's met year starts (``meset.f`` sets the year's end from
    the first met hour; ``CHK_ENDYR`` closes the year there). With no
    readable date it falls back to calendar years. ``month_values`` is for
    MONTH values, stamped at the end of their month: the year then starts
    on the first of the first value's month.
    """
    if year_start is None:
        valid = dates.dropna()
        if valid.empty:
            return _CALENDAR
        first = valid.min()
        return (int(first.month), 1 if month_values else int(first.day))
    if isinstance(year_start, str):
        if year_start.strip().lower() == "calendar":
            return _CALENDAR
        raise ValueError(
            f"year_start must be None, 'calendar' or a (month, day) pair; "
            f"got {year_start!r}"
        )
    try:
        month, day = year_start
    except (TypeError, ValueError):
        raise ValueError(
            f"year_start must be None, 'calendar' or a (month, day) pair; "
            f"got {year_start!r}"
        ) from None
    ok = all(isinstance(v, numbers.Integral) and not isinstance(v, bool)
             for v in (month, day))
    # 2000 is a leap year, so 29 February is a valid start.
    if not ok or not 1 <= month <= 12 or not 1 <= day <= calendar.monthrange(2000, month)[1]:
        raise ValueError(f"year_start {year_start!r} is not a (month, day) date")
    return (int(month), int(day))


def _met_years(dates: pd.Series, start: tuple[int, int]) -> pd.Series:
    """Each date's year label: the calendar year its met year starts in.

    With ``start`` (month, day), a date before that day of its calendar
    year belongs to the year that started the previous calendar year. A
    29 February start begins on 1 March in a common year, as AERMOD's
    ``CHK_ENDYR`` ends such a year on 28 February.
    """
    years = dates.dt.year
    if start == _CALENDAR:
        return years
    month, day = start
    before = (dates.dt.month < month) | ((dates.dt.month == month) & (dates.dt.day < day))
    return years - before.astype(int)


def _year_begin(year: int, start: tuple[int, int]) -> _dt.date:
    """The first day of the year labelled ``year``."""
    month, day = start
    if (month, day) == (2, 29) and not calendar.isleap(year):
        return _dt.date(year, 3, 1)
    return _dt.date(year, month, day)


def _year_days(year: int, start: tuple[int, int]) -> int:
    """Number of days in the year labelled ``year`` (365 or 366)."""
    return (_year_begin(year + 1, start) - _year_begin(year, start)).days


def _year_name(year: int, start: tuple[int, int]) -> str:
    """How a warning names a year: ``2019``, or the day a met year starts."""
    if start == _CALENDAR:
        return str(int(year))
    return f"the year starting {_year_begin(int(year), start):%Y-%m-%d}"


def _year_noun(start: tuple[int, int]) -> str:
    """``calendar year`` or ``met year`` for a year starting at ``start``."""
    return "calendar year" if start == _CALENDAR else "met year"


# ---------------------------------------------------------------------
# Hourly-mean warning
# ---------------------------------------------------------------------

#: Set while :func:`naaqs_compliance_report` runs a design-value function,
#: after it has given the hourly-mean warning itself.
_hourly_mean_warned: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_hourly_mean_warned", default=False)


def _warn_hourly_mean(df: pd.DataFrame, what: str) -> None:
    """:func:`~pyaermod.postfile.warn_hourly_mean_limitation` for 1-HR input.

    Called from a public function that averages hourly rows into 24-hour
    or annual means; the warning names the line that called it.
    """
    if _hourly_mean_warned.get() or not _is_hourly(df):
        return
    # 1 warn_hourly_mean_limitation, 2 this helper, 3 the public function,
    # 4 its caller.
    warn_hourly_mean_limitation(what, stacklevel=4)


# ---------------------------------------------------------------------
# EPA rank-based percentiles (40 CFR Part 50, Appendices N, S and T)
# ---------------------------------------------------------------------
#
# The NAAQS percentiles are *not* interpolated quantiles. Each appendix
# sorts the year's daily values from highest to lowest and reads the
# design value off a lookup table keyed on the number of days with
# valid data. The tables below are transcribed verbatim from the
# regulation; ``naaqs_percentile_rank`` reproduces them with the closed
# form ``ceil((1 - percentile/100) * n_days)``, and
# ``tests/test_naaqs_rank_tables.py`` checks the closed form against
# every row of every table for every day count.

#: 40 CFR 50 App. N Table 1 (24-hour PM2.5) and App. S Table 1 (1-hour
#: NO2): ``(max days in range, rank)`` for the 98th percentile.
PERCENTILE_98_RANK_TABLE: tuple[tuple[int, int], ...] = (
    (50, 1), (100, 2), (150, 3), (200, 4),
    (250, 5), (300, 6), (350, 7), (366, 8),
)

#: 40 CFR 50 App. T Table 1 (1-hour SO2): ``(max days in range, rank)``
#: for the 99th percentile.
PERCENTILE_99_RANK_TABLE: tuple[tuple[int, int], ...] = (
    (100, 1), (200, 2), (300, 3), (366, 4),
)


def naaqs_percentile_rank(n_days: int, percentile: float) -> int:
    """Rank of the ``percentile``-th value in a descending-sorted year.

    Parameters
    ----------
    n_days
        Number of days in the year with valid data.
    percentile
        98.0 or 99.0 (any percentile in (0, 100) is accepted and uses
        the same closed form the appendices tabulate).

    Returns
    -------
    int
        1 for the highest value, 2 for the second highest, and so on --
        ``ceil((1 - percentile/100) * n_days)``, clamped to at least 1.

    Notes
    -----
    Per 40 CFR 50 Appendix S Table 1, a full year (351-366 days) puts
    the 98th percentile at the **8th highest** daily value; Appendix T
    Table 1 puts the 99th percentile at the **4th highest**. Linear
    interpolation between order statistics -- what a naive
    ``Series.quantile`` does -- lands between ranks and reports a value
    the regulation never defines.
    """
    if n_days < 1:
        raise ValueError(f"n_days must be >= 1, got {n_days}")
    if not 0.0 < percentile < 100.0:
        raise ValueError(f"percentile must be in (0, 100), got {percentile}")
    # Exact rational arithmetic, not floats: 0.02 * 50 is 1.0000000000000002
    # in binary, whose ceiling is 2, which would put a 50-day year on the
    # second-highest value where appendix S Table 1 says the highest.
    fraction = 1 - Fraction(percentile).limit_denominator(10 ** 9) / 100
    return max(1, math.ceil(fraction * n_days))


# ---------------------------------------------------------------------
# Frame preparation
# ---------------------------------------------------------------------

def _one_source_group(df: pd.DataFrame) -> pd.DataFrame:
    """Reject frames holding more than one source group.

    A POSTFILE written with several ``SRCGROUP``s stacks their rows in
    one file. Pooling them would rank a mixture of unrelated impact
    series and quietly report a design value for no group at all, so
    the caller has to pick one.
    """
    if "grp" not in df.columns:
        return df
    groups = pd.unique(df["grp"].astype(str))
    if len(groups) > 1:
        raise ValueError(
            "design-value inputs must hold a single source group; found "
            f"{sorted(groups)}. Filter first, e.g. df[df['grp'] == "
            f"{groups[0]!r}]."
        )
    return df


def _dedupe_receptors(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse receptors that a POSTFILE lists more than once.

    AERMOD writes one row per receptor per period, and a deck may
    declare the same location twice (EPA's own ``surfcoal`` test case
    does). Those rows are byte-identical repeats, and leaving them in
    makes the 2nd-highest value a copy of the 1st. Distinct receptors
    that merely share (x, y) -- different flagpole heights, say -- are
    not something (x, y) grouping can represent, so they raise.
    """
    key = ["x", "y", "date"]
    out = df.drop_duplicates(subset=[*key, "concentration"])
    if out.duplicated(subset=key).any():
        clash = out[out.duplicated(subset=key, keep=False)].head(4)
        raise ValueError(
            "two receptors share (x, y) but report different "
            "concentrations for the same period, so they cannot be "
            f"ranked as one receptor:\n{clash[[*key, 'concentration']]}"
        )
    return out


def _is_hourly(df: pd.DataFrame) -> bool:
    """True when the frame carries 1-hour values needing daily rollup."""
    if "ave" not in df.columns:
        return False
    return "1-HR" in {str(a).strip().upper() for a in pd.unique(df["ave"])}


def _daily_series(df: pd.DataFrame, how: str) -> pd.DataFrame:
    """Per-(receptor, day) daily value, as ``x, y, date, concentration``.

    ``how`` is ``"mean"`` for standards whose daily value is the 24-hour
    average (PM2.5, PM10) and ``"max"`` for standards whose daily value
    is the maximum of the shorter-period values within the day (the
    1-hour NO2 and SO2 forms, and the 8-hour ozone form). Frames that
    already hold the standard's own averaging period -- AERMOD
    ``AVE='24-HR'`` block averages, one per day -- are passed through
    with a per-day max, which is a no-op on one value per day.
    """
    work = _dedupe_receptors(_one_source_group(df))
    agg = how if _is_hourly(work) else "max"
    g = work.assign(_d=_parse_yymmddhh_to_date(work["date"]))
    daily = (
        g.groupby(["x", "y", "_d"], as_index=False, sort=False)["concentration"]
        .agg(agg)
        .rename(columns={"_d": "date"})
    )
    # A day with no value (a blank, or every hour NaN) is not a day of data:
    # it neither ranks nor counts toward the year's day count.
    missing = daily["concentration"].isna()
    if missing.any():
        warnings.warn(
            f"{int(missing.sum())} receptor-day(s) have no concentration "
            "(NaN) and were left out of the ranking and the day counts.",
            stacklevel=4,
        )
        daily = daily[~missing]
    return daily


def _agg_daily_max(df: pd.DataFrame) -> pd.DataFrame:
    """Per-(receptor, day) max -- the daily-maximum series."""
    return _daily_series(df, "max")


def _nth_highest(values: np.ndarray, rank: int) -> float:
    """``rank``-th highest of ``values`` (1 = highest)."""
    values = values[~np.isnan(values)]
    n = len(values)
    if n == 0:
        return float("nan")
    return float(np.sort(values)[-min(rank, n)])


def _annual_rank_per_receptor(
    df_daily: pd.DataFrame, percentile: float, years: pd.Series,
) -> pd.DataFrame:
    """Annual EPA-rank percentile of the daily series, per receptor.

    The rank is chosen per (receptor, year) from that year's own count
    of days with data, exactly as the appendices prescribe -- a short
    year moves the design value up the sorted list rather than
    interpolating. ``years`` labels each daily row's (met) year.
    """
    df = df_daily.copy()
    df["_year"] = years
    return (
        df.groupby(["x", "y", "_year"], as_index=False, sort=False)
        ["concentration"]
        .agg(lambda s: _nth_highest(
            s.to_numpy(), naaqs_percentile_rank(len(s), percentile)
        ))
    )


def _daily_years(
    daily: pd.DataFrame, year_start: YearStart,
) -> tuple[pd.Series, str]:
    """Year labels of a daily series, and its partial-year note."""
    start = _year_start(year_start, daily["date"])
    years = _met_years(daily["date"], start)
    return years, _partial_year_note(daily["date"], years, start,
                                     calendar_asked=year_start is not None
                                     and start == _CALENDAR)


#: A year whose data span (first day to last day) is shorter than this
#: many days is called partial.
_FULL_YEAR_DAYS = 350


def _partial_year_note(
    dates: pd.Series, years: pd.Series, start: tuple[int, int], *,
    calendar_asked: bool = False,
) -> str:
    """Words naming years whose data span under ~350 days, or ``""``.

    ``years`` labels each date's year (:func:`_met_years` with ``start``).
    ``calendar_asked`` is True when the caller chose calendar years: a met
    year that does not run January to December then reads as two partial
    calendar years, while AERMOD counts it as one (``CHK_ENDYR`` in
    ``aermod.f``).
    """
    by_year = dates.dt.normalize().groupby(years)
    days = (by_year.max() - by_year.min()).dt.days + 1
    short = {int(y): int(n) for y, n in days.items() if n < _FULL_YEAR_DAYS}
    if not short:
        return ""
    if start == _CALENDAR:
        noun = "Calendar year(s)"
        listed = ", ".join(f"{y} (data span {n} days)" for y, n in sorted(short.items()))
    else:
        noun = "Met year(s) starting"
        listed = ", ".join(f"{_year_begin(y, start):%Y-%m-%d} (data span {n} days)"
                           for y, n in sorted(short.items()))
    if calendar_asked:
        return (
            f"{noun} {listed} are partial: with year_start='calendar' a "
            "met year that does not run January to December is split into "
            "calendar years, but AERMOD counts the met year as one year, so "
            "the ranks and the year count can differ from AERMOD's "
            "(year_start=None follows the met year)"
        )
    return (
        f"{noun} {listed} are partial: a year with fewer days of data is "
        "ranked on its own day count and still counts as a year"
    )


def _average_across_years(
    per_year: pd.DataFrame, *, expected_years: Optional[int], label: str,
    partial_note: str = "",
) -> pd.DataFrame:
    """Mean of the annual values, with the year count carried through.

    AERMOD forms the multi-year design value the same way
    (``SUMHNH / NUMYRS`` in ``aermod.f``): average the annual ranked
    values, do not re-rank the pooled record.
    """
    n_years = int(per_year["_year"].nunique())
    mismatch = expected_years is not None and n_years != expected_years
    if mismatch or partial_note:
        text = (
            f"{label} is defined over {expected_years} years but the input "
            f"covers {n_years}; the returned value averages the "
            f"{n_years} year(s) present."
            if mismatch else f"{label} input covers {n_years} year(s)."
        )
        if partial_note:
            text += " " + partial_note + "."
        warnings.warn(text, stacklevel=3)
    out = (
        per_year.groupby(["x", "y"], as_index=False, sort=False)
        ["concentration"].mean()
    )
    out["n_years"] = n_years
    return out


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def add_background(
    df: pd.DataFrame,
    background: Union[float, pd.Series, dict],
) -> pd.DataFrame:
    """Add a background concentration to every row of ``df``.

    Parameters
    ----------
    df
        POSTFILE-shaped DataFrame.
    background
        Either a uniform number (any real number, numpy scalars such as
        ``np.float32`` included, but not a bool), a pd.Series indexed by
        date (YYMMDDHH), or a dict mapping date -> float. Dates and keys
        are matched as
        8-character YYMMDDHH stamps, so text, integers and whole-number
        floats all match (2005's first hour reads ``"05010101"``,
        ``5010101`` or ``5010101.0``). Two keys naming the same stamp
        raise :class:`ValueError`.

    Returns
    -------
    A new DataFrame with ``concentration`` += background; ``date`` is
    left as given. Rows whose date has no background value are left
    unchanged, with a warning naming how many dates that is: a background
    that matches no date at all (usually keys that are not YYMMDDHH
    stamps) or only some of them (hours missing from the background
    series), since those hours then get no background.

    Raises
    ------
    TypeError
        If ``background`` is none of those (a bool, a string, a list ...).
    """
    return _add_background(df, background)[0]


def _add_background(
    df: pd.DataFrame,
    background: Union[float, pd.Series, dict],
) -> tuple[pd.DataFrame, Optional[pd.Series]]:
    """:func:`add_background`, also returning the frame's dates as stamp text.

    The text (:func:`_stamp_text` of ``df['date']``, row for row) is what a
    date-keyed background is matched on; it is *None* for a uniform one,
    which reads no dates.

    Its warnings name the line that called :func:`add_background` or
    :func:`naaqs_compliance_report`, each of which calls this directly
    (``stacklevel=3``): attributed to a line of this module, Python's
    default filter would show them once a session, and a second
    mismatched background would go unwarned.
    """
    out = df.copy()
    if isinstance(background, numbers.Real) and not isinstance(background, bool):
        out["concentration"] = out["concentration"] + float(background)
        return out, None
    if isinstance(background, dict):
        background = pd.Series(background)
    if not isinstance(background, pd.Series):
        raise TypeError(
            "background must be a number, a pd.Series indexed by YYMMDDHH "
            f"date or a dict of date -> value; got {type(background).__name__}"
        )
    keys = _stamp_text(pd.Series(background.index))
    repeated = keys[keys.duplicated()].unique()
    if len(repeated):
        raise ValueError(
            "the background has more than one value for "
            f"{', '.join(repeated[:4])}; its keys must name each YYMMDDHH "
            "stamp once."
        )
    by_stamp = pd.Series(background.to_numpy(), index=keys.to_numpy())
    stamps = _stamp_text(out["date"])
    bg = stamps.map(by_stamp)
    if len(out) and bg.isna().all():
        warnings.warn(
            "the background matches no date in the frame, so nothing was "
            "added; its keys must be YYMMDDHH stamps as in df['date'].",
            stacklevel=3,
        )
    elif bg.isna().any():
        # A row without a date gets no background either, so a missing
        # date counts as one more unmatched date (nunique() would drop it).
        missing = stamps[bg.isna()].nunique(dropna=False)
        warnings.warn(
            f"{missing} of {stamps.nunique(dropna=False)} dates in the frame "
            "have no background value, so nothing was added to their rows; "
            "give the background for every hour, or a single number.",
            stacklevel=3,
        )
    out["concentration"] = out["concentration"] + bg.fillna(0.0)
    return out, stamps


def annual_mean(
    df: pd.DataFrame, *, pollutant: str = "", year_start: YearStart = None,
) -> pd.DataFrame:
    """Annual-mean design-value calculation.

    Used for the PM2.5 annual NAAQS (40 CFR 50.20(a)-(b), Appendix N),
    whose form is the three-year average of annual means, and the NO2
    annual NAAQS (40 CFR 50.11(a), (e); Appendix S), whose form is one
    calendar year's mean. This returns the mean of each year at each
    receptor; :func:`naaqs_compliance_report` combines the years in the
    form of each standard. The year is the met year (see the module
    docstring and ``year_start``); it stands in for the calendar year
    of the rule, and ``year`` in the result is the calendar year the met
    year starts in.

    NOTE: Appendix N (4.4(a)-(b)) forms the annual PM2.5 mean as the mean
    of the calendar quarters' means of the daily values; this function
    averages every row of the year, which differs slightly for a complete
    year (the quarters have different lengths) and can differ more with
    gaps.

    Hourly (``1-HR``) input warns once that the mean divides by the
    number of rows (:func:`pyaermod.postfile.warn_hourly_mean_limitation`).

    Returns one row per (x, y, year) with column ``concentration``.
    """
    _warn_hourly_mean(df, "the annual means")
    work = _dedupe_receptors(_one_source_group(df))
    return _annual_means(work, _row_years(work["date"], year_start))


def _row_years(date_col: pd.Series, year_start: YearStart) -> pd.Series:
    """The (met) year of each POSTFILE row, from its YYMMDDHH date.

    Calendar years are read straight from the stamp, as they always were;
    met years need the dates parsed.
    """
    if isinstance(year_start, str) and year_start.strip().lower() == "calendar":
        return _parse_yymmddhh_to_year(date_col)
    dates = _parse_yymmddhh_to_date(date_col)
    start = _year_start(year_start, dates)
    if start == _CALENDAR:
        return _parse_yymmddhh_to_year(date_col)
    return _met_years(dates, start)


def _annual_means(work: pd.DataFrame, years: pd.Series) -> pd.DataFrame:
    """Mean per (x, y, year) of a frame already checked and deduplicated.

    ``years`` gives each row's (met) year. The core of
    :func:`annual_mean`, for callers that have checked the frame and
    parsed its dates themselves.
    """
    return (
        work.assign(_year=years)
        .groupby(["x", "y", "_year"], as_index=False, sort=False)
        ["concentration"].mean()
        .rename(columns={"_year": "year"})
    )


def nth_highest_daily_max_design_value(
    df: pd.DataFrame,
    rank: int,
    *,
    daily: str = "max",
    n_years: Optional[int] = None,
    pollutant: str = "",
    averaging_period: str = "",
    year_start: YearStart = None,
) -> pd.DataFrame:
    """Multi-year average of the annual ``rank``-th-highest daily value.

    This is the general form behind the 1-hour NO2, 1-hour SO2 and
    24-hour PM2.5 standards, and the one AERMOD itself computes under
    ``NO2AVE`` / ``SO2AVE`` / ``PM25AVE``: rank each year's daily series
    independently, then take the arithmetic mean of those annual values
    across the years modelled (``SUMHNH / NUMYRS`` in ``aermod.f``).
    The years are met years, as AERMOD's are (see ``year_start``).

    Parameters
    ----------
    df
        POSTFILE-shaped frame for a single source group.
    rank
        1 for the annual maximum, 8 for the NO2/PM2.5 98th percentile of
        a full year, 4 for the SO2 99th percentile of a full year. See
        :func:`naaqs_percentile_rank` to derive it from a percentile.
    daily
        ``"max"`` (default) to take each day's maximum sub-daily value,
        ``"mean"`` to take each day's 24-hour average.
    n_years
        Number of years the standard is defined over; a mismatch with
        the data warns rather than fails.
    year_start
        Where each year begins: ``None`` (default) from the first date
        in the data, as AERMOD's met year does (``CHK_ENDYR``);
        ``"calendar"`` for calendar years; or a ``(month, day)`` pair.
        Data that start on 1 January give calendar years either way.

    Returns
    -------
    One row per receptor with ``x``, ``y``, ``concentration`` and the
    actual ``n_years`` averaged.
    """
    if rank < 1:
        raise ValueError(f"rank must be >= 1, got {rank}")
    if daily == "mean":
        _warn_hourly_mean(df, "the 24-hour means")
    per_day = _daily_series(df, daily)
    per_day["_year"], partial_note = _daily_years(per_day, year_start)
    per_year = (
        per_day.groupby(["x", "y", "_year"], as_index=False, sort=False)
        ["concentration"].agg(lambda s: _nth_highest(s.to_numpy(), rank))
    )
    label = f"{pollutant or 'design value'} H{rank}H"
    out = _average_across_years(per_year, expected_years=n_years, label=label,
                                partial_note=partial_note)
    return out.assign(
        form=f"annual {rank}-highest daily {daily}",
        averaging_period=averaging_period,
        pollutant=pollutant,
    )


def pm25_24hr_design_value(
    df: pd.DataFrame, *, n_years: int = 3, year_start: YearStart = None,
) -> pd.DataFrame:
    """PM2.5 24-hour design value: 3-year avg of annual 98th percentiles.

    Per 40 CFR 50.20(a), (c) and Appendix N. Standard: 35 µg/m³.

    The daily value is the **24-hour average**, so hourly input
    (``AVE='1-HR'``) is averaged within each (receptor, day) group, with
    a warning that such a mean divides by the number of rows
    (:func:`pyaermod.postfile.warn_hourly_mean_limitation`); input that
    already carries AERMOD's ``AVE='24-HR'`` block averages is used
    as-is. Each year's 98th percentile is the rank Appendix N Table 1
    assigns to that year's day count -- the 8th highest for a full year
    -- and the design value is the mean of those annual values. The
    years are met years (``year_start``, see
    :func:`nth_highest_daily_max_design_value`), standing in for the
    calendar years of Appendix N.
    """
    _warn_hourly_mean(df, "the 24-hour PM2.5 means")
    daily = _daily_series(df, "mean")
    years, partial_note = _daily_years(daily, year_start)
    per_year = _annual_rank_per_receptor(daily, 98.0, years)
    out = _average_across_years(
        per_year, expected_years=n_years, label="The 24-hour PM2.5 NAAQS",
        partial_note=partial_note,
    )
    return out.assign(form="98th percentile", averaging_period="24-hour",
                      pollutant="PM2.5")


def no2_1hr_design_value(
    df: pd.DataFrame, *, n_years: int = 3, year_start: YearStart = None,
) -> pd.DataFrame:
    """NO2 1-hour design value: 3-year avg of annual 98th percentile of
    daily max 1-hour concentrations.

    Per 40 CFR 50.11(b), (f) and Appendix S. Standard: 100 ppb. The
    annual 98th percentile is the rank Appendix S Table 1 assigns to that
    year's day count -- the 8th highest daily maximum for a full year.
    The years are met years (``year_start``, see
    :func:`nth_highest_daily_max_design_value`), standing in for the
    calendar years of Appendix S.
    """
    daily = _daily_series(df, "max")
    years, partial_note = _daily_years(daily, year_start)
    per_year = _annual_rank_per_receptor(daily, 98.0, years)
    out = _average_across_years(
        per_year, expected_years=n_years, label="The 1-hour NO2 NAAQS",
        partial_note=partial_note,
    )
    return out.assign(form="98th percentile of daily max",
                      averaging_period="1-hour", pollutant="NO2")


def so2_1hr_design_value(
    df: pd.DataFrame, *, n_years: int = 3, year_start: YearStart = None,
) -> pd.DataFrame:
    """SO2 1-hour design value: 3-year avg of annual 99th percentile of
    daily max 1-hour concentrations.

    Per 40 CFR 50.17(b) and Appendix T. Standard: 75 ppb. The annual
    99th percentile is the rank Appendix T Table 1 assigns to that year's
    day count -- the 4th highest daily maximum for a full year. The years
    are met years (``year_start``, see
    :func:`nth_highest_daily_max_design_value`), standing in for the
    calendar years of Appendix T.
    """
    daily = _daily_series(df, "max")
    years, partial_note = _daily_years(daily, year_start)
    per_year = _annual_rank_per_receptor(daily, 99.0, years)
    out = _average_across_years(
        per_year, expected_years=n_years, label="The 1-hour SO2 NAAQS",
        partial_note=partial_note,
    )
    return out.assign(form="99th percentile of daily max",
                      averaging_period="1-hour", pollutant="SO2")


def pm10_24hr_design_value(
    df: pd.DataFrame, *, rank: Optional[int] = None, year_start: YearStart = None,
) -> pd.DataFrame:
    """PM10 24-hour design value: highest Nth-highest 24-hour value.

    The standard (150 µg/m³, 40 CFR 50.6(a), Appendix K) is met when the
    expected number of days per calendar year above 150 µg/m³ is at most
    one, averaged over three years. Unlike the percentile standards this
    value is **not** an average across years: it ranks the pooled
    multi-year record and takes the *highest sixth-high* (H6H) when five
    years of meteorology are modelled -- five allowed exceedances plus
    one -- or the *highest second-high* (H2H) with one year. That
    modelling rule is the High-N+1-High of the AERMOD User's Guide
    (section 3.2.16.2), carried over from the pre-2017 Guideline on Air
    Quality Models (Appendix W, 7.2.1.1(b)); it is not in Part 50 or in
    the 2017 or current Appendix W.

    ``rank`` defaults to 6 for a record of five or more years and 2
    otherwise, and can be set explicitly. The years counted are met
    years (``year_start``, see :func:`nth_highest_daily_max_design_value`),
    so four July-to-June years are four years, not five. The daily value
    is the 24-hour average, so hourly input is averaged within each day
    (with the warning of
    :func:`pyaermod.postfile.warn_hourly_mean_limitation`).

    NOTE: with N complete years the form of Appendix K corresponds to
    the (N+1)-th highest value (User's Guide 3.2.16.2: H3H, H4H, H5H for
    two, three, four years); the default here uses H2H for two to four
    years, which is more stringent. Appendix K (1.0(b)) also rounds each
    daily value to the nearest 10 µg/m³ before comparing it with 150, so
    only values of 155 and above are exceedances there, while Appendix W
    9.2.2(b) says modelled values are not rounded; this function and
    :func:`naaqs_compliance_report` compare the unrounded value with 150.
    """
    _warn_hourly_mean(df, "the 24-hour PM10 means")
    daily = _daily_series(df, "mean")
    years, partial_note = _daily_years(daily, year_start)
    n_years = int(years.nunique())
    if partial_note:
        warnings.warn(
            f"PM10 input covers {n_years} year(s), which sets the "
            f"rank. {partial_note}.",
            stacklevel=2,
        )
    if rank is None:
        rank = 6 if n_years >= 5 else 2
    out = (
        daily.groupby(["x", "y"], as_index=False, sort=False)["concentration"]
        .agg(lambda s: _nth_highest(s.to_numpy(), rank))
    )
    out["n_years"] = n_years
    out["form"] = f"H{rank}H (highest {rank}-highest 24-hour)"
    out["averaging_period"] = "24-hour"
    out["pollutant"] = "PM10"
    return out


def o3_8hr_design_value(
    df_8hr: pd.DataFrame, *, n_years: int = 3, year_start: YearStart = None,
) -> pd.DataFrame:
    """O3 8-hour design value: 3-year avg of annual 4th-highest daily
    max 8-hour average concentration.

    Per 40 CFR 50.19 and Appendix U. Standard: 70 ppb. The years are met
    years (``year_start``, see :func:`nth_highest_daily_max_design_value`).

    Note: this expects AERMOD's 8-hour averages as input (``AVE='8-HR'``).
    AERMOD forms an N-HR average only at the hours that are multiples of
    N (``MOD(IHOUR, KAVE) == 0`` in ``aermod.f``), so an 8-HR POSTFILE
    holds three fixed, non-overlapping blocks per day (ending at hours 8,
    16 and 24), not running 8-hour means. Each (receptor, day) max is
    taken to obtain the daily 8-hr max series. The maximum of three
    blocks is never above the maximum of the 24 running means, so the
    value can be lower than one built from running means.

    NOTE: Appendix U (3(b)-(d)) forms the daily maximum from running
    8-hour averages stored at their first hour, over the 17 periods
    starting 07:00 to 23:00, with validity rules (6 of 8 hours, 13 of 17
    periods); this function uses AERMOD's block averages instead.

    Raises
    ------
    ValueError
        If the frame holds ``AVE='1-HR'`` rows, which are hourly values
        and not 8-hour averages.
    """
    if _is_hourly(df_8hr):
        raise ValueError(
            "o3_8hr_design_value needs AERMOD's 8-HR averages (AVE='8-HR'), "
            "but the frame holds 1-HR rows; request AVERTIME 8 and read that "
            "POSTFILE instead of passing 1-hour values as 8-hour averages."
        )
    return nth_highest_daily_max_design_value(
        df_8hr, rank=4, daily="max", n_years=n_years,
        pollutant="O3", averaging_period="8-hour", year_start=year_start,
    ).assign(form="annual 4th-highest daily max")


# ---------------------------------------------------------------------
# AERMOD's own design-value outputs (OU MAXDAILY / MXDYBYYR / MAXDCONT)
# ---------------------------------------------------------------------

_MAXDAILY_COLUMNS = ("x", "y", "concentration", "zelev", "zhill", "zflag",
                     "ave", "grp", "jday", "hr", "date", "netid")


def _read_maxdaily_like(path: Union[str, Path], kind: str) -> pd.DataFrame:
    """Parse a MAXDAILY or MXDYBYYR file into a POSTFILE-shaped frame.

    Both files share one record layout (``ouset.f`` format MXDFRM): X, Y,
    concentration, ZELEV, ZHILL, ZFLAG, then AVE (MAXDAILY) or RANK
    (MXDYBYYR), GRP, Julian day, hour, YYMMDDHH date and network ID.
    The network ID is blank for discrete receptors, so the row is split
    on whitespace and the last field is optional.
    """
    rows = []
    with open(path, encoding="latin-1") as fh:
        for line in fh:
            if not line.strip() or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 11:
                raise ValueError(
                    f"{path}: expected at least 11 fields per {kind} record, "
                    f"got {len(parts)}: {line.rstrip()!r}"
                )
            netid = parts[11] if len(parts) > 11 else ""
            rows.append((
                float(parts[0]), float(parts[1]), fortran_float(parts[2]),
                float(parts[3]), float(parts[4]), float(parts[5]),
                parts[6], parts[7], int(parts[8]), int(parts[9]),
                parts[10].zfill(8), netid,
            ))
    df = pd.DataFrame(rows, columns=list(_MAXDAILY_COLUMNS))
    if kind == "MXDYBYYR":
        # AERMOD prints the rank as an ordinal ("1ST", "4TH", "10TH").
        df = df.rename(columns={"ave": "rank"})
        df["rank"] = df["rank"].str.extract(r"^(\d+)", expand=False).astype(int)
    return df


def read_maxdaily(path: Union[str, Path]) -> pd.DataFrame:
    """Read an AERMOD ``OU MAXDAILY`` file.

    The file holds every day's maximum 1-hour value (24-hour value for
    PM2.5) at every receptor, which is exactly the daily series the
    NAAQS percentile forms rank. The frame has the POSTFILE columns
    (``x``, ``y``, ``concentration``, ``ave``, ``grp``, ``date`` in
    YYMMDDHH) plus ``zelev``, ``zhill``, ``zflag``, ``jday``, ``hr`` and
    ``netid``, so it feeds :func:`no2_1hr_design_value`,
    :func:`so2_1hr_design_value` and :func:`pm25_24hr_design_value`
    directly.
    """
    return _read_maxdaily_like(path, "MAXDAILY")


def read_mxdybyyr(path: Union[str, Path]) -> pd.DataFrame:
    """Read an AERMOD ``OU MXDYBYYR`` file.

    One row per receptor, year and rank: the ranked daily maxima AERMOD
    itself computed (``rank`` 1 is that year's highest daily value). The
    date column carries the day the ranked value occurred.
    """
    return _read_maxdaily_like(path, "MXDYBYYR")


def mxdybyyr_design_value(df: pd.DataFrame, rank: int) -> pd.DataFrame:
    """Design value from AERMOD's own ranked daily maxima.

    Averages the ``rank``-th ranked value across the years in an
    MXDYBYYR frame (:func:`read_mxdybyyr`), receptor by receptor: the
    same ``SUMHNH / NUMYRS`` form AERMOD prints, and the cross-check for
    :func:`no2_1hr_design_value` / :func:`so2_1hr_design_value` computed
    from the MAXDAILY series.

    AERMOD writes one rank-``rank`` row per receptor for each of its met
    years, so the year count is the number of those rows at a receptor,
    not the number of calendar years their dates fall in (a July-to-June
    year can put its ranked days in two calendar years). The function
    needs no ``year_start``: AERMOD has already grouped the years.
    """
    work = _one_source_group(df)
    sel = work[work["rank"] == rank].copy()
    if sel.empty:
        raise ValueError(
            f"no rank-{rank} rows; the deck's RECTABLE range must reach "
            f"rank {rank} for MXDYBYYR to write it"
        )
    # A receptor the deck declares twice repeats its rows byte for byte.
    sel = sel.drop_duplicates(subset=["x", "y", "date", "concentration"])
    sel["_year"] = sel.groupby(["x", "y"], sort=False).cumcount()
    out = _average_across_years(
        sel[["x", "y", "_year", "concentration"]], expected_years=None,
        label=f"rank {rank}",
    )
    return out.assign(form=f"annual rank {rank} (AERMOD MXDYBYYR)")


def naaqs_output_pathway(
    pollutant: str,
    *,
    source_group: str = "ALL",
    stem: str = "design",
    threshold: Optional[float] = None,
    receptor_table_rank: Optional[int] = None,
) -> OutputPathway:
    """An :class:`~pyaermod.pathways.OutputPathway` for a NAAQS design value.

    Requests the three AERMOD outputs the 1-hour NO2/SO2 and 24-hour
    PM2.5 design-value workflow needs, with the rank taken from the
    NAAQS table rather than typed by hand:

    - ``MAXDAILY`` (``<stem>_maxdaily.dat``): the daily series, for
      :func:`read_maxdaily` and the design-value functions;
    - ``MXDYBYYR`` (``<stem>_mxdybyyr.dat``): AERMOD's ranked values,
      for :func:`mxdybyyr_design_value` as a cross-check;
    - ``MAXDCONT`` (``<stem>_maxdcont.dat``): source-group contributions
      at the design rank, or from the design rank down to ``threshold``
      when one is given (the THRESH form).

    ``receptor_table_rank`` defaults to the design rank, or to the
    smallest range AERMOD accepts for the THRESH form (design rank plus
    five, ``ouset.f`` E273). The control pathway must select the
    matching processing: POLLUTID NO2/SO2 with AVERTIME 1, or PM25 with
    AVERTIME 24; :class:`pyaermod.validator.Validator` checks that.
    """
    from .naaqs import get_naaqs
    from .pathways import MaxDailyContribution, MaxDailyFile, OutputPathway

    key = pollutant.strip().upper()
    period = "24-hour" if key in ("PM2.5", "PM25", "PM-2.5") else "1-hour"
    standard = get_naaqs(pollutant, period)
    rank = standard.design_rank()
    if receptor_table_rank is None:
        receptor_table_rank = rank if threshold is None else rank + 5
    if threshold is None:
        contribution = MaxDailyContribution(
            source_group, rank, f"{stem}_maxdcont.dat", lower_rank=rank,
        )
    else:
        contribution = MaxDailyContribution(
            source_group, rank, f"{stem}_maxdcont.dat", threshold=threshold,
        )
    return OutputPathway(
        receptor_table=True,
        receptor_table_rank=receptor_table_rank,
        max_table=False,
        max_daily_files=[MaxDailyFile(source_group, f"{stem}_maxdaily.dat")],
        max_daily_by_year_files=[MaxDailyFile(source_group, f"{stem}_mxdybyyr.dat")],
        max_daily_contributions=[contribution],
    )


#: How :func:`naaqs_compliance_report` may combine the years' annual NO2
#: means: the CFR form, one calendar year (the highest), or their average.
_NO2_ANNUAL_FORMS = ("highest_year", "multi_year_mean")

#: 40 CFR 50 Appendix S: an annual NO2 mean is valid when at
#: least 75 % of the year is covered.
_NO2_ANNUAL_COMPLETENESS = 0.75


def _coverage_unit(ave: object) -> tuple[str, int]:
    """The unit a year's coverage is counted in for one POSTFILE ``ave``.

    Returns the unit and the number of those units one value covers:
    ``("hour", N)`` for N-HR values shorter than a day (AERMOD's block
    averages, so an 8-HR value covers 8 hours; Appendix S judges an annual
    mean by the share of the year's hours), ``("month", 1)`` for MONTH
    values, ``("year", 1)`` for ANNUAL values (each is a whole year's
    mean), ``("period", 1)`` for PERIOD values (one mean over the whole
    run) and ``("day", 1)`` for everything else: 24-HR values, and
    anything not named.

    An N-HR label whose N is no short-term period AERMOD has (1, 2, 3, 4,
    6, 8, 12 or 24 hours) raises :class:`ValueError`: it is an ANNUAL or
    PERIOD value whose year or hour count was read as an averaging period,
    as a binary POSTFILE read without its averaging period can be.
    """
    text = str(ave).strip().upper()
    named = {"MONTH": "month", "ANNUAL": "year", "PERIOD": "period"}
    if text in named:
        return named[text], 1
    hours = label_hours(text)
    if hours is not None:
        if hours not in SHORT_TERM_HOURS:
            raise ValueError(
                f"{text} is not an averaging period AERMOD writes: its short-"
                "term periods are 1, 2, 3, 4, 6, 8, 12 and 24 hours. A binary "
                "ANNUAL POSTFILE holds its number of years (and a PERIOD one "
                "its number of hours) where a short-term one holds the hours "
                "averaged, so these are most likely ANNUAL or PERIOD values; "
                "read the file with read_postfile(path, "
                "averaging_period='ANNUAL') (or 'PERIOD')."
            )
        if hours < 24:
            return "hour", hours
    return "day", 1


#: An AERMOD YYMMDDHH stamp: hours run 01..24 (00 is accepted too).
_YYMMDDHH = r"\d{6}(?:[01]\d|2[0-4])"


def _no2_stamps(
    date_col: pd.Series, text: Optional[pd.Series] = None,
) -> tuple[pd.Series, pd.Series]:
    """The date column as normalised YYMMDDHH text and as day timestamps.

    ``text`` is :func:`_stamp_text` of ``date_col`` when the caller has it
    already (from matching a background), so the column is not read again.
    Raises a ValueError naming the first few values that are not AERMOD
    YYMMDDHH stamps, rather than failing deep inside the parser.
    """
    if text is None:
        text = _stamp_text(date_col)
    bad = ~text.str.fullmatch(_YYMMDDHH)
    if not bad.any():
        stamp = _stamp_text_to_date(text)
        bad = stamp.isna()
    if bad.any():
        shown = date_col[bad].map(str).unique()[:4]
        raise ValueError(
            "the date column must hold AERMOD YYMMDDHH stamps; cannot read "
            f"{', '.join(shown)}."
        )
    return text, stamp


def _annual_numyrs(date_col: pd.Series) -> Optional[int]:
    """The number of years behind ANNUAL POSTFILE rows, or None if unknown.

    AERMOD writes NUMYRS (I8.8) where a POSTFILE has the date, so a value
    averaged over five years reads ``00000005``. A field that is a date, or
    is not one count shared by every row, says nothing about the length.
    A count read from a float column (``5.0``) is still a count.
    """
    text = _date_text(date_col)
    if text.empty or not text.str.fullmatch(r"\d{1,8}").all():
        return None
    counts = text.map(int).unique()
    # NUMYRS is a count of met years, so a small number; the smallest real
    # YYMMDDHH stamp, 00010101 (2000-01-01 hour 01), reads 10101. Anything
    # outside 1-99 is a date (00123124 is 2000-12-31 hour 24), not a count.
    if len(counts) != 1 or not 1 <= counts[0] <= 99:
        return None
    return int(counts[0])


def _ave_names(df: pd.DataFrame) -> list[str]:
    """The frame's averaging periods (``ave``), stripped, upper-cased, sorted.

    Empty when the frame has no ``ave`` column.
    """
    if "ave" not in df.columns:
        return []
    return sorted({str(a).strip().upper() for a in pd.unique(df["ave"])})


def _no2_annual_input(
    df: pd.DataFrame, aves: list[str],
) -> tuple[pd.DataFrame, str, int]:
    """The rows behind an annual NO2 design value and their coverage unit.

    Both forms of :func:`naaqs_compliance_report`'s annual NO2 value read
    their input through this. The frame must hold one source group and one
    averaging period (one ``ave`` value): rows of different periods are
    different quantities, and averaging or ranking them together means
    nothing. ``aves`` is :func:`_ave_names` of the frame, which the caller
    has already read. Without an ``ave`` column the rows are taken as
    sub-annual values, counted in days. Returns the frame and
    :func:`_coverage_unit` of its averaging period.
    """
    work = _one_source_group(df)
    if len(aves) > 1:
        raise ValueError(
            "an annual NO2 mean needs one averaging period; found "
            f"{', '.join(aves)}. Pass one averaging period, e.g. "
            f"df[df['ave'] == {aves[0]!r}]."
        )
    unit, per_value = _coverage_unit(aves[0]) if aves else ("day", 1)
    return work, unit, per_value


def _refuse_one_value_per_receptor(work: pd.DataFrame, aves: list[str]) -> None:
    """Refuse N-HR rows that hold one value per receptor.

    One value per receptor is what an ANNUAL or PERIOD POSTFILE holds; a
    short-term series has many. A binary one read without its averaging
    period labels NUMYRS (or the run's hours) N-HR when N is a short-term
    period ending at the record's hour. ``work`` is one source group's
    rows, already deduplicated (:func:`_dedupe_receptors`), so a receptor
    a deck declares twice still has one row. Only an N-HR label is
    checked, and the receptors are counted once, against the row count.
    """
    if not aves or label_hours(aves[0]) is None or work.empty:
        return
    if len(work) == len(work[["x", "y"]].drop_duplicates()):
        raise ValueError(
            f"every receptor has one {aves[0]} value, which looks like an "
            "ANNUAL or PERIOD POSTFILE: a binary one holds its number of "
            "years (or hours) where a short-term one holds the hours "
            "averaged. Read it with read_postfile(path, "
            "averaging_period='ANNUAL' or 'PERIOD')."
        )


def _no2_annual_design_value(
    df: pd.DataFrame, form: str, aves: list[str],
    stamps: Optional[pd.Series] = None, year_start: YearStart = None,
) -> pd.DataFrame:
    """Annual NO2 design value per receptor in ``form`` (see _NO2_ANNUAL_FORMS).

    ``aves`` is :func:`_ave_names` of ``df``. ``stamps``, when given, is
    :func:`_stamp_text` of ``df['date']`` row for row (as
    :func:`_add_background` returns it), used instead of reading the dates
    again.

    An ANNUAL value over N years is AERMOD's average of the N years'
    annual means: in the ``"multi_year_mean"`` form it is the design value
    itself, whatever N is. In the ``"highest_year"`` form it is a whole
    year's mean only when the run covered one year; over several years it
    is a lower bound on the highest year, so it is refused, as is one whose
    number of years cannot be read. A PERIOD value is one mean over the
    whole run, which cannot be split into calendar years; either form uses
    it as it is, with a warning. Neither has a date to parse: the date
    field holds a count.

    Sub-annual values are combined by (met) year, ``year_start`` deciding
    where each year begins: averaged across every year present for
    ``"multi_year_mean"``, and for ``"highest_year"`` as
    :func:`_no2_highest_complete_year` describes.
    """
    work, unit, per_value = _no2_annual_input(df, aves)
    if unit == "year" and form == "highest_year":
        numyrs = _annual_numyrs(work["date"])
        if numyrs != 1:
            span = (f"{numyrs} years" if numyrs is not None else
                    "an unknown number of years (the date column does not "
                    "hold AERMOD's NUMYRS count, so it may be several)")
            raise ValueError(
                f"the ANNUAL values cover {span}. AERMOD's multi-year ANNUAL "
                "value is the average of the years' annual means, a lower "
                "bound on the annual NO2 design value, which is the highest "
                "single calendar year's mean (40 CFR 50.11(e), Appendix S). "
                "An hourly (or 24-HR / MONTH) POSTFILE gives the per-year "
                "means."
            )

    if stamps is not None:
        # By position, not index label: the frame's labels may repeat.
        work = work.assign(_stamp=stamps.to_numpy())
    # Dedupe after the period check: rows of different periods that end on
    # the same hour would otherwise read as repeats of each other.
    work = _dedupe_receptors(work)
    _refuse_one_value_per_receptor(work, aves)
    receptor = ["x", "y"]
    if unit in ("year", "period"):
        # One mean per receptor, used as it is.
        if unit == "period":
            warnings.warn(
                "a PERIOD average is one mean over the whole run, not a "
                "calendar year's mean, so the annual NO2 design value is the "
                "PERIOD mean; it equals the annual mean (40 CFR 50 Appendix "
                "S) only for a run of one calendar year.",
                stacklevel=3,
            )
        return (work.groupby(receptor, as_index=False, sort=False)
                ["concentration"].max())
    text, stamp = _no2_stamps(
        work["date"], work["_stamp"] if stamps is not None else None)
    start = _year_start(year_start, stamp, month_values=unit == "month")
    years = _met_years(stamp, start)
    if form == "multi_year_mean":
        return (_annual_means(work, years)
                .groupby(receptor, as_index=False, sort=False)
                ["concentration"].mean())
    if unit == "hour":
        unit_of_row = text
    elif unit == "month":
        unit_of_row = stamp.dt.month
    else:
        unit_of_row = stamp
    return _no2_highest_complete_year(
        work.assign(_year=years, _unit=unit_of_row), unit, per_value, start)


def _no2_highest_complete_year(
    work: pd.DataFrame, unit: str, per_value: int,
    start: tuple[int, int] = _CALENDAR,
) -> pd.DataFrame:
    """Highest annual mean per receptor, over the years at least 75 % covered.

    ``work`` holds sub-annual rows of one averaging period, already checked
    and deduplicated by :func:`_no2_annual_design_value`, with each row's
    year in ``_year`` (the met year beginning on ``start``, which stands
    in for the calendar year of Appendix S) and its coverage unit in
    ``_unit``. Coverage is counted in ``unit``, as 40 CFR 50 Appendix S
    (3.1(b)) counts it for the annual mean: the share of the year's hours
    (8760 or 8784) covered at that receptor for 1-HR to 12-HR values,
    ``per_value`` hours for each distinct stamp; the share of its days
    (365 or 366) for 24-HR values and frames without an ``ave`` column;
    and the share of its 12 months for MONTH values. The 75 % threshold
    and the units are the same for a met year as for a calendar year;
    only the year's first day moves.

    A year below 75 % is left out with a warning. A receptor with no
    year at 75 % gets the mean over its whole record instead, also with
    a warning, rather than its highest partial year.
    """
    receptor = ["x", "y"]
    keys = [*receptor, "_year"]
    means = work.groupby(keys, as_index=False, sort=False).agg(
        concentration=("concentration", "mean"), _n=("_unit", "nunique"))
    if unit == "month":
        whole = pd.Series(12, index=means.index)
    else:
        days = means["_year"].map(lambda y: _year_days(int(y), start))
        whole = days * 24 if unit == "hour" else days
    means["_ok"] = means["_n"] * per_value >= _NO2_ANNUAL_COMPLETENESS * whole

    any_ok = means.groupby(receptor, sort=False)["_ok"].transform("any")
    noun = {"hour": "hours", "month": "months"}.get(unit, "days")
    year_noun = _year_noun(start)
    dropped = sorted({int(y) for y in means.loc[~means["_ok"] & any_ok, "_year"]})
    if dropped:
        warnings.warn(
            "the annual NO2 design value leaves out "
            f"{', '.join(_year_name(y, start) for y in dropped)}: data on fewer "
            f"than 75% of the year's {noun} at some receptor (40 CFR 50 "
            "Appendix S) is too little for a valid annual mean.",
            stacklevel=4,
        )
    highest = (means[means["_ok"]]
               .groupby(receptor, as_index=False, sort=False)
               ["concentration"].max())
    if any_ok.all():
        return highest

    warnings.warn(
        f"no {year_noun} has data on at least 75% of its {noun} (40 CFR 50 "
        "Appendix S) at some receptor, so its annual NO2 design value is the "
        f"mean over the whole record, not a {year_noun.replace(' ', '-')} mean.",
        stacklevel=4,
    )
    incomplete = means.loc[~any_ok, receptor].drop_duplicates()
    whole_record = (work.merge(incomplete, on=receptor)
                    .groupby(receptor, as_index=False, sort=False)
                    ["concentration"].mean())
    # Back in the receptors' order of appearance.
    return (means[receptor].drop_duplicates()
            .merge(pd.concat([highest, whole_record]), on=receptor))


#: The pollutant keys :func:`naaqs_compliance_report` takes, each with the
#: means it forms from hourly rows ("" for the forms built from maxima).
_REPORT_FORMS = {
    "PM2.5": "24-hour PM2.5", "PM25": "24-hour PM2.5",
    "PM2.5_ANNUAL": "annual PM2.5", "PM25_ANNUAL": "annual PM2.5",
    "PM10": "24-hour PM10", "NO2_ANNUAL": "annual NO2",
    "NO2": "", "SO2": "", "O3": "",
}


def naaqs_compliance_report(
    pollutant: str,
    df: pd.DataFrame,
    *,
    background: Optional[Union[float, dict, pd.Series]] = None,
    n_years: int = 3,
    no2_annual: str = "highest_year",
    year_start: YearStart = None,
) -> pd.DataFrame:
    """One-stop compliance roll-up: design value + NAAQS comparison.

    Dispatches to the right design-value function for ``pollutant``,
    optionally adds ``background``, joins the NAAQS row, and flags
    receptors that exceed.

    Returns a DataFrame with columns:

    - x, y: receptor coords
    - design_value: numeric DV
    - naaqs_level, units, cfr_reference: the standard as 40 CFR 50 sets
      it (ppb for SO2, NO2 and O3)
    - naaqs_level_ugm3: the level in µg/m³, the unit AERMOD reports
    - exceeds: bool, ``design_value > naaqs_level_ugm3``

    The design value is in AERMOD's µg/m³, so ``exceeds`` compares it
    with the level converted to µg/m³ (75 ppb of SO2 is 196.4 µg/m³),
    never with a level in ppb. Modelled values are compared unrounded,
    as Appendix W (40 CFR 51) 9.2.2(b) says modelled concentrations
    should not be rounded; the rounding and truncation conventions of the
    Part 50 appendices (N, S, T, U, K) apply to monitored design values.

    Supported pollutants: PM2.5 (24-hour), PM10, NO2 (1-hour), SO2,
    O3, plus annual forms via ``pollutant="PM2.5_annual"`` /
    ``"NO2_annual"``.

    Years are met years: ``year_start`` (default ``None``, read from the
    first date in the data; ``"calendar"``; or a ``(month, day)`` pair)
    is passed to the design-value function, as described in
    :func:`nth_highest_daily_max_design_value`. Where Part 50 speaks of a
    calendar year the modelled met year stands in for it; data starting
    on 1 January give calendar years either way.

    Hourly (``1-HR``) input to a form built from means (PM2.5, PM10,
    PM2.5_annual, NO2_annual) warns once that the means divide by the
    number of rows (:func:`pyaermod.postfile.warn_hourly_mean_limitation`).

    The annual PM2.5 form is the average of the annual means (40 CFR
    50.20(a)-(b), Appendix N). NOTE: Appendix N 4.4 forms each year's
    mean as the mean of its calendar quarters' means; this report averages
    every row of the year (see :func:`annual_mean`). The annual NO2
    standard is a single calendar year's mean (40 CFR 50.11(a), (e);
    Appendix S), so with several years of data
    ``no2_annual="highest_year"`` (the default) takes the highest year's
    mean at each receptor. Only years with data on at least 75% of their
    hours count (Appendix S 3.1(b) treats an annual mean as valid from 75%
    coverage), so a few days of a following year cannot set the design
    value; the years left out are named in a :class:`UserWarning`. The
    frame must hold one averaging period (one ``ave`` value). Coverage is
    counted in hours for 1-HR (and other sub-daily block) values, so two
    hours a day is not a complete year; a 24-HR POSTFILE (or one without
    an ``ave`` column) counts days, a MONTH POSTFILE counts months, and a
    PERIOD mean, which covers
    the whole run rather than one calendar year, is used as it is with a
    warning. An ANNUAL value is used only when it covers one year: over
    several years (AERMOD writes NUMYRS where the date would be) it is the
    average of the years' means, a lower bound on the design value, so it
    raises :class:`ValueError`, as does an ANNUAL value whose number of
    years cannot be read. If no year at a receptor reaches 75%
    (a record of a few months, say), the design value there is the
    mean over its whole record and a warning says so.
    ``no2_annual="multi_year_mean"`` averages the years instead,
    which some reviewing agencies accept for five years of NWS met data;
    it can be below the highest year, and it averages every year present,
    complete or not. It too needs one averaging period. An ANNUAL value,
    which over several years is already the average of the years' means,
    is that mean as it is, whatever its number of years; a PERIOD mean is
    used as it is, with the same warning as above.

    ``background`` is added before the design value is formed. A date-keyed
    background (dict or Series) cannot be matched to ANNUAL or PERIOD
    values, whose date field is not an hour, so it raises
    :class:`ValueError` there; pass a single number instead.
    """
    from .naaqs import get_naaqs  # local import to avoid cycles

    pollutant = pollutant.upper()
    keyed = isinstance(background, (dict, pd.Series))
    # Read once: the background check and the annual NO2 value both use it.
    aves = _ave_names(df) if keyed or pollutant == "NO2_ANNUAL" else []
    if keyed:
        whole = [a for a in aves if a in ("ANNUAL", "PERIOD")]
        if whole:
            raise ValueError(
                f"a background keyed by date cannot be matched to "
                f"{' / '.join(whole)} values: their date field holds a year "
                "count or the run's last hour, not the hours the background "
                "is keyed on, so it would add nothing. Pass the background as "
                "a single number, e.g. its annual mean."
            )
    if pollutant not in _REPORT_FORMS:
        raise ValueError(
            f"Unsupported pollutant {pollutant!r}; supported: PM2.5, "
            f"PM2.5_annual, PM10, NO2, NO2_annual, SO2, O3"
        )
    if pollutant == "NO2_ANNUAL" and no2_annual not in _NO2_ANNUAL_FORMS:
        raise ValueError(f"no2_annual must be one of {', '.join(_NO2_ANNUAL_FORMS)}; "
                         f"got {no2_annual!r}")
    if _REPORT_FORMS[pollutant] and _is_hourly(df) and not _hourly_mean_warned.get():
        # Once, naming the caller's line; the function it runs stays quiet.
        warn_hourly_mean_limitation(
            f"the {_REPORT_FORMS[pollutant]} means", stacklevel=3)
    # The dispatch stays in this frame: the warnings below it count their
    # stack levels from here to name the caller's line.
    token = _hourly_mean_warned.set(True)
    try:
        work, stamps = (_add_background(df, background) if background is not None
                        else (df, None))
        if pollutant in ("PM2.5", "PM25"):
            dv = pm25_24hr_design_value(work, n_years=n_years, year_start=year_start)
            std = get_naaqs("PM2.5", "24-hour")
        elif pollutant in ("PM2.5_ANNUAL", "PM25_ANNUAL"):
            # The multi-year average: the mean of the annual means.
            dv = (annual_mean(work, year_start=year_start)
                  .groupby(["x", "y"], as_index=False, sort=False)
                  ["concentration"].mean())
            std = get_naaqs("PM2.5", "annual")
        elif pollutant == "PM10":
            dv = pm10_24hr_design_value(work, year_start=year_start)
            std = get_naaqs("PM10", "24-hour")
        elif pollutant == "NO2":
            dv = no2_1hr_design_value(work, n_years=n_years, year_start=year_start)
            std = get_naaqs("NO2", "1-hour")
        elif pollutant == "NO2_ANNUAL":
            dv = _no2_annual_design_value(work, no2_annual, aves, stamps, year_start)
            std = get_naaqs("NO2", "annual")
        elif pollutant == "SO2":
            dv = so2_1hr_design_value(work, n_years=n_years, year_start=year_start)
            std = get_naaqs("SO2", "1-hour")
        else:
            dv = o3_8hr_design_value(work, n_years=n_years, year_start=year_start)
            std = get_naaqs("O3", "8-hour")
    finally:
        _hourly_mean_warned.reset(token)

    out = dv.rename(columns={"concentration": "design_value"})
    out["naaqs_level"] = std.level
    out["units"] = std.units
    out["cfr_reference"] = std.cfr_reference
    out["naaqs_level_ugm3"] = std.level_ugm3
    out["exceeds"] = out["design_value"] > std.level_ugm3
    return out


__all__ = [
    "PERCENTILE_98_RANK_TABLE",
    "PERCENTILE_99_RANK_TABLE",
    "DesignValue",
    "add_background",
    "annual_mean",
    "mxdybyyr_design_value",
    "naaqs_compliance_report",
    "naaqs_output_pathway",
    "naaqs_percentile_rank",
    "no2_1hr_design_value",
    "nth_highest_daily_max_design_value",
    "o3_8hr_design_value",
    "pm10_24hr_design_value",
    "pm25_24hr_design_value",
    "read_maxdaily",
    "read_mxdybyyr",
    "so2_1hr_design_value",
]
