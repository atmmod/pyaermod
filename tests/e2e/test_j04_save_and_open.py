"""J4: Save As, click New, then Open the saved file through the upload control.

What the user must see (PLAN-gui.md): every step shows the saved values
again, the header shows the file name, and no exception appears in the
server log.

Defect D4 (fixed in WP-G2): Open crashed on NiceGUI 3, whose upload event
has no ``name`` or ``content``; the traceback appeared only in the server
log. Cancelling the Open dialog while a file is still on its way is not an
error either: NiceGUI 3.17 lets Starlette's ``ClientDisconnect`` reach
uvicorn's log, which the GUI filters out.
"""

from __future__ import annotations

import uuid

import pytest
from playwright.sync_api import expect

from pyaermod.gui_v2.project_io import save_project
from pyaermod.gui_v2.state import _empty_project
from pyaermod.receptors import DiscreteReceptor

from .reference import GRID, PROFILE_FILE, STACK, STATIONS, SURFACE_FILE

pytestmark = pytest.mark.e2e


def test_j04_save_as_new_open_restores_the_project(gui, step):
    gui.open()
    gui.project.set_titles("Saved project", "Reopened by journey J4")
    gui.project.set_pollutant("NO2")
    gui.sources.add_point_source(**STACK)
    gui.receptors.add_polar_grid(**GRID)
    gui.meteorology.set_met_files(SURFACE_FILE, PROFILE_FILE)
    gui.meteorology.set_stations(**STATIONS)
    step("project_built")

    name = f"j04-{uuid.uuid4().hex[:8]}.json"
    saved = gui.project.save_as(name)
    gui.expect_header_names(name)
    gui.expect_unsaved_changes(False)
    step("saved")

    gui.project.new()
    step("after_new")
    gui.project.open_file(saved)
    gui.expect_server_log_clean()
    step("reopened")

    gui.expect_header_names(name)
    gui.project.expect_title("Saved project")
    gui.project.expect_pollutant("NO2")
    gui.sources.expect_ids(["STACK1"])
    gui.receptors.expect_names(["GRID1"])
    gui.meteorology.expect_met_files(str(SURFACE_FILE), str(PROFILE_FILE))


#: Uploads crawl at this many bytes per second while the dialog is cancelled.
_SLOW_UPLOAD = {"offline": False, "latency": 200, "downloadThroughput": -1,
                "uploadThroughput": 2000}
_NORMAL = {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1}


def test_j04_cancelling_open_mid_upload_keeps_the_project(gui, step, journey):
    # A saved project fixture big enough to take seconds at _SLOW_UPLOAD.
    other = _empty_project()
    other.control.title_one = "Must not load"
    other.receptors.discrete_receptors = [DiscreteReceptor(x_coord=float(i), y_coord=0.0)
                                          for i in range(300)]
    big = save_project(other, journey.root / "big-project.json")
    assert big.stat().st_size > 10 * _SLOW_UPLOAD["uploadThroughput"]

    gui.open()
    gui.project.set_titles("Keep me")
    step("before_open")

    cdp = gui.page.context.new_cdp_session(gui.page)
    cdp.send("Network.enable")
    cdp.send("Network.emulateNetworkConditions", _SLOW_UPLOAD)
    gui.project.panel.get_by_role("button", name="Open...").click()
    dialog = gui.dialog()
    with gui.page.expect_file_chooser() as chooser:
        dialog.get_by_role("button", name="Choose File").first.click()
    with gui.page.expect_event("requestfailed", predicate=lambda r: "/upload/" in r.url):
        chooser.value.set_files(str(big))       # auto_upload starts sending at once
        dialog.get_by_role("button", name="Cancel").click()
    expect(dialog).to_be_hidden()
    cdp.send("Network.emulateNetworkConditions", _NORMAL)
    step("cancelled")

    gui.project.expect_title("Keep me")
    gui.expect_unsaved_changes(True)
    gui.expect_server_log_clean()           # the fixture checks again at the end
