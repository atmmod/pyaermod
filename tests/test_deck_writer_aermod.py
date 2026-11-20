"""Deck-writer behaviour checked against AERMOD v24142 / v26135.

Each test states what AERMOD reads (Fortran routine cited) and asserts
the deck pyaermod writes matches it. All of them were run through the
real binaries in the 2026-11 codebase review.
"""

from __future__ import annotations

import shlex

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    BuoyLineSegment,
    BuoyLineSource,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    ParticleDepositionParams,
    PointSource,
    ReceptorPathway,
    SourcePathway,
    UrbanArea,
)
from pyaermod.input_reader import parse_aermod_input
from pyaermod.validator import Validator


def _stack(sid="S1", **kw):
    params = dict(stack_height=30.0, stack_temp=400.0, exit_velocity=10.0,
                  stack_diameter=1.0, emission_rate=1.0)
    params.update(kw)
    return PointSource(sid, 0.0, 0.0, **params)


def _project(sources=None, control=None, receptors=None, met=None, **so_kw):
    return AERMODProject(
        control=control or ControlPathway("t", averaging_periods=["1"], regulatory_default=False),
        sources=SourcePathway(sources=sources or [_stack()], **so_kw),
        receptors=receptors or ReceptorPathway(discrete_receptors=[DiscreteReceptor(500.0, 0.0)]),
        meteorology=met or MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )


def _block(text, code):
    """The cards of one pathway, STARTING and FINISHED excluded, as token lists."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.split() == [code, "STARTING"])
    end = next(i for i, ln in enumerate(lines) if ln.split() == [code, "FINISHED"])
    return [shlex.split(ln) for ln in lines[start + 1:end] if ln.strip()]


# ---------------------------------------------------------------------
# A1: ELEVUNIT belongs to SO and RE (soset.f SOCARD -> SOELUN,
# reset.f RECARD -> REELUN); COCARD has no branch for it (E110).
# ---------------------------------------------------------------------

def test_elevunit_feet_is_never_a_co_card():
    p = _project(control=ControlPathway("t", averaging_periods=["1"], elevation_units="FEET"),
                 receptors=ReceptorPathway(discrete_receptors=[DiscreteReceptor(500.0, 0.0)],
                                           elevation_units="FEET"))
    text = p.to_aermod_input(validate=False)
    assert not any(card[0] == "ELEVUNIT" for card in _block(text, "CO"))


def test_elevunit_feet_is_the_first_so_card():
    p = _project(control=ControlPathway("t", averaging_periods=["1"], elevation_units="FEET"))
    text = p.to_aermod_input(validate=False)
    assert _block(text, "SO")[0] == ["ELEVUNIT", "FEET"]


# ---------------------------------------------------------------------
# A2: with several URBANOPT cards, URBANSRC is ``urbid srcid...``
# (soset.f URBANS, L_MULTURB branch: FIELD(3) is the urban ID).
# ---------------------------------------------------------------------

def test_urbansrc_names_the_area_when_there_are_several():
    control = ControlPathway("t", averaging_periods=["1"], urban_areas=[
        UrbanArea(500000, urban_id="A1"), UrbanArea(200000, urban_id="B2")])
    p = _project(sources=[_stack("S1", is_urban=True, urban_area_name="A1"),
                          _stack("S2", is_urban=True, urban_area_name="B2")],
                 control=control)
    cards = [c for c in _block(p.to_aermod_input(validate=False), "SO") if c[0] == "URBANSRC"]
    assert sorted(cards) == [["URBANSRC", "A1", "S1"], ["URBANSRC", "B2", "S2"]]


# ---------------------------------------------------------------------
# A4: deposition cards are keyed by source ID; a BUOYLINE's sources are
# its segments, not the BLPGROUP ID (soset.f PARTDEP; a BLPGROUP ID
# there indexes L_METHOD2 with 0 and AERMOD aborts).
# ---------------------------------------------------------------------

def test_buoyline_deposition_cards_name_the_segments():
    dep = ParticleDepositionParams([5.0, 10.0], [0.5, 0.5], [1.0, 1.0])
    blp = BuoyLineSource("BLD", 10, 3, 3, 1, 5, 1e4,
                         [BuoyLineSegment("L1", 0, 0, 10, 0), BuoyLineSegment("L2", 0, 5, 10, 5)],
                         particle_deposition=dep)
    text = blp.to_aermod_input()
    for keyword in ("PARTDIAM", "MASSFRAX", "PARTDENS"):
        ids = sorted(ln.split()[1] for ln in text.splitlines() if ln.split()[:1] == [keyword])
        assert ids == ["L1", "L2"], (keyword, ids)


# ---------------------------------------------------------------------
# A7: AERMOD has no default in-stack ratio (setup.f:1708 removed it;
# coset.f resets ANO2_RATIO to -9 without NO2STACK and soset.f SRCQA
# gives E336). A deck that has no NO2STACK must not gain one.
# ---------------------------------------------------------------------

_OLM_DECK = """\
CO STARTING
   TITLEONE  olm
   MODELOPT  CONC FLAT OLM
   AVERTIME  1
   POLLUTID  NO2
   OZONEVAL  40 PPB
   RUNORNOT  RUN
CO FINISHED
SO STARTING
   LOCATION  S1 POINT 0 0 0
   SRCPARAM  S1 1.0 30 400 10 1
   NO2RATIO  S1 0.2
   SRCGROUP  ALL
