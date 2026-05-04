"""Tests for the GUI v2 project save/load round-trip."""

from __future__ import annotations

import json

import pytest

from pyaermod import (
    AERMODProject,
    AreaPolySource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    LineSource,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
    SourcePathway,
)
from pyaermod.gui_v2.project_io import (
    SAVE_FORMAT_VERSION,
    load_project,
    save_project,
)


def _full_project():
    return AERMODProject(
        control=ControlPathway(
            title_one="Test run", title_two="Line two",
            pollutant_id=PollutantType.NO2,
            averaging_periods=["1", "ANNUAL"],
        ),
        sources=SourcePathway(sources=[
            PointSource(
                source_id="STK1", x_coord=100.0, y_coord=200.0,
                stack_height=30.0, stack_temp=400.0, exit_velocity=10.0,
                stack_diameter=2.0, emission_rate=1.0,
            ),
            LineSource(
                source_id="LINE1", x_start=0.0, y_start=0.0,
                x_end=100.0, y_end=0.0,
                emission_rate=0.5, release_height=2.0,
            ),
            AreaPolySource(
                source_id="AP1",
                vertices=[(0, 0), (10, 0), (10, 10), (0, 10)],
                emission_rate=0.1, release_height=1.0,
            ),
        ]),
        receptors=ReceptorPathway(
            cartesian_grids=[CartesianGrid()],
            polar_grids=[PolarGrid(grid_name="POL1",
                                   x_origin=0.0, y_origin=0.0)],
            discrete_receptors=[
                DiscreteReceptor(x_coord=500.0, y_coord=500.0),
            ],
        ),
        meteorology=MeteorologyPathway(
            surface_file="x.sfc", profile_file="x.pfl",
        ),
        output=OutputPathway(),
    )


class TestRoundTrip:
    def test_basic_roundtrip(self, tmp_path):
        p1 = _full_project()
        save_project(p1, tmp_path / "out.json")
        p2 = load_project(tmp_path / "out.json")
        assert p2.control.title_one == "Test run"
        assert p2.control.pollutant_id == PollutantType.NO2

    def test_sources_dispatched_to_correct_classes(self, tmp_path):
        p1 = _full_project()
        save_project(p1, tmp_path / "out.json")
        p2 = load_project(tmp_path / "out.json")
        types = [type(s).__name__ for s in p2.sources.sources]
        assert types == ["PointSource", "LineSource", "AreaPolySource"]

    def test_source_field_values_preserved(self, tmp_path):
        p1 = _full_project()
        save_project(p1, tmp_path / "out.json")
        p2 = load_project(tmp_path / "out.json")
        s = p2.sources.sources[0]
        assert s.source_id == "STK1"
        assert s.stack_height == 30.0
        assert s.emission_rate == 1.0

    def test_receptor_roundtrip(self, tmp_path):
        p1 = _full_project()
        save_project(p1, tmp_path / "out.json")
        p2 = load_project(tmp_path / "out.json")
        assert len(p2.receptors.cartesian_grids) == 1
        assert len(p2.receptors.polar_grids) == 1
        assert p2.receptors.polar_grids[0].grid_name == "POL1"
        assert len(p2.receptors.discrete_receptors) == 1
        assert p2.receptors.discrete_receptors[0].x_coord == 500.0

    def test_polygon_vertices_preserved(self, tmp_path):
        p1 = _full_project()
        save_project(p1, tmp_path / "out.json")
        p2 = load_project(tmp_path / "out.json")
        ap = next(s for s in p2.sources.sources
                  if type(s).__name__ == "AreaPolySource")
        assert len(ap.vertices) == 4

    def test_meteorology_paths_preserved(self, tmp_path):
        p1 = _full_project()
        save_project(p1, tmp_path / "out.json")
        p2 = load_project(tmp_path / "out.json")
        assert p2.meteorology.surface_file == "x.sfc"
        assert p2.meteorology.profile_file == "x.pfl"


class TestFileFormat:
    def test_writes_format_version(self, tmp_path):
        save_project(_full_project(), tmp_path / "out.json")
        raw = json.loads((tmp_path / "out.json").read_text())
        assert raw["save_format_version"] == SAVE_FORMAT_VERSION

    def test_writes_pyaermod_version(self, tmp_path):
        from pyaermod import __version__
        save_project(_full_project(), tmp_path / "out.json")
        raw = json.loads((tmp_path / "out.json").read_text())
        assert raw["pyaermod_version"] == __version__

    def test_creates_parent_directory(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "out.json"
        save_project(_full_project(), target)
        assert target.exists()

    def test_pollutant_enum_round_trip(self, tmp_path):
        p1 = _full_project()
        save_project(p1, tmp_path / "out.json")
        raw = json.loads((tmp_path / "out.json").read_text())
        assert raw["project"]["control"]["pollutant_id"]["_enum"] == \
            "PollutantType.NO2"

    def test_load_rejects_non_pyaermod_json(self, tmp_path):
        bogus = tmp_path / "bogus.json"
        bogus.write_text(json.dumps({"hello": "world"}))
        with pytest.raises(ValueError, match="not a pyaermod project"):
            load_project(bogus)

    def test_load_rejects_unknown_format_version(self, tmp_path):
        bogus = tmp_path / "future.json"
        bogus.write_text(json.dumps({
            "pyaermod_version": "99.0",
            "save_format_version": 999,
            "project": {},
        }))
        with pytest.raises(ValueError, match="format_version"):
            load_project(bogus)
