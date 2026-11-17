"""SO BACKGRND checks AERMOD makes that the validator must make too.

Ground truth is EPA's AERMOD v26135 soset.f, confirmed by probe decks
``scripts/oracle_decks/33*.inp`` (PR #70 review verification):

* a declared sector with no values stops SRCQA with E238 (probe 33);
* sectors are numbered by position in BGSECTOR, so ``SECTk`` with k above
  the number of sectors is E203 "BGSECTOR ID" (probe 33b);
* a modelled sector background beside verbatim BGSECTOR/BACKGRND lines
  writes both, and AERMOD stops with E203 (probe 33c); a whole-domain
  HOURLY file kept verbatim beside a whole-domain flag is valid (32d).
"""

from __future__ import annotations

import pytest

from pyaermod import BackgroundConcentration, BackgroundSector
from pyaermod.input_reader import parse_aermod_input
from pyaermod.validator import Validator
from tests.test_background_concentration import (
    _SECTOR_HOURLY,
    _background_errors,
    _deck,
    _project_with,
)


def _two_sectors():
    return [BackgroundSector(1, 0.0), BackgroundSector(2, 180.0)]


# ----------------------------------------------------------------------
# Finding 1: every declared sector needs values (E238)
# ----------------------------------------------------------------------

def test_a_declared_sector_without_values_is_an_error():
    bg = BackgroundConcentration(sectors=_two_sectors(),
                                 sector_values={(1, "ANNUAL"): 5.0})
    errors = _background_errors(_project_with(bg))
    assert any("sector 2" in e.message and "E238" in e.message for e in errors), errors


def test_sectors_with_no_values_at_all_are_an_error():
    bg = BackgroundConcentration(sectors=_two_sectors(), sector_values={})
    errors = _background_errors(_project_with(bg))
    assert sum("E238" in e.message for e in errors) == 2, errors


# ----------------------------------------------------------------------
# Finding 2: sector IDs are 1..N in BGSECTOR order (E203)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("ids", [
    [1, 5],      # written as SECT5 with 2 sectors
    [0, 1],      # SECT0
    [1, 1],      # duplicate
    [2, 3],
])
def test_sector_ids_other_than_one_to_n_are_an_error(ids):
    sectors = [BackgroundSector(sid, d) for sid, d in zip(ids, [0.0, 180.0])]
    bg = BackgroundConcentration(
        sectors=sectors, sector_values={(sid, "ANNUAL"): 5.0 for sid in ids})
    errors = _background_errors(_project_with(bg))
    assert any(e.field == "sectors" and "E203" in e.message for e in errors), errors


def test_sector_ids_one_to_n_in_any_list_order_validate():
    bg = BackgroundConcentration(
        sectors=[BackgroundSector(2, 180.0), BackgroundSector(1, 0.0)],
        sector_values={(1, "ANNUAL"): 5.0, (2, "ANNUAL"): 4.0})
    assert _background_errors(_project_with(bg)) == []


# ----------------------------------------------------------------------
# Finding 4: a modelled background beside verbatim background lines
# ----------------------------------------------------------------------

def _verbatim_sector_deck():
    project = parse_aermod_input(_deck(_SECTOR_HOURLY))
    assert project.sources.background is None
    return project


def test_modelled_sectors_beside_verbatim_sector_lines_are_an_error():
    project = _verbatim_sector_deck()
    project.sources.background = BackgroundConcentration(
        sectors=_two_sectors(),
        sector_values={(1, "ANNUAL"): 5.0, (2, "ANNUAL"): 4.0})
    errors = _background_errors(project)
    assert any(e.field == "unparsed_lines" for e in errors), errors
    assert any("remove" in e.message.lower() for e in errors)


@pytest.mark.parametrize("bg", [
    BackgroundConcentration(uniform_value=5.0),
    BackgroundConcentration(period_values={"SEASON": [1.0, 2.0, 3.0, 4.0]}),
])
def test_a_whole_domain_background_beside_verbatim_sector_lines_is_an_error(bg):
    project = _verbatim_sector_deck()
    project.sources.background = bg
    errors = _background_errors(project)
    assert any(e.field == "unparsed_lines" for e in errors), errors


