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


def test_when_no_year_is_complete_the_whole_record_mean_is_used_with_a_warning():
    df = pd.concat([_hours(2019, 40.0, days=30), _hours(2020, 150.0, days=1)],
                   ignore_index=True)
    with pytest.warns(UserWarning, match="no calendar year"):
        report = naaqs_compliance_report("NO2_annual", df)
    # 30 days at 40 and one day at 150, every hour present.
    assert report["design_value"].tolist() == [pytest.approx((30 * 40.0 + 150.0) / 31)]


def test_the_whole_record_fallback_applies_only_to_receptors_without_a_complete_year():
    df = pd.concat([_hours(2019, 30.0, days=30, x=100.0), _hours(2020, 90.0, days=10, x=100.0),
                    _hours(2019, 40.0), _hours(2020, 150.0, days=1)],
                   ignore_index=True)
    with pytest.warns(UserWarning) as caught:
        report = naaqs_compliance_report("NO2_annual", df)
    messages = [str(w.message) for w in caught]
    assert any("whole record" in m for m in messages)
    assert any("leaves out 2020" in m for m in messages)
    assert report["x"].tolist() == [100.0, 0.0]
    assert report["design_value"].tolist() == [
        pytest.approx((30 * 30.0 + 10 * 90.0) / 40), pytest.approx(40.0)]


def test_one_met_year_across_two_calendar_years_is_the_whole_record_mean():
    # One met year, 2019-07-01 .. 2020-06-30: neither calendar year reaches
    # 75 %, and the higher half-year mean (120) is not an annual mean.
    first = pd.date_range("2019-07-01", "2019-12-31", freq="D")
    second = pd.date_range("2020-01-01", "2020-06-30", freq="D")
    stamps = [f"{d:%y%m%d}{h:02d}" for d in first.append(second) for h in range(1, 25)]
    values = [40.0] * (24 * len(first)) + [120.0] * (24 * len(second))
    df = pd.DataFrame({"x": 0.0, "y": 0.0, "concentration": values,
                       "date": stamps, "ave": "1-HR", "group": "ALL"})
    with pytest.warns(UserWarning, match="whole record") as caught:
        report = naaqs_compliance_report("NO2_annual", df)
    expected = (40.0 * len(first) + 120.0 * len(second)) / (len(first) + len(second))
    assert report["design_value"].tolist() == [pytest.approx(expected)]
    assert report["exceeds"].tolist() == [False]
    assert any("not a calendar-year mean" in str(w.message) for w in caught)


def test_coverage_is_judged_per_receptor():
    df = pd.concat([_hours(2019, 40.0), _hours(2020, 150.0, days=1),
                    _hours(2019, 30.0, x=100.0), _hours(2020, 60.0, x=100.0)],
                   ignore_index=True)
    with pytest.warns(UserWarning, match="2020"):
        report = naaqs_compliance_report("NO2_annual", df)
    by_x = dict(zip(report["x"], report["design_value"]))
    assert by_x[0.0] == pytest.approx(40.0)
    assert by_x[100.0] == pytest.approx(60.0)


# ----------------------------------------------------------------------
# Coverage is counted in the unit of the averaging period
# ----------------------------------------------------------------------

def _rows(ave: str, rows: list[tuple[str, float]]) -> pd.DataFrame:
    """POSTFILE rows at one receptor: ``(YYMMDDHH, value)`` with one ``ave``."""
    return pd.DataFrame({"x": 0.0, "y": 0.0,
                         "concentration": [v for _, v in rows],
                         "date": [d for d, _ in rows], "ave": ave, "group": "ALL"})


def _month_end(year: int, month: int) -> str:
    """AERMOD's end-of-period stamp for a MONTH value: the month's last hour."""
    last = pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)
    return f"{last:%y%m%d}24"


def test_a_monthly_postfile_counts_months_not_days():
    df = _rows("MONTH", [(_month_end(2019, m), 40.0) for m in range(1, 13)]
               + [(_month_end(2020, 1), 150.0)])
    with pytest.warns(UserWarning, match="2020") as caught:
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(40.0)]
    assert report["exceeds"].tolist() == [False]
    assert not any("no year" in str(w.message) for w in caught)


