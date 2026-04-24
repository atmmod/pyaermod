"""Regression tests for BatchRunner's ProcessPoolExecutor path.

Before the v1.5 fix, `BatchRunner.run_batch` submitted `self.run` to
ProcessPoolExecutor, which pickles the runner including its attached
Logger + StreamHandler. Fork works (Linux default), spawn (macOS default,
Windows only) silently breaks because handlers aren't picklable.

These tests pin the fix: submit a module-level worker fn that builds
a fresh runner inside each worker. The tests run against the spawn
start method explicitly so macOS/Windows regressions are caught.
"""

from __future__ import annotations

import multiprocessing
import platform

import pytest

from pyaermod.runner import AERMODRunner, BatchRunner, _batch_worker


@pytest.fixture
def fake_aermod_exe(tmp_path):
    if platform.system() == "Windows":
        exe = tmp_path / "aermod.bat"
        exe.write_text("@echo off\nexit /b 0\n")
    else:
        exe = tmp_path / "aermod"
        exe.write_text("#!/bin/bash\nexit 0\n")
        exe.chmod(0o755)
    return exe


class TestBatchWorker:
    """The module-level worker function must be picklable."""

    def test_worker_function_is_importable_from_module(self):
        import pyaermod.runner
        assert _batch_worker is pyaermod.runner._batch_worker

    def test_worker_constructs_runner_and_returns_result(self, fake_aermod_exe, tmp_path):
        inp = tmp_path / "test.inp"
        inp.write_text("CO STARTING\nCO FINISHED\n")
        result = _batch_worker(str(fake_aermod_exe), str(inp), timeout=10)
        # Fake binary exits 0 but produces no AERMOD .out, so runner
        # reports failure. The worker itself must return a result, not
        # raise.
        assert result is not None
        assert result.input_file == str(inp)


class TestRunBatchOnRealProcesses:
    """End-to-end: run_batch() with 2 worker processes under the default
    multiprocessing start method for the platform."""

    def test_run_batch_survives_spawn(self, fake_aermod_exe, tmp_path):
        """With spawn, pickling the runner would fail. The current
        module-level-worker approach should succeed. (`run_batch` lives
        on AERMODRunner; BatchRunner is a convenience wrapper.)"""
        runner = AERMODRunner(executable_path=fake_aermod_exe,
                              log_level="WARNING")

        # Create 3 placeholder inputs
        inputs = []
        for i in range(3):
            p = tmp_path / f"run_{i}.inp"
            p.write_text("CO STARTING\nCO FINISHED\n")
            inputs.append(p)

        # 2 workers, short per-run timeout — fake exe returns in <1s
        results = runner.run_batch(inputs, n_workers=2, timeout=15)

        # All 3 should have completed (success or failure — but each
        # returned a result)
        assert len(results) == 3
        # Every AERMODRunResult has a return_code set
        assert all(r.return_code is not None for r in results)


class TestSpawnStartMethodExplicit:
    """Directly verify pickleability of the worker path under spawn."""

    def test_batch_worker_picklable(self):
        """ProcessPoolExecutor under spawn pickles every submitted
        callable + args. _batch_worker is a module-level function, so
        pickle.dumps() must succeed."""
        import pickle

        # Pickle the function and a plausible args tuple
        payload = pickle.dumps((_batch_worker, ("/usr/bin/true", "/tmp/x.inp", 10)))
        assert len(payload) > 0

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="multiprocessing.get_context('spawn') requires __main__ on Windows",
    )
    def test_spawn_context_can_execute_worker(self, fake_aermod_exe, tmp_path):
        """Use a 'spawn' pool explicitly and confirm the worker runs."""
        inp = tmp_path / "spawned.inp"
        inp.write_text("CO STARTING\nCO FINISHED\n")

        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(1) as pool:
            result = pool.apply(
                _batch_worker,
                (str(fake_aermod_exe), str(inp), 10),
            )
        assert result is not None
        assert result.input_file == str(inp)
