"""J1: build the reference scenario through the UI, run it and read Results.

What the user must see (PLAN-gui.md): the run status reads "Succeeded"
with 0 fatal errors; Results shows the four maxima and their location,
and the map renders; the downloaded deck matches the deck on disk.

The current GUI cannot set averaging periods, so the full journey stops
at that step (WP-G3). Defect D2 (Results never refreshes) is independent
of it and is exercised by the second test with the only run the current
GUI can make, its default ``1 ANNUAL``.
"""

from __future__ import annotations

import pytest

from .harness import deck_written_to
from .reference import (
    AVERAGING_PERIODS,
    E480_AVERAGING_PERIODS,
    MAX_LOCATION,
    MAXIMA,
    enter_reference_scenario,
)

pytestmark = pytest.mark.e2e


@pytest.mark.aermod_recording("albany_success")
def test_j01_build_run_and_read_results(gui, step, known_gap, run_dir):
    gui.open()
    step("blank_project")
    enter_reference_scenario(gui, step)
    gui.output.expect_output_type("CONC")
    gui.run.set_working_directory(run_dir)
    step("run_ready")

    with known_gap("WP-G3", "no averaging-period control on the Project step"):
        gui.project.set_averaging_periods(*AVERAGING_PERIODS)

    gui.run.start()
    gui.run.wait_until_finished()
    step("run_finished")
    gui.run.reports_success()
    with known_gap("WP-G4", "no message summary after a run"):
        gui.run.expect_message_counts(fatal=0, warnings=6)

    gui.results.open()
    step("results")
    with known_gap("D2", "Results tab never refreshes after a run"):
        gui.results.expect_maxima(MAXIMA, MAX_LOCATION)
    with known_gap("WP-G5", "no concentration map on Results"):
        gui.results.expect_map()
    with known_gap("WP-G5", "no deck download on Results"):
        downloaded = gui.results.download_deck()
        assert downloaded.read_bytes() == deck_written_to(run_dir).read_bytes()


@pytest.mark.aermod_recording("albany_e480")
def test_j01_results_follow_the_latest_run(gui, step, run_dir):
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*E480_AVERAGING_PERIODS)
    gui.results.expect_no_run()
    gui.run.set_working_directory(run_dir)
    gui.run.start()
    gui.run.wait_until_finished()
    step("run_finished")

    gui.results.open()
    step("results")
    gui.results.expect_showing_run(run_dir)