def test_nine_months_of_a_monthly_postfile_make_a_complete_year():
    df = _rows("MONTH", [(_month_end(2019, m), 40.0) for m in range(1, 13)]
               + [(_month_end(2020, m), 150.0) for m in range(1, 10)])
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(150.0)]




def test_a_period_average_is_used_with_a_warning_that_it_is_not_a_calendar_year():
    df = _rows("PERIOD", [("20123124", 45.0)])
    with pytest.warns(UserWarning, match="PERIOD") as caught:
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(45.0)]
    assert not any("no year" in str(w.message) for w in caught)


def test_averaging_periods_with_different_coverage_units_are_refused():
    df = pd.concat([_hours(2019, 40.0),
                    _rows("MONTH", [(_month_end(2019, m), 40.0) for m in range(1, 13)])],
                   ignore_index=True)
    with pytest.raises(ValueError, match="MONTH"):
        naaqs_compliance_report("NO2_annual", df)


@pytest.mark.parametrize("other", ["24-HR", "3-HR"])
def test_averaging_periods_with_the_same_coverage_unit_are_refused_too(other):
    # 1-HR and 24-HR (or 3-HR) rows both end at hour 24; pooling them would
    # otherwise fail on a misleading "two receptors share (x, y)".
    hourly = _hours(2019, 40.0)
    other_rows = hourly.assign(ave=other, concentration=41.0)
    df = pd.concat([hourly, other_rows], ignore_index=True)
    with pytest.raises(ValueError, match="one averaging period") as caught:
        naaqs_compliance_report("NO2_annual", df)
    assert "1-HR" in str(caught.value)
    assert other in str(caught.value)
    assert "share" not in str(caught.value)


def test_the_date_column_is_parsed_once(monkeypatch):
    from pyaermod import design_values as dv

    calls = []
    real = dv._stamp_text_to_date

    def counting(text):
        calls.append(len(text))
        return real(text)

    def refused(col):
        raise AssertionError("the year is derived from the parsed date")

    monkeypatch.setattr(dv, "_stamp_text_to_date", counting)
    monkeypatch.setattr(dv, "_parse_yymmddhh_to_date", refused)
    monkeypatch.setattr(dv, "_parse_yymmddhh_to_year", refused)
    report = naaqs_compliance_report("NO2_annual", _two_years(40.0, 120.0))
    assert report["design_value"].tolist() == [pytest.approx(120.0)]
    assert len(calls) == 1


# ----------------------------------------------------------------------
# An ANNUAL POSTFILE over several years is an average, not a design value
# ----------------------------------------------------------------------

def _annual_postfile(tmp_path, field: str, values=(40.0, 120.0)) -> pd.DataFrame:
    """Read an AERMOD text ANNUAL POSTFILE whose date field is ``field``.

    AERMOD (PSTANN) writes NUMYRS as I8.8 in the date column of an ANNUAL
    POSTFILE, under the label NUM YRS, so five years read as ``00000005``.
    """
    from pyaermod.postfile import read_postfile

    lines = [
        "* AERMOD (26135 ):  NO2 annual                                                          10/19/26",
        "* AERMET ( 26135):                                                                          14:10:38",
        "* MODELING OPTIONS USED:   RegDFAULT  CONC  ELEV  RURAL",
        "*         POST/PLOT FILE OF ANNUAL VALUES FOR SOURCE GROUP: ALL     ",
        f"*         FOR A TOTAL OF   {len(values)} RECEPTORS.",
        "*         FORMAT: (3(1X,F13.5),3(1X,F8.2),2X,A6,2X,A8,2X,I8.8,2X,A8)",
        "*        X             Y      AVERAGE CONC    ZELEV    ZHILL    ZFLAG    AVE     GRP      NUM YRS   NET ID",
        "* ____________  ____________  ____________   ______   ______   ______  ______  ________  ________  ________",
    ]
    for i, v in enumerate(values):
        lines.append(f" {100.0 * i:13.5f} {0.0:13.5f} {v:13.5f} {0.0:8.2f} {0.0:8.2f} "
                     f"{0.0:8.2f}  ANNUAL  ALL       {field}  GRID1   ")
    path = tmp_path / "annual.pst"
    path.write_text("\n".join(lines) + "\n")
    df = read_postfile(path).data
    assert df["ave"].tolist() == ["ANNUAL"] * len(values)
    assert df["date"].tolist() == [field] * len(values)
    return df


