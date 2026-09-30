"""AERMODRunner.start(): AERMOD in the background, with progress and cancel.

The AERMOD here is the end-to-end fake (``tests/e2e/fake_aermod.py``),
which replays a recording of the real v26135 binary line by line,
optionally pausing between lines (``PYAERMOD_E2E_DELAY``). Its stdout is
the real AERMOD's, so the progress lines parsed are AERMOD's own.
"""

from __future__ import annotations

import platform
import threading
import time
from pathlib import Path

import pytest

from pyaermod import runner as runner_module
from pyaermod.runner import (
    AERMODProgress,
    AERMODRunner,
    _acquire_dir_lock,
    _release_dir_lock,
    parse_progress_line,
)
from tests.e2e.harness import RECORDINGS, install_fake_aermod, process_running

pytestmark = pytest.mark.skipif(platform.system() == "Windows",
                                reason="the fake AERMOD is a POSIX script")


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """(runner, deck) for the albany_e480 recording; set the delay with the env var."""
    exe = install_fake_aermod(tmp_path / "bin")
    monkeypatch.setenv("PYAERMOD_E2E_RECORDING", str(RECORDINGS / "albany_e480"))
    monkeypatch.delenv("PYAERMOD_E2E_DELAY", raising=False)
    monkeypatch.delenv("PYAERMOD_E2E_FAKE_LOG", raising=False)
    work = tmp_path / "run"
    work.mkdir()
    deck = work / "deck.inp"
    deck.write_text((RECORDINGS / "albany_e480" / "aermod.inp").read_text())
    return AERMODRunner(executable_path=exe, log_level="WARNING"), deck


def _script(tmp_path: Path, body: str) -> AERMODRunner:
    exe = tmp_path / "aermod"
    exe.write_text(f"#!/bin/sh\n{body}\n")
    exe.chmod(0o755)
    return AERMODRunner(executable_path=exe, log_level="WARNING")


def _deck(tmp_path: Path) -> Path:
    deck = tmp_path / "deck.inp"
    deck.write_text("CO STARTING\nCO FINISHED\n")
    return deck


def test_parse_progress_line():
    assert parse_progress_line("+Now Processing Data For Day No.   61 of 1988") == (61, 1988)
    assert parse_progress_line("+Now Processing Events For Day No.  5 of 2020") == (5, 2020)
    assert parse_progress_line("+Now Processing SETUP Information") is None


def test_a_background_run_reports_each_stage_and_ends_like_run(fake):
    runner, deck = fake
    seen = []
    finished = []
    run = runner.start(deck, working_dir=deck.parent, on_progress=seen.append,
                       on_finish=finished.append)
    result = run.wait(30)
    assert run.done and run.result is result and finished == [result]
    assert [(p.stage, p.day, p.days_processed) for p in seen] == [
        ("setup", 0, 0), ("day", 61, 1), ("day", 62, 2), ("day", 63, 3), ("day", 64, 4),
        ("output", 64, 4)]
    assert all(p.year in (0, 1988) for p in seen)
    assert run.progress == seen[-1]
    # AERMOD's verdict, as run() reads it: fatal error E480.
    assert result.success is False and result.cancelled is False
    assert "E480" in [m.code for m in result.messages]
    assert Path(result.output_file) == deck.with_suffix(".out")
    assert "Now Processing Data For Day No.   64 of 1988" in result.stdout
    assert not (deck.parent / "aermod.inp").exists()

    same = runner.run(deck, working_dir=deck.parent)
    assert (same.success, same.messages, same.message_counts) == (
        result.success, result.messages, result.message_counts)


def test_cancel_stops_aermod_and_leaves_no_process(fake, monkeypatch):
    runner, deck = fake
    monkeypatch.setenv("PYAERMOD_E2E_DELAY", "0.5")
    day = threading.Event()
    run = runner.start(deck, working_dir=deck.parent,
                       on_progress=lambda p: day.set() if p.stage == "day" else None)
    assert day.wait(20), "AERMOD reported no day"
    pid = run.pid
    assert pid is not None and process_running(pid)
    assert run.cancel() is True and run.cancel_requested
    assert run.cancel() is False                         # once is enough
    result = run.wait(20)
    assert result.cancelled is True and result.success is False
    assert result.error_message == "Cancelled before AERMOD finished"
    assert result.output_file is None                    # AERMOD wrote none
    assert repr(result).startswith("AERMODRunResult(CANCELLED")
    assert not process_running(pid)
    assert run.cancel() is False                         # it has ended


def test_a_cancelled_run_does_not_claim_an_earlier_runs_out_file(fake, monkeypatch):
    runner, deck = fake
    runner.start(deck, working_dir=deck.parent).wait(30)
    assert deck.with_suffix(".out").exists()             # left by the first run
    monkeypatch.setenv("PYAERMOD_E2E_DELAY", "0.5")
    started = threading.Event()
    run = runner.start(deck, working_dir=deck.parent, on_progress=lambda p: started.set())
    assert started.wait(20)
    run.cancel()
    assert run.wait(20).output_file is None


