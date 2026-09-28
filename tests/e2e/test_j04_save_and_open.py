"""J4: Save As, click New, then Open the saved file through the upload control.

What the user must see (PLAN-gui.md): every step shows the saved values
again, the header shows the file name, and no exception appears in the
server log.

Defect D4: Open crashes on NiceGUI 3, whose upload event has no ``name``
or ``content``; the traceback appears only in the server log.
"""

from __future__ import annotations

import uuid

import pytest

from .reference import GRID, PROFILE_FILE, STACK, STATIONS, SURFACE_FILE

pytestmark = pytest.mark.e2e


def test_j04_save_as_new_open_restores_the_project(gui, step, known_gap):
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
    with known_gap("D4", "Open crashes on NiceGUI 3's upload API"):
        gui.project.open_file(saved)
        gui.expect_server_log_clean()
    step("reopened")

    gui.expect_header_names(name)
    gui.project.expect_title("Saved project")
    gui.project.expect_pollutant("NO2")
    gui.sources.expect_ids(["STACK1"])
    gui.receptors.expect_names(["GRID1"])
    gui.meteorology.expect_met_files(str(SURFACE_FILE), str(PROFILE_FILE))