def test_a_whole_domain_hourly_file_beside_a_whole_domain_flag_validates():
    """Probe 32d: ``BACKGRND HOURLY file`` with ``BACKGRND ANNUAL x`` runs."""
    project = parse_aermod_input(_deck("   BACKGRND  HOURLY  bg.dat\n"
                                       "   BACKGRND  ANNUAL  5.0"))
    assert project.sources.background is not None
    assert _background_errors(project) == []


def test_modelled_sectors_beside_a_verbatim_whole_domain_hourly_file_are_an_error():
    project = parse_aermod_input(_deck("   BACKGRND  HOURLY  bg.dat"))
    project.sources.background = BackgroundConcentration(
        sectors=_two_sectors(),
        sector_values={(1, "ANNUAL"): 5.0, (2, "ANNUAL"): 4.0})
    errors = _background_errors(project)
    assert any(e.field == "unparsed_lines" for e in errors), errors


def test_verbatim_sector_lines_alone_are_not_flagged():
    assert [e for e in _background_errors(_verbatim_sector_deck())
            if e.field == "unparsed_lines"] == []


# ----------------------------------------------------------------------
# Finding 6: non-numeric values are reported, not raised
# ----------------------------------------------------------------------

@pytest.mark.parametrize("bg", [
    BackgroundConcentration(period_values={"SEASON": ["1", 2.0, 3.0, 4.0]}),
    BackgroundConcentration(period_values={"ANNUAL": "5"}),
    BackgroundConcentration(period_values={"ANNUAL": True}),
    BackgroundConcentration(period_values={"ANNUAL": None}),
    BackgroundConcentration(uniform_value="5"),
    BackgroundConcentration(
        sectors=[BackgroundSector(1, 0.0), BackgroundSector(2, 180.0)],
        sector_values={(1, "ANNUAL"): "x", (2, "ANNUAL"): 4.0}),
])
def test_non_numeric_background_values_are_an_error(bg):
    errors = _background_errors(_project_with(bg))
    assert any("number" in e.message for e in errors), errors


def test_numpy_numbers_are_numbers():
    np = pytest.importorskip("numpy")
    bg = BackgroundConcentration(period_values={"SEASON": list(np.array([1.0, 2.0, 3.0, 4.0]))})
    assert _background_errors(_project_with(bg)) == []


# ----------------------------------------------------------------------
# Finding 7: one temporal-flag check for BACKGRND, O3VALUES and NOX_VALS
# ----------------------------------------------------------------------

def test_one_helper_checks_temporal_flags():
    assert Validator._check_temporal_values("SEASON", [1.0, 2.0, 3.0, 4.0]) == []
    assert Validator._check_temporal_values("ANNUAL", 5.0) == []
    (msg,) = Validator._check_temporal_values("SEASON", [1.0])
    assert "SEASON needs 4 values, got 1" in msg
    (msg,) = Validator._check_temporal_values("WEEKLY", [1.0])
    assert "unknown temporal flag 'WEEKLY'" in msg
    (msg,) = Validator._check_temporal_values("ANNUAL", ["5"])
    assert "number" in msg


def test_a_background_flag_message_names_the_sector():
    bg = BackgroundConcentration(sectors=_two_sectors(),
                                 sector_values={(1, "WEEKLY"): 5.0, (2, "ANNUAL"): 4.0})
    errors = _background_errors(_project_with(bg))
    assert any("unknown temporal flag 'WEEKLY' for sector 1" in e.message for e in errors), errors


# ----------------------------------------------------------------------
# Review finding 3: arrays, Series and ranges are sequences of values
# ----------------------------------------------------------------------

def test_an_array_series_or_range_of_values_validates():
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    for values in (np.array([1.0, 2.0, 3.0, 4.0]),
                   pd.Series([1.0, 2.0, 3.0, 4.0], index=[7, 8, 9, 10]),
                   range(1, 5)):
        assert Validator._check_temporal_values("SEASON", values) == [], type(values)
        bg = BackgroundConcentration(period_values={"SEASON": values})
        assert _background_errors(_project_with(bg)) == [], type(values)


