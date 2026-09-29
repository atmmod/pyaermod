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
    project_from_json,
    project_to_json,
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


class TestTextRoundTrip:
    """``project_to_json`` / ``project_from_json``: the file format as text.

    The GUI opens uploaded files and delivers Save As as a browser
    download, so it needs the format without a file on the server's disk.
    """

    def test_to_json_is_what_save_project_writes(self, tmp_path):
        project = _full_project()
        save_project(project, tmp_path / "out.json")
        assert (tmp_path / "out.json").read_text(encoding="utf-8") == project_to_json(project)

    def test_from_json_round_trips(self):
        p1 = _full_project()
        p2 = project_from_json(project_to_json(p1))
        assert p2.to_aermod_input(validate=False) == p1.to_aermod_input(validate=False)
        assert [type(s).__name__ for s in p2.sources.sources] == [
            "PointSource", "LineSource", "AreaPolySource"]

    def test_from_json_accepts_bytes(self):
        p2 = project_from_json(project_to_json(_full_project()).encode("utf-8"))
        assert p2.control.title_one == "Test run"

    def test_errors_name_their_origin(self):
        with pytest.raises(ValueError, match=r"^upload\.json: not valid JSON"):
            project_from_json("{not json", origin="upload.json")
        with pytest.raises(ValueError, match=r"^<text>: not a pyaermod project"):
            project_from_json("{}")

    def test_load_project_errors_name_the_file(self, tmp_path):
        bogus = tmp_path / "bogus.json"
        bogus.write_text("[]")
        with pytest.raises(ValueError, match=str(bogus)):
            load_project(bogus)

    @pytest.mark.parametrize("text, message", [
        ("[]", "not a pyaermod project"),
        ('"project"', "not a pyaermod project"),
        ('{"project": []}', "project must be a JSON object"),
        ('{"project": {"control": []}}', "project.control must be a JSON object"),
        ('{"project": {"sources": {"sources": {}}}}', "project.sources.sources must be a JSON list"),
        ('{"project": {"sources": {"sources": [1]}}}', r"project.sources.sources\[0\] must be a JSON object"),
        ('{"project": {"receptors": {"polar_grids": "x"}}}', "project.receptors.polar_grids must be a JSON list"),
        ('{"project": {"meteorology": 3}}', "project.meteorology must be a JSON object"),
        ('{"save_format_version": "1", "project": {}}', "is not a number"),
    ])
    def test_shape_errors_raise_value_error(self, text, message):
        with pytest.raises(ValueError, match=message):
            project_from_json(text)

    def test_missing_required_field_raises_value_error(self):
        with pytest.raises(ValueError, match=r"^<text>: project.control: .*title_one"):
            project_from_json('{"project": {"control": null}}')

    def test_missing_pathways_fall_back_to_defaults(self):
        project = project_from_json(
            '{"project": {"control": {"title_one": "T"}, "sources": null, '
            '"meteorology": {"surface_file": "a", "profile_file": "b"}}}')
        assert project.control.title_one == "T"
        assert project.sources.sources == []
        assert project.receptors.polar_grids == []
