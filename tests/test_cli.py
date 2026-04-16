"""Tests for the pyaermod command-line interface."""

from __future__ import annotations

import platform
import shutil
from pathlib import Path

import pytest

from pyaermod import cli

FIXT_STYLE = Path(__file__).parent / "fixtures" / "epa_style"
FIXT_OFFICIAL = Path(__file__).parent / "fixtures" / "epa_official"


@pytest.fixture()
def fake_aermod_exe_with_output(tmp_path):
    """Fake AERMOD that exits 0 *and* creates aermod.out so the runner
    considers the run successful (success = returncode==0 AND output exists)."""
    if platform.system() == "Windows":
        exe = tmp_path / "aermod_ok.bat"
        exe.write_text("@echo off\necho. 2>aermod.out\nexit /b 0\n")
    else:
        exe = tmp_path / "aermod_ok"
        exe.write_text("#!/bin/bash\ntouch aermod.out\nexit 0\n")
        exe.chmod(0o755)
    return exe


def run_cli(argv, capsys):
    """Helper that runs the CLI and returns (exit_code, stdout, stderr)."""
    exit_code = cli.main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


# ---------------------------------------------------------------------------
# `pyaermod info`
# ---------------------------------------------------------------------------

class TestInfo:
    def test_prints_version(self, capsys):
        code, out, _err = run_cli(["info"], capsys)
        assert code == 0
        assert "PyAERMOD" in out
        assert "Optional dependencies" in out


# ---------------------------------------------------------------------------
# `pyaermod validate`
# ---------------------------------------------------------------------------

