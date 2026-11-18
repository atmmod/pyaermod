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


# ----------------------------------------------------------------------
# Rules from soset.f BACK_GRND and BGSECTOR (v26135)
# ----------------------------------------------------------------------

def test_a_uniform_value_is_written_with_the_annual_flag():
    """``BACKGRND 5.0`` has no flag: AERMOD stops with E201."""
    text = BackgroundConcentration(uniform_value=5.0).to_aermod_input()
    assert _background_lines(text) == ["BACKGRND ANNUAL 5"]


def test_a_bare_value_in_a_deck_is_read_as_uniform():
    project = parse_aermod_input(_deck("   BACKGRND  5.0"))
    assert project.sources.background.uniform_value == 5.0
    assert _background_lines(project.sources.background.to_aermod_input()) == [
        "BACKGRND ANNUAL 5"]


def _kept_background(project) -> list:
    return [" ".join([u.keyword, *u.fields]) for u in project.unparsed_lines
            if u.keyword in ("BGSECTOR", "BACKGRND")]


# Review finding 2: a bare value is modelled only when it is the deck's
# one whole-domain BACKGRND value line; otherwise every bare line is kept.

@pytest.mark.parametrize("so", [
    "   BACKGRND  5.0\n   BACKGRND  SEASON  1  2  3  4",
    "   BACKGRND  SEASON  1  2  3  4\n   BACKGRND  5.0",
])
def test_a_bare_value_beside_a_flag_line_is_kept_verbatim(so):
    # A whole-domain value line kept verbatim keeps them all verbatim
    # (review finding 4 of the second round), so the pair is written
    # back as the deck had it, in its order, and nothing is modelled.
    project = parse_aermod_input(_deck(so))
    assert project.sources.background is None
    deck_lines = [" ".join(ln.split()) for ln in so.splitlines()]
    assert _kept_background(project) == deck_lines
    assert _background_lines(project.to_aermod_input(validate=False)) == deck_lines


def test_a_bare_value_beside_an_unreadable_flag_line_is_kept_verbatim():
    so = "   BACKGRND  5.0\n   BACKGRND  ANNUAL  x4"
    project = parse_aermod_input(_deck(so))
    assert project.sources.background is None
    assert _kept_background(project) == ["BACKGRND 5.0", "BACKGRND ANNUAL x4"]


def test_two_bare_values_are_both_kept_verbatim_in_order():
    so = "   BACKGRND  5.0\n   BACKGRND  6.0"
    project = parse_aermod_input(_deck(so))
    assert project.sources.background is None
    assert _kept_background(project) == ["BACKGRND 5.0", "BACKGRND 6.0"]
    assert _background_lines(project.to_aermod_input()) == ["BACKGRND 5.0", "BACKGRND 6.0"]


def test_a_bare_value_beside_a_whole_domain_hourly_file_is_read_as_uniform():
    project = parse_aermod_input(_deck("   BACKGRND  HOURLY  bg.dat\n   BACKGRND  5.0"))
    assert project.sources.background.uniform_value == 5.0
    assert _kept_background(project) == ["BACKGRND HOURLY bg.dat"]
    assert _background_errors(project) == []


def test_a_whole_domain_flag_without_values_is_kept_verbatim():
    project = parse_aermod_input(_deck("   BACKGRND  ANNUAL"))
    assert project.sources.background is None
    assert _kept_background(project) == ["BACKGRND ANNUAL"]


def test_two_flags_for_the_whole_domain_are_an_error():
    """E165: inconsistent non-HOURLY BACKGRND options for the same sector."""
    bg = BackgroundConcentration(period_values={"ANNUAL": 5.0, "SEASON": [1.0, 2.0, 3.0, 4.0]})
    errors = _background_errors(_project_with(bg))
    assert any("one temporal flag" in e.message for e in errors)


