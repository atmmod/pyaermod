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
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional, Union

import numpy as np
import pandas as pd


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

def _parse_yymmddhh_to_year(date_col: pd.Series) -> pd.Series:
    """Extract the 4-digit year from an YYMMDDHH POSTFILE date column.

    AERMOD encodes the year as 2 digits prefixed by century rollover
    behaviour: 00..49 -> 2000..2049, 50..99 -> 1950..1999.
    """
    s = date_col.astype(str).str.zfill(8)
    yy = s.str.slice(0, 2).astype(int)
    return yy.where(yy < 50, yy + 1900).where(yy >= 50, yy + 2000)


def _parse_yymmddhh_to_date(date_col: pd.Series) -> pd.Series:
    """Convert YYMMDDHH to a pandas Timestamp (truncated to day)."""
    s = date_col.astype(str).str.zfill(8)
    yy = s.str.slice(0, 2).astype(int)
    yyyy = yy.where(yy < 50, yy + 1900).where(yy >= 50, yy + 2000)
    mm = s.str.slice(2, 4).astype(int)
    dd = s.str.slice(4, 6).astype(int)
    return pd.to_datetime(
        {"year": yyyy, "month": mm, "day": dd}, errors="coerce"
    )


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
    return (
        g.groupby(["x", "y", "_d"], as_index=False, sort=False)["concentration"]
        .agg(agg)
        .rename(columns={"_d": "date"})
    )


def _agg_daily_max(df: pd.DataFrame) -> pd.DataFrame:
    """Per-(receptor, day) max -- the daily-maximum series."""
    return _daily_series(df, "max")


def _nth_highest(values: np.ndarray, rank: int) -> float:
    """``rank``-th highest of ``values`` (1 = highest)."""
    n = len(values)
    if n == 0:
        return float("nan")
    return float(np.sort(values)[-min(rank, n)])


def _annual_rank_per_receptor(
    df_daily: pd.DataFrame, percentile: float,
) -> pd.DataFrame:
    """Annual EPA-rank percentile of the daily series, per receptor.

    The rank is chosen per (receptor, year) from that year's own count
    of days with data, exactly as the appendices prescribe -- a short
    year moves the design value up the sorted list rather than
    interpolating.
    """
    df = df_daily.copy()
    df["_year"] = df["date"].dt.year
    return (
        df.groupby(["x", "y", "_year"], as_index=False, sort=False)
        ["concentration"]
        .agg(lambda s: _nth_highest(
            s.to_numpy(), naaqs_percentile_rank(len(s), percentile)
        ))
    )


