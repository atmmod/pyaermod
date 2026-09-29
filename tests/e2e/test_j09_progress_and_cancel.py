"""J9: start a long run, watch its progress and cancel it.

What the user must see (PLAN-gui.md): progress advances with AERMOD's day
count, and other steps stay usable during the run. Cancel stops the
process without leaving an orphaned ``aermod``, and the status reads
"Cancelled". WP-G2's review added two checks (PLAN-gui.md, "Notes from
WP-G2"): a double-click on Run starts exactly one AERMOD, and another
browser tab stays usable while a run goes on.

The long run is a recording replayed with a pause between stdout lines,
so these tests belong to tier T2 only: the real binary finishes the
reference scenario in about 0.1 s. The recording is ``albany_e480``, the
reference scenario with the GUI's default averaging periods, because the
current GUI cannot enter the ``albany_success`` periods (WP-G3); a
cancelled run never reaches the E480 check, so its outcome is irrelevant.

Today the run blocks the server's event loop, so nothing on the page
responds until AERMOD exits.
"""

from __future__ import annotations

import time

import pytest

from .harness import REAL_AERMOD, process_running
from .pages import App
from .reference import E480_AVERAGING_PERIODS, enter_reference_scenario

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(REAL_AERMOD, reason="needs the slow recording (tier T2)"),
]

# Seven stdout lines one second apart: setup, days 61 to 64, output, fatal.
SLOW = pytest.mark.aermod_recording("albany_e480", delay=1.0)


def _start_long_run(gui, run_dir) -> None:
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*E480_AVERAGING_PERIODS)
    gui.run.set_working_directory(run_dir)
    gui.run.start()


@SLOW
def test_j09_progress_follows_the_day_count(gui, step, run_dir):
    _start_long_run(gui, run_dir)
    step("running")
    gui.run.expect_progress_day(61)
    gui.sources.editor_value("STACK1", "stack height")
    gui.run.expect_progress_day(64)
    gui.run.wait_until_finished()


@SLOW
def test_j09_cancel_stops_the_run(gui, step, run_dir, journey):
    _start_long_run(gui, run_dir)
    step("running")
    gui.run.cancel()
    gui.run.reports_cancelled()
    step("cancelled")
    started = journey.server.fake_events("start")
    assert started, "AERMOD was never started"
    left = [e["pid"] for e in started if process_running(e["pid"])]
    assert not left, f"cancel left aermod running: pids {left}"


@SLOW
def test_j09_a_double_click_starts_one_aermod(gui, step, run_dir, journey):
    gui.open()
    enter_reference_scenario(gui)
    gui.project.set_averaging_periods(*E480_AVERAGING_PERIODS)
    gui.run.set_working_directory(run_dir)
    gui.run.double_click_start()
    step("running")
    gui.run.wait_until_finished()
    started = journey.server.fake_events("start")
    assert len(started) == 1, f"a double-click started {len(started)} AERMOD runs"


@SLOW
def test_j09_another_tab_stays_usable_during_a_run(gui, step, run_dir, journey):
    _start_long_run(gui, run_dir)
    gui.run.expect_progress_day(61)
    other = App(journey.page.context.new_page(), gui.url, journey=journey).open()
    begun = time.monotonic()
    for name in ("Sources", "Receptors", "Meteorology", "Project"):
        other.open_step(name)
    took = time.monotonic() - begun
    step("running")
    assert took < 5, f"switching four steps in another tab took {took:.1f} s during a run"
    gui.run.expect_progress_day(64)
    gui.run.wait_until_finished()
