"""The period an AERMET surface file covers, and the ANNUAL check built on it.

``SurfaceFilePeriod.complete_years`` claims to be AERMOD's NUMYRS for a
run over the whole file. The cases below were checked against AERMOD
v26135 (gfortran -O2, the same build the GUI recordings came from) by
truncating EPA met files and running the Albany stack with ``AVERTIME 1
ANNUAL``: AERMOD stopped with E480 exactly when complete_years was 0.
The files here are synthetic copies of those cases' first and last
hours; only the dates matter.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from pyaermod.aermet import SurfaceFilePeriod, read_surface_period
from pyaermod.gui_v2.state import _empty_project
from pyaermod.validator_advanced import check_annual_met_coverage, surface_file_path

FIXTURES = Path(__file__).parent / "fixtures" / "epa_official"

HEADER = ("   41.300N   74.000W          UA_ID: 00014735  SF_ID: 14735     "
          "OS_ID: 99999        VERSION: 26135    CCVR_Sub\n")
DATA = ("   -2.7  0.062 -9.000 -9.000 -999.   37.      7.9  0.7500   1.50   1.00"
        "    0.80  317.5   10.0  273.8   10.0     0  -9.00   999.  1003.     4 NAD-OS  NoSubs\n")


def _sfc(tmp_path: Path, first: datetime, hours: int, *, two_digit: bool = False,
         name: str = "met.sfc") -> Path:
    """A surface file of ``hours`` consecutive hours; ``first`` is hour 1's start."""
    lines = [HEADER]
    for i in range(hours):
        start = first + timedelta(hours=i)
        year = start.year % 100 if two_digit else start.year
        jday = start.timetuple().tm_yday
        lines.append(f"{year:4d} {start.month:2d} {start.day:2d} {jday:3d} "
                     f"{start.hour + 1:2d} {DATA}")
    path = tmp_path / name
    path.write_text("".join(lines), encoding="latin-1")
    return path


def _hours(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 3600)


class TestReadSurfacePeriod:
    def test_the_albany_file(self):
        period = read_surface_period(FIXTURES / "AERMET2.SFC")
        assert period.first == datetime(1988, 3, 1)
        assert period.last == datetime(1988, 3, 5)
        assert (period.hours, period.days) == (96, 4)
        assert (period.surface_station, period.upper_air_station) == ("14735", "00014735")
        assert period.first_year == 1988
        assert (period.first_day, period.last_day) == (date(1988, 3, 1), date(1988, 3, 4))
        assert period.complete_years == 0
        assert period.describe() == "1988-03-01 to 1988-03-04 (4 days, 96 hours)"

    def test_two_digit_years_are_windowed_as_aermod_does(self, tmp_path):
        # 50-99 are 19xx and 00-49 are 20xx (aermod.f, ISTRT_CENT/ISTRT_WIND).
        old = read_surface_period(_sfc(tmp_path, datetime(1988, 1, 1), 24, two_digit=True))
        new = read_surface_period(_sfc(tmp_path, datetime(2020, 1, 1), 24, two_digit=True,
                                       name="new.sfc"))
        assert (old.first_year, new.first_year) == (1988, 2020)

    def test_lines_that_are_not_hourly_records_are_skipped(self, tmp_path):
        path = _sfc(tmp_path, datetime(1988, 3, 1), 2)
        path.write_text(path.read_text() + "\n  not a record\n1988  3  1  61 99 bad hour\n")
        assert read_surface_period(path).hours == 2

    def test_a_file_without_records_is_refused(self, tmp_path):
        path = tmp_path / "empty.sfc"
        path.write_text(HEADER)
        with pytest.raises(ValueError, match="no hourly records"):
            read_surface_period(path)

    def test_a_missing_file_raises_oserror(self, tmp_path):
        with pytest.raises(OSError):
            read_surface_period(tmp_path / "nope.sfc")

    def test_describe_says_one_day_and_one_hour(self, tmp_path):
        period = read_surface_period(_sfc(tmp_path, datetime(1988, 3, 1), 1))
        assert period.describe() == "1988-03-01 to 1988-03-01 (1 day, 1 hour)"


