"""Journeys of the browser GUI (webapp/) in a real browser.

The page talks to pyaermod.browser through scripts/wasm/app_dev_server.py
(CPython, rpc.js's HttpBackend), and AERMOD is a replay of a recording
(tests/e2e/fake_aermod.py). The same page with Pyodide and AERMOD's
WebAssembly build is checked by .github/workflows/wasm_aermod.yml.
"""

from __future__ import annotations

import importlib.util
import json
import re
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

REPO = Path(__file__).resolve().parents[2]
RECORDINGS = REPO / "tests" / "fixtures" / "gui" / "aermod_recordings"
MET = REPO / "tests" / "fixtures" / "epa_official"
AERMAP = REPO / "tests" / "fixtures" / "aermap_runner" / "networks"


def _dev_server():
    spec = importlib.util.spec_from_file_location(
        "app_dev_server", REPO / "scripts" / "wasm" / "app_dev_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def app(browser, tmp_path, monkeypatch):
    """The page, served fresh, with AERMOD replaying albany_success."""
    from pyaermod import browser as api

    monkeypatch.setattr(api, "WORK_DIR", None)
    monkeypatch.setattr(api, "RUNNER_FACTORY", None)
    monkeypatch.setenv("PYAERMOD_E2E_RECORDING", "albany_success")
    server = _dev_server().serve(0, replay="albany_success", work_dir=tmp_path / "work")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    context = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(f"http://127.0.0.1:{server.server_port}/")
    page.wait_for_selector("#app:not([hidden])", timeout=20000)
    yield page
    context.close()
    server.shutdown()
    assert errors == [], errors


def step(page, name):
    page.locator("#steps").get_by_role("button", name=re.compile(name)).click()
    page.wait_for_selector(f"main h1:has-text('{name}')")


def saved_document(page):
    step(page, "Project")
    with page.expect_download() as download:
        page.get_by_role("button", name="Save", exact=True).click()
    return json.loads(Path(download.value.path()).read_text())


def test_b01_import_a_deck_run_it_and_read_aermods_maxima(app):
    with app.expect_file_chooser() as chooser:
        app.get_by_role("button", name="Import deck...").click()
    chooser.value.set_files([RECORDINGS / "albany_success" / "aermod.inp",
                             MET / "AERMET2.SFC", MET / "AERMET2.PFL"])
    app.wait_for_selector("text=Imported aermod.inp")
    step(app, "Review & Run")
    app.get_by_role("button", name="Run AERMOD").click()
    app.wait_for_selector("main h1:has-text('Results')", timeout=30000)

    rows = app.locator("table[aria-label='Maximum for each averaging period'] tbody tr")
    got = {r.split("\t")[0]: r.split("\t") for r in rows.all_inner_texts()}
    expected = json.loads((RECORDINGS / "albany_success" / "manifest.json").read_text())["maxima"]
    assert len(got) == len(expected)
    for period, want in expected.items():
        label = {"1HR": "1-HR", "3HR": "3-HR", "24HR": "24-HR"}.get(period, period)
        cells = got[label]
        assert float(cells[1]) == pytest.approx(want["value"])
        assert (float(cells[3]), float(cells[4])) == (want["x"], want["y"])
    assert app.locator("img.map").count() >= 1
    with app.expect_download() as download:
        app.get_by_role("button", name=re.compile(r"\.out$")).click()
    assert b"AERMOD Finishes Successfully" in Path(download.value.path()).read_bytes()


def test_b02_build_a_project_with_forms_and_save_it(app):
    from pyaermod.gui_v2.project_io import project_from_json

    step(app, "Sources")
    app.get_by_role("button", name="Add source").click()
    app.get_by_label("Source id").fill("STACK1")
    app.get_by_label("Source id").dispatch_event("change")
    app.get_by_label(re.compile("^Stack height")).fill("50")
    app.get_by_label(re.compile("^Stack height")).dispatch_event("change")
    app.get_by_role("button", name="Save", exact=True).click()
    app.wait_for_selector("td:has-text('STACK1')")
    assert app.locator("#plan svg").count() == 1

    step(app, "Receptors")
    app.get_by_label("Receptor type").select_option("DiscreteReceptor")
    app.get_by_role("button", name="Add receptors").click()
    app.get_by_role("button", name="Save", exact=True).click()
    app.wait_for_selector("td:has-text('DiscreteReceptor')")

    step(app, "Meteorology")
    app.get_by_role("button", name=re.compile("^Use Albany")).click()
    app.wait_for_selector("td:has-text('AERMET2.PFL')")

    step(app, "Review & Run")
    app.wait_for_selector("text=Ready to run")
    assert app.get_by_role("button", name="Run AERMOD").is_enabled()
    assert "SRCPARAM  STACK1" in app.locator("pre.deck").inner_text()

    project = project_from_json(json.dumps(saved_document(app)))
    (source,) = project.sources.sources
    assert (source.source_id, source.stack_height) == ("STACK1", 50.0)
    assert project.meteorology.surface_file == "AERMET2.SFC"


def test_b03_a_pip_gui_project_opens(app, tmp_path):
    from pyaermod.gui_v2.project_io import save_project
    from pyaermod.gui_v2.state import _empty_project
    from pyaermod.input_generator import PointSource

    project = _empty_project()
    project.control.title_one = "Saved by pyaermod-app"
    project.sources.sources.append(PointSource("CHIMNEY", 10.0, 20.0, stack_diameter=1.0))
    path = save_project(project, tmp_path / "from_pip.json")
    with app.expect_file_chooser() as chooser:
        app.get_by_role("button", name="Open...").click()
    chooser.value.set_files(path)
    app.wait_for_selector("#project-title:has-text('from_pip.json')")
    step(app, "Sources")
    assert app.locator("td:has-text('CHIMNEY')").count() == 1


def test_b04_aermap_output_sets_receptor_elevations(app):
    step(app, "Receptors")
    app.get_by_label("Receptor type").select_option("DiscreteReceptor")
    app.get_by_role("button", name="Add receptors").click()
    for label, value in (("X coord", "500100"), ("Y coord", "4000100")):
        box = app.get_by_label(re.compile(f"^{label}"))
        box.fill(value)
        box.dispatch_event("change")
    app.get_by_role("button", name="Save", exact=True).click()
    app.wait_for_selector("td:has-text('DiscreteReceptor')")
    with app.expect_file_chooser() as chooser:
        app.get_by_role("button", name="Upload elevations...").click()
    chooser.value.set_files(AERMAP / "aermap_receptors.out")
    app.wait_for_selector("text=Elevations read from aermap_receptors.out")
    receptor = saved_document(app)["project"]["receptors"]["discrete_receptors"][0]
    assert (receptor["z_elev"], receptor["z_hill"]) == (105.0, 105.0)


@pytest.mark.parametrize("name", ["Project", "Sources", "Receptors", "Meteorology", "Output",
                                  "Review & Run", "Results"])
def test_b05_every_step_fits_a_phone(app, name):
    app.set_viewport_size({"width": 390, "height": 844})
    step(app, name)
    assert not app.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth")


def _add_point_source(page, name):
    page.get_by_role("button", name="Add source").click()
    box = page.get_by_label("Source id")
    box.fill(name)
    box.dispatch_event("change")
    page.get_by_role("button", name="Save", exact=True).click()
    page.wait_for_selector(f"td:text-is('{name}')")


def test_b06_deleting_while_editing_does_not_save_over_another_source(app):
    step(app, "Sources")
    for name in ("A", "B", "C"):
        _add_point_source(app, name)
    app.get_by_role("button", name="Edit B").click()
    app.get_by_role("button", name="Delete A").click()
    # The editor closed with the delete, so nothing can be saved over C.
    assert app.get_by_role("button", name="Save", exact=True).count() == 0
    names = app.locator("tbody tr td:first-child").all_inner_texts()
    assert names == ["B", "C"]


def test_b07_a_value_pyaermod_refuses_does_not_replace_the_kept_project(app):
    title = app.get_by_label("Title one")
    title.fill("Kept title")
    title.dispatch_event("change")
    app.wait_for_timeout(1200)                       # checked and kept
    app.locator("summary:has-text('Advanced')").click()
    chemistry = app.get_by_label("Chemistry")
    chemistry.fill('"OLM"')                          # valid JSON, not a chemistry object
    chemistry.dispatch_event("change")
    app.wait_for_timeout(1200)
    app.reload()
    app.wait_for_selector("#app:not([hidden])")
    assert app.get_by_label("Title one").input_value() == "Kept title"


def test_b08_a_value_that_does_not_parse_stops_the_editor_saving(app):
    step(app, "Sources")
    _add_point_source(app, "STACK1")
    app.get_by_role("button", name="Edit STACK1").click()
    height = app.get_by_label("Stack height")
    height.fill("abc")
    height.dispatch_event("change")
    assert app.locator(".field-error:visible").inner_text() == "Enter a number."
    app.get_by_role("button", name="Save", exact=True).click()
    # Refused, named, and still open with the text to correct.
    assert "Not saved: correct Stack height" in app.locator("#error").inner_text()
    assert height.input_value() == "abc"
    height.fill("65")
    height.dispatch_event("change")
    assert app.locator(".field-error:visible").count() == 0
    app.get_by_role("button", name="Save", exact=True).click()
    app.wait_for_selector("button:has-text('Add source')")
    source = saved_document(app)["project"]["sources"]["sources"][0]
    assert source["stack_height"] == 65