def test_two_flags_for_one_sector_are_an_error():
    bg = BackgroundConcentration(
        sectors=[BackgroundSector(1, 0.0), BackgroundSector(2, 180.0)],
        sector_values={(1, "ANNUAL"): 5.0, (1, "SEASON"): [1.0, 2.0, 3.0, 4.0],
                       (2, "ANNUAL"): 4.0})
    errors = _background_errors(_project_with(bg))
    assert any("one temporal flag" in e.message and "sector 1" in e.message
               for e in errors)


@pytest.mark.parametrize("directions", [
    [0.0],                                   # BGSECTOR needs 2 to 6
    [0.0, 60.0, 120.0, 180.0, 240.0, 300.0, 330.0],
    [180.0, 0.0],                            # out of order (E222)
    [0.0, 20.0],                             # narrower than 30 degrees (E227)
])
def test_sectors_aermod_refuses_are_an_error(directions):
    sectors = [BackgroundSector(i + 1, d) for i, d in enumerate(directions)]
    bg = BackgroundConcentration(sectors=sectors,
                                 sector_values={(1, "ANNUAL"): 5.0})
    errors = _background_errors(_project_with(bg))
    assert any(e.field == "sectors" for e in errors), directions


# ----------------------------------------------------------------------
# A sector form the model cannot hold is kept whole, never in part
# (review finding 10: ``BGSECTOR 0 180`` + an unreadable SECT1 line used
# to lose the BGSECTOR line, and AERMOD then stops with E171)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("so", [
    # no sector line is modelled
    "   BGSECTOR  0  180\n   BACKGRND  SECT1  ANNUAL  x5",
    # one sector line of two is unreadable
    "   BGSECTOR  0  180\n   BACKGRND  SECT1  ANNUAL  5.0\n"
    "   BACKGRND  SECT2  ANNUAL  x6",
    # a sector line with no flag
    "   BGSECTOR  0  180\n   BACKGRND  SECT1  ANNUAL  5.0\n   BACKGRND  SECT2",
    # a BGSECTOR direction that does not parse
    "   BGSECTOR  0  1x80\n   BACKGRND  SECT1  ANNUAL  5.0\n"
    "   BACKGRND  SECT2  ANNUAL  6.0",
    # BGSECTOR without any BACKGRND line
    "   BGSECTOR  0  180",
    # sector lines without BGSECTOR
    "   BACKGRND  SECT1  ANNUAL  5.0\n   BACKGRND  SECT2  ANNUAL  6.0",
    # a whole-domain profile beside the sector form
    "   BGSECTOR  0  180\n   BACKGRND  ANNUAL  4.0\n"
    "   BACKGRND  SECT1  ANNUAL  5.0\n   BACKGRND  SECT2  ANNUAL  6.0",
    # two BGSECTOR lines
    "   BGSECTOR  0  180\n   BGSECTOR  90  270\n"
    "   BACKGRND  SECT1  ANNUAL  5.0\n   BACKGRND  SECT2  ANNUAL  6.0",
    # a sector line with a value and no flag (review finding 5)
    "   BGSECTOR  0  180\n   BACKGRND  SECT1  ANNUAL  5.0\n   BACKGRND  SECT2  5",
    # a sector line with a flag and no values
    "   BGSECTOR  0  180\n   BACKGRND  SECT1  ANNUAL  5.0\n   BACKGRND  SECT2  ANNUAL",
    # a bare whole-domain value beside the sector form
    "   BGSECTOR  0  180\n   BACKGRND  4.0\n"
    "   BACKGRND  SECT1  ANNUAL  5.0\n   BACKGRND  SECT2  ANNUAL  6.0",
])
def test_a_sector_form_that_is_not_modelled_is_kept_verbatim_in_order(so):
    project = parse_aermod_input(_deck(so))
    assert project.sources.background is None
    original = [" ".join(ln.split()) for ln in so.splitlines()]
    kept = [" ".join([u.keyword, *u.fields]) for u in project.unparsed_lines
            if u.keyword in ("BGSECTOR", "BACKGRND")]
    assert kept == original
    assert _background_lines(project.to_aermod_input()) == original