class TestCompleteYears:
    """AERMOD's NUMYRS.

    The one-year LOVETT, MCR and SALEM cases on either side of the E480
    boundary were run through AERMOD v26135 (module docstring); the
    two- and five-year cases follow the same rule, which E480 cannot tell
    apart from one year.
    """

    @pytest.mark.parametrize(("first", "end", "years"), [
        # LOVETT 1988 (a leap year from 1 January): 8784 hours make a year,
        (datetime(1988, 1, 1), datetime(1989, 1, 1), 1),
        # one hour fewer does not (AERMOD: E480).
        (datetime(1988, 1, 1), datetime(1988, 12, 31, 23), 0),
        # MCR from 1 May 1992: the year ends at hour 24 of 30 April 1993,
        (datetime(1992, 5, 1), datetime(1993, 5, 1), 1),
        (datetime(1992, 5, 1), datetime(1993, 4, 30, 23), 0),
        (datetime(1992, 5, 1), datetime(1993, 5, 20), 1),
        # and from hour 2 of 1 May it ends at hour 1 of 1 May.
        (datetime(1992, 5, 1, 1), datetime(1993, 5, 1), 0),
        (datetime(1992, 5, 1, 1), datetime(1993, 5, 1, 1), 1),
        # SALEM from 1 March 1986: the year ends on 28 February (not a leap year),
        (datetime(1986, 3, 1), datetime(1987, 3, 1), 1),
        (datetime(1986, 3, 1), datetime(1987, 2, 28, 23), 0),
        # and on 29 February in a leap year, so two years need until 1 March 1988.
        (datetime(1986, 3, 1), datetime(1988, 2, 29), 1),
        (datetime(1986, 3, 1), datetime(1988, 3, 1), 2),
        # Five calendar years.
        (datetime(1986, 1, 1), datetime(1991, 1, 1), 5),
    ])
    def test_complete_years(self, tmp_path, first, end, years):
        period = read_surface_period(_sfc(tmp_path, first, _hours(first, end)))
        assert period.complete_years == years

    def test_a_year_that_starts_on_the_first_of_a_month_at_hour_1(self):
        # The year ends at hour 24 of the previous month's last day.
        period = SurfaceFilePeriod(first=datetime(2001, 1, 1), last=datetime(2002, 1, 1),
                                   hours=8760, days=365)
        assert period.complete_years == 1


def _annual_project(surface_file: str, periods=("1", "ANNUAL")):
    project = _empty_project()
    project.control.averaging_periods = list(periods)
    project.meteorology.surface_file = surface_file
    return project


class TestCheckAnnualMetCoverage:
    def test_annual_with_four_days_is_warned_about(self):
        [finding] = check_annual_met_coverage(_annual_project(str(FIXTURES / "AERMET2.SFC")))
        assert finding.severity == "warning"
        assert (finding.pathway, finding.field) == ("MeteorologyPathway", "surface_file")
        assert finding.message.startswith(
            "ANNUAL averages need at least one full year of met data, but AERMET2.SFC "
            "holds 1988-03-01 to 1988-03-04 (4 days, 96 hours)")
        assert "E480" in finding.message

    def test_no_annual_no_warning(self):
        project = _annual_project(str(FIXTURES / "AERMET2.SFC"), periods=("1", "3", "PERIOD"))
        assert check_annual_met_coverage(project) == []

    def test_a_full_year_is_fine(self, tmp_path):
        path = _sfc(tmp_path, datetime(1988, 1, 1), 8784)
        assert check_annual_met_coverage(_annual_project(str(path))) == []

    def test_a_relative_file_is_read_from_the_working_directory(self, tmp_path):
        _sfc(tmp_path, datetime(1988, 3, 1), 96)
        project = _annual_project("met.sfc")
        assert surface_file_path(project.meteorology, tmp_path) == tmp_path / "met.sfc"
        [finding] = check_annual_met_coverage(project, base_dir=tmp_path)
        assert "met.sfc holds 1988-03-01" in finding.message

    def test_an_unreadable_or_unset_file_says_nothing(self, tmp_path):
        assert check_annual_met_coverage(_annual_project(str(tmp_path / "nope.sfc"))) == []
        assert check_annual_met_coverage(_annual_project("")) == []
        assert surface_file_path(_annual_project("  ").meteorology) is None

    def test_a_period_already_read_is_used(self, tmp_path):
        period = SurfaceFilePeriod(first=datetime(1988, 1, 1), last=datetime(1989, 1, 1),
                                   hours=8784, days=366)
        assert check_annual_met_coverage(_annual_project("anything.sfc"), period=period) == []

    def test_startend_limits_the_data(self, tmp_path):
        path = _sfc(tmp_path, datetime(1988, 1, 1), 8784)
        project = _annual_project(str(path))
        met = project.meteorology
        met.start_year, met.start_month, met.start_day = 1988, 1, 1
        met.end_year, met.end_month, met.end_day = 1988, 6, 30
        [finding] = check_annual_met_coverage(project)
        assert "within STARTEND" in finding.message
        met.end_month, met.end_day = 12, 31
        assert check_annual_met_coverage(project) == []

    def test_a_startend_outside_the_data_is_left_to_aermod(self, tmp_path):
        path = _sfc(tmp_path, datetime(1988, 3, 1), 96)
        project = _annual_project(str(path))
        met = project.meteorology
        met.start_year, met.start_month, met.start_day = 1990, 1, 1
        met.end_year, met.end_month, met.end_day = 1990, 12, 31
        assert check_annual_met_coverage(project) == []
