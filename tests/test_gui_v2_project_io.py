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

    @pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
    def test_a_number_that_is_not_finite_is_refused_by_name(self, saved, token):
        # Python's json reads these non-standard tokens; AERMOD cannot use them.
        text = _with(saved, ("sources", "sources", 0, "x_coord"), 0.0).replace(
            '"x_coord": 0.0', f'"x_coord": {token}', 1)
        shown = {"NaN": "nan", "Infinity": "inf", "-Infinity": "-inf"}[token]
        with pytest.raises(ValueError, match=(
                rf"^f\.json: project\.sources\.sources\[0\]\.x_coord must be a finite "
                rf"number, not {shown}$")):
            project_from_json(text, origin="f.json")

    def test_a_non_finite_number_in_an_untyped_value_is_refused(self, saved):
        doc = json.loads(saved)
        doc["project"]["sources"]["background"] = {
            "_type": "BackgroundConcentration", "period_values": {"ANNUAL": 1.0}}
        text = json.dumps(doc).replace('"ANNUAL": 1.0', '"ANNUAL": NaN')
        with pytest.raises(ValueError, match=(
                r"background\.period_values\['ANNUAL'\] must be a finite number, not nan")):
            project_from_json(text)


class TestSavingRefusesWhatOpeningWould:
    """pyaermod never writes a project file it would refuse to open."""

    @pytest.mark.parametrize("field, value, message", [
        ("emission_rate", None, r"emission_rate must be a number, not null"),
        ("x_coord", float("nan"), r"x_coord must be a finite number, not nan"),
        ("y_coord", float("-inf"), r"y_coord must be a finite number, not -inf"),
        ("source_id", 12, r"source_id must be text, not a number"),
    ])
    def test_a_value_the_loader_refuses_is_not_saved(self, tmp_path, field, value, message):
        project = _full_project()
        setattr(project.sources.sources[0], field, value)
        pattern = rf"^cannot save the project: project\.sources\.sources\[0\]\.{message}"
        with pytest.raises(ValueError, match=pattern):
            project_to_json(project)
        with pytest.raises(ValueError, match=pattern):
            save_project(project, tmp_path / "p.json")
        assert not (tmp_path / "p.json").exists()

    def test_a_value_no_project_file_can_hold_is_a_type_error(self):
        project = _full_project()
        project.sources.sources[0].source_id = object()
        with pytest.raises(TypeError, match="cannot save a object in a project file"):
            project_to_json(project)

    def test_numpy_values_and_paths_are_saved_as_plain_json(self):
        import numpy as np
        project = _full_project()
        stack = project.sources.sources[0]
        stack.x_coord, stack.stack_height = np.float64(100.5), np.int64(30)
        project.sources.sources[2].vertices = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]])
        project.meteorology.surface_file = Path("met") / "x.sfc"
        project.control.elevation_units = project.control.elevation_units  # unchanged
        reopened = project_from_json(project_to_json(project))
        assert reopened.sources.sources[0].x_coord == 100.5
        assert reopened.sources.sources[0].stack_height == 30
        assert reopened.sources.sources[2].vertices == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
        assert reopened.meteorology.surface_file == str(Path("met") / "x.sfc")


class TestEveryRefusalNamesTheField:
    """Each way a document can be malformed gives its own message."""

    @pytest.fixture
    def saved(self):
        return project_to_json(_deposition_project())

    @pytest.mark.parametrize("edit, message", [
        # a tuple of the wrong arity
        (lambda p: p["control"].update(arm2_ratios=[0.5]),
         r"project\.control\.arm2_ratios must have 2 values, not 1"),
        (lambda p: p["control"].update(arm2_ratios="0.5 0.9"),
         r"project\.control\.arm2_ratios must be a JSON list, not text '0\.5 0\.9'"),
        # a dict whose non-text keys are not [key, value] pairs
        (lambda p: p["sources"]["background"].update(sector_values={"_items": [[1, "ANNUAL", 3.0]]}),
         r"project\.sources\.background\.sector_values must list \[key, value\] pairs"),
        (lambda p: p["sources"]["background"].update(sector_values={"_items": "none"}),
         r"project\.sources\.background\.sector_values must list \[key, value\] pairs"),
        # an enum of another class, or text no member has as its value
        (lambda p: p["sources"]["sources"][0].update(
            deposition_method=[{"_enum": "PollutantType.NO2"}, 0.5]),
         r"project\.sources\.sources\[0\]\.deposition_method\[0\] must be a DepositionMethod, "
         r"not a PollutantType"),
        (lambda p: p["sources"]["sources"][0].update(deposition_method=["METHOD9", 0.5]),
         r"project\.sources\.sources\[0\]\.deposition_method\[0\]: unknown DepositionMethod "
         r"value 'METHOD9'"),
        # the class's own check (MaxDailyContribution needs a rank or a threshold)
        (lambda p: p["output"].update(max_daily_contributions=[
            {"_type": "MaxDailyContribution", "source_group": "ALL", "upper_rank": 1,
             "filename": "m.dat"}]),
         r"project\.output\.max_daily_contributions\[0\]: .*lower_rank"),
        # an untyped value naming an enum class or a dataclass the model lacks
        (lambda p: p["sources"]["background"].update(period_values={"A": {"_enum": "Nope.X"}}),
         r"project\.sources\.background\.period_values\['A'\]: unknown enum 'Nope\.X'"),
        (lambda p: p["sources"]["background"].update(period_values={"A": {"_type": "Nope"}}),
         r"project\.sources\.background\.period_values\['A'\]: unknown type 'Nope'"),
        # a field of the wrong kind of JSON value
        (lambda p: p["sources"]["sources"][0].update(particle_deposition=[1, 2]),
         r"project\.sources\.sources\[0\]\.particle_deposition must be a JSON object, "
         r"not a JSON list"),
        (lambda p: p["control"].update(gas_deposition_seasons={"a": 1}),
         r"project\.control\.gas_deposition_seasons must be a JSON list, not a JSON object"),
        (lambda p: p["control"].update(title_one=None),
         r"project\.control\.title_one must be text, not null"),
    ], ids=["tuple-arity", "tuple-not-a-list", "items-pair", "items-not-a-list",
            "enum-class", "enum-value-text", "class-check", "untyped-enum", "untyped-type",
            "object-as-list", "list-as-object", "null-for-text"])
    def test_malformed_values_are_refused(self, saved, edit, message):
        doc = json.loads(saved)
        edit(doc["project"])
        with pytest.raises(ValueError, match=f"^f.json: {message}"):
            project_from_json(json.dumps(doc), origin="f.json")

    def test_untyped_values_keep_their_enums_and_objects(self, saved):
        doc = json.loads(saved)
        doc["project"]["sources"]["background"]["period_values"] = {
            "A": {"_enum": "PollutantType.NO2"},
            "B": {"_type": "BackgroundSector", "sector_id": 1, "start_direction": 0.0},
        }
        values = project_from_json(json.dumps(doc)).sources.background.period_values
        assert values == {"A": PollutantType.NO2, "B": BackgroundSector(1, 0.0)}

    def test_nesting_the_decoder_cannot_follow_is_refused(self, saved):
        # json.loads reads this; rebuilding it would overflow the stack.
        doc = json.loads(saved)
        nested: dict = {}
        for _ in range(600):
            nested = {"n": nested}
        doc["project"]["sources"]["background"]["period_values"] = nested
        with pytest.raises(ValueError, match=r"^f\.json: nested too deeply to be a project file$"):
            project_from_json(json.dumps(doc), origin="f.json")


