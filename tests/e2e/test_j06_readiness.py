"""J6: open Review & Run on a blank project.

What the user must see (PLAN-gui.md): the Run button is disabled; the
checklist names the missing source, receptors and met files, and each
item links to its step; fixing each problem clears its item.
"""

from __future__ import annotations

import re

import pytest

from .reference import GRID, PROFILE_FILE, STACK, SURFACE_FILE

pytestmark = pytest.mark.e2e

SOURCE = re.compile(r"\bsources?\b", re.I)
RECEPTORS = re.compile(r"\breceptors?\b", re.I)
MET = re.compile(r"\bmet(eorolog\w*)?\b|\bsurface file\b", re.I)


def test_j06_blank_project_is_not_ready_to_run(gui, step):
    gui.open()
    gui.run.open()
    step("blank_review")
    gui.run.expect_run_blocked()
    gui.run.expect_checklist_names(SOURCE, RECEPTORS, MET)

    gui.run.follow_checklist_item(SOURCE)
    gui.expect_current_step("Sources")
    gui.sources.add_point_source(**STACK)
    gui.run.open()
    gui.run.expect_checklist_clear_of(SOURCE)

    gui.run.follow_checklist_item(RECEPTORS)
    gui.expect_current_step("Receptors")
    gui.receptors.add_polar_grid(**GRID)
    gui.run.open()
    gui.run.expect_checklist_clear_of(RECEPTORS)

    gui.run.follow_checklist_item(MET)
    gui.expect_current_step("Meteorology")
    gui.meteorology.set_met_files(SURFACE_FILE, PROFILE_FILE)
    gui.run.open()
    gui.run.expect_checklist_clear_of(MET)
    step("ready")
    gui.run.expect_run_allowed()
