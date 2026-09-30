"""OutputPathway.period_plot_files / period_postfiles: one file per averaging period.

The plot-file and POSTFILE layouts are those ``pathways._plotfile_fields``
and the POSTFILE writer already follow (ouset.f PERPLT/OUPLOT/OUPOST): the
short-term periods take a rank on PLOTFILE and the period forms do not.
The GUI turns both on by default for the Results step; the recordings
under tests/fixtures/gui/aermod_recordings show AERMOD v26135 accepting
the lines and writing the files.
"""

from __future__ import annotations

import pytest

from pyaermod.input_generator import (
    AERMODProject,
    ControlPathway,
    MeteorologyPathway,
    PointSource,
    PolarGrid,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.input_reader import parse_aermod_input
from pyaermod.pathways import OutputPathway, period_file_name
from pyaermod.validator import Validator


def _albany_project(periods, surface_file):
    return AERMODProject(
        control=ControlPathway(title_one="Albany", pollutant_id="SO2",
                               averaging_periods=list(periods)),
        sources=SourcePathway(sources=[PointSource(
            "STACK1", 0.0, 0.0, stack_height=65.0, stack_temp=425.0, exit_velocity=18.0,
            stack_diameter=3.0, emission_rate=100.0)]),
        receptors=ReceptorPathway(polar_grids=[PolarGrid(grid_name="GRID1")]),
        meteorology=MeteorologyPathway(surface_file, "AERMET2.PFL", surface_station_id=14735,
                                       upper_air_station_id=14735, data_start_year=1988),
        output=OutputPathway(),
    )


@pytest.mark.parametrize(("period", "name"), [
    ("1", "run_01H.plt"), ("3", "run_03H.plt"), ("24", "run_24H.plt"),
    ("MONTH", "run_MONTH.plt"), ("period", "run_PERIOD.plt"), ("ANNUAL", "run_ANNUAL.plt"),
])
def test_file_names_follow_epa_decks(period, name):
    assert period_file_name("run", period, ".plt") == name


def test_nothing_is_written_by_default():
    text = OutputPathway().to_aermod_input(averaging_periods=["1", "ANNUAL"])
    assert "PLOTFILE" not in text and "POSTFILE" not in text


def test_one_file_of_each_per_period():
    out = OutputPathway(period_plot_files="run", period_postfiles="run")
    lines = [ln.split() for ln in out.to_aermod_input(averaging_periods=["1", "24", "PERIOD"])
             .splitlines()]
    assert ["PLOTFILE", "1", "ALL", "FIRST", "run_01H.plt"] in lines
    assert ["PLOTFILE", "24", "ALL", "FIRST", "run_24H.plt"] in lines
    assert ["PLOTFILE", "PERIOD", "ALL", "run_PERIOD.plt"] in lines
    assert ["POSTFILE", "1", "ALL", "PLOT", "run_01H.pst"] in lines
    assert ["POSTFILE", "PERIOD", "ALL", "PLOT", "run_PERIOD.pst"] in lines
    assert out.period_plot_file_names(["1", "PERIOD"]) == {
        "1": "run_01H.plt", "PERIOD": "run_PERIOD.plt"}
    assert out.period_postfile_names(["24"]) == {"24": "run_24H.pst"}


def test_without_periods_nothing_is_written():
    out = OutputPathway(period_plot_files="run", period_postfiles="run")
    assert "PLOTFILE" not in out.to_aermod_input()


def test_postfile_format_is_followed():
    out = OutputPathway(period_postfiles="run", postfile_format="UNFORM")
    assert "POSTFILE  1  ALL  UNFORM  run_01H.pst" in out.to_aermod_input(averaging_periods=["1"])


def test_the_project_passes_its_periods_and_the_deck_reads_back():
    project = _albany_project(["1", "3", "24", "PERIOD"], "AERMET2.SFC")
    project.output.period_plot_files = "pyaermod"
    project.output.period_postfiles = "pyaermod"
    deck = project.to_aermod_input(validate=False)
    assert deck.count("PLOTFILE") == 4 and deck.count("POSTFILE") == 4
    again = parse_aermod_input(deck)
    # The reader keeps them as explicit plot files and POSTFILEs (the ones
    # it does not model verbatim), which write the same lines back.
    read_back = [again.output.plot_file] + [g[2] for g in again.output.plot_file_groups]
    assert sorted(read_back) == sorted(
        project.output.period_plot_file_names(project.control.averaging_periods).values())
    rewritten = again.to_aermod_input(validate=False)
    assert rewritten.count("PLOTFILE") == 4 and rewritten.count("POSTFILE") == 4


def test_noheader_counts_period_files_as_in_use():
    project = _albany_project(["1"], "AERMET2.SFC")
    project.output.no_header = ["PLOTFILE", "POSTFILE"]
    names = {e.field for e in Validator.validate(project).errors}
    assert "no_header" in names
    project.output.period_plot_files = "p"
    project.output.period_postfiles = "p"
    assert "no_header" not in {e.field for e in Validator.validate(project).errors}
