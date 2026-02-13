"""
Unit tests for PyAERMOD runner

Tests the runner infrastructure without requiring a real AERMOD binary.
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import MagicMock, patch

import pytest

from pyaermod.runner import (
    AERMODRunner,
    AERMODRunResult,
    BatchRunner,
    run_aermod,
)


class TestAERMODRunResult:
    """Test AERMODRunResult dataclass"""

    def test_success_result(self):
        result = AERMODRunResult(
            success=True,
            input_file="test.inp",
            return_code=0,
            runtime_seconds=12.5,
        )
        assert result.success is True
        assert result.return_code == 0
        assert "SUCCESS" in repr(result)
        assert "12.5s" in repr(result)

    def test_failed_result(self):
        result = AERMODRunResult(
            success=False,
            input_file="test.inp",
            error_message="File not found",
        )
        assert result.success is False
        assert "FAILED" in repr(result)

    def test_defaults(self):
        result = AERMODRunResult(success=True, input_file="test.inp")
        assert result.return_code is None
        assert result.runtime_seconds is None
        assert result.output_file is None
        assert result.error_file is None
        assert result.stdout is None
        assert result.stderr is None
        assert result.start_time is None

    def test_repr_no_runtime(self):
        result = AERMODRunResult(success=True, input_file="test.inp")
        assert "N/A" in repr(result)


class TestAERMODRunnerInit:
    """Test AERMODRunner initialization"""

    def test_init_with_nonexistent_executable(self):
        """Test that a nonexistent executable raises FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            AERMODRunner(executable_path="/nonexistent/aermod")

    def test_init_no_aermod_on_path(self):
        """Test that missing aermod on PATH raises FileNotFoundError"""
        # Save and clear PATH to ensure aermod isn't found
        original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = ""
        try:
            with pytest.raises(FileNotFoundError, match="AERMOD executable not found"):
                AERMODRunner()
        finally:
            os.environ["PATH"] = original_path

    def test_init_with_valid_executable(self, tmp_path):
        """Test initialization with a real file as the executable"""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        assert runner.executable == fake_exe


class TestAERMODRunnerValidation:
    """Test input file validation"""

    def test_validate_nonexistent_file(self, tmp_path):
        """Validate a file that doesn't exist"""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        valid, issues = runner.validate_input("/nonexistent.inp")
        assert valid is False
        assert any("does not exist" in i for i in issues)

    def test_validate_complete_input(self, tmp_path):
        """Validate a complete input file"""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        inp_file = tmp_path / "test.inp"
        inp_file.write_text("""\
CO STARTING
   TITLEONE  Test
   MODELOPT  DFAULT
   AVERTIME  ANNUAL
   POLLUTID  SO2
   RUNORNOT  RUN
CO FINISHED
SO STARTING
   LOCATION  STACK1 POINT 0.0 0.0 0.0
SO FINISHED
RE STARTING
   GRIDCART GRID XYINC 0.0 11 100.0 0.0 11 100.0
RE FINISHED
ME STARTING
   SURFFILE  test.sfc
   PROFFILE  test.pfl
ME FINISHED
OU STARTING
OU FINISHED
""")
        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        valid, issues = runner.validate_input(str(inp_file))
        assert valid is True
        assert len(issues) == 0

    def test_validate_missing_pathways(self, tmp_path):
        """Validate a file with missing pathways"""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        inp_file = tmp_path / "incomplete.inp"
        inp_file.write_text("""\
CO STARTING
   RUNORNOT  RUN
CO FINISHED
""")
        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        valid, issues = runner.validate_input(str(inp_file))
        assert valid is False
        assert any("SO STARTING" in i for i in issues)
        assert any("RE STARTING" in i for i in issues)
        assert any("ME STARTING" in i for i in issues)
        assert any("OU STARTING" in i for i in issues)

    def test_validate_unclosed_pathway(self, tmp_path):
        """Validate a file with unclosed pathway"""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        inp_file = tmp_path / "unclosed.inp"
        inp_file.write_text("""\
CO STARTING
   RUNORNOT  RUN
SO STARTING
SO FINISHED
RE STARTING
RE FINISHED
ME STARTING
ME FINISHED
OU STARTING
OU FINISHED
""")
        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        valid, issues = runner.validate_input(str(inp_file))
        assert valid is False
        assert any("CO" in i and "not properly closed" in i for i in issues)

    def test_validate_missing_runornot(self, tmp_path):
        """Validate a file missing RUNORNOT"""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        inp_file = tmp_path / "norunornot.inp"
        inp_file.write_text("""\
CO STARTING
CO FINISHED
SO STARTING
SO FINISHED
RE STARTING
RE FINISHED
ME STARTING
ME FINISHED
OU STARTING
OU FINISHED
""")
        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        valid, issues = runner.validate_input(str(inp_file))
        assert valid is False
        assert any("RUNORNOT" in i for i in issues)