def test_a_multi_year_annual_postfile_is_refused_as_a_lower_bound(tmp_path):
    df = _annual_postfile(tmp_path, "00000005")
    with pytest.raises(ValueError, match="lower bound") as caught:
        naaqs_compliance_report("NO2_annual", df)
    message = str(caught.value)
    assert "5 years" in message
    assert "average" in message
    assert "hourly" in message


def test_a_one_year_annual_postfile_is_the_design_value(tmp_path):
    import warnings
    df = _annual_postfile(tmp_path, "00000001")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(40.0), pytest.approx(120.0)]
    assert report["exceeds"].tolist() == [False, True]


def test_an_annual_value_of_unknown_length_is_refused(tmp_path):
    # A date in the NUM YRS column says nothing about how many years the
    # value averages, so it may be a multi-year average.
    df = _rows("ANNUAL", [("19123124", 40.0), ("20123124", 120.0)])
    with pytest.raises(ValueError, match="lower bound"):
        naaqs_compliance_report("NO2_annual", df)


def test_an_annual_year_count_given_as_an_integer_is_read():
    df = _rows("ANNUAL", [(3, 40.0)])
    with pytest.raises(ValueError, match="3 years"):
        naaqs_compliance_report("NO2_annual", df)
    report = naaqs_compliance_report("NO2_annual", _rows("ANNUAL", [(1, 40.0)]))
    assert report["design_value"].tolist() == [pytest.approx(40.0)]


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


# ----------------------------------------------------------------------
# The multi-year mean checks its input as the highest year does
# ----------------------------------------------------------------------

def _no_date_parsing(monkeypatch):
    """Fail the test if anything reads the date column as YYMMDDHH."""
    from pyaermod import design_values as dv

    def refused(col):
        raise AssertionError("an ANNUAL or PERIOD value has no year to parse")

    monkeypatch.setattr(dv, "_parse_yymmddhh_to_date", refused)
    monkeypatch.setattr(dv, "_parse_yymmddhh_to_year", refused)
    monkeypatch.setattr(dv, "_stamp_text_to_date", refused)


@pytest.mark.parametrize("form", ["highest_year", "multi_year_mean"])
def test_hourly_and_annual_rows_together_are_refused_in_either_form(form):
    df = pd.concat([_hours(2019, 40.0), _rows("ANNUAL", [("00000001", 40.0)])],
                   ignore_index=True)
    with pytest.raises(ValueError, match="one averaging period") as caught:
        naaqs_compliance_report("NO2_annual", df, no2_annual=form)
    assert "1-HR" in str(caught.value)
    assert "ANNUAL" in str(caught.value)


def test_the_multi_year_mean_refuses_two_periods_of_the_same_unit():
    hourly = _hours(2019, 40.0)
    df = pd.concat([hourly, hourly.assign(ave="24-HR", concentration=41.0)],
                   ignore_index=True)
    with pytest.raises(ValueError, match="one averaging period"):
        naaqs_compliance_report("NO2_annual", df, no2_annual="multi_year_mean")


def test_a_multi_year_annual_postfile_is_the_multi_year_mean(tmp_path, monkeypatch):
    # AERMOD's ANNUAL value over five years is the average of the five
    # annual means: the multi-year mean itself. NUMYRS is not a year.
    import warnings
    df = _annual_postfile(tmp_path, "00000005")
    _no_date_parsing(monkeypatch)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        report = naaqs_compliance_report("NO2_annual", df, no2_annual="multi_year_mean")
    assert report["x"].tolist() == [0.0, 100.0]
    assert report["design_value"].tolist() == [pytest.approx(40.0), pytest.approx(120.0)]
    assert report["exceeds"].tolist() == [False, True]


