"""Validator checks added with the regulatory-text corrections.

CO LOW_WIND (coset.f LOW_WND, identical in v23132, v24142 and v26135):
the card needs MODELOPT ALPHA (E133), which AERMOD refuses beside DFAULT
(E204); six numbers with ranges (E380, E208, E426) and the word PBAL.

URBANSRC (soset.f URBANS): with more than one URBANOPT card the urban
area's ID comes before the sources, so an urban source needs its
``urban_area_name``.
"""

from __future__ import annotations

import pytest

from pyaermod import (
    AERMODProject,
    CartesianGrid,
    ControlPathway,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.naaqs import NAAQS_TABLE, get_naaqs
from pyaermod.pathways import UrbanArea
from pyaermod.validator import Validator


def _project(sources=None, **ctrl_kw) -> AERMODProject:
    ctrl_kw.setdefault("terrain_type", "ELEV")
    sources = sources or [_stack("S1")]
    return AERMODProject(
        control=ControlPathway(title_one="t", **ctrl_kw),
        sources=SourcePathway(sources=sources),
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid(
            grid_name="G", x_init=-100, x_num=5, x_delta=50,
            y_init=-100, y_num=5, y_delta=50)]),
        meteorology=MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl"),
        output=OutputPathway(),
    )


def _stack(source_id, **kw) -> PointSource:
    return PointSource(source_id=source_id, x_coord=0, y_coord=0, stack_height=30.0,
                       stack_temp=400.0, exit_velocity=10.0, stack_diameter=2.0,
                       emission_rate=1.0, **kw)


def _low_wind_errors(**ctrl_kw):
    result = Validator.validate(_project(**ctrl_kw))
    return [e.message for e in result.errors
            if e.field == "low_wind_option" and e.severity == "error"]


ALPHA = {"regulatory_default": False, "alpha": True}


@pytest.mark.parametrize("option", [
    "0.3",
    "0.3 0.5",
    "0.2 0.2828 1.0 0.02 24.0 0.0",
    "0.01 1.001 0.0 3.0 48 0.0 PBAL",
    "1.0 0.5 0.95 0.02 0.5 0.5 pbalance",
    "2D-1 5.0E-1",
])
def test_valid_low_wind_fields_pass_with_alpha(option):
    assert _low_wind_errors(low_wind_option=option, **ALPHA) == []


@pytest.mark.parametrize("option,code", [
    ("LOWWIND3", "E208"),
    ("0.3 abc", "E208"),
    ("0.005", "E380"),        # SVmin below 0.01
    ("1.5", "E380"),          # SVmin above 1.001
    ("0.3 0.0", "E380"),      # WSmin below 0.01
    ("0.3 0.5 1.5", "E380"),  # FRANmax above 1
    ("0.3 0.5 1.0 3.5", "E380"),           # SWmin above 3
    ("0.3 0.5 1.0 0.02 0.1", "E380"),      # BigT below 0.5
    ("0.3 0.5 1.0 0.02 60", "E380"),       # BigT above 48
    ("0.3 0.5 0.5 0.02 24 0.8", "E426"),   # FRANmin above FRANmax
    # FRANmax unreadable (E208) but FRANmin given: this raised KeyError. AERMOD
    # compares FRANmin with its default FRANmax (1.0) and reports only E208
    # (real v24142 and v26135 runs, 2026-11-21).
    ("0.3 0.5 abc 0.02 24 0.3", "E208"),
    ("0.3 0.5 1.0 0.02 24 0.0 YES", "E203"),
    ("0.3 0.5 1.0 0.02 24 0.0 PBAL 1", "E202"),
])
def test_bad_low_wind_fields_are_errors(option, code):
    errors = _low_wind_errors(low_wind_option=option, **ALPHA)
    assert len(errors) == 1 and code in errors[0], errors


def test_low_wind_needs_alpha():
    errors = _low_wind_errors(low_wind_option="0.3 0.5", regulatory_default=False)
    assert len(errors) == 1 and "E133" in errors[0]


@pytest.mark.parametrize("alpha", [False, True])
def test_low_wind_is_an_error_with_dfault(alpha):
    errors = _low_wind_errors(low_wind_option="0.3 0.5", regulatory_default=True,
                              alpha=alpha)
    assert len(errors) == 1 and "DFAULT" in errors[0]


def test_no_low_wind_option_says_nothing():
    assert _low_wind_errors() == []


# ---------------------------------------------------------------------
# Several urban areas
# ---------------------------------------------------------------------

TWO_AREAS = [UrbanArea(population=500000, urban_id="A1"),
             UrbanArea(population=200000, urban_id="B2")]


def _urban_name_errors(project):
    return [e for e in Validator.validate(project).errors if e.field == "urban_area_name"]


def test_urban_source_without_an_area_is_an_error_with_several_areas():
    project = _project(sources=[_stack("S1", is_urban=True, urban_area_name="A1"),
                                _stack("S2", is_urban=True)],
                       urban_areas=TWO_AREAS)
    errors = _urban_name_errors(project)
    assert len(errors) == 1
    assert "S2" in errors[0].pathway and errors[0].severity == "error"


def test_one_urban_area_needs_no_area_name():
    project = _project(sources=[_stack("S1", is_urban=True)],
                       urban_areas=TWO_AREAS[:1])
    assert _urban_name_errors(project) == []


def test_a_rural_source_needs_no_area_name():
    project = _project(sources=[_stack("S1", is_urban=True, urban_area_name="B2"),
                                _stack("S2")],
                       urban_areas=TWO_AREAS)
    assert _urban_name_errors(project) == []


# ---------------------------------------------------------------------
# NAAQS table: labels and citations (40 CFR Part 50 as of 2026-11-17)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("pollutant,period,level,cites", [
    ("PM2.5", "annual", 9.0, ["50.20", "App. N"]),
    ("PM2.5", "24-hour", 35.0, ["50.20", "App. N"]),
    ("PM10", "24-hour", 150.0, ["50.6(a)", "App. K"]),
    ("NO2", "annual", 53.0, ["50.11(a), (e)", "App. S"]),
    ("NO2", "1-hour", 100.0, ["50.11(b), (f)", "App. S"]),
])
def test_citations_name_the_section_in_force(pollutant, period, level, cites):
    std = get_naaqs(pollutant, period)
    assert std.level == level  # the corrections change no number
    for cite in cites:
        assert cite in std.cfr_reference


def test_no_standard_cites_the_superseded_pm25_section():
    assert not [s for rows in NAAQS_TABLE.values() for s in rows
                if "50.18" in s.cfr_reference]


def test_pm10_form_is_expected_exceedances_over_three_years():
    form = get_naaqs("PM10", "24-hour").form
    assert "expected exceedances" in form and "3-yr" in form
    assert "5-yr" not in form
