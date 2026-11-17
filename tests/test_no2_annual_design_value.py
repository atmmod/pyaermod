"""The annual NO2 design value is one calendar year's mean (review H6).

40 CFR 50.11(e) and Appendix S: the annual NO2 standard is met when the
annual mean of a calendar year is at or below 53 ppb, so the design value
is a single year's mean, unlike PM2.5, whose annual form is a three-year
average of annual means (Appendix N). With several years of met data the
modelled design value is therefore the highest of the annual means; the
average of the annual means can be below it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from pyaermod.design_values import naaqs_compliance_report
from pyaermod.gui_v2 import run_results as rr


def _hours(year: int, value: float, *, days: int | None = None,
           x: float = 0.0) -> pd.DataFrame:
    """Hourly POSTFILE rows at one receptor for the first ``days`` days of ``year``.

    ``days=None`` covers the whole calendar year. AERMOD numbers the
    hours 01..24 within the day.
    """
    dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    if days is not None:
        dates = dates[:days]
    stamps = [f"{d:%y%m%d}{h:02d}" for d in dates for h in range(1, 25)]
    return pd.DataFrame({"x": x, "y": 0.0, "concentration": value,
                         "date": stamps, "ave": "1-HR", "group": "ALL"})


def _days(year: int, value: float, *, days: int | None = None) -> pd.DataFrame:
    """Daily (24-HR) POSTFILE rows at one receptor, one per day."""
    dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    if days is not None:
        dates = dates[:days]
    return pd.DataFrame({"x": 0.0, "y": 0.0, "concentration": value,
                         "date": [f"{d:%y%m%d}24" for d in dates],
                         "ave": "24-HR", "group": "ALL"})


def _two_years(first: float, second: float) -> pd.DataFrame:
    """Hourly values at one receptor: ``first`` all of 2019, ``second`` all of 2020."""
    return pd.concat([_hours(2019, first), _hours(2020, second)], ignore_index=True)


def test_the_design_value_is_the_highest_years_mean():
    report = naaqs_compliance_report("NO2_annual", _two_years(40.0, 120.0))
    assert report["design_value"].tolist() == [pytest.approx(120.0)]
    assert report["exceeds"].tolist() == [True]          # 100 µg/m³ is 53 ppb


def test_the_multi_year_average_is_available_on_request():
    report = naaqs_compliance_report("NO2_annual", _two_years(40.0, 120.0),
                                     no2_annual="multi_year_mean")
    assert report["design_value"].tolist() == [pytest.approx(80.0)]
    assert report["exceeds"].tolist() == [False]


def test_an_unknown_annual_form_is_refused():
    with pytest.raises(ValueError, match="no2_annual"):
        naaqs_compliance_report("NO2_annual", _two_years(1.0, 2.0), no2_annual="median")


def test_pm25_annual_is_still_the_multi_year_average():
    report = naaqs_compliance_report("PM2.5_annual", _two_years(4.0, 12.0))
    assert report["design_value"].tolist() == [pytest.approx(8.0)]


# ----------------------------------------------------------------------
# Only complete years count towards the highest year (Appendix S, 75 %)
# ----------------------------------------------------------------------

def test_one_day_of_a_new_year_does_not_set_the_design_value():
    df = pd.concat([_hours(2019, 40.0), _hours(2020, 150.0, days=1)], ignore_index=True)
    with pytest.warns(UserWarning, match="2020"):
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(40.0)]
    assert report["exceeds"].tolist() == [False]


def test_a_year_with_three_quarters_of_its_days_counts():
    # 2020 is a leap year: 275 of 366 days is 75.1 %, 274 is 74.9 %.
    df = pd.concat([_hours(2019, 40.0), _hours(2020, 150.0, days=275)], ignore_index=True)
    report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(150.0)]

    df = pd.concat([_hours(2019, 40.0), _hours(2020, 150.0, days=274)], ignore_index=True)
    with pytest.warns(UserWarning, match="2020"):
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(40.0)]


def test_a_year_short_of_three_quarters_is_left_out_of_daily_input_too():
    df = pd.concat([_days(2019, 40.0), _days(2020, 150.0, days=30)], ignore_index=True)
    with pytest.warns(UserWarning, match="2020"):
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(40.0)]


def test_complete_years_raise_no_warning():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        report = naaqs_compliance_report("NO2_annual", _two_years(40.0, 120.0))
    assert report["design_value"].tolist() == [pytest.approx(120.0)]


def test_when_no_year_is_complete_all_years_are_used_with_a_warning():
    df = pd.concat([_hours(2019, 40.0, days=30), _hours(2020, 150.0, days=1)],
                   ignore_index=True)
    with pytest.warns(UserWarning, match="no year"):
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(150.0)]


def test_coverage_is_judged_per_receptor():
    df = pd.concat([_hours(2019, 40.0), _hours(2020, 150.0, days=1),
                    _hours(2019, 30.0, x=100.0), _hours(2020, 60.0, x=100.0)],
                   ignore_index=True)
    with pytest.warns(UserWarning, match="2020"):
        report = naaqs_compliance_report("NO2_annual", df)
    by_x = dict(zip(report["x"], report["design_value"]))
    assert by_x[0.0] == pytest.approx(40.0)
    assert by_x[100.0] == pytest.approx(60.0)


def test_the_multi_year_mean_still_averages_every_year():
    import warnings
    df = pd.concat([_hours(2019, 40.0), _hours(2020, 150.0, days=1)], ignore_index=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        report = naaqs_compliance_report("NO2_annual", df, no2_annual="multi_year_mean")
    assert report["design_value"].tolist() == [pytest.approx(95.0)]


# ----------------------------------------------------------------------
# The GUI's NAAQS check on AERMOD's ANNUAL table
# ----------------------------------------------------------------------

def _results(value: float, years: int):
    title = ("THE SUMMARY OF MAXIMUM ANNUAL RESULTS AVERAGED OVER "
             f"{years} YEARS")
    annual = SimpleNamespace(units="ug/m^3", max_value=value, max_location=(10.0, 20.0),
                             title=title, output_type="CONC", averaging_period="ANNUAL")
    return SimpleNamespace(run_info=SimpleNamespace(pollutant_id="NO2"),
                           concentrations={"ANNUAL": annual}, summaries=[annual])


def _annual_check(value: float, years: int) -> rr.NaaqsCheck:
    [check] = [c for c in rr.naaqs_checks(_results(value, years))
               if c.standard.averaging_period == "annual"]
    return check


def test_one_year_annual_table_is_the_design_value():
    check = _annual_check(50.0, 1)
    assert check.basis == "design value"
    assert check.verdict == "Below the NAAQS"


def test_a_multi_year_average_below_the_level_is_not_called_below_the_naaqs():
    check = _annual_check(90.0, 5)
    assert check.basis == "lower bound"
    assert check.value == pytest.approx(90.0)
    assert "Below the NAAQS" not in check.verdict
    assert "highest single year" in check.verdict
    assert "average of 5 annual means" in check.how


def test_a_multi_year_average_above_the_level_is_above_the_naaqs():
    check = _annual_check(120.0, 5)
    assert check.basis == "lower bound"
    assert check.verdict.startswith("Above the NAAQS")


def test_pm25_multi_year_annual_table_is_still_the_design_value():
    results = _results(8.0, 5)
    results.run_info.pollutant_id = "PM25"
    [check] = [c for c in rr.naaqs_checks(results)
               if c.standard.averaging_period == "annual"]
    assert check.basis == "design value"


# ----------------------------------------------------------------------
# The caption under the NAAQS table explains only the bases it shows
# ----------------------------------------------------------------------

def test_the_caption_explains_a_lower_bound_only_when_one_is_shown():
    design = _annual_check(50.0, 1)
    lower = _annual_check(90.0, 5)
    caption = rr.naaqs_caption([design])
    assert caption.startswith("A screening comparison uses the highest value")
    assert "lower bound" not in caption.lower()
    assert "A lower bound is AERMOD's average" in rr.naaqs_caption([design, lower])