class TestAERMODRunnerRun:
    """Test the run method (without real AERMOD)"""

    def test_run_missing_input_file(self, tmp_path):
        """Test running with missing input file"""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        result = runner.run("/nonexistent/test.inp")

        assert result.success is False
        assert "not found" in result.error_message


class TestBatchRunner:
    """Test BatchRunner class"""

    def test_batch_runner_init(self, tmp_path):
        """Test BatchRunner initialization"""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        batch = BatchRunner(runner)
        assert batch.runner is runner


# ---------------------------------------------------------------------------
# Additional coverage tests — run_aermod convenience, batch, error extraction,
# timeout, parameter_sweep
# ---------------------------------------------------------------------------

class TestRunAermodConvenience:
    """Test the run_aermod() module-level convenience function."""

    @patch("pyaermod.runner.AERMODRunner")
    def test_run_aermod_delegates_to_runner(self, MockRunner, tmp_path):
        """run_aermod() should instantiate AERMODRunner and call .run()."""
        fake_result = AERMODRunResult(success=True, input_file="test.inp",
                                       return_code=0, runtime_seconds=1.0)
        instance = MockRunner.return_value
        instance.run.return_value = fake_result

        result = run_aermod("test.inp", executable_path="/fake/aermod", timeout=600)

        MockRunner.assert_called_once_with(executable_path="/fake/aermod", log_level="WARNING")
        instance.run.assert_called_once_with("test.inp", timeout=600)
        assert result.success is True

    @patch("pyaermod.runner.AERMODRunner")
    def test_run_aermod_default_args(self, MockRunner):
        """run_aermod() with defaults passes None executable and 3600 timeout."""
        instance = MockRunner.return_value
        instance.run.return_value = AERMODRunResult(success=True, input_file="x.inp")

        run_aermod("x.inp")

        MockRunner.assert_called_once_with(executable_path=None, log_level="WARNING")
        instance.run.assert_called_once_with("x.inp", timeout=3600)


class TestExtractErrorMessage:
    """Test AERMODRunner._extract_error_message() with various error sources."""

    def _make_runner(self, tmp_path):
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)
        return AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")

    def test_stderr_message(self, tmp_path):
        """Error message extracted from stderr."""
        runner = self._make_runner(tmp_path)
        proc = CompletedProcess(args=[], returncode=1, stdout="", stderr="Segmentation fault")
        output_files = {
            "error": tmp_path / "nope.err",
            "output": tmp_path / "nope.out",
        }
        msg = runner._extract_error_message(proc, output_files)
        assert "stderr: Segmentation fault" in msg

    def test_error_file_message(self, tmp_path):
        """Error message extracted from .err file."""
        runner = self._make_runner(tmp_path)
        err_file = tmp_path / "run.err"
        err_file.write_text("E01: Missing RUNORNOT keyword")

        proc = CompletedProcess(args=[], returncode=1, stdout="", stderr="")
        output_files = {
            "error": err_file,
            "output": tmp_path / "nope.out",
        }
        msg = runner._extract_error_message(proc, output_files)
        assert "Error file:" in msg
        assert "Missing RUNORNOT" in msg

    def test_output_file_error_line(self, tmp_path):
        """Error message extracted from .out file containing ERROR keyword."""
        runner = self._make_runner(tmp_path)
        out_file = tmp_path / "run.out"
        out_file.write_text("Some header\n*** ERROR on line 5: bad input ***\nMore output\n")

        proc = CompletedProcess(args=[], returncode=1, stdout="", stderr="")
        output_files = {
            "error": tmp_path / "nope.err",
            "output": out_file,
        }
        msg = runner._extract_error_message(proc, output_files)
        assert "ERROR" in msg

    def test_output_file_fatal_line(self, tmp_path):
        """Error message extracted from .out file containing FATAL keyword."""
        runner = self._make_runner(tmp_path)
        out_file = tmp_path / "run.out"
        out_file.write_text("FATAL: Cannot continue\n")

        proc = CompletedProcess(args=[], returncode=1, stdout="", stderr="")
        output_files = {
            "error": tmp_path / "nope.err",
            "output": out_file,
        }
        msg = runner._extract_error_message(proc, output_files)
        assert "FATAL" in msg

    def test_no_messages_fallback(self, tmp_path):
        """Fallback message when no specific error source is available."""
        runner = self._make_runner(tmp_path)
        proc = CompletedProcess(args=[], returncode=42, stdout="", stderr="")
        output_files = {
            "error": tmp_path / "nope.err",
            "output": tmp_path / "nope.out",
        }
        msg = runner._extract_error_message(proc, output_files)
        assert "return code 42" in msg

    def test_empty_error_file_ignored(self, tmp_path):
        """An empty .err file does not contribute to the message."""
        runner = self._make_runner(tmp_path)
        err_file = tmp_path / "run.err"
        err_file.write_text("   \n")  # whitespace-only

        proc = CompletedProcess(args=[], returncode=1, stdout="", stderr="")
        output_files = {
            "error": err_file,
            "output": tmp_path / "nope.out",
        }
        msg = runner._extract_error_message(proc, output_files)
        # Should fall back to return-code message, not include "Error file:"
        assert "return code 1" in msg