def test_an_annual_value_of_unknown_length_is_still_the_multi_year_mean(monkeypatch):
    # Whatever the number of years, an ANNUAL value averages their means.
    df = _rows("ANNUAL", [("20123124", 70.0)])
    _no_date_parsing(monkeypatch)
    report = naaqs_compliance_report("NO2_annual", df, no2_annual="multi_year_mean")
    assert report["design_value"].tolist() == [pytest.approx(70.0)]


def test_a_period_average_is_the_multi_year_mean_with_the_same_warning(monkeypatch):
    df = _rows("PERIOD", [("00000005", 45.0)])
    _no_date_parsing(monkeypatch)
    with pytest.warns(UserWarning, match="PERIOD") as caught:
        report = naaqs_compliance_report("NO2_annual", df, no2_annual="multi_year_mean")
    assert report["design_value"].tolist() == [pytest.approx(45.0)]
    with pytest.warns(UserWarning) as highest:
        naaqs_compliance_report("NO2_annual", df)
    assert [str(w.message) for w in caught] == [str(w.message) for w in highest]


# ----------------------------------------------------------------------
# NUMYRS is a small count; a year-2000 date is not one
# ----------------------------------------------------------------------

@pytest.mark.parametrize("field", ["00123124", "00010101", "00000100"])
def test_a_year_2000_date_is_not_read_as_a_year_count(field):
    # 00123124 is 2000-12-31 hour 24, not 123124 years.
    df = _rows("ANNUAL", [(field, 40.0)])
    with pytest.raises(ValueError, match="unknown number of years") as caught:
        naaqs_compliance_report("NO2_annual", df)
    assert str(int(field)) not in str(caught.value)


@pytest.mark.parametrize(("field", "years"), [("00000099", 99), ("00000002", 2)])
def test_a_year_count_up_to_99_is_read(field, years):
    df = _rows("ANNUAL", [(field, 40.0)])
    with pytest.raises(ValueError, match=f"cover {years} years"):
        naaqs_compliance_report("NO2_annual", df)


def test_a_count_of_zero_years_is_not_a_count():
    df = _rows("ANNUAL", [("00000000", 40.0)])
    with pytest.raises(ValueError, match="unknown number of years"):
        naaqs_compliance_report("NO2_annual", df)


# ----------------------------------------------------------------------
# Hourly coverage is counted in hours (Appendix S: 75 % of the year's hours)
# ----------------------------------------------------------------------

def _hours_each_day(year: int, value: float, hours: range) -> pd.DataFrame:
    """1-HR rows for every day of ``year``, but only at the given ``hours``."""
    dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    stamps = [f"{d:%y%m%d}{h:02d}" for d in dates for h in hours]
    return pd.DataFrame({"x": 0.0, "y": 0.0, "concentration": value,
                         "date": stamps, "ave": "1-HR", "group": "ALL"})


def test_two_hours_a_day_is_not_a_complete_year():
    # Every day has a row, but only 730 of 8760 hours do.
    df = _hours_each_day(2001, 40.0, range(1, 3))
    with pytest.warns(UserWarning, match="hours") as caught:
        naaqs_compliance_report("NO2_annual", df)
    assert any("no calendar year" in str(w.message) for w in caught)


def test_a_year_short_of_three_quarters_of_its_hours_is_left_out():
    # 2020: 18 of 24 hours every day is exactly 75 %; 17 is 70.8 %.
    full = _hours(2019, 40.0)
    df = pd.concat([full, _hours_each_day(2020, 150.0, range(1, 19))], ignore_index=True)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(150.0)]

    df = pd.concat([full, _hours_each_day(2020, 150.0, range(1, 18))], ignore_index=True)
    with pytest.warns(UserWarning, match="2020") as caught:
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(40.0)]
    assert any("hours" in str(w.message) for w in caught)


