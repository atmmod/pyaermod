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

import calendar
import math
import warnings
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

import numpy as np
import pandas as pd

from ._fortran import fortran_float

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

    Used for the PM2.5 annual NAAQS (40 CFR 50.18), whose form is the
    three-year average of annual means, and the NO2 annual NAAQS (40 CFR
    50.11(e)), whose form is one calendar year's mean. This returns the
    mean of each year at each receptor; :func:`naaqs_compliance_report`
    combines the years in the form of each standard.

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
    """
    work = _one_source_group(df)
    sel = work[work["rank"] == rank].copy()
    if sel.empty:
        raise ValueError(
            f"no rank-{rank} rows; the deck's RECTABLE range must reach "
            f"rank {rank} for MXDYBYYR to write it"
        )
    sel["_year"] = _parse_yymmddhh_to_year(sel["date"])
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
    period = "24-hour" if key in ("PM2.5", "PM25") else "1-hour"
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


def _coverage_unit(ave: object) -> str:
    """The unit a year's coverage is counted in for one POSTFILE ``ave``.

    ``"month"`` for MONTH values, ``"year"`` for ANNUAL values (each is a
    whole year's mean), ``"period"`` for PERIOD values (one mean over the
    whole run) and ``"day"`` for everything else: 1-HR, 3-HR, 24-HR ...
    """
    text = str(ave).strip().upper()
    return {"MONTH": "month", "ANNUAL": "year", "PERIOD": "period"}.get(text, "day")


def _annual_numyrs(date_col: pd.Series) -> Optional[int]:
    """The number of years behind ANNUAL POSTFILE rows, or None if unknown.

    AERMOD writes NUMYRS (I8.8) where a POSTFILE has the date, so a value
    averaged over five years reads ``00000005``. A field that is a date, or
    is not one count shared by every row, says nothing about the length.
    """
    text = date_col.astype(str).str.strip()
    if text.empty or not text.str.fullmatch(r"\d{1,8}").all():
        return None
    counts = text.map(int).unique()
    # NUMYRS is a count of met years, so a small number; the smallest real
    # YYMMDDHH stamp, 00010101 (2000-01-01 hour 01), reads 10101. Anything
    # outside 1-99 is a date (00123124 is 2000-12-31 hour 24), not a count.
    if len(counts) != 1 or not 1 <= counts[0] <= 99:
        return None
    return int(counts[0])


def _no2_annual_input(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """The rows behind an annual NO2 design value and their coverage unit.

    Both forms of :func:`naaqs_compliance_report`'s annual NO2 value read
    their input through this. The frame must hold one source group and one
    averaging period (one ``ave`` value): rows of different periods are
    different quantities, and averaging or ranking them together means
    nothing. Without an ``ave`` column the rows are taken as sub-annual
    values, counted in days.
    """
    work = _one_source_group(df)
    if "ave" in work.columns:
        aves = sorted(pd.unique(work["ave"].astype(str).str.strip().str.upper()))
    else:
        aves = []
    if len(aves) > 1:
        raise ValueError(
            "an annual NO2 mean needs one averaging period; found "
            f"{', '.join(aves)}. Pass one averaging period, e.g. "
            f"df[df['ave'] == {aves[0]!r}]."
        )
    return work, _coverage_unit(aves[0]) if aves else "day"


def _no2_annual_design_value(df: pd.DataFrame, form: str) -> pd.DataFrame:
    """Annual NO2 design value per receptor in ``form`` (see _NO2_ANNUAL_FORMS).

    An ANNUAL value over N years is AERMOD's average of the N years'
    annual means: in the ``"multi_year_mean"`` form it is the design value
    itself, whatever N is. In the ``"highest_year"`` form it is a whole
    year's mean only when the run covered one year; over several years it
    is a lower bound on the highest year, so it is refused, as is one whose
    number of years cannot be read. A PERIOD value is one mean over the
    whole run, which cannot be split into calendar years; either form uses
    it as it is, with a warning. Neither has a date to parse: the date
    field holds a count.

    Sub-annual values are combined by year: averaged across every year
    present for ``"multi_year_mean"``, and for ``"highest_year"`` as
    :func:`_no2_highest_complete_year` describes.
    """
    work, unit = _no2_annual_input(df)
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

    # Dedupe after the period check: rows of different periods that end on
    # the same hour would otherwise read as repeats of each other.
    work = _dedupe_receptors(work)
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
    if form == "multi_year_mean":
        return (annual_mean(work)
                .groupby(receptor, as_index=False, sort=False)
                ["concentration"].mean())
    return _no2_highest_complete_year(work, unit)


def _no2_highest_complete_year(work: pd.DataFrame, unit: str) -> pd.DataFrame:
    """Highest annual mean per receptor, over the years at least 75 % covered.

    ``work`` holds sub-annual rows of one averaging period, already checked
    and deduplicated by :func:`_no2_annual_design_value`. Coverage is
    counted in ``unit``: the share of the calendar year's days (365 or 366)
    with at least one row for that receptor for hourly to 24-hour values,
    so it reads the same from hourly and daily POSTFILEs, and the share of
    its 12 months for MONTH values.

    A year below 75 % is left out with a warning. A receptor with no
    calendar year at 75 % gets the mean over its whole record instead,
    also with a warning, rather than its highest partial year.
    """
    receptor = ["x", "y"]
    stamp = _parse_yymmddhh_to_date(work["date"])
    if stamp.isna().any():
        bad = work.loc[stamp.isna(), "date"].astype(str).unique()[:4]
        raise ValueError(
            "the date column must hold AERMOD YYMMDDHH stamps; cannot read "
            f"{', '.join(bad)}."
        )
    work = work.assign(_year=stamp.dt.year,
                       _unit=stamp if unit == "day" else stamp.dt.month)
    keys = [*receptor, "_year"]
    means = work.groupby(keys, as_index=False, sort=False).agg(
        concentration=("concentration", "mean"), _n=("_unit", "nunique"))
    if unit == "day":
        whole = means["_year"].map(lambda y: 366 if calendar.isleap(y) else 365)
    else:
        whole = pd.Series(12, index=means.index)
    means["_ok"] = means["_n"] >= _NO2_ANNUAL_COMPLETENESS * whole

    any_ok = means.groupby(receptor, sort=False)["_ok"].transform("any")
    noun = "months" if unit == "month" else "days"
    dropped = sorted({int(y) for y in means.loc[~means["_ok"] & any_ok, "_year"]})
    if dropped:
        warnings.warn(
            "the annual NO2 design value leaves out "
            f"{', '.join(map(str, dropped))}: data on fewer than 75% of the "
            f"year's {noun} at some receptor (40 CFR 50 Appendix S) is too "
            "little for a valid annual mean.",
            stacklevel=4,
        )
    highest = (means[means["_ok"]]
               .groupby(receptor, as_index=False, sort=False)
               ["concentration"].max())
    if any_ok.all():
        return highest

    warnings.warn(
        f"no calendar year has data on at least 75% of its {noun} (40 CFR 50 "
        "Appendix S) at some receptor, so its annual NO2 design value is the "
        "mean over the whole record, not a calendar-year mean.",
        stacklevel=4,
    )
    incomplete = means.loc[~any_ok, receptor].drop_duplicates()
    whole_record = (work.merge(incomplete, on=receptor)
                    .groupby(receptor, as_index=False, sort=False)
                    ["concentration"].mean())
    # Back in the receptors' order of appearance.
    return (means[receptor].drop_duplicates()
            .merge(pd.concat([highest, whole_record]), on=receptor))


def naaqs_compliance_report(
    pollutant: str,
    df: pd.DataFrame,
    *,
    background: Optional[Union[float, dict, pd.Series]] = None,
    n_years: int = 3,
    no2_annual: str = "highest_year",
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
    never with a level in ppb.

    Supported pollutants: PM2.5 (24-hour), PM10, NO2 (1-hour), SO2,
    O3, plus annual forms via ``pollutant="PM2.5_annual"`` /
    ``"NO2_annual"``.

    The annual PM2.5 form is the average of the annual means (40 CFR 50.18,
    Appendix N). The annual NO2 standard is a single calendar year's mean
    (40 CFR 50.11(e), Appendix S), so with several years of data
    ``no2_annual="highest_year"`` (the default) takes the highest year's
    mean at each receptor. Only years with data on at least 75% of their
    days count (Appendix S treats an annual mean as valid from 75%
    coverage), so a few days of a following year cannot set the design
    value; the years left out are named in a :class:`UserWarning`. The
    frame must hold one averaging period (one ``ave`` value). A MONTH
    POSTFILE counts months instead of days, and a PERIOD mean, which covers
    the whole run rather than one calendar year, is used as it is with a
    warning. An ANNUAL value is used only when it covers one year: over
    several years (AERMOD writes NUMYRS where the date would be) it is the
    average of the years' means, a lower bound on the design value, so it
    raises :class:`ValueError`, as does an ANNUAL value whose number of
    years cannot be read. If no calendar year at a receptor reaches 75%
    (one met year starting in July, say), the design value there is the
    mean over its whole record and a warning says so.
    ``no2_annual="multi_year_mean"`` averages the years instead,
    which some reviewing agencies accept for five years of NWS met data;
    it can be below the highest year, and it averages every year present,
    complete or not. It too needs one averaging period. An ANNUAL value,
    which over several years is already the average of the years' means,
    is that mean as it is, whatever its number of years; a PERIOD mean is
    used as it is, with the same warning as above.
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
        if no2_annual not in _NO2_ANNUAL_FORMS:
            raise ValueError(f"no2_annual must be one of {', '.join(_NO2_ANNUAL_FORMS)}; "
                             f"got {no2_annual!r}")
        dv = _no2_annual_design_value(work, no2_annual)
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