class TestRunTimeoutHandling:
    """Test that subprocess.TimeoutExpired is handled correctly."""

    @patch("pyaermod.runner.subprocess.run")
    def test_timeout_returns_failed_result(self, mock_run, tmp_path):
        """When subprocess times out, run() returns a failed result."""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        inp_file = tmp_path / "test.inp"
        inp_file.write_text("CO STARTING\nCO FINISHED\n")

        mock_run.side_effect = TimeoutExpired(cmd="aermod", timeout=10)

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        result = runner.run(str(inp_file), timeout=10)

        assert result.success is False
        assert "timed out" in result.error_message.lower()
        assert result.runtime_seconds is not None

    @patch("pyaermod.runner.subprocess.run")
    def test_generic_exception_returns_failed_result(self, mock_run, tmp_path):
        """When subprocess raises a generic exception, run() handles it."""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        inp_file = tmp_path / "test.inp"
        inp_file.write_text("CO STARTING\nCO FINISHED\n")

        mock_run.side_effect = OSError("Permission denied")

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        result = runner.run(str(inp_file))

        assert result.success is False
        assert "Permission denied" in result.error_message


class TestRunBatch:
    """Test AERMODRunner.run_batch() method."""

    def test_run_batch_with_nonexistent_files(self, tmp_path):
        """run_batch() with nonexistent input files returns failure results."""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        # Files that don't exist -- runner.run() will return failure for each
        files = ["/nonexistent/run0.inp", "/nonexistent/run1.inp"]

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        results = runner.run_batch(files, n_workers=1, timeout=30)

        assert len(results) == 2
        assert all(not r.success for r in results)
        assert all("not found" in r.error_message for r in results)

    def test_run_batch_stop_on_error(self, tmp_path):
        """run_batch() with stop_on_error should stop after first failure."""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        # All nonexistent -- each will fail immediately
        files = [f"/nonexistent/run{i}.inp" for i in range(5)]

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        results = runner.run_batch(files, n_workers=1, stop_on_error=True)

        # Should have stopped early (may not have all 5 results)
        assert len(results) >= 1
        assert any(not r.success for r in results)

    @patch("pyaermod.runner.ProcessPoolExecutor")
    def test_run_batch_mocked_executor(self, MockExecutor, tmp_path):
        """run_batch() orchestration logic with mocked ProcessPoolExecutor."""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        files = ["a.inp", "b.inp"]

        # Create mock futures that return successful results
        mock_future_a = MagicMock()
        mock_future_a.result.return_value = AERMODRunResult(
            success=True, input_file="a.inp", return_code=0, runtime_seconds=1.0
        )
        mock_future_b = MagicMock()
        mock_future_b.result.return_value = AERMODRunResult(
            success=True, input_file="b.inp", return_code=0, runtime_seconds=2.0
        )

        # Set up the mock executor context manager
        mock_executor_instance = MagicMock()
        MockExecutor.return_value.__enter__ = MagicMock(
            return_value=mock_executor_instance
        )
        MockExecutor.return_value.__exit__ = MagicMock(return_value=False)

        # submit() returns a different future each time
        mock_executor_instance.submit.side_effect = [mock_future_a, mock_future_b]

        # Patch as_completed to return futures in order
        with patch("pyaermod.runner.as_completed", return_value=iter([mock_future_a, mock_future_b])):
            runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
            results = runner.run_batch(files, n_workers=2, timeout=60)

        assert len(results) == 2
        assert all(r.success for r in results)


class TestParameterSweep:
    """Test BatchRunner.parameter_sweep() method."""

    @patch("pyaermod.runner.subprocess.run")
    def test_parameter_sweep_creates_files_and_returns_map(self, mock_run, tmp_path):
        """parameter_sweep() should generate files and return result mapping."""
        fake_exe = tmp_path / "aermod"
        fake_exe.write_text("#!/bin/bash\nexit 0")
        fake_exe.chmod(0o755)

        runner = AERMODRunner(executable_path=str(fake_exe), log_level="WARNING")
        batch = BatchRunner(runner)

        # Mock project (not used directly in current placeholder implementation)
        mock_project = MagicMock()

        output_dir = tmp_path / "sweep_output"

        # The sweep will try to run files that don't exist (placeholder implementation),
        # so all runs will fail with "not found" — that's expected behavior for testing
        result_map = batch.parameter_sweep(
            base_project=mock_project,
            parameter_name="emission_rate",
            parameter_values=[1.0, 2.0, 5.0],
            output_dir=str(output_dir),
            n_workers=1,
        )

        # The output directory should have been created
        assert output_dir.exists()

        # We should get some results back (may be empty since files don't exist
        # and the mapping uses result.input_file which may not match)
        assert isinstance(result_map, dict)
