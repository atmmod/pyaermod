"""Validator checks that disagree with what AERMOD v24142 accepts.

Each test states AERMOD's behaviour (soset.f / coset.f, confirmed with
setup-only runs of bin/aermod) and asserts that the validator matches it:
no error for a deck AERMOD runs, an error for a deck AERMOD refuses.
"""

from pathlib import Path

import pytest

import pyaermod
from pyaermod.input_generator import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.input_reader import read_aermod_input
from pyaermod.pathways import (
    ChemistryMethod,
    ChemistryOptions,
    OzoneData,
    UrbanArea,
)
from pyaermod.sources import (
    BackgroundConcentration,
    BuoyLineSegment,
    BuoyLineSource,
    GasDepositionParams,
    Method2Params,
    ParticleDepositionParams,
    SourceGroupDefinition,
)
from pyaermod.validator import Validator
from pyaermod.validator_advanced import advanced_validate

EPA_OFFICIAL = (
    Path(pyaermod.__file__).resolve().parents[2] / "tests" / "fixtures" / "epa_official"
)


def _project(sources=None, **control):
    control.setdefault("terrain_type", "ELEV")
    return AERMODProject(
        control=ControlPathway(title_one="t", **control),
        sources=SourcePathway(sources=sources if sources is not None else [_stack()]),
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid(
            grid_name="G", x_init=-100, x_num=5, x_delta=50,
            y_init=-100, y_num=5, y_delta=50)]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )


def _stack(source_id="S1", **kw):
    args = dict(source_id=source_id, x_coord=0, y_coord=0, stack_height=20,
                stack_diameter=2, exit_velocity=10, stack_temp=400,
                emission_rate=1)
    args.update(kw)
    return PointSource(**args)


def _errors(project, field=None):
    return [e for e in Validator.validate(project).errors
            if e.severity == "error" and (field is None or e.field == field)]


# ---------------------------------------------------------------------------
# Real EPA decks: every one runs in AERMOD, so every one must validate.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "deck", sorted(p.name for p in EPA_OFFICIAL.glob("*.inp")))
def test_epa_official_deck_validates(deck):
    project = read_aermod_input(EPA_OFFICIAL / deck)
    assert _errors(project) == []


# ---------------------------------------------------------------------------
# C1: POLLUTID takes any name (coset.f POLLID 2512-2514, 2584)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["BENZENE", "CHROMIUM", "SF6", "LEAD", "PM-2.5", "HG0"])
def test_any_pollutant_id_is_accepted(name):
    assert _errors(_project(pollutant_id=name), "pollutant_id") == []


# ---------------------------------------------------------------------------
# C2 / B4: BACKGROUND in a source group (soset.f SRCGRP 5876-5916)
# ---------------------------------------------------------------------------

def test_background_member_of_source_group_with_background_data():
    project = read_aermod_input(EPA_OFFICIAL / "bg_no2_olm_ppb.inp")
    assert _errors(project, "member_source_ids") == []


def test_source_id_range_in_source_group_is_accepted():
    # soset.f SRCGRP 5947-5960: a field with '-' is a range of IDs
    project = _project(sources=[_stack("STACK1"), _stack("STACK2", x_coord=50)])
    project.sources.group_definitions = [
        SourceGroupDefinition(group_name="G1", member_source_ids=["STACK1-STACK2"])]
    assert _errors(project, "member_source_ids") == []


def test_unknown_literal_member_is_still_an_error():
    # soset.f SRCGRP 5942-5945: E224
    project = _project()
    project.sources.group_definitions = [
        SourceGroupDefinition(group_name="G1", member_source_ids=["NOPE"])]
    assert _errors(project, "member_source_ids")


# ---------------------------------------------------------------------------
# C3: SO / RE INCLUDED and EVALCART supply sources and receptors
# ---------------------------------------------------------------------------

_DECK = """CO STARTING
   TITLEONE t
   MODELOPT CONC ELEV
   AVERTIME 1
   POLLUTID SO2
   RUNORNOT RUN
CO FINISHED
SO STARTING
{so}
   SRCGROUP ALL
SO FINISHED
RE STARTING
{re}
RE FINISHED
ME STARTING
   SURFFILE a.sfc
   PROFFILE a.pfl
   SURFDATA 14735 1988
   UAIRDATA 14735 1988
   PROFBASE 0.0 METERS
ME FINISHED
OU STARTING
   RECTABLE ALLAVE FIRST
OU FINISHED
"""
_SRC = ("   LOCATION S1 POINT 0 0 0\n"
        "   SRCPARAM S1 1.0 20 400 10 2")


