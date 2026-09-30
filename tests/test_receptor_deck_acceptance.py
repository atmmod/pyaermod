"""AERMOD reads the receptor elevations, DEBUGOPT and depletion options
the writer emits, without the warnings that meant it was using defaults.

Under elevated terrain (``ELEV``, or ``FLAT`` overridden by ``DFAULT``)
reset.f RECART warns W214 when a Cartesian grid has no ELEV/HILL rows and
DISCAR warns W228 when a DISCCART line lacks its hill height; under FLAT
with FLAGPOLE, DISCAR reads the third field as the flagpole height. Each
case writes one project and runs the binary's setup pass (``RUNORNOT
NOT``): it must finish setup with no fatal error and none of those
warnings. The last test writes the same receptors without the run's
options, as releases before 1.x did, and expects the warnings back, so
the check can fail.

Shares the harness of :mod:`tests.test_source_deck_acceptance`, and skips
with it when the binary or EPA's meteorology is missing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    MeteorologyPathway,
    OutputPathway,
    SourcePathway,
)
from pyaermod.pathways import ControlPathway, TerrainType
from pyaermod.receptors import CartesianGrid, DiscreteReceptor, ReceptorPathway
from pyaermod.sources import OpenPitSource, ParticleDepositionParams, PointSource

from .test_source_deck_acceptance import (
    PROFILE,
    SURFACE,
    pytestmark,  # the binary/meteorology skip conditions
    run_setup_check,
)

_MESSAGE_RE = re.compile(r"^\s*(CO|SO|RE|ME|OU) ([EW]\d{3})\s+\d+\s+(\w+):", re.M)
UNWANTED = {"W213", "W214", "W216", "W228", "W229"}
GRID = dict(x_init=-500.0, x_num=3, x_delta=500.0, y_init=-500.0, y_num=3, y_delta=500.0)


def _stack() -> PointSource:
    return PointSource("SRC1", 0.0, 0.0, stack_height=50.0, stack_diameter=2.0,
                       stack_temp=400.0, exit_velocity=15.0, emission_rate=10.0)


def _pit() -> OpenPitSource:
    # The pilot's pit (paper/demo pilot, DBG deck): AREA debug needs an
    # AREA, LINE or OPENPIT source and DEPOS debug needs deposition.
    return OpenPitSource(
        "PIT", -500.0, -350.0, emission_rate=9.0e-6, x_dimension=1000.0,
        y_dimension=700.0, pit_volume=1.05e8,
        particle_deposition=ParticleDepositionParams(
            diameters=[1.85, 3.88, 7.77, 12.66, 23.3, 46.61],
            mass_fractions=[0.053, 0.147, 0.15, 0.13, 0.26, 0.26],
            densities=[2.65] * 6,
        ),
    )


def _deck(control: ControlPathway, receptors: ReceptorPathway, source=None) -> str:
    project = AERMODProject(
        control=control,
        sources=SourcePathway(sources=[source or _stack()]),
        receptors=receptors,
        meteorology=MeteorologyPathway(
            surface_file=SURFACE.name, profile_file=PROFILE.name,
            surface_station_id=14735, upper_air_station_id=14735,
            data_start_year=1988,
        ),
        output=OutputPathway(),
    )
    return re.sub(r"RUNORNOT\s+\w+", "RUNORNOT NOT", project.to_aermod_input(validate=False))


def _messages(work: Path) -> set[str]:
    text = (work / "aermod.out").read_text(encoding="latin-1", errors="replace")
    return {code for _, code, _ in _MESSAGE_RE.findall(text)}


def _receptors() -> ReceptorPathway:
    return ReceptorPathway(
        cartesian_grids=[CartesianGrid(**GRID, z_elev=12.5, z_hill=40.25)],
        discrete_receptors=[DiscreteReceptor(1000.0, 0.0),
                            DiscreteReceptor(0.0, 1000.0, 5.0, 30.0, 4.0)],
    )


def _ctl(**kw) -> ControlPathway:
    kw.setdefault("title_one", "receptor acceptance")
    kw.setdefault("averaging_periods", ["1"])
    kw.setdefault("pollutant_id", "SO2")
    return ControlPathway(**kw)


CASES = [
    ("dfault_flat_is_elev", _ctl(terrain_type=TerrainType.FLAT, regulatory_default=True), None),
    ("elev", _ctl(terrain_type=TerrainType.ELEVATED, regulatory_default=False), None),
    ("elev_flagpole", _ctl(terrain_type=TerrainType.ELEVATED, flag_pole_height=1.5), "flags"),
    ("flat_flagpole", _ctl(terrain_type=TerrainType.FLAT, regulatory_default=False,
                           flag_pole_height=1.5), "flags"),
]


@pytest.mark.parametrize(("label", "control", "flags"), CASES, ids=[c[0] for c in CASES])
def test_receptor_fields_are_read_without_defaults(label, control, flags, tmp_path):
    receptors = _receptors()
    if flags:
        # A grid's FLAG rows are written from a non-zero z_flag (W216
        # otherwise, with the FLAGPOLE height -- the same numbers).
        receptors.cartesian_grids[0].z_flag = 2.0
    deck = _deck(control, receptors)
    errors = run_setup_check(deck, tmp_path)
    assert not errors, f"{label}: " + "\n  ".join(errors) + f"\n\ndeck:\n{deck}"
    assert not (_messages(tmp_path) & UNWANTED), f"{label}:\n{deck}"


def test_pilot_debugopt_deck_needs_no_text_patch(tmp_path):
    """DEBUGOPT AREA DEPOS on an OPENPIT deposition run passes DEBOPT's E194 checks."""
    control = _ctl(terrain_type=TerrainType.ELEVATED, pollutant_id="PM10",
                   averaging_periods=["24", "PERIOD"],
                   calculate_deposition=True, calculate_dry_deposition=True,
                   calculate_wet_deposition=True, debug_options=["AREA", "DEPOS"])
    receptors = ReceptorPathway(discrete_receptors=[DiscreteReceptor(0.0, -2000.0),
                                                    DiscreteReceptor(0.0, 2000.0)])
    deck = _deck(control, receptors, source=_pit())
    assert "   DEBUGOPT  AREA  DEPOS" in deck
    errors = run_setup_check(deck, tmp_path)
    assert not errors, "\n  ".join(errors) + f"\n\ndeck:\n{deck}"
    assert not (_messages(tmp_path) & UNWANTED)


