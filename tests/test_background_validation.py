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


@pytest.mark.parametrize("ids", [[1, 5], [0, 1], [1, 1], [2, 3], [1, 3]])
@pytest.mark.parametrize("value_ids", ["same", "one_to_n"])
def test_sector_ids_other_than_one_to_n_are_one_error(ids, value_ids):
    # One mistake, one message: ids [1, 3] are not also "sector 2 has no
    # values" (E238) or "sector_id 2 not defined", which follow from it.
    sectors = [BackgroundSector(sid, d) for sid, d in zip(ids, [0.0, 180.0])]
    keys = ids if value_ids == "same" else [1, 2]
    bg = BackgroundConcentration(
        sectors=sectors, sector_values={(sid, "ANNUAL"): 5.0 for sid in keys})
    errors = _background_errors(_project_with(bg))
    assert [e.field for e in errors] == ["sectors"], errors
    assert "1..2" in errors[0].message and "E203" in errors[0].message


def test_a_bad_profile_is_still_reported_beside_bad_sector_ids():
    bg = BackgroundConcentration(
        sectors=[BackgroundSector(1, 0.0), BackgroundSector(3, 180.0)],
        sector_values={(1, "SEASON"): [1.0, 2.0], (3, "ANNUAL"): 5.0})
    errors = _background_errors(_project_with(bg))
    assert [e.field for e in errors] == ["sectors", "sector_values"], errors


def test_values_for_a_sector_not_listed_are_an_error_when_the_ids_are_one_to_n():
    bg = BackgroundConcentration(
        sectors=_two_sectors(),
        sector_values={(1, "ANNUAL"): 5.0, (2, "ANNUAL"): 4.0, (3, "ANNUAL"): 3.0})
    errors = _background_errors(_project_with(bg))
    assert [e.message for e in errors] == ["sector_id 3 not defined in sectors list"], errors


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


# ----------------------------------------------------------------------
# Review finding 6: NaN and +/-inf are no background value. ``v < 0``
# is False for NaN and +inf, so they passed, and the writer emitted
# ``nan``/``inf``, which AERMOD cannot read.
# ----------------------------------------------------------------------

_NON_FINITE = [float("nan"), float("inf"), float("-inf")]


@pytest.mark.parametrize("value", _NON_FINITE)
def test_a_non_finite_uniform_value_is_an_error(value):
    errors = _background_errors(_project_with(BackgroundConcentration(uniform_value=value)))
    assert any(e.field == "uniform_value" and "finite" in e.message for e in errors), errors


@pytest.mark.parametrize("value", _NON_FINITE)
def test_a_non_finite_period_value_is_an_error(value):
    bg = BackgroundConcentration(period_values={"SEASON": [1.0, value, 3.0, 4.0]})
    errors = _background_errors(_project_with(bg))
    assert any(e.field == "period_values" and "finite" in e.message for e in errors), errors


@pytest.mark.parametrize("value", _NON_FINITE)
def test_a_non_finite_sector_value_is_an_error(value):
    bg = BackgroundConcentration(sectors=_two_sectors(),
                                 sector_values={(1, "ANNUAL"): value, (2, "ANNUAL"): 5.0})
    errors = _background_errors(_project_with(bg))
    assert any(e.field == "sector_values" and "finite" in e.message
               and "sector 1" in e.message for e in errors), errors


def test_finite_background_values_still_validate():
    bg = BackgroundConcentration(sectors=_two_sectors(),
                                 sector_values={(1, "SEASON"): [0.0, 1.5, 2.0, 1e6],
                                                (2, "ANNUAL"): 5.0})
    assert _background_errors(_project_with(bg)) == []
    assert _background_errors(_project_with(BackgroundConcentration(uniform_value=0.0))) == []


def _no2_project(chemistry):
    from pyaermod.input_generator import ControlPathway, PollutantType
    from tests.test_validator import _make_valid_project
    control = ControlPathway(title_one="t", pollutant_id=PollutantType.NO2,
                             averaging_periods=["1"], chemistry=chemistry)
    return _make_valid_project(control=control)