def test_three_hour_blocks_over_a_whole_year_are_complete():
    # AERMOD's 3-HR values are block averages, eight a day ending 03..24:
    # each covers three hours, so a full year of them covers every hour.
    import warnings
    dates = pd.date_range("2019-01-01", "2019-12-31", freq="D")
    stamps = [f"{d:%y%m%d}{h:02d}" for d in dates for h in range(3, 25, 3)]
    df = pd.DataFrame({"x": 0.0, "y": 0.0, "concentration": 40.0,
                       "date": stamps, "ave": "3-HR", "group": "ALL"})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        report = naaqs_compliance_report("NO2_annual", df)
    assert report["design_value"].tolist() == [pytest.approx(40.0)]


# ----------------------------------------------------------------------
# A date-keyed background cannot be matched to ANNUAL or PERIOD values
# ----------------------------------------------------------------------

@pytest.mark.parametrize("ave", ["ANNUAL", "PERIOD"])
@pytest.mark.parametrize("make", [dict, pd.Series])
def test_a_date_keyed_background_on_annual_or_period_rows_is_refused(ave, make):
    df = _rows(ave, [("00000001", 40.0)])
    background = make({"19010101": 5.0})
    with pytest.raises(ValueError, match="single number") as caught:
        naaqs_compliance_report("NO2_annual", df, background=background,
                                no2_annual="multi_year_mean")
    assert ave in str(caught.value)


def test_a_uniform_background_on_annual_rows_is_added():
    df = _rows("ANNUAL", [("00000001", 40.0)])
    report = naaqs_compliance_report("NO2_annual", df, background=10.0)
    assert report["design_value"].tolist() == [pytest.approx(50.0)]


# ----------------------------------------------------------------------
# A date that is not a YYMMDDHH stamp gets a plain explanation
# ----------------------------------------------------------------------

@pytest.mark.parametrize("form", ["highest_year", "multi_year_mean"])
@pytest.mark.parametrize("bad", ["2001-01-01", "abcdefgh", "19133101", "19010125"])
def test_a_date_that_is_not_a_stamp_is_named(form, bad):
    df = _hours(2019, 40.0)
    df.loc[5, "date"] = bad
    with pytest.raises(ValueError, match="YYMMDDHH") as caught:
        naaqs_compliance_report("NO2_annual", df, no2_annual=form)
    assert bad in str(caught.value)


# ----------------------------------------------------------------------
# The input is checked and deduplicated once
# ----------------------------------------------------------------------

@pytest.mark.parametrize("form", ["highest_year", "multi_year_mean"])
def test_the_input_is_checked_and_deduplicated_once(form, monkeypatch):
    from pyaermod import design_values as dv

    calls = {"group": 0, "dedupe": 0}
    group, dedupe = dv._one_source_group, dv._dedupe_receptors

    def counting_group(df):
        calls["group"] += 1
        return group(df)

    def counting_dedupe(df):
        calls["dedupe"] += 1
        return dedupe(df)

    monkeypatch.setattr(dv, "_one_source_group", counting_group)
    monkeypatch.setattr(dv, "_dedupe_receptors", counting_dedupe)
    report = naaqs_compliance_report("NO2_annual", _two_years(40.0, 120.0), no2_annual=form)
    assert report["design_value"].tolist() == [
        pytest.approx(120.0 if form == "highest_year" else 80.0)]
    assert calls == {"group": 1, "dedupe": 1}


# ----------------------------------------------------------------------
# A numeric date column (a CSV round trip) reads like the text one
# ----------------------------------------------------------------------

def _as_float_dates(df: pd.DataFrame) -> pd.DataFrame:
    """``df`` with its date column as float64, as a CSV with a gap reads back."""
    return df.assign(date=df["date"].astype(float))


@pytest.mark.parametrize(("form", "expected"),
                         [("highest_year", 120.0), ("multi_year_mean", 80.0)])
