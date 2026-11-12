"""pyaermod.browser: the browser GUI's JSON API, under CPython.

The same module runs in Pyodide inside the browser GUI's Web Worker; the
WebAssembly half is covered by .github/workflows/wasm_aermod.yml
(scripts/wasm/pyodide_smoke.mjs). Runs here replay recorded AERMOD runs
through tests/e2e/fake_aermod.py, as the GUI journeys do.
"""

from __future__ import annotations

import base64
import builtins
import importlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from pyaermod import browser
from pyaermod.gui_v2.project_io import project_from_json, project_to_json
from pyaermod.gui_v2.readiness import review
from pyaermod.gui_v2.session import Session
from pyaermod.input_generator import CartesianGrid, DiscreteReceptor, PointSource

FIXTURES = Path(__file__).parent / "fixtures"
RECORDINGS = FIXTURES / "gui" / "aermod_recordings"
FAKE_AERMOD = Path(__file__).parent / "e2e" / "fake_aermod.py"
MET = FIXTURES / "epa_official"
AERMAP = FIXTURES / "aermap_runner" / "networks"


def call(operation, **kwargs):
    return json.loads(browser.call(operation, json.dumps(kwargs)))


def ok(operation, **kwargs):
    reply = call(operation, **kwargs)
    assert reply["ok"], reply.get("error")
    return reply


@pytest.fixture(autouse=True)
def work(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(browser, "RUNNER_FACTORY", None)
    return tmp_path / "work"


def put(path: Path, name=None):
    return ok("put_file", name=name or path.name,
              data_b64=base64.b64encode(path.read_bytes()).decode())


@pytest.fixture
def replay(tmp_path, monkeypatch):
    """Make AERMOD a replay of ``recording`` (tests/e2e/fake_aermod.py)."""
    from pyaermod.runner import AERMODRunner

    exe = tmp_path / "bin" / "aermod"
    exe.parent.mkdir()
    exe.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE_AERMOD} \"$@\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)

    def use(recording: str):
        monkeypatch.setenv("PYAERMOD_E2E_RECORDING", recording)
        monkeypatch.setattr(browser, "RUNNER_FACTORY",
                            lambda: AERMODRunner(executable_path=str(exe), log_level="WARNING"))
    return use


# ----------------------------------------------------------------------
# The module itself
# ----------------------------------------------------------------------

