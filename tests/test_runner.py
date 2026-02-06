"""
Unit tests for PyAERMOD runner

Tests the runner infrastructure without requiring a real AERMOD binary.
"""

import pytest
import tempfile
import os
from pathlib import Path
from datetime import datetime
from pyaermod_runner import (
    AERMODRunResult,
    AERMODRunner,
    BatchRunner,
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
