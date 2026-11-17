"""SO BACKGRND as AERMOD reads it (review findings H2 and H3).

``BACKGRND [SECTn] flag values...`` takes a temporal-variation flag, the
same flags as EMISFACT and O3VALUES (ANNUAL 1 value, SEASON 4, MONTH 12,
HROFDY 24, ...), with the values continued over as many lines as needed,
each repeating the flag. ``BACKGRND [SECTn] HOURLY file [format]`` names
an hourly file. The reader used to keep one value after the flag, turn
continuation lines into entries of their own, and drop a sector's HOURLY
line without a trace.
"""

from __future__ import annotations

import pytest

from pyaermod import BackgroundConcentration, BackgroundSector
from pyaermod.input_reader import parse_aermod_input
from pyaermod.validator import Validator


def _deck(so_lines: str) -> str:
    return f"""\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC FLAT
   AVERTIME  1  24  ANNUAL
   POLLUTID  SO2
CO FINISHED
SO STARTING
   LOCATION  S1  POINT  0.0  0.0  0.0
   SRCPARAM  S1  1.0  30.0  400.0  10.0  2.0
{so_lines}
   SRCGROUP  ALL
SO FINISHED
RE STARTING
   DISCCART  100.0  0.0
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
ME FINISHED
OU STARTING
   RECTABLE  ALLAVE  FIRST
OU FINISHED
"""


def _background_errors(project) -> list:
    return [e for e in Validator.validate(project).errors
            if e.pathway == "BackgroundConcentration"]


def _background_lines(text: str) -> list:
    return [" ".join(ln.split()) for ln in text.splitlines()
            if ln.split()[:1] in (["BACKGRND"], ["BGSECTOR"])]


# ----------------------------------------------------------------------
# H2: every value of a temporal flag is kept
# ----------------------------------------------------------------------

def test_a_season_profile_on_one_line_keeps_all_four_values():
    project = parse_aermod_input(_deck("   BACKGRND  SEASON  1.0  2.0  3.0  4.0"))
    assert project.sources.background.period_values == {"SEASON": [1.0, 2.0, 3.0, 4.0]}
    assert project.unparsed_lines == []


def test_a_profile_continued_on_a_second_line_is_one_profile():
    project = parse_aermod_input(_deck("   BACKGRND  SEASON  1.0  2.0\n"
                                       "   BACKGRND  SEASON  3.0  4.0"))
    assert project.sources.background.period_values == {"SEASON": [1.0, 2.0, 3.0, 4.0]}


def test_repeat_shorthand_is_expanded():
    project = parse_aermod_input(_deck("   BACKGRND  MONTH  6*3.0  6*5.0"))
    assert project.sources.background.period_values == {"MONTH": [3.0] * 6 + [5.0] * 6}


def test_an_annual_value_stays_a_number():
    project = parse_aermod_input(_deck("   BACKGRND  ANNUAL  5.0"))
    assert project.sources.background.period_values == {"ANNUAL": 5.0}


def test_a_sector_profile_keeps_all_its_values():
    project = parse_aermod_input(_deck(
        "   BGSECTOR  0  180\n"
        "   BACKGRND  SECT1  SEASON  1.0  2.0\n"
        "   BACKGRND  SECT1  SEASON  3.0  4.0\n"
        "   BACKGRND  SECT2  ANNUAL  6.0"))
    bg = project.sources.background
    assert bg.sector_values == {(1, "SEASON"): [1.0, 2.0, 3.0, 4.0], (2, "ANNUAL"): 6.0}


def test_a_season_profile_validates():
    project = parse_aermod_input(_deck("   BACKGRND  SEASON  1.0  2.0  3.0  4.0"))
    assert _background_errors(project) == []


@pytest.mark.parametrize("so,written", [
    ("   BACKGRND  SEASON  1.0  2.0\n   BACKGRND  SEASON  3.0  4.0",
     ["BACKGRND SEASON 1 2 3 4"]),
    ("   BGSECTOR  0  180\n   BACKGRND  SECT1  SEASON  1  2  3  4\n"
     "   BACKGRND  SECT2  ANNUAL  6",
     ["BGSECTOR 0.0 180.0", "BACKGRND SECT1 SEASON 1 2 3 4", "BACKGRND SECT2 ANNUAL 6"]),
])
def test_a_profile_is_written_as_aermod_reads_it(so, written):
    project = parse_aermod_input(_deck(so))
    assert _background_lines(project.sources.background.to_aermod_input()) == written