def test_it_imports_without_nicegui_or_a_window(monkeypatch):
    """The worker has no NiceGUI, pywebview or server: importing must not need them."""
    real = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"nicegui", "webview", "fastapi", "uvicorn"}:
            raise ImportError(f"{name} is not in the browser")
        return real(name, *args, **kwargs)

    for name in [m for m in sys.modules if m.startswith("pyaermod")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(builtins, "__import__", guarded)
    module = importlib.import_module("pyaermod.browser")
    assert json.loads(module.call("schema"))["ok"]


def test_an_unknown_operation_or_a_bug_is_a_reply_not_an_exception():
    reply = call("no_such_thing")
    assert reply == {"ok": False, "error": {"kind": "internal", "step": None,
                                            "message": "unknown operation 'no_such_thing'"}}
    assert not call("load", text="not json")["ok"]
    assert call("load", wrong_argument=1)["error"]["kind"] == "internal"


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------

def test_the_schema_covers_every_source_and_receptor_type_the_pip_gui_offers():
    from pyaermod.gui_v2.pages.receptors import _RECEPTOR_TYPES
    from pyaermod.gui_v2.pages.sources import _SOURCE_TYPES

    s = ok("schema")
    assert s["sources"] == list(_SOURCE_TYPES) and s["receptors"] == list(_RECEPTOR_TYPES)
    for name in (*_SOURCE_TYPES, *_RECEPTOR_TYPES, "ControlPathway", "MeteorologyPathway",
                 "OutputPathway"):
        fields = s["classes"][name]["fields"]
        assert fields and all(f["kind"] for f in fields), name
    assert s["banner"] == browser.BANNER and "not for regulatory use" in s["banner"]


def test_the_schema_offers_choices_and_units():
    s = ok("schema")
    control = {f["name"]: f for f in s["classes"]["ControlPathway"]["fields"]}
    assert control["pollutant_id"]["kind"] == "enum" and control["pollutant_id"]["custom"]
    assert {"value": {"_enum": "PollutantType.PM25"}, "label": "PM25"} in \
        control["pollutant_id"]["choices"]
    assert control["averaging_periods"]["kind"] == "multichoice"
    assert "ANNUAL" in control["averaging_periods"]["choices"]
    point = {f["name"]: f for f in s["classes"]["PointSource"]["fields"]}
    assert point["stack_height"]["kind"] == "number" and point["stack_height"]["units"] == "m"
    assert point["building_height"]["kind"] == "numbers"
    poly = {f["name"]: f for f in s["classes"]["AreaPolySource"]["fields"]}
    assert poly["vertices"]["kind"] == "points"
    # Every field a step group names exists on its class.
    for step, cls in (("meteorology", "MeteorologyPathway"), ("output", "OutputPathway"),
                      ("project", "ControlPathway")):
        names = {f["name"] for f in s["classes"][cls]["fields"]}
        for group in s["groups"][step]:
            assert set(group["fields"]) <= names, (step, group)


# ----------------------------------------------------------------------
# Projects: the pip GUI's file format, both ways
# ----------------------------------------------------------------------

def _albany_project():
    project = project_from_json(json.dumps(ok("new_project")["document"]))
    project.sources.sources.append(PointSource("STACK1", 0.0, 0.0, stack_height=50.0, stack_diameter=2.0,
                                                exit_velocity=15.0, stack_temp=400.0))
    project.receptors.discrete_receptors.append(DiscreteReceptor(500.0, 0.0))
    project.meteorology.surface_file = "AERMET2.SFC"
    project.meteorology.profile_file = "AERMET2.PFL"
    project.meteorology.surface_station_id = 14735
    project.meteorology.upper_air_station_id = 14735
    project.meteorology.data_start_year = 1988
    project.control.averaging_periods = ["1", "24"]
    return project


def test_a_pip_gui_project_file_opens_unchanged_and_saves_back_the_same():
    text = project_to_json(_albany_project())          # what pyaermod-app saves
    document = ok("load", text=text)["document"]
    assert document == json.loads(text)
    # And what the browser saves opens in pyaermod-app.
    assert project_to_json(project_from_json(json.dumps(document))) == text


def test_a_bad_project_names_the_field_and_its_step():
    document = json.loads(project_to_json(_albany_project()))
    document["project"]["sources"]["sources"][0]["stack_height"] = "tall"
    error = call("load", text=json.dumps(document))["error"]
    assert error["kind"] == "project" and error["step"] == "sources"
    assert "stack_height" in error["message"]


def test_new_items_carry_their_type_and_the_pip_gui_defaults():
    item = ok("new_item", type_name="PointSource")["item"]
    assert item["_type"] == "PointSource" and item["stack_height"] == 10.0
    assert ok("new_item", type_name="CartesianGrid")["item"]["_type"] == "CartesianGrid"
    assert call("new_item", type_name="Nope")["error"]["kind"] == "invalid"


# ----------------------------------------------------------------------
# Review: the same checklist as the pip GUI
# ----------------------------------------------------------------------

def test_the_checklist_is_the_pip_guis(replay, work):
    replay("albany_success")
    put(MET / "AERMET2.SFC")
    project = _albany_project()
    project.meteorology.profile_file = ""                  # one problem left
    document = json.loads(project_to_json(project))
    found = ok("check", document=document)
    session = Session(project_from_json(json.dumps(document)))
    session.run_options.working_dir = str(work)
    expected = review(session, have_binary=True)
    # The pip GUI's items, and on Meteorology one more: the profile file
    # named nowhere is caught by both; nothing else differs.
    assert [(i["step"], i["problems"]) for i in found["blocking"]] == \
        [(i.step, i.problems) for i in expected.blocking]
    assert not found["ready"] and found["blocking"][0]["step"] == "meteorology"


def test_a_met_file_nobody_uploaded_blocks_the_run(replay):
    replay("albany_success")
    put(MET / "AERMET2.SFC")
    found = ok("check", document=json.loads(project_to_json(_albany_project())))
    (item,) = found["blocking"]
    assert item["step"] == "meteorology"
    assert item["problems"] == ["AERMET2.PFL (ME PROFFILE) has not been uploaded: add it on "
                                "the Meteorology step's file list, or pick a sample"]


def test_without_aermod_the_checklist_says_the_build_did_not_load(work):
    document = json.loads(project_to_json(_albany_project()))
    found = ok("check", document=document)
    run_items = [i for i in found["blocking"] if i["step"] == "run"]
    assert run_items and "WebAssembly build did not load" in run_items[0]["problems"][0]


def test_deck_and_plan_view():
    document = json.loads(project_to_json(_albany_project()))
    assert "SRCPARAM  STACK1" in ok("deck", document=document)["deck"]
    assert ok("plan_view", document=document)["svg"].startswith("<svg")


# ----------------------------------------------------------------------
# Files and decks
# ----------------------------------------------------------------------

@pytest.mark.parametrize("name", ["../escape.txt", "/etc/escape.txt", "a\\..\\escape.txt"])
def test_uploads_land_in_the_working_directory_only(work, name):
    reply = ok("put_file", name=name, data_b64=base64.b64encode(b"x").decode())
    assert reply["name"] == "escape.txt"
    assert (work / "escape.txt").read_bytes() == b"x"
    assert not (work.parent / "escape.txt").exists()


def test_a_name_that_is_no_file_is_refused():
    assert call("put_file", name="..", data_b64="")["error"]["kind"] == "file"


def test_an_imported_deck_says_which_files_it_still_needs(work):
    text = (RECORDINGS / "albany_success" / "aermod.inp").read_text()
    reply = ok("import_deck", name="albany.inp", text=text)
    assert reply["missing_files"] == ["AERMET2.PFL", "AERMET2.SFC"]
    put(MET / "AERMET2.SFC")
    put(MET / "AERMET2.PFL")
    assert ok("import_deck", name="albany.inp", text=text)["missing_files"] == []


def test_input_files_in_other_folders_are_looked_for_by_name():
    """EPA's decks name ../meteorology/...; uploads are flat, so the name is what counts."""
    text = (RECORDINGS / "albany_success" / "aermod.inp").read_text().replace(
        "SURFFILE  AERMET2.SFC", 'SURFFILE  "../../etc/AERMET2.SFC"')
    reply = ok("import_deck", name="epa.inp", text=text)
    met = reply["document"]["project"]["meteorology"]
    assert met["surface_file"] == "AERMET2.SFC"
    assert reply["renamed"] == [{"keyword": "ME SURFFILE", "from": "../../etc/AERMET2.SFC",
                                 "to": "AERMET2.SFC"}]


@pytest.mark.parametrize("card", ['SUMMFILE  "../../tmp/evil.sum"', "SUMMFILE  /tmp/evil.sum"])
def test_a_deck_that_writes_outside_is_refused(card):
    text = (RECORDINGS / "albany_success" / "aermod.inp").read_text().replace(
        "OU STARTING", f"OU STARTING\n   {card}")
    error = call("import_deck", name="evil.inp", text=text)["error"]
    assert error["kind"] == "deck" and error["step"] == "project"
    assert "outside" in error["message"]


# ----------------------------------------------------------------------
# Terrain
# ----------------------------------------------------------------------

def _networks_project():
    from pyaermod.pathways import TerrainType

    project = _albany_project()
    project.control.terrain_type = TerrainType.ELEVATED
    project.receptors.discrete_receptors = [DiscreteReceptor(500100.0, 4000100.0)]
    project.receptors.cartesian_grids.append(CartesianGrid(
        grid_name="G1", x_init=500100.0, x_num=3, x_delta=100.0,
        y_init=4000200.0, y_num=2, y_delta=100.0))
    return project


def test_aermap_receptor_output_sets_grid_and_discrete_elevations():
    put(AERMAP / "aermap_receptors.out")
    document = json.loads(project_to_json(_networks_project()))
    reply = ok("apply_terrain", document=document, name="aermap_receptors.out")
    assert reply["kind"] == "receptors" and reply["notes"] == []
    receptors = reply["document"]["project"]["receptors"]
    grid = receptors["cartesian_grids"][0]
    assert grid["grid_elevations"] == [[108.0, 110.0, 112.0], [111.0, 113.0, 115.0]]
    assert receptors["discrete_receptors"][0]["z_elev"] == 105.0


def test_a_csv_of_elevations_sets_matching_receptors(work):
    (work).mkdir(parents=True, exist_ok=True)
    csv_text = "x,y,elevation,hill\n500100,4000100,42.5,60\n"
    ok("put_file", name="terrain.csv", data_b64=base64.b64encode(csv_text.encode()).decode())
    document = json.loads(project_to_json(_networks_project()))
    reply = ok("apply_terrain", document=document, name="terrain.csv")
    rec = reply["document"]["project"]["receptors"]["discrete_receptors"][0]
    assert reply["kind"] == "csv" and (rec["z_elev"], rec["z_hill"]) == (42.5, 60.0)


def test_terrain_that_matches_nothing_or_flat_terrain_is_explained():
    from pyaermod.pathways import TerrainType

    put(AERMAP / "aermap_receptors.out")
    project = _albany_project()                                 # other coordinates
    project.control.terrain_type = TerrainType.FLAT
    document = json.loads(project_to_json(project))
    notes = ok("apply_terrain", document=document, name="aermap_receptors.out")["notes"]
    assert any("matched" in n for n in notes)
    assert any("terrain is Flat" in n for n in notes)


def test_aermap_source_output_sets_base_elevations():
    put(AERMAP / "aermap_sources.out")
    project = _networks_project()
    project.sources.sources = [PointSource("STK", 500200.0, 4000300.0, stack_diameter=1.0)]
    reply = ok("apply_terrain", document=json.loads(project_to_json(project)),
               name="aermap_sources.out")
    assert reply["kind"] == "sources"
    assert reply["document"]["project"]["sources"]["sources"][0]["base_elevation"] == 113.0


@pytest.mark.parametrize("text,expected", [
    (b"x,y,z\n1,2\n", "line 2"),                   # too few values
    (b"x,y,z\n1,2,3\n4,y,5\n", "line 3"),          # not a number
    (b"x,y,z\n# nothing\n", "holds no elevations"),
    (b"\x00\xff\x00garbage", "could not be read"),
])
def test_a_bad_terrain_file_says_what_is_wrong(text, expected):
    name = "bad.csv" if expected != "could not be read" else "bad.out"
    ok("put_file", name=name, data_b64=base64.b64encode(text).decode())
    document = json.loads(project_to_json(_networks_project()))
    error = call("apply_terrain", document=document, name=name)["error"]
    assert error["kind"] == "terrain" and expected in error["message"], error


def test_terrain_that_was_not_uploaded_is_refused():
    document = json.loads(project_to_json(_networks_project()))
    error = call("apply_terrain", document=document, name="nothing.csv")["error"]
    assert error["step"] == "receptors" and "not been uploaded" in error["message"]


# ----------------------------------------------------------------------
# Running AERMOD (a replay of the real binary)
# ----------------------------------------------------------------------

@pytest.mark.skipif(os.name == "nt", reason="the replay wrapper is a shell script")
def test_a_run_returns_aermods_maxima(replay):
    replay("albany_success")
    put(MET / "AERMET2.SFC")
    put(MET / "AERMET2.PFL")
    text = (RECORDINGS / "albany_success" / "aermod.inp").read_text()
    document = ok("import_deck", name="albany.inp", text=text)["document"]

    reply = ok("run", document=document)

    assert reply["status"] == "Succeeded", reply["status_text"]
    results = reply["results"]
    assert results["succeeded"] and results["files"]
    expected = json.loads((RECORDINGS / "albany_success" / "manifest.json").read_text())["maxima"]
    by_period = {m["period"]: m for m in results["maxima"]}
    assert len(by_period) == len(expected)
    for key, want in expected.items():
        got = next(m for p, m in by_period.items() if p.replace("-", "").replace(" ", "")
                   .upper().startswith(key.replace("HR", "").replace("PERIOD", "PERIOD"))
                   or key in p.upper().replace("-", "").replace(" ", ""))
        assert float(got["value"]) == pytest.approx(want["value"])
        assert (got["x"], got["y"]) == (want["x"], want["y"])
    assert results["maps"] and results["maps"][0]["src"].startswith("data:image/png;base64,")
    assert results["tables"] and len(results["tables"][0]["rows"]) <= browser.MAX_TABLE_ROWS
    out = next(f["name"] for f in results["files"] if f["name"].endswith(".out"))
    assert b"AERMOD Finishes Successfully" in base64.b64decode(
        ok("get_file", name=out)["data_b64"])


@pytest.mark.skipif(os.name == "nt", reason="the replay wrapper is a shell script")
def test_a_deck_named_aermod_inp_imports_and_runs(replay, work):
    """aermod.inp is the name AERMOD reads; an imported deck must not be left under it."""
    replay("albany_success")
    put(MET / "AERMET2.SFC")
    put(MET / "AERMET2.PFL")
    text = (RECORDINGS / "albany_success" / "aermod.inp").read_text()
    document = ok("import_deck", name="aermod.inp", text=text)["document"]
    assert not (work / "aermod.inp").exists()
    assert ok("run", document=document)["status"] == "Succeeded"


@pytest.mark.skipif(os.name == "nt", reason="the replay wrapper is a shell script")
def test_a_failed_run_shows_aermods_errors_and_no_values(replay):
    replay("albany_e480")
    put(MET / "AERMET2.SFC")
    put(MET / "AERMET2.PFL")
    text = (RECORDINGS / "albany_e480" / "aermod.inp").read_text()
    document = ok("import_deck", name="albany.inp", text=text)["document"]
    reply = ok("run", document=document)
    assert reply["status"] == "Failed"
    assert not reply["results"]["succeeded"] and reply["results"]["maxima"] == []
    assert any(m["code"] == "E480" for m in reply["messages"])


def test_a_project_that_is_not_ready_is_not_run(replay):
    replay("albany_success")
    document = json.loads(project_to_json(_albany_project()))     # no met files uploaded
    error = call("run", document=document)["error"]
    assert error["kind"] == "not_ready" and error["step"] == "meteorology"


# ----------------------------------------------------------------------
# Files, errors and where AERMOD is looked for
# ----------------------------------------------------------------------

def test_files_are_listed_fetched_and_removed():
    put(MET / "AERMET2.SFC")
    assert ok("list_files")["files"] == [{"name": "AERMET2.SFC",
                                          "size": (MET / "AERMET2.SFC").stat().st_size}]
    data = base64.b64decode(ok("get_file", name="AERMET2.SFC")["data_b64"])
    assert data == (MET / "AERMET2.SFC").read_bytes()
    assert ok("remove_file", name="AERMET2.SFC")["files"] == []
    assert call("get_file", name="AERMET2.SFC")["error"]["kind"] == "file"


def test_the_working_directory_is_made_when_first_needed(monkeypatch):
    monkeypatch.setattr(browser, "WORK_DIR", None)
    first = browser.work_dir()
    assert first.is_dir() and browser.work_dir() == first


def test_a_deck_that_cannot_be_read_or_written_says_so():
    error = call("import_deck", name="x.inp", text="not a deck")["error"]
    assert error["kind"] == "deck" and "could not be read" in error["message"]


def test_a_project_the_writer_refuses_is_a_deck_error(monkeypatch):
    from pyaermod.gui_v2.session import DeckError, Session

    def refuse(self):
        raise DeckError("project.sources[0]: cannot be written")

    monkeypatch.setattr(Session, "deck_text", refuse)
    error = call("deck", document=json.loads(project_to_json(_albany_project())))["error"]
    assert error == {"kind": "deck", "message": "project.sources[0]: cannot be written",
                     "step": None}


def test_a_problem_the_pip_gui_and_the_upload_check_both_find_is_one_item():
    project = _albany_project()
    project.meteorology.profile_file = ""                      # the pip GUI's item
    found = ok("check", document=json.loads(project_to_json(project)))
    (met,) = [i for i in found["blocking"] if i["step"] == "meteorology"]
    assert "profile file must not be empty" in met["problems"]
    assert any("AERMET2.SFC (ME SURFFILE) has not been uploaded" in p for p in met["problems"])


def test_arguments_must_be_an_object_and_a_bug_is_reported(monkeypatch):
    assert json.loads(browser.call("schema", "[1]"))["error"]["kind"] == "internal"

    def broken():
        raise RuntimeError("boom")

    monkeypatch.setitem(browser._OPERATIONS, "schema", broken)
    error = json.loads(browser.call("schema"))["error"]
    assert error["message"] == "RuntimeError: boom" and "Traceback" in error["traceback"]


def test_under_pyodide_aermod_is_the_webassembly_build(monkeypatch):
    from pyaermod import wasm_runner

    monkeypatch.setattr(wasm_runner, "IS_EMSCRIPTEN", True)
    monkeypatch.setattr(wasm_runner, "find_wasm_aermod", lambda: Path("/x/aermod.js"))
    assert browser._have_aermod()

    def missing():
        raise wasm_runner.WasmAERMODNotFound("none")

    monkeypatch.setattr(wasm_runner, "find_wasm_aermod", missing)
    assert not browser._have_aermod()


# ----------------------------------------------------------------------
# Review fixes (independent review of the browser GUI)
# ----------------------------------------------------------------------

def test_an_output_outside_the_working_directory_blocks_the_run():
    project = _albany_project()
    project.output.summary_file = "/tmp/elsewhere/evil.sum"
    found = ok("check", document=json.loads(project_to_json(project)))
    assert not found["ready"]
    (item,) = [i for i in found["blocking"] if i["step"] == "output"]
    assert any("outside" in p and "evil.sum" in p for p in item["problems"])


def test_a_met_file_name_with_a_blank_is_quoted_in_the_deck(replay):
    replay("albany_success")
    ok("put_file", name="My Met.SFC", data_b64=base64.b64encode(b"x").decode())
    project = _albany_project()
    project.meteorology.surface_file = "My Met.SFC"
    found = ok("check", document=json.loads(project_to_json(project)))
    assert 'SURFFILE  "My Met.SFC"' in found["deck"]
    assert not any("My Met.SFC" in p for i in found["blocking"] for p in i["problems"])


def test_an_output_name_with_a_blank_is_quoted_in_the_deck():
    project = _albany_project()
    project.output.summary_file = "my sum.sum"
    found = ok("check", document=json.loads(project_to_json(project)))
    assert 'SUMMFILE  "my sum.sum"' in found["deck"]
    assert 'SUMMFILE  "my sum.sum"' in ok("deck", document=json.loads(
        project_to_json(project)))["deck"]


@pytest.mark.parametrize("name", ["met/", ".."])
def test_a_met_path_that_is_no_file_name_is_one_item_not_an_error(name):
    project = _albany_project()
    project.meteorology.surface_file = name
    found = ok("check", document=json.loads(project_to_json(project)))
    problems = [p for i in found["blocking"] if i["step"] == "meteorology" for p in i["problems"]]
    assert any(name in p for p in problems)
    assert any(i["step"] == "run" or i["step"] == "meteorology" for i in found["blocking"])