@pytest.mark.parametrize(("dry", "wet", "header"), [
    (False, False, ("NO DRY DEPLETION", "NO WET DEPLETION")),
    (True, False, ("Uses DRY DEPLETION", "NO WET DEPLETION")),
])
def test_depletion_switches_reach_aermod(dry, wet, header, tmp_path):
    control = _ctl(pollutant_id="PM10", calculate_deposition=True,
                   dry_depletion=dry, wet_depletion=wet)
    receptors = ReceptorPathway(discrete_receptors=[DiscreteReceptor(1000.0, 0.0)])
    source = _stack()
    source.particle_deposition = ParticleDepositionParams(diameters=[10.0], mass_fractions=[1.0],
                                                          densities=[1.0])
    deck = _deck(control, receptors, source=source)
    assert not run_setup_check(deck, tmp_path), deck
    text = (tmp_path / "aermod.out").read_text(encoding="latin-1", errors="replace")
    for phrase in header:
        assert phrase in text


def test_the_check_can_fail(tmp_path):
    """Without the run's options the receptors are written as before: W214 and W228."""
    receptors = _receptors()
    lines = ["RE STARTING", *(g.to_aermod_input() for g in receptors.cartesian_grids),
             *(r.to_aermod_input() for r in receptors.discrete_receptors), "RE FINISHED"]
    deck = _deck(_ctl(terrain_type=TerrainType.ELEVATED), receptors)
    deck = re.sub(r"RE STARTING.*RE FINISHED", "\n".join(lines), deck, flags=re.S)
    assert not run_setup_check(deck, tmp_path)
    assert {"W214", "W228"} <= _messages(tmp_path)