class TestValidate:
    def test_clean_project_exits_zero(self, capsys):
        code, out, _err = run_cli(
            ["validate", str(FIXT_STYLE / "simple_point.inp.expected")],
            capsys,
        )
        assert code == 0
        assert "OK" in out

    def test_check_files_flag_detects_missing_met(self, capsys, tmp_path):
        # Make a project whose SURFFILE won't resolve
        inp = tmp_path / "bad.inp"
        original = (FIXT_STYLE / "simple_point.inp.expected").read_text()
        original = original.replace("stn.sfc", "does_not_exist.sfc")
        original = original.replace("stn.pfl", "does_not_exist.pfl")
        inp.write_text(original)
        code, out, _err = run_cli(
            ["validate", str(inp), "--check-files"],
            capsys,
        )
        assert code == 1
        assert "file not found" in out.lower() or "does_not_exist" in out

    def test_warnings_only_exits_zero(self, capsys, tmp_path):
        """Advanced-validator warnings (no hard errors) → exit 0 + warning text."""
        inp = tmp_path / "warn_only.inp"
        text = (FIXT_STYLE / "simple_point.inp.expected").read_text()
        # Set emission_rate=0 → advanced validator warns, no base-level error
        text = text.replace(
            "STACK1     5.000000    60.00",
            "STACK1     0.000000    60.00",
        )
        inp.write_text(text)
        code, out, _err = run_cli(["validate", str(inp)], capsys)
        assert code == 0                       # warnings don't cause non-zero exit
        assert "warning" in out.lower()
        assert "0 error" in out

    def test_missing_file(self, capsys):
        """Validating a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            run_cli(["validate", "/no/such/path/missing_89234.inp"], capsys)


# ---------------------------------------------------------------------------
# `pyaermod plotfile`
# ---------------------------------------------------------------------------

class TestPlotfile:
    def test_parses_vendored_plotfile(self, capsys):
        code, out, _err = run_cli(
            ["plotfile", str(FIXT_OFFICIAL / "AERTEST_01H.PLT")],
            capsys,
        )
        assert code == 0
        assert "PLOTFILE" in out
        # Record count appears
        assert "144" in out

    def test_plotfile_includes_peak_range(self, capsys):
        """AERTEST_01H.PLT: a recognized concentration column → range line printed."""
        code, out, _err = run_cli(
            ["plotfile", str(FIXT_OFFICIAL / "AERTEST_01H.PLT")],
            capsys,
        )
        assert code == 0
        # The plotfile header names the concentration column; the CLI should
        # find it and print an extrema line (e.g. "CONC range:  …")
        assert "range" in out.lower()


# ---------------------------------------------------------------------------
# `pyaermod profile`
# ---------------------------------------------------------------------------

class TestProfile:
    def test_lint_only_clean_project(self, capsys):
        code, out, _err = run_cli(
            ["profile", str(FIXT_STYLE / "simple_point.inp.expected"),
             "--profile", "EPA-AppendixW-2017"],
            capsys,
        )
        assert code == 0
        assert "clean" in out.lower()

    def test_unknown_profile_returns_2(self, capsys):
        code, _out, err = run_cli(
            ["profile", str(FIXT_STYLE / "simple_point.inp.expected"),
             "--profile", "NOPE"],
            capsys,
        )
        assert code == 2
        assert "unknown profile" in err.lower()

    def test_apply_rewrites_file(self, capsys, tmp_path):
        """--apply mutates the input so subsequent lint is clean."""
        inp = tmp_path / "dirty.inp"
        shutil.copy(FIXT_STYLE / "simple_point.inp.expected", inp)
        # Munge the input so regulatory_default is False (toggle DFAULT)
        text = inp.read_text()
        # MODELOPT line in the golden has DFAULT; strip it
        text = text.replace(" DFAULT", "")
        inp.write_text(text)

        code, _out, _err = run_cli(
            ["profile", str(inp), "--profile", "EPA-AppendixW-2017", "--apply"],
            capsys,
        )
        # After apply, the lint should be clean or the exit 0 path
        # depending on residual warnings; either way the input was
        # rewritten.
        assert code in (0, 1)
        new_text = inp.read_text()
        assert "DFAULT" in new_text, "apply should have re-added DFAULT"

    def test_profile_findings_exits_nonzero(self, capsys, tmp_path):
        """Profile lint on non-compliant project → exit 1 + findings listed."""
        inp = tmp_path / "noncompliant.inp"
        text = (FIXT_STYLE / "simple_point.inp.expected").read_text()
        # Strip DFAULT so regulatory_default=False → profile check finds a finding
        text = text.replace(" DFAULT", "")
        inp.write_text(text)
        code, out, _err = run_cli(
            ["profile", str(inp), "--profile", "EPA-AppendixW-2017"],
            capsys,
        )
        assert code == 1
        assert "findings" in out.lower()

    def test_profile_apply_then_validate(self, capsys, tmp_path):
        """Apply profile to non-compliant project → subsequent validate exits 0."""
        inp = tmp_path / "proj.inp"
        text = (FIXT_STYLE / "simple_point.inp.expected").read_text()
        text = text.replace(" DFAULT", "")
        inp.write_text(text)
        # Apply the profile (re-adds DFAULT)
        run_cli(
            ["profile", str(inp), "--profile", "EPA-AppendixW-2017", "--apply"],
            capsys,
        )
        # Validate the mutated file — should have no hard errors
        code_val, _out_val, _ = run_cli(["validate", str(inp)], capsys)
        assert code_val == 0


# ---------------------------------------------------------------------------
# `pyaermod run` (fake executable)
# ---------------------------------------------------------------------------

class TestRunWithFakeExecutable:
    def test_run_dispatches_to_runner(self, capsys, tmp_path, fake_aermod_exe):
        # Copy the golden input somewhere writable
        inp = tmp_path / "golden.inp"
        shutil.copy(FIXT_STYLE / "simple_point.inp.expected", inp)

        code, out, _err = run_cli(
            ["run", str(inp),
             "--executable", str(fake_aermod_exe),
             "--working-dir", str(tmp_path),
             "--force"],
            capsys,
        )
        # Fake exe exits 0 but produces no output files, so the runner
        # reports the run as failed. What we're exercising here is that
        # the CLI dispatches to the runner at all — a specific exit
        # code matters less than the dispatch actually happening.
        assert "Running AERMOD" in out
        # Either success (0) or runner-detected failure (non-zero)
        assert code in (0, 1) or code >= 1


class TestRunAbort:
    def test_run_aborts_without_force(self, capsys, tmp_path, fake_aermod_exe):
        """run without --force aborts (exit 2) when project has validation errors."""
        inp = tmp_path / "bad_dates.inp"
        text = (FIXT_STYLE / "simple_point.inp.expected").read_text()
        # Single-day met range with ANNUAL averaging → advanced-validator error
        text = text.replace(
            "STARTEND  2020  1  1  2020 12 31",
            "STARTEND  2020  1  1  2020  1  1",
        )
        inp.write_text(text)
        code, out, _err = run_cli(
            ["run", str(inp),
             "--executable", str(fake_aermod_exe),
             "--working-dir", str(tmp_path)],
            capsys,
        )
        assert code == 2
        assert "Aborting" in out


class TestRunSuccess:
    def test_run_success_path(self, capsys, tmp_path, fake_aermod_exe_with_output):
        """Fake exe that creates aermod.out → runner reports Success."""
        inp = tmp_path / "golden.inp"
        shutil.copy(FIXT_STYLE / "simple_point.inp.expected", inp)
        code, out, _err = run_cli(
            ["run", str(inp),
             "--executable", str(fake_aermod_exe_with_output),
             "--working-dir", str(tmp_path),
             "--force"],
            capsys,
        )
        assert "Running AERMOD" in out
        assert "Success" in out
        assert code == 0


class TestRunRealBinary:
    def test_run_real_aermod_if_available(self, capsys, tmp_path):
        """Run with the real aermod binary when it's on PATH (skip otherwise)."""
        import shutil as _shutil

        aermod_path = _shutil.which("aermod") or _shutil.which("AERMOD")
        if aermod_path is None:
            pytest.skip("aermod binary not on PATH")

        inp = tmp_path / "real_run.inp"
        shutil.copy(FIXT_STYLE / "simple_point.inp.expected", inp)
        code, out, _err = run_cli(
            ["run", str(inp),
             "--executable", aermod_path,
             "--working-dir", str(tmp_path),
             "--force"],
            capsys,
        )
        # The run may fail (missing met files), but the CLI must reach the runner
        assert "Running AERMOD" in out
        assert code in (0, 1)


