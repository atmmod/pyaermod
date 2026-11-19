"""F3: design values follow the meteorological year, as AERMOD does.

AERMOD's year ends on the anniversary of its first met hour (meset.f
IENDMN/IENDDY/IENDHOUR, aermod.f CHK_ENDYR). The design-value functions
read that boundary from the first date of the data (``year_start=None``),
keep calendar years on request (``"calendar"``) and take an explicit
``(month, day)``. Data that start on 1 January give the same numbers as
calendar years, bit for bit.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from pyaermod import design_values as dv

#: The warning every mean built from hourly POSTFILE rows carries.
_HOURLY_MEAN = "an hourly POSTFILE has a row for every hour"


def _frame(values, start):
    days = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame(dict(x=0.0, y=0.0, concentration=values,
                             date=[f"{t:%y%m%d}24" for t in days], ave="24-HR", grp="ALL"))


def _hourly(values_per_day, start):
    """1-HR rows, 24 a day, each day's hours at that day's value plus the hour/100."""
    days = pd.date_range(start, periods=len(values_per_day), freq="D")
    rows = [(f"{d:%y%m%d}{h:02d}", v + h / 100.0)
            for d, v in zip(days, values_per_day) for h in range(1, 25)]
    return pd.DataFrame(dict(x=0.0, y=0.0, concentration=[v for _, v in rows],
                             date=[s for s, _ in rows], ave="1-HR", grp="ALL"))


def _quiet(fn, *args, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return fn(*args, **kwargs)


# ----------------------------------------------------------------------
# The verifier's cases, without the "or a warning" escape
# ----------------------------------------------------------------------

def test_one_july_to_june_year_is_ranked_as_one_year():
    f = _frame(np.arange(1, 366.0), "2019-07-01")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = dv.pm25_24hr_design_value(f, n_years=1)
    # 98th percentile of 365 days is the 8th highest: 358.
    assert out["concentration"].iloc[0] == 358.0
    assert int(out["n_years"].iloc[0]) == 1


def test_pm10_does_not_count_four_july_to_june_years_as_five():
    f = _frame(np.arange(1, 4 * 365 + 1, dtype=float)[::-1], "2019-07-01")
    out = _quiet(dv.pm10_24hr_design_value, f)
    assert int(out["n_years"].iloc[0]) == 4
    assert out["form"].iloc[0].startswith("H2H")


def test_calendar_years_keep_the_old_split():
    f = _frame(np.arange(1, 366.0), "2019-07-01")
    with pytest.warns(UserWarning, match="partial") as caught:
        out = dv.pm25_24hr_design_value(f, n_years=1, year_start="calendar")
    assert out["concentration"].iloc[0] == 271.5
    assert int(out["n_years"].iloc[0]) == 2
    assert any("year_start=None" in str(w.message) for w in caught)


def test_an_explicit_boundary_matches_the_detected_one():
    f = _frame(np.arange(1, 366.0), "2019-07-01")
    detected = dv.pm25_24hr_design_value(f, n_years=1)
    given = dv.pm25_24hr_design_value(f, n_years=1, year_start=(7, 1))
    pd.testing.assert_frame_equal(detected, given)


def test_a_short_final_year_still_warns_that_it_is_partial():
    f = _frame(np.arange(1, 365 + 40.0), "2019-07-01")
    with pytest.warns(UserWarning, match=r"starting 2020-07-01 \(data span 38 days\)"):
        out = dv.pm25_24hr_design_value(f, n_years=2)
    assert int(out["n_years"].iloc[0]) == 2


@pytest.mark.parametrize("bad", ["fiscal", (13, 1), (2, 30), (0, 1), 7, (True, 1), (7,)])
def test_a_boundary_that_is_no_date_is_refused(bad):
    with pytest.raises(ValueError, match="year_start"):
        dv.pm25_24hr_design_value(_frame(np.arange(1, 366.0), "2019-07-01"),
                                  year_start=bad)


# ----------------------------------------------------------------------
# January data: bit-identical to calendar years
# ----------------------------------------------------------------------

def _three_january_years():
    rng = np.random.default_rng(7)
    days = (pd.Timestamp("2021-01-01") - pd.Timestamp("2018-01-01")).days + 120
    return _frame(rng.gamma(2.0, 10.0, size=days), "2018-01-01")


@pytest.mark.parametrize("fn, kwargs", [
    (dv.pm25_24hr_design_value, {}),
    (dv.no2_1hr_design_value, {}),
    (dv.so2_1hr_design_value, {}),
    (dv.pm10_24hr_design_value, {}),
    (dv.nth_highest_daily_max_design_value, {"rank": 3}),
    (dv.annual_mean, {}),
])
def test_january_data_give_the_calendar_year_result(fn, kwargs):
    f = _three_january_years()
    detected = _quiet(fn, f, **kwargs)
    calendar_years = _quiet(fn, f, year_start="calendar", **kwargs)
    pd.testing.assert_frame_equal(detected, calendar_years, check_exact=True)


def test_january_data_give_the_calendar_year_report():
    f = _three_january_years()
    for pollutant in ("PM2.5", "PM2.5_annual", "PM10", "NO2", "SO2"):
        detected = _quiet(dv.naaqs_compliance_report, pollutant, f)
        calendar_years = _quiet(dv.naaqs_compliance_report, pollutant, f,
                                year_start="calendar")
        pd.testing.assert_frame_equal(detected, calendar_years, check_exact=True)


def test_january_hourly_no2_annual_is_the_calendar_year_result():
    rng = np.random.default_rng(3)
    f = _hourly(rng.gamma(2.0, 10.0, size=365 + 366 + 30), "2019-01-01")
    for form in ("highest_year", "multi_year_mean"):
        detected = _quiet(dv.naaqs_compliance_report, "NO2_annual", f, no2_annual=form)
        calendar_years = _quiet(dv.naaqs_compliance_report, "NO2_annual", f,
                                no2_annual=form, year_start="calendar")
        pd.testing.assert_frame_equal(detected, calendar_years, check_exact=True)


def test_january_data_give_the_numbers_they_gave_before():
    # Known answers from calendar-year grouping: 1..365 in 2019 and
    # 366..730 in 2020 (a leap year, 366 days); 8th highest of each year.
    f = _frame(np.arange(1, 732.0), "2019-01-01")
    out = dv.pm25_24hr_design_value(f, n_years=2)
    assert out["concentration"].iloc[0] == ((365 - 7) + (731 - 7)) / 2


# ----------------------------------------------------------------------
# Met years elsewhere
# ----------------------------------------------------------------------

def test_annual_mean_groups_a_july_start_record_by_met_year():
    f = _frame(np.r_[np.full(184, 10.0), np.full(182, 30.0)], "2019-07-01")
    out = dv.annual_mean(f)
    assert out["year"].tolist() == [2019]
    assert out["concentration"].iloc[0] == pytest.approx((184 * 10 + 182 * 30) / 366)
    assert len(dv.annual_mean(f, year_start="calendar")) == 2


def test_mxdybyyr_counts_its_rows_not_calendar_years():
    # Two met years from July 2019: their highest days fall on 2020-03-01
    # and 2020-08-01, one calendar year, but AERMOD wrote one row per year.
    df = pd.DataFrame({"x": 0.0, "y": 0.0, "concentration": [5.0, 7.0], "grp": "ALL",
                       "rank": 1, "date": ["20030124", "20080124"]})
    out = dv.mxdybyyr_design_value(df, rank=1)
    assert int(out["n_years"].iloc[0]) == 2
    assert out["concentration"].iloc[0] == 6.0


# ----------------------------------------------------------------------
# Means of hourly rows carry the POSTFILE limitation warning, once
# ----------------------------------------------------------------------

def _hourly_mean_warnings(fn, *args, **kwargs):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fn(*args, **kwargs)
    return [w for w in caught if _HOURLY_MEAN in str(w.message)]


@pytest.mark.parametrize("fn, kwargs", [
    (dv.pm25_24hr_design_value, {}),
    (dv.pm10_24hr_design_value, {}),
    (dv.annual_mean, {}),
    (dv.nth_highest_daily_max_design_value, {"rank": 1, "daily": "mean"}),
])
def test_a_function_averaging_hourly_rows_warns_once_at_the_callers_line(fn, kwargs):
    caught = _hourly_mean_warnings(fn, _hourly(np.arange(1, 40.0), "2019-01-01"), **kwargs)
    assert len(caught) == 1
    assert caught[0].filename == __file__


@pytest.mark.parametrize("pollutant", ["PM2.5", "PM10", "PM2.5_annual", "NO2_annual"])
def test_the_report_warns_once_for_a_mean_of_hourly_rows(pollutant):
    caught = _hourly_mean_warnings(dv.naaqs_compliance_report, pollutant,
                                   _hourly(np.arange(1, 40.0), "2019-01-01"))
    assert len(caught) == 1
    assert caught[0].filename == __file__


@pytest.mark.parametrize("pollutant", ["NO2", "SO2"])
def test_daily_maxima_do_not_carry_the_hourly_mean_warning(pollutant):
    assert _hourly_mean_warnings(dv.naaqs_compliance_report, pollutant,
                                 _hourly(np.arange(1, 40.0), "2019-01-01")) == []


def test_daily_values_do_not_carry_the_hourly_mean_warning():
    assert _hourly_mean_warnings(dv.pm25_24hr_design_value,
                                 _frame(np.arange(1, 40.0), "2019-01-01")) == []