class TestTheDecoderChecksEachKindOfType:
    """``_Decoder.value`` for annotation kinds the model uses rarely or not yet."""

    @staticmethod
    def _value(value, annotation):
        from pyaermod.gui_v2.project_io import _Decoder
        return _Decoder("f.json").value(value, annotation, "x")

    @pytest.mark.parametrize("value, annotation, expected", [
        (None, type(None), None),
        ("a", "typing.Literal", "a"),
        ("dir/f.sfc", Path, Path("dir/f.sfc")),
        ([1, 2, 3], "Tuple[int, ...]", (1, 2, 3)),
        ([1, "a"], tuple, (1, "a")),
        ({"1": 2.0, "3": 4.0}, "Dict[int, float]", {1: 2.0, 3: 4.0}),
        ({"_items": [[[1, "A"], 2.0]]}, dict, {(1, "A"): 2.0}),
        ([1, {"k": [2]}], list, [1, {"k": [2]}]),
        (3, object, 3),
        ({"k": 1}, "frozenset", {"k": 1}),
    ])
    def test_values_that_fit_are_kept(self, value, annotation, expected):
        import typing
        annotation = {"typing.Literal": typing.Literal["a", "b"],
                      "Tuple[int, ...]": typing.Tuple[int, ...],
                      "Dict[int, float]": typing.Dict[int, float],
                      "frozenset": frozenset}.get(annotation, annotation)
        assert self._value(value, annotation) == expected

    @pytest.mark.parametrize("value, annotation, message", [
        (1, type(None), "x must be null, not a number"),
        ("c", "typing.Literal", r"x must be one of \['a', 'b'\], not 'c'"),
        (1, bool, "x must be true/false, not a number"),
        (1, Path, "x must be text, not a number"),
        (1, "Path|None", "x must be text, not a number"),      # Optional: the inner check
        ({"x": 1}, list, "x must be a JSON list, not a JSON object"),
        ([1], dict, "x must be a JSON object, not a JSON list"),
        ({"a": 1}, "Dict[int, float]", r"x has key 'a', not a whole number"),
        ({"_items": [[True, 2.0]]}, "Dict[int, float]", r"x key must be a number, not true/false"),
        (None, PollutantType, "x must be a PollutantType, not null"),
        ({"_enum": "PollutantType.NO2"}, "Union[int, str]",
         r"x must be a number or text, not a JSON object"),
        ([1], "Point|Area", r"x must be a JSON object, not a JSON list"),
        ({"source_id": "S"}, "Point|Area", r"x has no _type saying which kind"),
        (None, "Point|Area", r"x must be a JSON object or a JSON object, not null"),
    ])
    def test_values_that_do_not_fit_are_refused(self, value, annotation, message):
        import typing
        annotation = {"typing.Literal": typing.Literal["a", "b"],
                      "Path|None": typing.Optional[Path],
                      "Dict[int, float]": typing.Dict[int, float],
                      "Union[int, str]": typing.Union[int, str],
                      "Point|Area": typing.Union[PointSource, AreaPolySource]}.get(annotation, annotation)
        with pytest.raises(ValueError, match=f"^f.json: {message}"):
            self._value(value, annotation)

    def test_json_kind_names_a_value_json_cannot_hold(self):
        from pyaermod.gui_v2.project_io import _json_kind
        assert _json_kind(object()) == "object"