def test_sources_from_so_included_count(tmp_path):
    (tmp_path / "src.dat").write_text(_SRC + "\n")
    deck = tmp_path / "a.inp"
    deck.write_text(_DECK.format(so="   INCLUDED src.dat", re="   DISCCART 100 100"))
    assert _errors(read_aermod_input(deck), "sources") == []


@pytest.mark.parametrize("re_line", ["   INCLUDED rec.dat", "   EVALCART 100 100 0 0 0 ARC1"])
def test_receptors_from_re_included_or_evalcart_count(tmp_path, re_line):
    (tmp_path / "rec.dat").write_text("   DISCCART 100 100\n")
    deck = tmp_path / "a.inp"
    deck.write_text(_DECK.format(so=_SRC, re=re_line))
    assert _errors(read_aermod_input(deck), "grids/receptors") == []


# ---------------------------------------------------------------------------
# C4: stack temperature (soset.f PPARM 2770-2782; calc1.f 5965-5969)
# Ts == 0 is an ambient release, Ts < 0 is a fixed Ts - Ta offset, and only
# 0 < Ts < 200 K is fatal (E320).  Setup-only bin/aermod runs agree.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ts", [0.0, -30.0])
def test_zero_or_negative_stack_temp_is_valid(ts):
    assert _errors(_project(sources=[_stack(stack_temp=ts)]), "stack_temp") == []


@pytest.mark.parametrize("ts", [1.0, 100.0, 199.9])
def test_stack_temp_between_0_and_200_kelvin_is_an_error(ts):
    assert _errors(_project(sources=[_stack(stack_temp=ts)]), "stack_temp")


@pytest.mark.parametrize("field", ["stack_diameter", "stack_height"])
def test_zero_stack_diameter_or_height_is_valid(field):
    # PPARM: DS < 1e-5 is reset to 1e-5, HS only E209 when negative
    assert _errors(_project(sources=[_stack(**{field: 0.0})]), field) == []


# ---------------------------------------------------------------------------
# C5: METHOD_2 provides the particle category (soset.f METH_2 5658/5768
# sets INPD = 1; SRCQA 1181-1186 E242 only when INPD == 0)
# ---------------------------------------------------------------------------

def test_method_2_satisfies_deposition_requirement():
    src = _stack(method_2=Method2Params(fine_mass_fraction=0.55, mass_mean_diameter=1.2))
    project = _project(sources=[src], regulatory_default=False, alpha=True,
                       calculate_dry_deposition=True)
    assert _errors(project, "deposition") == []


# ---------------------------------------------------------------------------
# C6 / B5: URBANOPT with a population only (coset.f URBOPT 4911-4925)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("control", [
    {"urban_population": 100000.0},
    {"urban_areas": [UrbanArea(population=100000.0)]},
])
def test_urban_source_with_population_only(control):
    project = _project(sources=[_stack(is_urban=True)], **control)
    assert _errors(project, "urban_option") == []


def test_urban_source_without_any_urbanopt_is_an_error():
    project = _project(sources=[_stack(is_urban=True)])
    assert _errors(project)


@pytest.mark.parametrize("control", [
    {"urban_population": 50.0},
    {"urban_areas": [UrbanArea(population=50.0)]},
])
def test_urban_population_below_100_is_an_error(control):
    # coset.f URBOPT 4851-4854 / 4917-4920: E203
    project = _project(sources=[_stack(is_urban=True)], **control)
    # (not the C6 false error about the missing urban name)
    assert [e for e in _errors(project)
            if "urban_option is not set" not in e.message]


# ---------------------------------------------------------------------------
# C7: no fixed receptor limit (aermod.f RECSIZ 7333-7350 counts, then allocates)
# ---------------------------------------------------------------------------

def test_large_receptor_grid_is_not_an_error():
    project = _project()
    project.receptors.cartesian_grids = [CartesianGrid(
        grid_name="BIG", x_init=0, x_num=400, x_delta=10,
        y_init=0, y_num=400, y_delta=10)]
    findings = advanced_validate(project)
    assert [f for f in findings if f.severity == "error"] == []