def test_a_float_date_column_is_read_like_the_text_one(form, expected):
    # 2005 reads back as 5010101.0: the leading zero is gone as well.
    df = pd.concat([_hours(2005, 40.0), _hours(2006, 120.0)], ignore_index=True)
    floats = _as_float_dates(df)
    assert floats["date"].dtype == "float64"
    assert floats["date"].iloc[0] == 5010101.0
    report = naaqs_compliance_report("NO2_annual", floats, no2_annual=form)
    assert report["design_value"].tolist() == [pytest.approx(expected)]


def test_a_csv_round_trip_with_a_missing_date_still_reads_the_dates(tmp_path):
    # One blank date in a CSV turns the whole column to float64, and it
    # stays float after the blank row is dropped.
    df = pd.concat([_hours(2005, 40.0), _hours(2006, 120.0)], ignore_index=True)
    df.loc[3, "date"] = ""
    path = tmp_path / "post.csv"
    df.to_csv(path, index=False)
    back = pd.read_csv(path).dropna(subset=["date"])
    assert back["date"].dtype == "float64"
    report = naaqs_compliance_report("NO2_annual", back)
    assert report["design_value"].tolist() == [pytest.approx(120.0)]


@pytest.mark.parametrize("form", ["highest_year", "multi_year_mean"])
@pytest.mark.parametrize(("bad", "shown"), [(19010101.5, "19010101.5"),
                                            (float("nan"), "nan")])
def test_a_float_date_that_is_not_a_stamp_is_named(form, bad, shown):
    df = _as_float_dates(_hours(2019, 40.0))
    df.loc[5, "date"] = bad
    with pytest.raises(ValueError, match="YYMMDDHH") as caught:
        naaqs_compliance_report("NO2_annual", df, no2_annual=form)
    assert shown in str(caught.value)


def test_an_annual_year_count_given_as_a_float_is_read():
    df = _rows("ANNUAL", [(5.0, 40.0)])
    with pytest.raises(ValueError, match="cover 5 years"):
        naaqs_compliance_report("NO2_annual", df)
    report = naaqs_compliance_report("NO2_annual", _rows("ANNUAL", [(1.0, 40.0)]))
    assert report["design_value"].tolist() == [pytest.approx(40.0)]


def test_a_fractional_annual_year_count_is_not_a_count():
    df = _rows("ANNUAL", [(1.5, 40.0)])
    with pytest.raises(ValueError, match="unknown number of years"):
        naaqs_compliance_report("NO2_annual", df)


# ----------------------------------------------------------------------
# The averaging periods are read once
# ----------------------------------------------------------------------

def test_the_averaging_periods_are_read_once(monkeypatch):
    from pyaermod import design_values as dv

    calls = []
    real = dv._ave_names

    def counting(df):
        calls.append(len(df))
        return real(df)

    monkeypatch.setattr(dv, "_ave_names", counting)
    df = _two_years(40.0, 120.0)
    background = dict.fromkeys(df["date"], 1.0)
    report = naaqs_compliance_report("NO2_annual", df, background=background)
    assert report["design_value"].tolist() == [pytest.approx(121.0)]
    assert len(calls) == 1


# ----------------------------------------------------------------------
# The date column is read as text once
# ----------------------------------------------------------------------

@pytest.mark.parametrize(("form", "unit"), [
    ("highest_year", "1-HR"), ("multi_year_mean", "1-HR"),
    ("highest_year", "24-HR"), ("highest_year", "MONTH"),
])
def test_the_date_column_is_read_as_text_once(form, unit, monkeypatch):
    # A date-keyed background reads the dates as YYMMDDHH text to match
    # them; the design value reuses that text instead of reading it again.
    from pyaermod import design_values as dv

    if unit == "1-HR":
        df = _two_years(40.0, 120.0)
    elif unit == "24-HR":
        df = pd.concat([_days(2019, 40.0), _days(2020, 120.0)], ignore_index=True)
    else:
        df = _rows("MONTH", [(_month_end(y, m), v) for y, v in ((2019, 40.0), (2020, 120.0))
                             for m in range(1, 13)])
    calls = []
    real = dv._date_text

    def counting(col):
        calls.append(len(col))
        return real(col)

    monkeypatch.setattr(dv, "_date_text", counting)
    background = dict.fromkeys(df["date"], 1.0)
    report = naaqs_compliance_report("NO2_annual", df, background=background,
                                     no2_annual=form)
    expected = 121.0 if form == "highest_year" else 81.0
    assert report["design_value"].tolist() == [pytest.approx(expected)]
    # once for the background's keys, once for the frame's dates
    assert calls == [len(background), len(df)]


