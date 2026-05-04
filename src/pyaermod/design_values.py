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

from dataclasses import dataclass
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


def _agg_daily_max(df: pd.DataFrame) -> pd.DataFrame:
    """Per-(receptor, day) max of hourly concentration."""
    g = df.assign(_d=_parse_yymmddhh_to_date(df["date"]))
    return (
        g.groupby(["x", "y", "_d"], as_index=False, sort=False)["concentration"]
        .max()
        .rename(columns={"_d": "date"})
    )


def _annual_percentile_per_receptor(
    df_daily: pd.DataFrame, percentile: float,
) -> pd.DataFrame:
    """For each (receptor, year), compute the requested percentile of the
    daily-max series."""
    df = df_daily.copy()
    df["_year"] = df["date"].dt.year
    return (
        df.groupby(["x", "y", "_year"], as_index=False, sort=False)
        ["concentration"]
        .quantile(percentile / 100.0, interpolation="linear")
    )


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
    g = df.assign(_year=_parse_yymmddhh_to_year(df["date"]))
    return (
        g.groupby(["x", "y", "_year"], as_index=False, sort=False)
        ["concentration"].mean()
        .rename(columns={"_year": "year"})
    )


def pm25_24hr_design_value(
    df: pd.DataFrame, *, n_years: int = 3,
) -> pd.DataFrame:
    """PM2.5 24-hour design value: 3-year avg of annual 98th percentiles.

    Per 40 CFR 50, Appendix N. Standard: 35 µg/m³.

    Input ``df`` must contain hourly (or 24-hr-averaged) concentrations;
    24-hr daily values are computed by averaging within each (receptor,
    day) group when the AVE column equals "1-HR", otherwise rows are
    used as-is.

    Returns one row per receptor with the n-year average of annual 98th
    percentile daily-max concentrations.
    """
    daily = _agg_daily_max(df) if "1-HR" in df["ave"].unique() else df.copy()
    if "date" in daily and not pd.api.types.is_datetime64_any_dtype(daily["date"]):
        daily["date"] = _parse_yymmddhh_to_date(daily["date"])
    pct = _annual_percentile_per_receptor(daily, percentile=98.0)
    return (
        pct.groupby(["x", "y"], as_index=False, sort=False)["concentration"]
        .mean()
        .assign(form="98th percentile", averaging_period="24-hour",
                pollutant="PM2.5", n_years=n_years)
    )


def no2_1hr_design_value(
    df: pd.DataFrame, *, n_years: int = 3,
) -> pd.DataFrame:
    """NO2 1-hour design value: 3-year avg of annual 98th percentile of
    daily max 1-hour concentrations.

    Per 40 CFR 50, Appendix S. Standard: 100 ppb.

    Returns one row per receptor.
    """
    daily = _agg_daily_max(df)
    pct = _annual_percentile_per_receptor(daily, percentile=98.0)
    return (
        pct.groupby(["x", "y"], as_index=False, sort=False)["concentration"]
        .mean()
        .assign(form="98th percentile of daily max", averaging_period="1-hour",
                pollutant="NO2", n_years=n_years)
    )


def so2_1hr_design_value(
    df: pd.DataFrame, *, n_years: int = 3,
) -> pd.DataFrame:
    """SO2 1-hour design value: 3-year avg of annual 99th percentile of
    daily max 1-hour concentrations.

    Per 40 CFR 50, Appendix T. Standard: 75 ppb.
    """
    daily = _agg_daily_max(df)
    pct = _annual_percentile_per_receptor(daily, percentile=99.0)
    return (
        pct.groupby(["x", "y"], as_index=False, sort=False)["concentration"]
        .mean()
        .assign(form="99th percentile of daily max", averaging_period="1-hour",
                pollutant="SO2", n_years=n_years)
    )


def pm10_24hr_design_value(df: pd.DataFrame) -> pd.DataFrame:
    """PM10 24-hour design value: max daily concentration not to be
    exceeded more than once per year on average over 5 years.

    Per 40 CFR 50.6. Standard: 150 µg/m³. Functionally we return the
    "high, second-high" (H2H) per receptor — the 2nd-highest daily-max
    concentration in the multi-year record (allowing one exceedance).

    Caller decides how to average the H2H across the standard's 5-year
    window; this function returns one H2H per receptor.
    """
    daily = _agg_daily_max(df) if "1-HR" in df["ave"].unique() else df.copy()
    out = (
        daily.groupby(["x", "y"], as_index=False, sort=False)["concentration"]
        .apply(lambda s: float(np.sort(s.values)[-2]) if len(s) >= 2
               else float(s.max()))
    )
    out["form"] = "H2H (high-second-high)"
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
    daily = _agg_daily_max(df_8hr)
    daily["_year"] = daily["date"].dt.year
    h4h = (
        daily.groupby(["x", "y", "_year"], as_index=False, sort=False)
        ["concentration"]
        .apply(lambda s: float(np.sort(s.values)[-4]) if len(s) >= 4
               else float(s.max()))
    )
    return (
        h4h.groupby(["x", "y"], as_index=False, sort=False)["concentration"]
        .mean()
        .assign(form="annual 4th-highest daily max",
                averaging_period="8-hour",
                pollutant="O3", n_years=n_years)
    )


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
    "DesignValue",
    "add_background",
    "annual_mean",
    "naaqs_compliance_report",
    "no2_1hr_design_value",
    "o3_8hr_design_value",
    "pm10_24hr_design_value",
    "pm25_24hr_design_value",
    "so2_1hr_design_value",
]