def test_a_negative_value_in_an_array_is_an_error():
    np = pytest.importorskip("numpy")
    bg = BackgroundConcentration(period_values={"SEASON": np.array([1.0, -2.0, 3.0, 4.0])})
    errors = _background_errors(_project_with(bg))
    assert any(">= 0" in e.message for e in errors), errors


def test_a_string_of_values_is_one_non_numeric_value():
    problems = Validator._check_temporal_values("SEASON", "1 2 3 4")
    assert any("needs 4 values, got 1" in p for p in problems), problems
    assert any("number" in p for p in problems), problems


def test_an_array_ozone_profile_validates():
    np = pytest.importorskip("numpy")
    from pyaermod.pathways import TemporalValues

    assert Validator._check_temporal_values(
        "MONTH", TemporalValues("MONTH", np.full(12, 40.0)).values) == []


# ----------------------------------------------------------------------
# Review finding 6: a modelled whole-domain background beside a verbatim
# whole-domain non-HOURLY BACKGRND line is two flags for the domain (E165)
# ----------------------------------------------------------------------

_MONTH_TYPO = "   BACKGRND  MONTH  1  2  x  4  5  6  7  8  9  10  11  12"


@pytest.mark.parametrize("bg", [
    BackgroundConcentration(uniform_value=5.0),
    BackgroundConcentration(period_values={"SEASON": [1.0, 2.0, 3.0, 4.0]}),
])
def test_a_whole_domain_background_beside_a_verbatim_flag_line_is_an_error(bg):
    project = parse_aermod_input(_deck("   BACKGRND  ANNUAL  5\n" + _MONTH_TYPO))
    # One whole-domain line kept verbatim keeps them all (round 2, finding 4).
    assert project.sources.background is None
    assert [u.fields[0] for u in project.unparsed_lines if u.keyword == "BACKGRND"] == [
        "ANNUAL", "MONTH"]
    project.sources.background = bg
    errors = _background_errors(project)
    assert any(e.field == "unparsed_lines" and "E165" in e.message for e in errors), errors


def test_a_whole_domain_background_beside_a_verbatim_bare_value_is_an_error():
    project = parse_aermod_input(_deck("   BACKGRND  5.0\n   BACKGRND  6.0"))
    assert project.sources.background is None
    project.sources.background = BackgroundConcentration(uniform_value=4.0)
    errors = _background_errors(project)
    assert any(e.field == "unparsed_lines" for e in errors), errors


def test_a_whole_domain_background_beside_a_verbatim_hourly_file_validates():
    project = parse_aermod_input(_deck("   BACKGRND  HOURLY  bg.dat"))
    for bg in (BackgroundConcentration(uniform_value=5.0),
               BackgroundConcentration(period_values={"SEASON": [1.0, 2.0, 3.0, 4.0]})):
        project.sources.background = bg
        assert _background_errors(project) == [], bg


@pytest.mark.parametrize("so", [
    "   BACKGRND  HOURLY  bg.dat\n   BACKGRND  ANNUAL  5.0",
    "   BACKGRND  ANNUAL  5.0\n   BACKGRND  HOURLY  bg.dat  (F10.3)",
    "   BACKGRND  HOURLY  bg.dat\n   BACKGRND  MONTH  12*3.0",
    "   BACKGRND  HOURLY  bg.dat\n   BACKGRND  5.0",
    "   BACKGRND  SEASON  1  2\n   BACKGRND  SEASON  3  4",
    # AERMOD reads values with STODBL, which takes a D exponent
    "   BACKGRND  MONTH  1  2  3  4  5  6\n   BACKGRND  MONTH  7D0  8  9  10  11  12",
    "   BACKGRND  HOURLY  bg.dat\n   BACKGRND  5.0D0",
])
def test_a_valid_whole_domain_deck_reads_to_a_valid_project(so):
    assert _background_errors(parse_aermod_input(_deck(so))) == []


