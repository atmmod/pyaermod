"""J2: the reference scenario with averaging periods 1 and ANNUAL.

What the user must see (PLAN-gui.md): before the run, a warning that
ANNUAL needs a full year of met data. If the user runs anyway, the status
reads "Failed", the message table lists E480 with its text, and Results
does not present concentrations as valid.

AERMOD aborts this run with fatal error E480 and still exits with code 0
(recording ``albany_e480``). The GUI used to report that as a success
(defect D1); since WP-G1 the runner requires AERMOD's own completion
banner and no fatal errors, so the failed status is asserted outright.
The warning and the failed run are separate tests, so that the failed
status is checked whether or not the warning exists.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from .reference import E480_AVERAGING_PERIODS, enter_reference_scenario

pytestmark = pytest.mark.e2e

ANNUAL_NEEDS_A_YEAR = re.compile(r"ANNUAL.*\b(year|12 months)\b", re.I)


@pytest.mark.aermod_recording("albany_e480")
def test_j02_warns_before_an_annual_run_on_short_met(gui, step):
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*E480_AVERAGING_PERIODS)
    gui.run.open()
    step("before_run")
    gui.run.expect_warning(ANNUAL_NEEDS_A_YEAR)


@pytest.mark.aermod_recording("albany_e480")
def test_j02_run_anyway_reports_failure(gui, step, known_gap, run_dir):
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*E480_AVERAGING_PERIODS)
    gui.run.set_working_directory(run_dir)
    gui.run.start()
    gui.run.wait_until_finished()
    step("run_finished")

    gui.run.reports_failure()
    gui.run.expect_message("E480", "Less than 1yr")

    gui.results.open()
    step("results")
    gui.results.expect_failed_run_without_valid_results()


@pytest.mark.aermod_recording("missing_met")
def test_j02_a_missing_surface_file_blocks_the_run(gui, step, run_dir, tmp_path):
    """AERMOD would stop in setup with E500 (recording ``missing_met``): the
    GUI says so before the run, in the header, the badge and the checklist
    alike (code-G3), and does not start it."""
    missing = tmp_path / "met" / "MISSING.SFC"
    gui.open()
    enter_reference_scenario(gui, surface_file=missing)
    gui.project.set_averaging_periods(*E480_AVERAGING_PERIODS)
    gui.run.set_working_directory(run_dir)
    step("blocked")
    expect(gui.header).to_contain_text("Not ready to run: 1 problem in Meteorology")
    gui.expect_step_status("Meteorology", "error")
    gui.run.expect_checklist_names(f"Surface file {missing} does not exist")
    gui.run.expect_run_blocked()
