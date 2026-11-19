"""Deck-writer behaviour checked against AERMOD v24142 / v26135.

Each test states what AERMOD reads (Fortran routine cited) and asserts
the deck pyaermod writes matches it. All of them were run through the
real binaries in the 2026-11 codebase review (verify/v-deck).
"""

from __future__ import annotations

import shlex

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    BackgroundConcentration,
    BuoyLineSegment,
    BuoyLineSource,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    ParticleDepositionParams,
    PointSource,
    ReceptorPathway,
    SourceGroupDefinition,
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
# A3: BACKGRND is not in group ALL unless the ALL card says BACKGROUND
# (soset.f SOGRP; SRCQA W321). With the default deck the reported
# concentrations carry no background at all.
# ---------------------------------------------------------------------

def test_background_in_group_all_passes_validation():
    """``SRCGROUP ALL BACKGROUND`` is the only way to add the background
    to ALL; AERMOD accepts it, so the validator must too."""
    p = _project(background=BackgroundConcentration(uniform_value=3.0),
                 group_definitions=[SourceGroupDefinition("ALL", ["BACKGROUND"])])
    text = p.to_aermod_input()  # must not raise
    assert ["SRCGROUP", "ALL", "BACKGROUND"] in _block(text, "SO")


def test_background_in_no_group_is_reported():
    p = _project(background=BackgroundConcentration(uniform_value=3.0))
    result = Validator.validate(p)
    messages = [str(m) for m in result.errors + result.warnings]
    assert any("BACKGROUND" in m.upper() and "GROUP" in m.upper() for m in messages), messages


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
# A5: AERMOD reads each runstream record as A512 (modules.f ISTRG=512,
# setup.f line 121) and drops the rest without a message.
# ---------------------------------------------------------------------

def test_no_card_is_longer_than_512_characters_and_no_member_is_lost():
    ids = [f"STACK{i:04d}" for i in range(100)]
    p = _project(sources=[_stack(s) for s in ids],
                 group_definitions=[SourceGroupDefinition("GRP1", ids)])
    text = p.to_aermod_input()
    assert max(len(ln) for ln in text.splitlines()) <= 512
    members = [m for c in _block(text, "SO") if c[:2] == ["SRCGROUP", "GRP1"] for m in c[2:]]
    assert members == ids


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
