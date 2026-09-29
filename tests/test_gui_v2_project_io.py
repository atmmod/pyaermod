"""Tests for the GUI v2 project save/load round-trip."""

from __future__ import annotations

import json
from pathlib import Path

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
from pyaermod.input_generator import (
    BackgroundConcentration,
    BackgroundSector,
    EmissionUnits,
    GasDepositionParams,
    OpenPitSource,
    ParticleDepositionParams,
    SourceGroupDefinition,
)


def _with(text: str, path: tuple, value) -> str:
    """``text`` (a saved project) with the value at ``project.<path>`` replaced."""
    doc = json.loads(text)
    node = doc["project"]
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return json.dumps(doc)


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
        ('{"save_format_version": "1", "project": {}}', "is not a number"),
        ('{"save_format_version": true, "project": {}}', "is not a number"),
    ])
    def test_shape_errors_raise_value_error(self, text, message):
        with pytest.raises(ValueError, match=message):
            project_from_json(text)

    @pytest.mark.parametrize("path, value, message", [
        (("sources", "sources"), {}, r"project\.sources\.sources must be a JSON list"),
        (("sources", "sources"), [1], r"project\.sources\.sources\[0\] must be a JSON object"),
        (("receptors", "polar_grids"), "x", r"project\.receptors\.polar_grids must be a JSON list"),
        (("meteorology",), 3, r"project\.meteorology must be a JSON object"),
    ])
    def test_misshapen_pathways_raise_value_error(self, path, value, message):
        with pytest.raises(ValueError, match=f"^<text>: {message}"):
            project_from_json(_with(project_to_json(_full_project()), path, value))

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


# ---------------------------------------------------------------------
# Everything the model holds survives a save and an open
# ---------------------------------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures"
_DECKS = sorted(
    [*(_FIXTURES / "epa_official").glob("*.inp"), *(_FIXTURES / "epa_style").glob("*.inp"),
     _FIXTURES / "gui" / "aermod_recordings" / "aertest" / "aertest.inp"],
    key=lambda p: p.name,
)


def _deposition_project():
    """The demonstration study's shape: an open pit with size-resolved dry deposition."""
    return AERMODProject(
        control=ControlPathway(
            title_one="REE mine fugitive dust", pollutant_id="TSP",
            averaging_periods=["24", "PERIOD"],
        ),
        sources=SourcePathway(
            sources=[
                OpenPitSource(
                    source_id="PIT1", x_coord=0.0, y_coord=0.0, emission_rate=1.5e-6,
                    release_height=5.0, x_dimension=400.0, y_dimension=250.0,
                    pit_volume=4.0e6, angle=15.0,
                    particle_deposition=ParticleDepositionParams(
                        diameters=[1.0, 2.5, 6.0, 10.0, 20.0, 40.0],
                        mass_fractions=[0.05, 0.1, 0.2, 0.25, 0.25, 0.15],
                        densities=[2.6] * 6,
                    ),
                ),
                PointSource(
                    source_id="STK1", x_coord=500.0, y_coord=0.0, stack_height=20.0,
                    stack_temp=400.0, exit_velocity=10.0, stack_diameter=1.0,
                    emission_rate=1.0,
                    gas_deposition=GasDepositionParams(0.1, 1e-5, 2.5e4, 557.0),
                ),
            ],
            background=BackgroundConcentration(
                sectors=[BackgroundSector(1, 0.0), BackgroundSector(2, 180.0)],
                sector_values={(1, "ANNUAL"): 12.0, (2, "ANNUAL"): 8.5},
            ),
            group_definitions=[SourceGroupDefinition("PIT", ["PIT1"])],
            emission_units=EmissionUnits(1.0e6, "GRAMS/SEC", "MICROGRAMS/M**3"),
        ),
        receptors=ReceptorPathway(cartesian_grids=[CartesianGrid()]),
        meteorology=MeteorologyPathway(surface_file="x.sfc", profile_file="x.pfl"),
        output=OutputPathway(),
    )