SO FINISHED
RE STARTING
   DISCCART  500 0
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  14735 1988
   UAIRDATA  14735 1988
   PROFBASE  0 METERS
ME FINISHED
OU STARTING
   RECTABLE  ALLAVE FIRST
OU FINISHED
"""


def test_rewrite_does_not_invent_no2stack():
    text = parse_aermod_input(_OLM_DECK).to_aermod_input(validate=False)
    assert "NO2STACK" not in text


def test_olm_source_without_any_ratio_is_an_error():
    """E336 in AERMOD: no NO2STACK and no NO2RATIO for the source."""
    deck = _OLM_DECK.replace("   NO2RATIO  S1 0.2\n", "")
    result = Validator.validate(parse_aermod_input(deck))
    assert not result.is_valid
    assert any(e.field == "no2_ratio" and "E336" in e.message for e in result.errors)


def test_olm_source_with_its_own_ratio_needs_no_no2stack():
    result = Validator.validate(parse_aermod_input(_OLM_DECK))
    assert not [e for e in result.errors if e.field == "no2_ratio"]


# ---------------------------------------------------------------------
# arch A2: DEFINE splits fields at blanks outside double quotes
# (setup.f DEFINE); an unquoted met path with a blank is E500 in
# MEOPEN, the quoted one runs.
# ---------------------------------------------------------------------

def test_met_file_with_blank_is_written_as_one_field():
    met = MeteorologyPathway(surface_file="My Met/a.sfc", profile_file="My Met/a.pfl")
    text = _project(met=met).to_aermod_input(validate=False)
    cards = {c[0]: c[1:] for c in _block(text, "ME")}
    assert cards["SURFFILE"] == ["My Met/a.sfc"]
    assert cards["PROFFILE"] == ["My Met/a.pfl"]
    assert '"My Met/a.sfc"' in text


# ---------------------------------------------------------------------
# DOCS-2: a refused write must leave an existing deck alone.
# ---------------------------------------------------------------------

def test_refused_write_keeps_the_existing_file(tmp_path):
    target = tmp_path / "aermod.inp"
    target.write_text("OLDCONTENT\n")
    bad = _project(sources=[_stack("S1", stack_height=-5.0)])
    with pytest.raises(ValueError):
        bad.write(target)
    assert target.read_text() == "OLDCONTENT\n"


def test_refused_write_creates_no_file(tmp_path):
    target = tmp_path / "new" / "aermod.inp"
    bad = _project(sources=[_stack("S1", stack_height=-5.0)])
    with pytest.raises(ValueError):
        bad.write(target)
    assert not target.exists()


# ---------------------------------------------------------------------
# slice-a A6 / A8: values the reader keeps must be written back as read.
# ---------------------------------------------------------------------

def test_areacirc_szinit_round_trips():
    """soset.f ACPARM: emis relhgt radius [nverts [szinit]]."""
    deck = _OLM_DECK.replace("   LOCATION  S1 POINT 0 0 0\n   SRCPARAM  S1 1.0 30 400 10 1\n",
                             "   LOCATION  S1 AREACIRC 0 0 0\n   SRCPARAM  S1 0.001 2 50 16 3.5\n")
    src = parse_aermod_input(deck).sources.sources[0]
    assert src.initial_sigma_z == pytest.approx(3.5)
    srcparam = src.to_aermod_input().splitlines()[1].split()
    assert srcparam[0] == "SRCPARAM"
    assert srcparam[-2:] == ["16", "3.50"]


def test_ratios_and_particles_are_written_as_read():
    deck = (_OLM_DECK.replace("NO2RATIO  S1 0.2", "NO2RATIO  S1 0.12345")
            .replace("OZONEVAL  40 PPB", "OZONEVAL  40 PPB\n   NO2STACK  0.123456")
            .replace("   SRCGROUP  ALL", "   PARTDIAM  S1 1.23456 12.3456\n   MASSFRAX  S1 0.5 0.5\n"
                                          "   PARTDENS  S1 2.65432 1.23456\n   SRCGROUP  ALL"))
    text = parse_aermod_input(deck).to_aermod_input(validate=False)
    cards = {ln.split()[0]: ln.split()[1:] for ln in text.splitlines() if ln.strip()}
    assert cards["NO2RATIO"] == ["S1", "0.12345"]
    assert cards["NO2STACK"] == ["0.123456"]
    assert cards["PARTDIAM"] == ["S1", "1.23456", "12.3456"]
    assert cards["PARTDENS"] == ["S1", "2.65432", "1.23456"]


def test_small_values_are_numbers_aermod_reads():
    """STODBL takes an exponent only after a decimal point (``1e-05`` is E208)."""
    from pyaermod.pathways import exact_num
    assert exact_num(1e-05) == "1.0e-05"
    assert exact_num(0.5) == "0.5"


def test_low_wind_option_is_written_as_given():
    """coset.f LOW_WND: numeric fields, ALPHA required (E133)."""
    control = ControlPathway("t", averaging_periods=["1"], regulatory_default=False,
                             alpha=True, low_wind_option="0.3 0.5")
    assert ["LOW_WIND", "0.3", "0.5"] in _block(_project(control=control).to_aermod_input(validate=False), "CO")


def test_write_keeps_file_mode(tmp_path):
    import os
    import stat
    target = tmp_path / "aermod.inp"
    target.write_text("OLD\n")
    os.chmod(target, 0o640)
    _project().write(target, validate=False)
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert "SO STARTING" in target.read_text()
    assert [p.name for p in tmp_path.iterdir()] == ["aermod.inp"]
