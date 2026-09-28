"""J9: start a long run, watch its progress and cancel it.

What the user must see (PLAN-gui.md): progress advances with AERMOD's day
count, and other steps stay usable during the run. Cancel stops the
process without leaving an orphaned ``aermod``, and the status reads
"Cancelled".

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

import pytest

from .harness import REAL_AERMOD, process_running
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
def test_j09_progress_follows_the_day_count(gui, step, known_gap, run_dir):
    _start_long_run(gui, run_dir)
    step("running")
    with known_gap("WP-G4", "the run blocks the server: no progress, no other step responds"):
        gui.run.expect_progress_day(61)
        gui.sources.editor_value("STACK1", "stack height")
        gui.run.expect_progress_day(64)
    gui.run.wait_until_finished()


@SLOW
def test_j09_cancel_stops_the_run(gui, step, known_gap, run_dir, journey):
    _start_long_run(gui, run_dir)
    step("running")
    with known_gap("WP-G4", "no Cancel button"):
        gui.run.cancel()
    gui.run.reports_cancelled()
    step("cancelled")
    started = journey.server.fake_events("start")
    assert started, "AERMOD was never started"
    left = [e["pid"] for e in started if process_running(e["pid"])]
    assert not left, f"cancel left aermod running: pids {left}"