def test_a_fully_modelled_sector_form_is_not_kept_verbatim():
    so = ("   BGSECTOR  0  180\n   BACKGRND  SECT1  ANNUAL  5.0\n"
          "   BACKGRND  SECT2  ANNUAL  6.0")
    project = parse_aermod_input(_deck(so))
    assert [u for u in project.unparsed_lines
            if u.keyword in ("BGSECTOR", "BACKGRND")] == []
    assert project.sources.background.sector_values == {(1, "ANNUAL"): 5.0,
                                                         (2, "ANNUAL"): 6.0}


# ----------------------------------------------------------------------
# One continuation writer for BACKGRND, O3VALUES and NOX_VALS
# (review finding 8)
# ----------------------------------------------------------------------

def test_continued_value_lines_repeats_the_prefix_on_every_line():
    from pyaermod.pathways import continued_value_lines

    lines = continued_value_lines("BACKGRND", "SECT1  HROFDY",
                                  [float(i) + 0.5 for i in range(24)])
    assert lines == [
        "   BACKGRND  SECT1  HROFDY  " + " ".join(f"{i + 0.5:g}" for i in range(12)),
        "   BACKGRND  SECT1  HROFDY  " + " ".join(f"{i + 0.5:g}" for i in range(12, 24)),
    ]
    assert continued_value_lines("O3VALUES", "ANNUAL", [40.0], per_line=5) == [
        "   O3VALUES  ANNUAL  40"]



# ----------------------------------------------------------------------
# Review finding 3: any non-string iterable is a sequence of values
# ----------------------------------------------------------------------

def _sequences():
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    return [np.array([1.0, 2.0, 3.0, 4.0]),
            pd.Series([1.0, 2.0, 3.0, 4.0], index=[10, 11, 12, 13]),
            range(1, 5)]


def test_continued_value_lines_takes_arrays_series_and_ranges():
    from pyaermod.pathways import continued_value_lines

    for values in _sequences():
        assert continued_value_lines("BACKGRND", "SEASON", values) == [
            "   BACKGRND  SEASON  1 2 3 4"], type(values)
        assert continued_value_lines("BACKGRND", "SEASON", values, per_line=3) == [
            "   BACKGRND  SEASON  1 2 3", "   BACKGRND  SEASON  4"], type(values)


def test_a_background_profile_given_as_an_array_is_written():
    for values in _sequences():
        bg = BackgroundConcentration(period_values={"SEASON": values})
        assert _background_lines(bg.to_aermod_input()) == ["BACKGRND SEASON 1 2 3 4"]


def test_a_string_is_one_value_not_a_sequence_of_characters():
    from pyaermod.pathways import continued_value_lines

    with pytest.raises((TypeError, ValueError)):
        continued_value_lines("BACKGRND", "SEASON", "1234")


# ----------------------------------------------------------------------
# Review round 2, finding 4: the whole-domain profile is modelled whole
# or not at all, as the sector form is
# ----------------------------------------------------------------------

@pytest.mark.parametrize("so", [
    # the second line of a MONTH profile does not parse
    "   BACKGRND  MONTH  1  2  3  4  5  6\n   BACKGRND  MONTH  7  8  9  10  11  x",
    # the first line does not parse
    "   BACKGRND  MONTH  1  2  x  4  5  6\n   BACKGRND  MONTH  7  8  9  10  11  12",
    # beside a whole-domain hourly file, which stays where the deck had it
    "   BACKGRND  HOURLY  bg.dat\n   BACKGRND  SEASON  1  2\n   BACKGRND  SEASON  3  x",
    "   BACKGRND  SEASON  1  2\n   BACKGRND  HOURLY  bg.dat\n   BACKGRND  SEASON  3  x",
    # a flag without values beside a full profile
    "   BACKGRND  ANNUAL\n   BACKGRND  SEASON  1  2  3  4",
])
def test_a_whole_domain_profile_with_a_line_kept_verbatim_is_kept_whole(so):
    project = parse_aermod_input(_deck(so))
    assert project.sources.background is None
    deck_lines = [" ".join(ln.split()) for ln in so.splitlines()]
    assert _kept_background(project) == deck_lines
    assert _background_lines(project.to_aermod_input(validate=False)) == deck_lines
    assert [e for e in _background_errors(project) if e.field == "unparsed_lines"] == []