@pytest.mark.parametrize("value", _NON_FINITE)
def test_a_non_finite_o3values_or_nox_vals_value_is_an_error(value):
    from pyaermod.input_generator import (
        ChemistryMethod,
        ChemistryOptions,
        NOxBackground,
        OzoneData,
        TemporalValues,
    )
    chem = ChemistryOptions(
        method=ChemistryMethod.GRSM,
        ozone_data=OzoneData(varying=TemporalValues("SEASON", [40.0, value, 40.0, 40.0])),
        nox_background=NOxBackground(varying=TemporalValues("ANNUAL", [value])))
    errors = Validator.validate(_no2_project(chem), advanced=False).errors
    for field in ("ozone_data", "nox_background"):
        assert any(field in e.field and "finite" in e.message for e in errors), (field, errors)


# ----------------------------------------------------------------------
# Review finding 7: a start_direction that is no number (a string from a
# hand-edited project file) used to raise TypeError in the range check.
# ----------------------------------------------------------------------

@pytest.mark.parametrize("direction", ["90", None, float("nan"), float("inf"), True])
def test_a_start_direction_that_is_no_finite_number_is_an_error(direction):
    bg = BackgroundConcentration(
        sectors=[BackgroundSector(1, 0.0), BackgroundSector(2, direction)],
        sector_values={(1, "ANNUAL"): 1.0, (2, "ANNUAL"): 2.0})
    errors = _background_errors(_project_with(bg))
    assert any(e.field == "sectors" and "finite number" in e.message
               and repr(direction) in e.message for e in errors), errors
    # The range and order checks are skipped, not run on a bad value.
    assert not any("0..360" in e.message or "ascending" in e.message for e in errors), errors


def test_a_string_ozone_sector_direction_is_an_error_not_a_crash():
    from pyaermod.input_generator import BackgroundSpec, ChemistryMethod, ChemistryOptions, OzoneData
    oz = OzoneData(sectors=[0.0, "180"], by_sector={1: BackgroundSpec(value=40.0),
                                                    2: BackgroundSpec(value=40.0)})
    chem = ChemistryOptions(method=ChemistryMethod.OLM, ozone_data=oz)
    errors = Validator.validate(_no2_project(chem), advanced=False).errors
    assert any(e.field == "ozone_data.sectors" and "finite number" in e.message
               for e in errors), errors


# ----------------------------------------------------------------------
# A one-shot iterator (map, generator, zip) is no profile: the validator
# used it up, so the writer then wrote a card without values. It is an
# error asking for a list, and the validator takes nothing from it.
# ----------------------------------------------------------------------

def _one_shot(kind):
    values = [1.0, 2.0, 3.0, 4.0]
    return {"map": lambda: map(float, values),
            "generator": lambda: (v for v in values),
            "zip": lambda: zip(values, values)}[kind]()


@pytest.mark.parametrize("kind", ["map", "generator", "zip"])
def test_a_one_shot_iterator_is_an_error_asking_for_a_list(kind):
    values = _one_shot(kind)
    (msg,) = Validator._check_temporal_values("SEASON", values)
    assert "one-shot iterator" in msg and "list" in msg, msg
    assert next(values) is not None  # nothing was taken from it


@pytest.mark.parametrize("kind", ["map", "generator", "zip"])
@pytest.mark.parametrize("mode", ["period", "sector"])
def test_a_background_given_a_one_shot_iterator_is_an_error(kind, mode):
    values = _one_shot(kind)
    if mode == "period":
        bg = BackgroundConcentration(period_values={"SEASON": values})
    else:
        bg = BackgroundConcentration(sectors=_two_sectors(),
                                     sector_values={(1, "SEASON"): values, (2, "ANNUAL"): 5.0})
    for _ in range(2):  # validating twice gives the same answer
        errors = _background_errors(_project_with(bg))
        assert len(errors) == 1, errors
        assert "one-shot iterator" in errors[0].message and "list" in errors[0].message
    assert next(values) is not None


@pytest.mark.parametrize("kind", ["map", "generator"])
def test_an_o3values_or_nox_vals_one_shot_iterator_is_an_error(kind):
    from pyaermod.input_generator import (
        ChemistryMethod,
        ChemistryOptions,
        NOxBackground,
        OzoneData,
        TemporalValues,
    )
    chem = ChemistryOptions(
        method=ChemistryMethod.GRSM,
        ozone_data=OzoneData(varying=TemporalValues("SEASON", _one_shot(kind))),
        nox_background=NOxBackground(varying=TemporalValues("SEASON", _one_shot(kind))))
    errors = Validator.validate(_no2_project(chem), advanced=False).errors
    for field in ("ozone_data", "nox_background"):
        assert any(field in e.field and "one-shot iterator" in e.message for e in errors), (field, errors)