def test_a_long_profile_is_split_over_lines_that_repeat_the_flag():
    values = [float(i) for i in range(96)]
    text = BackgroundConcentration(period_values={"SEASHR": values}).to_aermod_input()
    lines = _background_lines(text)
    assert len(lines) > 1 and all(ln.startswith("BACKGRND SEASHR ") for ln in lines)
    again = parse_aermod_input(_deck(text))
    assert again.sources.background.period_values == {"SEASHR": values}


# ----------------------------------------------------------------------
# The validator checks flags and counts as AERMOD does
# ----------------------------------------------------------------------

def _project_with(bg: BackgroundConcentration):
    project = parse_aermod_input(_deck(""))
    project.sources.background = bg
    return project


@pytest.mark.parametrize("values", [
    {"SEASON": [1.0, 2.0, 3.0]},          # SEASON needs 4
    {"MONTH": 3.0},                       # MONTH needs 12
    {"24": 10.0},                         # an averaging period, not a flag
])
def test_a_profile_aermod_would_refuse_is_an_error(values):
    errors = _background_errors(_project_with(BackgroundConcentration(period_values=values)))
    assert errors, values


def test_a_sector_profile_with_the_wrong_count_is_an_error():
    bg = BackgroundConcentration(
        sectors=[BackgroundSector(1, 0.0), BackgroundSector(2, 180.0)],
        sector_values={(1, "SEASON"): [1.0, 2.0], (2, "ANNUAL"): 5.0})
    errors = _background_errors(_project_with(bg))
    assert any("SEASON" in e.message for e in errors)


def test_a_valid_sector_profile_validates():
    bg = BackgroundConcentration(
        sectors=[BackgroundSector(1, 0.0), BackgroundSector(2, 180.0)],
        sector_values={(1, "MONTH"): [3.0] * 12, (2, "ANNUAL"): 5.0})
    assert _background_errors(_project_with(bg)) == []


# ----------------------------------------------------------------------
# H3: a sector's hourly file is not lost
# ----------------------------------------------------------------------

_SECTOR_HOURLY = ("   BGSECTOR  0  180\n"
                  "   BACKUNIT  PPB\n"
                  "   BACKGRND  SECT1  HOURLY  bg1.dat\n"
                  "   BACKGRND  SECT1  MONTH  12*3.0\n"
                  "   BACKGRND  SECT2  SEASON  1.0  2.0  3.0  4.0")


def test_sector_hourly_background_is_kept_verbatim():
    project = parse_aermod_input(_deck(_SECTOR_HOURLY))
    kept = [(u.keyword, " ".join(u.fields)) for u in project.unparsed_lines]
    assert ("BGSECTOR", "0 180") in kept
    assert ("BACKGRND", "SECT1 HOURLY bg1.dat") in kept
    assert ("BACKGRND", "SECT1 MONTH 12*3.0") in kept
    assert ("BACKGRND", "SECT2 SEASON 1.0 2.0 3.0 4.0") in kept
    # Not also modelled, which would write the sectors twice.
    assert project.sources.background is None


def test_sector_hourly_background_is_written_back_once_in_order():
    project = parse_aermod_input(_deck(_SECTOR_HOURLY))
    lines = _background_lines(project.to_aermod_input())
    assert lines == ["BGSECTOR 0 180", "BACKGRND SECT1 HOURLY bg1.dat",
                     "BACKGRND SECT1 MONTH 12*3.0", "BACKGRND SECT2 SEASON 1.0 2.0 3.0 4.0"]


def test_sector_hourly_file_is_listed_as_an_input_file():
    from pyaermod.input_reader import input_files

    project = parse_aermod_input(_deck(_SECTOR_HOURLY))
    assert "bg1.dat" in [f.path for f in input_files(project)]
