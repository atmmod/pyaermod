"""J9: start a long run, watch its progress and cancel it.

What the user must see (PLAN-gui.md): progress advances with AERMOD's day
count, and other steps stay usable during the run. Cancel stops the
process without leaving an orphaned ``aermod``, and the status reads
"Cancelled". WP-G2's review added two checks (PLAN-gui.md, "Notes from
WP-G2"): a double-click on Run starts exactly one AERMOD, and another
browser tab stays usable while a run goes on. WP-G4's review added two
more: New during a run stops AERMOD and leaves no progress or Cancel,
and stopping the server (SIGTERM or SIGHUP) stops AERMOD too.

The long run is a recording replayed with a pause between stdout lines,
so these tests belong to tier T2 only: the real binary finishes the
reference scenario in about 0.1 s. The recording is ``albany_e480``, the
reference scenario with the GUI's default averaging periods; a cancelled
run never reaches the E480 check, so its outcome is irrelevant.
"""

from __future__ import annotations

import os
import re
import signal
import time

import pytest
from playwright.sync_api import expect

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
    begun = time.monotonic()               # loading the tab counts too
    other = App(journey.page.context.new_page(), gui.url, journey=journey).open()
    for name in ("Sources", "Receptors", "Meteorology", "Project"):
        other.open_step(name)
    took = time.monotonic() - begun
    step("other_tab", page=other.page)
    step("running")
    assert took < 5, f"opening another tab and four of its steps took {took:.1f} s during a run"
    # ... and all of it while the run was still going.
    expect(gui.run.status()).to_have_count(0)
    gui.run.expect_progress_day(64)
    gui.run.wait_until_finished()


@SLOW
def test_j09_new_during_a_run_stops_it_and_clears_its_progress(gui, step, run_dir, journey):
    _start_long_run(gui, run_dir)
    gui.run.expect_progress_day(61)
    gui.project.new()
    gui.run.open()
    step("after_new")
    gui.run.expect_no_progress()
    expect(gui.run.panel.get_by_text(re.compile(r"\bnot been run\b", re.I))).to_be_visible()
    started = journey.server.fake_events("start")
    assert started, "AERMOD was never started"
    deadline = time.monotonic() + 15      # SIGTERM, then a kill after 5 s
    left = [e["pid"] for e in started]
    while left and time.monotonic() < deadline:
        time.sleep(0.1)
        left = [pid for pid in left if process_running(pid)]
    assert not left, f"New left aermod running: pids {left}"


@SLOW
@pytest.mark.parametrize("sig", ["SIGTERM", "SIGHUP"])
def test_j09_stopping_the_server_stops_aermod(gui, step, run_dir, journey, sig):
    """A service manager stops the server with SIGTERM, a closed terminal with
    SIGHUP; neither may leave AERMOD writing into the working directory."""
    if not hasattr(signal, sig):
        pytest.skip(f"no {sig} on this platform")
    _start_long_run(gui, run_dir)
    gui.run.expect_progress_day(61)
    step("running")
    started = journey.server.fake_events("start")
    assert started, "AERMOD was never started"
    journey.page.close()                    # the user has gone; the run goes on
    server = journey.server.proc
    os.kill(server.pid, getattr(signal, sig))   # the server only, not its group
    server.wait(timeout=30)
    left = [e["pid"] for e in started if process_running(e["pid"])]
    assert not left, f"stopping the server with {sig} left aermod running: pids {left}"