@pytest.mark.parametrize("so,modelled,kept", [
    ("   BACKGRND  HOURLY  bg.dat\n   BACKGRND  ANNUAL  5.0",
     {"ANNUAL": 5.0}, ["BACKGRND HOURLY bg.dat"]),
    ("   BACKGRND  SEASON  1  2\n   BACKGRND  SEASON  3  4",
     {"SEASON": [1.0, 2.0, 3.0, 4.0]}, []),
    ("   BACKGRND  MONTH  1  2  3  4  5  6\n   BACKGRND  MONTH  7D0  8  9  10  11  12",
     {"MONTH": [float(i) for i in range(1, 13)]}, []),
    ("   BACKGRND  HOURLY  bg.dat\n   BACKGRND  5.0D0", None, ["BACKGRND HOURLY bg.dat"]),
])
def test_a_valid_whole_domain_deck_is_still_modelled(so, modelled, kept):
    project = parse_aermod_input(_deck(so))
    bg = project.sources.background
    if modelled is None:
        assert bg.uniform_value == 5.0
    else:
        assert bg.period_values == modelled
    assert _kept_background(project) == kept


# ----------------------------------------------------------------------
# BGSECTOR directions read back exactly (review finding 2: ``:.1f``
# turned ``BGSECTOR 22.25 180`` into ``BGSECTOR 22.2 180.0`` and moved
# the sector boundary)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("directions", [
    "22.25  180",
    "0.05  90.125  200",
    "10.123456789  190.987654321",
])
def test_bgsector_directions_read_back_exactly(directions):
    n = len(directions.split())
    so = (f"   BGSECTOR  {directions}\n"
          + "\n".join(f"   BACKGRND  SECT{i}  ANNUAL  {i}.0" for i in range(1, n + 1)))
    project = parse_aermod_input(_deck(so))
    read = [s.start_direction for s in project.sources.background.sectors]
    assert read == [float(d) for d in directions.split()]
    again = parse_aermod_input(project.to_aermod_input())
    assert [s.start_direction for s in again.sources.background.sectors] == read


@pytest.mark.parametrize("direction", [22.25, 1.0 / 3.0, 359.99, 1e-7])
def test_any_bgsector_direction_is_written_so_it_reads_back_exactly(direction):
    bg = BackgroundConcentration(
        sectors=[BackgroundSector(1, direction), BackgroundSector(2, 180.0)],
        sector_values={(1, "ANNUAL"): 1.0, (2, "ANNUAL"): 2.0})
    line = next(ln for ln in _background_lines(bg.to_aermod_input())
                if ln.startswith("BGSECTOR"))
    assert [float(t) for t in line.split()[1:]] == [direction, 180.0]


def test_bgsector_directions_with_one_decimal_keep_one_decimal():
    bg = BackgroundConcentration(
        sectors=[BackgroundSector(1, 0.0), BackgroundSector(2, 90.0),
                 BackgroundSector(3, 22.5)],
        sector_values={(1, "ANNUAL"): 1.0, (2, "ANNUAL"): 2.0, (3, "ANNUAL"): 3.0})
    assert "   BGSECTOR  0.0 90.0 22.5" in bg.to_aermod_input().splitlines()


# ----------------------------------------------------------------------
# A value AERMOD's STODBL does not read (NaN, an infinity, ``1_000``,
# which Python's float() reads) is no value: the line does not parse,
# so the profile is kept verbatim whole, as for any other value that
# does not parse, and nothing non-finite is modelled.
# ----------------------------------------------------------------------