class TestEverythingRoundTrips:
    """A file pyaermod wrote reads back as the same model and the same deck."""

    @pytest.mark.parametrize("deck", _DECKS, ids=lambda p: p.name)
    def test_every_fixture_deck_survives_save_and_open(self, deck):
        from pyaermod.input_reader import read_aermod_input

        project = read_aermod_input(deck)
        reopened = project_from_json(project_to_json(project))
        assert reopened == project
        assert reopened.to_aermod_input(validate=False) == project.to_aermod_input(validate=False)

    def test_deposition_background_and_groups_survive(self):
        project = _deposition_project()
        reopened = project_from_json(project_to_json(project))
        pit = reopened.sources.sources[0]
        assert isinstance(pit.particle_deposition, ParticleDepositionParams)
        assert pit.particle_deposition.diameters == [1.0, 2.5, 6.0, 10.0, 20.0, 40.0]
        assert pit.emission_rate == 1.5e-6
        assert reopened.control.pollutant_id == "TSP"
        assert reopened.sources.background.sector_values == {(1, "ANNUAL"): 12.0,
                                                             (2, "ANNUAL"): 8.5}
        assert reopened.sources.emission_units == project.sources.emission_units
        assert reopened == project
        assert reopened.to_aermod_input(validate=False) == project.to_aermod_input(validate=False)

    def test_files_without_nested_type_tags_still_load(self):
        # Before the tags covered nested objects, only list elements had them.
        doc = json.loads(project_to_json(_deposition_project()))

        def untag(node, keep):
            if isinstance(node, dict):
                if not keep:
                    node.pop("_type", None)
                for key, value in node.items():
                    untag(value, keep=key == "sources" and isinstance(value, list))
            elif isinstance(node, list):
                for item in node:
                    untag(item, keep)

        untag(doc["project"], keep=False)
        reopened = project_from_json(json.dumps(doc))
        assert reopened == _deposition_project()


class TestValuesAreChecked:
    """A file that loads is one the GUI and the deck writer can use."""

    @pytest.fixture
    def saved(self):
        return project_to_json(_full_project())

    @pytest.mark.parametrize("path, value, message", [
        (("control", "pollutant_id"), {"_enum": "PollutantType.NOPE"},
         r"project\.control\.pollutant_id: unknown PollutantType member 'NOPE'"),
        (("control", "pollutant_id"), {"_enum": 5},
         r"project\.control\.pollutant_id: 5 is not an enum tag"),
        (("control", "pollutant_id"), {"_enum": "PollutantType"},
         r"project\.control\.pollutant_id: 'PollutantType' is not an enum tag"),
        (("control", "pollutant_id"), 7,
         r"project\.control\.pollutant_id must be text or a PollutantType, not a number"),
        (("control", "title_one"), 3, r"project\.control\.title_one must be text, not a number"),
        (("meteorology", "profile_base_elevation"), "abc",
         r"project\.meteorology\.profile_base_elevation must be a number, not text 'abc'"),
        (("sources", "sources", 2, "vertices"), [[0]],
         r"project\.sources\.sources\[2\]\.vertices\[0\] must have 2 values, not 1"),
        (("sources", "sources", 0, "stack_height"), True,
         r"project\.sources\.sources\[0\]\.stack_height must be a number, not true/false"),
        (("sources", "sources", 0, "_type"), "PointSorce",
         r"project\.sources\.sources\[0\]: unknown type 'PointSorce'"),
        (("receptors", "polar_grids", 0, "_type"), "CartesianGrid",
         r"project\.receptors\.polar_grids\[0\]: unknown type 'CartesianGrid' \(expected PolarGrid\)"),
        (("sources", "sources", 0), {"source_id": "S"},
         r"project\.sources\.sources\[0\] has no _type"),
        (("sources", "sources", 0, "source_id"), None,
         r"project\.sources\.sources\[0\]\.source_id must be text, not null"),
    ])
    def test_a_wrong_value_refuses_the_file(self, saved, path, value, message):
        with pytest.raises(ValueError, match=f"^f.json: {message}"):
            project_from_json(_with(saved, path, value), origin="f.json")

    def test_a_missing_required_field_is_named(self, saved):
        doc = json.loads(saved)
        del doc["project"]["sources"]["sources"][0]["x_coord"]
        with pytest.raises(ValueError, match=r"sources\[0\]: missing required field 'x_coord'"):
            project_from_json(json.dumps(doc))

    def test_a_pollutant_outside_the_enum_is_kept_as_text(self, saved):
        project = project_from_json(_with(saved, ("control", "pollutant_id"), "TSP"))
        assert project.control.pollutant_id == "TSP"

    def test_bytes_that_are_not_utf8_name_the_file(self):
        with pytest.raises(ValueError, match=r"^binary\.json: not a UTF-8 text file"):
            project_from_json(b"\xff\xfe\x00{", origin="binary.json")

    def test_a_deeply_nested_document_is_refused(self):
        deep = '{"project": ' + "[" * 100_000 + "]" * 100_000 + "}"
        with pytest.raises(ValueError, match=r"^<text>: nested too deeply"):
            project_from_json(deep)