def _average_across_years(
    per_year: pd.DataFrame, *, expected_years: Optional[int], label: str,
) -> pd.DataFrame:
    """Mean of the annual values, with the year count carried through.

    AERMOD forms the multi-year design value the same way
    (``SUMHNH / NUMYRS`` in ``aermod.f``): average the annual ranked
    values, do not re-rank the pooled record.
    """
    n_years = int(per_year["_year"].nunique())
    if expected_years is not None and n_years != expected_years:
        warnings.warn(
            f"{label} is defined over {expected_years} years but the input "
            f"covers {n_years}; the returned value averages the "
            f"{n_years} year(s) present.",
            stacklevel=3,
        )
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
        Either a uniform float, a pd.Series indexed by date string
        (YYMMDDHH), or a dict mapping date string -> float. Index
        format must match ``df['date']``.

    Returns
    -------
    A new DataFrame with ``concentration`` += background. Rows whose
    date has no background entry are left unchanged.
    """
    out = df.copy()
    if isinstance(background, (int, float)):
        out["concentration"] = out["concentration"] + float(background)
        return out
    if isinstance(background, dict):
        background = pd.Series(background)
    bg = out["date"].astype(str).map(background).fillna(0.0)
    out["concentration"] = out["concentration"] + bg
    return out


def annual_mean(
    df: pd.DataFrame, *, pollutant: str = "",
) -> pd.DataFrame:
    """Annual-mean design-value calculation.

    Used for the PM2.5 annual NAAQS (40 CFR 50.18) and the NO2 annual
    NAAQS (40 CFR 50.11). The standard form is the multi-year average
    of annual means; this returns per-receptor *annual* means — caller
    averages across years if a 3-year design value is wanted.

    Returns one row per (x, y, year) with column ``concentration``.
    """
    work = _dedupe_receptors(_one_source_group(df))
    g = work.assign(_year=_parse_yymmddhh_to_year(work["date"]))
    return (
        g.groupby(["x", "y", "_year"], as_index=False, sort=False)
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
) -> pd.DataFrame:
    """Multi-year average of the annual ``rank``-th-highest daily value.

    This is the general form behind the 1-hour NO2, 1-hour SO2 and
    24-hour PM2.5 standards, and the one AERMOD itself computes under
    ``NO2AVE`` / ``SO2AVE`` / ``PM25AVE``: rank each year's daily series
    independently, then take the arithmetic mean of those annual values
    across the years modelled (``SUMHNH / NUMYRS`` in ``aermod.f``).

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

    Returns
    -------
    One row per receptor with ``x``, ``y``, ``concentration`` and the
    actual ``n_years`` averaged.
    """
    if rank < 1:
        raise ValueError(f"rank must be >= 1, got {rank}")
    per_day = _daily_series(df, daily)
    per_day["_year"] = per_day["date"].dt.year
    per_year = (
        per_day.groupby(["x", "y", "_year"], as_index=False, sort=False)
        ["concentration"].agg(lambda s: _nth_highest(s.to_numpy(), rank))
    )
    label = f"{pollutant or 'design value'} H{rank}H"
    out = _average_across_years(per_year, expected_years=n_years, label=label)
    return out.assign(
        form=f"annual {rank}-highest daily {daily}",
        averaging_period=averaging_period,
        pollutant=pollutant,
    )


def pm25_24hr_design_value(
    df: pd.DataFrame, *, n_years: int = 3,
) -> pd.DataFrame:
    """PM2.5 24-hour design value: 3-year avg of annual 98th percentiles.

    Per 40 CFR 50 Appendix N. Standard: 35 µg/m³.

    The daily value is the **24-hour average**, so hourly input
    (``AVE='1-HR'``) is averaged within each (receptor, day) group;
    input that already carries AERMOD's ``AVE='24-HR'`` block averages
    is used as-is. Each year's 98th percentile is the rank Appendix N
    Table 1 assigns to that year's day count -- the 8th highest for a
    full year -- and the design value is the mean of those annual
    values.
    """
    per_year = _annual_rank_per_receptor(
        _daily_series(df, "mean"), percentile=98.0,
    )
    out = _average_across_years(
        per_year, expected_years=n_years, label="The 24-hour PM2.5 NAAQS",
    )
    return out.assign(form="98th percentile", averaging_period="24-hour",
                      pollutant="PM2.5")


def no2_1hr_design_value(
    df: pd.DataFrame, *, n_years: int = 3,
) -> pd.DataFrame:
    """NO2 1-hour design value: 3-year avg of annual 98th percentile of
    daily max 1-hour concentrations.

    Per 40 CFR 50 Appendix S. Standard: 100 ppb. The annual 98th
    percentile is the rank Appendix S Table 1 assigns to that year's day
    count -- the 8th highest daily maximum for a full year.
    """
    per_year = _annual_rank_per_receptor(
        _daily_series(df, "max"), percentile=98.0,
    )
    out = _average_across_years(
        per_year, expected_years=n_years, label="The 1-hour NO2 NAAQS",
    )
    return out.assign(form="98th percentile of daily max",
                      averaging_period="1-hour", pollutant="NO2")


def so2_1hr_design_value(
    df: pd.DataFrame, *, n_years: int = 3,
) -> pd.DataFrame:
    """SO2 1-hour design value: 3-year avg of annual 99th percentile of
    daily max 1-hour concentrations.

    Per 40 CFR 50 Appendix T. Standard: 75 ppb. The annual 99th
    percentile is the rank Appendix T Table 1 assigns to that year's day
    count -- the 4th highest daily maximum for a full year.
    """
    per_year = _annual_rank_per_receptor(
        _daily_series(df, "max"), percentile=99.0,
    )
    out = _average_across_years(
        per_year, expected_years=n_years, label="The 1-hour SO2 NAAQS",
    )
    return out.assign(form="99th percentile of daily max",
                      averaging_period="1-hour", pollutant="SO2")


def pm10_24hr_design_value(
    df: pd.DataFrame, *, rank: Optional[int] = None,
) -> pd.DataFrame:
    """PM10 24-hour design value: highest Nth-highest 24-hour value.

    Per 40 CFR 50.6 the standard (150 µg/m³) may not be exceeded more
    than once per year on average. Unlike the percentile standards this
    one is **not** averaged across years: Appendix W Table 8-2 ranks the
    pooled multi-year record and takes the *highest sixth-high* (H6H)
    when five years of NWS meteorology are modelled -- five allowed
    exceedances plus one -- or the *highest second-high* (H2H) with a
    single year of site-specific data.

    ``rank`` defaults to that rule (6 for a five-year record, 2
    otherwise) and can be set explicitly. The daily value is the
    24-hour average, so hourly input is averaged within each day.
    """
    daily = _daily_series(df, "mean")
    n_years = int(daily["date"].dt.year.nunique())
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
    df_8hr: pd.DataFrame, *, n_years: int = 3,
) -> pd.DataFrame:
    """O3 8-hour design value: 3-year avg of annual 4th-highest daily
    max 8-hour average concentration.

    Per 40 CFR 50.19. Standard: 70 ppb.

    Note: this expects the 8-hour rolling-average concentrations as
    input (AERMOD AVE='8-HR' column). Each (receptor, day) max is
    taken to obtain the daily 8-hr max series.
    """
    return nth_highest_daily_max_design_value(
        df_8hr, rank=4, daily="max", n_years=n_years,
        pollutant="O3", averaging_period="8-hour",
    ).assign(form="annual 4th-highest daily max")


def naaqs_compliance_report(
    pollutant: str,
    df: pd.DataFrame,
    *,
    background: Optional[Union[float, dict, pd.Series]] = None,
    n_years: int = 3,
) -> pd.DataFrame:
    """One-stop compliance roll-up: design value + NAAQS comparison.

    Dispatches to the right design-value function for ``pollutant``,
    optionally adds ``background``, joins the NAAQS row, and flags
    receptors that exceed.

    Returns a DataFrame with columns:

    - x, y: receptor coords
    - design_value: numeric DV
    - naaqs_level, units, cfr_reference
    - exceeds: bool

    Supported pollutants: PM2.5 (24-hour), PM10, NO2 (1-hour), SO2,
    O3, plus annual forms via ``pollutant="PM2.5_annual"`` /
    ``"NO2_annual"``.
    """
    from .naaqs import get_naaqs  # local import to avoid cycles

    work = add_background(df, background) if background is not None else df

    pollutant = pollutant.upper()
    if pollutant == "PM2.5" or pollutant == "PM25":
        dv = pm25_24hr_design_value(work, n_years=n_years)
        std = get_naaqs("PM2.5", "24-hour")
    elif pollutant == "PM2.5_ANNUAL" or pollutant == "PM25_ANNUAL":
        dv = annual_mean(work).rename(columns={"concentration": "concentration"})
        # Caller wants multi-year average -> mean of annual means
        dv = (dv.groupby(["x", "y"], as_index=False, sort=False)
              ["concentration"].mean())
        std = get_naaqs("PM2.5", "annual")
    elif pollutant == "PM10":
        dv = pm10_24hr_design_value(work)
        std = get_naaqs("PM10", "24-hour")
    elif pollutant == "NO2":
        dv = no2_1hr_design_value(work, n_years=n_years)
        std = get_naaqs("NO2", "1-hour")
    elif pollutant == "NO2_ANNUAL":
        dv = (annual_mean(work)
              .groupby(["x", "y"], as_index=False, sort=False)
              ["concentration"].mean())
        std = get_naaqs("NO2", "annual")
    elif pollutant == "SO2":
        dv = so2_1hr_design_value(work, n_years=n_years)
        std = get_naaqs("SO2", "1-hour")
    elif pollutant == "O3":
        dv = o3_8hr_design_value(work, n_years=n_years)
        std = get_naaqs("O3", "8-hour")
    else:
        raise ValueError(
            f"Unsupported pollutant {pollutant!r}; supported: PM2.5, "
            f"PM2.5_annual, PM10, NO2, NO2_annual, SO2, O3"
        )

    out = dv.rename(columns={"concentration": "design_value"})
    out["naaqs_level"] = std.level
    out["units"] = std.units
    out["cfr_reference"] = std.cfr_reference
    out["exceeds"] = out["design_value"] > std.level
    return out


__all__ = [
    "PERCENTILE_98_RANK_TABLE",
    "PERCENTILE_99_RANK_TABLE",
    "DesignValue",
    "add_background",
    "annual_mean",
    "naaqs_compliance_report",
    "naaqs_percentile_rank",
    "no2_1hr_design_value",
    "nth_highest_daily_max_design_value",
    "o3_8hr_design_value",
    "pm10_24hr_design_value",
    "pm25_24hr_design_value",
    "so2_1hr_design_value",
]