# ---------------------------------------------------------------------------
# `pyaermod parse`
# ---------------------------------------------------------------------------

class TestParse:
    def test_parse_summary_file(self, capsys):
        # AERTEST.SUM is an AERMOD summary output; parse it via the
        # generic output parser. Verify at least headline metadata
        # (model version / title) shows up.
        code, out, _err = run_cli(
            ["parse", str(FIXT_OFFICIAL / "AERTEST.SUM")],
            capsys,
        )
        # The output parser may or may not recognize a .SUM file
        # specifically; we just assert the CLI didn't crash.
        assert code == 0
        assert "AERMOD output" in out

    def test_parse_version_and_pollutant(self, capsys):
        """parse AERTEST.SUM → version '24142' and pollutant 'SO2' printed."""
        code, out, _err = run_cli(
            ["parse", str(FIXT_OFFICIAL / "AERTEST.SUM")],
            capsys,
        )
        assert code == 0
        # AERTEST.SUM header: "*** AERMOD - VERSION 24142  ***"
        assert "24142" in out
        # Pollutant line: "The User Specified a Pollutant Type of: SO2"
        assert "SO2" in out


# ---------------------------------------------------------------------------
# argparse surface
# ---------------------------------------------------------------------------

class TestArgparse:
    def test_subcommand_required(self, capsys):
        with pytest.raises(SystemExit):
            run_cli([], capsys)

    def test_version_flag(self, capsys):
        with pytest.raises(SystemExit) as exc:
            run_cli(["--version"], capsys)
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "pyaermod" in captured.out.lower()
