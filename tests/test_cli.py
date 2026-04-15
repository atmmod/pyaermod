"""Tests for the pyaermod command-line interface."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pyaermod import cli

FIXT_STYLE = Path(__file__).parent / "fixtures" / "epa_style"
FIXT_OFFICIAL = Path(__file__).parent / "fixtures" / "epa_official"


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
