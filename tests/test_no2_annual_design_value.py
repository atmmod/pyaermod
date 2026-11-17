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


def _two_years(first: float, second: float) -> pd.DataFrame:
    """Hourly values at one receptor: ``first`` all of 2019, ``second`` all of 2020."""
    rows = []
    for year, value in ((19, first), (20, second)):
        for day in range(1, 29):
            for hour in range(1, 25):
                rows.append({"x": 0.0, "y": 0.0, "concentration": value,
                             "date": f"{year:02d}01{day:02d}{hour:02d}",
                             "group": "ALL"})
    return pd.DataFrame(rows)


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
