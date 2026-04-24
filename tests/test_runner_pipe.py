"""Regression tests for AERMODRunner pipe-buffer behavior.

Before the v1.5 fix, AERMODRunner.run() used subprocess.run(capture_output=True)
which routes stdout/stderr through OS pipes (~64 KB buffer on Linux). On
runs that produce more than the buffer size of stdout and no one is
reading, subprocess.run deadlocks until the timeout expires.

These tests verify the current file-redirect approach survives a fake
binary that writes many megabytes to stdout.
"""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from pyaermod.runner import AERMODRunner, _read_capped


@pytest.fixture
def chatty_aermod_exe(tmp_path):
    """A fake AERMOD binary that writes ~4 MB of text to stdout.

    4 MB is well above any plausible OS pipe buffer (typically 64 KB
    on Linux, 8 KB on macOS); subprocess.run(capture_output=True) on
    the old code path would deadlock here.
    """
    if platform.system() == "Windows":
        pytest.skip("fake-binary fixture assumes POSIX shell")
    exe = tmp_path / "aermod"
    exe.write_text(
        "#!/bin/bash\n"
        # 4 MB: 40k lines x 100 bytes each
        "yes 'AERMOD chatty diagnostic line '"
        "'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUV' | head -40000\n"
        "exit 0\n"
    )
    exe.chmod(0o755)
    return exe


class TestReadCapped:
    def test_small_file_returned_entirely(self, tmp_path):
        p = tmp_path / "small.txt"
        p.write_text("hello world")
        assert _read_capped(p, max_bytes=100) == "hello world"

    def test_missing_file_returns_empty(self, tmp_path):
        assert _read_capped(tmp_path / "nope.txt") == ""

    def test_large_file_returns_tail_with_marker(self, tmp_path):
        p = tmp_path / "big.txt"
        # 10_000 bytes
        p.write_text("x" * 10_000)
        result = _read_capped(p, max_bytes=1_000)
        assert result.startswith("[...truncated:")
        assert "9,000 bytes omitted" in result
        # Tail contains the last 1000 x's
        assert result.endswith("x" * 1_000)


class TestPipeBufferDeadlock:
    """The canonical regression: a chatty fake binary that would have
    deadlocked on the old capture_output=True path."""

    def test_4mb_stdout_run_completes(self, chatty_aermod_exe, tmp_path):
        """4 MB of stdout must not deadlock. On the old pipe-based path
        this test would hit the default timeout (3600s in runner.py)
        and fail; on the file-redirect path it completes in well under
        a second."""
        runner = AERMODRunner(executable_path=chatty_aermod_exe,
                              log_level="WARNING")
        # Make a dummy input file
        inp = tmp_path / "test.inp"
        inp.write_text("CO STARTING\nCO FINISHED\n")

        # 30s timeout; file-redirect path should complete in <1s
        result = runner.run(str(inp), working_dir=str(tmp_path),
                            timeout=30)

        # Fake binary doesn't produce .out / .err / .sum so the runner
        # reports success=False, but the subprocess itself MUST have
        # completed (i.e. no TimeoutExpired).
        assert "timed out" not in (result.error_message or "").lower()
        # Runtime was a fraction of the timeout
        assert result.runtime_seconds is not None
        assert result.runtime_seconds < 5.0

    def test_captured_stdout_is_truncated_not_oom(self, chatty_aermod_exe, tmp_path):
        """The captured stdout on a huge run must be capped, not loaded
        in full into memory."""
        runner = AERMODRunner(executable_path=chatty_aermod_exe,
                              log_level="WARNING")
        inp = tmp_path / "test.inp"
        inp.write_text("CO STARTING\nCO FINISHED\n")
        result = runner.run(str(inp), working_dir=str(tmp_path),
                            timeout=30)

        # Captured stdout should be at most ~1 MB (the _read_capped cap);
        # the raw file is ~4 MB. Either a truncation marker is present
        # or the content is bounded.
        if result.stdout:
            assert len(result.stdout) <= 1_100_000  # 1 MB + marker slack
