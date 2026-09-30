"""J3: fill in a project, click New, then edit the new project and save it.

What the user must see (PLAN-gui.md): every step shows the blank project
(title, source table, receptor table, met paths and an empty Results
step), the unsaved-changes marker clears, and edits made after New appear
in the saved file.

Defect D3 (fixed in WP-G2): New replaced the project, but every widget
stayed bound to the old project's objects, so the screen kept showing the
old project and later edits were lost. The two symptoms are separate
tests.
"""

from __future__ import annotations

import uuid

import pytest

from pyaermod.gui_v2.project_io import load_project

from .reference import GRID, PROFILE_FILE, STACK, SURFACE_FILE

pytestmark = pytest.mark.e2e


def test_j03_new_shows_the_blank_project(gui, step):
    gui.open()
    blank_title = gui.project.title()
    gui.project.set_titles("Project A")
    gui.sources.add_point_source(**STACK)
    gui.receptors.add_polar_grid(**GRID)
    gui.meteorology.set_met_files(SURFACE_FILE, PROFILE_FILE)
    gui.expect_unsaved_changes(True)
    step("project_a")

    gui.project.new()
    step("after_new")
    gui.expect_unsaved_changes(False)
    gui.project.expect_title(blank_title)
    gui.sources.expect_ids([])
    gui.receptors.expect_names([])
    gui.meteorology.expect_met_files("", "")
    gui.results.expect_no_run()


def test_j03_edits_after_new_are_saved(gui, step):
    gui.open()
    gui.project.set_titles("Project A")
    gui.project.new()
    gui.project.set_titles("Project B")
    gui.sources.add_point_source(**STACK)
    step("edited_after_new")

    saved = gui.project.save_as(f"j03-{uuid.uuid4().hex[:8]}.json")
    gui.expect_unsaved_changes(False)
    project = load_project(saved)
    assert project.control.title_one == "Project B"
    assert [s.source_id for s in project.sources.sources] == ["STACK1"]