# ---------------------------------------------------------------------------
# C9: TTRM needs ozone and ALPHA (coset.f 554-570 E283; MODOPT 1810-1815 E198)
# ---------------------------------------------------------------------------

def test_ttrm_without_ozone_is_an_error():
    chem = ChemistryOptions(method=ChemistryMethod.TTRM)
    project = _project(pollutant_id="NO2", regulatory_default=False, alpha=True,
                       chemistry=chem)
    assert any("zone" in e.message for e in _errors(project))


def test_empty_ozone_data_is_an_error():
    # OzoneData() writes no OZONEVAL/OZONEFIL/O3VALUES card: E283
    chem = ChemistryOptions(method=ChemistryMethod.OLM, ozone_data=OzoneData())
    project = _project(pollutant_id="NO2", regulatory_default=False, chemistry=chem)
    assert any("zone" in e.message for e in _errors(project))


def test_ttrm_without_alpha_is_an_error():
    chem = ChemistryOptions(method=ChemistryMethod.TTRM,
                            ozone_data=OzoneData(uniform_value=40.0))
    project = _project(pollutant_id="NO2", regulatory_default=False, alpha=False,
                       chemistry=chem)
    assert any("ALPHA" in e.message for e in _errors(project))


# ---------------------------------------------------------------------------
# C10: source IDs (soset.f SOLOCA 2063-2076: E230 > 12 chars, E285 reserved;
# AERMOD upper-cases the deck so 's1' and 'S1' collide: E310)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ids", [
    ("S1", "s1"),
    ("ABCDEFGHIJKLM",),
    ("BACKGROUND",),
    ("BACKGRND",),
])
def test_invalid_source_ids_are_errors(ids):
    srcs = [_stack(sid, x_coord=10 * i) for i, sid in enumerate(ids)]
    assert _errors(_project(sources=srcs))


# ---------------------------------------------------------------------------
# C11: one source cannot be both gas and particle (soset.f SRCQA 1187-1191 E289)
# ---------------------------------------------------------------------------

def test_gas_and_particle_deposition_on_one_source_is_an_error():
    src = _stack(
        gas_deposition=GasDepositionParams(
            diffusivity=0.1, diffusivity_water=1e-5,
            cuticular_resistance=100, henry_constant=0.01),
        particle_deposition=ParticleDepositionParams(
            diameters=[1.0], mass_fractions=[1.0], densities=[1.0]),
    )
    project = _project(sources=[src], regulatory_default=False, alpha=True,
                       calculate_deposition=True, pollutant_id="SO2")
    assert _errors(project)


# ---------------------------------------------------------------------------
# Real EPA decks write: read_aermod_input(...).to_aermod_input(validate=True)
# must not raise for any deck AERMOD runs (B4, B5).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "deck", sorted(p.name for p in EPA_OFFICIAL.glob("*.inp")))
def test_epa_official_deck_writes_with_validation(deck):
    read_aermod_input(EPA_OFFICIAL / deck).to_aermod_input(validate=True)


# ---------------------------------------------------------------------------
# More of C2: BACKGROUND needs background data, ranges are checked, and
# background that no group names is left out of every result.
# ---------------------------------------------------------------------------

def _with_background(project):
    project.sources.background = BackgroundConcentration(uniform_value=10.0)
    return project


def test_background_member_without_background_data_is_an_error():
    # soset.f SRCGRP 5913-5918: E323
    project = _project()
    project.sources.group_definitions = [
        SourceGroupDefinition(group_name="G1", member_source_ids=["S1", "BACKGROUND"])]
    assert any("E323" in e.message for e in _errors(project, "member_source_ids"))


def test_background_member_with_background_data_is_accepted():
    project = _with_background(_project())
    project.sources.group_definitions = [
        SourceGroupDefinition(group_name="G1", member_source_ids=["S1", "backgrnd"])]
    assert _errors(project, "member_source_ids") == []


def test_background_in_no_group_is_warned():
    project = _with_background(_project())
    found = [e for e in Validator.validate(project).errors if e.field == "background"]
    assert [e.severity for e in found] == ["warning"]


def test_background_in_a_group_is_not_warned():
    project = _with_background(_project())
    project.sources.group_definitions = [
        SourceGroupDefinition(group_name="ALL", member_source_ids=["BACKGROUND"])]
    assert not [e for e in Validator.validate(project).errors if e.field == "background"]