@pytest.mark.parametrize("background", [True, False])
def test_a_crashed_run_does_not_claim_an_earlier_runs_out_file(fake, tmp_path, background):
    runner, deck = fake
    runner.run(deck, working_dir=deck.parent)
    assert deck.with_suffix(".out").exists()             # E480, left by the first run
    crash = _script(tmp_path, "echo '+Now Processing SETUP Information'\nkill -SEGV $$")
    if background:
        result = crash.start(deck, working_dir=deck.parent).wait(20)
    else:
        result = crash.run(deck, working_dir=deck.parent)
    assert result.return_code == -11 and result.success is False
    assert result.output_file is None
    assert result.messages == [] and result.message_counts == {}
    assert result.error_message.startswith(
        "AERMOD was stopped by signal 11 (SIGSEGV) before writing deck.out")
    assert "E480" not in result.error_message


def test_a_run_cancelled_before_aermod_starts_never_starts_it(fake):
    runner, deck = fake
    # Another run holds the working directory: this one waits for it.
    lock = _acquire_dir_lock(deck.parent / ".pyaermod.lock")
    try:
        run = runner.start(deck, working_dir=deck.parent)
        time.sleep(0.2)
        assert run.pid is None and not run.done
        assert run.cancel() is True
    finally:
        _release_dir_lock(lock)
    result = run.wait(20)
    assert run.pid is None
    assert result.cancelled and result.error_message == "Cancelled before AERMOD started"


def test_an_aermod_that_ignores_sigterm_is_killed(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "CANCEL_GRACE_SECONDS", 0.3)
    runner = _script(tmp_path, "trap '' TERM\necho '+Now Processing SETUP Information'\n"
                               "while :; do sleep 0.05; done")
    started = threading.Event()
    run = runner.start(_deck(tmp_path), on_progress=lambda p: started.set())
    assert started.wait(10)
    run.cancel()
    result = run.wait(10)
    assert result.cancelled and not process_running(run.pid)


def test_a_run_past_its_timeout_is_killed(tmp_path):
    runner = _script(tmp_path, "exec sleep 30")
    run = runner.start(_deck(tmp_path), timeout=0.3)
    result = run.wait(10)
    assert result.success is False and not result.cancelled
    assert result.error_message == "Execution timed out after 0.3 seconds"
    assert not process_running(run.pid)


def test_gfortran_is_asked_not_to_buffer_stdout(tmp_path, monkeypatch):
    monkeypatch.delenv("GFORTRAN_UNBUFFERED_PRECONNECTED", raising=False)
    runner = _script(tmp_path, 'echo "buffering=$GFORTRAN_UNBUFFERED_PRECONNECTED"')
    result = runner.start(_deck(tmp_path)).wait(10)
    assert "buffering=y" in result.stdout


def test_a_missing_deck_ends_the_run_at_once(tmp_path):
    runner = _script(tmp_path, "exit 0")
    result = runner.start(tmp_path / "nope.inp").wait(5)
    assert result.success is False and "Input file not found" in result.error_message


def test_a_binary_that_cannot_start_is_a_failed_result(tmp_path):
    runner = _script(tmp_path, "exit 0")
    runner.executable.unlink()
    result = runner.start(_deck(tmp_path)).wait(5)
    assert result.success is False and "No such file" in result.error_message


def test_wait_times_out_while_the_run_goes_on(tmp_path):
    runner = _script(tmp_path, "exec sleep 5")
    run = runner.start(_deck(tmp_path))
    with pytest.raises(TimeoutError):
        run.wait(0.1)
    assert run.result is None
    run.cancel()
    assert run.wait(10).cancelled


def test_callbacks_that_raise_do_not_break_the_run(fake, caplog):
    runner, deck = fake

    def boom(_):
        raise RuntimeError("callback bug")

    result = runner.start(deck, working_dir=deck.parent, on_progress=boom,
                          on_finish=boom).wait(30)
    assert "E480" in [m.code for m in result.messages]
    assert "on_progress callback raised" in caplog.text
    assert "on_finish callback raised" in caplog.text


def test_exiting_python_stops_runs_still_going(tmp_path):
    runner = _script(tmp_path, "echo '+Now Processing SETUP Information'\nexec sleep 30")
    started = threading.Event()
    run = runner.start(_deck(tmp_path), on_progress=lambda p: started.set())
    assert started.wait(10)
    runner_module._stop_active_runs()          # what atexit calls
    run.wait(10)
    assert not process_running(run.pid)


def test_progress_is_a_frozen_record():
    p = AERMODProgress(stage="day", day=61, year=1988, days_processed=1)
    with pytest.raises(AttributeError):
        p.day = 62  # type: ignore[misc]