def test_a_background_on_a_frame_with_repeated_index_labels_is_matched_by_row():
    # pd.concat without ignore_index repeats index labels; the dates read
    # for the background must still line up row by row with the design value.
    df = pd.concat([_hours(2019, 40.0), _hours(2020, 120.0)])
    assert df.index.duplicated().any()
    background = {d: (1.0 if d.startswith("19") else 2.0) for d in df["date"]}
    report = naaqs_compliance_report("NO2_annual", df, background=background)
    assert report["design_value"].tolist() == [pytest.approx(122.0)]


# ----------------------------------------------------------------------
# A binary ANNUAL POSTFILE is an ANNUAL value, not N-hour blocks
# ----------------------------------------------------------------------

def _binary_annual(tmp_path, numyrs: int, values=(40.0, 120.0)):
    """A binary (UNFORM) ANNUAL POSTFILE as PSTANN in output.f writes it.

    One Fortran sequential record: KURDAT (the run's last hour), NUMYRS,
    the group ID (CHARACTER*8) and one REAL*8 per receptor, between two
    4-byte record-length markers.
    """
    import struct

    payload = struct.pack("<ii8s", 21123124, numyrs, b"ALL     ")
    payload += struct.pack(f"<{len(values)}d", *values)
    marker = struct.pack("<i", len(payload))
    path = tmp_path / "annual.bin"
    path.write_bytes(marker + payload + marker)
    return path


def test_a_binary_multi_year_annual_postfile_is_refused_like_the_text_one(tmp_path):
    from pyaermod.postfile import read_postfile

    path = _binary_annual(tmp_path, 5)
    # The file cannot say whether 5 is NUMYRS or a PERIOD's hours.
    with pytest.raises(ValueError, match="averaging_period"):
        read_postfile(path)
    binary = read_postfile(path, averaging_period="ANNUAL").data
    text = _annual_postfile(tmp_path, "00000005")
    assert binary["ave"].tolist() == text["ave"].tolist()
    assert binary["date"].tolist() == text["date"].tolist()
    with pytest.raises(ValueError, match="lower bound") as caught:
        naaqs_compliance_report("NO2_annual", binary)
    assert "5 years" in str(caught.value)
    report = naaqs_compliance_report("NO2_annual", binary, no2_annual="multi_year_mean")
    assert report["design_value"].tolist() == [pytest.approx(40.0), pytest.approx(120.0)]


def test_a_binary_one_year_annual_postfile_is_the_design_value(tmp_path):
    from pyaermod.postfile import read_postfile

    binary = read_postfile(_binary_annual(tmp_path, 1), averaging_period="ANNUAL").data
    report = naaqs_compliance_report("NO2_annual", binary)
    assert report["design_value"].tolist() == [pytest.approx(40.0), pytest.approx(120.0)]


@pytest.mark.parametrize("form", ["highest_year", "multi_year_mean"])
@pytest.mark.parametrize("ave", ["5-HR", "720-HR", "0-HR", "48-HR"])
def test_an_hour_count_aermod_never_averages_over_is_refused(form, ave):
    # AERMOD's short-term periods are 1, 2, 3, 4, 6, 8, 12 and 24 hours; a
    # frame labelled otherwise is a binary ANNUAL or PERIOD file whose
    # NUMYRS or hours were read as an averaging period.
    df = _rows(ave, [("21123124", 40.0)])
    with pytest.raises(ValueError, match="averaging_period='ANNUAL'") as caught:
        naaqs_compliance_report("NO2_annual", df, no2_annual=form)
    message = str(caught.value)
    assert ave in message
    assert "1, 2, 3, 4, 6, 8, 12" in message
