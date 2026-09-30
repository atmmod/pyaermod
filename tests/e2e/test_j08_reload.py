"""J8: reload the browser in the middle of a project, and again after a run.

What the user must see (PLAN-gui.md): the project and the last run are
restored, or, if WP-G2 chooses the fallback, an unsaved-changes warning
appears before unload. WP-G2 chose the preferred behaviour (PLAN-gui.md,
"Reload decision"): each browser tab keeps its session, which these
tests pin. Before WP-G2 a reload created a fresh session and lost both
the project and the run; the two losses are separate tests.
"""

from __future__ import annotations

import pytest

from .reference import E480_AVERAGING_PERIODS, STACK, enter_reference_scenario

pytestmark = pytest.mark.e2e


def test_j08_reload_keeps_the_project(gui, step):
    gui.open()
    gui.project.set_titles("Survives a reload")
    gui.sources.add_point_source(**STACK)
    step("before_reload")
    gui.reload()
    step("after_reload")
    gui.project.expect_title("Survives a reload")
    gui.sources.expect_ids(["STACK1"])


@pytest.mark.aermod_recording("albany_e480")
def test_j08_reload_keeps_the_last_run(gui, step, run_dir):
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*E480_AVERAGING_PERIODS)
    gui.run.set_working_directory(run_dir)
    gui.run.start()
    gui.run.wait_until_finished()
    step("run_finished")
    gui.reload()
    step("after_reload")
    gui.run.expect_last_run_shown()
