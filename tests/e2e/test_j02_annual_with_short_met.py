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

from .reference import E480_AVERAGING_PERIODS, enter_reference_scenario

pytestmark = pytest.mark.e2e

ANNUAL_NEEDS_A_YEAR = re.compile(r"ANNUAL.*\b(year|12 months)\b", re.I)


@pytest.mark.aermod_recording("albany_e480")
def test_j02_warns_before_an_annual_run_on_short_met(gui, step, known_gap):
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*E480_AVERAGING_PERIODS)
    gui.run.open()
    step("before_run")
    with known_gap("WP-G4", "no pre-run ANNUAL warning"):
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
    with known_gap("WP-G4", "no message table listing E480"):
        gui.run.expect_message("E480", "Less than 1yr")

    gui.results.open()
    step("results")
    gui.results.expect_failed_run_without_valid_results()


@pytest.mark.aermod_recording("missing_met")
def test_j02_setup_error_reports_failure(gui, step, known_gap, run_dir, tmp_path):
    gui.open()
    enter_reference_scenario(gui, surface_file=tmp_path / "met" / "MISSING.SFC")
    gui.project.set_averaging_periods(*E480_AVERAGING_PERIODS)
    gui.run.set_working_directory(run_dir)
    gui.run.start()
    gui.run.wait_until_finished()
    step("run_finished")

    gui.run.reports_failure()
    with known_gap("WP-G4", "no message table listing E500"):
        gui.run.expect_message("E500", "SURFFILE")