def test_reversed_source_id_range_is_an_error():
    # soset.f SRCGRP: upper end below lower end is E203 SRCRANGE
    project = _project(sources=[_stack("STACK1"), _stack("STACK2", x_coord=50)])
    project.sources.group_definitions = [
        SourceGroupDefinition(group_name="G1", member_source_ids=["STACK2-STACK1"])]
    assert _errors(project, "member_source_ids")


def test_unknown_member_with_so_included_is_a_warning(tmp_path):
    (tmp_path / "src.dat").write_text(_SRC.replace("S1", "INC1") + "\n")
    deck = tmp_path / "a.inp"
    deck.write_text(_DECK.format(so=_SRC + "\n   INCLUDED src.dat", re="   DISCCART 100 100")
                    .replace("   SRCGROUP ALL", "   SRCGROUP ALL\n   SRCGROUP G1 S1 INC1"))
    project = read_aermod_input(deck)
    found = [e for e in Validator.validate(project).errors if e.field == "member_source_ids"]
    assert found and all(e.severity == "warning" for e in found)


def test_no_receptors_and_no_receptor_lines_is_still_an_error():
    project = _project()
    project.receptors.cartesian_grids = []
    assert _errors(project, "grids/receptors")


# ---------------------------------------------------------------------------
# More of C10 (also gui-live G4): blank IDs, blanks inside, BUOYLINE segments
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sid", ["", "   ", "A B"])
def test_blank_or_spaced_source_id_is_an_error(sid):
    assert _errors(_project(sources=[_stack(sid)]), "source_id")


def test_twelve_character_source_id_is_valid():
    assert _errors(_project(sources=[_stack("ABCDEFGHIJKL")]), "source_id") == []


def test_buoyline_segment_id_colliding_with_a_source_is_an_error():
    blp = BuoyLineSource(
        source_id="BLP", avg_line_length=100, avg_building_height=10,
        avg_building_width=20, avg_line_width=5, avg_building_separation=10,
        avg_buoyancy_parameter=500,
        line_segments=[BuoyLineSegment("S1", 0, 0, 100, 0),
                       BuoyLineSegment("L2", 0, 20, 100, 20)])
    project = _project(sources=[_stack("S1", x_coord=500), blp])
    assert any("duplicate" in e.message for e in _errors(project, "source_id"))


# ---------------------------------------------------------------------------
# More of C1: the pollutant name AERMOD would truncate
# ---------------------------------------------------------------------------

def test_pollutant_longer_than_eight_characters_is_warned():
    found = [e for e in Validator.validate(_project(pollutant_id="BENZENE123")).errors
             if e.field == "pollutant_id"]
    assert [e.severity for e in found] == ["warning"]


# ---------------------------------------------------------------------------
# slice-a A5: a card longer than AERMOD's 512-character record (ISTRG)
# ---------------------------------------------------------------------------

def test_card_longer_than_512_characters_is_an_error():
    ids = [f"STACK{i:04d}" for i in range(60)]
    project = _project(sources=[_stack(sid, x_coord=10 * i) for i, sid in enumerate(ids)])
    project.sources.group_definitions = [
        SourceGroupDefinition(group_name="GRP1", member_source_ids=ids)]
    found = _errors(project, "deck")
    assert found and "SRCGROUP" in found[0].message


def test_short_cards_are_fine():
    assert _errors(_project(), "deck") == []


def test_no_default_no2_ratio_does_not_crash_the_chemistry_check():
    """A deck with no NO2STACK card has no default ratio; None is not a number to range-check."""
    from types import SimpleNamespace

    from pyaermod.validator import ValidationResult, Validator

    chemistry = SimpleNamespace(
        default_no2_ratio=None, ozone_data=None, method=SimpleNamespace(value="ARM2"),
        nox_file=None, olm_groups=[], psd_groups=[],
    )
    control = SimpleNamespace(pollutant_id="NO2", alpha=False)
    result = ValidationResult()
    try:
        Validator._validate_chemistry(chemistry, control, result)
    except TypeError as exc:  # the old range check compared None with 0
        raise AssertionError(f"range check ran on None: {exc}") from exc
    except AttributeError:
        pass  # a later check wanting a fuller object is not what this test is about
    assert not any(e.field == "default_no2_ratio" for e in result.errors)
