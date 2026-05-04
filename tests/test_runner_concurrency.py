"""Concurrent-run safety tests for AERMODRunner.

Two AERMODRunner.run() calls into the same working_dir would, on the
old code path, overwrite each other's `aermod.inp` symlink and output
files silently. Now they serialize via an fcntl/msvcrt lock on a
sentinel file in the run dir.
"""

from __future__ import annotations

import platform
import threading
import time
from pathlib import Path

import pytest

from pyaermod.runner import (
    AERMODRunner,
    _acquire_dir_lock,
    _release_dir_lock,
)


@pytest.fixture
def slow_aermod_exe(tmp_path):
    """Fake AERMOD that sleeps 1s before exiting — long enough for a
    second concurrent run to attempt to start and have to wait."""
    if platform.system() == "Windows":
        pytest.skip("fixture is POSIX-only")
    exe = tmp_path / "aermod"
    exe.write_text("#!/bin/bash\nsleep 1\nexit 0\n")
    exe.chmod(0o755)
    return exe


class TestLockHelpers:
    def test_acquire_and_release_roundtrip(self, tmp_path):
        lock = tmp_path / ".lock"
        fh = _acquire_dir_lock(lock)
        assert fh is not None
        assert lock.exists()
        _release_dir_lock(fh)
        # Second acquire after release must succeed
        fh2 = _acquire_dir_lock(lock)
        _release_dir_lock(fh2)

    def test_release_none_is_noop(self):
        """Defensive: releasing None must not raise (pattern used in
        the runner.run finally block when acquisition fails)."""
        _release_dir_lock(None)


class TestConcurrentRuns:
    @pytest.mark.skipif(platform.system() == "Windows",
                        reason="POSIX-only fake binary")
    def test_two_runs_in_same_dir_serialize(self, slow_aermod_exe, tmp_path):
        """Two concurrent runs into the same working_dir must serialize:
        their elapsed wall-clock time is at least 2 * (per-run runtime),
        not 1x. Without the lock, they'd overlap and the second would
        clobber the first's aermod.inp symlink before AERMOD finished
        reading it."""
        runner = AERMODRunner(executable_path=slow_aermod_exe,
                              log_level="WARNING")

        # Two separate input files (so the runner's symlink target
        # differs between calls) but the same working_dir.
        inp_a = tmp_path / "a.inp"
        inp_b = tmp_path / "b.inp"
        for p in (inp_a, inp_b):
            p.write_text("CO STARTING\nCO FINISHED\n")

        results = {}

        def worker(label, inp):
            results[label] = runner.run(str(inp), working_dir=str(tmp_path),
                                         timeout=30)

        t0 = time.perf_counter()
        threads = [
            threading.Thread(target=worker, args=("a", inp_a)),
            threading.Thread(target=worker, args=("b", inp_b)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - t0

        # Each run sleeps 1s; serialized total >= 2s. Allow small
        # overhead. Without the lock, the two runs would overlap and
        # finish in ~1s.
        assert elapsed >= 1.8, (
            f"runs completed in {elapsed:.2f}s; expected >= 1.8s "
            "if serialized by the lock"
        )
        assert "a" in results and "b" in results