@pytest.mark.parametrize("so", [
    "   BACKGRND  SEASON  1  nan  3  4",
    "   BACKGRND  ANNUAL  inf",
    "   BACKGRND  ANNUAL  1_000",
    "   BACKGRND  MONTH  1  2  3  4  5  6\n   BACKGRND  MONTH  7  8  9  10  11  -Infinity",
    "   BACKGRND  NaN",
])
def test_a_non_finite_whole_domain_value_is_kept_verbatim(so):
    project = parse_aermod_input(_deck(so))
    assert project.sources.background is None
    deck_lines = [" ".join(ln.split()) for ln in so.splitlines()]
    assert _kept_background(project) == deck_lines
    assert _background_lines(project.to_aermod_input(validate=False)) == deck_lines


@pytest.mark.parametrize("so", [
    "   BGSECTOR  0  180\n   BACKGRND  SECT1  ANNUAL  nan\n   BACKGRND  SECT2  ANNUAL  6",
    "   BGSECTOR  0  inf\n   BACKGRND  SECT1  ANNUAL  5\n   BACKGRND  SECT2  ANNUAL  6",
    "   BGSECTOR  0  1_80\n   BACKGRND  SECT1  ANNUAL  5\n   BACKGRND  SECT2  ANNUAL  6",
])
def test_a_non_finite_sector_value_or_direction_is_kept_verbatim(so):
    project = parse_aermod_input(_deck(so))
    assert project.sources.background is None
    assert _kept_background(project) == [" ".join(ln.split()) for ln in so.splitlines()]


# ----------------------------------------------------------------------
# A one-shot iterator (map, generator, zip) is no profile: the first pass
# over it (the validator's) used it up, and the writer then wrote
# ``BACKGRND  SEASON`` with no values. Profiles are lists, tuples,
# ranges and anything with a tolist() (numpy, pandas); anything else is
# refused, not written as an empty card.
# ----------------------------------------------------------------------

def _one_shot(kind):
    values = [1.0, 2.0, 3.0, 4.0]
    return {"map": lambda: map(float, values),
            "generator": lambda: (v for v in values),
            "zip": lambda: (a for (a,) in zip(values)),
            "zip_object": lambda: zip(values),
            "iter": lambda: iter(values)}[kind]()


_ONE_SHOT_KINDS = ["map", "generator", "zip", "zip_object", "iter"]


@pytest.mark.parametrize("kind", _ONE_SHOT_KINDS)
def test_continued_value_lines_refuses_a_one_shot_iterator(kind):
    from pyaermod.pathways import continued_value_lines

    values = _one_shot(kind)
    with pytest.raises(TypeError, match="list"):
        continued_value_lines("BACKGRND", "SEASON", values)
    # Nothing was taken from it.
    assert next(values) is not None


@pytest.mark.parametrize("kind", _ONE_SHOT_KINDS)
@pytest.mark.parametrize("mode", ["period", "sector"])
def test_a_background_given_a_one_shot_iterator_is_never_written_empty(kind, mode):
    values = _one_shot(kind)
    if mode == "period":
        bg = BackgroundConcentration(period_values={"SEASON": values})
    else:
        bg = BackgroundConcentration(
            sectors=[BackgroundSector(1, 0.0), BackgroundSector(2, 180.0)],
            sector_values={(1, "SEASON"): values, (2, "ANNUAL"): 5.0})
    for _ in range(2):  # the second call too, not an empty card
        with pytest.raises(TypeError, match="one-shot iterator"):
            bg.to_aermod_input()


@pytest.mark.parametrize("kind", _ONE_SHOT_KINDS)
def test_a_project_with_a_one_shot_profile_is_not_written(kind):
    project = _project_with(BackgroundConcentration(period_values={"SEASON": _one_shot(kind)}))
    with pytest.raises(TypeError, match="one-shot iterator"):
        project.to_aermod_input(validate=False)
    with pytest.raises(ValueError, match="list"):
        project.to_aermod_input()


@pytest.mark.parametrize("kind", ["map", "generator"])
def test_an_ozone_profile_given_a_one_shot_iterator_is_refused(kind):
    from pyaermod.pathways import OzoneData, TemporalValues, _ozone_lines

    oz = OzoneData(varying=TemporalValues("SEASON", _one_shot(kind)))
    with pytest.raises(TypeError, match="one-shot iterator"):
        _ozone_lines(oz)


