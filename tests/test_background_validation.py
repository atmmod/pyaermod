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