# ----------------------------------------------------------------------
# Review round 2, finding 3: the verbatim conflict matters only when the
# verbatim lines are written
# ----------------------------------------------------------------------

def _modelled_beside_verbatim():
    project = parse_aermod_input(_deck("   BACKGRND  5.0\n   BACKGRND  6.0"))
    assert project.sources.background is None
    project.sources.background = BackgroundConcentration(uniform_value=4.0)
    return project


def test_the_conflict_is_not_an_error_when_verbatim_lines_are_not_written():
    project = _modelled_beside_verbatim()
    text = project.to_aermod_input(validate=True, preserve_unparsed=False)
    assert [" ".join(ln.split()) for ln in text.splitlines()
            if ln.split()[:1] == ["BACKGRND"]] == ["BACKGRND ANNUAL 4"]
    assert [e for e in Validator.validate(project, preserve_unparsed=False).errors
            if e.field == "unparsed_lines"] == []


def test_the_conflict_is_an_error_when_verbatim_lines_are_written():
    project = _modelled_beside_verbatim()
    with pytest.raises(ValueError, match="unparsed_lines"):
        project.to_aermod_input(validate=True)
    assert any(e.field == "unparsed_lines" for e in Validator.validate(project).errors)


# ----------------------------------------------------------------------
# Review round 2, finding 6: one background mode at a time
# ----------------------------------------------------------------------

_SECTOR_MODE = dict(sectors=[BackgroundSector(1, 0.0), BackgroundSector(2, 180.0)],
                    sector_values={(1, "ANNUAL"): 5.0, (2, "ANNUAL"): 4.0})


@pytest.mark.parametrize("kwargs,named", [
    (dict(uniform_value=5.0, period_values={"ANNUAL": 4.0}),
     ["uniform_value", "period_values"]),
    (dict(uniform_value=5.0, **_SECTOR_MODE), ["uniform_value", "sectors"]),
    (dict(period_values={"ANNUAL": 4.0}, **_SECTOR_MODE), ["period_values", "sectors"]),
    (dict(uniform_value=5.0, period_values={"ANNUAL": 4.0}, **_SECTOR_MODE),
     ["uniform_value", "period_values", "sectors"]),
    (dict(uniform_value=5.0, sectors=_SECTOR_MODE["sectors"]),
     ["uniform_value", "sectors"]),
])
def test_more_than_one_background_mode_is_an_error(kwargs, named):
    errors = _background_errors(_project_with(BackgroundConcentration(**kwargs)))
    modes = [e for e in errors if "one of" in e.message and "mode" in e.message]
    assert len(modes) == 1, errors
    assert all(name in modes[0].message for name in named), modes[0].message


@pytest.mark.parametrize("kwargs", [
    dict(uniform_value=5.0),
    dict(period_values={"ANNUAL": 4.0}),
    dict(**_SECTOR_MODE),
    dict(uniform_value=None, period_values={}, sectors=None, sector_values=None),
])
def test_one_background_mode_is_not_a_mode_error(kwargs):
    errors = _background_errors(_project_with(BackgroundConcentration(**kwargs)))
    assert not [e for e in errors if "mode" in e.message], errors


# ----------------------------------------------------------------------
# sector_values without sectors: the writer needs both, so the
# background would vanish from the deck without a word
# ----------------------------------------------------------------------

@pytest.mark.parametrize("sectors", [None, []])
def test_sector_values_without_sectors_are_an_error(sectors):
    bg = BackgroundConcentration(sectors=sectors, sector_values={(1, "ANNUAL"): 5.0})
    assert "BACKGRND" not in bg.to_aermod_input()
    errors = _background_errors(_project_with(bg))
    assert any(e.field == "sector_values" and "sectors" in e.message
               and "E171" in e.message for e in errors), errors


@pytest.mark.parametrize("sector_values", [None, {}])
def test_sectors_without_sector_values_are_an_error_per_sector(sector_values):
    bg = BackgroundConcentration(sectors=_two_sectors(), sector_values=sector_values)
    errors = _background_errors(_project_with(bg))
    assert sum("E238" in e.message for e in errors) == 2, errors