@pytest.mark.parametrize("values", [{1.0, 2.0, 3.0, 4.0}, {"a": 1.0}])
def test_an_unordered_container_is_no_profile(values):
    from pyaermod.pathways import continued_value_lines

    with pytest.raises(TypeError, match="list"):
        continued_value_lines("BACKGRND", "SEASON", values)


def test_tuples_and_lists_are_profiles():
    from pyaermod.pathways import continued_value_lines

    for values in ((1.0, 2.0, 3.0, 4.0), [1.0, 2.0, 3.0, 4.0]):
        assert continued_value_lines("BACKGRND", "SEASON", values) == [
            "   BACKGRND  SEASON  1 2 3 4"]


# ----------------------------------------------------------------------
# Profile values read back exactly (BACKGRND, O3VALUES, NOX_VALS)
# ----------------------------------------------------------------------
# ``.10g`` keeps ten significant digits, so 12.3456789012345 was written
# as 12.3456789 and read back as another number. A value ``.10g`` already
# writes exactly keeps its short form.

_LONG = [12.3456789012345, 0.1 + 0.2, 1.0 / 3.0, 123456789012.5]


def test_exact_num_keeps_short_forms_and_reads_back_exactly():
    from pyaermod.pathways import exact_num
    assert [exact_num(v) for v in (1.0, 2, 3.5, 0.1, 1e-5, 6.0)] == [
        "1", "2", "3.5", "0.1", "1e-05", "6"]
    for value in _LONG:
        assert float(exact_num(value)) == value


@pytest.mark.parametrize("value", [0.1, 1.0 / 3.0, 12.3456789, 1e-5, 2.5, 7.0])
def test_a_float32_reads_back_as_its_own_value(value):
    # np.float32(0.1) == float("0.1000000015") at float32 precision, but
    # the deck is read as a double: the text must read back to float(v).
    np = pytest.importorskip("numpy")
    from pyaermod.pathways import exact_num, one_decimal_or_exact
    v = np.float32(value)
    for write in (exact_num, one_decimal_or_exact):
        assert float(write(v)) == float(v), (write.__name__, write(v))
    assert exact_num(np.float32(7.0)) == "7"
    assert one_decimal_or_exact(np.float32(2.5)) == "2.5"


def test_an_unchanged_short_profile_is_written_as_before():
    text = BackgroundConcentration(period_values={"SEASON": [1.0, 2.0, 3.0, 4.0]}).to_aermod_input()
    assert _background_lines(text) == ["BACKGRND SEASON 1 2 3 4"]


@pytest.mark.parametrize("background", [
    BackgroundConcentration(period_values={"SEASON": _LONG}),
    BackgroundConcentration(uniform_value=12.3456789012345),
    BackgroundConcentration(
        sectors=[BackgroundSector(1, 0.0), BackgroundSector(2, 180.0)],
        sector_values={(1, "SEASON"): _LONG, (2, "ANNUAL"): 1.0 / 3.0}),
])
def test_a_background_profile_reads_back_exactly(background):
    again = parse_aermod_input(_deck(background.to_aermod_input())).sources.background
    if background.uniform_value is not None:
        assert again.period_values == {"ANNUAL": background.uniform_value}
    else:
        assert again.period_values == background.period_values
        assert again.sector_values == background.sector_values


def test_o3values_and_nox_vals_read_back_exactly():
    from pyaermod._fortran import fortran_float
    from pyaermod.pathways import NOxBackground, OzoneData, TemporalValues, _nox_lines, _ozone_lines
    lines = (_ozone_lines(OzoneData(varying=TemporalValues("SEASON", _LONG)))
             + _nox_lines(NOxBackground(varying=TemporalValues("SEASON", _LONG))))
    for keyword in ("O3VALUES", "NOX_VALS"):
        [line] = [ln for ln in lines if ln.split()[0] == keyword]
        assert [fortran_float(t, strict=True) for t in line.split()[2:]] == _LONG
